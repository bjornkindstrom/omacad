# Changelog

Versions: 0.x while the feature set is still growing, 1.0 when Omacad is a complete and dependable CAD.
The version lives in `omacad/__init__.py`; every build is published as release `v<version>` (and as `latest`).

## 0.6.1 - 2026-10-11

### Added
- **Report problem (F9, Help menu, status bar)**: describe what is wrong; the app takes a screenshot (before any dialog opens), saves it with the whole document, the camera, the undo history and the log in `~/.local/share/omacad/feedback/<time>/`, and starts Omarchy's default coding agent on it (`omarchy agent prompt`) to reproduce, fix, test and commit. The log (status messages, printed output, errors) is recorded by `omacad/applog.py`.
- `omacad.md` (+ `AGENTS.md`, `CLAUDE.md`): the memory of the AI agents: architecture, rules, how to test, and a log of solved problems.

### Fixed
- **Sketch Offset with arcs**: lines and arcs are offset as whole chains. Arcs keep their centre and change radius (r - d inward, r + d outward), every joint is remade, so a rounded rectangle gives a rounded rectangle with no broken lines; an inward offset larger than the radius drops the arcs and closes the chain with sharp corners.

## 0.6.0 - 2026-10-11 (Trygghet)

### Added
- **Global undo / redo (Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y) for everything**: every step that changes the document (primitives, extrude, revolve, fillet/chamfer, shell, hole, pattern, move, split, import, parameter changes, timeline edits, rename/suppress/delete, offset planes, section views, canvases, deleting bodies, starting and finishing sketches) is one undo step. Edits inside a sketch still undo one at a time. *Finish Sketch* can be undone and takes you back into the sketch. The Edit menu shows what will be undone ("Undo Extrude"); undo waits while a tool panel is open or something is being dragged.
- Test suite (`tests/`, pytest): exact-volume checks for fillet/chamfer (irregular outlines, circles, edited history, rounded block foot), shell, revolve, hole, mirror, trim/offset/mirror in sketches, face edges, undo/redo of every step type and file round trips. CI runs it before the Windows build; a failing test stops the release.

### Fixed
- **Delete body** is now a real step in the history (it used to come back at the next rebuild) and can be undone.

## 0.5.2 - 2026-10-11

### Fixed
- Fillet/Chamfer at the **foot of a block with rounded vertical corners** (a wall rising from a flat face): only the straight pieces were filled and the corner arc was left out, giving a gap. The whole foot outline (straight pieces + corner arcs) is now one pickable edge that is filled in one go, for both Fillet and Chamfer. (Inner outlines were only recognised for outer rims before.)

## 0.5.1 - 2026-10-11

### Added
- **Box selection in sketches**: drag a box on empty space (left to right = only what is fully inside, blue; right to left = everything it touches, green). With **Fillet** the box picks all corners inside it (then Enter = one radius), with **Offset** it picks the chains it touches. Ctrl+drag adds to the selection. **Alt+drag orbits** in sketch mode.

## 0.5.0 - 2026-10-11 (Fusion 360 parity step 1)
Not yet released as a build. Includes everything from 0.4.1 below.

### Added
- **Revolve** is a real feature now: profile, axis (a construction line / any line of the sketch, or the sketch X/Y axis), angle (360 = full, negative flips), One Side / Symmetric / Two Sides, Auto/New/Join/Cut/Intersect, live preview.
- **Include / Project face edges**: sketching on a face includes its outline (lines, full circles, arcs) as real, purple sketch elements - offset them, trim them, snap to them, draw on them. Toggle "Include Face Edges" in the sketch palette; the **Project (edges)** button includes in-plane body edges in any sketch.
- Hole feature in the model (simple / counterbore / countersink, flat or 118 deg tip, through); dialog and placement come next.

### Changed
- Arrow handles (extrude etc.): the grab area follows the drawn head with a margin and a ring marks the grab point.

## 0.4.1 - 2026-10-11

### Added
- Sketch Fillet: **Shift+click** picks several corners (click a picked corner again to drop it), then **Enter** or a plain click on one more corner asks for one radius with live preview. One undo step.

- Sketch **Offset** works like Fusion: press O (or the ribbon button), a click takes the whole connected chain, click more curves to add (click a picked chain again to drop it, Alt+click = one element), Enter or right-click asks for the distance with live preview (negative = inward).

### Fixed
- Sketch selection: Shift+click used to pan instead of selecting, and Ctrl+click toggled twice. Both now add/remove one element.
- Rounded vertical corner standing on a lower step (stairs): a hairline notch was cut into the lower surface, drawn as a square corner outline round the rounded foot. The fillet tool now only reaches past an edge end where there is open space.

## 0.4.0 - 2026-10-11
First numbered version.

### Added
- Sketch **Trim** (T): remove the piece of a line, circle or arc up to the nearest crossings (dangling stubs too).
- Sketch **Mirror** (Shift+M): pick shapes, then a line or an origin axis.
- Pattern/Mirror: mirror steps across an origin or offset plane.
- **Shell** directions: Inside, Outside, Both (separate thickness each).
- Fillet/Chamfer edge picking: X / Alt see-through, Shift+double-click loop on the other face, Ctrl+click removes, Backspace undoes, Ctrl+Backspace clears.
- Version shown in the title bar and About dialog.

### Fixed
- Shell crashed on OK; Move Body dialog crashed on open.
- Fillet/Chamfer: mild bends in an extruded outline were taken for curved surfaces (walls not pickable); edges that moved after editing earlier steps were skipped (sharp edge left behind); inside corners of a bevelled outline got a notch; circle tools use the cylinder's segment count (half the triangles).
- Canvas image stayed the same when a new canvas reused an id.
- No demo "Base Box" at startup.
