# Changelog

Versions: 0.x while the feature set is still growing, 1.0 when Omacad is a complete and dependable CAD.
The version lives in `omacad/__init__.py`; every build is published as release `v<version>` (and as `latest`).

## 0.7.9.57 - 2026-10-17

### Fixed
- **Missing or swapped letter parts (`e`, `o`, `a`, `å`, `ä`, `ö`) after editing sketch text** (#44): when a `SketchText`'s height, font, spacing or string content was edited, `solve_profiles()` could reorder profiles so a letter's outer profile and its counter-hole swapped indices or changed count, causing `Emboss` / `Extrude` / `Revolve` to pick the inner hole instead of the letter. `ProfileRefs` now tracks `_follows_text` and automatically synchronizes with `sketch.text_profile_indices()` whenever text is edited.
- **UI responsiveness & anti-freeze during live 3D previews**: added 50–60 ms `QTimer` debouncing and interactive quality mode (`quality.set_interactive_mode(True)`) to live previews in `feature_edit.py` and `tool_prompts.py`, precomputed fillet edge resolution outside the spinbox callback in `feature_edit.py`, added fast Ray–AABB bounding-box rejection in `picker_mixin.py`, and cleaned up stale OpenGL VAO/VBO cache entries in `render_mixin.py`.
- **`EQUAL` constraint between circles**: `solve_sketch()` now writes back solved radii for all `SketchCircle` entities whenever the solver changes their radius (not only polygon group circles).

### Added
- **Dimensioning for Arcs and Slots (`D` tool & right-click menu)**: clicking a `SketchArc` with the Dimension tool sets its **Radius (`R`)**; clicking a `SketchSlot`'s side sets its **Center-to-Center Length**, and clicking its rounded end cap sets its **Slot Width (`Ø`)**. Both are also available in the right-click context menu.
- **Complete Timeline Editing for `Split Body`, `Shell`, `Combine` and `Thread`**:
  - Added full timeline editing + live 3D split-plane preview for `Split Body`.
  - `Shell` timeline editing now preserves and allows changing open faces (`open_faces`).
  - `Combine` timeline editing now updates `target_body_id` and `tool_body_id` with historical body names from before the step.
  - `ThreadFeature` now persists `exprs` and `suppressed` across save/load and timeline edits.
- **Browser & Ribbon polish**: enabled renaming construction planes (`cplane`) in the Browser, unchecked all 14 sketch tool buttons when leaving sketch mode, added missing timeline icons/tooltips, and translated remaining Swedish UI strings in `side_panel.py`, `tool_prompts.py`, `boolean_dlg.py` and `thread_dlg.py` to English.

## 0.7.9.56 - 2026-10-17

### Added
- **Start Offset in mm for Extrude** (#43): added a **Start Offset** field (`mm`, with formula and parameter support) in *Extrude* so extrusions (*One Side*, *Symmetric*, *Two Sides*) can begin at a signed offset distance from the sketch plane, with live 3D handle positioning and timeline editing support.

### Changed
- **Offset Face dialog**: removed the embedded thread-fit guide box from the *Offset Face* panel.

## 0.7.9.55 - 2026-10-17

### Added
- **Live 3D preview when editing from Timeline** (#31): editing any step from the timeline (*Extrude*, *Emboss*, *Revolve*, *Box*, *Cylinder*, *Sphere*, *Fillet/Chamfer*, *Offset Face*, *Shell*, *Combine*, *Pattern/Mirror*, *Move*, *Thread*) now shows a live 3D preview in the viewport while you adjust values and temporarily hides the replaced target body.
- **Edit Revolve, Shell and Combine from Timeline**: double-clicking or right-clicking a *Revolve*, *Shell* or *Combine* step in the timeline now opens its dialog to edit parameters.
- **Copy primitives with Pattern / Mirror** (#35): standalone primitives (*Box*, *Cylinder*, *Sphere*, *Thread*) can now be copied with *Linear Pattern*, *Circular Pattern* and *Mirror*, and are automatically pre-checked in the Pattern dialog when created last.
- **Easy text editing in sketches** (#38):
  - Clicking or double-clicking anywhere inside the letters or bounding box of a `SketchText` selects / edits it.
  - Added an **🔤 Edit Text…** button in the *Sketch Palette* whenever the active sketch contains text.
  - Text items are now listed as child nodes under their sketch in the *Browser* tree—double-clicking or right-clicking a text node enters the sketch and opens the text editor directly.
- **Full cylindrical wrapping (>180° / 360°) and Wrap toggle in Emboss** (#40): added a **Wrap around curved surface** checkbox (enabled by default) in *Emboss*. When enabled on a cylinder, the embossed/debossed profile wraps around the cylinder's circumference using true arc-length mapping (`theta = s / r`), supporting wide text and full 360° wraps; unchecking it uses flat projection.
- **Smart Box & Smart Cylinder** (#42): *Box* and *Cylinder* dialogs and timeline editors now include optional **Wall Thickness (Shell)** (hollow with open top), **Outer Edges** (*Fillet* or *Chamfer* + size) and **Inner Edges** (*Fillet* or *Chamfer* + size) in a single parametric step.
- **Standalone Offset Face button & clearer Guide Line button in Ribbon**: added `Offset Face` to the Solid tab when *Group Modify* is off, styled all ribbon dropdown menus consistently with the active theme, and renamed `Construct (X)` to `Guide Line (X)` (`┄`) with a clearer tooltip.

## 0.7.9.54 - 2026-10-17

### Fixed
- **Black tooltip box on timeline steps, Browser and Inspector** (#39): `TimelineBar.scroll_area`, `BrowserWidget` and `InspectorPanel` had selector-less stylesheets (`border: none; background: transparent;`) which cascaded to every descendant widget—including Qt's `QTipLabel` popup window—turning the tooltip background `RGBA(0, 0, 0, 0)` (solid black on Windows and Wayland). Scoped those stylesheets to their container classes/IDs (`QScrollArea`, `QWidget#BrowserWidget`, `QWidget#InspectorPanel`).

## 0.7.9.53 - 2026-10-17

### Fixed
- **Tooltips and button margins**: styled `QToolTip` globally, scoped `TimelineChip` frame styles, and reduced `QPushButton` horizontal padding so dialog buttons (*Yes*, *No*, *Send request*) never clip text on high-DPI / low-resolution screens.
- **Settings dialog cleanup**: removed duplicate *Toolbar button size* control, organized preferences into clear tabs (*Appearance*, *Interface*, *Sketch & View*, *General*), and integrated *Theme Editor* as a button inside *Appearance*.

## 0.7.9.52 - 2026-10-17

### Added
- **Your own image in Request a change / Report problem**: the dialog has *Use my own image…* (pick a PNG/JPEG from your computer; you can zoom and draw on it) and *Use the screenshot* to go back. With your own image, it is sent instead of the built-in screenshots (`screenshot_own.png`).

## 0.7.9.51 - 2026-10-17

### Fixed
- **Emboss / Deboss now hugs a cylinder** (via the in-app report): text sketched on a plane in front of a cylinder used to float at the plane; the letters now wrap round the cylinder behind them (standing the depth above its surface, or pressed in for Deboss) and are joined to it. A flat face behind a sketch plane in the air is reached too.

## 0.7.9.50 - 2026-10-17

### Added
- **Text in sketches** (Sketch > Text, as in Fusion): options in the side panel: Type (*Text* in a frame, or *Text On Path* along a circle, arc or line), the text (several lines), Font, Bold / Italic, Height (of a capital letter), Character spacing, Horizontal and Vertical alignment, Angle, Flip, and for a path: Placement (above / below) and *Fit to path*. A ghost follows the cursor; click to place, or click the circle / arc / line the text follows (it lights up). The letters are real sketch profiles, with the holes of O, A, B ... as holes: they can be extruded, embossed, moved (M), rotated, mirrored (Mirror makes a mirrored copy), saved, and the text moves with its path when the circle changes. Right-click a text: **Edit Text…** or **Explode Text** (turns it into lines). Placing and editing is one undo step; Cancel / Esc removes it.
- **Emboss** (Solid > Create > Emboss, as in Fusion): pick the profiles (it starts with all the letters of the newest text sketch picked; *Select all text of this sketch*), set the **Depth** (positive = Emboss adds material, negative = Deboss presses it in; the Effect follows the sign), **Flip normal**, **Horizontal / Vertical distance** and **Rotation**. Live green / red preview, one undo step, editable from the timeline, formulas and parameters work. Emboss steps can be copied round a circle with Pattern / Mirror (Circular pattern).

## 0.7.9.49 - 2026-10-17

### Changed
- The SOLID / SKETCH selector moved out of the ribbon: it is a small bar in the 3D view directly above the Browser, part of the big box, and the Browser moved down to make room. SKETCH still appears only while a sketch is open. The ribbon is one row lower (just the buttons).

## 0.7.9.48 - 2026-10-17

### Changed
- All ribbon buttons are the same size, in both tabs, with and without names (the widest plain button sets the width), instead of each button being as wide as its own text. The small margins from 0.7.9.47 are kept.

## 0.7.9.47 - 2026-10-17

### Changed
- Timeline: only the last step shows its name, the others are small icons. Hover a step and it grows to show its name, and the model shows what that step made: green = material it added (a coil, an extruded face with its preview), red = material it removed; a sketch step lights its sketch up. Moving away restores what you had (a step you clicked stays coloured). A quick pass over the steps does not compute anything.
- The SOLID / SKETCH tabs are small muted text on the window's own background instead of a band of their own, with a thin line under the active one.
- Ribbon buttons have much smaller margins, with and without text, so more fit and the ribbon is lower.

### Fixed
- Help > Changelog has a Close button and opens at the newest version (it used to open at the oldest entries at the bottom).

## 0.7.9.46 - 2026-10-17

### Changed
- The bar at the bottom of the window is gone, and with it the *Report problem* button (F9 and Help > Report problem still work). The status message now sits in the 3D view above the Azimuth / Elevation / Zoom line, and the sketch status and the units at the lower right, as plain text that takes no room of its own. A running background job shows "Working…" in the same line. The view is about 50 px taller.

## 0.7.9.45 - 2026-10-17

### Added
- A thread on a cylinder now follows the cylinder's diameter (#37): it is measured when the Thread step runs, so an Offset Face (or any earlier step) that changes the cylinder carries the thread along; the difference you typed (for example -0.01 mm) is kept. New threads on a cylinder follow by default; in *Edit Thread* the checkbox **Follow the cylinder's diameter** switches it on for an older thread (it then takes the cylinder's diameter as it is now).

## 0.7.9.44 - 2026-10-17

### Fixed
- Under a section view the preview of a cut (Extrude cut, Offset Face ...) was partly hidden behind the opaque cut face; it is now drawn after it and shows through the cross-section (#36).

## 0.7.9.43 - 2026-10-17

### Changed
- Move / Rotate gizmo: smaller wheels and arrows, pale and translucent until the mouse is on them. Rotation rings show degree ticks (every 15°, longer at 45° and 90°) outside the ring: drag close to the ring to turn freely, drag outside the ticks to snap to 15° steps.

## 0.7.9.42 - 2026-10-17

### Added
- Move / Rotate: **Face to face**. Press *Pick two faces…*, click a face on the body, then the face or plane it should go to; the movement and turning are filled in (live preview). *Direction*: **Touch** (turn so the faces meet, like assembling parts), **Flush** (both faces look the same way, in one plane) or **Slide** (no turning, along the target's normal). *Centre on target* puts the face's centre on the target's centre, off keeps the sideways position. Changing the choices recomputes from the same two clicks.

## 0.7.9.41 - 2026-10-17

### Added
- Right-click with two or more bodies selected: **Join N Bodies** (joins them into the first one, one undo step), in every right-click menu outside sketch mode.
- Thread / Coil: the lead-in is now a choice: *Smooth lead-in & runout* (0.75 turn), *Smooth lead-in & runout, short* (0.3 turn) to try, or *None*. Editing an existing thread selects the matching entry.

### Fixed
- Combine (the dialog) was not an undo step; it is now (`Document.combine_bodies`).

## 0.7.9.40 - 2026-10-17

### Added
- Planes without a tool: an origin or construction plane lights up under the cursor, and every shown plane has its name in small text in its lower-right corner as seen from the camera.
- Right-click on a plane: Split Body with this Plane, Offset Plane from this Plane, Create Sketch on this Plane, Hide Plane.
- Right-click on a flat face: Offset Plane from this Face.
- While Split Body is open, clicking a plane in the view makes it the splitting plane.

### Fixed
- A hidden origin plane could still be clicked and right-clicked where it would have been.

## 0.7.9.39 - 2026-10-17

### Fixed
- The Inspector (Design overview, Shortcuts, tool panels) is as wide as what it shows instead of a fixed 380 px, stays at the right edge, and the ViewCube moves along with it.
- The window screenshot in a problem report (F9) now includes the Browser and Inspector panels that float on the 3D view.

## 0.7.9.38 - 2026-10-17

### Fixed
- CI: the visual thread test skips itself without a real display (it crashed on the build server, so 0.7.9.37 was not released).

## 0.7.9.37 - 2026-10-16

### Fixed
- Offset Face on a thread gave no clearance: it changed the Thread step, and the jar is cut by the lid, so the lid's thread grew with the groove and the fit stayed exact. Now it is an Offset Face step that changes only the body you click: the threaded zone (coil and bore/pin) is rebuilt bigger or smaller and cut from or added to that body. -0.2 on the jar gives ~0.2 mm of air all round the lid's thread; the lid keeps its size.
- The thread offset is now the same along the whole coil, also in the lead-in taper.

## 0.7.9.36 - 2026-10-16

### Fixed
- Under a section view the live preview of a tool (Offset Face, Extrude ...) was the whole solid and covered what you were looking at, for example the thread inside a jar. It is now cut like the bodies.

### Added
- How-to video script `video/offset_thread_take.py` (Offset Face on a thread, with the Browser and the tool panel in the picture).

## 0.7.9.35 - 2026-10-16

### Fixed
- Offset Face on a thread did nothing when the click landed on the wall between the turns (a short cylinder band, "could not be moved"). A cylinder that is coaxial with a thread and inside its length now changes the Thread step too, so the whole threaded zone works.

## 0.7.9.34 - 2026-10-16

### Fixed
- A body hidden with its eye in the Browser came back after any rebuild of the history (for example Offset Face on a thread brought the lid, with its big thread, back into the jar). Hidden bodies now stay hidden.

### Changed
- The thread-fit guide is a small box inside the Offset Face panel (picture, text, Back/Next, Hide). "Bigger" opens the same guide in a large window at the same step.

## 0.7.9.33 - 2026-10-16

### Added
- In-app guides: Help > Guides opens a small window with pictures and short steps. The first guide, "Make a thread looser or tighter (Offset Face)", is also behind the "? Guide: thread fit" button in the Offset Face panel. Guide pictures are small JPEGs (max 900 px wide, 120 KB each) so the app does not grow.

## 0.7.9.32 - 2026-10-16

### Fixed
- The Offset Face explanation line was cut off at the bottom of the tool panel; it is shorter now ("Thread 1 coil: OK makes every turn 0.2 mm thicker.").

## 0.7.9.31 - 2026-10-16

### Fixed
- Offset Face on a thread: the live preview still deformed the mesh and looked hairy; it now shows the rebuilt thread, exactly what OK gives. The explanation line under the dialog text uses the theme's text colour (the yellow one was unreadable).

## 0.7.9.30 - 2026-10-16

### Added
- Offset Face explains itself: a tip on how to get a looser or tighter thread fit, and a line that says what OK will do when the picked surface is a thread coil ("makes the whole coil 0.2 mm thicker").

## 0.7.9.29 - 2026-10-16

### Changed
- Offset Face on a thread/coil surface now changes the Thread step itself (new `grow` value: the tooth profile is offset on every side) instead of deforming the finished mesh. The result is an exact, clean thread, it follows later Moves, and it is one undo step.

## 0.7.9.28 - 2026-10-16

### Added
- Hovering a sketch line, circle, arc or rectangle, or a solid edge, shows its measures (length, angle, radius, diameter) in the inspector (#30).

## 0.7.9.27 - 2026-10-16

### Fixed
- Ribbon buttons were clipped on Windows and the second row of constraint buttons was hidden in sketch mode (#33, #34): the ribbon had a fixed height. It now follows the height of its content.

## 0.7.9.26 - 2026-10-16

### Fixed
- Offset Face on a thread/coil left hundreds of wall vertices almost unmoved, giving a jagged result: micro triangles that flip by float rounding made the fold guard halve the step over and over. Only real triangles count now.

## 0.7.9.25 - 2026-10-16

### Fixed
- Offset Face on a thread or other curved surface no longer folds the flat faces next to it (end caps) into slivers: rim vertices slide within the neighbouring face, and a move that would turn a triangle inside out stops short.

## 0.7.9.24 - 2026-10-16

### Fixed
- **Request #32: Offset Face on a cylinder left slivers (fins) of the old wall behind** (the report's body fell apart into 53 pieces): the ring that is added or removed now reaches a little past the old wall, so no hair-thin remainder is left. Test with the report's document in `tests/test_offset_face_hover_and_slivers.py`.
- **Offset Face: cylinders, threads and other curved surfaces now light up under the cursor** (like flat faces), so you can see what a click will pick.

## 0.7.9.23 - 2026-10-16

### Fixed
- Offset Face under a Section View: clicks now hit the cut surface you see (for example the inner thread) instead of the half of the body that is cut away.

## 0.7.9.23 - 2026-10-16

### Changed
- **Section view: every body gets its own tint on the cut face** (yellow, light blue, green, pink, lavender, peach, in the order of the bodies), with hatching in a darker shade of the same colour, so touching bodies can be told apart. A single body looks as before. Test in `tests/test_section_hatch.py`.

## 0.7.9.22 - 2026-10-16

### Added
- **Offset Face works on curved surfaces such as threads and coils**: clicking a surface that is not flat or a plain cylinder picks the whole smooth patch around the click (a whole round thread, a flank, a fillet) and moves it along its own normal; + adds material, - removes it. Clicking the same patch twice moves it once. Tests in `tests/test_offset_face.py` (sphere, flat patch, real thread).

## 0.7.9.21 - 2026-10-16

### Added
- **Offset Face** (Modify > Offset Face, Modify menu in the ribbon, or right-click a face): click flat faces, holes or pins, type a distance (+ adds material, so a hole gets smaller; - removes it), OK. Made for tolerances on threads, pins and pockets. Flat faces move along their normal (neighbouring faces that are slanted stay bounded by their own planes); full cylinders change radius. Live preview, one undo step, editable in the timeline, formulas and parameters work in the distance. Tests in `tests/test_offset_face.py` and `tests/test_offset_face_ui.py`.
- **Help > Changelog** shows the whole `CHANGELOG.md` inside the app (searchable). The file is packaged with the app. Test in `tests/test_changelog_dialog.py`.

## 0.7.9.20 - 2026-10-16

### Fixed
- **Fillet at the foot of a leaning wall hung over the box edge when the radius was too big**: a concave straight edge was never size-limited, so the filling extended past the floor face. Like in Fusion 360 the radius is now limited so the fillet stays on the floor (and the wall). Fillets that fit were already exact. Test in `tests/test_wall_foot_fillet.py`.

## 0.7.9.19 - 2026-10-16

### Fixed
- **Mouse move raised AttributeError after 0.7.9.18** (panels in the 3D view looked displaced): `Viewport3D` never defined `hover_face` until Fillet/Chamfer was started, but the idle hover reads it on every move. It is now set in `__init__`. Test in `tests/test_idle_hover.py`.

## 0.7.9.18 - 2026-10-16

### Fixed
- **No hover highlight outside Fillet/Chamfer** (report via F9): edges and flat faces now light up under the cursor whenever nothing is being edited, and right-clicking a lit edge (or a face) offers Fillet / Chamfer, which opens the tool with those edges already picked. Test in `tests/test_idle_hover.py`.

## 0.7.9.17 - 2026-10-16

### Fixed
- **The four timeline playback buttons were empty squares** (the arrow emoji did not render): they now have drawn icons (rewind, step back, step forward, fast forward) in all three icon sets, and follow the theme. Test in `tests/test_timeline_icons.py`.

## 0.7.9.16 - 2026-10-16

### Added (request from Björn)
- **Right-click on a sketch in the 3D view offers Edit Sketch** (also Extrude and Hide Sketch): on the sketch's lines or circles, and "Edit Sketch" also leads the menu when you right-click inside one of its shaded profiles. Test in `tests/test_browser_tree.py`.

## 0.7.9.15 - 2026-10-16

### Changed (requests from Björn: browser like Fusion 360)
- **The browser tree is built like Fusion 360's** (same colours/theme as before): `(Unsaved)` / the file name at the top, then Document Settings (Units, Parametric Design), Named Views (Home, Top, Front, Right, Back, Left, Bottom; click one to go there), Origin, Analysis (the section views), Bodies, Canvases and Sketches. All sketches sit under Sketches (also those drawn on a body face). Bodies, Canvases and Sketches have an eye on the group that shows/hides everything in it, and **V** shows/hides the selected item. The group names no longer carry counts, so open/closed state is kept.
- **Right-click menus like Fusion 360:** sketch: Extrude (E), Offset Plane, Edit Sketch, Rename, Show/Hide (V), Find in Window, Find in Timeline, Delete; body: Move, Shell, Split, Rename, Show/Hide, Find in Window/Timeline, Export STL/STEP, Delete; planes and canvases got Show/Hide and Rename too. Find in Window frames the body or sketch, Find in Timeline scrolls to its step and colours what it changed.
- **Menus were black:** every pop-up menu is now dark grey with an orange selection, like the menu bar.
- Tests in `tests/test_browser_tree.py`.

## 0.7.9.14 - 2026-10-16

### Changed (request from Björn: Section View like Fusion 360)
- **The cut face of a section view is hatched like Fusion 360:** pale yellow with dark diagonal hatching and a black outline (holes stay open), instead of a flat highlight colour. The hatching keeps about the same density on screen when you zoom. Logic in `omacad/model/section_hatch.py` (shapely), drawing in `render_section_cap`. Tests in `tests/test_section_hatch.py`.

## 0.7.9.13 - 2026-10-16

### Fixed / Changed (reports from Björn)
- **Tick boxes were black** (Pattern "Copy these steps", "Second direction", every list/tree/dialog check box): no theme was applied to the indicators, so the style drew black boxes where a tick could not be told from an empty box, which made it look impossible to un-tick a step. They are now a clear empty box and an orange box with a white tick, in the theme's colours (`theme.indicator_stylesheet`, set on the application).
- **The tool panel fits its content:** the panel on the right is now only as tall as the open tool needs (no scrolling when there is room), and only scrolls when the window is too short. The sideways scrollbar is gone (the panel is 380 px wide for the 358 px tool boxes). Test in `tests/test_tool_panel_fit.py`.

## 0.7.9.12 - 2026-10-16

### Changed (requests for change from Björn)
- **Smart Circle works with lines at any angle:** step 2 now measures from the centre, at right angles, to the nearest straight line of any angle (vertical, horizontal or slanted; sketch lines and face edges); step 3 does the same to the nearest line that is not parallel to the first, and the two distances fix the centre. Both steps are still needed. With nothing typed a step still just takes the cursor, as before. The dotted measure line and the dimensions it creates (distance from the centre to the line) follow the right angle. Before, only vertical and horizontal lines were considered. Tests in `tests/test_smart_circle.py`.
- **New Dimension icon:** the Dimension button no longer uses the ruler (that is the Measure icon). It shows a Fusion 360 style dimension: a shape with extension lines, a dimension line with arrowheads and a value box (all three icon sets).

## 0.7.9.11 - 2026-10-16

### Changed (requests for change from Björn)
- **No sketch-mode banner:** the "SKETCH MODE: Sketch 1 (XY) · Under defined" box at the top of the 3D view is gone (it covered the drawing). The sketch name, plane and solve status ("Under defined (2 DOF)") now sit at the right end of the status bar.
- **Dimension value box in the 3D view:** with the Dimension tool, as soon as two points are picked a small box appears next to them showing the distance as it is. It follows the cursor (above/below = horizontal, left/right = vertical, diagonal = aligned) until you type; type a number, a formula or a parameter name, then press Enter or click to place the dimension (a click without typing keeps the measured value, Esc cancels). Other dimension values (diameter, length, angle, distance to a line, editing an existing dimension) also open as a box next to the cursor instead of in the side panel. Tests in `tests/test_inline_dimension_box.py`.

## 0.7.9.10 - 2026-10-16

### Changed / Added (requests for change from Björn)
- **Smaller plane markers:** the origin plane markers (shown while picking a plane, and when you turn a plane on under Origin) now cover only the first quadrant of each plane (positive u and v) and are smaller: 20 mm, or 75% of the model's largest coordinate. Only that quadrant can be clicked. Test in `tests/test_origin_plane_quadrant.py`.
- **Thread / Coil at the top of a cylinder:** after picking a cylinder (outside or inside) the Thread dialog has "Place at: Bottom end / Top end" and a gap in mm from that end, so a short thread no longer always starts at the bottom. A thread longer than the free space falls back to the bottom. Stored on the step (`anchor`, `anchor_gap`, `host_length`) so it can be edited and is saved. Tests in `tests/test_thread_anchor.py`.

## 0.7.9.9 - 2026-10-16

### Added (request for change from Lennart: distances between objects, movable dimensions)
- **Drag a dimension out of the way:** in a sketch, press a dimension badge and drag it; the dimension line follows the cursor (length, rectangle sides, diameter/radius, angle, horizontal/vertical/aligned distance, distance from a point to a line). A plain click still edits the value. A drag is one undo step. Logic in `omacad/model/dim_layout.py` (`offset_for_point`, the inverse of the drawing layout).
- **Distance between two parallel lines:** with the Dimension tool, clicking two lines that are parallel (within 0.5 degrees) now gives a distance (and keeps them parallel with a constraint) instead of an angle.
- **Set the distance between two bodies (3D):** in the Measure tool pick an edge on each of two bodies, then press D, type the wanted distance and the second body moves along the measured line (a Move step in the timeline, so it can be edited and undone).
- Tests in `tests/test_dimension_distance.py`.

## 0.7.9.8 - 2026-10-16

### Added (request for change from Björn: files)
- **Unsaved-changes question:** New Design, Open (also from Open Recent) and closing the window ask "Do you want to save the changes to <name>?" (Save / Don't Save / Cancel) when the design differs from what is on disk. A cancelled Save As or a failed write keeps the current design. Selecting or moving the camera is not a change.
- **File > Open Recent** (last 10 files, newest first, missing files are removed, "Clear Recent Files"). Files are added when opened or saved.
- Save As already existed (File > Save Project As..., Ctrl+Shift+S). Tests in `tests/test_file_session.py`; the logic is in `omacad/ui/controllers/file_session.py`.

## 0.7.9.7 - 2026-10-16

### Fixed
- **The Browser tree collapsed whenever something changed** (hiding a plane, axis, body ...): the tree is rebuilt from the document on every change and every node came back with its default state (the Origin group closed). Now the expanded/collapsed state of every node and the scroll position are kept across a rebuild. Test in `tests/test_origin_visibility.py`.

## 0.7.9.6 - 2026-10-16

### Added (request for change from Lennart: control what is shown of the origin)
- **Origin visibility:** the whole origin, each of the X/Y/Z axes and each of the XY/XZ/YZ planes can be shown or hidden, from the eye icons in the Browser (Origin group) or from View > Origin. The planes are hidden by default, as before; showing one draws it as a translucent quad. Turning a single part on also turns the origin back on. The axes no longer depend on the ground grid being shown. The choice is saved in the `.omacad` file (`origin_vis`). Picking a plane while sketching still shows all three. Tests in `tests/test_origin_visibility.py`.

## 0.7.9.5 - 2026-10-16

### Changed (request for change: bigger drawing area)
- **Icon-only ribbon:** the text under the toolbar buttons is gone by default, buttons and margins are tighter and the ribbon is about 30% lower, so the drawing area gets bigger. Hovering a button shows a tooltip that starts with its name. Settings > Sketch & View has "Show button names under the toolbar icons" to bring the labels back. Test in `tests/test_ribbon_compact.py`.

## 0.7.9.3 - 2026-10-16

### Added & Enhanced (Fusion 360 Parity)
- **Fuskion420-tema (Fusion 360 färgval):**
  - Nytt tema `assets/themes/fuskion420.toml` med exakta färgval från Autodesk Fusion (canvas `#F7F7F7`, grid `#D8DDE3`, accent/highlight `#0696D7`, finish green `#2E7D32` och rena gråa nyanser).
  - Valbart i Settings-dialogen under Theme Mode ("Fusion 360 (fuskion420)").
- **Genomskinligt Browser-träd:**
  - Vänstra Browser-panelen har gjorts genomskinlig och integrerad i skärmen så 3D-vyn syns igenom, med flytande hover- och markeringsstilar precis som i Fusion 360.
- **Filnamn i menyraden:**
  - Det aktiva dokumentets filnamn visas nu tydligt uppe till höger i menyraden med ren typografi och ikon (`📄 <filnamn>`).
- **Genomskinlig Inspector (högra verktygsfältet):**
  - Högra verktygsfältet är nu helt genomskinligt där det inte finns innehåll. Endast aktiva verktygsdialoger, sketch palette och infokort har kortbakgrund, medan tomma ytor smälter in i 3D-skärmen.

## 0.7.9.2 - 2026-10-16

### Fixed
- **Settings-dialogen och sparaknappar på mindre skärmar (Windows):**
  - Flikarna i Settings-dialogen (Theme samt Sketch & View) är nu inbäddade i `QScrollArea` och dialogens initiala storlek är anpassad så att Save/Cancel-knapparna längst ned alltid syns och går att klicka på oavsett skärmupplösning eller skalfaktor i Windows.
  - Regressionstest tillagt i `tests/test_settings_dialog.py`.

## 0.7.9.1 - 2026-10-16

### Fixed
- **Fill face pattern on edge-based features without sketches (e.g. chamfers/fillets on bottom face):**
  - When patterning a fillet or chamfer with "Fill face pattern" (such as chamfering holes on the bottom face of a model), the pattern failed because `_source_plane` assumed the source feature was created from a sketch (`sk.plane`).
  - Now `PatternFeature._source_plane` determines the target face plane from the feature's edges and planar face matches on the body, or from the coplanar faces of the modified region.
  - Regression test added in `tests/test_fill_face_chamfer.py`.

## 0.7.9.0 - 2026-10-15

### Added & Fixed (Fusion 360 Parity)
- **Markering av plana ytor i Fillet och Chamfer (Fusion 360-paritet):**
  - I Fillet/Chamfer-kantmarkeringsläge kan användaren nu klicka direkt på en plan yta (eller hovra över den) för att markera alla dess yttre gränskonturer och inre hål/slitsöglor på en gång, precis som i Fusion 360.
  - Hovring över en plan yta i kantläget ger en genomskinlig färgmarkering för tydlig feedback.
  - Klick på en plan yta markerar alla tillhörande loopar/kanter; om de redan är markerade avmarkeras de (eller avmarkeras selektivt med Ctrl+klick).
  - Löser problemet där användare vänt en modell upp och ner och försökt fasa/runda undersidan och dess konturer.

## 0.7.8.9 - 2026-10-15

### Fixed
- **Markering av LoopEdge vid överlappande cirkelbågar (Fillet/Chamfer):**
  - På plana ytor med sammansatta konturer (raka sidor och hörnradier, t.ex. avrundade plattor) fanns både en övergripande `LoopEdge` och enskilda `CircularEdge`-bågar för hörnen. Vid klick för kantmarkering prioriterades cirkelbågen om den låg marginellt närmare skärmklicket, vilket hindrade användaren från att markera och fasa/runda hela ytterkonturen. Nu prioriteras `LoopEdge` vid sammanfallande kanter (near-ties inom 1 px) i `_pick_edge`.

## 0.7.8.8 - 2026-10-15

### Performance & Fixed (Shell Feature)
- **Massiv optimering av Shell-verktyget:**
  - Snabbväg `_shrink`: Planära och konvexa solider eroderas nu inåt via snabba planförskjutningar (`trim_by_plane`) i stället för tung 3D Minkowski-difference, vilket ger en hastighetsökning på 20–50×.
  - Optimerad sfärupplösning för Minkowski-beräkningar på krökta solider för att drastiskt reducera CPU-belastning.
  - Debounce (75 ms) på förhandsvisningen i Shell-dialogen för att förhindra att UI:t fryser vid snabb textinmatning eller stegning av väggtjocklek.

## 0.7.8.7 - 2026-10-15

### Performance & Engine (High-Performance Engine)
- **Topologicache för plana ytor och kanter:**
  - `compute_planar_faces_and_edges` cachar nu analysen per geometriskt fingerprint, vilket ger över 800× snabbare uppslag för oförändrade solider.
- **Inkrementell tidslinjeomräkning (Incremental Timeline Recompute):**
  - Tidslinjen sparar och återanvänder checkpoints för stegen i historiken; vid ändring beräknas enbart påverkade nedströmssteg om istället för hela historiken från steg 0.
- **GPU VBO/VAO Caching för 3D-solider:**
  - Viewporten laddar nu upp body-meshar och skarpa linjekonturer direkt till dedikerade GPU VBO/VAO:er så kameranavigation (orbit/pan/zoom) flyter med full GPU-framerate utan CPU-tapp.
- **Adaptiv tessellering under interaktiv dragning:**
  - Under aktiv dragning i 3D-handtag (t.ex. extrude-pil) används en optimerad lägre segmentupplösning, med automatisk återgång till full finupplösning vid släpp.
- **Profilcache för 2D-skisser:**
  - `Sketch.solve_profiles` fingeravtryckstestar linjer och referenser för att undvika onödig Shapely-polygonisering.
- **Bakgrundstråd (`QThreadPool`) och laddningsindikator:**
  - Integrerad trådpool och progressindikator i statusraden för asynkrona geometriberäkningar.

## 0.7.8.6 - 2026-10-15

### Performance & Fixed
- **Prestandalyft för solider och omräkning av tidslinjen:**
  - `compute_planar_faces_and_edges`: delar topologisk analys mellan ytor och kanter i en enda genomgång istället för dubbla körningar.
  - Snabbväg för enkla trianglar i `_group_min_width` och tidig exit i `_curved_roots` gör igenkänning av plana ytor och kanter upp till 6× snabbare.
  - Live-preview i Thread & Coil har fått 60 ms debounce vilket förhindrar att UI:t fryser vid snabb textinmatning eller stegning i spinnboxar.
  - Tidslinjeomräkning på modeller med coils och gängor går nu över 70 % snabbare, och hela testsviten exekverar på halva tiden.

## 0.7.8.5 - 2026-10-15

### Fixed
- **Automatisk kapning av fnas och överhäng på gängändar (Thread / Coil end trimming):**
  - Gängor och coils kapas nu automatiskt exakt längs ändplanen `z=0` och `z=length` med `trim_by_plane`.
  - Detta eliminerar fnas och profiler som sticker ut förbi cylinderns ändytor vid både trapetsformade, metriska och runda profiler.

## 0.7.8.4 - 2026-10-15

### Added
- **Valbar AI-agent för felrättning (agy / Claude / Gemini / Omarchy):**
  - Stöd för att köra **Antigravity CLI (`agy`)** direkt när fel rapporteras (F9).
  - Möjlighet att välja standard-AI i Inställningar (`Ctrl+,` -> *Sketch & View* -> *AI agent for fixing errors*).
  - Val av AI direkt i felrapporteringsdialogen med sparad standard.

## 0.7.8.3 - 2026-10-15

### Fixed
- A flat face is no longer split by 1e-9 float noise in tiny triangle normals, so the rim circle of a tilted cylinder top can be selected for Fillet/Chamfer.

## 0.7.8.2 - 2026-10-15

### Fixed
- **Rund gängprofil för burkar och behållare (DIN 168 / bottle round thread):**
  - Justerade rundprofilens radie och flankbredd till korrekta behållarproportioner (radial höjd ~0.22·pitch och axiell halvvidd ~0.28·pitch).
  - Integrerade exakt FDM-tolerans/clearance mellan utvändig gänga (burkhals) och invändig gängskärare (lock) så att lock glider på mjukt utan att kärva eller kollidera.

## 0.7.8.1 - 2026-10-15

### Fixed
- Rounded thread/coil left bare cylinder between the turns (wire radius was 0.22 x pitch). The ridge is now an ellipse almost as wide as the pitch.

## 0.7.7.3 - 2026-10-15

### Fixed
- **Dölj origin-plan vid cylinderplockning (*Hide Origin Planes in Thread/Coil Pick*):**
  - Stora origin-plan (XY, XZ, YZ) ritas inte längre ut och blockerar inte klick när du väljer cylindrar eller ytor för Thread / Coil.
  - Klick i 3D-vyn träffar nu garanterat cylinderytan eller modellens ytor utan att origin-planen kommer i vägen.

## 0.7.7.2 - 2026-10-15

### Fixed
- **Mått & Passning utan glapp (*Zero-Gap Seamless Attachment*):**
  - Åtgärdat beräkningen för spiralradier vid applicering på befintliga cylindrar. Coils och gängor lägger sig nu direkt på cylinderns ytteryta ($R = D/2$) med sömlös överlappning så att boolesk sammanfogning (`Join`) blir 100% vattentät utan något synligt glapp eller nedsänkning.
  - Korrigerat skärradien för invändig gängning i hål (`Cut`) så att gängspåret skär rent och med rätt djup in i hålväggen.
- **Helautomatisk aktivering & måttsättning (*Auto-Measure on Click*):**
  - När verktyget öppnas aktiveras ytplockning direkt – du behöver inte trycka på "Välj yta / cylinder", utan kan direkt klicka på valfri cylinder eller hål i 3D-vyn.
  - Cylindern mäts automatiskt och sätter in exakt diameter, längd samt rekommenderad stigning/preset anpassad för 3D-print.
  - Ytplockningen förblir aktiv så du enkelt kan klicka på andra cylindrar eller ytor för att direkt uppdatera måtten.

## 0.7.7.1 - 2026-10-15

### Added
- **Automatisk attach till cylinder (utsida eller hål):**
  - Klicka på mantelytan på en cylinder eller insidan av ett cylindriskt hål för att automatiskt fästa gängan eller coilen.
  - Omacad analyserar automatiskt geometrin och fyller i cylinderns mittaxel, diameter och längd.
  - Normalanalys känner av om du klickat på **utsidan** (Male / yttergänga) och ställer in `Join`, eller **insidan** (Female / innergänga) och ställer in `Cut`.
- **Rundad coil-profil (*Round / Circular Coil*):**
  - Lagt till profilen "Round / Circular Coil" för fjädrar, rundgängor, rörcoils och runda spiralspår med jämn och vattentät geometri samt konsekvent triangelorientering.

## 0.7.7 - 2026-10-14

### Added
- **3D-Print-optimerat gäng- och coilverktyg (*Thread / Coil*):**
  - **45° Trapezoidal-profil:** Eliminerar branta överhäng som säckar ihop i FDM-print. Kan skrivas rent oavsett munstycksstorlek eller lagerhöjd utan supportmaterial. (ISO 60° metrisk profil finns som valbart alternativ).
  - **Automatisk 3D-print tolerans/frigång (*Fit Clearance*):** Justerbar toleranskompensation (0.10–0.40 mm, standard 0.25 mm) anpassad för 0.4 mm munstycken så att bultar och muttrar inte nyper fast.
  - **Smooth Lead-in & Runout Taper:** Mjuk övergång och infasning under gängans första och sista varv för att förhindra snedgängning (cross-threading) och göra det enkelt att starta skruven.
  - **Snabbval / Presets:** Förinställda gängstandarder anpassade för 3D-print med lite grövre stigning (M6x1.25, M8x1.5, M10x2.0, M12x2.0, M16x2.5, M20x2.5, M24x3.0, M30x3.5) samt helt valfria anpassade dimensioner.
  - **Ytter- och innergänga:** Skapa antingen fristående bultar/kärnor eller applicera direkt på befintlig cylinder/hål i modellen (Join / Cut) med live 3D-förhandsgranskning.
  - **Full integration:** Registreras i parametriska tidslinjen (`ThreadFeature`), fullt redigerbar med dubbelklick och serialiseras i `.omacad`-filer.
  - **Ikoner för alla tre teman:** Nya handgjorda SVG-vektorikoner för *Modern Solid Fill*, *Technical Blueprint* och *Semantic Color-Coded CAD*.

## 0.7.6.4 - 2026-10-14

### Fixed
- The rotation gizmo rings crashed `paintGL` (a polyline was passed where line segments are expected); they are now drawn as segment pairs.
- Technical Blueprint icons for Offset Plane, Canvas, Parameters, Polygon, Rectangle and Slot were blank: the SVGs had duplicate `stroke` attributes and would not parse. `tests/test_icon_svgs.py` checks that every icon is valid XML.

## 0.7.6.3 - 2026-10-14

### Added
- **Combine: Behåll verktygskroppar (*Keep tool bodies*):**
  - Lagt till kryssrutan "Keep tool bodies" i Combine-dialogen (Fusion 360-stil). När denna är ikryssad förbrukas inte verktygskroppen (`tool body`) utan behålls i modellen efter Cut/Join/Intersect.
- **Interaktivt 3D-klick för att välja bodies i sidopanelens dialoger:**
  - När verktyg som **Combine**, **Split Body**, **Move / Rotate**, **Shell** eller **Pattern / Mirror** är öppna kan du nu klicka direkt på önskad solid i 3D-vyn för att välja eller ändra aktiv body i listorna till höger.

## 0.7.6.2 - 2026-10-14

### Improved
- **Tydlig styling och synlighet för rullgardinsmenyer (QComboBox):**
  - Rullgardinsrutor har nu en distinkt knappram med kontrastrik bakgrund (`#2D3138`), tydliga gränslinjer och en markerad drop-down-knapp med pil (`QComboBox::down-arrow`).
  - Förbättrad hover- och focus-återkoppling med CAD-accentfärg när menyn är aktiv.
  - Optimerade och förtydligade etiketter i dialoger (t.ex. Pattern/Mirror och Move) så att texter inte klipps eller försvinner bakom pilen.
  - Utökad bredd i sidopanelen till 380px (dialoger 358px) så att alla rullgardinsmenyer och etiketter ryms luftigt utan textavklippning.

## 0.7.6.1 - 2026-10-14

### Added
- **Fusion 360-stil på 3D Body Rotation Gizmo:**
  - Utökat Move-gizmon med 3 färgkodade cirkulära rotationsringar runt X (röd), Y (grön) och Z (blå).
  - Interaktiv vinkelrotering genom att klicka och dra direkt i ringarna med ren 5°/1° snäppning och direkt koppling till `rx`, `ry`, `rz`.
  - Uppdaterat Move / Rotate Body dialogen med aktiva knappar för både translationsaxlar (X, Y, Z) och rotationsaxlar (Rx, Ry, Rz).
- **Rotation av sketchelement:**
  - Implementerat `rotate_entity` och vinkelstöd i Move-verktyget för markerade sketchelement runt elementens geometriska mittpunkt / pivot.
  - Dynamisk inmatning (Tab) stöder nu `X`, `Y` och `Angle` för precis flytt och rotation av skisser.

### Fixed
- **Riktning på Fillet och Chamfer hjälppilar:**
  - Hjälppilen för fasning och avrundning pekar nu korrekt inåt mot materialet/avfasningen längs hörnbisektrisen (`d1 + d2` inåt mot kroppen på konvexa kanter) precis som i Fusion 360, istället för rakt ut i tomma luften.

## 0.7.6 - 2026-10-14

### Added
- **Tre teman och konsoliderad Theme-flik:** Lagt till tre tydliga lägen i Inställningar under en samlad flik "Theme":
  1. *Follow Omarchy system theme*
  2. *Light Mode: Clean Studio Latte*
  3. *Dark Mode: Tokyo Slate / Nord Frost*
  - "Start from" i temaeditorn har renodlats till de tre valda bas-teman.
- **Tre kompletta vektor-ikonteman:**
  - *Modern Solid Fill* (standard med fyllda stilrena former)
  - *Technical Blueprint* (tekniska konturlinjer och CAD-grafik)
  - *Semantic Color-Coded CAD* (färgkodade efter CAD-operationer)
  - Skarp rendering i alla upplösningar med dynamisk färganpassning efter ljust/mörkt tema.
- **Tydligare och taktila knappar i alla teman:**
  - Standardiserat QPushButton och Primary/Success/OK-knappar med förhöjd kontrast, distinkta ramar och bottenkanter för tydlig knappkänsla i både ljusa och mörka teman.
  - Ribbon-knappar har fått en subtil bakgrund och tydliga kantlinjer för ökad synlighet.
- **Flexibel placering av Box och Cylinder (Primitives):**
  - Stöd för att placera undersidan direkt i origo (`bottom_center`), hörn (`corner`), eller solid mittpunkt (`center`).
  - Stöd för placering direkt på godtycklig plan yta (*On face*) med orientering (horisontell/vertikal) och interaktiv val av yta i 3D-vyn samt live preview.

### Improved
- **Dockade verktygsdialoger i högerpanelen:** Verktygsrutor som Box, Cylinder, Fillet, Chamfer m.fl. dockas stabilt i högerpanelen (Inspector) så att de aldrig flyter iväg, försvinner eller skymmer 3D-modellen.

## 0.7.5.1 - 2026-10-14

### Added
- **Parameter auto-complete & parameter sets:** Typing in numeric fields now auto-completes parameter names with matching names and current values. Added "Save Set" and "Load Set" to the Change Parameters dialog to save and reuse parameter sets across projects.

### Fixed
- Extrude cut starting on a planar face no longer leaves an uncut zero-thickness coplanar skin/cap over the opening.
- Straight-edge chamfers and fillets now extend a tiny margin into the empty side of convex edges (just like circular loops already do), eliminating zero-thickness fins ("fnas") left in hole walls and inside polygon corners.

## 0.7.5 - 2026-10-13

### Fixed
- Mirrored/patterned holes left thin zero-thickness fins in their walls (debris after a later fillet): cuts that leave the body are now extended by moving the end-face vertices instead of unioning a shifted copy.

## 0.7.4.9 - 2026-10-13

### Fixed
- Fillet/Chamfer: picking an edge now selects the whole smooth chain (straight sides and tangent arcs), and the preview covers every picked edge instead of failing with "truth value of an array is ambiguous".

## 0.7.4.8 - 2026-10-13

### Fixed
- Sketch mode did not start and the viewport crashed in paintGL: the viewport modularization left the mixins without imports (`math`, `ctypes`, `Qt`, `theme`, sketch classes ...). Added them and a test that checks every module for undefined names.

## 0.7.4 - 2026-10-13

### Fixed
- **Shell: open faces can be picked again.** Clicking a face crashed (missing numpy import), and the hidden target body could not be hit. Shell now only offers the faces of the chosen body and no longer draws the origin planes.

## 0.7.3 - 2026-10-13

### Added
- **Trädstruktur för Bodies och Skisser**: Skisser som skapas på en yta av en viss kropp (eller Face-to-Sketch) grupperas nu automatiskt under den tillhörande kroppen som en utfällbar gren i Model Browser. Fristående skisser på basplan (XY, XZ, YZ) eller konstruktionsplan visas i en egen skiss-gren.
- **3D-markering av bodies med vänsterklick**: Klick på en solid i 3D-viewporten markerar kroppen direkt och sätter den som aktiv för verktyg som Move, Split och Shell. Klick i tomt utrymme avmarkerar.

### Improved
- **Shell live preview & skissrensning**: När Shell-verktyget öppnas döljs förbrukade skisser automatiskt. Ändring av väggtjocklek eller val av öppna ytor ger direkt 3D-förhandsvisning med tydlig färgmarkering på öppna ytor.

## 0.7.2 - 2026-10-13

### Improved
- **Direct typing on Extrude**: when starting Extrude or picking a sketch profile in the 3D viewport, the distance input field is immediately focused with its value selected so you can type the desired distance right away without having to click the text box. Keystrokes in the 3D viewport also automatically forward directly to the distance input.

## 0.7.1 - 2026-10-13

### Added
- **Toolbar button size** (Settings > Toolbar button size): adjust button and icon size in the top ribbon (Compact 75%, Medium 100%, Large 125%, Extra large 150%).
- **Fillet clearance clamping**: 3D fillet/chamfer automatically limits reach on convex straight edges so exaggerated radii do not cut past opposite walls or adjacent boundary edges.

### Fixed
- Dimension badges no longer obscure sketch circles/geometry when dimensioning circle to line.
- Smart circle anchor point fix: editing circle-to-edge distance moves the circle instead of shifting the entire sketch off origin.
- Removed redundant duplicate "BROWSER" inner header label in the left dock panel.

## 0.7.0 - 2026-10-13

### Added
- **Theme editor** (Settings > Theme editor): set every colour by hand (background, dark background, text, muted text, accent, 3D highlight, 3D view background, grid, and the four tool colours), see it live, save it under a name. Saved themes (`~/.config/omacad/themes`) appear with a star in the Theme list and carry their tool colours.
- `skills/omacad-video`: a skill describing how the demo videos are made (frame-exact capture, local narration and music).

### Fixed
- The inside of scroll areas (ribbon background, lists in dialogs) ignored the theme and stayed dark; Qt's own palette now follows the theme.
- Report problem / Request a change: the screenshot was shown too small on scaled (HiDPI) screens, and the dialog could be larger than a small screen so the text box was out of reach. It now fits the screen and the message box is framed and labelled.

## 0.6.34 - 2026-10-13

### Added
- Help > Request a change (F8): send a change request with screenshot and note; it is stored in a private GitHub repo for review. Unsent requests are kept locally and retried at startup.
- Whole UI in English.
- Windows build runs `Omacad.exe --selftest` before publishing.

## 0.6.33 - 2026-10-13

### Added
- **Choose the theme: follow Omarchy or pick one** (Settings > Färger > Tema): "Följ Omarchy-temat (live)" as before, or a fixed theme that Omarchy theme switches no longer change. The Omarchy themes are now bundled with the app (`assets/themes`), so the choice also works on Windows, where "Omacad standard (mörk)" is the default look.
- **Click in empty space to deselect the body** (a click on nothing clears the selection in the browser/inspector).

## 0.6.32 - 2026-10-13

### Changed
- **Smart Circle shows its numbers as dimensions while you type**: after Enter on the diameter, a diameter dimension appears on the circle; after each distance, a dimension line from the wall to the centre with its value. Before, the numbers only appeared once the circle was finished.

## 0.6.31 - 2026-10-12

### Fixed
- **Start-up error on a Windows PC** ("Error calling Python override of QProxyStyle::pixelMetric", repeated down the screen): the big-icon style could raise an error while Qt was drawing, which then repeated forever. It now falls back to the base style and never raises.

## 0.6.30 - 2026-10-12

### Fixed
- **Omacad.exe failed to start on some Windows PCs** ("LoadLibrary: invalid access to memory location"): the exe is no longer UPX-compressed or stripped, which could damage the Qt DLLs. It is larger but starts everywhere. The build also bundles python-solvespace, which was missing.

## 0.6.29 - 2026-10-12

### Fixed
- Pattern / Mirror finds nothing to copy when the hole is part of the extrude that creates the body (the default ticks start at the sketch, so there was no "before" body). It now copies the holes enclosed in the body's outline.

## 0.6.28 - 2026-10-12

### Changed
- **Fill pattern packs polygons of 3 to 8 sides tightly** (Staggered / Triangular layout): the lattice is now searched for the polygon itself, so squares form a square grid, hexagons a honeycomb, octagons their tightest grid, and triangles, pentagons and other odd polygons pair each copy with one turned 180 degrees. The gap between neighbours stays exactly the chosen value. Non-regular convex polygons work too.

## 0.6.27 - 2026-10-12

### Fixed
- **Fill pattern kept too far away from holes and bosses** (via F9): the edge margin was also applied round every hole and boss in the face, so large areas stayed empty. The margin now applies only to the outer edge; holes and bosses get just the gap between copies.

## 0.6.26 - 2026-10-12

### Fixed
- **Changing a rounded rectangle's width did nothing visible** (via F9): the solver moved one wall but left the corner arcs and the neighbouring lines behind. Fillet arcs are now refitted to their lines after every solve.

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
