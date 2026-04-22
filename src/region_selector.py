"""Snipping-tool-like fullscreen overlay for picking a recording region."""
from __future__ import annotations

import tkinter as tk
from typing import Optional


def select_region(root: tk.Misc) -> Optional[tuple[int, int, int, int]]:
    """Block until the user drags a region. Returns (x, y, w, h) or None."""
    picker = _RegionPicker(root)
    picker.wait_window()
    return picker.result


class _RegionPicker(tk.Toplevel):
    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.result: Optional[tuple[int, int, int, int]] = None

        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="#000000", cursor="crosshair")
        self.overrideredirect(True)

        self.canvas = tk.Canvas(self, bg="#000000", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.hint = self.canvas.create_text(
            20, 20, anchor="nw",
            text="Drag to select region   ·   Esc to cancel",
            fill="#ffffff", font=("Segoe UI", 14, "bold"),
        )

        self._start: Optional[tuple[int, int]] = None
        self._rect_id: Optional[int] = None

        self.bind("<Escape>", lambda _e: self._cancel())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.grab_set()
        self.focus_force()

    def _on_press(self, ev):
        self._start = (ev.x_root, ev.y_root)
        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
        self._rect_id = self.canvas.create_rectangle(
            ev.x, ev.y, ev.x, ev.y, outline="#4f8cff", width=2, fill="",
        )

    def _on_drag(self, ev):
        if self._start is None or self._rect_id is None:
            return
        x0 = self._start[0] - self.winfo_rootx()
        y0 = self._start[1] - self.winfo_rooty()
        self.canvas.coords(self._rect_id, x0, y0, ev.x, ev.y)

    def _on_release(self, ev):
        if self._start is None:
            return self._cancel()
        x1, y1 = self._start
        x2, y2 = ev.x_root, ev.y_root
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w < 8 or h < 8:
            return self._cancel()
        self.result = (x, y, w, h)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
