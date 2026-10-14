"""Getting frames off the screen."""

from playertwo.capture.change_detector import ChangeDetector, frame_difference
from playertwo.capture.downscale import downscale_to_width
from playertwo.capture.dxcam_source import Camera, CameraBackend, DxcamBackend, DxcamFrameSource
from playertwo.capture.frame_source import FrameSource
from playertwo.capture.region import capture_region
from playertwo.capture.target_window import TargetWindow

__all__ = [
    "Camera",
    "CameraBackend",
    "ChangeDetector",
    "DxcamBackend",
    "DxcamFrameSource",
    "FrameSource",
    "TargetWindow",
    "capture_region",
    "downscale_to_width",
    "frame_difference",
]
