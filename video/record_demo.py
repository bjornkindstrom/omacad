#!/usr/bin/env python3
"""Plays the intro-video demo in the real Omacad window (see SCRIPT.md).

Run on the real display (Wayland), not offscreen: the viewport needs a GL context.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication, QLabel

from omacad.ui.main_window import MainWindow


class Demo:
    def __init__(self, win: MainWindow, speed: float, on_done):
        self.win, self.doc, self.vp = win, win.doc, win.viewport
        self.speed, self.on_done = speed, on_done
        self.caption = QLabel(win)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet("background: rgba(0,0,0,170); color: white; font-size: 26px; padding: 12px 24px; border-radius: 10px;")
        self.caption.hide()
        self.spin = None

    def say(self, text: str):
        self.caption.setText(text)
        self.caption.adjustSize()
        self.caption.move((self.win.width() - self.caption.width()) // 2, self.win.height() - self.caption.height() - 40)
        self.caption.show()
        self.caption.raise_()

    # --- scenes: each returns after changing the document; SCENES lists (seconds to hold, function) ---
    def s1_title(self):
        self.say("Omacad: native parametric CAD for Omarchy")
        self.vp.set_view("HOME")

    def s2_sketch(self):
        self.say("Sketch on a plane. Rounded corners built in.")
        self.sk = self.doc.start_sketch("XY")
        self.vp.align_to_plane(self.sk.plane)
        before = self.sk.to_dict()
        self.sk.add_center_rounded_rect((0.0, 0.0), (30.0, 20.0), 6.0)
        self.doc.record_sketch_change(self.sk, before)
        self.doc.notify_changed()

    def s3_extrude(self):
        self.say("Finish the sketch and extrude. Every step is in the timeline.")
        self.doc.finish_sketch()
        self.doc.extrude_profile(self.sk.sketch_id, 0, 20.0)
        self.vp.set_view("HOME")
        self.vp.zoom_fit()
        self.spin = QTimer(self.win)
        self.spin.timeout.connect(self._orbit)
        self.spin.start(33)

    def _orbit(self):
        self.vp.azimuth += 1.2
        self.vp.update()

    def s4_hole(self):
        self.say("Sketch on a face, cut a hole.")
        self.spin.stop()
        self.vp.set_view("HOME")
        sk = self.doc.start_sketch("XY")
        before = sk.to_dict()
        sk.add_circle((0.0, 0.0), 7.0)
        self.doc.record_sketch_change(sk, before)
        self.doc.finish_sketch()
        self.doc.extrude_profile(sk.sketch_id, 0, 20.0, operation="cut")

    def s5_section(self):
        self.say("Section View: look inside the part.")
        self.sec = self.doc.add_section((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 0.0)
        self.vp.update()

    def s6_undo(self):
        self.say("Undo and redo cover everything.")
        for _ in range(3):
            self.doc.undo()
        self.vp.update()

    def s6b_redo(self):
        for _ in range(3):
            self.doc.redo()
        self.vp.set_view("HOME")

    def s8_end(self):
        self.say("Omacad: open source and free. Link in the description.")
        self.vp.set_view("HOME")

    SCENES = [
        (8, "s1_title"), (12, "s2_sketch"), (12, "s3_extrude"), (14, "s4_hole"),
        (12, "s5_section"), (5, "s6_undo"), (5, "s6b_redo"), (8, "s8_end"),
    ]

    def run(self, i: int = 0):
        if i >= len(self.SCENES):
            self.on_done()
            return
        hold, name = self.SCENES[i]
        getattr(self, name)()
        QTimer.singleShot(int(hold * 1000 / self.speed), lambda: self.run(i + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="run wf-recorder alongside (video/omacad_demo.mp4)")
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1920, 1080)
    win.show()

    rec = None
    out = os.path.join(ROOT, "video", "omacad_demo.mp4")

    def finish():
        if rec:
            rec.terminate()
            rec.wait()
            print(f"Saved {out}")
        app.quit()

    def start():
        nonlocal rec
        if args.record:
            if not shutil.which("wf-recorder"):
                sys.exit("wf-recorder not found: install it or record with OBS")
            rec = subprocess.Popen(["wf-recorder", "-f", out, "-y"])
        Demo(win, args.speed, finish).run()

    QTimer.singleShot(2000, start)   # let the GL context come up first
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
