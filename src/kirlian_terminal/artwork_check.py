"""An isolated, local check of native images and the character fallback."""

import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from PIL import Image, ImageDraw

from . import __version__
from .terminal_support import read_replies, safe_text, terminal_version

SAMPLES = {
    "A": "RGB uncompressed",
    "B": "RGBA uncompressed",
    "C": "RGBA compressed",
    "D": "PNG",
    "E": "Player placeholders",
    "F": "Block fallback",
}


def sample_image() -> Image.Image:
    """Use generated pixels so this check needs no library or private artwork."""
    image = Image.new("RGB", (160, 160), "#332538")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 80, 159, 159), fill="#64887b")
    draw.ellipse((24, 24, 136, 136), fill="#dfb66b")
    draw.ellipse((48, 48, 112, 112), fill="#eee9dd")
    return image


def reply_status(replies: str, image_id: int) -> str:
    for header, status in re.findall(r"\x1b_G([^;]*);([^\x1b]*)\x1b\\", replies):
        fields = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
        if fields.get("i") == str(image_id):
            return safe_text(status)
    return "no reply"


def check_identity() -> dict:
    """Identify loaded code without disclosing checkout or interpreter paths."""
    source = files("kirlian_terminal")
    return {
        "check_version": 2,
        "kirlian_version": __version__,
        "python_version": sys.version.split()[0],
        "dependencies": {name: version(name) for name in ("textual", "textual-image", "pillow")},
        "source_sha256": {
            name: hashlib.sha256(source.joinpath(name).read_bytes()).hexdigest()
            for name in ("artwork_check.py", "graphics.py", "terminal_support.py")
        },
    }


def send_uncompressed(image: Image.Image, image_id: int, mode: str) -> None:
    """Independent reference encodings, compared with the production sender."""
    from textual_image.renderable import tgp

    if mode == "PNG":
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data, pixel_format = buffer.getvalue(), 100
    else:
        data = image.convert(mode).tobytes()
        pixel_format = 24 if mode == "RGB" else 32
    encoded = base64.b64encode(data).decode("ascii")
    header = dict(
        a="T", t="d", f=pixel_format, s=image.width, v=image.height, i=image_id, c=20, r=6, C=1
    )
    for offset in range(0, len(encoded), 4096):
        tgp._send_tgp_message(
            **(header if offset == 0 else {}),
            m=int(offset + 4096 < len(encoded)),
            q=0,
            payload=encoded[offset : offset + 4096],
        )


def run_artwork_check(report_path: Path | None = None) -> None:
    """Run before Textual starts: it normally owns terminal input and output."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Run --check-artwork directly in your terminal, without a pipe or redirect.")
        return
    size = shutil.get_terminal_size()
    if size.columns < 80 or size.lines < 24:
        print("Please widen the terminal to at least 80 columns and 24 rows, then try again.")
        return

    # These imports probe terminal capabilities; keep them after the TTY checks.
    from rich.console import Console
    from textual_image._terminal import capture_mode, prepare_terminal_sequence
    from textual_image.renderable import halfcell, tgp

    from .graphics import KittyRenderable, send_pixels

    pixels = sample_image()
    native = KittyRenderable(pixels, width=20, height=6)
    image_ids = {letter: next(tgp.Image._image_id_counter) for letter in "ABCD"}
    console = Console(color_system="truecolor", force_terminal=True, no_color=False, width=20)
    write = sys.stdout.write
    replies = ""
    visible = "not recorded"

    def at(row: int, column: int, text: str) -> None:
        write(f"\x1b[{row};{column}H{text}")

    def draw_lines(renderable, start_row: int, column: int) -> None:
        lines = console.render_lines(renderable, console.options.update(width=20, height=6))
        for row, line in enumerate(lines, start_row):
            at(row, column, console._render_buffer(line))

    write("\x1b[?1049h\x1b[0m\x1b[2J\x1b[?25l")
    try:
        with capture_mode():
            at(1, 3, "Kirlian artwork check v2 - six versions of the same colored ring")
            for index, (letter, label) in enumerate(SAMPLES.items()):
                row, column = 4 + (index // 3) * 9, 3 + (index % 3) * 26
                at(row - 1, column, f"{letter}  {label}")
                at(row, column, "")
                sys.stdout.flush()
                if letter in "ABD":
                    send_uncompressed(
                        pixels, image_ids[letter], {"A": "RGB", "B": "RGBA", "D": "PNG"}[letter]
                    )
                elif letter == "C":
                    send_pixels(pixels, image_ids[letter], action="T", quiet=0, c=20, r=6, C=1)
                elif letter == "E":
                    draw_lines(native, row, column)
                    image_ids[letter] = native.terminal_image_id or 0
                else:
                    draw_lines(halfcell.Image(pixels, width=20, height=6), row, column)
            # Ask for a reply to the actual player image, whose normal commands
            # are quiet. This also checks whether its pixels reached the terminal.
            tgp._send_tgp_message(a="p", i=image_ids["E"], U=1, c=20, r=6, q=0)
            # Ask the running terminal itself; installed app metadata can differ.
            write(prepare_terminal_sequence("\x1b[>q\x1b[c"))
            sys.stdout.flush()
            replies = read_replies(sys.stdin.fileno())

        at(21, 3, "Which rings are visible? Type their letters (or none), then Enter: ")
        write("\x1b[?25h")
        sys.stdout.flush()
        visible = safe_text(input())
    except (KeyboardInterrupt, EOFError):
        visible = "cancelled"
    finally:
        native.cleanup()
        for letter in "ABCD":
            tgp._send_tgp_message(a="d", d="I", i=image_ids[letter], q=2)
        write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()

    report = {
        **check_identity(),
        "recorded_at": datetime.now(UTC).isoformat(),
        "visible": visible or "not recorded",
        "terminal_version": terminal_version(replies),
        "terminal_size": {"columns": size.columns, "rows": size.lines},
        "samples": {
            letter: {"encoding": label, "reply": reply_status(replies, image_ids[letter])}
            for letter, label in SAMPLES.items()
            if letter != "F"
        },
        "environment": {
            key: safe_text(os.environ.get(key, "(unset)"))
            for key in ("TERM_PROGRAM", "TERM_PROGRAM_VERSION", "TERM", "COLORTERM")
        }
        | {
            key: "set" if key in os.environ else "unset"
            for key in ("TMUX", "STY", "HERDR_SOCKET_PATH", "HERDR_PANE_ID", "NO_COLOR")
        },
    }
    # Only code identity, terminal metadata and observation; no paths or music.
    print("Kirlian artwork check v2")
    print("Visible: " + (visible or "not recorded"))
    print("Terminal version reply: " + report["terminal_version"])
    if report["terminal_version"].casefold() == "libghostty":
        print("This session reports an embedded Ghostty engine, not the standalone app.")
        print("Its host may accept images without displaying them. Auto mode uses blocks.")
        print("Enable graphics in the host, then retry with --artwork native.")
        print("See docs/terminals.md for Herdr and multiplexer setup.")
    for letter, sample in report["samples"].items():
        print(f"{letter} {sample['encoding']}: {sample['reply']}")
    for key, value in report["environment"].items():
        print(f"{key}: {value}")
    if report_path is not None:
        try:
            report_path = report_path.expanduser()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Report saved: {report_path}")
        except OSError as error:
            print(f"Could not save report: {error}", file=sys.stderr)
