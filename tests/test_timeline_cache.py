"""The incremental recompute cache must never hand out stale copies of the user's work."""
from omacad.model.document import Document


def _sketch_with_extrude():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5.0)
    return doc, sk.sketch_id


def test_sketch_edit_after_cached_recompute_is_kept():
    doc, sid = _sketch_with_extrude()
    doc.timeline.recompute(doc)
    doc.timeline.recompute(doc)          # second run restores the sketch step from the cache
    sk = doc.edit_sketch(sid)
    sk.add_rect((20, 0), (30, 10))
    doc.finish_sketch()
    assert len(doc.sketches[sid].entities) == 8
    assert len(doc.sketches[sid].profiles) == 2
    feat = next(f for f in doc.timeline.features if f.feature_type == "sketch")
    assert doc.sketches[sid] is feat.sketch
