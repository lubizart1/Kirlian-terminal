# SPDX-License-Identifier: GPL-3.0-or-later
"""Cover display with a portable alternative to terminal graphics."""

from collections import OrderedDict

from PIL import Image, ImageOps
from textual.app import ComposeResult
from textual.containers import Vertical
from textual_image._terminal import get_cell_size
from textual_image.widget import HalfcellImage

from .graphics import NATIVE_SUPPORTED, image_widget

# The xterm 256-color palette without its first 16 entries, which each terminal
# theme redefines: a 6x6x6 color cube and a 24-step gray ramp.
CUBE = (0, 95, 135, 175, 215, 255)
XTERM_COLORS = [(r, g, b) for r in CUBE for g in CUBE for b in CUBE] + [
    (8 + 10 * step,) * 3 for step in range(24)
]


def palette_image() -> Image.Image:
    image = Image.new("P", (1, 1))
    flat = [channel for color in XTERM_COLORS for channel in color]
    image.putpalette(flat + flat[: 768 - len(flat)])  # Pad with repeats, never new colors.
    return image


XTERM_PALETTE = palette_image()


def dithered(image: Image.Image, columns: int, rows: int) -> Image.Image:
    """The cover at exactly one pixel per half cell, dithered into the 256 colors.

    A 256-color terminal otherwise snaps each pixel to its nearest color, which
    turns gradients into bands; spreading the error keeps them smooth.
    """
    sized = image.convert("RGB").resize((columns, rows * 2), Image.Resampling.LANCZOS)
    return sized.quantize(palette=XTERM_PALETTE, dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")


class CoverImage(Vertical):
    """Keep the decoded cover while switching how the terminal draws it."""

    DEFAULT_CSS = """
    CoverImage { height: 17; }
    CoverImage > * { width: 100%; height: 100%; }
    """

    def __init__(self, mode: str = "auto", *, no_color: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.no_color = no_color
        self.mode = (
            mode
            if mode in {"blocks", "off"}
            else "native"
            if mode == "native" or NATIVE_SUPPORTED
            else "blocks"
        )
        self.native = image_widget(force=True)()
        self.blocks = HalfcellImage()
        self._image: Image.Image | None = None
        self._display_image: Image.Image | None = None
        self._grayscale: OrderedDict[int, tuple[Image.Image, Image.Image]] = OrderedDict()
        self._available = (34, 17)
        # Set by the app when the terminal has 256 colors rather than full color.
        self.dither = False
        self._dithered: tuple[tuple[int, int, int], Image.Image] | None = None
        self.native.display = self.mode == "native"
        self.blocks.display = self.mode == "blocks"

    def compose(self) -> ComposeResult:
        yield self.native
        yield self.blocks

    @property
    def renderer(self):
        return self.blocks if self.mode == "blocks" else self.native

    @property
    def image(self) -> Image.Image | None:
        return self._image

    @image.setter
    def image(self, image: Image.Image | None) -> None:
        if image is self._image:
            return
        self._image = image
        self._display_image = image
        if image is not None and self.no_color:
            key = id(image)
            if key not in self._grayscale:
                self._grayscale[key] = (image, ImageOps.grayscale(image).convert("RGB"))
            self._grayscale.move_to_end(key)
            self._display_image = self._grayscale[key][1]
            while len(self._grayscale) > 12:
                self._grayscale.popitem(last=False)
        if self.mode != "off":
            self.renderer.image = self._display_image
        self.fit(*self._available)

    def fit(self, columns: int, rows: int) -> None:
        """Give both renderers a concrete box, including before their first paint.

        The upstream auto-height measurement reads the widget's previous width.
        A newly shown image can therefore keep a cached height of zero. Fit the
        decoded aspect ratio here instead of depending on that circular layout.
        """
        self._available = (max(1, columns), max(1, rows))
        cell = get_cell_size()
        width, height = self._image.size if self._image else (1, 1)
        scale = min(
            self._available[0] * cell.width / width, self._available[1] * cell.height / height
        )
        self.styles.width = max(1, round(width * scale / cell.width))
        self.styles.height = max(1, round(height * scale / cell.height))
        if self.dither and self.mode == "blocks" and self._display_image is not None:
            size = (int(self.styles.width.value), int(self.styles.height.value))
            key = (id(self._display_image), *size)
            if self._dithered is None or self._dithered[0] != key:
                self._dithered = (key, dithered(self._display_image, *size))
            self.blocks.image = self._dithered[1]

    def toggle(self) -> bool:
        self.renderer.image = None  # Release any native image before hiding it.
        self.renderer.display = False
        self.mode = "native" if self.mode in {"blocks", "off"} else "blocks"
        self.renderer.image = self._display_image
        self.renderer.display = True
        self.fit(*self._available)  # Blocks on a 256-color terminal are dithered here.
        self.refresh(layout=True)
        return True

    def on_unmount(self) -> None:
        self.native.image = None
        self.blocks.image = None
        self._grayscale.clear()


class RecordPane(Vertical):
    """Size covers after this pane receives its actual layout dimensions."""

    # Lines each part needs before it has been laid out once.
    FALLBACK = {"record-details": 7, "record-stores": 3, "amp-mini": 10, "fact-card": 12}

    def on_resize(self) -> None:
        """The cover gets what is left after everything else the pane shows."""
        reserve = 0
        for child in self.children:
            if isinstance(child, CoverImage) or child.id == "cover-placeholder":
                continue
            if child.display:
                height = child.outer_size.height or self.FALLBACK.get(child.id or "", 0)
                height += child.styles.margin.height
                # The fact card grows when its next note is longer; keep room for that.
                reserve += max(12, height) if child.id == "fact-card" else height
        for cover in self.query(CoverImage):
            # App resize events arrive before pane geometry updates, so measuring
            # there can be stale.
            cover.fit(
                min(34, self.content_size.width),
                min(17, max(4, self.content_size.height - reserve)),
            )
