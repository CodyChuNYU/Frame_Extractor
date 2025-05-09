import asyncio, subprocess, random, os, sys, time, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError, TimeoutError
import gradio as gr

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

stop_flag = False
CPU_COUNT = os.cpu_count() or 4
current_process = None
current_executor = None

def get_video_duration(p):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(p)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        duration = result.stdout.strip()
        if not duration:
            raise ValueError(f"ffprobe failed to read duration for: {p}")
        return float(duration)
    except Exception as e:
        print(f"\n❌ Error reading duration from {p}: {e}")
        return -1

def get_video_fps(p):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(p)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        rate = result.stdout.strip()
        if not rate or '/' not in rate:
            raise ValueError(f"ffprobe failed to read FPS from: {p}")
        n, d = rate.split('/')
        return float(n) / float(d)
    except Exception as e:
        print(f"\n❌ Error reading FPS from {p}: {e}")
        return -1

def get_random_timestamps(dur, total):
    s = dur / total
    return random.sample([
        round(random.uniform(i * s + 0.001, max(i * s + 0.002, (i + 1) * s - 0.001)), 3)
        for i in range(total)
    ], total)

def process_frame(stem, path, idx, ts, out):
    fn = f"{stem}_rand_{idx:03}_{ts:.3f}s.png"
    o = Path(out) / fn
    subprocess.run(
        ['ffmpeg', '-threads', '1', '-ss', str(ts), '-i', str(path),
         '-frames:v', '1', str(o), '-loglevel', 'error']
    )
    return o.exists(), str(o), idx, ts, fn

def preview_start_frame(p, f):
    return preview_frame(p, f, "preview_start.png")

def preview_end_frame(p, f):
    return preview_frame(p, f, "preview_end.png")

def preview_frame(p, f, name):
    if not p:
        return None
    o = Path(tempfile.gettempdir()) / name
    if o.exists():
        o.unlink()
    subprocess.run(
        ['ffmpeg', '-ss', str((f - 1) / get_video_fps(p)), '-i', str(p),
         '-frames:v', '1', str(o), '-loglevel', 'error']
    )
    return str(o)

def on_video_load(p):
    if not p:
        return [gr.update(minimum=1, maximum=1, step=1, value=1),
                gr.update(minimum=1, maximum=1, step=1, value=1),
                None, None, gr.update(visible=False)]
    d, f = get_video_duration(p), get_video_fps(p)
    t = int(d * f)
    return [gr.update(minimum=1, maximum=t, step=1, value=1),
            gr.update(minimum=1, maximum=t, step=1, value=t),
            preview_start_frame(p, 1),
            preview_end_frame(p, t),
            gr.update(visible=True)]

def extract_frames(mode, folder, single, start, end, count, out, all_frames, jobs, interval):
    global stop_flag, current_process, current_executor
    stop_flag = False
    current_process = None
    current_executor = None

    out = out.strip() or "./ExtractedFrames"
    Path(out).mkdir(parents=True, exist_ok=True)

    vids = [Path(single)] if mode == "Single Video" else [
        v for v in Path(folder).iterdir() if v.suffix.lower() in {'.mp4', '.mov', '.mkv'}]

    for v in vids:
        if stop_flag:
            yield None, "🛑 Stopped."
            return

        stem = v.stem
        dur = get_video_duration(v)
        fps = get_video_fps(v)
        if dur <= 0 or fps <= 0:
            print(f"\n⚠️ Skipping {v} due to unreadable metadata.")
            yield None, f"⚠️ Skipped {v.name}"
            continue

        t0, total_extracted = time.time(), 0

        if all_frames:
            s_ts, e_ts = (start - 1) / fps, (end - 1) / fps
            interval = max(1, int(interval))
            tpl = str(Path(out) / f"{stem}_range_%04d.png")
            total = int((e_ts - s_ts) * fps / interval) + 1
            print(f"\n📼 Exporting Every {interval}th Frame from {stem} — estimated {total} frames")
            cmd = ['ffmpeg', '-threads', '1', '-ss', str(s_ts), '-to', str(e_ts), '-i', str(v),
                   '-vf', f"select=not(mod(n\\,{interval})),setpts=N/FRAME_RATE/TB",
                   '-vsync', 'vfr', '-hide_banner', '-loglevel', 'error', tpl]
            try:
                current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                last_printed = -1
                while current_process and current_process.poll() is None:
                    if stop_flag:
                        current_process.terminate()
                        print(f"\n⛔ {stem} extraction stopped by user.")
                        break
                    extracted = len(list(Path(out).glob(f"{stem}_range_*.png")))
                    if extracted != last_printed:
                        elapsed = max(time.time() - t0, 0.001)
                        rate = extracted / elapsed
                        pct = (extracted / total) * 100
                        eta = (total - extracted) / rate if rate else 0
                        bar = '=' * int((extracted / total) * 30)
                        sys.stdout.write(f"\r[{bar:<30}] {extracted:4}/{total:<4} | {rate:5.1f} fps | ETA: {eta:5.1f}s | {pct:5.1f}%")
                        sys.stdout.flush()
                        last_printed = extracted
                        yield str(Path(out) / f"{stem}_range_{extracted:04d}.png"), f"{stem}: {extracted}/{total}"
                    time.sleep(0.05)
            finally:
                try:
                    current_process.wait()
                except:
                    pass
                current_process = None
            print(f"\n✅ Done with {stem}. Total frames: {total}")
            continue

        stamps = get_random_timestamps(dur, count)
        existing = {float(p.stem.split('_')[-1][:-1]) for p in Path(out).glob(f"{stem}_rand_*_*.png") if p.stem.split('_')[-1].endswith('s')}
        work = [(i, ts) for i, ts in enumerate(stamps, 1) if ts not in existing]
        total = len(work)
        print(f"\n🎲 Extracting {total} random frames from {stem}")
        current_executor = ThreadPoolExecutor(max_workers=jobs)
        try:
            with current_executor as pool:
                futures = {pool.submit(process_frame, stem, v, i, ts, out): (i, ts) for i, ts in work}
                completed = 0
                for fut in as_completed(futures):
                    if stop_flag:
                        print(f"\n⛔ {stem} random extraction stopped.")
                        break
                    try:
                        ok, path, _, _, fn = fut.result(timeout=2)
                    except (CancelledError, TimeoutError):
                        continue
                    except Exception as e:
                        print(f"\n⚠️ Future failed: {e}")
                        continue
                    if ok:
                        completed += 1
                        elapsed = max(time.time() - t0, 0.001)
                        rate = completed / elapsed
                        pct = (completed / total) * 100
                        eta = (total - completed) / rate if rate else 0
                        bar = '=' * int((completed / total) * 30)
                        sys.stdout.write(f"\r[{bar:<30}] {completed:4}/{total:<4} | {rate:5.1f} fps | ETA: {eta:5.1f}s | {pct:5.1f}%")
                        sys.stdout.flush()
                        yield path, f"{stem}: {completed}/{total}"
                    else:
                        yield None, f"{stem}: failed {fn}"
        finally:
            current_executor = None
            print(f"\n✅ Done with {stem}. Total random frames: {total}")
    print("\n✅ All videos processed.")
    yield None, "✅ Done."

