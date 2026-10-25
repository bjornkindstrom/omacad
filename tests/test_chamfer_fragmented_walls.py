"""Report 20261025-125922: chamfering a curved outline drew stripes down the wall.

Topology and the outline tool must retain the solid's double precision. Rounding
outline coordinates through float32 before the boolean leaves thin wall slivers.
"""
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter

DOC = str(Path(__file__).parent / "data" / "chamfer_fragmented_walls.omacad")


@pytest.mark.parametrize("whole_selection", [False, True])
def test_chamfer_keeps_curved_walls_free_of_false_creases(whole_selection):
    doc = Exporter.load_project(DOC)
    if not whole_selection:
        # The loop alone must also work; the report selected two arcs on it too.
        feature = doc.timeline.features[-1]
        feature.edges = feature.edges[:1]
        doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    assert body.manifold.status().name == "NoError"
    assert body.manifold.volume() == pytest.approx(632680.238, abs=0.03)
    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    # Only the three horizontal rims are sharp: bottom, wall/bevel, bevel/top.
    assert np.allclose(segments[:, 0, 2], segments[:, 1, 2], atol=1e-4)
    assert np.allclose(np.unique(segments[..., 2]), [0.0, 45.292, 50.0])
    tangents = body.render_mesh.tangent_lines().reshape(-1, 2, 3)
    # Six straight-wall/arc transitions, at most one wall and one bevel seam each.
    assert 6 <= len(tangents) <= 12
    vertical = tangents[np.abs(tangents[:, 1, 2] - tangents[:, 0, 2]) > 40]
    assert len(vertical) == 6
    assert np.allclose(vertical[:, 0, :2], vertical[:, 1, :2], atol=1e-4)
