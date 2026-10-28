# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import fcntl
import json
import os
import pty
import random
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import zlib

import pytest
from PIL import Image
from terminal_protocol import unwrap_tmux

from kirlian_terminal.artwork_check import (
    check_identity,
    read_replies,
    reply_status,
    safe_text,
    terminal_version,
)


def test_reply_parsing_and_deadline():
    assert reply_status("\x1b_Gi=12;OK\x1b\\", 12) == "OK"
    assert reply_status("\x1b_Gi=13;ENOENT: image not found\x1b\\", 13).startswith("ENOENT")
    assert reply_status("\x1b_Gi=12;OK\x1b\\", 13) == "no reply"
    assert safe_text("\x1b\nhello\r☃") == "hello"
    assert terminal_version("\x1bP>|Ghostty 1.3.1\x1b\\") == "Ghostty 1.3.1"
    assert terminal_version("\x1b[?1;2c") == "no reply"
    reader, writer = os.pipe()
    try:
        os.write(writer, b"\x1b_Gi=12;OK\x1b\\\x1b[?1;2c")
        assert reply_status(read_replies(reader, 0.05), 12) == "OK"
        assert read_replies(reader, 0.01) == ""
    finally:
        os.close(reader)
        os.close(writer)


def test_rgba_transport_preserves_pixels_alpha_and_chunk_boundaries(monkeypatch):
    from textual_image.renderable import tgp

    from kirlian_terminal.graphics import send_pixels

    messages = []
    monkeypatch.setattr(tgp, "_send_tgp_message", lambda **message: messages.append(message))
    raw = random.Random(7).randbytes(64 * 64 * 4)
    send_pixels(Image.frombytes("RGBA", (64, 64), raw), 42)
    assert len(messages) > 1
    assert all(len(message["payload"]) <= 4096 for message in messages)
    assert (messages[0]["f"], messages[0]["s"], messages[0]["v"]) == (32, 64, 64)
    assert messages[-1]["m"] == 0
    assert all(message["m"] == 1 for message in messages[:-1])
    assert all(set(message) == {"m", "q", "payload"} for message in messages[1:])
    data = base64.b64decode("".join(message["payload"] for message in messages))
    assert zlib.decompress(data) == raw


