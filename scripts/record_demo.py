"""Record the demo video by driving the app in Chromium with Playwright.

Scenes follow docs/demo-script.md; each one is held for at least its narration time so a voice-over
fits. Writes demo.mp4 plus timeline.json (scene start times, for lining up narration audio).

Run against a throwaway copy of the data so the demo's saves and uploads don't touch your library:
    DATA_DIR=/tmp/demo-data .venv/bin/uvicorn app.main:app --port 8001
    <python with playwright + imageio-ffmpeg> scripts/record_demo.py --url http://localhost:8001 --pdf self-refine.pdf

With a narration take read straight through, pass it with the pause times between paragraphs:
    ... --narration voice.m4a --cuts 29.5,56.7,76.1,91.5,116.1,137.0,165.4,185.9
Each scene is then held exactly as long as its paragraph, and each paragraph is placed at its scene's
actual start, so a slow Gemini response delays the next paragraph instead of desynchronizing the rest.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Page, sync_playwright

# Seconds each scene is held for (≈ narration length in docs/demo-script.md).
SCENES = {1: 15, 2: 20, 3: 15, 4: 15, 5: 25, 6: 30, 7: 40, 8: 25, 9: 10}
WIDTH, HEIGHT = 1280, 800

# A visible cursor (headless video has none) and a small caption pill naming the current step.
OVERLAY_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const cursor = document.createElement('div');
  cursor.id = 'demo-cursor';
  Object.assign(cursor.style, {position: 'fixed', width: '18px', height: '18px', borderRadius: '50%',
    background: 'rgba(9,105,218,0.35)', border: '2px solid #0969da', pointerEvents: 'none',
    zIndex: 99999, left: '-40px', top: '-40px', transform: 'translate(-50%,-50%)', transition: 'transform .1s'});
  const caption = document.createElement('div');
  caption.id = 'demo-caption';
  Object.assign(caption.style, {position: 'fixed', left: '16px', bottom: '16px', padding: '6px 12px',
    borderRadius: '14px', background: 'rgba(31,35,40,0.85)', color: '#fff', font: '14px system-ui',
    pointerEvents: 'none', zIndex: 99999, display: 'none'});
  document.body.append(cursor, caption);
  document.addEventListener('mousemove', e => { cursor.style.left = e.clientX + 'px'; cursor.style.top = e.clientY + 'px'; });
  document.addEventListener('mousedown', () => cursor.style.transform = 'translate(-50%,-50%) scale(0.7)');
  document.addEventListener('mouseup', () => cursor.style.transform = 'translate(-50%,-50%)');
});
"""


class Demo:
    def __init__(self, page: Page):
        self.page = page
        self.t0 = time.time()
        self.timeline = []
        self.scene_start = 0.0

    def note(self, text: str, after_s: float, for_s: float):
        """Show a term on screen (e.g. a library name that is hard to hear) without blocking the scene."""
        self.page.evaluate("""([text, after, dur]) => setTimeout(() => {
            const n = document.createElement('div');
            n.textContent = text;
            Object.assign(n.style, {position: 'fixed', top: '90px', left: '50%', transform: 'translateX(-50%)',
              padding: '10px 18px', borderRadius: '8px', background: 'rgba(9,105,218,0.92)', color: '#fff',
              font: '600 22px system-ui', zIndex: 99999, pointerEvents: 'none', boxShadow: '0 4px 14px rgba(0,0,0,.2)'});
            document.body.append(n);
            setTimeout(() => n.remove(), dur * 1000);
        }, after * 1000)""", [text, after_s, for_s])

    def scene(self, number: int, caption: str):
        self.hold()
        self.current = number
        self.scene_start = time.time()
        self.timeline.append({"scene": number, "caption": caption, "start": round(self.scene_start - self.t0, 2)})
        self.page.evaluate("c => { const el = document.getElementById('demo-caption'); el.textContent = c; el.style.display = 'block'; }", caption)
        print(f"scene {number}: {caption}", flush=True)

    def hold(self):
        """Wait until the current scene has lasted at least its narration time."""
        if self.timeline:
            remaining = SCENES[self.current] - (time.time() - self.scene_start)
            if remaining > 0:
                self.page.wait_for_timeout(remaining * 1000)

    def click(self, locator, pause=600):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=25)
        self.page.wait_for_timeout(300)
        locator.click()
        self.page.wait_for_timeout(pause)

    def type(self, locator, text):
        self.click(locator, pause=200)
        locator.press_sequentially(text, delay=55)
        self.page.wait_for_timeout(400)

    def scroll(self, dy, steps=12):
        for _ in range(steps):
            self.page.mouse.wheel(0, dy / steps)
            self.page.wait_for_timeout(60)


