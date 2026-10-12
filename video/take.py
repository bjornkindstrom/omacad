"""Shared frame-exact capture helper for the video takes: renders the viewport frame by frame (no screen
recorder), draws cursor and captions on the frames and drives the viewport through its own event handlers."""
import os
import shutil
import subprocess

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPolygonF

W, H, FPS = 1280, 720, 30


class Take:
    def __init__(self, app, win, outdir):
        self.outdir = outdir
        self.marks = []
        self.app, self.win, self.vp = app, win, win.viewport
        self.frame, self.caption, self.cursor = 0, "", QPointF(W * 0.62, H * 0.75)
        shutil.rmtree(outdir, ignore_errors=True)
        os.makedirs(outdir)

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
            img.save(os.path.join(self.outdir, f"f{self.frame:05d}.png"))
            self.frame += 1

    def say(self, text):
        self.caption = text
        self.marks.append({"frame": self.frame, "text": text})   # scene starts, used by narrate.py

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

    def press(self, uv):
        pt = QPointF(*self.uv_to_px(uv))
        for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            fn = self.vp.mousePressEvent if t == QEvent.Type.MouseButtonPress else self.vp.mouseReleaseEvent
            fn(QMouseEvent(t, pt, pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton if t == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.shoot(6)

    def fly(self, target, distance, az, el, frames=45):
        """Smooth camera move to a new target/distance/azimuth/elevation."""
        vp = self.vp
        a0 = (np.array(vp.target, dtype=float), vp.distance, vp.azimuth, vp.elevation)
        for i in range(1, frames + 1):
            k = i / frames
            k = k * k * (3 - 2 * k)
            vp.target = np.array(a0[0] + (np.asarray(target, dtype=float) - a0[0]) * k, dtype=np.float32)
            vp.distance = a0[1] + (distance - a0[1]) * k
            vp.azimuth = a0[2] + (az - a0[2]) * k
            vp.elevation = a0[3] + (el - a0[3]) * k
            vp.update()
            self.cursor = QPointF(-50, -50)
            self.shoot()

    def encode(self, out):
        out = os.path.abspath(os.path.expanduser(out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(self.outdir, "f%05d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", out], check=True)
        import json
        json.dump({"fps": FPS, "frames": self.frame, "marks": self.marks}, open(os.path.join(self.outdir, "marks.json"), "w"), indent=1)
        print("Saved", out)

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
