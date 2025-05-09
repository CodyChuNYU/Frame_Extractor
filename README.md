# 🎞️ Frame Extractor

**Frame Extractor** is a Gradio-powered app built by **Cody Chu** that lets you extract random or full sequences of frames from videos using FFmpeg. It supports both batch-folder and single-video modes, and includes real-time frame previews, slider-based range selection, multithreaded performance, and a live CLI progress bar.

---

## 🔧 Features

- ✅ Extract **random frames** (evenly distributed, no duplicates)
- ✅ Export **every Nth frame** from a range (frame-accurate)
- ✅ Smart **start/end preview handling** — skips broken frames
- ✅ Multithreaded **FFmpeg execution** using all CPU cores
- ✅ Live progress bar **with file name + FPS + ETA**
- ✅ Supports **single video** or **batch folder mode**
- ✅ Clean **Stop/Resume** with graceful cancellation
- ✅ Works on **Windows, macOS, and Linux**

---

## 📦 Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) installed and in your system PATH
- Gradio 4.x (tested with `4.41.0`+)

Install dependencies:

```bash
pip install gradio
```

---

## 🚀 How to Use

```bash
python frame_extractor.py
```

The app will launch in your browser.

---

## 🖥️ Interface Overview

| Control                    | Description                                                                 |
|----------------------------|-----------------------------------------------------------------------------|
| **Input Mode**             | Choose between `Folder` (batch mode) or `Single Video`                     |
| **Output Folder**          | Destination for extracted PNG frames                                       |
| **Start/End Frame Sliders**| Defines the frame range in `Single Video` mode (auto-validates if broken)  |
| **Start/End Preview**      | Dynamically loads valid nearest preview frame (even if exact one fails)    |
| **Total Frames Per Video** | In Random Mode, how many frames to grab                                    |
| **Export ALL Frames**      | Toggle between Random and Full Export modes                                |
| **Frame Interval**         | For "All Frames", export every Nth frame                                    |
| **CPU Threads**            | Controls how many threads to run in parallel (auto uses all with FFmpeg)   |
| **Stop Button**            | Cancels extraction mid-process, cleanly                                     |

---

## 🛑 Stopping

Clicking "🛑 Stop" will:
- Terminate any running `ffmpeg` process
- Cancel active background threads
- Clean up and return control immediately
- No crashes, no hanging — fully safe

---

## 📝 Notes

- Frame previews will auto-adjust if frames are unreadable
- Multithreaded performance is **enabled by default**
- Frame file names include timestamps (for random) or frame numbers (for range)
- Output supports `.mp4`, `.mov`, `.mkv` inputs only
- Gradio UI is styled for minimalism and accessibility

---

## 📂 Example Output

```
video1_rand_001_12.345s.png
video2_range_0042.png
```

---

## 🧠 How It Works

- Uses `ffprobe` to detect video **duration** and **FPS**
- Computes **evenly spaced timestamps** for random mode
- Uses `ffmpeg` with **-threads 0** to auto-scale to all CPU cores
- Multithreaded frame grabbing using `ThreadPoolExecutor`
- Skips already-extracted files
- Smart preview sliders auto-locate the nearest working frame


---

## 🛠 Troubleshooting

| Problem                                 | Fix                                                              |
|-----------------------------------------|------------------------------------------------------------------|
| FFmpeg not found                        | Make sure it's in your system PATH                               |
| App crashes on stop                     | Fixed — now uses graceful cancel logic                           |
| Frames not saving                       | Check output path and write permissions                          |
| Blank or missing previews               | Will now auto-fallback to nearest valid frame                    |
| Gradio version mismatch                 | Requires `gradio>=4.41.0`                                        |

---

## 📄 License

MIT License © 2025 Cody Chu
