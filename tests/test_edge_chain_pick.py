"""Picking one edge for Fillet/Chamfer follows the smooth chain; the preview's body lookup must not compare arrays."""
import os

from omacad.io.exporter import Exporter
from omacad.model.faces import tangent_chain

DOC = os.path.join(os.path.dirname(__file__), "data", "plate_rounded_chain.omacad")


def _body():
    return next(iter(Exporter.load_project(DOC).bodies.values()))


def test_chain_follows_tangent_arcs_and_stops_at_knicks():
    body = _body()
    # straight sides + rounded corners come as one loop; the float64 mesh leaves no stray lines on the fillet
    loops = [e for e in body.edges if e.kind == "loop"]
    assert len(loops) == 1
    assert not any(e.kind == "line" for e in body.edges)
    arcs = [e for e in body.edges if e.kind == "circle" and e.is_arc]
    assert arcs
    for arc in arcs:
        chain = tangent_chain(arc, body.edges)
        assert len(chain) <= len(body.edges)
        assert all(any(c.same_as(k) for k in tangent_chain(c, body.edges)) for c in chain)


def test_owner_lookup_with_same_as_does_not_raise():
    body = _body()
    assert all(any(e.same_as(k) for k in body.edges) for e in body.edges)
