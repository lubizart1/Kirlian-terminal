# SPDX-License-Identifier: GPL-3.0-or-later
"""Scroll the highlighted row's title when it is too long for its column."""

from __future__ import annotations

import contextlib

from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import CellDoesNotExist, ColumnKey, RowKey

GAP = "   ·   "
HOLD = 8  # Ticks at the start before scrolling, so the beginning can be read first.


class Marquee:
    """One scrolling cell at a time; the original text returns when the cursor moves."""

    def __init__(self) -> None:
        self.cell: tuple[RowKey, ColumnKey, Text] | None = None
        self.offset = 0
        self.wait = HOLD

    def forget(self) -> None:
        """The table was rebuilt; its new cells already hold their full text."""
        self.cell = None

    def restore(self, table: DataTable) -> None:
        if self.cell is not None:
            row, column, original = self.cell
            with contextlib.suppress(CellDoesNotExist):
                table.update_cell(row, column, original)
        self.cell = None

    def tick(self, table: DataTable, column: str, moving: bool) -> None:
        if not moving or not table.row_count or column not in table.columns:
            self.restore(table)
            return
        try:
            row = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key
            current = table.get_cell(row, column)
        except CellDoesNotExist:
            self.cell = None
            return
        key = ColumnKey(column)
        if self.cell is not None and self.cell[:2] != (row, key):
            self.restore(table)
        if self.cell is None:
            if not isinstance(current, Text):
                return
            self.cell, self.offset, self.wait = (row, key, current), 0, HOLD
        original = self.cell[2]
        width = table.columns[key].width
        if original.cell_len <= width:
            if current is not original:
                table.update_cell(row, key, original)
            return
        if self.wait:
            self.wait -= 1
            return
        loop = original.plain + GAP
        self.offset = (self.offset + 1) % len(loop)
        if self.offset == 0:
            self.wait = HOLD
        frame = Text((loop + loop)[self.offset :], style=original.style, no_wrap=True)
        frame.truncate(width, overflow="crop")
        table.update_cell(row, key, frame)
