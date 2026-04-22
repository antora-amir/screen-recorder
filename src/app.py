"""Lumen Recorder — modern screen recorder UI."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from .recorder import (
    RecordingConfig,
    ScreenRecorder,
    list_audio_input_devices,
    list_monitors,
)
from .region_selector import select_region
from .settings import APP_NAME, Settings, default_output_dir


# --- theme tokens ---
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3b78eb"
DANGER = "#ff5a5a"
DANGER_HOVER = "#e84848"
SURFACE = "#1e1f24"
SURFACE_2 = "#262830"
SIDEBAR_BG = "#15161a"
MUTED = "#8a8f98"
TEXT = "#f2f3f5"


def _format_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class LumenApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        ctk.set_appearance_mode(self.settings.theme)
        ctk.set_default_color_theme("blue")

        self.title(APP_NAME)
        self.geometry("980x620")
        self.minsize(880, 560)
        self.configure(fg_color=SURFACE)

        self.recorder: Optional[ScreenRecorder] = None
        self._ticker_id: Optional[str] = None
        self._custom_region: Optional[tuple[int, int, int, int]] = None
        self._hotkey_handles: list = []

        self._build_layout()
        self._show_view("record")
        self._register_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================
    # Layout
    # ================================================================
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=SIDEBAR_BG)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(10, weight=1)

        brand = ctk.CTkLabel(
            self.sidebar, text="  ● Lumen",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=TEXT, anchor="w",
        )
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 4))
        sub = ctk.CTkLabel(
            self.sidebar, text="  Recorder",
            font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w",
        )
        sub.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 24))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, label, icon) in enumerate([
            ("record", "Record", "⏺"),
            ("library", "Library", "▦"),
            ("settings", "Settings", "⚙"),
        ]):
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {icon}   {label}",
                anchor="w",
                height=42,
                corner_radius=10,
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=TEXT,
                font=ctk.CTkFont(size=14),
                command=lambda k=key: self._show_view(k),
            )
            btn.grid(row=2 + i, column=0, sticky="ew", padx=12, pady=4)
            self.nav_buttons[key] = btn

        version = ctk.CTkLabel(
            self.sidebar, text="v1.0.0", text_color=MUTED,
            font=ctk.CTkFont(size=11),
        )
        version.grid(row=11, column=0, sticky="sw", padx=20, pady=16)

        # --- Main area ---
        self.main = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.views: dict[str, ctk.CTkFrame] = {
            "record": self._build_record_view(),
            "library": self._build_library_view(),
            "settings": self._build_settings_view(),
        }

    def _show_view(self, key: str):
        for v in self.views.values():
            v.grid_forget()
        self.views[key].grid(row=0, column=0, sticky="nsew")

        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=SURFACE_2, text_color=TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT)

        if key == "library":
            self._refresh_library()

    # ================================================================
    # RECORD VIEW
    # ================================================================
    def _build_record_view(self) -> ctk.CTkFrame:
        v = ctk.CTkFrame(self.main, fg_color=SURFACE)
        v.grid_columnconfigure(0, weight=1)
        v.grid_rowconfigure(3, weight=1)

        header = ctk.CTkLabel(
            v, text="Record",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=TEXT, anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 4))

        sub = ctk.CTkLabel(
            v, text="Capture your screen with system audio and microphone.",
            font=ctk.CTkFont(size=13), text_color=MUTED, anchor="w",
        )
        sub.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 18))

        # Status card — big timer + record button
        card = ctk.CTkFrame(v, fg_color=SURFACE_2, corner_radius=16)
        card.grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 20))
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=24, pady=24)

        self.status_dot = ctk.CTkLabel(
            left, text="●", text_color=MUTED, font=ctk.CTkFont(size=16),
        )
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(
            left, text="  Ready", text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.grid(row=0, column=1, sticky="w")

        self.timer_label = ctk.CTkLabel(
            left, text="00:00:00", text_color=TEXT,
            font=ctk.CTkFont(size=42, weight="bold"),
        )
        self.timer_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.hotkey_hint = ctk.CTkLabel(
            left,
            text=f"Hotkeys:  {self.settings.hotkey_start_stop.upper()} start/stop  ·  "
                 f"{self.settings.hotkey_pause_resume.upper()} pause",
            text_color=MUTED, font=ctk.CTkFont(size=11),
        )
        self.hotkey_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=24, pady=24)

        self.record_btn = ctk.CTkButton(
            right, text="● Start recording",
            width=200, height=56, corner_radius=28,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self._toggle_record,
        )
        self.record_btn.grid(row=0, column=0, padx=(0, 8))

        self.pause_btn = ctk.CTkButton(
            right, text="Pause",
            width=100, height=56, corner_radius=28,
            fg_color=SURFACE, hover_color="#33353d",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._toggle_pause, state="disabled",
        )
        self.pause_btn.grid(row=0, column=1)

        # Options grid (source / audio / quality)
        opts = ctk.CTkFrame(v, fg_color="transparent")
        opts.grid(row=3, column=0, sticky="nsew", padx=32, pady=(0, 24))
        opts.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")
        opts.grid_rowconfigure(0, weight=1)

        self._build_source_card(opts).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_audio_card(opts).grid(row=0, column=1, sticky="nsew", padx=8)
        self._build_quality_card(opts).grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        return v

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        c = ctk.CTkFrame(parent, fg_color=SURFACE_2, corner_radius=14)
        c.grid_columnconfigure(0, weight=1)
        lbl = ctk.CTkLabel(
            c, text=title, text_color=TEXT, anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        return c

    def _build_source_card(self, parent) -> ctk.CTkFrame:
        card = self._card(parent, "Source")

        self.source_var = ctk.StringVar(value=self.settings.source_mode)
        for i, (val, label) in enumerate([
            ("fullscreen", "Full screen"),
            ("monitor", "Specific monitor"),
            ("region", "Custom region"),
        ]):
            rb = ctk.CTkRadioButton(
                card, text=label, variable=self.source_var, value=val,
                command=self._on_source_change,
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                text_color=TEXT, font=ctk.CTkFont(size=13),
            )
            rb.grid(row=1 + i, column=0, sticky="w", padx=18, pady=6)

        self.monitor_menu = ctk.CTkOptionMenu(
            card, values=self._monitor_labels(),
            command=self._on_monitor_change,
            fg_color=SURFACE, button_color=SURFACE, button_hover_color="#33353d",
            text_color=TEXT,
        )
        idx = self.settings.monitor_index
        labels = self._monitor_labels()
        if 1 <= idx <= len(labels):
            self.monitor_menu.set(labels[idx - 1])
        self.monitor_menu.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 10))

        self.region_btn = ctk.CTkButton(
            card, text="Select region…", height=34,
            fg_color=SURFACE, hover_color="#33353d", text_color=TEXT,
            command=self._pick_region,
        )
        self.region_btn.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.region_info = ctk.CTkLabel(
            card, text="No region selected", text_color=MUTED,
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self.region_info.grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 18))

        self._on_source_change()
        return card

    def _build_audio_card(self, parent) -> ctk.CTkFrame:
        card = self._card(parent, "Audio")

        self.mic_var = ctk.BooleanVar(value=self.settings.record_microphone)
        mic_sw = ctk.CTkSwitch(
            card, text="Microphone", variable=self.mic_var,
            command=self._persist_audio, progress_color=ACCENT,
            text_color=TEXT, font=ctk.CTkFont(size=13),
        )
        mic_sw.grid(row=1, column=0, sticky="w", padx=18, pady=(4, 8))

        self.audio_devices = list_audio_input_devices()
        device_labels = [f"{i}: {n}" for i, n in self.audio_devices] or ["No input devices"]
        self.mic_menu = ctk.CTkOptionMenu(
            card, values=device_labels, command=self._on_mic_change,
            fg_color=SURFACE, button_color=SURFACE, button_hover_color="#33353d",
            text_color=TEXT,
        )
        # preselect saved device if still present
        if self.settings.mic_device_index is not None:
            for i, n in self.audio_devices:
                if i == self.settings.mic_device_index:
                    self.mic_menu.set(f"{i}: {n}")
                    break
        self.mic_menu.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))

        self.sys_audio_var = ctk.BooleanVar(value=self.settings.record_system_audio)
        sys_sw = ctk.CTkSwitch(
            card, text="System audio (experimental)",
            variable=self.sys_audio_var, command=self._persist_audio,
            progress_color=ACCENT, text_color=TEXT,
            font=ctk.CTkFont(size=13),
        )
        sys_sw.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 6))

        note = ctk.CTkLabel(
            card,
            text="Enable Stereo Mix in Windows sound\nsettings to capture system audio.",
            text_color=MUTED, font=ctk.CTkFont(size=11), justify="left", anchor="w",
        )
        note.grid(row=4, column=0, sticky="w", padx=18, pady=(0, 18))
        return card

    def _build_quality_card(self, parent) -> ctk.CTkFrame:
        card = self._card(parent, "Quality")

        fps_lbl = ctk.CTkLabel(
            card, text="Frame rate", text_color=MUTED,
            font=ctk.CTkFont(size=12), anchor="w",
        )
        fps_lbl.grid(row=1, column=0, sticky="w", padx=18, pady=(4, 2))

        self.fps_var = ctk.StringVar(value=str(self.settings.fps))
        fps_menu = ctk.CTkOptionMenu(
            card, values=["15", "24", "30", "60"],
            variable=self.fps_var, command=self._persist_quality,
            fg_color=SURFACE, button_color=SURFACE, button_hover_color="#33353d",
            text_color=TEXT,
        )
        fps_menu.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))

        q_lbl = ctk.CTkLabel(
            card, text="Encoding quality", text_color=MUTED,
            font=ctk.CTkFont(size=12), anchor="w",
        )
        q_lbl.grid(row=3, column=0, sticky="w", padx=18, pady=(4, 2))

        self.quality_var = ctk.StringVar(value=self.settings.quality)
        q_menu = ctk.CTkOptionMenu(
            card, values=["low", "medium", "high"],
            variable=self.quality_var, command=self._persist_quality,
            fg_color=SURFACE, button_color=SURFACE, button_hover_color="#33353d",
            text_color=TEXT,
        )
        q_menu.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 18))

        return card

    # ================================================================
    # LIBRARY VIEW
    # ================================================================
    def _build_library_view(self) -> ctk.CTkFrame:
        v = ctk.CTkFrame(self.main, fg_color=SURFACE)
        v.grid_columnconfigure(0, weight=1)
        v.grid_rowconfigure(2, weight=1)

        header = ctk.CTkLabel(
            v, text="Library",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=TEXT, anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 4))

        top = ctk.CTkFrame(v, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 14))
        top.grid_columnconfigure(0, weight=1)

        self.library_path_label = ctk.CTkLabel(
            top, text="", text_color=MUTED, anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.library_path_label.grid(row=0, column=0, sticky="ew")

        open_btn = ctk.CTkButton(
            top, text="Open folder", height=32, width=120,
            fg_color=SURFACE_2, hover_color="#33353d", text_color=TEXT,
            command=lambda: self._open_path(self.settings.output_dir),
        )
        open_btn.grid(row=0, column=1, padx=(8, 0))

        refresh_btn = ctk.CTkButton(
            top, text="Refresh", height=32, width=90,
            fg_color=SURFACE_2, hover_color="#33353d", text_color=TEXT,
            command=self._refresh_library,
        )
        refresh_btn.grid(row=0, column=2, padx=(8, 0))

        self.library_scroll = ctk.CTkScrollableFrame(v, fg_color=SURFACE)
        self.library_scroll.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self.library_scroll.grid_columnconfigure(0, weight=1)

        return v

    def _refresh_library(self):
        for w in self.library_scroll.winfo_children():
            w.destroy()

        folder = self.settings.output_dir
        self.library_path_label.configure(text=folder)

        try:
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith((".mp4", ".mkv", ".avi", ".mov"))
            ]
        except FileNotFoundError:
            files = []
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        if not files:
            empty = ctk.CTkLabel(
                self.library_scroll,
                text="No recordings yet.\nYour saved clips will appear here.",
                text_color=MUTED, font=ctk.CTkFont(size=13),
                justify="center",
            )
            empty.grid(row=0, column=0, pady=60)
            return

        for i, path in enumerate(files):
            self._library_row(path).grid(row=i, column=0, sticky="ew", pady=4, padx=8)

    def _library_row(self, path: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.library_scroll, fg_color=SURFACE_2, corner_radius=12)
        row.grid_columnconfigure(1, weight=1)

        icon = ctk.CTkLabel(
            row, text="▶", text_color=ACCENT,
            font=ctk.CTkFont(size=22),
        )
        icon.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=14)

        name = os.path.basename(path)
        name_lbl = ctk.CTkLabel(
            row, text=name, text_color=TEXT, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        name_lbl.grid(row=0, column=1, sticky="ew", pady=(14, 0))

        size_mb = os.path.getsize(path) / (1024 * 1024)
        mtime = time.strftime("%b %d, %Y %H:%M", time.localtime(os.path.getmtime(path)))
        meta = ctk.CTkLabel(
            row, text=f"{mtime}  ·  {size_mb:.1f} MB",
            text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11),
        )
        meta.grid(row=1, column=1, sticky="ew", pady=(0, 14))

        play = ctk.CTkButton(
            row, text="Play", width=72, height=32,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda p=path: self._open_path(p),
        )
        play.grid(row=0, column=2, rowspan=2, padx=4, pady=14)

        show = ctk.CTkButton(
            row, text="Reveal", width=76, height=32,
            fg_color=SURFACE, hover_color="#33353d", text_color=TEXT,
            command=lambda p=path: self._reveal_in_explorer(p),
        )
        show.grid(row=0, column=3, rowspan=2, padx=4, pady=14)

        delete = ctk.CTkButton(
            row, text="Delete", width=76, height=32,
            fg_color=SURFACE, hover_color=DANGER_HOVER, text_color=TEXT,
            command=lambda p=path: self._delete_recording(p),
        )
        delete.grid(row=0, column=4, rowspan=2, padx=(4, 18), pady=14)

        return row

    # ================================================================
    # SETTINGS VIEW
    # ================================================================
    def _build_settings_view(self) -> ctk.CTkFrame:
        v = ctk.CTkFrame(self.main, fg_color=SURFACE)
        v.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            v, text="Settings",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=TEXT, anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 18))

        # --- Output folder ---
        out_card = self._card(v, "Output folder")
        out_card.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 14))

        row = ctk.CTkFrame(out_card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        row.grid_columnconfigure(0, weight=1)

        self.out_entry = ctk.CTkEntry(row, fg_color=SURFACE, border_color=SURFACE, text_color=TEXT)
        self.out_entry.insert(0, self.settings.output_dir)
        self.out_entry.configure(state="readonly")
        self.out_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)

        ctk.CTkButton(
            row, text="Browse…", width=100, height=32,
            fg_color=SURFACE, hover_color="#33353d", text_color=TEXT,
            command=self._pick_output_dir,
        ).grid(row=0, column=1)

        # --- Hotkeys ---
        hk_card = self._card(v, "Hotkeys")
        hk_card.grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 14))

        hk_row = ctk.CTkFrame(hk_card, fg_color="transparent")
        hk_row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        hk_row.grid_columnconfigure((0, 1), weight=1, uniform="h")

        self._hk_field(hk_row, "Start / stop", "hotkey_start_stop").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._hk_field(hk_row, "Pause / resume", "hotkey_pause_resume").grid(row=0, column=1, sticky="ew", padx=(8, 0))

        # --- Appearance ---
        ap_card = self._card(v, "Appearance")
        ap_card.grid(row=3, column=0, sticky="ew", padx=32, pady=(0, 14))

        self.theme_var = ctk.StringVar(value=self.settings.theme)
        ctk.CTkOptionMenu(
            ap_card, values=["dark", "light", "system"], variable=self.theme_var,
            command=self._on_theme_change,
            fg_color=SURFACE, button_color=SURFACE, button_hover_color="#33353d",
            text_color=TEXT,
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 18))

        self.min_var = ctk.BooleanVar(value=self.settings.minimize_while_recording)
        ctk.CTkSwitch(
            ap_card, text="Minimize window while recording",
            variable=self.min_var, command=self._persist_misc,
            progress_color=ACCENT, text_color=TEXT,
        ).grid(row=2, column=0, sticky="w", padx=18, pady=(0, 18))

        return v

    def _hk_field(self, parent, label: str, attr: str) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            f, text=label, text_color=MUTED, anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))

        entry = ctk.CTkEntry(f, fg_color=SURFACE, border_color=SURFACE, text_color=TEXT)
        entry.insert(0, getattr(self.settings, attr))
        entry.grid(row=1, column=0, sticky="ew", ipady=4)

        def on_change(_e=None):
            v = entry.get().strip().lower() or getattr(self.settings, attr)
            setattr(self.settings, attr, v)
            self.settings.save()
            self._register_hotkeys()
            self.hotkey_hint.configure(
                text=f"Hotkeys:  {self.settings.hotkey_start_stop.upper()} start/stop  ·  "
                     f"{self.settings.hotkey_pause_resume.upper()} pause",
            )
        entry.bind("<FocusOut>", on_change)
        entry.bind("<Return>", on_change)
        return f

    # ================================================================
    # Event handlers
    # ================================================================
    def _on_source_change(self, *_):
        mode = self.source_var.get()
        self.settings.source_mode = mode
        self.settings.save()

        self.monitor_menu.configure(state="normal" if mode == "monitor" else "disabled")
        self.region_btn.configure(state="normal" if mode == "region" else "disabled")
        if mode != "region":
            self._custom_region = None
            self.region_info.configure(text="No region selected")

    def _monitor_labels(self) -> list[str]:
        mons = list_monitors()
        # mons[0] is the virtual "all monitors" entry; expose the individual ones
        labels = []
        for i, m in enumerate(mons[1:], start=1):
            labels.append(f"Monitor {i}  ·  {m['width']}×{m['height']}")
        return labels or ["Monitor 1"]

    def _on_monitor_change(self, value: str):
        try:
            idx = int(value.split()[1])
        except (ValueError, IndexError):
            idx = 1
        self.settings.monitor_index = idx
        self.settings.save()

    def _pick_region(self):
        self.withdraw()
        self.update()
        time.sleep(0.15)
        region = select_region(self)
        self.deiconify()
        if region:
            self._custom_region = region
            self.region_info.configure(
                text=f"Region: {region[2]}×{region[3]} at ({region[0]}, {region[1]})",
            )

    def _persist_audio(self, *_):
        self.settings.record_microphone = self.mic_var.get()
        self.settings.record_system_audio = self.sys_audio_var.get()
        self.settings.save()

    def _on_mic_change(self, value: str):
        try:
            idx = int(value.split(":", 1)[0])
            self.settings.mic_device_index = idx
        except ValueError:
            self.settings.mic_device_index = None
        self.settings.save()

    def _persist_quality(self, *_):
        try:
            self.settings.fps = int(self.fps_var.get())
        except ValueError:
            self.settings.fps = 30
        self.settings.quality = self.quality_var.get()
        self.settings.save()

    def _on_theme_change(self, value: str):
        self.settings.theme = value
        self.settings.save()
        ctk.set_appearance_mode(value)

    def _persist_misc(self, *_):
        self.settings.minimize_while_recording = self.min_var.get()
        self.settings.save()

    def _pick_output_dir(self):
        folder = filedialog.askdirectory(initialdir=self.settings.output_dir)
        if folder:
            self.settings.output_dir = folder
            self.settings.save()
            self.out_entry.configure(state="normal")
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, folder)
            self.out_entry.configure(state="readonly")

    # ================================================================
    # Recording control
    # ================================================================
    def _toggle_record(self):
        if self.recorder and self.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _toggle_pause(self):
        if not self.recorder or not self.recorder.is_recording:
            return
        if self.recorder.is_paused:
            self.recorder.resume()
            self.pause_btn.configure(text="Pause")
        else:
            self.recorder.pause()
            self.pause_btn.configure(text="Resume")

    def _start_recording(self):
        mode = self.source_var.get()
        region = None
        if mode == "region":
            if not self._custom_region:
                messagebox.showwarning(APP_NAME, "Please select a region first.")
                return
            region = self._custom_region

        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join(self.settings.output_dir, f"recording_{ts}.mp4")

        cfg = RecordingConfig(
            output_path=out_path,
            fps=int(self.fps_var.get() or 30),
            region=region,
            monitor_index=self.settings.monitor_index if mode != "fullscreen" else 1,
            record_system_audio=self.sys_audio_var.get(),
            record_microphone=self.mic_var.get(),
            mic_device_index=self.settings.mic_device_index,
            quality=self.quality_var.get(),
        )

        def status_cb(s: str):
            self.after(0, lambda: self._apply_status(s))

        self.recorder = ScreenRecorder(cfg, on_status=status_cb)

        try:
            self.recorder.start()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Failed to start recording:\n{e}")
            self.recorder = None
            return

        self.record_btn.configure(text="■ Stop recording", fg_color=DANGER, hover_color=DANGER_HOVER)
        self.pause_btn.configure(state="normal", text="Pause")
        self._apply_status("recording")
        self._tick_timer()

        if self.settings.minimize_while_recording:
            self.iconify()

    def _stop_recording(self):
        if not self.recorder:
            return
        self.record_btn.configure(state="disabled", text="Encoding…")
        self.pause_btn.configure(state="disabled")

        def worker():
            path = self.recorder.stop() if self.recorder else ""
            self.after(0, lambda: self._on_recording_saved(path))

        threading.Thread(target=worker, daemon=True).start()

    def _on_recording_saved(self, path: str):
        self.recorder = None
        if self._ticker_id:
            self.after_cancel(self._ticker_id)
            self._ticker_id = None
        self.timer_label.configure(text="00:00:00")
        self.record_btn.configure(
            state="normal", text="● Start recording",
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
        )
        self.pause_btn.configure(state="disabled", text="Pause")

        if self.state() == "iconic":
            self.deiconify()

        if path and os.path.exists(path):
            self._apply_status("ready")
            self._notify_saved(path)
        else:
            self._apply_status("error")
            messagebox.showerror(APP_NAME, "Recording failed to save.")

    def _notify_saved(self, path: str):
        ans = messagebox.askyesno(APP_NAME, f"Recording saved:\n{path}\n\nOpen now?")
        if ans:
            self._open_path(path)

    def _apply_status(self, status: str):
        mapping = {
            "ready": ("Ready", MUTED),
            "recording": ("Recording", "#ff4d4d"),
            "paused": ("Paused", "#ffb84d"),
            "encoding": ("Encoding…", ACCENT),
            "done": ("Ready", MUTED),
            "error": ("Error", DANGER),
        }
        label, color = mapping.get(status, ("Ready", MUTED))
        self.status_dot.configure(text_color=color)
        self.status_label.configure(text=f"  {label}")

    def _tick_timer(self):
        if self.recorder and self.recorder.is_recording:
            self.timer_label.configure(text=_format_time(self.recorder.elapsed()))
            self._ticker_id = self.after(250, self._tick_timer)

    # ================================================================
    # Hotkeys
    # ================================================================
    def _register_hotkeys(self):
        try:
            import keyboard  # local import so the app still works if the module is missing
        except Exception:
            return

        for h in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass
        self._hotkey_handles.clear()

        try:
            h1 = keyboard.add_hotkey(
                self.settings.hotkey_start_stop,
                lambda: self.after(0, self._toggle_record),
            )
            h2 = keyboard.add_hotkey(
                self.settings.hotkey_pause_resume,
                lambda: self.after(0, self._toggle_pause),
            )
            self._hotkey_handles.extend([h1, h2])
        except (ValueError, Exception):
            pass  # invalid combo — silently ignore

    # ================================================================
    # Misc
    # ================================================================
    def _open_path(self, path: str):
        if not os.path.exists(path):
            messagebox.showerror(APP_NAME, f"Not found:\n{path}")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", path])

    def _reveal_in_explorer(self, path: str):
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            self._open_path(os.path.dirname(path))

    def _delete_recording(self, path: str):
        if not messagebox.askyesno(APP_NAME, f"Delete this recording?\n{os.path.basename(path)}"):
            return
        try:
            os.remove(path)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not delete:\n{e}")
        self._refresh_library()

    def _on_close(self):
        if self.recorder and self.recorder.is_recording:
            if not messagebox.askyesno(APP_NAME, "A recording is in progress. Stop and exit?"):
                return
            try:
                self.recorder.stop()
            except Exception:
                pass
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.destroy()


def run():
    app = LumenApp()
    app.mainloop()


if __name__ == "__main__":
    run()