def set_stop_flag():
    global stop_flag, current_process, current_executor
    stop_flag = True
    if current_process:
        current_process.terminate()
        current_process = None
    if current_executor:
        current_executor.shutdown(wait=False, cancel_futures=True)
        current_executor = None
    return "🛑 Stopping..."

with gr.Blocks() as app:
    gr.Markdown("# 🎞️ Frame Extractor — Folder or Single Video")
    jobs = gr.Slider(label="CPU Threads", minimum=1, maximum=CPU_COUNT, step=1, value=min(8, CPU_COUNT))
    out = gr.Textbox(label="Output Folder", placeholder="C:/Frames (leave blank for default)")
    mode = gr.Radio(choices=["Folder", "Single Video"], label="Input Mode", value="Folder")
    folder = gr.Textbox(label="Video Folder", placeholder="C:/Videos")
    single = gr.File(file_count="single", type="filepath", visible=False, file_types=['.mp4', '.mov', '.mkv'], label="Single Video File")
    s, e = gr.Slider(label="Start Frame", minimum=1, maximum=1, step=1, value=1, visible=False), gr.Slider(label="End Frame", minimum=1, maximum=1, step=1, value=1, visible=False)
    with gr.Row(visible=False) as preview_row:
        p1 = gr.Image(type="filepath", label="Start Frame Preview")
        p2 = gr.Image(type="filepath", label="End Frame Preview")
    count = gr.Number(label="Total Frames Per Video", value=10, precision=0)
    all_chk = gr.Checkbox(label="Export ALL Frames", value=False)
    interval = gr.Number(label="Frame Interval (Every Nth Frame)", value=1, precision=0, visible=False)
    run, stop, status = gr.Button("▶️ Start Extraction"), gr.Button("🛑 Stop"), gr.Textbox(label="Status", interactive=False)
    preview = gr.Image(type="filepath", label="Frame Output")
    mode.change(fn=lambda m: (
        gr.update(visible=m != "Single Video"),
        gr.update(visible=m == "Single Video"),
        gr.update(visible=m == "Single Video"),
        gr.update(visible=m == "Single Video"),
        gr.update(visible=m == "Single Video"),
        gr.update(visible=m == "Single Video"),
        gr.update(visible=m == "Single Video")
    ), inputs=mode, outputs=[folder, single, s, e, p1, p2, preview_row])
    single.change(fn=on_video_load, inputs=[single], outputs=[s, e, p1, p2, preview_row])
    s.change(fn=preview_start_frame, inputs=[single, s], outputs=[p1])
    e.change(fn=preview_end_frame, inputs=[single, e], outputs=[p2])
    all_chk.change(fn=lambda c: [gr.update(visible=not c), gr.update(visible=c)], inputs=all_chk, outputs=[count, interval])
    app.queue()
    run.click(fn=extract_frames, inputs=[mode, folder, single, s, e, count, out, all_chk, jobs, interval], outputs=[preview, status], queue=True)
    stop.click(fn=set_stop_flag, inputs=None, outputs=[status])

if __name__ == "__main__":
    app.launch(inbrowser=True)
