"""Offset keeps arcs as arcs, lets radii follow and leaves no broken joints."""
import math

import pytest
from shapely.geometry import Polygon

from omacad.model.document import Document


def rounded_rect(r=3.0, w=40.0, h=24.0):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rect((0, 0), (w, h))
    for pt, la, lb, _a, _b in sk.find_corners():
        sk.fillet_corner(la, lb, r, pt)
    return d, sk


def endpoints(entities):
    pts = []
    for e in entities:
        if e.entity_type == "line":
            pts += [e.p1, e.p2]
        elif e.entity_type == "arc":
            pts += [e.p_start, e.p_end]
    return pts


def is_closed_chain(entities, tol=1e-6):
    """Every end point is shared by exactly two elements."""
    pts = endpoints(entities)
    for p in pts:
        if sum(1 for q in pts if math.hypot(p[0] - q[0], p[1] - q[1]) < tol) != 2:
            return False
    return True


def shape_polygon(sk, ids):
    """The outline of some elements as a polygon (arcs sampled)."""
    from omacad.model.sketch_offset import build_chains, to_seg
    chain, closed = build_chains([to_seg(e) for e in sk.entities if e.entity_id in ids])[0]
    pts = []
    for s in chain:
        pts += s.points(64)[:-1]
    return Polygon(pts)


@pytest.mark.parametrize("dist", [-1.0, -2.0, 2.0, 4.0])
def test_rounded_rectangle_offset_follows_the_radii(dist):
    d, sk = rounded_rect(3.0)
    ids = [e.entity_id for e in sk.entities]
    base = shape_polygon(sk, ids)
    new = sk.offset_entities(ids, dist)
    assert [e.entity_type for e in new].count("arc") == 4 and [e.entity_type for e in new].count("line") == 4
    assert is_closed_chain(new), "the offset has broken joints"
    radii = sorted(round(math.hypot(e.p_start[0] - c[0], e.p_start[1] - c[1]), 3)
                   for e in new if e.entity_type == "arc" for c in [e.get_circle_params()[0]])
    assert radii == [pytest.approx(3.0 + dist, abs=1e-3)] * 4
    expected = base.buffer(dist, join_style=1, resolution=256).area
    assert shape_polygon(sk, [e.entity_id for e in new]).area == pytest.approx(expected, rel=2e-3)


def test_inward_offset_larger_than_the_radius_drops_the_arcs_and_stays_closed():
    d, sk = rounded_rect(3.0)
    ids = [e.entity_id for e in sk.entities]
    new = sk.offset_entities(ids, -3.5)
    assert all(e.entity_type == "line" for e in new) and len(new) == 4
    assert is_closed_chain(new)
    assert shape_polygon(sk, [e.entity_id for e in new]).area == pytest.approx((40 - 7) * (24 - 7), rel=1e-6)


def test_open_chain_of_a_line_an_arc_and_a_line():
    d = Document()
    sk = d.start_sketch("XY")
    sk.entities = []
    from omacad.model.sketch import SketchArc, SketchLine
    sk.entities += [SketchLine("a", (0, 0), (10, 0)), SketchArc("b", (10, 0), (13.5355339, 1.4644661), (15, 5)), SketchLine("c", (15, 5), (15, 15))]
    new = sk.offset_entities(["a", "b", "c"], 2.0)          # to the left of the travel direction
    types = [e.entity_type for e in new]
    assert types.count("line") == 2 and types.count("arc") == 1 and len(new) == 3
    arc = [e for e in new if e.entity_type == "arc"][0]
    centre, radius = arc.get_circle_params()[0], arc.get_circle_params()[1]
    assert radius == pytest.approx(5.0 - 2.0, abs=1e-3)
    line_a = [e for e in new if e.entity_type == "line"][0]
    assert line_a.p1[1] == pytest.approx(2.0) and line_a.p2[1] == pytest.approx(2.0)
    assert is_open_connected(new)


def is_open_connected(entities):
    pts = endpoints(entities)
    shared = [sum(1 for q in pts if math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6) for p in pts]
    return shared.count(1) == 2 and all(n in (1, 2) for n in shared)


def test_offset_of_a_circle_and_lines_together():
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_circle((50, 50), 5)
    sk.add_rect((0, 0), (10, 10))
    new = sk.offset_entities([e.entity_id for e in sk.entities], -2)
    assert [e.entity_type for e in new].count("circle") == 1
    assert [e.entity_type for e in new if e.entity_type == "circle"][0] == "circle"
    c = [e for e in new if e.entity_type == "circle"][0]
    assert c.radius == pytest.approx(3.0)
