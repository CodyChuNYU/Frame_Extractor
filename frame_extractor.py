import asyncio, subprocess, random, os, sys, time, tempfile, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import gradio as gr

if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

stop_flag = False
CPU_COUNT = os.cpu_count() or 4
current_executor = None
PREVIEW_EVERY = 2  # Live preview update frequency

def sanitize_filename(name): return re.sub(r'[<>:"/\\|?*]', '_', name)

def get_video_duration(p):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                 '-of', 'default=noprint_wrappers=1:nokey=1', str(p)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except: return -1

def get_video_fps(p):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=r_frame_rate',
                                 '-of', 'default=noprint_wrappers=1:nokey=1', str(p)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        rate = result.stdout.strip()
        if '/' in rate:
            n, d = rate.split('/')
            return float(n) / float(d)
        return float(rate)
    except: return -1

def preview_frame(p, f, name):
    if not p: return None
    o = Path(tempfile.gettempdir()) / name
    if o.exists(): o.unlink()
    fps = get_video_fps(p)
    ts = max((f - 1) / fps, 0)
    subprocess.run(['ffmpeg', '-y', '-ss', str(ts), '-i', str(p), '-frames:v', '1', str(o), '-loglevel', 'error'])
    return str(o)

def preview_start_frame(p, f): return preview_frame(p, f, "preview_start.png")
def preview_end_frame(p, f): return preview_frame(p, f, "preview_end.png")

def on_video_load(p):
    if not p: return [gr.update(minimum=1, maximum=1), gr.update(minimum=1, maximum=1), None, None, gr.update(visible=False)]
    d, f = get_video_duration(p), get_video_fps(p)
    t = int(d * f)
    return [gr.update(minimum=1, maximum=t, value=1), gr.update(minimum=1, maximum=t, value=t),
            preview_start_frame(p, 1), preview_end_frame(p, t), gr.update(visible=True)]

def extract_frames(mode, folder, single, start, end, count, out, all_frames, jobs, interval):
    global stop_flag, current_executor
    stop_flag = False
    out = out.strip() or "./ExtractedFrames"
    Path(out).mkdir(parents=True, exist_ok=True)
    interval = max(1, int(interval or 1))

    vids = [Path(single)] if mode == "Single Video" else [v for v in Path(folder).iterdir() if v.suffix.lower() in {'.mp4', '.mov', '.mkv'}]

    for v in vids:
        if stop_flag: yield None, "🛑 Stopped."; return
        stem = sanitize_filename(v.stem)
        dur = get_video_duration(v)
        fps = get_video_fps(v)
        if dur <= 0 or fps <= 0: yield None, f"⚠️ Skipped {v.name}"; continue

        t0 = time.time()
        yield None, f"⚙️ Processing {v.name}..."

        if all_frames:
            frame_total = int(dur * fps)
            start_frame = (start - 1) if mode == "Single Video" else 0
            end_frame = (end - 1) if mode == "Single Video" else frame_total - 1
            frame_numbers = [i for i in range(int(start_frame), int(end_frame) + 1) if (i - int(start_frame)) % interval == 0]

            yield None, f"📸 Extracting {len(frame_numbers)} frames from {stem}..."
            current_executor = ThreadPoolExecutor(max_workers=jobs)
            completed = 0
            last_preview_path = None
            try:
                futures = {current_executor.submit(extract_frame_by_number, v, fps, fn, out, stem): fn for fn in frame_numbers}
                for fut in as_completed(futures):
                    if stop_flag: break
                    try:
                        ok, out_path, fn = fut.result()
                        completed += 1
                        rate = completed / (time.time() - t0)
                        bar = '=' * int((completed / len(frame_numbers)) * 30)
                        sys.stdout.write(f"\r[{bar:<30}] {completed}/{len(frame_numbers)} | {rate:.1f} fps")
                        sys.stdout.flush()

                        if completed % PREVIEW_EVERY == 0 or completed == len(frame_numbers):
                            last_preview_path = out_path
                            yield out_path, f"{stem}: {completed}/{len(frame_numbers)}"
                        else:
                            yield last_preview_path, f"{stem}: {completed}/{len(frame_numbers)}"
                    except Exception as e:
                        print(f"⚠️ Failed: {e}")
            finally:
                if current_executor:
                    current_executor.shutdown(wait=False, cancel_futures=True)
                    current_executor = None
                print(f"\n✅ Done with {stem}")
            continue

        # RANDOM MODE
        stamps = get_random_timestamps(dur, count)
        frame_numbers = sorted({int(ts * fps) for ts in stamps})
        yield None, f"🎲 Extracting {len(frame_numbers)} random frames from {stem}"
        current_executor = ThreadPoolExecutor(max_workers=jobs)
        completed = 0
        last_preview_path = None
        try:
            futures = {current_executor.submit(extract_frame_by_number, v, fps, fn, out, stem): fn for fn in frame_numbers}
            for fut in as_completed(futures):
                if stop_flag: break
                try:
                    ok, out_path, fn = fut.result()
                    completed += 1
                    rate = completed / (time.time() - t0)
                    bar = '=' * int((completed / len(frame_numbers)) * 30)
                    sys.stdout.write(f"\r[{bar:<30}] {completed}/{len(frame_numbers)} | {rate:.1f} fps")
                    sys.stdout.flush()

                    if completed % PREVIEW_EVERY == 0 or completed == len(frame_numbers):
                        last_preview_path = out_path
                        yield out_path, f"{stem}: {completed}/{len(frame_numbers)}"
                    else:
                        yield last_preview_path, f"{stem}: {completed}/{len(frame_numbers)}"
                except Exception as e:
                    print(f"⚠️ {e}")
        finally:
            if current_executor:
                current_executor.shutdown(wait=False, cancel_futures=True)
                current_executor = None
            print(f"\n✅ Done with {stem}")
    yield None, "✅ All videos done."

