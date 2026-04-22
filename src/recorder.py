"""Video + audio capture engine."""
from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import imageio_ffmpeg
import mss
import numpy as np
import sounddevice as sd
import soundfile as sf


@dataclass
class RecordingConfig:
    output_path: str
    fps: int = 30
    region: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h) in physical pixels
    monitor_index: int = 1  # mss monitor index (0 = all)
    record_system_audio: bool = False
    record_microphone: bool = True
    mic_device_index: Optional[int] = None
    quality: str = "high"  # low / medium / high


_QUALITY_CRF = {"low": 30, "medium": 24, "high": 20}


class ScreenRecorder:
    """Captures screen + audio on background threads and muxes to MP4."""

    def __init__(self, config: RecordingConfig, on_status: Optional[Callable[[str], None]] = None):
        self.config = config
        self.on_status = on_status or (lambda s: None)

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._video_thread: Optional[threading.Thread] = None
        self._audio_thread: Optional[threading.Thread] = None

        self._video_tmp = ""
        self._audio_tmp = ""
        self._start_time: float = 0.0
        self._paused_accum: float = 0.0
        self._pause_start: float = 0.0

        self._frame_count = 0
        self._is_recording = False

    # ----- public API -----
    @property
    def is_recording(self) -> bool:
        return self._is_recording

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def elapsed(self) -> float:
        if not self._is_recording:
            return 0.0
        now = time.time()
        extra = (now - self._pause_start) if self._pause_event.is_set() else 0.0
        return max(0.0, now - self._start_time - self._paused_accum - extra)

    def start(self) -> None:
        if self._is_recording:
            return

        os.makedirs(os.path.dirname(os.path.abspath(self.config.output_path)), exist_ok=True)

        tmp_dir = tempfile.gettempdir()
        stamp = int(time.time() * 1000)
        self._video_tmp = os.path.join(tmp_dir, f"sr_vid_{stamp}.mp4")
        self._audio_tmp = os.path.join(tmp_dir, f"sr_aud_{stamp}.wav")

        self._stop_event.clear()
        self._pause_event.clear()
        self._frame_count = 0
        self._paused_accum = 0.0
        self._start_time = time.time()
        self._is_recording = True

        self._video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self._video_thread.start()

        if self.config.record_microphone or self.config.record_system_audio:
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()

        self.on_status("recording")

    def pause(self) -> None:
        if not self._is_recording or self._pause_event.is_set():
            return
        self._pause_start = time.time()
        self._pause_event.set()
        self.on_status("paused")

    def resume(self) -> None:
        if not self._is_recording or not self._pause_event.is_set():
            return
        self._paused_accum += time.time() - self._pause_start
        self._pause_event.clear()
        self.on_status("recording")

    def stop(self) -> str:
        if not self._is_recording:
            return ""

        self._stop_event.set()
        self._pause_event.clear()

        if self._video_thread:
            self._video_thread.join(timeout=10)
        if self._audio_thread:
            self._audio_thread.join(timeout=10)

        self._is_recording = False
        self.on_status("encoding")

        final_path = self._mux()

        for p in (self._video_tmp, self._audio_tmp):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

        self.on_status("done")
        return final_path

    # ----- internals -----
    def _get_monitor(self, sct: mss.mss) -> dict:
        if self.config.region is not None:
            x, y, w, h = self.config.region
            return {"left": x, "top": y, "width": w, "height": h}
        idx = self.config.monitor_index
        monitors = sct.monitors
        if idx < 0 or idx >= len(monitors):
            idx = 1 if len(monitors) > 1 else 0
        return monitors[idx]

    def _video_loop(self) -> None:
        with mss.mss() as sct:
            monitor = self._get_monitor(sct)
            width = monitor["width"] - (monitor["width"] % 2)
            height = monitor["height"] - (monitor["height"] % 2)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(self._video_tmp, fourcc, self.config.fps, (width, height))
            if not writer.isOpened():
                self.on_status("error: could not open video writer")
                return

            frame_dt = 1.0 / self.config.fps
            next_t = time.time()

            try:
                while not self._stop_event.is_set():
                    if self._pause_event.is_set():
                        time.sleep(0.05)
                        next_t = time.time()
                        continue

                    img = np.asarray(sct.grab(monitor))  # BGRA
                    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    writer.write(frame)
                    self._frame_count += 1

                    next_t += frame_dt
                    sleep = next_t - time.time()
                    if sleep > 0:
                        time.sleep(sleep)
                    else:
                        next_t = time.time()
            finally:
                writer.release()

    def _audio_loop(self) -> None:
        samplerate = 44100
        channels = 2
        q: "queue.Queue[np.ndarray]" = queue.Queue()

        def callback(indata, frames, _time, status):
            if status:
                pass
            if not self._pause_event.is_set():
                q.put(indata.copy())

        device = self.config.mic_device_index
        try:
            with sf.SoundFile(self._audio_tmp, mode="w", samplerate=samplerate,
                              channels=channels, subtype="PCM_16") as f:
                with sd.InputStream(samplerate=samplerate, channels=channels,
                                    dtype="int16", callback=callback, device=device):
                    while not self._stop_event.is_set():
                        try:
                            data = q.get(timeout=0.2)
                            f.write(data)
                        except queue.Empty:
                            continue
                # drain
                while not q.empty():
                    try:
                        f.write(q.get_nowait())
                    except queue.Empty:
                        break
        except Exception as e:
            self.on_status(f"audio error: {e}")

    def _mux(self) -> str:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        crf = _QUALITY_CRF.get(self.config.quality, 23)
        out = self.config.output_path
        has_audio = os.path.exists(self._audio_tmp) and os.path.getsize(self._audio_tmp) > 1024

        cmd = [ffmpeg, "-y", "-i", self._video_tmp]
        if has_audio:
            cmd += ["-i", self._audio_tmp]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += [out]

        try:
            subprocess.run(cmd, capture_output=True, check=True,
                           creationflags=_no_window_flag())
            return out
        except subprocess.CalledProcessError:
            # Fallback: keep the raw mp4v file if re-encode fails
            try:
                if os.path.exists(self._video_tmp):
                    if os.path.exists(out):
                        os.remove(out)
                    os.replace(self._video_tmp, out)
                    return out
            except OSError:
                pass
            return ""


def _no_window_flag() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def list_audio_input_devices() -> list[tuple[int, str]]:
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                devices.append((i, d["name"]))
    except Exception:
        pass
    return devices


def list_monitors() -> list[dict]:
    with mss.mss() as sct:
        return list(sct.monitors)
