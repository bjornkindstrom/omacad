"""
Omacad - Import, Export & Project Persistence
Exports 3D solids to STL / OBJ formats and saves/loads .omacad project files.
"""

import json
import os
from typing import Optional
import trimesh
from omacad.model.document import Document, Parameter
from omacad.model.timeline import (Body, SketchFeature, BoxFeature, CylinderFeature, SphereFeature,
                                    ExtrudeFeature, RevolveFeature, CombineFeature, FilletFeature, PatternFeature)
from omacad.model.sketch import Sketch


class Exporter:
    """Handles STL / OBJ export and document persistence."""

    @staticmethod
    def export_body_to_stl(body: Body, filepath: str) -> bool:
        """Exports a single solid body to an STL file."""
        if not body.render_mesh or len(body.render_mesh.vertices) == 0:
            return False

        mesh = body.manifold.to_mesh()
        tm = trimesh.Trimesh(
            vertices=mesh.vert_properties[:, :3],
            faces=mesh.tri_verts,
            process=False
        )
        tm.export(filepath, file_type="stl")
        return True

    @staticmethod
    def export_body_to_obj(body: Body, filepath: str) -> bool:
        """Exports a single solid body to an OBJ file."""
        if not body.render_mesh or len(body.render_mesh.vertices) == 0:
            return False

        mesh = body.manifold.to_mesh()
        tm = trimesh.Trimesh(
            vertices=mesh.vert_properties[:, :3],
            faces=mesh.tri_verts,
            process=False
        )
        tm.export(filepath, file_type="obj")
        return True

    @staticmethod
    def export_all_to_stl(doc: Document, filepath: str) -> bool:
        """Combines all visible bodies and exports to STL."""
        meshes = []
        for b in doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                m = b.manifold.to_mesh()
                tm = trimesh.Trimesh(
                    vertices=m.vert_properties[:, :3],
                    faces=m.tri_verts,
                    process=False
                )
                meshes.append(tm)

        if not meshes:
            return False

        combined = trimesh.util.concatenate(meshes)
        combined.export(filepath, file_type="stl")
        return True

    @staticmethod
    def save_project(doc: Document, filepath: str) -> bool:
        """Saves parametric timeline and sketches to an Omacad (.omacad) JSON file."""
        data = {
            "name": doc.name,
            "units": doc.units,
            "parameters": [{"name": q.name, "expr": q.expr, "comment": q.comment} for q in doc.parameters],
            "timeline": [dict(f.to_dict(), exprs=dict(f.exprs)) for f in doc.timeline.features],
            "sketches": [s.to_dict() for s in doc.sketches.values()],
            "construction_planes": doc.construction_planes,
            "sections": doc.sections,
        }
        # write to a temp file first so an interrupted save never leaves a half-written project
        tmp = f"{filepath}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, filepath)
        return True

    @staticmethod
    def load_project(filepath: str) -> Document:
        """Loads an Omacad project from disk."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc = Document(data.get("name", "Omacad - Project"))
        doc.units = data.get("units", "mm")
        doc.parameters = [Parameter(q["name"], q["expr"], q.get("comment", "")) for q in data.get("parameters", [])]

        doc.construction_planes = dict(data.get("construction_planes", {}))
        doc.sections = dict(data.get("sections", {}))

        # Load sketches
        for s_data in data.get("sketches", []):
            sketch = Sketch.from_dict(s_data)
            doc.sketches[sketch.sketch_id] = sketch

        # Load timeline features
        for f_data in data.get("timeline", []):
            ft = f_data.get("feature_type")
            fid = f_data.get("feature_id")
            fname = f_data.get("name")
            if ft == "box":
                feat = BoxFeature(
                    fid, fname, f_data["length"], f_data["width"], f_data["height"], f_data["center"]
                )
                doc.timeline.add_feature(feat)
            elif ft == "cylinder":
                feat = CylinderFeature(
                    fid, fname, f_data["radius"], f_data["height"], f_data["center"]
                )
                doc.timeline.add_feature(feat)
            elif ft == "sphere":
                feat = SphereFeature(fid, fname, f_data["radius"])
                doc.timeline.add_feature(feat)
            elif ft == "sketch":
                sk = Sketch.from_dict(f_data["sketch"])
                doc.sketches[sk.sketch_id] = sk
                feat = SketchFeature(fid, fname, sk)
                doc.timeline.add_feature(feat)
            elif ft == "extrude":
                feat = ExtrudeFeature(
                    fid, fname, f_data["sketch_id"], f_data["profile_idx"], f_data["distance"], f_data["operation"],
                    f_data.get("direction", "one_side"), f_data.get("distance2", 0.0),
                    extra_profiles=f_data.get("extra_profiles", [])
                )
                doc.timeline.add_feature(feat)
            elif ft == "revolve":
                feat = RevolveFeature(fid, fname, f_data["sketch_id"], f_data["profile_idx"],
                                      f_data.get("segments", 48), f_data.get("operation", "new_body"))
                doc.timeline.add_feature(feat)
            elif ft == "fillet":
                feat = FilletFeature(fid, fname, [tuple(e) if e and isinstance(e[0], str) else (e[0], e[1]) for e in f_data["edges"]],
                                     f_data["size"], f_data.get("kind", "fillet"))
                doc.timeline.add_feature(feat)
            elif ft == "pattern":
                feat = PatternFeature(fid, fname, f_data.get("source_ids", []), f_data.get("kind", "linear"),
                                      **{k: f_data[k] for k in ("axis1", "count1", "spacing1", "axis2", "count2", "spacing2",
                                                                 "mirror_mode", "about", "angle") if k in f_data})
                doc.timeline.add_feature(feat)
            elif ft == "combine":
                feat = CombineFeature(fid, fname, f_data["target_body_id"], f_data["tool_body_id"],
                                      f_data.get("operation", "join"))
                doc.timeline.add_feature(feat)
            else:
                continue
            feat.suppressed = f_data.get("suppressed", False)
            feat.exprs = dict(f_data.get("exprs", {}))

        doc.timeline.recompute(doc)
        doc.notify_changed()
        return doc
