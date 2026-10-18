"""Snap points on a body for Move/Rotate: ends of straight edges and the corners roundings hide."""
import numpy as np
import pytest

from omacad.model.body_points import body_points, nearest_point, tangent_corner
from omacad.model.document import Document


def _rounded_block(r=4.0):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), r)
    d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 10)
    return d, next(iter(d.bodies.values()))


def _set(points, kind):
    return sorted(tuple(round(float(c), 4) for c in p.xyz) for p in points if p.kind == kind)


def test_box_has_its_eight_corners_as_ends():
    d = Document()
    d.add_box(30, 20, 10)
    pts = body_points(next(iter(d.bodies.values())))
    assert len(_set(pts, "end")) == 8
    assert not _set(pts, "corner")
    xs, ys, zs = zip(*_set(pts, "end"))
    assert (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) == pytest.approx((30, 20, 10))


def test_box_has_centres_of_top_and_bottom_faces():
    d = Document()
    d.add_box(30, 20, 10)
    body = next(iter(d.bodies.values()))
    points = {p.kind: p.xyz for p in body_points(body) if p.kind in ("top_center", "bottom_center")}
    assert points["bottom_center"] == pytest.approx((15, 10, 0), abs=1e-3)
    assert points["top_center"] == pytest.approx((15, 10, 10), abs=1e-3)
    assert nearest_point(body, (0, 0, 0), "top_center").xyz == pytest.approx((15, 10, 10), abs=1e-3)


def test_sphere_has_top_and_bottom_extreme_centres():
    d = Document()
    d.add_sphere(5)
    points = {p.kind: p.xyz for p in body_points(next(iter(d.bodies.values())))
              if p.kind in ("top_center", "bottom_center")}
    assert points["bottom_center"] == pytest.approx((0, 0, -5), abs=1e-3)
    assert points["top_center"] == pytest.approx((0, 0, 5), abs=1e-3)


def test_rounded_block_gives_the_hidden_sharp_corners_and_the_tangent_points():
    _, body = _rounded_block()
    pts = body_points(body)
    corners = _set(pts, "corner")
    expected = sorted((x, y, z) for x in (0.0, 30.0) for y in (0.0, 20.0) for z in (0.0, 10.0))
    assert np.allclose(corners, expected, atol=1e-3)
    ends = _set(pts, "end")
    assert len(ends) == 16                            # two tangent points per rounded corner, top and bottom
    assert (4.0, 0.0, 0.0) in [tuple(round(c, 3) for c in e) for e in ends]
    corner = next(p for p in pts if p.kind == "corner")
    for g in corner.guides:                           # guide lines run from the arc ends to the corner, 4 mm long
        assert float(np.linalg.norm(g - corner.xyz)) == pytest.approx(4.0, abs=1e-3)


def test_corner_stays_put_when_the_radius_changes():
    _, small = _rounded_block(2.0)
    _, large = _rounded_block(6.0)
    assert np.allclose(_set(body_points(small), "corner"), _set(body_points(large), "corner"), atol=1e-3)
    found = nearest_point(large, (30.2, 19.9, 10.1), "corner")
    assert found.xyz == pytest.approx((30, 20, 10), abs=1e-3)


def test_tangent_corner_of_a_quarter_turn():
    assert tangent_corner(np.array([1.0, 0, 0]), np.array([1.0, 0, 0]), np.array([2.0, 1, 0]),
                          np.array([0.0, 1, 0])) == pytest.approx((2, 0, 0))
    assert tangent_corner(np.array([0.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0.0, 1, 0]),
                          np.array([1.0, 0, 0])) is None   # parallel
