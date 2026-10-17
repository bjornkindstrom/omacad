"""
Omacad - Editing steps of the parametric history (timeline).

Each step type reuses the dialog it was created with, filled with its current values.
Accepting rebuilds everything after the step.
"""

from PySide6.QtWidgets import QMessageBox

from omacad.ui.dialogs import (
    BoxDialog, CylinderDialog, SphereDialog, ExtrudeDialog, RoundEdgesDialog, PatternDialog, MoveBodyDialog,
    ThreadDialog
)

DIRECTIONS = ["one_side", "symmetric", "two_sides"]
OPERATIONS = ["auto", "new_body", "join", "cut", "intersect"]  # same order as the Extrude dialog


def can_edit(feature) -> bool:
    return feature.feature_type in ("box", "cylinder", "sphere", "extrude", "emboss", "sketch", "fillet", "pattern", "move", "thread", "offset_face")


def edit_feature(win, doc, index: int) -> bool:
    """Opens the right editor for step `index`. Sketches are edited in sketch mode (returns False)."""
    feat = doc.timeline.features[index]
    t = feat.feature_type
    if t == "extrude":
        dlg = ExtrudeDialog(doc, win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.select_profile((feat.sketch_id, feat.profile_idx))
        dlg.cmb_dir.setCurrentIndex(DIRECTIONS.index(feat.direction) if feat.direction in DIRECTIONS else 0)
        dlg.spn_dist.setValue(feat.distance)
        dlg.spn_dist2.setValue(abs(feat.distance2))
        if feat.exprs.get("distance"):
            dlg.spn_dist.set_expression(feat.exprs["distance"])
        if feat.exprs.get("distance2"):
            dlg.spn_dist2.set_expression(feat.exprs["distance2"])
        dlg.cmb_op.setCurrentIndex(OPERATIONS.index(feat.operation) if feat.operation in OPERATIONS else 0)
        if not dlg.exec():
            return False
        s_id, p_idx, dist, op = dlg.get_values()
        direction, dist2 = dlg.get_direction()
        if s_id is None:
            return False
        if op == "auto":  # decide with the step's own parameters, as when it was made
            from omacad.model.timeline import ExtrudeFeature
            op = ExtrudeFeature("tmp", "tmp", s_id, p_idx, dist, "auto", direction, dist2).resolve_operation(doc)
        return doc.edit_feature(index, sketch_id=s_id, profile_idx=p_idx, distance=dist,
                                direction=direction, distance2=dist2, operation=op, exprs=dlg.get_expressions())
    if t == "emboss":
        from omacad.ui.dialogs import EmbossDialog
        dlg = EmbossDialog(win, feat.depth, editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.set_values(feat)
        if not dlg.exec():
            return False
        return doc.edit_feature(index, exprs=dlg.get_expressions(), **dlg.get_values())
    if t == "box":
        dlg = BoxDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_length.setValue(feat.length)
        dlg.spn_width.setValue(feat.width)
        dlg.spn_height.setValue(feat.height)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
            idx = dlg.cmb_placement.findData("on_face")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is True or feat.center == "center":
            idx = dlg.cmb_placement.findData("center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is False or feat.center == "corner":
            idx = dlg.cmb_placement.findData("corner")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        else:
            idx = dlg.cmb_placement.findData("bottom_center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        for key, spin in (("length", dlg.spn_length), ("width", dlg.spn_width), ("height", dlg.spn_height)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])
        if not dlg.exec():
            return False
        l, w, h, center, po, pn, pu, pv = dlg.get_values()
        return doc.edit_feature(index, length=l, width=w, height=h, center=center,
                                plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                exprs=dlg.get_expressions())
    if t == "cylinder":
        dlg = CylinderDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_radius.setValue(feat.radius)
        dlg.spn_height.setValue(feat.height)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
            idx = dlg.cmb_placement.findData("on_face")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is True or feat.center == "center":
            idx = dlg.cmb_placement.findData("center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        else:
            idx = dlg.cmb_placement.findData("bottom_center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        for key, spin in (("radius", dlg.spn_radius), ("height", dlg.spn_height)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])
        if not dlg.exec():
            return False
        r, h, center, po, pn, pu, pv = dlg.get_values()
        return doc.edit_feature(index, radius=r, height=h, center=center,
                                plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                exprs=dlg.get_expressions())
    if t == "sphere":
        dlg = SphereDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_radius.setValue(feat.radius)
        if feat.exprs.get("radius"):
            dlg.spn_radius.set_expression(feat.exprs["radius"])
        if not dlg.exec():
            return False
        return doc.edit_feature(index, radius=dlg.get_values(), exprs=dlg.get_expressions())
    if t == "fillet":
        dlg = RoundEdgesDialog(win, feat.kind, feat.size, editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        if feat.exprs.get("size"):
            dlg.spn_size.set_expression(feat.exprs["size"])
        if not dlg.exec():
            return False
        return doc.edit_feature(index, size=dlg.spn_size.value(), kind=dlg.kind(), exprs=dlg.get_expressions())
    if t == "offset_face":
        from omacad.ui.dialogs import OffsetFaceDialog
        dlg = OffsetFaceDialog(win, feat.distance, editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        if feat.exprs.get("distance"):
            dlg.spn_dist.set_expression(feat.exprs["distance"])
        if not dlg.exec():
            return False
        return doc.edit_feature(index, distance=dlg.distance(), exprs=dlg.get_expressions())
    if t == "pattern":
        dlg = PatternDialog(doc, win, feat)
        dlg.setWindowTitle(f"Edit {feat.name}")
        if not dlg.exec():
            return False
        return doc.edit_feature(index, source_ids=dlg.source_ids(), kind=dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())
    if t == "move":
        dlg = MoveBodyDialog(doc, win, preselected_body_id=feat.target_body_id)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_dx.setValue(feat.dx)
        dlg.spn_dy.setValue(feat.dy)
        dlg.spn_dz.setValue(feat.dz)
        dlg.spn_rx.setValue(feat.rx)
        dlg.spn_ry.setValue(feat.ry)
        dlg.spn_rz.setValue(feat.rz)
        if hasattr(dlg, "cmb_pivot") and hasattr(feat, "pivot"):
            idx = 0 if feat.pivot == "center" else 1
            dlg.cmb_pivot.setCurrentIndex(idx)
        for key, spin in (("dx", dlg.spn_dx), ("dy", dlg.spn_dy), ("dz", dlg.spn_dz),
                          ("rx", dlg.spn_rx), ("ry", dlg.spn_ry), ("rz", dlg.spn_rz)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])
        if not dlg.exec():
            return False
        bid, dx, dy, dz, rx, ry, rz, pivot, exprs = dlg.get_values()
        return doc.edit_feature(index, target_body_id=bid, dx=dx, dy=dy, dz=dz, rx=rx, ry=ry, rz=rz, pivot=pivot, exprs=exprs)
    if t == "thread":
        dlg = ThreadDialog(doc, win, preselected_body_id=feat.target_body_id)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_dia.setValue(feat.diameter)
        dlg.spn_pitch.setValue(feat.pitch)
        dlg.spn_length.setValue(feat.length)
        dlg.spn_clearance.setValue(feat.clearance)
        prof_idx = dlg.cmb_profile.findData(getattr(feat, "profile", "trapezoidal_45"))
        if prof_idx >= 0:
            dlg.cmb_profile.setCurrentIndex(prof_idx)
        dlg.set_lead_in(feat.taper_lead_in, feat.taper_turns)
        idx_type = 1 if feat.is_female else 0
        dlg.cmb_type.setCurrentIndex(idx_type)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
        dlg.set_anchor(getattr(feat, "anchor", "bottom"), getattr(feat, "anchor_gap", 0.0), getattr(feat, "host_length", None))
        before = doc.step_states.get(index, {}).get(feat.target_body_id) if feat.target_body_id else None
        host = feat.measure_host(before) if before is not None and feat.host_length is not None else None
        dlg.set_host(host, feat.follow_host)
        if not dlg.exec():
            return False
        vals = dlg.get_values()
        return doc.edit_feature(index, **vals)
    QMessageBox.information(win, "Edit", f"{feat.name} can't be edited here yet.")
    return False


def confirm_delete(win, doc, index: int) -> bool:
    deps = doc.dependents_of(index)
    names = ", ".join(doc.timeline.features[i].name for i in deps)
    text = f"Delete {doc.timeline.features[index].name}?"
    if deps:
        text += f"\n\nThese steps are built on it and will be deleted too:\n{names}"
    return QMessageBox.question(win, "Delete step", text) == QMessageBox.StandardButton.Yes
