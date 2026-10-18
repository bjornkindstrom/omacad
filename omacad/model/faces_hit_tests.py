"""Faces hit tests for CAD mesh geometry."""

from typing import Optional
import math
import numpy as np
from omacad.model.faces_types import PlanarFace

_FACE_STACKS: dict = {}


def _ray_triangles(tris: np.ndarray, ray_origin, ray_dir) -> np.ndarray:
    """Moller-Trumbore against many triangles (N, 3, 3) at once: hit distance per triangle, inf where missed."""
    o = np.asarray(ray_origin, dtype=np.float64)
    d = np.asarray(ray_dir, dtype=np.float64)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
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
    return np.where(hit, t, np.inf)

def ray_hit_face(face: PlanarFace, ray_origin: np.ndarray, ray_dir: np.ndarray) -> Optional[float]:
    """Nearest hit distance of a ray on one face, or None."""
    t = _ray_triangles(face.tris, ray_origin, ray_dir)
    return float(t.min()) if len(t) and np.isfinite(t.min()) else None

def ray_hit_faces(faces, ray_origin: np.ndarray, ray_dir: np.ndarray) -> np.ndarray:
    """Nearest hit distance per face (inf = missed), all triangles of all faces in one go. The triangles
    are stacked once per face list (a body's list is replaced when it is rebuilt): hovering a body with
    thousands of faces stays fast."""
    hit = _FACE_STACKS.get(id(faces))
    if hit is None or hit[0] is not faces:
        if len(_FACE_STACKS) > 64:
            _FACE_STACKS.clear()
        tris = [np.asarray(f.tris, dtype=np.float64).reshape(-1, 3, 3) for f in faces]
        owner = np.repeat(np.arange(len(tris)), [len(t) for t in tris]).astype(int)
        hit = _FACE_STACKS[id(faces)] = (faces, np.concatenate(tris) if tris else np.zeros((0, 3, 3)), owner)
    _, tris, owner = hit
    out = np.full(len(faces), np.inf)
    if len(tris):
        np.minimum.at(out, owner, _ray_triangles(tris, ray_origin, ray_dir))
    return out

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
        "length_exact": z_max - z_min,
        "axis": axis,
        "origin": origin_pt,
        "is_internal": is_internal,
        "u_axis": u_vec,
        "v_axis": v_vec,
        "patch": patch,
    }
