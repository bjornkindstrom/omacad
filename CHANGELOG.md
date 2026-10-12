# Changelog

Versions: 0.x while the feature set is still growing, 1.0 when Omacad is a complete and dependable CAD.
The version lives in `omacad/__init__.py`; every build is published as release `v<version>` (and as `latest`).

## 0.6.25 - 2026-10-12

### Changed
- **Rounded rectangles are sized by their overall width and height** (via F9): the two size dimensions now measure the whole part (left wall to right wall, bottom to top wall) instead of the straight pieces between the corners. Change them and the corner radii keep their mm, and anything dimensioned from a wall (a Smart Circle hole, for instance) follows that wall.
- **Move / Rotate Body: "Lay on plane"** (via F9): a button in the panel; click it, then click the face that should rest on the ground, and the rotation and height are filled in (adjust or OK). Works about the body centre or the world origin.

## 0.6.24 - 2026-10-12

### Fixed
- Problem report screenshot now includes the 3D view's overlay (sketch dimensions, banner, ViewCube).

## 0.6.23 - 2026-10-12

### Changed
- About now says "Vibecoded by Kindstrom".

## 0.6.22 - 2026-10-12

### Fixed
- Smart Circle picked from the ribbon dropdown could not take typed numbers, because the keyboard focus stayed on the ribbon button. The view now takes the focus when the tool starts and when the cursor moves over it.

## 0.6.21 - 2026-10-12

### Changed
- The ribbon's Circle button has a dropdown with Center Circle and Smart Circle.

## 0.6.20 - 2026-10-12

### Changed
- **Rounded rectangle: radius after width and height** (via F9): after you type width and height and press Enter, a third field, Radius, opens and the preview shows all four corners rounding as you type. Enter confirms (an empty Radius keeps the value from the sketch panel). Works for both rounded rectangle tools.
- **Smart Circle shows its mode**: until you have a diameter, a small dashed shadow circle follows the cursor so it is clear the tool is active.

## 0.6.19 - 2026-10-12

### Fixed
- **Fill pattern left channels and strips unfilled** (via F9): hairline cracks between the triangles of the face were widened to margin-wide stripes by the inset, so whole rows of copies were missing; and on a sketch plane whose origin is not the world origin the face was shifted against the copies, so copies landed off the plate. Both fixed.

## 0.6.18 - 2026-10-12

### Added
- **Smart Circle** (Shift+C, or right-click in a sketch → Draw → Smart Circle): place a circle with numbers and Enter. Type the diameter, Enter; then the distance from the centre to the nearest *vertical* line (a sketch line or a face edge, highlighted as you move), Enter; then the same to the nearest *horizontal* line, Enter. The cursor picks which line and which side (a minus flips the side); an empty field + Enter or a click takes the cursor position. Backspace on an empty field goes back a step. The circle gets a diameter dimension and a distance dimension for every typed value, so it stays parametric. Afterwards the tool is ready for the next circle.

## 0.6.17 - 2026-10-12

### Added
- **Fillet and chamfer on arcs** (via F9): an open arc where a flat face meets part of a cylinder (a concave cut, a rounded corner) can now be picked and rounded or bevelled, not only full circles and whole outlines. The step remembers the arc by centre, radius and angle. Measure shows radius, arc length and angle for an arc.

## 0.6.16 - 2026-10-12

### Changed
- **Shapes inside the profile you extrude stay open** (via F9): when sketches lie in the same plane and one shape sits inside the profile you pick, extruding the big profile no longer fills the shape in; it is left open, as in Fusion. The selection highlight leaves it unshaded. **Shift+click** a profile of another sketch in the same plane to include it again (Shift+click it once more to remove it). The extrude step stores the open shapes and the extra profiles, so they do not depend on which sketches are visible. Steps from older files are unchanged.

## 0.6.15 - 2026-10-12

### Fixed
- **Changing Curve smoothness broke the model** (via F9): Extrude and Revolve pointed at their profile by number only, and a sketch is numbered differently when circles are cut into a different number of pieces, so steps ended up on the wrong profile (a spike, or nothing). Steps now also remember each profile's centre and area and find it again. Files from before this (made at 48 pieces) are read at 48 first to remember their profiles, so they open right at any smoothness. A file written by this version stores `curve_segments` and the signatures.

## 0.6.14 - 2026-10-12

### Added
- **Mark up the report screenshot**: in *Report problem* you can zoom the picture (mouse wheel around the pointer, middle/right button or Ctrl+drag to move, double-click to fit) and draw with a pen, rectangle or arrow. The marked picture is saved as `screenshot_marked.png` and the agent is told to look at it first.
- **Click what to copy in Pattern / Mirror**: click a surface in the 3D view and the step that made it (and its sketch) is ticked in the list; click again to untick. `Document.step_at_point`.
- **Right-click on a sketch profile** gives a menu for that profile (Extrude, Revolve, Deselect, plus Undo/Redo and View) and selects it.

### Fixed
- Right-clicking the selected profile used to light up the whole face around it and open the face menu.

## 0.6.13 - 2026-10-12

### Added
- **Arrow settings** (Settings > Sketch & Visning): *Arrow size* (0.3-4x) and *Arrow distance from the surface* (default 2 mm). The extrude arrow is now always drawn that far off the surface, in the direction it points, so it never starts inside the material; the distance you drag is unchanged.

### Fixed
- Tests no longer read or write the user's real settings file (a changed Curve smoothness could make a test fail).

