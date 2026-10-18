"""An extruded cut tangent to a shell wall must not leave narrow mesh strips."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.kernel import CadKernel


DOC = Path(__file__).parent / "data" / "extrude_cut_thread_fuzz.omacad"


def test_extrude_cut_through_threaded_shell_resolves_coincident_wall():
    doc = Exporter.load_project(str(DOC))
    body_id = "body_cylinder_1"
    before = doc.step_states[9][body_id]
    cutter = doc.timeline.features[9].build_solid(doc)
    expected = before - CadKernel.grown(cutter, 1e-6)

    body = doc.bodies[body_id]
    mesh = body.manifold.to_mesh()
    assert body.manifold.volume() == pytest.approx(expected.volume(), abs=1e-6)
    # The plain cut creates 7,206 triangles, including narrow fragments along
    # the near-coincident inner wall. The tolerance-expanded tool resolves them.
    assert len(mesh.tri_verts) < 6_000