@pytest.mark.parametrize(
    "cancel,rgb_only,multiplexed",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, False),
        (False, False, True),
    ],
)
def test_artwork_check_in_owned_pty(tmp_path, cancel, rgb_only, multiplexed):
    """Exercise replies and cleanup, without claiming real emulator visibility."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 800, 480))
    before = termios.tcgetattr(slave)
    env = dict(os.environ, TERM="xterm-256color", NO_COLOR="1", PATH="")
    env.pop("TMUX", None)
    env.pop("STY", None)
    env["HERDR_SOCKET_PATH"] = "/private/test-only/herdr.sock"
    env["HERDR_PANE_ID"] = "test-private-pane"
    if multiplexed:
        env["TMUX"] = "/tmp/kirlian-test,1,0"
    unused_data = tmp_path / "unused-library"
    report_path = tmp_path / "diagnostics" / "artwork.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "kirlian_terminal",
            "--check-artwork",
            "--data-dir",
            str(unused_data),
            "--artwork-report",
            str(report_path),
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
    )
    output = bytearray()
    responded = set()
    answered = False
    loading = None
    payloads = bytearray()
    images = {}
    command = re.compile(rb"\x1b_G([^\x1b]*)\x1b\\|\x1b\[c|\x1b\[>q")
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.03)[0]:
                output.extend(os.read(master, 65536))
            # Only completed envelopes reach the simulated outer terminal.
            stream = output
            if multiplexed:
                stream = unwrap_tmux(output)
            for match in command.finditer(stream):
                if match.start() in responded:
                    continue
                responded.add(match.start())
                if match[1] is None:
                    os.write(
                        master,
                        b"\x1bP>|Test Terminal 1.0\x1b\\"
                        if match[0] == b"\x1b[>q"
                        else b"\x1b[?1;2c",
                    )
                    continue
                header, _, payload = match[1].partition(b";")
                fields = dict(part.split(b"=", 1) for part in header.split(b",") if b"=" in part)
                status = None
                if fields.get(b"a") == b"q":
                    status = b"OK"
                elif payload:
                    if loading is None:
                        loading = fields
                        payloads.clear()
                    payloads.extend(payload)
                    if fields.get(b"m") == b"0":
                        fields = loading
                        loading = None
                        # Generic support need not mean every format works.
                        status = b"EINVAL: unsupported format"
                        if fields.get(b"f") in ((b"24",) if rgb_only else (b"24", b"32")):
                            data = base64.b64decode(payloads)
                            if fields.get(b"o") == b"z":
                                data = zlib.decompress(data)
                            dimensions = (int(fields[b"s"]), int(fields[b"v"]))
                            mode = "RGB" if fields[b"f"] == b"24" else "RGBA"
                            assert len(data) == dimensions[0] * dimensions[1] * len(mode)
                            images[fields[b"i"]] = Image.frombytes(mode, dimensions, data).convert(
                                "RGBA"
                            )
                            status = b"OK"
                elif fields.get(b"a") == b"p":
                    status = b"OK" if fields[b"i"] in images else b"ENOENT: image not found"
                if status is not None and fields.get(b"q") != b"2":
                    os.write(master, b"\x1b_Gi=" + fields[b"i"] + b";" + status + b"\x1b\\")
            if not answered and b"then Enter:" in output:
                answered = True
                if cancel:
                    process.send_signal(signal.SIGINT)
                else:
                    os.write(master, b"A F\n" if rgb_only else b"A B C E F\n")
            if process.poll() is not None:
                while select.select([master], [], [], 0)[0]:
                    output.extend(os.read(master, 65536))
                break
        assert process.poll() == 0, output[-2000:]
        assert termios.tcgetattr(slave) == before
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        os.close(master)
        os.close(slave)

    assert answered
    assert not unused_data.exists()
    observation = "cancelled" if cancel else "A F" if rgb_only else "A B C E F"
    assert f"Visible: {observation}".encode() in output
    assert b"A RGB uncompressed: OK" in output
    assert b"D PNG: EINVAL: unsupported format" in output
    assert b"Kirlian artwork check v2" in output
    assert b"NO_COLOR: set" in output
    assert b"\x1b[?1049l" in output
    assert loading is None
    assert len(images) == (1 if rgb_only else 4)
    assert all(image.getpixel((0, 0)) == (51, 37, 56, 255) for image in images.values())
    assert all(
        image.getpixel((image.width // 2, image.height // 2)) == (238, 233, 221, 255)
        for image in images.values()
    )
    report = json.loads(report_path.read_text())
    assert report["visible"] == observation
    assert report["source_sha256"] == check_identity()["source_sha256"]
    assert report["terminal_version"] == "Test Terminal 1.0"
    assert report["samples"]["A"]["reply"] == "OK"
    assert report["samples"]["C"]["reply"] == ("EINVAL: unsupported format" if rgb_only else "OK")
    assert report["samples"]["E"]["reply"] == ("ENOENT: image not found" if rgb_only else "OK")
    assert str(tmp_path) not in report_path.read_text()
    assert report["environment"]["HERDR_SOCKET_PATH"] == "set"
    assert report["environment"]["HERDR_PANE_ID"] == "set"
    assert "/private/test-only" not in report_path.read_text()
    assert "test-private-pane" not in report_path.read_text()
    if multiplexed:
        # Every graphics operation, including deletion, must be wrapped. Text
        # placeholders remain regular terminal cells for tmux to lay out.
        remainder = re.sub(rb"\x1bPtmux;((?:[^\x1b]|\x1b\x1b)*)\x1b\\", b"", output)
        assert b"\x1b_G" not in remainder
        assert chr(0x10EEEE).encode() in remainder
        assert b"a=d,d=I" in stream
