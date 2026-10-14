"""Real screen capture via the Windows Desktop Duplication API (dxcam). Phase 1."""

from playertwo.config import CaptureSettings
from playertwo.types import Frame


class DxcamFrameSource:
    """FrameSource backed by dxcam. Windows only; dxcam is imported lazily."""

    def __init__(self, settings: CaptureSettings) -> None:
        self._settings = settings

    def grab(self) -> Frame | None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")

    def close(self) -> None:
        raise NotImplementedError("Phase 1: feat/capture-input/1")
