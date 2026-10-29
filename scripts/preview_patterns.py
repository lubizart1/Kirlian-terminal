# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the actual pattern catalog to a shareable SVG, without opening music.

uv run python scripts/preview_patterns.py --output .local/patterns.svg
Add --all for a contact sheet of every pattern instead of one Drift per family.
"""

import argparse
import io
import re
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.terminal_theme import TerminalTheme
from rich.text import Text

from kirlian_terminal.animations import CATALOG
from kirlian_terminal.palette import ribbon_color


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/patterns.svg"))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--characters", choices=("dots", "ascii"), default="dots")
    args = parser.parse_args()
    colors = ("#b69cbe", "#afb497", "#c9b7aa")
    columns, width = (2, 68) if args.all else (1, 112)
    console = Console(
        width=(width + 6) * columns,
        height=1000,
        record=True,
        force_terminal=True,
        color_system="truecolor",
        no_color=False,
        file=io.StringIO(),
    )
    table = Table.grid(padding=(1, 3))
    for _ in range(columns):
        table.add_column(width=width)
    patterns = CATALOG if args.all else CATALOG[::10]
    cards = []
    for pattern in patterns:
        card = Text(pattern.label + "\n\n", style="#e5ddcd")
        for line in pattern.ribbon_frame(args.seconds, width, args.characters).splitlines():
            for start in range(0, width, 4):
                card.append(line[start : start + 4], ribbon_color(colors, start / (width - 1)))
            card.append("\n")
        cards.append(card)
    for i in range(0, len(cards), columns):
        table.add_row(*cards[i : i + columns])
    console.print(table)
    theme = TerminalTheme((16, 15, 19), (229, 221, 205), [(16, 15, 19)] * 8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    svg = console.export_svg(title="Kirlian · Ribbon studies", theme=theme)
    # Rich's default SVG loads web fonts. This preview must also work offline.
    svg = re.sub(r"\s*@font-face\s*\{.*?\}", "", svg, flags=re.DOTALL)
    svg = svg.replace("Fira Code, monospace", "Menlo, Consolas, monospace")
    view_box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    svg = svg.replace("<svg ", f'<svg width="{view_box[1]}" height="{view_box[2]}" ', 1)
    args.output.write_text(svg)
    print(args.output)


if __name__ == "__main__":
    main()
