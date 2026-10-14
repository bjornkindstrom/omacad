"""
Tests for 3D-printable thread and coil generation.
"""

import pytest
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.document import Document
from omacad.model.features.thread import ThreadFeature
from omacad.io.exporter import Exporter


def test_cad_kernel_create_thread_male_trapezoidal():
    """Verify male thread generation produces a valid, watertight solid manifold."""
    bolt = CadKernel.create_thread(
        diameter=10.0,
        pitch=2.0,
        length=20.0,
        is_female=False,
        clearance=0.25,
        profile="trapezoidal_45",
        taper_lead_in=True,
        taper_turns=0.75,
        include_core=True,
    )
    assert not bolt.is_empty()
    assert str(bolt.status()) == "Error.NoError"
    assert bolt.volume() > 0.0


def test_cad_kernel_create_thread_female_cutter():
    """Verify female thread cutter produces a valid manifold and can cut a hole."""
    cutter = CadKernel.create_thread(
        diameter=12.0,
        pitch=2.0,
        length=15.0,
        is_female=True,
        clearance=0.25,
        profile="trapezoidal_45",
        taper_lead_in=True,
        include_core=False,
    )
    assert not cutter.is_empty()
    assert str(cutter.status()) == "Error.NoError"

    # Blank nut block
    nut_blank = CadKernel.create_box(20.0, 20.0, 15.0, center=False)
    hole = CadKernel.create_cylinder(radius=5.0, height=20.0, center=False)
    # Cut hole and female thread
    nut = (nut_blank - hole) - cutter
    assert not nut.is_empty()
    assert str(nut.status()) == "Error.NoError"
    assert nut.volume() < nut_blank.volume()


def test_document_add_thread_feature_and_timeline():
    """Verify adding a thread to a Document updates bodies, timeline and serialization."""
    doc = Document()
    body = doc.add_thread(
        diameter=8.0,
        pitch=1.5,
        length=16.0,
        clearance=0.2,
        profile="trapezoidal_45",
        taper_lead_in=True,
    )
    assert body is not None
    assert body.body_id in doc.bodies
    assert len(doc.timeline.features) == 1
    assert doc.timeline.features[0].feature_type == "thread"

    # Serialize to dict and reload
    doc_json = doc.snapshot()
    doc2 = Document()
    doc2.restore(doc_json)
    assert len(doc2.timeline.features) == 1
    feat = doc2.timeline.features[0]
    assert feat.feature_type == "thread"
    assert feat.diameter == 8.0
    assert feat.pitch == 1.5
    assert feat.clearance == 0.2
    assert len(doc2.bodies) == 1