def extract_frame_by_number(video_path, fps, frame_num, output_dir, stem):
    ts = frame_num / fps
    fn = f"{stem}_{frame_num:08d}.png"
    out_path = Path(output_dir) / fn
    cmd = ['ffmpeg', '-y', '-threads', '1', '-ss', str(ts), '-i', str(video_path),
           '-frames:v', '1', str(out_path), '-loglevel', 'error']
    subprocess.run(cmd)
    return out_path.exists(), str(out_path), frame_num

def get_random_timestamps(dur, count):
    count = int(count)
    return sorted(random.sample([i / 1000 for i in range(1, int(dur * 1000))], count))

def set_stop_flag():
    global stop_flag, current_executor
    stop_flag = True
    if current_executor:
        current_executor.shutdown(wait=False, cancel_futures=True)
        current_executor = None
    return "🛑 Stopping..."

# Gradio UI
with gr.Blocks(css=".preview-frame img {object-fit: contain; max-width: 100%; max-height: 100%;}") as app:
    gr.Markdown("# 🎞️ Frame Extractor — Folder or Single Video")
    jobs = gr.Slider(label="CPU Threads", minimum=1, maximum=CPU_COUNT, step=1, value=min(8, CPU_COUNT))
    out = gr.Textbox(label="Output Folder", placeholder="C:/Frames")
    mode = gr.Radio(choices=["Folder", "Single Video"], label="Input Mode", value="Folder")
    folder = gr.Textbox(label="Video Folder", placeholder="C:/Videos")
    single = gr.File(file_count="single", type="filepath", visible=False, file_types=['.mp4', '.mov', '.mkv'], label="Single Video File")
    s, e = gr.Slider(label="Start Frame", minimum=1, maximum=1, step=1, value=1, visible=False), gr.Slider(label="End Frame", minimum=1, maximum=1, step=1, value=1, visible=False)
    with gr.Row(visible=False) as preview_row:
        p1 = gr.Image(type="filepath", label="Start Frame Preview")
        p2 = gr.Image(type="filepath", label="End Frame Preview")
    count = gr.Number(label="Total Random Frames", value=10, precision=0)
    all_chk = gr.Checkbox(label="Export ALL Frames", value=False)
    interval = gr.Number(label="Interval (Every Nth Frame)", value=1, precision=0, visible=False)
    run, stop, status = gr.Button("▶️ Start"), gr.Button("🛑 Stop"), gr.Textbox(label="Status", interactive=False)
    preview = gr.Image(type="filepath", label="Latest Frame", elem_classes="preview-frame", height=240)

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

    run.click(fn=extract_frames, inputs=[mode, folder, single, s, e, count, out, all_chk, jobs, interval], outputs=[preview, status], queue=True)
    stop.click(fn=set_stop_flag, outputs=[status])
    app.queue()

if __name__ == "__main__":
    app.launch(inbrowser=True)
