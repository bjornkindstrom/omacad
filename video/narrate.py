#!/usr/bin/env python3
"""Add a local text-to-speech narration to a take: one sentence per scene, spoken by ComfyUI (tts.py), each
placed at the frame where its scene starts (video/<take>/marks.json written by take.py) and mixed onto the video.

    .venv/bin/python video/narrate.py video/plate/marks.json ~/Videos/omacad-plate-holes.mp4 ~/Videos/omacad-plate-holes-narrated.mp4 --lines video/lines_plate.json

`--lines` is a JSON list with one narration sentence per mark, in order (null = silent). A sentence that is
longer than its scene is not cut: the next sentence just starts after it. Audio is cached per text+voice+seed
under video/audio/, so only changed sentences are generated again.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts

AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("marks")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--lines", required=True)
    ap.add_argument("--voice", default=tts.NARRATOR)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    marks = json.load(open(a.marks))
    lines = json.load(open(a.lines))
    assert len(lines) == len(marks["marks"]), f"{len(lines)} lines but {len(marks['marks'])} marks"
    os.makedirs(AUDIO, exist_ok=True)
    clips, cursor = [], 0.0
    for m, line in zip(marks["marks"], lines):
        if not line:
            continue
        key = hashlib.sha1(f"clone2|{line}|{a.voice}|{a.seed}".encode()).hexdigest()[:12]
        path = os.path.join(AUDIO, f"{key}.flac")
        if not os.path.exists(path):
            print("TTS:", line)
            tts.synthesize(line, path, a.voice, a.seed)
        start = max(m["frame"] / marks["fps"], cursor)      # never overlap the previous sentence
        clips.append((path, start))
        cursor = start + duration(path) + 0.25
    vdur = marks["frames"] / marks["fps"]
    if cursor > vdur:
        print(f"Warning: narration runs {cursor - vdur:.1f} s past the end of the video and is cut: lengthen the last scene")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", a.video]
    for p, _ in clips:
        cmd += ["-i", p]
    filt = "".join(f"[{i + 1}:a]adelay={int(st * 1000)}|{int(st * 1000)}[a{i}];" for i, (_, st) in enumerate(clips))
    filt += "".join(f"[a{i}]" for i in range(len(clips))) + f"amix=inputs={len(clips)}:normalize=0,loudnorm=I=-16:TP=-1.5,apad[aout]"
    cmd += ["-filter_complex", filt, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{vdur:.3f}", os.path.abspath(os.path.expanduser(a.out))]
    subprocess.run(cmd, check=True)
    print("Saved", a.out)


if __name__ == "__main__":
    main()
