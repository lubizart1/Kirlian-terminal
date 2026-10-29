# SPDX-License-Identifier: GPL-3.0-or-later
"""One owned mpv process, a persistent JSON connection, and observed state."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import METER, AmpSettings, Levels, Tempo
from .i18n import _


class PlaybackError(Exception):
    """An actionable playback failure for display in the interface."""


@dataclass
class PlaybackState:
    paused: bool = True
    idle: bool = True
    loading: bool = False
    started_serial: int = 0
    position: float = 0
    duration: float = 0
    volume: float = 50
    index: int = -1
    path: str = ""
    playlist: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    codec: str = ""
    bitrate: int = 0
    samplerate: int = 0
    channels: int = 0

    def consume(self, event: dict[str, Any]) -> None:
        if event.get("event") == "property-change":
            value = event.get("data")
            name = event.get("name")
            if name == "pause" and value is not None:
                self.paused = bool(value)
            elif name == "idle-active":
                self.idle = bool(value)
            elif name == "time-pos":
                self.position = float(value or 0)
            elif name == "duration":
                self.duration = float(value or 0)
            elif name == "volume" and value is not None:
                self.volume = float(value)
            elif name == "playlist-pos":
                self.index = int(value) if value is not None else -1
            elif name == "path":
                self.path = str(value or "")
            elif name == "playlist":
                self.playlist = value or []
            elif name == "audio-codec-name":
                self.codec = str(value or "")
            elif name == "audio-bitrate":
                self.bitrate = int(value or 0)
            elif name == "audio-params":
                params = value if isinstance(value, dict) else {}
                self.samplerate = int(params.get("samplerate") or 0)
                self.channels = int(params.get("channel-count") or 0)
        elif event.get("event") == "start-file":
            self.loading = True
            self.position = self.duration = 0
            self.error = ""
        elif event.get("event") == "file-loaded":
            self.loading = False
            self.started_serial += 1
        elif event.get("event") == "end-file":
            self.loading = False
            if event.get("reason") == "error":
                self.error = _(
                    "Cannot play this file: {reason}",
                    reason=event.get("file_error") or _("unsupported or unreadable"),
                )


class Player:
    def __init__(
        self,
        on_change: Callable[[PlaybackState], None] | None = None,
        executable: str | None = None,
        extra_args: Sequence[str] = (),
    ) -> None:
        self.state = PlaybackState()
        self.on_change = on_change or (lambda state: None)
        self.executable = executable
        self.extra_args = extra_args
        self.process: asyncio.subprocess.Process | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.reader_task: asyncio.Task | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.request_id = 0
        self.temp: tempfile.TemporaryDirectory | None = None
        self.lock = asyncio.Lock()
        self.closing = False

    async def start(self) -> None:
        executable = self.executable or shutil.which("mpv")
        if not executable:
            raise PlaybackError(_("mpv is missing. Install it, then restart Kirlian (see README)."))
        self.temp = tempfile.TemporaryDirectory(prefix="kirlian-", dir="/tmp")
        socket = Path(self.temp.name) / "mpv.sock"
        try:
            self.process = await asyncio.create_subprocess_exec(
                executable,
                "--no-config",
                "--load-scripts=no",
                "--idle=yes",
                "--no-terminal",
                "--no-video",
                "--audio-display=no",
                "--ytdl=no",
                "--access-references=no",
                "--input-default-bindings=no",
                "--pause=yes",
                "--volume=50",
                "--loop-playlist=no",
                "--loop-file=no",
                f"--af={METER}",
                f"--input-ipc-server={socket}",
                *self.extra_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            for _attempt in range(300):
                if self.process.returncode is not None:
                    raise PlaybackError(_("mpv could not start. Check your mpv installation."))
                try:
                    reader, self.writer = await asyncio.open_unix_connection(
                        socket, limit=16 * 1024 * 1024
                    )
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    await asyncio.sleep(0.05)
            else:
                raise PlaybackError(
                    _(
                        "mpv did not start within 15 seconds. "
                        "Run mpv --version, then restart Kirlian."
                    )
                )
            self.reader_task = asyncio.create_task(self._read(reader))
            for index, name in enumerate(
                (
                    "pause",
                    "idle-active",
                    "time-pos",
                    "duration",
                    "volume",
                    "playlist-pos",
                    "path",
                    "playlist",
                    "audio-codec-name",
                    "audio-bitrate",
                    "audio-params",
                ),
                1,
            ):
                await self.command("observe_property", index, name)
        except (OSError, PlaybackError) as error:
            await self.close()
            raise PlaybackError(str(error)) from error
        except asyncio.CancelledError:
            await self.close()
            raise

    async def _read(self, reader: asyncio.StreamReader) -> None:
        try:
            while line := await reader.readline():
                try:
                    event = json.loads(line.decode("utf-8", errors="replace"))
                except (ValueError, UnicodeError):
                    continue
                future = self.pending.get(event.get("request_id"))
                if future is not None and not future.done():
                    if event.get("error") == "success":
                        future.set_result(event.get("data"))
                    else:
                        future.set_exception(PlaybackError(f"mpv: {event.get('error')}"))
                elif "event" in event:
                    self.state.consume(event)
                    self.on_change(self.state)
        except (OSError, ValueError):
            pass
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(PlaybackError(_("The playback connection closed.")))
            if not self.closing:
                self.state.idle = True
                self.state.loading = False
                self.state.error = "mpv stopped unexpectedly. Restart Kirlian to reconnect."
                self.on_change(self.state)

    async def command(self, *args: object) -> Any:
        if not self.writer or self.writer.is_closing():
            raise PlaybackError(_("Playback is unavailable. Restart Kirlian after checking mpv."))
        self.request_id += 1
        request_id = self.request_id
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            self.writer.write(
                (json.dumps({"command": args, "request_id": request_id}) + "\n").encode("utf-8")
            )
            await self.writer.drain()
            return await asyncio.wait_for(future, timeout=3)
        except (OSError, TimeoutError) as error:
            raise PlaybackError(_("mpv did not respond. Try again or restart Kirlian.")) from error
        finally:
            self.pending.pop(request_id, None)

    async def play(self, paths: Sequence[str], index: int = 0) -> None:
        if not paths or not 0 <= index < len(paths):
            return
        async with self.lock:
            await self.command("set_property", "pause", True)
            await self.command("loadfile", paths[0], "replace")
            for path in paths[1:]:
                await self.command("loadfile", path, "append")
            await self.command("playlist-play-index", index)
            await self.command("set_property", "pause", False)

    async def control(self, *args: object) -> Any:
        async with self.lock:
            if args and args[0] == "seek" and (self.state.loading or self.state.idle):
                raise PlaybackError(_("Wait for a track to start before seeking."))
            return await self.command(*args)

    async def append(self, paths: Sequence[str]) -> None:
        async with self.lock:
            for path in paths:
                await self.command("loadfile", path, "append")

    async def jump(self, index: int) -> None:
        async with self.lock:
            await self.command("playlist-play-index", index)
            await self.command("set_property", "pause", False)

    async def toggle_pause(self) -> None:
        async with self.lock:
            if self.state.idle and self.state.playlist:
                await self.command("playlist-play-index", 0)
                await self.command("set_property", "pause", False)
            else:
                await self.command("cycle", "pause")

    async def levels(self) -> Levels | None:
        """The latest measured frame, or None when nothing is playing."""
        try:
            return Levels.parse(await self.command("get_property", "af-metadata/meter"))
        except PlaybackError:
            return None

    async def apply_amp(self, amp: AmpSettings) -> None:
        """Install or remove the equalizer chain and set ReplayGain."""
        async with self.lock:
            await self.command("af", "set", amp.filters())
            await self.command("set_property", "replaygain", amp.replaygain)

    async def apply_tempo(self, tempo: Tempo) -> None:
        """mpv changes speed without changing pitch unless tape mode links them."""
        async with self.lock:
            await self.command("set_property", "audio-pitch-correction", not tempo.tape)
            await self.command("set_property", "speed", tempo.speed)
            await self.command("set_property", "pitch", tempo.pitch)

    async def tune(self, target: str, command: str, value: str) -> None:
        """Adjust one stage of the running equalizer without rebuilding it."""
        await self.command("af-command", "eq", command, value, target)

    async def close(self) -> None:
        self.closing = True
        if self.process and self.process.returncode is None:
            with contextlib.suppress(PlaybackError):
                await self.command("quit")
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        self.process.kill()
                    await self.process.wait()
        if self.writer:
            self.writer.close()
            with contextlib.suppress(OSError):
                await self.writer.wait_closed()
        if self.reader_task:
            self.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader_task
        if self.temp:
            self.temp.cleanup()