## 0.6.12 - 2026-10-12

### Added
- **Curve smoothness setting** (Settings > Sketch & Visning): how many flat pieces a circle is cut into (32 to 360, default 96, was a fixed 48). Lower is lighter for the computer, higher gives smoother round shapes. Applies to circles, arcs, cylinders and spheres; the model is rebuilt when you change it. `omacad/model/quality.py`.

### Fixed
- **Foot fillets did not flow into each other at corners**: filleting the straight edges at the foot of a polygon wall left a notch at every corner, because each band ended square. Neighbouring foot edges on the same floor now run past the corner and are cut along the bisector (mitred).
- **Fill pattern drew broken triangles in the middle of the face**: copies touching a hole or something standing on the face were clipped, leaving fragments. Now only the outer edge of the face may cut a copy; a copy that would touch a hole is left out whole.

## 0.6.11 - 2026-10-12

### Added
- **Lay a face flat**: right-click a face > *Lay this face on the ground (XY)* or *on a face or plane...* turns and moves the body (one undoable Move step) so that face rests on the plane. `Document.lay_face_on`, helpers in `omacad/model/geometry.py`.
- **Right-click while a tool panel is open** (Extrude, Fillet, ...): *Finish* and *Cancel* in the menu. Right-click on the Move arrows picks the axis (X/Y/Z).
- **Esc leaves the current function** wherever the focus is: first a pending step, then the sketch tool, then the open tool panel, then the selection.

### Fixed
- The distance on the extrude arrow stays after you release the mouse (it follows the arrow until the tool closes; symmetric extrude shows the full distance).
- Spin box up/down buttons were blank boxes in some themes: they now have a visible background and arrows in the theme's text colour.
- The X/Y/Z buttons in Move were too narrow and hard to read: short labels, in the axis colours (filled when active).

## 0.6.10 - 2026-10-12

### Fixed
- **Polygon "Sides" field said mm**: the number of sides is a count, so it is shown as a whole number without a unit.

### Added
- **Value on the extrude arrow**: while you drag the arrow, the distance is shown as a label beside the middle of the shaft.
- **More right-click menus**: on empty space in 3D you get New Sketch on XY/XZ/YZ, Undo/Redo and View (Home/Top/Front/Right, fit, grid, edges); in a sketch you get Finish Sketch, Draw and Modify tool lists, Dimension, Construction mode, Undo/Redo and View (Look at sketch). The Draw/Modify lists come from the registry `omacad/ui/sketch_tools.py` (rectangle kinds in a Rectangle submenu), so a new tool appears in the menu once it is listed there; `tests/test_sketch_tools_registry.py` fails if a tool is missing. The face menu and the sketch element menu also end with Undo/Redo and View.

## 0.6.9 - 2026-10-12

### Added
- **Camera settings** (Settings > Sketch & Visning): perspective field of view (10-60°, default 30° instead of the fixed 45° that made the view look skewed) and an orthographic camera. Changing either leaves the zoom unchanged; only the perspective distortion changes. Tests in `tests/test_projection.py`.

## 0.6.8 - 2026-10-11

### Added
- **Timeline click shows what the step did**: clicking a step in the timeline colours the material it added (green) and removed (red) in the view; a second click clears it.

## 0.6.7 - 2026-10-11

### Fixed
- **Rough edge when a foot fillet is too big for the shelf**: a fillet at the foot of a wall assumed flat face under it. When a rim fillet had already narrowed the shelf, the fillet hung over the rounding like a thin lip. The radius now shrinks to the widest one that still rests on the face, so the two roundings run out smoothly into each other.

## 0.6.6 - 2026-10-11

### Fixed
- **Top view jumped when orbiting**: passing 89° elevation switched the camera's up vector to world Y regardless of azimuth, so the view rolled up to 90° at once. Z is now up at every elevation (the orbit stops at ±89.9°), so the view turns smoothly over the top. The plan's milestones after 0.6.x were renumbered (0.7 and up).

## 0.6.5 - 2026-10-11

### Changed
- A sketch on a face now has its origin in the middle of the face (the origin snap locks to the centre; edges, corners and midpoints already snap) and a grid on the face plane, centred there and sized to the face, instead of the ground grid around the world origin.

## 0.6.4 - 2026-10-11

### Added
- **Center Rounded Rect**: a rounded rectangle drawn from its centre (fourth kind in the rectangle dropdown, uses the palette's corner radius).

### Changed
- The sketch palette now sits at the top of the right-hand inspector instead of floating over the canvas.

## 0.6.3 - 2026-10-11

### Added
- **Rectangle dropdown**: 2-Point, Center and Rounded Rect are one ribbon button. Clicking it draws the default kind, the arrow lists all three and *Button default* chooses which one the button draws (remembered in settings).
- **Automatic restart on a new version**: the app watches the commit of its source tree; when a new commit appears (e.g. the agent finished a reported fix) it saves the document, the sketch being edited and the camera to `~/.local/share/omacad/session.json`, restarts and puts everything back (`app.py --resume`). It waits while a dialog is open, cancels if saving fails, and can be turned off in Settings.

## 0.6.2 - 2026-10-11

### Added
- **Rounded Rect** (sketch ribbon): a two-corner rectangle with all four corners rounded in one step. The radius is the *Corner radius* field in the sketch palette (capped just under half the shorter side); the live preview shows the rounded outline and Tab still types width and height. Reported from the app with F9.

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
