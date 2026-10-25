"""Object history presentation and editing helpers for the browser."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtGui import QColor
from omacad.ui.timeline_bar import FeatureNodeWidget
from omacad.model.feature_parameters import parameter_unit


ROLE = Qt.ItemDataRole.UserRole
FEATURE_ROLE = ROLE + 1


def add_histories(browser, root):
    doc = browser.doc
    history = doc.object_history
    history.sync(doc)
    group = QTreeWidgetItem(root, ['Objects', ''])
    group.setData(0, ROLE, ('group', 'objects'))
    group.setExpanded(True)
    excluded = history.excluded()
    features = {f.feature_id: f for f in doc.timeline.features}
    for oid, obj in history.objects.items():
        if obj.parent_id is None:
            _add_object(browser, group, oid, features, excluded)
    # An unfinished sketch has not yet become a feature.
    sk = doc.active_sketch
    if sk and not any(f.feature_type == 'sketch' and f.sketch.sketch_id == sk.sketch_id for f in features.values()):
        node = QTreeWidgetItem(group, ['✏️ ' + sk.name, ''])
        node.setData(0, ROLE, ('sketch', sk.sketch_id))


def _add_object(browser, group, oid, features, excluded):
    """One object's history; objects a Combine used up hang under that Combine as branches."""
    doc = browser.doc
    history = doc.object_history
    obj = history.objects[oid]
    children = history.children(oid)
    label = obj.name
    parent = QTreeWidgetItem(group, [label, ''])
    parent.setData(0, ROLE, ('object', oid))
    parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsEditable)
    parent.setExpanded(True)
    font = parent.font(0)
    font.setBold(oid == history.active_id)
    parent.setFont(0, font)
    parent.setToolTip(0, 'Active object' if oid == history.active_id else 'Click to activate this object')
    if obj.origin_feature_id in features:
        link = QTreeWidgetItem(parent, ["🔗 " + features[obj.origin_feature_id].name, ""])
        link.setData(0, ROLE, ("feature_link", obj.origin_feature_id))
    for fid in obj.feature_ids:
        feat = features[fid]
        icon = FeatureNodeWidget.FEATURE_ICONS.get(feat.feature_type, '⚙️')
        node = QTreeWidgetItem(parent, [icon + ' ' + feat.name, ''])
        node.setData(0, ROLE, ('feature', fid))
        node.setData(0, FEATURE_ROLE, fid)
        if feat.feature_type == 'sketch':
            node.setData(0, ROLE, ('sketch', feat.sketch.sketch_id))
            browser._style_eye(node, feat.sketch.visible)
            for dim in feat.sketch.dimensions:
                unit = '°' if dim.dim_type == 'ANGLE' else 'mm'
                row = QTreeWidgetItem(node, [f'{dim.name or dim.dim_type}: {dim.expr or f"{dim.value:g}"} {unit}', ''])
                row.setData(0, ROLE, ('dimension', (feat.sketch.sketch_id, dim.dim_id)))
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
                row.setToolTip(0, f'{dim.value:g} — double-click to edit')
            from omacad.model.sketch import SketchText
            for entity in feat.sketch.entities:
                if isinstance(entity, SketchText):
                    row = QTreeWidgetItem(node, ['🔤 ' + entity.text.replace('\n', ' ')[:24], ''])
                    row.setData(0, ROLE, ('sketch_text', f'{feat.sketch.sketch_id}:{entity.entity_id}'))
        else:
            node.setFlags(node.flags() | Qt.ItemFlag.ItemIsEditable)
            for key in doc.EDITABLE.get(feat.feature_type, ()):
                value = getattr(feat, key, None)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or key in ('profile_idx', 'segments'):
                    continue
                formula = feat.exprs.get(key)
                shown = f'{formula} = {value:g}' if formula else f'{value:g}'
                row = QTreeWidgetItem(node, [f'{key.replace("_", " ").capitalize()}: {shown} {parameter_unit(key)}'.rstrip(), ''])
                row.setData(0, ROLE, ('parameter', (fid, key)))
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
                row.setToolTip(0, 'Double-click to edit this parameter or expression')
        if feat.error:
            node.setForeground(0, QColor('#e06c75'))
            node.setToolTip(0, feat.error)
        if feat.suppressed or fid in excluded:
            node.setForeground(0, QColor('#858585'))
            node.setToolTip(0, 'Suppressed' if feat.suppressed else 'After history marker / blocked by dependency')
        branches = children.get(fid, [])
        for child in branches:
            _add_object(browser, node, child, features, excluded)
        for dep in history.dependencies.get(fid, []):
            if history.owners.get(dep) not in (oid, *branches) and dep in features:
                link = QTreeWidgetItem(node, ['🔗 ' + features[dep].name, ''])
                link.setData(0, ROLE, ('feature_link', dep))
        if history.markers.get(oid, object()) == fid:
            QTreeWidgetItem(parent, ['● History marker — later steps paused', ''])
    # Current geometry stays separately selectable for export and body tools.
    for bid in obj.body_ids:
        body = doc.bodies.get(bid)
        if body is None:
            continue
        item = QTreeWidgetItem(parent, ['🧊 ' + body.name, ''])
        item.setData(0, ROLE, ('body', bid))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        browser._style_eye(item, body.visible)
        item.setSelected(body.selected)
    if oid not in history.markers:
        end = QTreeWidgetItem(parent, ['● End of history', ''])
        end.setData(0, ROLE, ('history_end', oid))


def find_feature(browser, feature_id):
    for item, _ in browser._walk():
        if item.data(0, FEATURE_ROLE) == feature_id:
            parent = item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
            browser.tree.setCurrentItem(item)
            browser.tree.scrollToItem(item)
            return True
    return False


def edit_parameter(browser, kind, item_id):
    for item, _ in browser._walk():
        if item.data(0, ROLE) == (kind, item_id):
            browser.tree.editItem(item, 0)
            return
