#!/usr/bin/env python3
"""The two-minute feature tour: narrated, with background music. Films the whole window (ribbon, tree, timeline).

    .venv/bin/python video/tour_take.py --out ~/Videos/omacad-tour-silent.mp4
    .venv/bin/python video/music.py video/audio/music.flac --seconds 130
    .venv/bin/python video/narrate.py video/tour/marks.json ~/Videos/omacad-tour-silent.mp4 ~/Videos/omacad-tour.mp4 --music video/audio/music.flac

The sentences in SCENES are spoken first (ComfyUI must be running), so every scene lasts as long as its sentence.
Real display needed; the window goes fullscreen while it renders (10-20 minutes). Your Omarchy theme is never
changed (the theme scene only swaps the app's own colours).
"""
import argparse
import math
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication

import narrate
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui import theme
from omacad.ui.main_window import MainWindow
from take import Take
from theme_take import build_part

OUTDIR = os.path.join(ROOT, "video", "tour")
THEMES = ["tokyo-night", "catppuccin-latte", "gruvbox", "osaka-jade", "rose-pine", "nord"]
TOP = SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, 8.0]))
PLATE_C = (30.0, 20.0, 4.0)

# Spoken text: names are respelled so the voice says them right (Omacad, CAD, Omarchy).
LINES = {
    "intro": "This is Oh-mah-cad: a native, parametric 3D C A D for Oh-mar-key Linux. Here is a quick tour.",
    "sketch": "Everything starts with a sketch. Pick the rounded rectangle, then just type the width, the height and the corner radius.",
    "smart": "Smart Circle places a hole with numbers. Type the diameter, then the distance to a wall in each direction. Every number becomes a dimension, so the sketch stays fully defined.",
    "extrude": "Extrude the sketch, and the circle becomes a hole. Drag the arrow or type the distance, and Auto mode decides whether to add or cut.",
    "chamfer": "Round or bevel edges with fillet and chamfer. It works on straight edges, circles and whole outlines.",
    "mirror": "Copy the hole with its chamfer to all four corners, with a single Mirror step.",
    "fill": "Fill pattern covers a whole face. Draw one polygon, and Oh-mah-cad packs the surface with exact gaps, steering around anything that stands on it.",
    "polygons": "It works for any polygon from three to eight sides, and everything is parametric. Change the sketch, and the pattern packs itself again.",
    "revolve": "Revolve turns a profile into a turned part, around any axis you choose.",
    "section": "Section View lets you slide a plane through the model, to look inside.",
    "undo": "Undo and redo cover every single step, so nothing you try can be lost.",
    "theme": "Oh-mah-cad follows your Oh-mar-key theme live: colours, fonts, everything.",
    "report": "Found a bug? Press F9. Oh-mah-cad sends a screenshot and your model to an AI agent that fixes it, and restarts with your work intact.",
    "end": "Oh-mah-cad is open source and free. Thanks for watching.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "tour_silent.mp4"))
    args = ap.parse_args()
    # speak every sentence first, so the scenes can be as long as the speech
    durations = {}
    for k, line in LINES.items():
        durations[line] = narrate.clip(line)[1]
    print("narration seconds:", round(sum(durations.values()), 1), flush=True)

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()

    def run():
        try:
            _run()
        except Exception:
            import traceback
            traceback.print_exc()
            app.quit()

    def _run():
        for _ in range(10):
            app.processEvents()
        theme.COLORS_FILE_ORIGINAL = theme.COLORS_FILE
        t = Take(app, win, OUTDIR, window=True)
        t.durations = durations
        L = LINES

        def vp():
            return win.viewport

        def doc():
            return win.doc

        def cam(target, dist, az, el):
            v = vp()
            v.target, v.distance, v.azimuth, v.elevation = np.array(target, dtype=np.float32), dist, az, el
            v.update()

        def orbit(frames, degrees, bob=0.0):
            v = vp()
            a0, e0 = v.azimuth, v.elevation
            for i in range(1, frames + 1):
                k = i / frames
                v.azimuth = a0 + degrees * k
                v.elevation = e0 + bob * math.sin(math.pi * 2 * k)
                v.update()
                t.cursor = QPointF(-50, -50)
                t.shoot()

        def fresh():
            win.attach_document(Document(), None)
            win.doc.auto_include_edges = False
            for _ in range(5):
                app.processEvents()

        # ---- 1. intro: a finished part turning ----
        fresh()
        build_part(doc())
        cam((40.0, 25.0, 4.0), 125.0, 25.0, 30.0)
        t.shoot(10)
        t.scene("Omacad: parametric CAD for Omarchy", L["intro"], lambda: orbit(int(5.5 * 30), 170, 6))

        # ---- 2. sketch ----
        fresh()
        d, v = doc(), vp()
        sk = d.start_sketch("XY")
        v.align_to_plane(sk.plane)
        cam((30.0, 20.0, 0.0), 72.0, 0.0, 89.9)
        t.cursor = QPointF(120, 400)
        t.shoot(8)

        def sketch_scene():
            v.set_sketch_tool("ROUNDED_RECT")
            v.setFocus()
            t.move_event(t.uv_to_px((-8.0, -6.0)))
            t.shoot(10)
            t.glide((0.0, 0.0), 20)
            t.press((0.0, 0.0))
            t.glide((40.0, 25.0), 25)
            for s in ("60", "40", "8"):
                t.type_number(s)
                t.shoot(8)
                t.enter(12)
            t.shoot(20)

        t.scene("Sketch: rounded rectangle", L["sketch"], sketch_scene)

        # ---- 3. smart circle ----
        def smart_scene():
            v.set_sketch_tool("SMART_CIRCLE")
            v.setFocus()
            t.glide((14.0, 14.0), 24)
            t.circle("6", (3.0, 12.0), "8", (12.0, 3.0), "8")
            v.set_sketch_tool("NONE")
            t.shoot(20)

        t.scene("Smart Circle: numbers and Enter", L["smart"], smart_scene)

        # ---- 4. extrude ----
        def extrude_scene():
            d.finish_sketch()
            d.extrude_profile(sk.sketch_id, 0, 8.0)
            t.fly(PLATE_C, 80.0, 30.0, 45.0, 60)
            t.fly((8.0, 8.0, 8.0), 38.0, 35.0, 48.0, 40)

        t.scene("Extrude", L["extrude"], extrude_scene)

        # ---- 5. chamfer ----
        ch_holder = {}

        def chamfer_scene():
            body = next(iter(d.bodies.values()))
            edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.2]
            ch_holder["f"] = d.add_fillet(edges, 1.0, "chamfer")
            t.fly((8.0, 8.0, 8.0), 24.0, 40.0, 50.0, 40)

        t.scene("Fillet and Chamfer", L["chamfer"], chamfer_scene)

        # ---- 6. mirror ----
        def mirror_scene():
            ext = [f for f in d.timeline.features if f.feature_type == "extrude"][0]
            d.add_pattern([ext.feature_id, ch_holder["f"].feature_id], "mirror", mirror_mode="xy")
            t.fly(PLATE_C, 85.0, 30.0, 45.0, 45)

        t.scene("Mirror and Pattern", L["mirror"], mirror_scene)

        # ---- 7. cylinder + polygon fill ----
        hex_holder = {}

        def fill_scene():
            cs = d.start_sketch_on_plane(TOP)
            cs.add_circle((40.0, 20.0), 5.0)
            d.finish_sketch()
            d.extrude_profile(cs.sketch_id, 0, 12.0, "join")
            t.fly(PLATE_C, 85.0, 215.0, 45.0, 30)
            hs = d.start_sketch_on_plane(TOP)
            hs.add_polygon((16.0, 30.0), (19.0, 30.0), 6)
            d.finish_sketch()
            d.extrude_profile(hs.sketch_id, 0, -9.0, "cut")
            hex_holder["sk"] = hs.sketch_id
            hexcut = [f for f in d.timeline.features if f.feature_type == "extrude"][-1]
            d.add_pattern([hexcut.feature_id], "fill", spacing1=1.5, spacing2=3.0, count1=0.0, mirror_mode="stagger")
            t.fly(PLATE_C, 80.0, 235.0, 55.0, 40)
            orbit(60, 55, 0)

        t.scene("Fill pattern", L["fill"], fill_scene)

        # ---- 8. polygons: pentagon, triangle ----
        def polygon_scene():
            for sides in (5, 3, 8):
                s1 = d.edit_sketch(hex_holder["sk"])
                before = s1.to_dict()
                s1.delete_entities([e.entity_id for e in s1.entities])
                s1.add_polygon((16.0, 30.0), (19.0, 30.0), sides)
                d.record_sketch_change(s1, before)
                d.finish_sketch()
                t.shoot(8)
                orbit(60, 40, 0)

        t.scene("Any polygon, 3 to 8 sides", L["polygons"], polygon_scene)

        # ---- 9. revolve ----
        fresh()
        d, v = doc(), vp()

        def revolve_scene():
            rs = d.start_sketch("XZ")
            pts = [(0, 0), (22, 0), (22, 6), (14, 26), (17, 44), (0, 44)]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                rs.add_line(a, b)
            v.align_to_plane(rs.plane)
            cam((10.0, 0.0, 22.0), 110.0, v.azimuth, v.elevation)
            t.shoot(30)
            d.finish_sketch()
            d.add_revolve(rs.sketch_id, 0, ("v",), 360.0, "new_body")
            t.fly((0.0, 0.0, 22.0), 120.0, 30.0, 25.0, 45)
            orbit(60, 70, 4)

        t.scene("Revolve", L["revolve"], revolve_scene)

        # ---- 10. section view ----
        def section_scene():
            sid = d.add_section((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -24.0)
            t.fly((0.0, 0.0, 22.0), 120.0, 20.0, 18.0, 25)
            n = 150
            for i in range(n + 1):
                k = i / n
                d.sections[sid]["offset"] = -24.0 + 48.0 * (0.5 - 0.5 * math.cos(math.pi * k))
                d.notify_changed()
                v.azimuth = 20.0 + 25.0 * math.sin(math.pi * k)
                v.update()
                t.shoot()

        t.scene("Section View", L["section"], section_scene)

        # ---- 11. undo / redo ----
        def undo_scene():
            t.fly((0.0, 0.0, 22.0), 120.0, 30.0, 25.0, 15)
            for _ in range(3):
                d.undo()
                t.shoot(24)
            for _ in range(3):
                d.redo()
                t.shoot(24)

        t.scene("Undo and Redo", L["undo"], undo_scene)

        # ---- 12. theme ----
        def theme_scene():
            n, hold, fade = int(durations[L["theme"]] * 30) + 20, 40, 8
            for i in range(n):
                v.azimuth += 1.6
                v.elevation = 25.0 + 6.0 * math.sin(i / 20.0)
                v.update()
                k, f = divmod(i, hold)
                cur, nxt = THEMES[k % len(THEMES)], THEMES[(k + 1) % len(THEMES)]
                set_theme(cur)
                img = t._grab()
                if f >= hold - fade:
                    a = (f - (hold - fade) + 1) / (fade + 1)
                    set_theme(nxt)
                    other = t._grab()
                    p = QPainter(img)
                    p.setOpacity(a * a * (3 - 2 * a))
                    p.drawImage(0, 0, other)
                    p.end()
                t.cursor = QPointF(-50, -50)
                t._finish(img)
            set_theme(THEMES[0])

        shown = {"n": None}

        def set_theme(name):
            if shown["n"] != name:
                theme.COLORS_FILE = Path("/usr/share/omarchy/themes") / name / "colors.toml"
                theme.refresh()
                for _ in range(4):
                    app.processEvents()
                shown["n"] = name

        try:
            t.scene("Follows your Omarchy theme", L["theme"], theme_scene)
        finally:
            theme.COLORS_FILE = theme.COLORS_FILE_ORIGINAL
            theme.refresh()

        # ---- 13. report, end ----
        t.scene("F9: report a problem to your AI agent", L["report"], lambda: orbit(int(durations[L["report"]] * 30), 120, 4))
        t.scene("Omacad: open source and free", L["end"], lambda: orbit(int(durations[L["end"]] * 30) + 30, 60, 3))
        t.shoot(30)
        t.encode_scaled(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
