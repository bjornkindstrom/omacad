"""
Omacad - Planar face extraction & picking
Groups coplanar triangles of a body into planar faces so sketches can be started on them.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import math
import numpy as np
import manifold3d as m3d
import trimesh


@dataclass
class PlanarFace:
    body_id: str
    index: int
    normal: np.ndarray      # unit outward normal (3,)
    origin: np.ndarray      # a point on the face (3,)
    area: float
    tris: np.ndarray        # (N, 3, 3) world-space triangles for picking/highlighting


def _group_min_width(v, f, tm, tri_ids) -> float:
    """Narrow dimension of a coplanar triangle group (principal-axis extent): thin strips are the
    facets of a tessellated curved surface, a real flat face is wide."""
    pts = v[np.unique(f[np.array(tri_ids)].ravel())]
    c = pts - pts.mean(axis=0)
    if len(c) < 3:
        return 0.0
    w, vecs = np.linalg.eigh(c.T @ c)
    # in-plane principal axes = the two eigenvectors with the largest eigenvalues
    axes = vecs[:, np.argsort(w)[::-1][:2]]
    proj = c @ axes
    ext = proj.max(axis=0) - proj.min(axis=0)
    return float(ext.min())


def _coplanar(a_idx, b_idx, normals, v, f, areas, tol) -> bool:
    """Are two adjacent triangles part of one flat face? Tiny triangles left by boolean operations may
    be a hair off the plane, so they get a looser test."""
    d = float(np.dot(normals[a_idx], normals[b_idx]))
    off = abs(float(np.dot(normals[a_idx], v[f[a_idx, 0]])) - float(np.dot(normals[a_idx], v[f[b_idx, 0]])))
    if d > 1.0 - 1e-9 and off < tol:
        return True
    # float noise in a small triangle's normal (1e-9 off) must not split a face: judge by how far
    # every corner of the neighbour sits from this triangle's plane
    if d > 1.0 - 1e-7:
        n = normals[a_idx]
        if float(np.abs((v[f[b_idx]] - v[f[a_idx, 0]]) @ n).max()) < tol:
            return True
    small = min(areas[a_idx], areas[b_idx]) < 0.01
    return small and d > 1.0 - 1e-4 and off < 1e-3


SLIVER_AREA = 1e-3  # mm^2: boolean operations leave hair-thin triangles; they are not faces


def _sliver_roots(v, f, tm, groups) -> set:
    """Groups that are leftovers of boolean operations: almost no area, or hair-thin (< 0.02 mm wide)."""
    out = set()
    for r, ids in groups.items():
        if float(tm.area_faces[ids].sum()) < SLIVER_AREA or _group_min_width(v, f, tm, ids) < 0.02:
            out.add(r)
    return out


def _curved_roots(v, f, tm, find, groups, adj, angles) -> set:
    """Groups that are strips of a curved surface. A group is curved when it meets a neighbour at a
    shallow angle and is not clearly wider than that neighbour; so a wide flat face next to a fillet
    (also a shallow join) stays planar, while the thin strips of the fillet and of cylinders do not.
    Sliver triangles between two strips are looked through (the strips are neighbours of each other)."""
    sliver = _sliver_roots(v, f, tm, groups)
    shallow = {}
    touching = {}  # every neighbour regardless of angle (needed to look through slivers)
    for (a_idx, b_idx), ang in zip(adj, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb:
            continue
        touching.setdefault(ra, set()).add(rb)
        touching.setdefault(rb, set()).add(ra)
        if ang < np.radians(25.0):
            shallow.setdefault(ra, set()).add(rb)
            shallow.setdefault(rb, set()).add(ra)
    normal_of = {r: tm.face_normals[ids[0]] for r, ids in groups.items()}
    # slivers often come in chains: look through whole clusters of them
    cluster = {r: r for r in sliver}

    def cfind(x):
        while cluster[x] != x:
            cluster[x] = cluster[cluster[x]]
            x = cluster[x]
        return x

    for sl in sliver:
        for n in touching.get(sl, ()):
            if n in sliver and cfind(n) != cfind(sl):
                cluster[cfind(n)] = cfind(sl)
    members: dict = {}
    for sl in sliver:
        members.setdefault(cfind(sl), []).append(sl)
    for cl in members.values():
        real = {x for sl in cl for x in touching.get(sl, ()) if x not in sliver}
        for x in real:
            for y in real:
                if x != y and float(normal_of[x] @ normal_of[y]) > np.cos(np.radians(25.0)):
                    shallow.setdefault(x, set()).add(y)
    width = {}
    curved = set()
    for r, neighbours in shallow.items():
        if r in sliver:
            continue
        width.setdefault(r, _group_min_width(v, f, tm, groups[r]))
        similar = 0
        for n in neighbours:
            if n in sliver:
                continue
            width.setdefault(n, _group_min_width(v, f, tm, groups[n]))
            if width[n] >= width[r] / 4.0:
                similar += 1
        # A strip of a curved surface has a shallow neighbour on both sides. A single mild bend between two
        # walls (an irregular outline, 23 degrees say) is not a curve: both walls stay flat.
        if similar >= 2:
            curved.add(r)
    return curved


def compute_planar_faces(manifold: m3d.Manifold, body_id: str = "") -> List[PlanarFace]:
    """Returns every planar facet (>= 2 coplanar adjacent triangles) of the solid."""
    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    if len(f) < 2:
        return []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)

    # Union-find over adjacent, coplanar triangles (trimesh.facets needs scipy/networkx)
    parent = np.arange(len(f))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    normals = tm.face_normals
    adj = tm.face_adjacency
    tol = 1e-6 * max(1.0, float(np.ptp(v, axis=0).max()))
    areas = tm.area_faces
    for a_idx, b_idx in adj:
        if _coplanar(a_idx, b_idx, normals, v, f, areas, tol):
            ra, rb = find(int(a_idx)), find(int(b_idx))
            if ra != rb:
                parent[rb] = ra

    groups = {}
    for i in range(len(f)):
        groups.setdefault(find(i), []).append(i)

    # Tessellated curved surfaces: thin strips meeting their neighbours at a shallow angle
    curved = _curved_roots(v, f, tm, find, groups, adj, tm.face_adjacency_angles)

    faces: List[PlanarFace] = []
    slivers = _sliver_roots(v, f, tm, groups)
    for root, tri_ids in groups.items():
        if root in curved or root in slivers:
            continue
        ids = np.array(tri_ids)
        faces.append(PlanarFace(
            body_id=body_id,
            index=len(faces),
            normal=np.asarray(normals[ids[0]], dtype=np.float64),
            origin=v[f[ids[0], 0]],
            area=float(tm.area_faces[ids].sum()),
            tris=v[f[ids]],
        ))
    return faces


def ray_hit_face(face: PlanarFace, ray_origin: np.ndarray, ray_dir: np.ndarray) -> Optional[float]:
    """Moller-Trumbore against all triangles of a face. Returns nearest hit distance or None."""
    o = np.asarray(ray_origin, dtype=np.float64)
    d = np.asarray(ray_dir, dtype=np.float64)
    v0, v1, v2 = face.tris[:, 0], face.tris[:, 1], face.tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    w = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1.0 + 1e-9) & (t > 1e-6)
    return float(t[hit].min()) if hit.any() else None


def in_plane_edges(bodies, plane, tol_rel: float = 1e-3):
    """Body edges lying in a sketch plane, as 2D (u, v) segments."""
    o = np.asarray(plane.origin, dtype=np.float64)
    n = np.asarray(plane.normal, dtype=np.float64)
    ua = np.asarray(plane.u_axis, dtype=np.float64)
    va = np.asarray(plane.v_axis, dtype=np.float64)
    out = []
    for body in bodies:
        mesh = body.render_mesh
        if not body.visible or mesh is None or len(mesh.sharp_lines) == 0:
            continue
        pts = np.asarray(mesh.sharp_lines, dtype=np.float64).reshape(-1, 2, 3) - o
        tol = tol_rel * max(1.0, float(np.ptp(mesh.bounds_max - mesh.bounds_min)))
        on_plane = (np.abs(pts @ n) < tol).all(axis=1)
        for a, b in pts[on_plane]:
            out.append(((float(a @ ua), float(a @ va)), (float(b @ ua), float(b @ va))))
    return out


@dataclass
class PlanarEdge:
    """A straight edge between two planar faces, with what is needed to round or chamfer it."""
    p0: np.ndarray
    p1: np.ndarray
    n1: np.ndarray       # outward normals of the two faces
    n2: np.ndarray
    d1: np.ndarray       # unit vectors lying in each face, pointing away from the edge
    d2: np.ndarray
    convex: bool         # True: a solid corner (material is removed); False: an inside corner (material is added)

    kind = "line"

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.p1 - self.p0))

    def polyline(self, n: int = 2) -> np.ndarray:
        return np.array([self.p0, self.p1])

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "line":
            return False
        return (np.allclose(self.p0, other.p0, atol=1e-6) and np.allclose(self.p1, other.p1, atol=1e-6)) or \
               (np.allclose(self.p0, other.p1, atol=1e-6) and np.allclose(self.p1, other.p0, atol=1e-6))

    def ref(self):
        """What a Fillet/Chamfer step stores to find this edge again."""
        return (tuple(map(float, self.p0)), tuple(map(float, self.p1)))


@dataclass
class CircularEdge:
    """A full circle where a flat face meets a cylinder (top of a pin, rim of a hole, screw head ...)."""
    center: np.ndarray
    axis: np.ndarray     # unit normal of the flat face (outward)
    radius: float
    s1: float            # +1: the flat face lies outside the circle, -1: inside it
    s2: float            # +1: the cylinder wall continues along +axis, -1: along -axis
    convex: bool         # rim of solid material (cut) vs inside corner (fill)
    nseg: int = 48       # segments of the tessellated circle (decides how far the chords sag inside the radius)
    a0: float = 0.0      # an arc only: where it starts (radians, in `_basis`) and how far it runs
    sweep: float = 2 * np.pi

    kind = "circle"

    @property
    def is_arc(self) -> bool:
        return self.sweep < 2 * np.pi - 1e-6

    def _basis(self):
        a = self.axis
        u = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(a, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        return u, np.cross(a, u)

    def polyline(self, n: int = 96) -> np.ndarray:
        u, v = self._basis()
        ang = self.a0 + np.linspace(0.0, self.sweep, max(2, int(n * self.sweep / (2 * np.pi))) + 1)
        return self.center + self.radius * (np.outer(np.cos(ang), u) + np.outer(np.sin(ang), v))

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "circle":
            return False
        if self.is_arc != other.is_arc:
            return False
        if self.is_arc and (float(self.axis @ other.axis) < 0.999 or abs(self.sweep - other.sweep) > 1e-3
                            or abs(math.remainder(self.a0 - other.a0, 2 * np.pi)) > 1e-3):
            return False
        return (abs(abs(float(self.axis @ other.axis)) - 1.0) < 1e-6 and abs(self.radius - other.radius) < 1e-4 * max(1.0, self.radius)
                and np.linalg.norm(self.center - other.center) < 1e-4 * max(1.0, self.radius))

    def ref(self):
        if self.is_arc:
            return ("arc", tuple(map(float, self.center)), tuple(map(float, self.axis)), float(self.radius),
                    float(self.a0), float(self.sweep))
        return ("circle", tuple(map(float, self.center)), tuple(map(float, self.axis)), float(self.radius))


@dataclass
class LoopEdge:
    """The whole outline of a flat face that mixes straight pieces and arcs (a plate with rounded corners,
    a slot ...), where every wall stands square on the face. Rounded or bevelled as one piece."""
    pts: np.ndarray      # (N, 3) points in order, the face on the left of the direction of travel (not closed)
    n: np.ndarray        # outward unit normal of the flat face
    convex: bool = True

    kind = "loop"

    @property
    def perimeter(self) -> float:
        d = np.roll(self.pts, -1, axis=0) - self.pts
        return float(np.linalg.norm(d, axis=1).sum())

    @property
    def centroid(self) -> np.ndarray:
        return self.pts.mean(axis=0)

    def polyline(self, n: int = 0) -> np.ndarray:
        return np.vstack([self.pts, self.pts[:1]])

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "loop":
            return False
        tol = 1e-4 * max(1.0, self.perimeter)
        return (float(self.n @ other.n) > 0.999 and np.linalg.norm(self.centroid - other.centroid) < tol
                and abs(self.perimeter - other.perimeter) < tol)

    def ref(self):
        return ("loop", tuple(map(float, self.centroid)), tuple(map(float, self.n)), float(self.perimeter))


def tangent_chain(edge, edges) -> list:
    """`edge` plus every straight piece or arc joined to it end to end with a smooth (tangent) turn,
    e.g. the straight side and the rounded corner next to it. Corners with a visible knick stop the chain."""
    def ends(e):
        pts = e.polyline()
        t0 = pts[1] - pts[0]
        t1 = pts[-1] - pts[-2]
        return [(pts[0], -t0 / np.linalg.norm(t0)), (pts[-1], t1 / np.linalg.norm(t1))]
    pool = [c for c in edges if c.kind == "line" or (c.kind == "circle" and c.is_arc)]
    if edge.kind not in ("line", "circle") or (edge.kind == "circle" and not edge.is_arc):
        return [edge]
    chain, frontier = [edge], [edge]
    while frontier:
        cur = frontier.pop()
        for p, t in ends(cur):
            for c in pool:
                if any(c.same_as(k) for k in chain):
                    continue
                for q, u in ends(c):
                    # both directions point away from the joint, so a smooth continuation has them opposite
                    if np.linalg.norm(p - q) < 1e-4 and float(t @ u) < -0.995:
                        chain.append(c)
                        frontier.append(c)
                        break
    return chain


def _loop_edges(v, f, normals, find, adj, adj_edges, angles, planar) -> list:
    """Outlines of flat faces made of straight pieces and arcs with square walls (see LoopEdge)."""
    by_face: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ang < np.radians(1.0):
            continue
        for pl_tri, nb_tri, pr, nr in ((a_idx, b_idx, ra, rb), (b_idx, a_idx, rb, ra)):
            if pr not in planar:
                continue
            n_pl = normals[pl_tri]
            third_nb = v[[i for i in f[nb_tri] if i not in (e0, e1)][0]]
            third_pl = v[[i for i in f[pl_tri] if i not in (e0, e1)][0]]
            square = abs(float(normals[nb_tri] @ n_pl)) < 0.1
            side = float(n_pl @ (third_nb - v[e0]))
            # +1: the wall falls away below the face (an outer rim), -1: the wall rises from the face (the foot of a block)
            ok = (1 if side < -1e-9 else -1 if side > 1e-9 else 0) if square else 0
            by_face.setdefault(pr, []).append((int(e0), int(e1), ok, nr in planar, third_pl, n_pl))
    out = []
    for pr, segs in by_face.items():
        comp: dict = {}

        def vfind(x):
            while comp.setdefault(x, x) != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for e0, e1, *_ in segs:
            ra, rb = vfind(e0), vfind(e1)
            if ra != rb:
                comp[rb] = ra
        parts: dict = {}
        for seg in segs:
            parts.setdefault(vfind(seg[0]), []).append(seg)
        for part in parts.values():
            kinds = {sg[2] for sg in part}
            if len(kinds) != 1 or 0 in kinds or not any(sg[3] for sg in part) or all(sg[3] for sg in part):
                continue   # needs both straight pieces (plane/plane) and arcs (plane/curved), all square, all on one side
            nbrs: dict = {}
            for e0, e1, *_ in part:
                nbrs.setdefault(e0, []).append(e1)
                nbrs.setdefault(e1, []).append(e0)
            if any(len(x) != 2 for x in nbrs.values()):
                continue
            start = part[0][0]
            order, prev, cur = [start], None, start
            while len(order) <= len(part):
                nxt = [x for x in nbrs[cur] if x != prev][0]
                if nxt == start:
                    break
                order.append(nxt)
                prev, cur = cur, nxt
            if len(order) != len(part):
                continue
            pts = v[order]
            n_pl = part[0][5]
            t = pts[1] - pts[0]
            left = np.cross(n_pl, t)
            seg_pts = {order[0], order[1]}
            ref_seg = next((sg for sg in part if {sg[0], sg[1]} == seg_pts), part[0])
            if float((ref_seg[4] - pts[0]) @ left) < 0:
                pts = pts[::-1].copy()
            out.append(LoopEdge(pts.copy(), n_pl.copy(), kinds == {1}))
    return out


def compute_planar_edges(manifold: m3d.Manifold) -> list:
    """Straight edges between two flat faces and full circles between a flat face and a cylinder."""
    mesh = manifold.to_mesh()
    return _planar_edges_from(mesh, manifold)


def _planar_edges_from(mesh, manifold) -> list:
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    if len(f) < 4:
        return []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    normals = tm.face_normals
    adj, adj_edges, angles = tm.face_adjacency, tm.face_adjacency_edges, tm.face_adjacency_angles

    parent = np.arange(len(f))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tol = 1e-6 * max(1.0, float(np.ptp(v, axis=0).max()))
    areas = tm.area_faces
    for a_idx, b_idx in adj:
        if _coplanar(a_idx, b_idx, normals, v, f, areas, tol):
            ra, rb = find(int(a_idx)), find(int(b_idx))
            if ra != rb:
                parent[rb] = ra
    groups: dict = {}
    for i in range(len(f)):
        groups.setdefault(find(i), []).append(i)
    curved = _curved_roots(v, f, tm, find, groups, adj, angles)
    slivers = _sliver_roots(v, f, tm, groups)
    planar = {r for r in groups if r not in curved and r not in slivers}

    # collect boundary segments between two different planar faces
    buckets: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ra not in planar or rb not in planar or ang < np.radians(1.0):
            continue
        key = (min(ra, rb), max(ra, rb))
        third_a = v[[i for i in f[a_idx] if i not in (e0, e1)][0]]
        third_b = v[[i for i in f[b_idx] if i not in (e0, e1)][0]]
        if ra > rb:
            a_idx, b_idx, third_a, third_b = b_idx, a_idx, third_b, third_a
        buckets.setdefault(key, []).append((v[e0], v[e1], normals[a_idx], normals[b_idx], third_a, third_b))

    edges: List[PlanarEdge] = []
    for segs in buckets.values():
        p0, p1 = segs[0][0], segs[0][1]
        t = (p1 - p0) / np.linalg.norm(p1 - p0)
        # order the pieces along the edge and merge those that touch
        pieces = sorted(((float((a - p0) @ t), float((b - p0) @ t), a, b, n1, n2, ta, tb)
                         for a, b, n1, n2, ta, tb in segs), key=lambda z: min(z[0], z[1]))
        cur = None
        for s0, s1, a, b, n1, n2, ta, tb in pieces:
            lo, hi = (a, b) if s0 <= s1 else (b, a)
            lo_s, hi_s = min(s0, s1), max(s0, s1)
            if cur is not None and lo_s <= cur["hi_s"] + tol * 10:
                if hi_s > cur["hi_s"]:
                    cur["hi"], cur["hi_s"] = hi, hi_s
                continue
            if cur is not None:
                edges.append(_edge_from(cur, t))
            cur = {"lo": lo, "hi": hi, "hi_s": hi_s, "n1": n1, "n2": n2, "ta": ta, "tb": tb}
        if cur is not None:
            edges.append(_edge_from(cur, t))
    lines = [e for e in edges if e is not None and e.length > 1e-6]
    loops = _loop_edges(v, f, normals, find, adj, adj_edges, angles, planar)
    if loops:   # a straight piece that is part of such an outline is rounded together with it
        def on_loop(e):
            for lp in loops:
                poly = lp.polyline()
                if abs(float(lp.n @ (e.p0 - poly[0]))) > 1e-4 or abs(float(lp.n @ (e.p1 - poly[0]))) > 1e-4:
                    continue
                seg = poly[1:] - poly[:-1]
                for q in (e.p0, (e.p0 + e.p1) / 2.0, e.p1):
                    w = q - poly[:-1]
                    tt = np.clip(np.einsum("ij,ij->i", w, seg) / np.maximum(np.einsum("ij,ij->i", seg, seg), 1e-18), 0, 1)
                    if np.linalg.norm(w - tt[:, None] * seg, axis=1).min() > 1e-4:
                        break
                else:
                    return True
            return False
        lines = [e for e in lines if not on_loop(e)]
    return lines + loops + _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals)


def _edge_from(c, t):
    p0, p1 = c["lo"], c["hi"]
    m = (p0 + p1) / 2.0

    def inward(third):  # direction in that face's plane, perpendicular to the edge, away from it
        w = third - m
        w = w - (w @ t) * t
        n = np.linalg.norm(w)
        return w / n if n > 1e-12 else None

    d1, d2 = inward(c["ta"]), inward(c["tb"])
    if d1 is None or d2 is None:
        return None
    convex = float(c["n1"] @ (c["tb"] - m)) < 0
    return PlanarEdge(p0, p1, c["n1"], c["n2"], d1, d2, convex)


def match_edge(stored_p0, stored_p1, candidates: List[PlanarEdge], tol: float = 1e-3):
    """The candidate lying on the same line as a stored edge (it may have been shortened by
    earlier rounding at its ends). Returns the one overlapping most, or None."""
    a = np.asarray(stored_p0, dtype=float)
    b = np.asarray(stored_p1, dtype=float)
    L = np.linalg.norm(b - a)
    if L < 1e-9:
        return None
    t = (b - a) / L
    best, best_overlap = None, 1e-6
    for c in candidates:
        for q in (c.p0, c.p1):
            if np.linalg.norm((q - a) - ((q - a) @ t) * t) > tol * max(1.0, L):
                break
        else:
            lo, hi = sorted((float((c.p0 - a) @ t), float((c.p1 - a) @ t)))
            overlap = min(hi, L) - max(lo, 0.0)
            if overlap > best_overlap:
                best, best_overlap = c, overlap
    return best


def _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals) -> list:
    """Closed loops where a flat face meets the strips of a cylinder whose axis is the face normal."""
    # cluster the strips of one curved surface (shallow-angle neighbours belong together)
    cl = {r: r for r in curved}

    def cfind(x):
        while cl[x] != x:
            cl[x] = cl[cl[x]]
            x = cl[x]
        return x

    for (a_idx, b_idx), ang in zip(adj, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra != rb and ra in curved and rb in curved and ang < np.radians(25.0):
            ca, cb = cfind(ra), cfind(rb)
            if ca != cb:
                cl[cb] = ca

    buckets: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ang < np.radians(25.0):
            continue
        if ra in planar and rb in curved:
            pl_tri, cu_tri, pr, cr = a_idx, b_idx, ra, rb
        elif rb in planar and ra in curved:
            pl_tri, cu_tri, pr, cr = b_idx, a_idx, rb, ra
        else:
            continue
        third_pl = v[[i for i in f[pl_tri] if i not in (e0, e1)][0]]
        third_cu = v[[i for i in f[cu_tri] if i not in (e0, e1)][0]]
        buckets.setdefault((pr, cfind(cr)), []).append((int(e0), int(e1), pl_tri, cu_tri, third_pl, third_cu))

    # group by flat face only, then split into connected loops (strips can hang together through slivers)
    by_face: dict = {}
    for (pr, _), segs in buckets.items():
        by_face.setdefault(pr, []).extend(segs)
    loops = []
    for pr, segs in by_face.items():
        comp = {}

        def vfind(x):
            while comp.setdefault(x, x) != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for e0, e1, *_ in segs:
            ra, rb = vfind(e0), vfind(e1)
            if ra != rb:
                comp[rb] = ra
        parts: dict = {}
        for seg in segs:
            parts.setdefault(vfind(seg[0]), []).append(seg)
        loops.extend((pr, part) for part in parts.values())

    out = []
    for pr, segs in loops:
        n_plane = normals[segs[0][2]]
        # every vertex of a closed loop has exactly two segments
        deg: dict = {}
        for e0, e1, *_ in segs:
            deg[e0] = deg.get(e0, 0) + 1
            deg[e1] = deg.get(e1, 0) + 1
        ends = [k for k, d in deg.items() if d == 1]
        closed = not ends and len(segs) >= 8
        if not closed and not (len(ends) == 2 and all(d <= 2 for d in deg.values()) and len(segs) >= 4):
            continue
        pts = v[list(deg.keys())]
        # circle fit in the plane of the face
        u = np.cross(n_plane, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(n_plane, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        w = np.cross(n_plane, u)
        xy = np.stack([(pts - pts[0]) @ u, (pts - pts[0]) @ w], axis=1)
        A = np.c_[2 * xy, np.ones(len(xy))]
        sol, *_ = np.linalg.lstsq(A, (xy ** 2).sum(axis=1), rcond=None)
        cx, cy = sol[0], sol[1]
        R = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0)))
        resid = np.abs(np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) - R)
        if R < 1e-6 or resid.max() > 2e-3 * max(1.0, R):
            continue
        center = pts[0] + cx * u + cy * w
        # the wall must be a cylinder around the face normal (wall strips perpendicular to it)
        if any(abs(float(normals[cu] @ n_plane)) > 0.1 for _, _, _, cu, _, _ in segs):
            continue
        e0, e1, pl_tri, cu_tri, third_pl, third_cu = segs[0]
        m = v[e0]
        # which side of the circle the flat face lies on: use the centre of its triangle (a corner can sit
        # exactly on the circle)
        # (only the direction matters: step from the middle of the segment into the flat triangle and see
        # whether that moves away from the axis; the triangle's centroid can lie on the wrong side of a big face)
        mid = (v[e0] + v[e1]) / 2.0
        radial = (mid - center) - ((mid - center) @ n_plane) * n_plane
        s1 = 1.0 if float((third_pl - mid) @ radial) > 0 else -1.0
        s2 = 1.0 if float((third_cu - center) @ n_plane) > 0 else -1.0
        convex = float(n_plane @ (third_cu - m)) < 0
        if closed:
            out.append(CircularEdge(center, n_plane.copy(), R, s1, s2, convex, len(segs)))
            continue
        # an open arc: walk the chain from one end and measure the angle it covers
        nxt: dict = {}
        for e0, e1, *_ in segs:
            nxt.setdefault(e0, []).append(e1)
            nxt.setdefault(e1, []).append(e0)
        order, prev = [ends[0]], None
        while True:
            cand = [x for x in nxt[order[-1]] if x != prev]
            if not cand:
                break
            prev = order[-1]
            order.append(cand[0])
        if len(order) != len(deg):
            continue
        q = v[order] - center
        ang = np.unwrap(np.arctan2(q @ w, q @ u))
        sweep = float(ang[-1] - ang[0])
        a0 = float(ang[0])
        if sweep < 0:
            a0, sweep = float(ang[-1]), -sweep
        if sweep < np.radians(8.0) or sweep > 2 * np.pi - 0.2:
            continue
        out.append(CircularEdge(center, n_plane.copy(), R, s1, s2, convex, int(round(len(segs) * 2 * np.pi / sweep)), a0, sweep))
    return out


def edge_from_ref(ref, candidates):
    """The current edge a stored Fillet/Chamfer reference points at (lines may have been shortened)."""
    if ref and ref[0] == "arc":
        probe = CircularEdge(np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3]), 1.0, 1.0, True,
                             a0=float(ref[4]), sweep=float(ref[5]))
        return next((c for c in candidates if getattr(c, "kind", "") == "circle" and probe.same_as(c)), None)
    if ref and ref[0] == "circle":
        probe = CircularEdge(np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3]), 1.0, 1.0, True)
        return next((c for c in candidates if getattr(c, "kind", "") == "circle" and probe.same_as(c)), None)
    if ref and ref[0] == "loop":
        c0, n0, per = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        tol = 1e-3 * max(1.0, per)
        return next((c for c in candidates if getattr(c, "kind", "") == "loop" and float(c.n @ n0) > 0.999
                     and np.linalg.norm(c.centroid - c0) < tol and abs(c.perimeter - per) < tol), None)
    lines = [c for c in candidates if getattr(c, "kind", "") == "line"]
    return match_edge(ref[0], ref[1], lines)


def fuzzy_edge_from_ref(ref, candidates, used=(), reach: float = 1e9):
    """When an upstream change moved or resized the geometry (a longer box, a wider cylinder) the stored
    end points no longer lie on any edge. Pick the same kind of edge that is nearest to where the old one was:
    a parallel line, a circle round the same axis, an outline facing the same way. Edges already claimed by
    another reference in the same step (`used`) are not taken twice."""
    def free(c):
        return not any(c is u or (getattr(c, "kind", "") == getattr(u, "kind", "") and c.same_as(u)) for u in used)

    if ref and ref[0] in ("circle", "arc"):
        c0, ax, R = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        cand = [c for c in candidates if getattr(c, "kind", "") == "circle" and free(c) and float(c.axis @ ax) > 0.999
                and c.is_arc == (ref[0] == "arc")]
        cand = [c for c in cand if np.linalg.norm(c.center - c0) <= reach]
        # same side of the part: the circle's centre moves least along its own axis
        return min(cand, key=lambda c: np.linalg.norm(c.center - c0) + 0.05 * abs(c.radius - R), default=None)
    if ref and ref[0] == "loop":
        c0, n0, per = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        cand = [c for c in candidates if getattr(c, "kind", "") == "loop" and free(c) and float(c.n @ n0) > 0.999
                and 0.4 <= c.perimeter / max(per, 1e-9) <= 2.5 and np.linalg.norm(c.centroid - c0) <= reach]
        return min(cand, key=lambda c: np.linalg.norm(c.centroid - c0), default=None)
    a, b = np.array(ref[0], dtype=float), np.array(ref[1], dtype=float)
    L = float(np.linalg.norm(b - a))
    if L < 1e-9:
        return None
    t = (b - a) / L
    mid = (a + b) / 2.0
    cand = []
    for c in candidates:
        if getattr(c, "kind", "") != "line" or not free(c):
            continue
        d = c.p1 - c.p0
        lc = float(np.linalg.norm(d))
        if lc < 1e-9 or abs(float(d @ t)) / lc < 0.999:
            continue
        cmid = (c.p0 + c.p1) / 2.0
        off = cmid - mid
        dist = float(np.linalg.norm(off - (off @ t) * t))   # how far the line moved sideways
        if dist <= reach:
            cand.append((dist + 0.25 * abs(lc - L) + 0.01 * abs(float(off @ t)), c))
    return min(cand, key=lambda z: z[0], default=(0, None))[1]


def ray_mesh_hit(mesh, ray_origin, ray_dir):
    """Nearest hit of a ray with a RenderMesh (unrolled triangles). Returns (t, triangle index) or None."""
    tri = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)
    o, d = np.asarray(ray_origin, dtype=np.float64), np.asarray(ray_dir, dtype=np.float64)
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    sv = o - v0
    u = np.einsum("ij,ij->i", sv, p) * inv
    q = np.cross(sv, e1)
    w = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9) & (t > 1e-6)
    if not hit.any():
        return None
    ts = np.where(hit, t, np.inf)
    i = int(ts.argmin())
    return float(ts[i]), i


def smooth_patch_vertices(mesh, tri_idx: int, max_angle_deg: float = 35.0):
    """Vertices of the smoothly connected surface around a triangle (a cylinder wall, a flat face, a sphere...).
    Neighbouring triangles join while their normals differ by less than max_angle_deg."""
    tri = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(ln > 0, ln, 1.0)[:, None]
    scale = max(float(np.ptp(tri.reshape(-1, 3), axis=0).max()), 1.0)
    keys = np.round(tri.reshape(-1, 3) / (scale * 1e-6)).astype(np.int64)
    ids = {}
    vid = np.array([ids.setdefault(tuple(k), len(ids)) for k in keys]).reshape(-1, 3)
    by_vertex = {}
    for t, row in enumerate(vid):
        for x in row:
            by_vertex.setdefault(int(x), []).append(t)
    cos_min = math.cos(math.radians(max_angle_deg))
    seen, stack = {tri_idx}, [tri_idx]
    while stack:
        t = stack.pop()
        for x in vid[t]:
            for nb in by_vertex[int(x)]:
                if nb not in seen and float(nrm[t] @ nrm[nb]) >= cos_min:
                    seen.add(nb)
                    stack.append(nb)
    return tri[sorted(seen)].reshape(-1, 3)


def detect_cylinder_surface(mesh, tri_idx: int) -> Optional[dict]:
    """Detect if the smooth patch around tri_idx is a cylindrical surface (pin/bolt or internal hole).

    Returns a dict with:
      radius: cylinder radius (mm)
      diameter: cylinder diameter (mm)
      length: cylinder length along axis (mm)
      axis: normalized 3D axis vector
      origin: 3D point at the bottom/start of cylinder on the axis
      is_internal: True for internal hole / female, False for external pin / male
      u_axis, v_axis: orthogonal vectors perpendicular to axis
    or None if the patch is planar, spherical, or irregular.
    """
    patch = smooth_patch_vertices(mesh, tri_idx, max_angle_deg=35.0)
    if len(patch) < 24:
        return None

    tri = patch.reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    if np.any(ln == 0):
        return None
    nrm = nrm / ln[:, None]

    # If all normals are almost identical, it's a planar face, not a cylinder
    if float(np.ptp(nrm, axis=0).max()) < 0.15:
        return None

    # For a cylindrical surface, face normals are perpendicular to the cylinder axis: nrm @ axis ~ 0
    # SVD on face normals: the singular vector with smallest singular value is the axis
    try:
        _, s, vh = np.linalg.svd(nrm)
        if s[2] / max(s[0], 1e-9) > 0.35:
            # Normals vary in all 3 directions (e.g. sphere or torus), not cylinder
            return None
        axis = vh[2].copy()
    except Exception:
        return None

    axis_len = float(np.linalg.norm(axis))
    if axis_len < 1e-6:
        return None
    axis /= axis_len

    # Standardize axis direction: prefer positive Z, then positive Y, then positive X
    if axis[2] < -1e-4 or (abs(axis[2]) <= 1e-4 and (axis[1] < -1e-4 or (abs(axis[1]) <= 1e-4 and axis[0] < 0))):
        axis = -axis

    # Create perpendicular basis u_vec, v_vec
    if abs(axis[0]) < 0.9:
        u_vec = np.cross(axis, [1.0, 0.0, 0.0])
    else:
        u_vec = np.cross(axis, [0.0, 1.0, 0.0])
    u_vec /= float(np.linalg.norm(u_vec))
    v_vec = np.cross(axis, u_vec)

    p_mean = patch.mean(axis=0)
    diff = patch - p_mean
    u_coords = diff @ u_vec
    v_coords = diff @ v_vec

    # 2D circle fit via linear least squares
    A = np.column_stack([2.0 * u_coords, 2.0 * v_coords, np.ones(len(patch))])
    b = u_coords**2 + v_coords**2
    try:
        sol, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        du, dv, c_const = sol
        rad_sq = c_const + du**2 + dv**2
        if rad_sq <= 0:
            return None
        radius = float(np.sqrt(rad_sq))
    except Exception:
        return None

    if radius < 0.1 or radius > 5000.0:
        return None

    center_on_axis = p_mean + du * u_vec + dv * v_vec

    # Verify fit quality: points should be at distance ~ radius from axis
    dists_to_axis = np.linalg.norm(diff - np.outer(diff @ axis, axis) - (du * u_vec + dv * v_vec), axis=1)
    if float(np.std(dists_to_axis)) > 0.15 * radius:
        return None

    z_coords = (patch - center_on_axis) @ axis
    z_min, z_max = float(z_coords.min()), float(z_coords.max())
    length = max(0.5, z_max - z_min)
    origin_pt = center_on_axis + z_min * axis

    # Determine internal (hole) vs external (pin):
    sample_pt = patch[0]
    sample_norm = nrm[0]
    radial_vec = sample_pt - (center_on_axis + ((sample_pt - center_on_axis) @ axis) * axis)
    is_internal = bool(float(sample_norm @ radial_vec) < 0.0)

    return {
        "radius": radius,
        "diameter": round(2.0 * radius, 3),
        "length": round(length, 3),
        "axis": axis,
        "origin": origin_pt,
        "is_internal": is_internal,
        "u_axis": u_vec,
        "v_axis": v_vec,
        "patch": patch,
    }
