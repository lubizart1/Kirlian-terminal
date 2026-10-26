"""Cover display with a portable alternative to terminal graphics."""

from collections import OrderedDict

from PIL import Image, ImageOps
from textual.app import ComposeResult
from textual.containers import Vertical
from textual_image._terminal import get_cell_size
from textual_image.widget import HalfcellImage

from .graphics import NATIVE_SUPPORTED, image_widget


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

    def toggle(self) -> bool:
        self.renderer.image = None  # Release any native image before hiding it.
        self.renderer.display = False
        self.mode = "native" if self.mode in {"blocks", "off"} else "blocks"
        self.renderer.image = self._display_image
        self.renderer.display = True
        self.refresh(layout=True)
        return True

    def on_unmount(self) -> None:
        self.native.image = None
        self.blocks.image = None
        self._grayscale.clear()


class RecordPane(Vertical):
    """Size covers after this pane receives its actual layout dimensions."""

    def on_resize(self) -> None:
        # Keep room for the complete caption, plus the fact card when it is shown.
        reserve = 7
        for card in self.query("#fact-card"):
            if card.display:
                reserve += max(12, card.outer_size.height)
        for cover in self.query(CoverImage):
            # App resize events arrive before pane geometry updates, so measuring
            # there can be stale.
            cover.fit(
                min(34, self.content_size.width),
                min(17, max(4, self.content_size.height - reserve)),
            )
