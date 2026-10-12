"""Small rotation helpers shared by the model."""
import math
import numpy as np


def rotation_aligning(a, b) -> np.ndarray:
    """3x3 rotation turning unit vector `a` into unit vector `b` by the shortest way."""
    a = np.asarray(a, dtype=float) / np.linalg.norm(a)
    b = np.asarray(b, dtype=float) / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if c > 1.0 - 1e-12:
        return np.eye(3)
    if c < -1.0 + 1e-12:   # opposite: half a turn about any axis perpendicular to a
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)
    k = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


def euler_xyz_degrees(R) -> tuple:
    """(rx, ry, rz) in degrees such that R = Rz(rz) @ Ry(ry) @ Rx(rx): the order Manifold.rotate applies
    (first about X, then Y, then Z)."""
    ry = -math.asin(max(-1.0, min(1.0, float(R[2, 0]))))
    if abs(R[2, 0]) > 1.0 - 1e-9:   # gimbal lock: fold the whole twist into X
        rx = math.atan2(-float(R[1, 2]), float(R[1, 1]))
        rz = 0.0
    else:
        rx = math.atan2(float(R[2, 1]), float(R[2, 2]))
        rz = math.atan2(float(R[1, 0]), float(R[0, 0]))
    return math.degrees(rx), math.degrees(ry), math.degrees(rz)


def lay_on_ground_values(face_normal, face_origin, centre, about_centre: bool = True) -> tuple:
    """(dx, dy, dz, rx, ry, rz) for a Move step that turns a body so the face lies flat on the ground (z = 0, the body
    above it). Rotation is about `centre` (the body's middle) or the world origin; the shift is straight up or down."""
    n = np.asarray(face_normal, dtype=float)
    R = rotation_aligning(n / np.linalg.norm(n), [0.0, 0.0, -1.0])
    rx, ry, rz = euler_xyz_degrees(R)
    pivot = np.asarray(centre, dtype=float) if about_centre else np.zeros(3)
    moved = pivot + R @ (np.asarray(face_origin, dtype=float) - pivot)
    return 0.0, 0.0, -float(moved[2]), rx, ry, rz
