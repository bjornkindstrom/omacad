"""Shell on a cylinder: its side facets are one curved face but many planes; every one must be offset."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.features.shell import ShellFeature
from omacad.model import quality


def _cylinder():
    return Document().add_cylinder(20, 40).manifold


def _area(r):
    n = quality.circle_segments()
    return n/2*math.sin(2*math.pi/n)*r**2


def _offset(t):
    """Radius whose polygon lies t (normal to the facets) from the cylinder's polygon."""
    return 20 + t/math.cos(math.pi/quality.circle_segments())


@pytest.mark.parametrize("open_top", [False, True])
def test_inside_shell_of_cylinder_keeps_its_side_wall(open_top):
    faces = [{"normal": [0, 0, 1], "origin": [0, 0, 40]}] if open_top else None
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "inside", open_faces=faces)
    cavity = _area(_offset(-2)) * (38 if open_top else 36)
    assert shelled.volume() == pytest.approx(_area(20)*40 - cavity, rel=1e-6)


def test_outside_shell_of_cylinder_stays_round():
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "outside")
    assert shelled.bounding_box()[3] == pytest.approx(_offset(2), rel=1e-6)
    assert shelled.volume() == pytest.approx(_area(_offset(2))*44 - _area(20)*40, rel=1e-6)
