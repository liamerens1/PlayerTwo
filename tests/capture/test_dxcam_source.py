import numpy as np

from playertwo.capture import Camera, DxcamFrameSource, downscale_to_width
from playertwo.config import CaptureSettings
from playertwo.types import Frame, Rect

PRIMARY = Rect(0, 0, 1920, 1080)
LEFT = Rect(-1920, 0, 0, 1080)


class FakeCamera:
    def __init__(self, output: int | None, frames: list[Frame | None]) -> None:
        self.output = output
        self._frames = frames
        self.regions: list[tuple[int, int, int, int] | None] = []
        self.released = False

    def grab(self, region: tuple[int, int, int, int] | None = None) -> Frame | None:
        self.regions.append(region)
        return self._frames.pop(0) if self._frames else _frame(1920, 1080)

    def release(self) -> None:
        self.released = True


class FakeBackend:
    def __init__(self, outputs: list[Rect], frames: list[Frame | None] | None = None) -> None:
        self._outputs = outputs
        self._frames = frames
        self.cameras: list[FakeCamera] = []

    def outputs(self) -> list[Rect]:
        return self._outputs

    def create(self, output_index: int | None) -> Camera:
        frames: list[Frame | None] = (
            list(self._frames) if self._frames is not None else [_frame(1920, 1080)]
        )
        self.cameras.append(FakeCamera(output_index, frames))
        return self.cameras[-1]


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
    backends: list[FakeBackend] = []

    def factory() -> FakeBackend:
        backends.append(FakeBackend([PRIMARY]))
        return backends[-1]

    source = DxcamFrameSource(CaptureSettings(width=640), backend_factory=factory)
    assert backends == []
    frame = source.grab()
    assert frame is not None and frame.shape == (360, 640, 3) and frame.dtype == np.uint8
    (camera,) = backends[0].cameras
    assert camera.output is None  # primary monitor
    assert camera.regions == [None]  # the whole monitor


def test_no_new_frame_returns_none() -> None:
    backend = FakeBackend([PRIMARY], frames=[None])
    source = DxcamFrameSource(CaptureSettings(), backend_factory=lambda: backend)
    assert source.grab() is None


def test_close_releases_camera_and_allows_reopen() -> None:
    backend = FakeBackend([PRIMARY])
    source = DxcamFrameSource(CaptureSettings(), backend_factory=lambda: backend)
    source.close()  # closing before any grab is a no-op
    source.grab()
    source.close()
    assert backend.cameras[0].released
    source.grab()
    assert len(backend.cameras) == 2


def test_window_capture_grabs_only_the_window_on_its_monitor() -> None:
    backend = FakeBackend([PRIMARY, LEFT])
    window = Rect(-1600, 100, -320, 820)  # 1280x720 client area on the left monitor
    source = DxcamFrameSource(
        CaptureSettings(width=640), window=lambda: window, backend_factory=lambda: backend
    )
    source.grab()
    (camera,) = backend.cameras
    assert camera.output == 1
    assert camera.regions == [(320, 100, 1600, 820)]


def test_window_moving_to_another_monitor_switches_camera() -> None:
    backend = FakeBackend([PRIMARY, LEFT])
    rects = iter([Rect(100, 100, 1380, 820), Rect(200, 100, 1480, 820), Rect(-1500, 0, -220, 720)])
    source = DxcamFrameSource(
        CaptureSettings(), window=lambda: next(rects), backend_factory=lambda: backend
    )
    source.grab()
    source.grab()  # moved on the same monitor: same camera, new region
    assert len(backend.cameras) == 1
    assert backend.cameras[0].regions == [(100, 100, 1380, 820), (200, 100, 1480, 820)]
    source.grab()  # dragged to the left monitor
    assert backend.cameras[0].released
    assert backend.cameras[1].output == 1
    assert backend.cameras[1].regions == [(420, 0, 1700, 720)]


def test_missing_or_minimised_window_gives_no_frame() -> None:
    backend = FakeBackend([PRIMARY])
    source = DxcamFrameSource(
        CaptureSettings(), window=lambda: None, backend_factory=lambda: backend
    )
    assert source.grab() is None
    assert backend.cameras == []


def test_window_off_every_monitor_gives_no_frame() -> None:
    backend = FakeBackend([PRIMARY])
    off = Rect(5000, 5000, 6280, 5720)
    source = DxcamFrameSource(
        CaptureSettings(), window=lambda: off, backend_factory=lambda: backend
    )
    assert source.grab() is None
