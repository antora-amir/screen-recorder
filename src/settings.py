"""Persistent user settings stored as JSON in %APPDATA%/Lumen Recorder."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field


APP_NAME = "Lumen Recorder"


def _app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def default_output_dir() -> str:
    videos = os.path.join(os.path.expanduser("~"), "Videos", APP_NAME)
    os.makedirs(videos, exist_ok=True)
    return videos


@dataclass
class Settings:
    output_dir: str = field(default_factory=default_output_dir)
    fps: int = 30
    quality: str = "high"
    source_mode: str = "fullscreen"  # fullscreen / region / monitor
    monitor_index: int = 1
    record_microphone: bool = True
    record_system_audio: bool = False
    mic_device_index: int | None = None
    hotkey_start_stop: str = "f9"
    hotkey_pause_resume: str = "f10"
    minimize_while_recording: bool = True
    theme: str = "dark"  # dark / light / system

    @property
    def file_path(self) -> str:
        return os.path.join(_app_data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        inst = cls()
        try:
            with open(inst.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(inst, k):
                    setattr(inst, k, v)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return inst

    def save(self) -> None:
        data = asdict(self)
        data.pop("file_path", None)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