def media_duration(path: Path) -> float:
    """Seconds, from ffmpeg's "Duration: HH:MM:SS.xx" line."""
    info = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
    h, m, sec = info.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def add_narration(video: Path, narration: Path, cuts: list[float], timeline: list[dict], out: Path):
    """Cut the narration at `cuts` into one clip per scene and start each clip at its scene's start."""
    bounds = [0.0, *cuts, None]
    parts, labels = [], []
    for i, scene in enumerate(timeline):
        start, end = bounds[i], bounds[i + 1]
        trim = f"atrim=start={start}" + (f":end={end}" if end is not None else "")
        delay = int(scene["start"] * 1000)
        parts.append(f"[1:a]{trim},asetpts=PTS-STARTPTS,adelay={delay}:all=1[a{i}]")
        labels.append(f"[a{i}]")
    mix = f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[aout]"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(narration),
                    "-filter_complex", ";".join(parts + [mix]), "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(out)], check=True)


def run(url: str, pdf: Path, out_dir: Path, narration: Path | None = None, cuts: list[float] | None = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT},
                                      record_video_dir=str(out_dir), record_video_size={"width": WIDTH, "height": HEIGHT})
        context.add_init_script(OVERLAY_JS)
        page = context.new_page()
        demo = Demo(page)
        page.goto(url)
        page.wait_for_selector("#search-topics .topic-link")
        page.mouse.move(640, 300)

        demo.scene(1, "AI Research Assistant")

        demo.scene(2, "1. Search arXiv")
        demo.click(page.locator(".topic-link", has_text="automated program repair"))
        page.wait_for_selector("#search-results .card", timeout=60_000)
        page.wait_for_timeout(1500)
        demo.scroll(500)
        page.wait_for_timeout(1500)
        demo.scroll(-500)

        demo.scene(3, "2. Save to the library")
        demo.note("PyMuPDF — extracts the PDF's full text", after_s=6.0, for_s=7.0)
        save = page.locator("#search-results .card").first.get_by_role("button", name="Save to library")
        demo.click(save)
        page.locator("#search-results .card").first.get_by_role("button", name="Saved").wait_for(timeout=120_000)

        demo.scene(4, "Library (stored in SQLite)")
        demo.click(page.locator(".tab", has_text="Library"))
        page.wait_for_selector("#library-list .card")
        page.wait_for_timeout(1000)
        demo.scroll(700, steps=20)
        page.wait_for_timeout(1000)
        demo.scroll(-700, steps=20)

        demo.scene(5, "3. Upload a PDF")
        demo.click(page.locator("#upload-input"), pause=300)
        page.locator("#upload-input").set_input_files(str(pdf))
        page.wait_for_timeout(800)
        demo.click(page.locator("#upload-form button"))
        page.wait_for_function("document.getElementById('upload-status').textContent.startsWith('Added')", timeout=180_000)
        uploaded = page.locator("#library-list .card", has_text="Uploaded PDF").filter(has_text="Refine").first
        uploaded.scroll_into_view_if_needed()
        box = uploaded.bounding_box()
        page.mouse.move(box["x"] + 200, box["y"] + 40, steps=20)

        demo.scene(6, "4. Summarize with Gemini")
        demo.click(uploaded.get_by_role("button", name="Open"))
        summarize = page.get_by_role("button", name="Summarize with Gemini")
        summarize.wait_for()
        demo.click(summarize)
        page.get_by_role("button", name="Regenerate summary").wait_for(timeout=180_000)
        page.wait_for_timeout(1500)
        demo.scroll(450, steps=25)
        page.wait_for_timeout(2500)
        demo.scroll(450, steps=25)

        demo.scene(7, "5. Ask questions about the paper")
        answered = lambda n: page.wait_for_function(  # noqa: E731
            f"document.querySelectorAll('.qa-item').length >= {n} && !document.querySelector('.qa-history').textContent.includes('Thinking…')",
            timeout=180_000)
        def show_newest_answer():  # newest answer is first in the history; bring the form + answer into view
            page.locator(".qa-form").evaluate("el => el.scrollIntoView({block: 'start', behavior: 'smooth'})")
            page.wait_for_timeout(2500)
        demo.click(page.get_by_role("button", name="What datasets are used?"))
        answered(1)
        show_newest_answer()
        textarea = page.locator(".qa-form textarea")
        demo.type(textarea, "How does it compare with the baselines?")
        textarea.press("Enter")
        answered(2)
        show_newest_answer()
        demo.type(textarea, "Who won the 2022 FIFA World Cup?")
        textarea.press("Enter")
        answered(3)
        show_newest_answer()

        demo.scene(8, "Extra: citation graph")
        demo.click(page.locator(".tab", has_text="Library"))
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        demo.click(page.locator("#graph-toggle"))
        page.wait_for_function("graph && graph.nodes.length > 0", timeout=180_000)
        page.locator("#graph").evaluate("el => el.scrollIntoView({block: 'center', behavior: 'smooth'})")
        page.wait_for_timeout(5000)  # let the layout settle and fit
        # Hover the most-linked paper: map its canvas position to page coordinates.
        hub = page.evaluate("""() => {
            const top = graph.nodes.get().sort((a, b) => b.degree - a.degree)[0];
            const pos = graph.network.canvasToDOM(graph.network.getPositions([top.id])[top.id]);
            const rect = document.getElementById('graph').getBoundingClientRect();
            return {x: rect.left + pos.x, y: rect.top + pos.y};
        }""")
        page.mouse.move(hub["x"], hub["y"], steps=30)
        page.wait_for_timeout(4000)
        page.mouse.move(hub["x"] + 260, hub["y"] - 150, steps=20)
        page.locator("#graph-labels").select_option("10")
        page.wait_for_timeout(1500)

        demo.scene(9, "Search · Save · Upload · Summarize · Ask")
        demo.click(page.locator(".tab", has_text="Search"))
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        demo.hold()

        video = Path(page.video.path())
        context.close()
        browser.close()

    mp4 = out_dir / "demo.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(mp4)], check=True)
    (out_dir / "timeline.json").write_text(json.dumps(demo.timeline, indent=2))
    print(f"wrote {mp4} and timeline.json")
    if narration:
        final = out_dir / "demo-narrated.mp4"
        add_narration(mp4, narration, cuts, demo.timeline, final)
        print(f"wrote {final}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("demo-out"))
    ap.add_argument("--narration", type=Path, help="one narration take, read straight through")
    ap.add_argument("--cuts", help="comma-separated pause times (s) between the 9 paragraphs")
    args = ap.parse_args()
    cuts = [float(c) for c in args.cuts.split(",")] if args.cuts else None
    if args.narration:
        if not cuts or len(cuts) != len(SCENES) - 1:
            ap.error(f"--narration needs --cuts with {len(SCENES) - 1} times")
        # Hold each scene exactly as long as its paragraph of narration.
        total = media_duration(args.narration)
        bounds = [0.0, *cuts, total]
        SCENES.update({n: bounds[n] - bounds[n - 1] for n in SCENES})
        print("scene lengths:", {n: round(v, 1) for n, v in SCENES.items()})
    run(args.url, args.pdf, args.out, args.narration, cuts)
