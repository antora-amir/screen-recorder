# Lumen Recorder

A modern screen recorder for Windows with a clean dark UI. Inspired by OBS Studio and ShareX.

![platform: Windows](https://img.shields.io/badge/platform-Windows-blue) ![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

## Features

- **Three capture sources** — full screen, a specific monitor, or a custom drag-to-select region
- **Audio** — microphone (with device picker) and optional system audio (via Windows Stereo Mix)
- **Quality controls** — 15 / 24 / 30 / 60 FPS and low / medium / high H.264 encoding
- **Controls** — start, stop, pause, resume with a live timer
- **Global hotkeys** — F9 start/stop, F10 pause (customizable)
- **Library view** — every saved recording with play, reveal-in-Explorer, and delete
- **Settings** — custom output folder, theme (dark / light / system), auto-minimize while recording
- **Self-contained ffmpeg** — no external install needed; bundled via `imageio-ffmpeg`
- **Single-file build** — ship one `.exe` that runs on any Windows PC

## Quick start (source)

Requires Python 3.10 or newer. Python 3.12 is the most compatible.

```bat
install.bat   :: one-time: creates .venv and installs deps
run.bat       :: launches the app
```

Settings and recordings persist between sessions:

- Settings: `%APPDATA%\Lumen Recorder\settings.json`
- Recordings (default): `%USERPROFILE%\Videos\Lumen Recorder\`

## Build a standalone `.exe`

Produces a single file you can copy to any Windows machine — no Python or dependencies needed on the target PC.

```bat
install.bat   :: if you haven't already
build.bat     :: bundles with PyInstaller into dist\LumenRecorder.exe
```

The resulting `dist\LumenRecorder.exe` is ~80–120 MB (it includes Python, Tk, ffmpeg, OpenCV, and Pillow). Double-click to run.

## Usage

1. Launch the app.
2. On the **Record** tab pick a source (full screen / monitor / custom region), toggle mic and system audio, and choose FPS and quality.
3. Click **● Start recording** or press **F9**. Press **F10** to pause.
4. Click **■ Stop recording** (or press **F9** again). The file is encoded to MP4 and saved automatically.
5. Open the **Library** tab to play, reveal, or delete recordings.

### System audio

Windows doesn't expose "what you hear" as a default input. To record system audio:

1. Right-click the speaker icon in the taskbar → **Sound settings** → **More sound settings**.
2. In the **Recording** tab, right-click empty space → **Show disabled devices**.
3. Enable **Stereo Mix**, then select it as the mic device in Lumen's Audio card.

## Troubleshooting

### `pip` can't build Pillow / numpy / opencv on install

You're probably on a very new Python (3.14+) that has no prebuilt wheels yet. Install **Python 3.12** from python.org and edit `install.bat`:

```bat
set "PYTHON=py -3.12"
```

Delete the old `.venv` folder and rerun `install.bat`.

### Hotkeys don't fire

The `keyboard` library uses a global hook. On some systems it needs the app to run as administrator. Right-click `run.bat` → **Run as administrator**.

### Recorded video has no sound

- Confirm the **Microphone** switch is on.
- In the Audio card, pick the correct input device from the dropdown.
- For system audio, see the Stereo Mix steps above.

### Recording looks laggy at 60 FPS

Python-based screen capture at 60 FPS is demanding. Drop to 30 FPS, or reduce quality to `medium` / `low` to lighten the encode cost.

## Project layout

```
.
├── main.py                    # Entry point
├── src/
│   ├── app.py                 # CustomTkinter UI (Record / Library / Settings)
│   ├── recorder.py            # mss + OpenCV video, sounddevice audio, ffmpeg mux
│   ├── region_selector.py     # Fullscreen drag-to-select overlay
│   └── settings.py            # JSON settings persistence
├── requirements.txt
├── install.bat                # Creates .venv and installs deps
├── run.bat                    # Launches the app
└── build.bat                  # Builds dist\LumenRecorder.exe via PyInstaller
```

## Tech stack

- **UI** — [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- **Screen capture** — [mss](https://github.com/BoboTiG/python-mss) (fast DXGI-backed grab)
- **Video encoding** — [OpenCV](https://opencv.org/) for intermediate frames, [ffmpeg](https://ffmpeg.org/) via [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) for final H.264 encode and mux
- **Audio** — [sounddevice](https://python-sounddevice.readthedocs.io/) + [soundfile](https://pysoundfile.readthedocs.io/)
- **Hotkeys** — [keyboard](https://github.com/boppreh/keyboard)

## License

MIT
