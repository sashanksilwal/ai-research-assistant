"""Burn on-screen labels into the narrated demo when a hard-to-hear term is spoken.

Times are positions in the narration take (as transcribed); they are mapped to video time with the
scene start times from timeline.json and the paragraph cut points used by record_demo.py.

    <python with imageio-ffmpeg> scripts/add_terms.py demo-out/demo-narrated.mp4 demo-out/timeline.json \
        --cuts 29.47,56.67,76.09,91.52,116.13,137.0,165.37,185.85 --out demo-final.mp4
"""
import argparse
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"  # has →, · and other symbols

# (seconds into the narration, seconds on screen, label). PyMuPDF is shown by record_demo.py itself.
TERMS = [
    (19.0, 2.5, "Claude Code"),
    (21.5, 7.0, "FastAPI · SQLite · arXiv API · Gemini"),
    (30.0, 3.5, "arXiv API"),
    (79.0, 6.0, "SQLite database"),
    (95.0, 4.5, "Self-Refine (Madaan et al., 2023)"),
    (120.0, 5.5, "Full paper text → Gemini (references removed)"),
    (170.0, 5.0, "Semantic Scholar · OpenAlex"),
    (190.0, 6.0, "github.com/sashanksilwal/ai-research-assistant"),
]


def to_video_time(t: float, cuts: list[float], timeline: list[dict]) -> float:
    """Narration time -> video time: same offset into the paragraph, measured from its scene's start."""
    bounds = [0.0, *cuts]
    paragraph = max(i for i, b in enumerate(bounds) if b <= t)
    return timeline[paragraph]["start"] + (t - bounds[paragraph])


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("timeline", type=Path)
    ap.add_argument("--cuts", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    cuts = [float(c) for c in args.cuts.split(",")]
    timeline = json.loads(args.timeline.read_text())

    filters = []
    for t, duration, label in TERMS:
        start = to_video_time(t, cuts, timeline)
        filters.append(
            f"drawtext=fontfile='{FONT}':text='{escape(label)}':fontsize=26:fontcolor=white"
            f":box=1:boxcolor=0x0969da@0.92:boxborderw=14:x=(w-text_w)/2:y=90"
            f":enable='between(t,{start:.2f},{start + duration:.2f})'"
        )
        print(f"{start:6.1f}s  {label}")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(args.video),
                    "-vf", ",".join(filters), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    "-c:a", "copy", str(args.out)], check=True)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
