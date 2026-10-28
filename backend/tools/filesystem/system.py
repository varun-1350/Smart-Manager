from __future__ import annotations

import os
import time
from typing import Callable

from backend.security.config import BLOCKED_EXTENSIONS

from .common import ToolError, ToolResult, require_abs


def _startfile(path: str) -> None:
    if not hasattr(os, "startfile"):
        raise ToolError("Opening files is only supported on Windows.")
    os.startfile(path)


def open_path(path, *, opener: Callable[[str], None] | None = None) -> ToolResult:
    path = require_abs(path)
    if not os.path.lexists(path):
        raise ToolError(f"'{path}' doesn't exist.")
    if path.is_file() and path.suffix.lower() in BLOCKED_EXTENSIONS:
        raise ToolError(f"'{path.name}' is a program or script type. I won't open it.")
    try:
        (opener or _startfile)(str(path))
    except ToolError:
        raise
    except OSError as exc:
        raise ToolError(f"Windows couldn't open '{path.name}': {exc}") from exc
    # We can only confirm the request was made, not that the app opened it.
    return ToolResult("open_file", f"Asked Windows to open {path}", {"path": str(path)},
                      verified=False)


class WindowsClipboard:
    """Unicode clipboard via the Windows API (standard library only)."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def __init__(self):
        if os.name != "nt":
            raise ToolError("Clipboard access is only supported on Windows.")
        import ctypes
        from ctypes import wintypes
        self._ct = ctypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.OpenClipboard.argtypes, u.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
        u.CloseClipboard.argtypes, u.CloseClipboard.restype = [], wintypes.BOOL
        u.EmptyClipboard.argtypes, u.EmptyClipboard.restype = [], wintypes.BOOL
        u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u.SetClipboardData.restype = wintypes.HANDLE
        u.GetClipboardData.argtypes, u.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
        k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k.GlobalAlloc.restype = wintypes.HGLOBAL
        k.GlobalLock.argtypes, k.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
        k.GlobalUnlock.argtypes, k.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
        k.GlobalFree.argtypes, k.GlobalFree.restype = [wintypes.HGLOBAL], wintypes.HGLOBAL
        self._u, self._k = u, k

    def _open(self) -> None:
        for _ in range(10):                      # another app may be holding the clipboard
            if self._u.OpenClipboard(None):
                return
            time.sleep(0.05)
        raise ToolError("The clipboard is busy. Please try again.")

    def set(self, text: str) -> None:
        data = (text + "\0").encode("utf-16-le")
        handle = self._k.GlobalAlloc(self.GMEM_MOVEABLE, len(data))
        if not handle:
            raise ToolError("Couldn't allocate memory for the clipboard.")
        ptr = self._k.GlobalLock(handle)
        if not ptr:
            self._k.GlobalFree(handle)
            raise ToolError("Couldn't lock memory for the clipboard.")
        self._ct.memmove(ptr, data, len(data))
        self._k.GlobalUnlock(handle)
        try:
            self._open()
        except ToolError:
            self._k.GlobalFree(handle)
            raise
        try:
            self._u.EmptyClipboard()
            if not self._u.SetClipboardData(self.CF_UNICODETEXT, handle):
                self._k.GlobalFree(handle)
                raise ToolError("Windows refused to set the clipboard.")
        finally:
            self._u.CloseClipboard()             # on success the clipboard now owns the memory

    def get(self) -> str | None:
        self._open()
        try:
            handle = self._u.GetClipboardData(self.CF_UNICODETEXT)
            if not handle:
                return None
            ptr = self._k.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return self._ct.wstring_at(ptr)
            finally:
                self._k.GlobalUnlock(handle)
        finally:
            self._u.CloseClipboard()


def copy_path_to_clipboard(path, *, clipboard=None) -> ToolResult:
    path = require_abs(path)
    if not os.path.lexists(path):
        raise ToolError(f"'{path}' doesn't exist.")
    clip = clipboard or WindowsClipboard()
    clip.set(str(path))
    if clip.get() != str(path):
        raise ToolError("The clipboard didn't hold the path after copying.")
    return ToolResult("copy_path_to_clipboard", f"Copied the path of {path.name} to the clipboard",
                      {"path": str(path)})