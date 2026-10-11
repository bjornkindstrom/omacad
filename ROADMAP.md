# Omacad – progress and roadmap

Native parametric 3D CAD for Omarchy (Hyprland/Wayland). Python 3.14, PySide6 + OpenGL, manifold3d, shapely, SolveSpace.
This file lists what has been built, step by step, and what is left. (Swedish feature overview: `README.md`.)

## Done

### 1. Foundation
- Fusion-style UI: ribbon (SOLID / SKETCH), browser tree, timeline bar, ViewCube, OpenGL canvas with edge lines, themed from the active Omarchy theme and font.
- Primitives (box, cylinder, sphere), Combine (join / cut / intersect), STL/OBJ export, `.omacad` project files (JSON, atomic save).

### 2. Sketching
- Sketch on origin planes, on any flat body face (right-click → *Create Sketch on this Face*) and on offset planes.
- Tools: line, 2-point rect, centre rect, circle, 3-point arc, slot, **regular polygon** (`P`, side count + side length, stays regular).
- Snapping to points, midpoints, grid and all body face edges. Tab-entry of dimensions while drawing; Enter/Esc behaviour like Fusion.
- Select / move / delete, undo / redo for sketch changes, sketch visibility (eye), rename (F2).
- Constraints via SolveSpace: horizontal, vertical, parallel, perpendicular, equal, tangent, concentric, coincident, fixed, point-on-circle.
- Dimensions as real constraints: length, distance (H/V/aligned), point-to-line, angle, diameter; guided right-click menus; measuring from circle/polygon centres; formulas and named parameters in every field.
- **Offset (`O`)** of sketch elements with live preview. **Measure (`I`)** for lines, circles and body edges (length, distance, angle).
- **Fillet (`F`)**: Runda hörn mellan linjer i skisser med tangentbågar och parametriska radie-mått, fullt integrerat med profilupplösning och 3D-extrudering.

### 3. Solids
- **Extrude**: draggable arrow *and* typed value, one side / symmetric / two sides, *To face…*, Auto / New / Join / Cut / Intersect, live preview, manual profile selection (Shift+click to add/remove; nothing auto-picked), extrude a whole face. Profiles with holes now extrude correctly.
- **Fillet / Chamfer**: straight edges, full circles (screw holes, countersinks), whole outlines with rounded corners (also radii larger than the corners), inside and outside corners, double-click selects a loop, live preview.
- **Pattern / Mirror**: linear, mirror (auto: corners / round bodies along the diameter with N evenly spaced copies), circular, and **Fill the face** (fixed gap, edge margin / frame, grid or honeycomb, partial copies cut at the frame, avoids bosses and other features on the face), all with live preview.
- **Offset Plane** (pick XY/XZ/YZ, then any surface incl. cylinders), **Section View** (draggable offset, saved in the tree, toggled with the eye).

### 4. Parametric history
- Timeline editing (click a step to change it, roll back, suppress), parameters with formulas, automatic hiding of used sketches, delete/suppress with downstream rebuild.
- Robustness: sliver clean-up after booleans, zero-area triangle handling in the renderer.

### 5. UX
- All tool dialogs dock in a right-hand panel so the model is never covered.
- Context menus on faces, sketch elements, tree items; icons enlarged; themed with Omarchy.
- **Settings (`Ctrl+,`)**: Persistent inställningar i `~/.config/omacad/settings.json`. Konfigurerbara färger för 3D-extrude pilar, mätverktyg (I), aktiva sketchlinjer, konstruktionslinjer, highlight, inverterat mushjul, standard-radie för fillets samt placering och autogömning av sketch-paletten.

### 6. Project and web
- Private repo `bjornkindstrom/omacad`; screenshots in `screenshots/`.
- Project page on kindstrom.duckdns.org (admin in `~/Work/kindstrom-site`).

## Remaining

### Sketching
- Arcs and slots inside the constraint solver (radius/angle dimensions, tangent arcs).
- Trim, rotate, scale, copy, mirror/pattern *inside* a sketch, Project/Include of body edges.
- Dimensions on whole polygons across flats; centred (instead of anchored) fill lattice option.

### Solids
- Revolve (dialog is a stub), Sweep/Loft, Shell, Hole feature with standards, Draft/Taper in Extrude.
- Fillet/Chamfer for cones, partial arcs and variable radius.
- Pattern/face sketches/offset planes associative with the body (today they are absolute).
- Choose target bodies for Join/Cut; multi-body workflows.

### History and files
- Undo/redo for timeline edits and non-sketch changes (today only sketch edits).
- STEP / IGES import and export (OpenCASCADE), assemblies and joints, CAM / G-code.
- Persist more view state (camera, section views are saved; hidden bodies are too).

### Quality
- Automated tests (today verified with scripted GUI runs on the real display).
- Web page: refresh the older screenshots (parameters, history) and add polygon / fill / measure sections.
