"""
Omacad - Solid Geometry Kernel
Wraps Manifold3D and Trimesh for watertight CAD operations and mesh extraction.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np
import manifold3d as m3d
import trimesh


@dataclass
class RenderMesh:
    """Holds tessellated data ready for OpenGL rendering."""
    vertices: np.ndarray      # Shape (N, 3), float32 (triangles unrolled)
    normals: np.ndarray       # Shape (N, 3), float32
    sharp_lines: np.ndarray   # Shape (M, 3), float32 (pairs of vertices for lines)
    bounds_min: np.ndarray    # [min_x, min_y, min_z]
    bounds_max: np.ndarray    # [max_x, max_y, max_z]
    center: np.ndarray        # [cx, cy, cz]


class CadKernel:
    """Provides high-level solid modeling operations."""

    @staticmethod
    def create_box(length: float, width: float, height: float, center: bool = False) -> m3d.Manifold:
        """Create a 3D rectangular box/prism."""
        return m3d.Manifold.cube([float(length), float(width), float(height)], center=center)

    @staticmethod
    def create_cylinder(radius: float, height: float, segments: int = 48, center: bool = False) -> m3d.Manifold:
        """Create a cylinder with specified radius and height."""
        cyl = m3d.Manifold.cylinder(float(height), float(radius), float(radius), circular_segments=segments)
        if center:
            mat = np.array([
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, -height / 2.0]
            ], dtype=float)
            cyl = cyl.transform(mat)
        return cyl

    @staticmethod
    def create_sphere(radius: float, segments: int = 36) -> m3d.Manifold:
        """Create a UV sphere."""
        return m3d.Manifold.sphere(float(radius), circular_segments=segments)

    @staticmethod
    def extrude_cross_section(
        polygon_pts: List[Tuple[float, float]], 
        height: float, 
        transform_mat: Optional[np.ndarray] = None
    ) -> m3d.Manifold:
        """
        Extrude a 2D planar polygon along its normal vector.
        polygon_pts: list of (u, v) points forming a closed loop
        height: extrusion distance
        transform_mat: optional 3x4 transform matrix to place the solid in 3D space
        """
        if len(polygon_pts) < 3:
            raise ValueError("Polygon must have at least 3 points")
        
        # Ensure polygon vertices are clean float tuples
        coords = [[float(p[0]), float(p[1])] for p in polygon_pts]
        cs = m3d.CrossSection([coords])
        manifold = m3d.Manifold.extrude(cs, height=float(height))
        
        if transform_mat is not None:
            if transform_mat.shape != (3, 4):
                raise ValueError("Transform matrix must have shape (3, 4)")
            manifold = manifold.transform(transform_mat.astype(float))
            
        return manifold

    @staticmethod
    def revolve_cross_section(
        polygon_pts: List[Tuple[float, float]],
        segments: int = 48,
        transform_mat: Optional[np.ndarray] = None
    ) -> m3d.Manifold:
        """Revolve a 2D planar polygon around the V axis."""
        coords = [[float(p[0]), float(p[1])] for p in polygon_pts]
        cs = m3d.CrossSection([coords])
        manifold = m3d.Manifold.revolve(cs, circular_segments=segments)
        
        if transform_mat is not None:
            manifold = manifold.transform(transform_mat.astype(float))
            
        return manifold

    @staticmethod
    def edge_round_tool(edge, size: float, kind: str, extend=0.0, arc_segments: int = 24) -> m3d.Manifold:
        """The sliver along an edge that a chamfer/fillet removes (convex edge) or fills in (concave).

        Cross-section in the plane across the edge, with the corner at the origin and e1 along face 1:
        chamfer = triangle (corner, A, B); fillet = corner, A, arc towards the corner, B, where A and B
        are the tangent points a distance size/tan(theta/2) along the faces."""
        t = (edge.p1 - edge.p0) / np.linalg.norm(edge.p1 - edge.p0)
        origin = edge.p0.copy()
        ext_start, ext_end = (extend if isinstance(extend, (tuple, list)) else (extend, extend))   # at p0, at p1
        e1 = edge.d1
        e2 = edge.d2 - (edge.d2 @ e1) * e1
        e2 = e2 / np.linalg.norm(e2)
        if np.cross(e1, e2) @ t < 0:      # keep the frame right-handed so the solid isn't inside-out
            t, origin = -t, edge.p1.copy()
            ext_start, ext_end = ext_end, ext_start
        cos_th = float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0))
        theta = math.acos(cos_th)         # angle between the faces, as seen from the edge
        half = theta / 2.0
        if kind == "chamfer":
            s = float(size)
            A = np.array([s, 0.0])
            B = s * np.array([math.cos(theta), math.sin(theta)])
            poly = [(0.0, 0.0), tuple(A), tuple(B)]
        else:
            r = float(size)
            s = r / math.tan(half)
            A = np.array([s, 0.0])
            B = s * np.array([math.cos(theta), math.sin(theta)])
            rc = r / math.sin(half)
            c = rc * np.array([math.cos(half), math.sin(half)])
            pa, pb = math.atan2(A[1] - c[1], A[0] - c[0]), math.atan2(B[1] - c[1], B[0] - c[0])
            sweep = (pb - pa + math.pi) % (2 * math.pi) - math.pi   # the short way round: faces the corner
            arc = [(c[0] + r * math.cos(pa + sweep * k / arc_segments), c[1] + r * math.sin(pa + sweep * k / arc_segments))
                   for k in range(1, arc_segments)]
            poly = [(0.0, 0.0), tuple(A)] + arc + [tuple(B)]
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        if area < 0:
            poly.reverse()
        length = float(np.linalg.norm(edge.p1 - edge.p0)) + ext_start + ext_end
        solid = m3d.Manifold.extrude(m3d.CrossSection([[list(map(float, q)) for q in poly]]), height=length)
        mat = np.column_stack([e1, e2, t, origin - t * ext_start]).astype(float)
        return solid.transform(mat)

    @staticmethod
    def drop_slivers(solid: m3d.Manifold) -> m3d.Manifold:
        """Removes loose, practically volume-less shells that a boolean can leave where two almost-equal
        surfaces (a mirrored copy of a tessellated curve) fail to coincide."""
        try:
            parts = solid.decompose()
        except Exception:
            return solid
        if len(parts) <= 1:
            return solid
        total = max(abs(p.volume()) for p in parts)
        keep = [p for p in parts if abs(p.volume()) > max(1e-5 * total, 1e-3)]
        if len(keep) == len(parts) or not keep:
            return solid
        return m3d.Manifold.compose(keep) if len(keep) > 1 else keep[0]

    @staticmethod
    def round_tool(edge, size: float, kind: str, extend=0.0) -> m3d.Manifold:
        """Tool body for a straight or circular edge."""
        if getattr(edge, "kind", "line") == "circle":
            return CadKernel.circle_round_tool(edge, size, kind)
        if getattr(edge, "kind", "line") == "loop":
            return CadKernel.loop_round_tool(edge, size, kind)
        return CadKernel.edge_round_tool(edge, size, kind, extend)

    @staticmethod
    def loop_round_tool(edge, size: float, kind: str, arc_segments: int = 16) -> m3d.Manifold:
        """Fillet/chamfer all the way round an outline of straight pieces and arcs: the usual corner
        cross-section swept along the outline (mitred where the direction changes)."""
        P = np.asarray(edge.pts, dtype=float)
        n = np.asarray(edge.n, dtype=float)
        N = len(P)
        r = float(size)
        t = np.roll(P, -1, axis=0) - P                      # segment i goes from point i to point i+1
        t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
        inw = np.cross(n, t)                                # into the face (it lies on the left)
        prev = np.roll(inw, 1, axis=0)                      # inward normal of the segment ending at point i
        miter = (prev + inw) / (1.0 + np.einsum("ij,ij->i", prev, inw))[:, None]   # length 1/cos(half turn)
        # when the inner outline folds over itself (radius larger than the corner arcs) the tube would
        # intersect itself; then the section is swept piece by piece and the pieces are merged
        inner = P + r * miter
        d_in = np.roll(inner, -1, axis=0) - inner
        folded = bool((np.einsum("ij,ij->i", d_in, t) <= 1e-9).any())
        m = 0.05 * r + 1e-3
        convex = bool(getattr(edge, "convex", True))
        if convex:
            if kind == "chamfer":
                sec = [(-m, m), (r, m), (r, 0.0), (0.0, -r), (-m, -r)]
            else:
                arc = [(r + r * math.cos(ph), -r + r * math.sin(ph))
                       for ph in np.linspace(math.pi / 2, math.pi, arc_segments + 1)]
                sec = [(-m, m), (r, m)] + arc + [(-m, -r)]
        else:
            # the foot of a wall rising from the face: material is ADDED in the corner between face and wall
            # (a = along the face away from the wall, h = up the wall); the margin overlaps the existing material
            if kind == "chamfer":
                sec = [(-m, -m), (r, -m), (r, 0.0), (0.0, r), (-m, r)]
            else:
                arc = [(r - r * math.cos(b), r - r * math.sin(b)) for b in np.linspace(math.pi / 2, 0.0, arc_segments + 1)]
                sec = [(-m, -m), (r, -m)] + arc + [(-m, r)]
        if folded:
            return CadKernel._loop_tool_pieces(P, n, t, inw, sec)
        M = len(sec)
        verts = np.array([P[i] + a * miter[i] + h * n for i in range(N) for a, h in sec], dtype=np.float64)
        tris = []
        for i in range(N):
            j = (i + 1) % N
            for k in range(M):
                k2 = (k + 1) % M
                a, b, c, d = i * M + k, j * M + k, j * M + k2, i * M + k2
                tris += [[a, b, c], [a, c, d]]
        # end caps are not needed: the tube is closed around the loop. Fix orientation by the signed volume.
        tr = np.array(tris, dtype=np.uint32)
        vol = np.einsum("ij,ij->i", verts[tr[:, 0]], np.cross(verts[tr[:, 1]], verts[tr[:, 2]])).sum() / 6.0
        if vol < 0:
            tr = tr[:, ::-1]
        mesh = m3d.Mesh(vert_properties=verts.astype(np.float32), tri_verts=np.ascontiguousarray(tr))
        solid = m3d.Manifold(mesh)
        if solid.is_empty():
            raise ValueError("Could not build the rounding for this outline.")
        return solid

    @staticmethod
    def foot_fill_tool(body: m3d.Manifold, edge, size: float, kind: str) -> m3d.Manifold:
        """Filling tool for the foot of a wall (a LoopEdge with convex=False). The fillet lies on the face next to
        the wall, so it needs flat face under it. Where an earlier rounding has already cut that face away (a
        shelf narrower than the radius) the tool would hang over the cut like a lip; the radius is then reduced
        to the widest one that still rests on the face, so the fillet runs out smoothly into the other rounding."""
        n = np.asarray(edge.n, dtype=float)
        u = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
        u /= np.linalg.norm(u)
        basis = np.column_stack([u, np.cross(n, u), n])
        below = m3d.Manifold.cube((1e5, 1e5, 1e5), True).transform(
            np.column_stack([basis, np.asarray(edge.pts[0], dtype=float) - n * 5e4]))   # everything under the face plane

        def hangs(tool) -> bool:
            return ((tool ^ below) - body).volume() > 1e-6 * max(float(size), 1.0) ** 3

        tool = CadKernel.loop_round_tool(edge, size, kind)
        if not hangs(tool):
            return tool
        lo, hi = 0.0, float(size)
        for _ in range(12):
            mid = (lo + hi) / 2.0
            if hangs(CadKernel.loop_round_tool(edge, mid, kind)):
                hi = mid
            else:
                lo = mid
        return CadKernel.loop_round_tool(edge, lo, kind) if lo > 1e-3 else m3d.Manifold()

    @staticmethod
    def _loop_tool_pieces(P, n, t, inw, sec) -> m3d.Manifold:
        """The corner cross-section extruded along every straight piece of the outline (arcs are many short
        pieces), merged. Where the radius is larger than a corner arc the pieces overlap and cut a dome."""
        N = len(P)
        # join consecutive pieces that run in the same direction
        starts = [i for i in range(N) if float(t[i] @ t[i - 1]) < 1.0 - 1e-9]
        if not starts:
            starts = [0]
        poly = [list(map(float, q)) for q in sec]
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
        if area < 0:
            poly.reverse()
        cs = m3d.CrossSection([poly])
        pieces = []
        for k, i0 in enumerate(starts):
            i1 = starts[(k + 1) % len(starts)]
            idx = i0
            length = 0.0
            while True:
                length += float(np.linalg.norm(P[(idx + 1) % N] - P[idx]))
                idx = (idx + 1) % N
                if idx == i1:
                    break
            if length < 1e-9:
                continue
            solid = m3d.Manifold.extrude(cs, height=length)
            mat = np.column_stack([inw[i0], n, t[i0], P[i0]]).astype(float)
            pieces.append(solid.transform(mat))
        result = m3d.Manifold.batch_boolean(pieces, m3d.OpType.Add)
        if result.is_empty():
            raise ValueError("Could not build the rounding for this outline.")
        return result

    @staticmethod
    def circle_round_tool(edge, size: float, kind: str, arc_segments: int = 24) -> m3d.Manifold:
        """Same cross-section as a straight edge (a right angle between the flat face and the cylinder
        wall) revolved around the circle's axis."""
        R = float(edge.radius)
        # The wall of the original solid is a polygon whose chords sag inside the radius; a tool that
        # only reached R would leave a hair-thin lip along the old edge (visible as a leftover line).
        # So the tool also covers a margin on the empty side of the corner (harmless for a union too:
        # there it overlaps existing material).
        sag = R * (1.0 - math.cos(math.pi / max(int(getattr(edge, "nseg", 48)), 6)))
        m = 2.0 * sag + 1e-3 * max(1.0, R)
        if kind == "chamfer":
            s = float(size)
            local = [(-m, -m), (s, -m), (s, 0.0), (0.0, s), (-m, s)]
        else:
            r = float(size)
            # tangent points A=(r,0) on the face and B=(0,r) on the wall; the arc is centred at (r,r)
            # and bulges towards the corner. Walk it from A to B (interior points only).
            arc = []
            for k in range(1, arc_segments):
                beta = (math.pi / 2) * (1.0 - k / arc_segments)
                arc.append((r - r * math.cos(beta), r - r * math.sin(beta)))
            local = [(-m, -m), (r, -m), (r, 0.0)] + arc + [(0.0, r), (-m, r)]
        # local x runs along the face (away from the edge), local y along the wall (away from the face)
        poly = [(R + edge.s1 * x, edge.s2 * y) for x, y in local]
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        if area < 0:
            poly.reverse()
        cs = m3d.CrossSection([[list(map(float, q)) for q in poly]])
        if min(q[0] for q in poly) < 0:   # a round bigger than the radius: keep the part beside the axis
            half = m3d.CrossSection([[(0.0, -1e6), (1e6, -1e6), (1e6, 1e6), (0.0, 1e6)]])
            cs = cs ^ half
        if cs.is_empty():
            return m3d.Manifold()
        solid = m3d.Manifold.revolve(cs, circular_segments=max(int(getattr(edge, "nseg", 48)), 12))   # same segment count as the wall so vertices line up
        u, v = edge._basis()
        mat = np.column_stack([u, v, edge.axis, edge.center]).astype(float)
        return solid.transform(mat)

    @staticmethod
    def boolean_union(a: m3d.Manifold, b: m3d.Manifold) -> m3d.Manifold:
        """Boolean Join (A ∪ B)"""
        return a + b

    @staticmethod
    def boolean_difference(target: m3d.Manifold, tool: m3d.Manifold) -> m3d.Manifold:
        r"""Boolean Cut (Target \ Tool)"""
        return target - tool

    @staticmethod
    def boolean_intersection(a: m3d.Manifold, b: m3d.Manifold) -> m3d.Manifold:
        """Boolean Intersect (A ∩ B)"""
        return a ^ b

    @staticmethod
    def extract_render_mesh(manifold: m3d.Manifold, edge_angle_threshold_deg: float = 20.0) -> RenderMesh:
        """
        Extract triangle buffers and sharp CAD feature edges for OpenGL rendering.
        """
        mesh = manifold.to_mesh()
        v = mesh.vert_properties[:, :3]
        f = mesh.tri_verts

        if len(f) == 0:
            empty = np.zeros((0, 3), dtype=np.float32)
            return RenderMesh(
                vertices=empty,
                normals=empty,
                sharp_lines=empty,
                bounds_min=np.zeros(3, dtype=np.float32),
                bounds_max=np.zeros(3, dtype=np.float32),
                center=np.zeros(3, dtype=np.float32)
            )

        # Flat shaded vertices per triangle for crisp CAD rendering
        tri_verts = v[f].reshape(-1, 3).astype(np.float32)

        # Compute face normals
        v0 = v[f[:, 0]]
        v1 = v[f[:, 1]]
        v2 = v[f[:, 2]]
        cross_prod = np.cross(v1 - v0, v2 - v0)
        lengths = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        face_normals = cross_prod / lengths
        tri_normals = np.repeat(face_normals, 3, axis=0).astype(np.float32)

        # Extract sharp CAD edges using trimesh
        try:
            tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
            rad_thresh = np.radians(edge_angle_threshold_deg)
            sharp_mask = tm.face_adjacency_angles > rad_thresh
            # booleans on tessellated curves leave zero-area triangles whose normals are meaningless:
            # they would show up as stray "sharp" lines across smooth surfaces
            diag = float(np.linalg.norm(np.ptp(v, axis=0))) or 1.0
            areas = tm.area_faces
            fa = tm.face_adjacency
            sharp_mask &= (areas[fa[:, 0]] > 1e-7 * diag * diag) & (areas[fa[:, 1]] > 1e-7 * diag * diag)
            sharp_edges = tm.face_adjacency_edges[sharp_mask]
            
            # Also include single-face boundary edges (if open mesh)
            if len(tm.faces) > 0 and len(tm.face_adjacency) < len(tm.edges_unique):
                boundary_edges = tm.edges_unique[tm.edges_unique_inverse != 2] if hasattr(tm, 'edges_unique_inverse') else []
                if len(boundary_edges) > 0:
                    sharp_edges = np.vstack([sharp_edges, boundary_edges])

            if len(sharp_edges) > 0:
                sharp_lines = v[sharp_edges].reshape(-1, 3).astype(np.float32)
            else:
                sharp_lines = np.zeros((0, 3), dtype=np.float32)
        except Exception:
            sharp_lines = np.zeros((0, 3), dtype=np.float32)

        b_min = np.min(v, axis=0).astype(np.float32)
        b_max = np.max(v, axis=0).astype(np.float32)
        center = ((b_min + b_max) * 0.5).astype(np.float32)

        return RenderMesh(
            vertices=tri_verts,
            normals=tri_normals,
            sharp_lines=sharp_lines,
            bounds_min=b_min,
            bounds_max=b_max,
            center=center
        )
