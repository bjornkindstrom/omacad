#!/usr/bin/env python3
"""Makes a guide picture small enough to live in the repo: crop (optional), scale to at most MAX_W px wide, JPEG.

    .venv/bin/python tools/guide_image.py SRC.png omacad/guides/<guide>/1.jpg [--crop x,y,w,h]

The budget (MAX_W, QUALITY, MAX_BYTES) is enforced for every guide by tests/test_guides.py.
"""
import argparse
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage

MAX_W = 900          # a guide window is ~520 px wide: 900 stays sharp on a high-DPI screen
QUALITY = 78
MAX_BYTES = 120_000  # per picture


def shrink(src: QImage, dst: str) -> int:
    img = src.scaledToWidth(MAX_W, Qt.TransformationMode.SmoothTransformation) if src.width() > MAX_W else src
    quality = QUALITY
    while True:
        img.save(dst, "JPG", quality)
        size = __import__("os").path.getsize(dst)
        if size <= MAX_BYTES or quality <= 40:
            return size
        quality -= 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--crop", default="")
    args = ap.parse_args()
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    img = QImage(args.src)
    if img.isNull():
        sys.exit(f"cannot read {args.src}")
    if args.crop:
        img = img.copy(*[int(v) for v in args.crop.split(",")])
    print(args.dst, shrink(img, args.dst), "bytes")


if __name__ == "__main__":
    main()
