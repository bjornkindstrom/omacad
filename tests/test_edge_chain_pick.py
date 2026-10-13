"""Picking one edge for Fillet/Chamfer follows the smooth chain; the preview's body lookup must not compare arrays."""
import os

from omacad.io.exporter import Exporter
from omacad.model.faces import tangent_chain

DOC = os.path.join(os.path.dirname(__file__), "data", "plate_rounded_chain.omacad")


def _body():
    return next(iter(Exporter.load_project(DOC).bodies.values()))


def test_chain_follows_tangent_arcs_and_stops_at_knicks():
    body = _body()
    sizes = [len(tangent_chain(e, body.edges)) for e in body.edges if e.kind == "line"]
    assert max(sizes) >= 3                      # straight side + rounded corners
    assert all(s <= len(body.edges) for s in sizes)
    e = next(e for e in body.edges if e.kind == "line" and len(tangent_chain(e, body.edges)) >= 3)
    chain = tangent_chain(e, body.edges)
    assert any(c.kind == "circle" for c in chain)
    assert all(any(c.same_as(k) for k in tangent_chain(c, body.edges)) for c in chain)


def test_owner_lookup_with_same_as_does_not_raise():
    body = _body()
    assert all(any(e.same_as(k) for k in body.edges) for e in body.edges)
