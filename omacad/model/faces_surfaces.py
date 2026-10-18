"""Faces surfaces for CAD mesh geometry."""

from typing import List, Tuple
import numpy as np
import manifold3d as m3d
import trimesh
from omacad.model.faces_types import PlanarFace, PlanarEdge
from omacad.model.faces_topology import _coplanar, _curved_roots, _sliver_roots
from omacad.model.faces_edges import _edge_from, _loop_edges, _circular_edges

_TOPOLOGY_CACHE: dict = {}
_TOPOLOGY_CACHE_MAX = 512


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

def clear_topology_cache():
    """Clears the global topology analysis cache."""
    _TOPOLOGY_CACHE.clear()

def compute_planar_faces_and_edges(manifold: m3d.Manifold, body_id: str = "") -> Tuple[List[PlanarFace], list]:
    """Computes both planar faces and edges in a single shared topological pass (2x faster than separate calls).
    Cached by manifold geometric fingerprint to avoid redundant trimesh topology analysis."""
    if manifold.is_empty():
        return [], []

    # Fast fingerprint from manifold geometric invariants (avoids full mesh hashing)
    try:
        cache_key = (
            manifold.num_vert(),
            manifold.num_edge(),
            manifold.num_tri(),
            manifold.genus(),
            round(manifold.volume(), 5),
            round(manifold.surface_area(), 5),
            tuple(round(x, 5) for x in manifold.bounding_box())
        )
    except Exception:
        cache_key = None

    if cache_key is not None and cache_key in _TOPOLOGY_CACHE:
        cached_faces, cached_edges = _TOPOLOGY_CACHE[cache_key]
        # Fast rebinding of body_id on cached faces without deep copy
        faces = [
            PlanarFace(
                body_id=body_id,
                index=f.index,
                normal=f.normal,
                origin=f.origin,
                area=f.area,
                tris=f.tris,
            ) for f in cached_faces
        ]
        return faces, cached_edges

    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    if len(f) < 2:
        return [], []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)

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

    groups: dict = {}
    for i in range(len(f)):
        groups.setdefault(find(i), []).append(i)

    angles = tm.face_adjacency_angles
    curved = _curved_roots(v, f, tm, find, groups, adj, angles)
    slivers = _sliver_roots(v, f, tm, groups)
    planar = {r for r in groups if r not in curved and r not in slivers}

    faces: List[PlanarFace] = []
    for root in planar:
        tri_ids = groups[root]
        ids = np.array(tri_ids)
        faces.append(PlanarFace(
            body_id=body_id,
            index=len(faces),
            normal=np.asarray(normals[ids[0]], dtype=np.float64),
            origin=v[f[ids[0], 0]],
            area=float(tm.area_faces[ids].sum()),
            tris=v[f[ids]],
        ))

    if len(f) < 4:
        return faces, []

    adj_edges = tm.face_adjacency_edges
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
    if loops:
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
    all_edges = lines + loops + _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals)
    from omacad.model.wrapped_edges import cylindrical_contours
    all_edges += cylindrical_contours(v, f, tm)

    if cache_key is not None:
        if len(_TOPOLOGY_CACHE) >= _TOPOLOGY_CACHE_MAX:
            _TOPOLOGY_CACHE.clear()
        _TOPOLOGY_CACHE[cache_key] = (faces, all_edges)

    return faces, all_edges
