# SPDX-License-Identifier: GPL-3.0-or-later
"""Small compatibility adapter for textual-image's Kitty renderer.

Placeholder foreground colors are protocol data, not presentation colors.
Keep them intact and target cleanup by image ID so other images are untouched.
"""

import asyncio
import base64
import os
import zlib
from collections import OrderedDict

from PIL import Image
from textual import work
from textual_image._terminal import get_cell_size
from textual_image.renderable import Image as DetectedRenderable
from textual_image.renderable import tgp
from textual_image.widget import HalfcellImage, SixelImage, TGPImage
from textual_image.widget import Image as DetectedImage

from .terminal_support import query_terminal_version


def encode_pixels(image: Image.Image) -> str:
    pixels = image.convert("RGBA")
    return base64.b64encode(zlib.compress(pixels.tobytes())).decode("ascii")


def send_encoded(
    encoded: str, size: tuple[int, int], image_id: int, *, action="t", quiet=2, **placement
) -> None:
    header = dict(a=action, f=32, s=size[0], v=size[1], i=image_id, o="z", **placement)
    for offset in range(0, len(encoded), 4096):
        tgp._send_tgp_message(
            **(header if offset == 0 else {}),
            m=int(offset + 4096 < len(encoded)),
            q=quiet,
            payload=encoded[offset : offset + 4096],
        )


def send_pixels(image: Image.Image, image_id: int, *, action="t", quiet=2, **placement) -> None:
    """Send core-protocol RGBA pixels, without requiring a terminal PNG decoder."""
    send_encoded(
        encode_pixels(image), image.size, image_id, action=action, quiet=quiet, **placement
    )


class KittyRenderable(tgp.Image):
    encoded: str | None = None
    encoded_size: tuple[int, int] | None = None

    def prepare(self, width: int, height: int) -> None:
        self.encoded_size = (max(1, width), max(1, height))
        pixels = self._image_data.pil_image.resize(self.encoded_size, Image.Resampling.LANCZOS)
        self.encoded = encode_pixels(pixels)

    def _send_image_to_terminal(self, width: int, height: int) -> None:
        self.terminal_image_id = next(tgp.Image._image_id_counter)
        if self.encoded_size != (width, height) or self.encoded is None:
            # Standalone diagnostic renderables do not have a widget worker.
            self.prepare(width, height)
        send_encoded(self.encoded, self.encoded_size, self.terminal_image_id)

    def cleanup(self) -> None:
        if self.terminal_image_id is not None:
            tgp._send_tgp_message(a="d", d="I", i=self.terminal_image_id, q=2)
            self.terminal_image_id = None


class KittyImage(TGPImage, Renderable=KittyRenderable):
    """Prepare pixels off-thread and retain a bounded set of terminal images."""

    CACHE_SIZE = 12

    def __init__(self, *args, **kwargs):
        # Values retain the source object as well, so identity keys cannot be reused.
        self._images = OrderedDict()
        self._requested_key = None
        self._preparation = None
        super().__init__(*args, **kwargs)

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, value):
        if value is self._image:
            return
        if self._preparation is not None:
            self._preparation.cancel()
        self._requested_key = None
        # The base setter deletes the previous renderable. Keep it in our LRU
        # instead; virtual placements only appear where their text cells are drawn.
        self._renderable = None
        TGPImage.image.fset(self, value)
        if value is None:
            for _, renderable in self._images.values():
                renderable.cleanup()
            self._images.clear()

    def render(self):
        if self._image is None or not self.content_size:
            return ""
        size = self._get_styled_size()
        cell = get_cell_size()
        key = (id(self._image), size, self.content_size, cell)
        if key in self._images:
            if key != self._requested_key and self._preparation is not None:
                self._preparation.cancel()
            self._requested_key = key
            self._images.move_to_end(key)
            self._renderable = self._images[key][1]
            return self._renderable
        if key != self._requested_key:
            self._requested_key = key
            self._preparation = self.prepare_image(self._image, key, size, cell)
        return ""

    @work(group="native-image", exclusive=True)
    async def prepare_image(self, image, key, size, cell) -> None:
        bounds = self.content_size

        def prepare():
            renderable = KittyRenderable(image, *size)
            renderable.prepare(*renderable._render_size.get_pixel_size(*bounds, cell))
            return renderable

        renderable = await asyncio.to_thread(prepare)
        if key != self._requested_key or not self.is_mounted:
            return
        self._images[key] = (image, renderable)
        while len(self._images) > self.CACHE_SIZE:
            _, (_, old) = self._images.popitem(last=False)
            old.cleanup()
        self.refresh()

    def get_line_filters(self):
        # NO_COLOR, dimming, or palette transforms must not rewrite image IDs.
        # The cover adapter grayscales the actual pixels when requested instead.
        return []

    def on_unmount(self) -> None:
        self.image = None


def automatic_renderer(detected, terminal: str, version_reply: str = ""):
    # Warp currently answers the graphics probe without implementing the Unicode
    # placements this renderer uses. Keep a deliberate fallback until verified.
    if terminal.casefold().startswith("warp") and detected is KittyImage:
        return HalfcellImage
    # The library can accept/store images without its host painting them. Its
    # default identity does not identify a graphics-capable host. Use a safe
    # automatic fallback; explicit native mode can still test such hosts.
    if version_reply.strip().casefold() == "libghostty" and detected is KittyImage:
        return HalfcellImage
    return detected


TerminalImage = automatic_renderer(
    KittyImage if DetectedRenderable is tgp.Image else DetectedImage,
    os.environ.get("TERM_PROGRAM", ""),
    query_terminal_version() if DetectedRenderable is tgp.Image else "",
)
NATIVE_SUPPORTED = TerminalImage in (KittyImage, SixelImage)


def image_widget(force: bool = False):
    """Explicit native mode can retry Kitty if the startup probe was inconclusive."""
    return KittyImage if force and not NATIVE_SUPPORTED else TerminalImage
