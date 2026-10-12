# Intro video: status and handover

Everything here was written in a cloud session **without a screen or PySide6**, so nothing has been run yet. Fix it up on the real machine (Wayland).

## Files
- `SCRIPT.md`: scene table (time, on screen, narration), recording prep, YouTube title/description/thumbnail ideas.
- `record_demo.py`: drives the real `MainWindow` through the scenes with captions. `--record` starts `wf-recorder` (-> `omacad_demo.mp4`), `--speed 1.5` for rehearsal.
- `comfyui_prompts.md`: image prompts for the title card, end card, thumbnail and b-roll.

## Demo flow (scene functions in `record_demo.py`)
1. `s1_title` caption + home view
2. `s2_sketch` centre rounded rect (60 x 40 mm, r 6) on XY
3. `s3_extrude` finish sketch, extrude 10 mm, orbit
4. `s4_hole` one hole (r 2.5) near a corner, `s4b_mirror` Mirror (`mirror_mode="xy"`) to all four corners, `s4c_fill` hexagon cut + Fill pattern (gap 1.5, margin 4, `stagger`)
5. `s4d_edit` edit the first sketch (80 x 40, r 10), Finish Sketch, everything rebuilds
6. `s5_section` Section View, `s6_undo`/`s6b_redo`, `s8_end`

## Known issues / to check on the machine
- Never run. Expect API mistakes in `record_demo.py`; run with `--speed 3` first.
- Fill pattern parameters (`spacing1/2`, `mirror_mode="stagger"`) are guessed from `timeline.py`; compare with the Pattern dialog.
- `s4d_edit`: the hole sketches do not move, so after widening the plate the holes are no longer at the corners. Either edit the hole sketch too or choose a smaller change.
- Holes and hexagon are sketched on the XY plane, not on a face; `SCRIPT.md` scene 4 mentions sketching on a face. Consider a real face sketch (`start_sketch_on_plane(SketchPlane.centered_on(...))`).
- Fillet scene (5 in the table) is not automated; `add_fillet` needs edge refs.
- F9 scene is manual (starts the real agent).
- Turn off `auto_restart` before recording, or a commit restarts the app mid-take.
- Window must be 1920x1080 (`hyprctl dispatch resizeactive exact 1920 1080`).
- Caption bar is a plain QLabel; restyle to the theme if wanted.

## Next steps
1. Run, fix, tune the hold times in `SCENES`.
2. Record with `--record`, record the voice-over after the finished picture.
3. Generate images with `comfyui_prompts.md`, cut together, upload.
