"""Mouse-look for the testbed: read how far the cursor moved, then put it back.

Done with Win32 calls instead of Panda3D's `movePointer`, which silently does nothing
while the cursor is outside the window. With it, a cursor that started outside the window
was read as the same large offset on every frame and the character spun non-stop.
"""

import ctypes
import sys


class _Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class _Rect(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    )


def _user32() -> ctypes.CDLL:
    user32 = ctypes.CDLL("user32")
    user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Point)]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.ClipCursor.argtypes = [ctypes.POINTER(_Rect)]
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    return user32


class MouseLook:
    """Captures the cursor in a window and reports horizontal movement in pixels."""

    def __init__(self, hwnd: int) -> None:
        self._hwnd = hwnd
        self._user32 = _user32() if sys.platform == "win32" else None

    def focused(self) -> bool:
        """Whether Windows has this window in front. Asked of Windows itself: Panda3D
        reported a newly opened window as focused while Windows had kept another app in
        front (it blocks focus stealing), so the game clock ran and the cursor was held
        while the window was in the background."""
        if self._user32 is None:
            return True
        return bool(self._user32.GetForegroundWindow() == self._hwnd)

    def _client_rect(self) -> _Rect:
        assert self._user32 is not None
        rect = _Rect()
        self._user32.GetClientRect(self._hwnd, ctypes.byref(rect))
        origin = _Point(0, 0)
        self._user32.ClientToScreen(self._hwnd, ctypes.byref(origin))
        return _Rect(origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)

    def _center(self) -> tuple[int, int]:
        rect = self._client_rect()
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2

    def capture(self) -> None:
        """Keep the cursor inside the window and put it in the middle."""
        if self._user32 is None:
            return
        rect = self._client_rect()
        self._user32.ClipCursor(ctypes.byref(rect))
        self._user32.SetCursorPos(*self._center())

    def release(self) -> None:
        if self._user32 is not None:
            self._user32.ClipCursor(None)

    def take_dx(self) -> int:
        """Pixels the cursor moved right since the last call (negative: left), then
        re-centre it."""
        if self._user32 is None:
            return 0
        rect = self._client_rect()
        cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        point = _Point(0, 0)
        self._user32.GetCursorPos(ctypes.byref(point))
        self._user32.SetCursorPos(cx, cy)
        return plausible_dx(int(point.x - cx), rect.right - rect.left)


def plausible_dx(dx: int, window_width: int) -> int:
    """`dx`, or 0 if it can't be a real movement. While the cursor is held inside the
    window it is never more than half the width from the centre. Larger readings happen
    while a window is restoring (Windows reports it at -32000, -32000): one read as
    +32000 px and spun the player to a random direction when an episode started."""
    if window_width <= 0 or abs(dx) > window_width // 2:
        return 0
    return dx
