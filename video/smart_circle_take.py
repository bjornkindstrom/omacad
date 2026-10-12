#!/usr/bin/env python3
"""Frame-exact demo of the Smart Circle tool: type a diameter, then the distance to the nearest
vertical and horizontal line, Enter after each. Two circles are placed in a 60 x 40 mm plate.

    .venv/bin/python video/smart_circle_take.py                 # -> video/smart_circle/smart_circle.mp4
    .venv/bin/python video/smart_circle_take.py --out ~/Videos/omacad-smart-circle.mp4

Same approach as pan_take.py: every frame is rendered with grabFramebuffer(), no screen recorder, so the
result is identical on every run. The cursor and the captions are drawn onto the frames here (the real
cursor is not captured). Real display (Wayland) needed, the viewport needs a GL context.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPolygonF, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow

W, H, FPS = 1280, 720, 30
PLATE = (60.0, 40.0)
OUTDIR = os.path.join(ROOT, "video", "smart_circle")


class Take:
    def __init__(self, app, win):
        self.app, self.win, self.vp = app, win, win.viewport
        self.frame, self.caption, self.cursor = 0, "", QPointF(W * 0.62, H * 0.75)
        shutil.rmtree(OUTDIR, ignore_errors=True)
        os.makedirs(OUTDIR)

    # --- rendering ---
    def shoot(self, n: int = 1):
        for _ in range(n):
            for _ in range(3):
                self.app.processEvents()
            img = self.vp.grabFramebuffer()
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if self.caption:
                f = QFont("sans", 20)
                p.setFont(f)
                w = p.fontMetrics().horizontalAdvance(self.caption) + 48
                p.setBrush(QColor(0, 0, 0, 175))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect((W - w) // 2, H - 140, w, 54, 10, 10)
                p.setPen(QColor("white"))
                p.drawText((W - w) // 2, H - 140, w, 54, Qt.AlignmentFlag.AlignCenter, self.caption)
            c = self.cursor     # arrow cursor
            p.setBrush(QColor("white"))
            p.setPen(QColor("black"))
            p.drawPolygon(QPolygonF([c, c + QPointF(0, 19), c + QPointF(5, 15), c + QPointF(9, 24), c + QPointF(12, 22.5),
                                     c + QPointF(8, 14), c + QPointF(14, 14)]))
            p.end()
            img.save(os.path.join(OUTDIR, f"f{self.frame:05d}.png"))
            self.frame += 1

    def say(self, text):
        self.caption = text

    # --- input, through the viewport's own event handlers ---
    def uv_to_px(self, uv):
        plane = self.vp.doc.active_sketch.plane
        return self.vp.world_to_screen(plane.uv_to_world(uv[0], uv[1]))

    def move_event(self, px):
        self.cursor = QPointF(*px)
        pt = QPointF(*px)
        self.vp.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, pt, pt, Qt.MouseButton.NoButton,
                                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    def glide(self, uv, frames=24):
        a, b = np.array([self.cursor.x(), self.cursor.y()]), np.array(self.uv_to_px(uv))
        for i in range(1, frames + 1):
            t = i / frames
            t = t * t * (3 - 2 * t)
            self.move_event(a + (b - a) * t)
            self.shoot()

    def key(self, k, text=""):
        self.vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier, text))

    def type_number(self, s, per_key=5):
        for ch in s:
            self.key(Qt.Key.Key_Period if ch == "." else getattr(Qt.Key, f"Key_{ch}"), ch)
            self.shoot(per_key)

    def enter(self, hold=18):
        self.key(Qt.Key.Key_Return)
        self.shoot(hold)

    def circle(self, d, across_uv, across, down_uv, down):
        self.say(f"Type the diameter: {d} mm, Enter")
        self.shoot(8)
        self.type_number(d)
        self.shoot(10)
        self.enter()
        self.say("Move next to a vertical line, type the distance, Enter")
        self.glide(across_uv)
        self.shoot(10)
        self.type_number(across)
        self.shoot(10)
        self.enter()
        self.say("Same to a horizontal line")
        self.glide(down_uv)
        self.shoot(10)
        self.type_number(down)
        self.shoot(10)
        self.enter(26)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "smart_circle.mp4"))
    args = ap.parse_args()
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1600, 900)
    win.show()
    win.viewport.setFixedSize(W, H)
    win.viewport.show_grid = True

    def run():
        t = Take(app, win)
        vp, doc = win.viewport, win.doc
        sk = doc.start_sketch("XY")
        before = sk.to_dict()
        sk.add_rect((0.0, 0.0), PLATE)
        doc.record_sketch_change(sk, before)
        vp.align_to_plane(sk.plane)
        vp.target = np.array([PLATE[0] / 2, PLATE[1] / 2, 0.0], dtype=np.float32)
        vp.distance = 80.0
        vp.update()
        t.shoot(20)
        t.say("Smart Circle: place a circle with numbers")
        t.shoot(30)
        vp.set_sketch_tool("SMART_CIRCLE")
        vp.setFocus()
        t.move_event(t.uv_to_px((44.0, 14.0)))
        t.shoot(20)
        t.circle("8", (50.0, 20.0), "10", (40.0, 36.0), "6")        # right wall 10 mm, top wall 6 mm
        t.say("The circle keeps its dimensions: change one and it follows")
        t.glide((24.0, 12.0))
        t.shoot(20)
        t.circle("6", (3.0, 20.0), "12", (20.0, 3.0), "9")          # left wall 12 mm, bottom wall 9 mm
        vp.set_sketch_tool("NONE")
        t.say("Done: every circle is fully dimensioned")
        t.shoot(60)
        # finish the sketch and cut the plate so the result shows
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, 8.0)
        vp.set_view("HOME")
        vp.zoom_fit()
        t.say("Extrude: the circles become holes")
        for i in range(75):
            vp.azimuth += 1.6
            vp.update()
            t.cursor = QPointF(-50, -50)
            t.shoot()
        t.shoot(15)
        out = os.path.abspath(os.path.expanduser(args.out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(OUTDIR, "f%05d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", out], check=True)
        print("Saved", out)
        app.quit()

    from PySide6.QtCore import QTimer
    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
