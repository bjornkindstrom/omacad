"""#61: curved surfaces are shaded smooth (shared vertex normals), sharp CAD edges stay crisp."""
import numpy as np
import manifold3d as m3d

from omacad.model.kernel import CadKernel


def test_box_keeps_flat_faces():
    rm = CadKernel.extract_render_mesh(m3d.Manifold.cube((10, 20, 5)))
    tri = rm.vertices.reshape(-1, 3, 3)
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    face /= np.linalg.norm(face, axis=1, keepdims=True)
    assert np.allclose(rm.normals.reshape(-1, 3, 3), face[:, None, :], atol=1e-5)


def test_cylinder_wall_normals_point_radially():
    cyl = m3d.Manifold.cylinder(10.0, 5.0, circular_segments=48)
    rm = CadKernel.extract_render_mesh(cyl)
    p, n = rm.vertices, rm.normals
    wall = np.abs(n[:, 2]) < 0.5
    radial = p[wall, :2] / np.linalg.norm(p[wall, :2], axis=1, keepdims=True)
    assert np.allclose(n[wall, :2], radial, atol=1e-4) and np.allclose(n[wall, 2], 0.0, atol=1e-4)
    caps = np.abs(n[:, 2]) > 0.5
    assert np.allclose(np.abs(n[caps, 2]), 1.0, atol=1e-6)    # the rim stays a sharp edge
