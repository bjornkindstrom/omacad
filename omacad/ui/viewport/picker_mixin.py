"""Selection and picking mixin for Viewport3D: bodies, edges, planes, surfaces."""

from typing import Optional, List, Tuple
import math
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from OpenGL import GL
import omacad.ui.viewport as _vp_pkg
from omacad.ui import theme
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect
from omacad.model.faces import ray_hit_face, tangent_chain


class PickerMixin:
    """Mixin providing body, edge, and plane picking operations for Viewport3D."""
    def pick_body(self, x: float, y: float) -> Optional[str]:
        """Returns the body_id of the nearest 3D solid body under the cursor."""
        from omacad.model.faces import ray_mesh_hit
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best_t, best_id = float("inf"), None
        for bid, body in self.doc.bodies.items():
            mesh = body.render_mesh
            if mesh is not None and len(mesh.vertices) > 0:
                hit = ray_mesh_hit(mesh, origin, ray_dir)
                if hit is not None and hit[0] < best_t:
                    best_t = hit[0]
                    best_id = bid
            for face in getattr(body, "faces", []):
                t = ray_hit_face(face, origin, ray_dir)
                if t is not None and t < best_t:
                    best_t = t
                    best_id = bid
        return best_id

    # ---- Edge selection (fillet / chamfer) ------------------------------------------
    def begin_edge_pick(self):
        self.edge_pick_mode = True
        self.edge_xray = False
        self.hover_edge = None
        self.selected_edges = []
        self.setFocus()
        self.update()

    def end_edge_pick(self, cancelled: bool = False):
        self.edge_pick_mode = False
        self.hover_edge = None
        self.selected_edges = []
        if cancelled:
            self.edge_pick_cancelled.emit()
        self.update()

    @staticmethod
    def _same_edge(a, b) -> bool:
        return a.same_as(b)

    def _pick_edge(self, x: float, y: float):
        """The straight edge between two flat faces nearest the cursor (within 8 px, and not hidden)."""
        proj, view, _ = self.get_matrices()
        origin, _ = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        xray = self.edge_xray or bool(QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        best, best_d, best_eye = None, 8.0, 1e18
        for body in self.doc.bodies.values():
            if not body.visible:
                continue
            for e in body.edges:
                pts = e.polyline()
                screen = [self.world_to_screen(p) for p in pts]
                d, near = best_d, None
                for i in range(len(screen) - 1):
                    if screen[i] is None or screen[i + 1] is None:
                        continue
                    dd = self._point_to_segment_dist((x, y), screen[i], screen[i + 1])
                    if dd < d:
                        d, near = dd, i
                if near is None:
                    continue
                # hidden behind a face? test the point of the edge nearest the cursor
                mid = (pts[near] + pts[near + 1]) / 2.0
                direction = mid - origin
                dist = float(np.linalg.norm(direction))
                direction = direction / dist if dist > 1e-9 else direction
                blocked = (not xray) and any((t := ray_hit_face(f, origin, direction)) is not None and t < dist - 1e-3
                                             for bd in self.doc.bodies.values() if bd.visible for f in bd.faces)
                if not blocked and (d < best_d - 1.0 or (d <= best_d + 1.0 and dist < best_eye)):
                    best, best_d, best_eye = e, min(d, best_d), dist   # near-ties (edges on top of each other): the closer one
        return best

    def _edge_loop(self, e, other_face: bool = False):
        """Double-click: the edges joined end to end around one flat face (e.g. the whole top of a box).
        Of the two faces an edge borders, the one facing the camera is used."""
        if e.kind in ("circle", "loop"):
            return [e]
        proj, view, _ = self.get_matrices()
        eye = np.linalg.inv(view)[:3, 3]
        mid = (e.p0 + e.p1) / 2.0
        to_eye = eye - mid
        n = e.n1 if float(e.n1 @ to_eye) >= float(e.n2 @ to_eye) else e.n2
        if other_face:   # Shift: the face on the other side of the edge (e.g. the riser instead of the tread)
            n = e.n2 if n is e.n1 else e.n1
        d = float(n @ e.p0)
        candidates = [c for b in self.doc.bodies.values() if b.visible for c in b.edges if c.kind == "line"
                      and abs(float(n @ c.p0) - d) < 1e-4 and abs(float(n @ c.p1) - d) < 1e-4]
        chain, frontier = [e], [e]
        while frontier:
            cur = frontier.pop()
            for c in candidates:
                if any(c.same_as(k) for k in chain):
                    continue
                if any(np.linalg.norm(a - b) < 1e-4 for a in (cur.p0, cur.p1) for b in (c.p0, c.p1)):
                    chain.append(c)
                    frontier.append(c)
        return chain

    def _update_edge_hover(self, x: float, y: float):
        e = self._pick_edge(x, y)
        if (e is None) != (self.hover_edge is None) or (e is not None and not self._same_edge(e, self.hover_edge)):
            self.hover_edge = e
            self.update()

    def _visible_edges(self):
        return [c for b in self.doc.bodies.values() if b.visible for c in b.edges]

    def _toggle_edge(self, e):
        """Click: the edge and everything joined to it smoothly is added, or removed if `e` is already picked."""
        chain = tangent_chain(e, self._visible_edges())
        if any(self._same_edge(sel, e) for sel in self.selected_edges):
            self.selected_edges = [s for s in self.selected_edges if not any(self._same_edge(s, c) for c in chain)]
        else:
            self.selected_edges += [c for c in chain if not any(self._same_edge(c, s) for s in self.selected_edges)]
        self.edges_selection_changed.emit()
        self.update()

    def render_edge_pick(self, mvp: np.ndarray):
        if not self.edge_pick_mode or self.prog_thick is None:
            return
        GL.glDisable(GL.GL_DEPTH_TEST)
        def flat(edges):
            out = []
            for e in edges:
                pts = e.polyline()
                for i in range(len(pts) - 1):
                    out += [*pts[i], *pts[i + 1]]
            return out

        if self.edge_xray:   # every pickable edge, also the hidden ones
            self.draw_thick_lines(mvp, flat([e for b in self.doc.bodies.values() if b.visible for e in b.edges]), (0.75, 0.8, 0.9, 0.55), 1.6)
        if self.hover_edge is not None and not any(self._same_edge(self.hover_edge, s) for s in self.selected_edges):
            self.draw_thick_lines(mvp, flat([self.hover_edge]), (1.0, 1.0, 1.0, 1.0), 3.5)
        if self.selected_edges:
            self.draw_thick_lines(mvp, flat(self.selected_edges), (*theme.palette().highlight01(), 1.0), 4.0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    # ---- Sketch element selection --------------------------------------------

    def begin_plane_pick(self, purpose: str = "sketch"):
        self.plane_pick_purpose = purpose
        self.plane_pick_mode = True
        self.hover_plane = None
        self.setFocus()
        self.update()

    def end_plane_pick(self, cancelled: bool = False):
        self.plane_pick_mode = False
        self.hover_plane = None
        self.highlighted_faces = []
        if cancelled:
            self.plane_pick_cancelled.emit()
        self.plane_pick_purpose = "sketch"
        self.update()

    def _origin_plane_half_size(self) -> float:
        ext = 30.0
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh is not None and len(b.render_mesh.vertices):
                ext = max(ext, float(np.abs(b.render_mesh.bounds_min).max()) * 1.2,
                          float(np.abs(b.render_mesh.bounds_max).max()) * 1.2)
        return ext

    def _pick_plane_target(self, x: float, y: float):
        """Nearest origin plane (within its drawn quad) or planar body face under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = _vp_pkg.ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_t = None, float("inf")
        half = self._origin_plane_half_size()
        candidates = [(("origin", n), pl) for n, pl in self.doc.origin_planes.items()]
        only_origin = self.plane_pick_mode and self.plane_pick_purpose == "offset_origin_only"
        shell_pick = self.plane_pick_mode and self.plane_pick_purpose == "shell_face"
        if shell_pick:
            candidates = []
        elif not only_origin:
            candidates += [(("cplane", pid), self.doc.construction_plane(pid))
                           for pid, c in self.doc.construction_planes.items() if c.get("visible", True)]
        for key, plane in candidates:
            hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
            if hit is None:
                continue
            u, v = plane.world_to_uv(hit)
            t = float(np.linalg.norm(hit - origin))
            if abs(u) <= half and abs(v) <= half and t < best_t:
                best, best_t = key, t
        # Body faces take priority over origin planes (a plane passing through a body
        # would otherwise hide the faces behind it)
        face_best, face_t = None, float("inf")
        for body in ([] if only_origin else self.doc.bodies.values()):
            if shell_pick:   # the shelled body is hidden behind its preview; only its faces count
                if body.body_id != self.shell_target_body_id:
                    continue
            elif not body.visible:
                continue
            for face in body.faces:
                t = ray_hit_face(face, origin, ray_dir)
                if t is not None and t < face_t:
                    face_best, face_t = ("face", face), t
        if face_best is not None:
            return face_best
        return best

    def _update_plane_hover(self, x: float, y: float):
        hover = self._pick_plane_target(x, y)

        def key(h):
            return None if h is None else (h[0], h[1] if h[0] in ("origin", "cplane") else (h[1].body_id, h[1].index))
        if key(hover) != key(self.hover_plane):
            self.hover_plane = hover
            self.update()

    def set_preview_plane(self, plane):
        self.preview_plane = plane
        self.update()

    def _pick_cylinder_surface(self, x: float, y: float) -> Optional[dict]:
        """Detect if clicked/hovered surface is a cylindrical face (bolt or hole) or return hit info."""
        from omacad.model.faces import ray_mesh_hit, detect_cylinder_surface
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], body.body_id, mesh, hit[1])
        if best is None:
            return None
        t, body_id, mesh, tri = best
        cyl_info = detect_cylinder_surface(mesh, tri)
        if cyl_info is not None:
            cyl_info["body_id"] = body_id
            return cyl_info
        return None

    def _pick_surface(self, x: float, y: float):
        """Any body surface under the cursor (curved ones too): the hit point and its smooth patch of vertices."""
        from omacad.model.faces import ray_mesh_hit, smooth_patch_vertices
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], mesh, hit[1])
        if best is None:
            return None
        t, mesh, tri = best
        return {"point": np.asarray(origin, dtype=float) + t * np.asarray(ray_dir, dtype=float),
                "patch": smooth_patch_vertices(mesh, tri)}

    def plane_from_target(self, target):
        from omacad.model.sketch import SketchPlane
        kind, payload = target
        if kind == "origin":
            return SketchPlane.create_named(payload)
        if kind == "cplane":
            return self.doc.construction_plane(payload)
        p = SketchPlane.from_face(payload.normal, payload.origin).centered_on(payload.tris)
        p.face = payload
        return p

    def render_plane_pick(self, mvp: np.ndarray):
        """Translucent origin-plane quads and hovered face while choosing a sketch plane."""
        cplanes = [(pid, self.doc.construction_plane(pid)) for pid, c in self.doc.construction_planes.items() if c.get("visible", True)]
        if self.plane_pick_mode and self.plane_pick_purpose in ("offset_surface", "shell_face"):
            cplanes = []
        if (not self.plane_pick_mode and self.ctx_face is None and not cplanes and self.preview_plane is None) or not self.prog_flat:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        half = self._origin_plane_half_size()
        base = {"XY": (0.30, 0.55, 1.0), "XZ": (0.35, 0.85, 0.40), "YZ": (1.0, 0.40, 0.35)}
        for name, plane in (self.doc.origin_planes.items() if self.plane_pick_mode and self.plane_pick_purpose not in ("offset_surface", "shell_face") else ()):
            hovered = self.hover_plane == ("origin", name)
            corners = [plane.uv_to_world(-half, -half), plane.uv_to_world(half, -half),
                       plane.uv_to_world(half, half), plane.uv_to_world(-half, half)]
            quad = np.array([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]], dtype=np.float32)
            r, g, b = base[name]
            GL.glUniform4f(loc_col, r, g, b, 0.45 if hovered else 0.14)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, quad)
            outline = np.array([c for i in range(4) for c in (corners[i], corners[(i + 1) % 4])], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.9 if hovered else 0.5)
            self.set_line_width(1.5)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        extra = [(("cplane", pid), pl, (0.75, 0.55, 0.95)) for pid, pl in cplanes]
        if self.preview_plane is not None:
            extra.append((None, self.preview_plane, (1.0, 0.65, 0.2)))
        for key, plane, (r, g, b) in extra:
            hovered = key is not None and self.plane_pick_mode and self.hover_plane == key
            strong = hovered or key is None
            corners = [plane.uv_to_world(-half, -half), plane.uv_to_world(half, -half),
                       plane.uv_to_world(half, half), plane.uv_to_world(-half, half)]
            quad = np.array([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.40 if hovered else (0.25 if key is None else 0.10))
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, quad)
            outline = np.array([c for i in range(4) for c in (corners[i], corners[(i + 1) % 4])], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.95 if strong else 0.55)
            self.set_line_width(1.5)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        shown = self.hover_plane if self.plane_pick_mode else (("face", self.ctx_face) if self.ctx_face is not None else None)
        if shown and shown[0] == "face":
            face = shown[1]
            lift = face.normal * 0.05  # avoid z-fighting with the body surface
            tris = (face.tris + lift).reshape(-1, 3).astype(np.float32)
            GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 0.55)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        for hf in self.highlighted_faces:
            face = getattr(hf, "face", hf) if not isinstance(hf, dict) else None
            if face is not None and hasattr(face, "tris"):
                lift = face.normal * 0.05
                tris = (face.tris + lift).reshape(-1, 3).astype(np.float32)
                GL.glUniform4f(loc_col, 0.95, 0.35, 0.25, 0.6)  # warm red/coral for open faces
                self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def align_to_plane(self, plane):
        """Orbits the camera so it looks straight at the given sketch plane."""
        n = np.asarray(plane.normal, dtype=np.float64)
        el = math.degrees(math.asin(max(-1.0, min(1.0, float(n[2])))))
        if abs(n[2]) > 0.999:
            self.azimuth = 0.0
            self.elevation = 89.9 if n[2] > 0 else -89.9
        else:
            self.azimuth = math.degrees(math.atan2(n[0], -n[1])) % 360.0
            self.elevation = el
        self.update()

    def look_at_active_plane(self):
        """Aligns camera orthogonally to current active sketch plane."""
        if self.doc.active_sketch:
            self.align_to_plane(self.doc.active_sketch.plane)

    def toggle_construction_mode(self):
        """Toggles construction geometry creation mode (X key)."""
        self.construction_mode = not self.construction_mode
        self.construction_mode_changed.emit(self.construction_mode)
        self.update()

    def world_to_screen(self, world_pt: np.ndarray) -> Optional[Tuple[float, float]]:
        """Projects a 3D point in world space to 2D screen viewport coordinates."""
        proj, view, _ = self.get_matrices()
        pv = proj @ view
        p4 = np.array([world_pt[0], world_pt[1], world_pt[2], 1.0], dtype=np.float32)
        clip = pv @ p4
        if clip[3] <= 0.001:
            return None
        ndc_x = clip[0] / clip[3]
        ndc_y = clip[1] / clip[3]
        sx = (ndc_x + 1.0) * 0.5 * float(self.width())
        sy = (1.0 - ndc_y) * 0.5 * float(self.height())
        return sx, sy

