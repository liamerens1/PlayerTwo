import numpy as np

from playertwo.capture import DxcamFrameSource, downscale_to_width
from playertwo.config import CaptureSettings
from playertwo.types import Frame


class FakeCamera:
    def __init__(self, frames: list[Frame | None]) -> None:
        self._frames = frames
        self.released = False

    def grab(self) -> Frame | None:
        return self._frames.pop(0)

    def release(self) -> None:
        self.released = True


def _frame(width: int, height: int) -> Frame:
    return np.random.default_rng(0).integers(0, 256, (height, width, 3), dtype=np.uint8)


def test_downscale_keeps_aspect_and_dtype() -> None:
    out = downscale_to_width(_frame(1920, 1080), 640)
    assert out.shape == (360, 640, 3)
    assert out.dtype == np.uint8


def test_downscale_never_upscales() -> None:
    frame = _frame(320, 200)
    assert downscale_to_width(frame, 640) is frame


def test_camera_is_created_lazily_and_frames_are_downscaled() -> None:
    created: list[FakeCamera] = []

    def factory() -> FakeCamera:
        camera = FakeCamera([_frame(1920, 1080)])
        created.append(camera)
        return camera

    source = DxcamFrameSource(CaptureSettings(width=640), camera_factory=factory)
    assert created == []
    frame = source.grab()
    assert len(created) == 1
    assert frame is not None
    assert frame.shape == (360, 640, 3)
    assert frame.dtype == np.uint8


def test_no_new_frame_returns_none() -> None:
    source = DxcamFrameSource(CaptureSettings(), camera_factory=lambda: FakeCamera([None]))
    assert source.grab() is None


def test_close_releases_camera_and_allows_reopen() -> None:
    cameras: list[FakeCamera] = []

    def factory() -> FakeCamera:
        cameras.append(FakeCamera([_frame(100, 100)]))
        return cameras[-1]

    source = DxcamFrameSource(CaptureSettings(), camera_factory=factory)
    source.close()  # closing before any grab is a no-op
    source.grab()
    source.close()
    assert cameras[0].released
    source.grab()
    assert len(cameras) == 2
