"""Real screen capture via the Windows Desktop Duplication API (dxcam)."""

from collections.abc import Callable
from typing import Protocol

from playertwo.capture.downscale import downscale_to_width
from playertwo.config import CaptureSettings
from playertwo.types import Frame


class Camera(Protocol):
    """The slice of a dxcam camera this source uses. Faked in tests."""

    def grab(self) -> Frame | None: ...

    def release(self) -> None: ...


def _create_dxcam_camera() -> Camera:
    import dxcam

    # numpy processor: dxcam's default backend needs OpenCV, which isn't a dependency.
    camera: Camera = dxcam.create(output_color="RGB", processor_backend="numpy")
    return camera


class DxcamFrameSource:
    """FrameSource backed by dxcam, capturing the primary monitor. Windows only.

    The camera is created on the first grab, so constructing this is free and dxcam is
    only imported when capture is actually used.
    """

    def __init__(
        self,
        settings: CaptureSettings,
        camera_factory: Callable[[], Camera] = _create_dxcam_camera,
    ) -> None:
        self._settings = settings
        self._camera_factory = camera_factory
        self._camera: Camera | None = None

    def grab(self) -> Frame | None:
        """The newest frame downscaled to `capture.width`, or None if the screen hasn't
        changed since the last grab."""
        if self._camera is None:
            self._camera = self._camera_factory()
        frame = self._camera.grab()
        if frame is None:
            return None
        return downscale_to_width(frame, self._settings.width)

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None
