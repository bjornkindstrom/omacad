from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchSpline, move_entity, rotate_entity


def test_spline_interpolates_picked_points_and_roundtrips():
    points = [(0, 0), (5, 8), (10, 0)]
    spline = SketchSpline("spline_1", points)

    sampled = spline.get_points()
    assert sampled[0] == points[0]
    assert sampled[-1] == points[-1]
    assert all(point in sampled for point in points)
    assert len(spline.to_lines()) == 32
    assert SketchSpline.from_dict(spline.to_dict()).points == points


def test_spline_sketch_serialization_and_transformations():
    sketch = Sketch("sketch_1", plane=SketchPlane.create_named("XY"))
    spline = sketch.add_spline([(0, 0), (5, 8), (10, 0)])
    restored = Sketch.from_dict(sketch.to_dict())
    assert restored.entities[0].to_dict() == spline.to_dict()

    move_entity(spline, 2, -1)
    assert spline.points[0] == (2, -1)
    rotate_entity(spline, 90, (0, 0))
    assert abs(spline.points[0][0] - 1) < 1e-9
    assert abs(spline.points[0][1] - 2) < 1e-9
