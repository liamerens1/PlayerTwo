"""Real screen capture via the Windows Desktop Duplication API (dxcam)."""

import logging
from collections.abc import Callable
from typing import Any, Protocol

from playertwo.capture.downscale import downscale_to_width
from playertwo.capture.region import capture_region
from playertwo.config import CaptureSettings
from playertwo.types import Frame, Rect

logger = logging.getLogger(__name__)


class Camera(Protocol):
    """The slice of a dxcam camera this source uses. Faked in tests."""

    def grab(self, region: tuple[int, int, int, int] | None = None) -> Frame | None: ...

    def release(self) -> None: ...


class CameraBackend(Protocol):
    """Lists the monitors and makes a camera for one of them. Faked in tests."""

    def outputs(self) -> list[Rect]:
        """Each output's rectangle in desktop coordinates, in camera index order."""
        ...

    def create(self, output_index: int | None) -> Camera:
        """A camera for that output; None means the primary monitor."""
        ...


class DxcamBackend:
    """CameraBackend over dxcam. Importing dxcam is deferred to construction."""

    def __init__(self) -> None:
        import dxcam

        # dxcam has no public list of its outputs, so read its factory's. Its order is the
        # output_idx that dxcam.create expects.
        factory: Any = vars(dxcam)["__factory"]
        self._dxcam = dxcam
        self._outputs = [
            Rect(c.left, c.top, c.right, c.bottom)
            for c in (output.desc.DesktopCoordinates for output in factory.outputs[0])
        ]

    def outputs(self) -> list[Rect]:
        return self._outputs

    def create(self, output_index: int | None) -> Camera:
        # numpy processor: dxcam's default backend needs OpenCV, which isn't a dependency.
        camera: Camera = self._dxcam.create(
            output_idx=output_index, output_color="RGB", processor_backend="numpy"
        )
        return camera


class DxcamFrameSource:
    """FrameSource backed by dxcam. Windows only.

    With `window` (a function returning the game window's client rectangle on screen),
    only that area is captured, from whichever monitor shows most of it; moving the
    window, or dragging it to another monitor, is picked up on the next grab. Without
    it, the whole primary monitor is captured.

    dxcam is only imported on the first grab, so constructing this is free.
    """

    def __init__(
        self,
        settings: CaptureSettings,
        window: Callable[[], Rect | None] | None = None,
        backend_factory: Callable[[], CameraBackend] = DxcamBackend,
    ) -> None:
        self._settings = settings
        self._window = window
        self._backend_factory = backend_factory
        self._backend: CameraBackend | None = None
        self._camera: Camera | None = None
        self._output: int | None = None

    def grab(self) -> Frame | None:
        """The newest frame downscaled to `capture.width`, or None if nothing changed
        since the last grab (or the game window is missing or minimised)."""
        if self._backend is None:
            self._backend = self._backend_factory()
        region: tuple[int, int, int, int] | None = None
        output: int | None = None
        if self._window is not None:
            rect = self._window()
            placed = None if rect is None else capture_region(rect, self._backend.outputs())
            if placed is None:
                return None
            output, area = placed
            region = (area.left, area.top, area.right, area.bottom)
        if self._camera is None or output != self._output:
            if self._camera is not None:
                logger.info("game window moved to monitor %s; switching camera", output)
                self._camera.release()
            self._camera = self._backend.create(output)
            self._output = output
        frame = self._camera.grab(region=region)
        if frame is None:
            return None
        return downscale_to_width(frame, self._settings.width)

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None
