"""Shell feature: hollows out solid bodies."""

from typing import List, Dict, Any, Optional
import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature


class ShellFeature(Feature):
    """Hollows out a 3D solid body, optionally opening selected faces. direction: "inside" (wall grows inward by
    `thickness`), "outside" (wall grows outward by `thickness`) or "both" (`thickness` inward and `thickness2` outward)."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        thickness: float = 2.0,
        open_faces: Optional[List[Dict[str, Any]]] = None,
        direction: str = "inside",
        thickness2: float = 2.0,
    ):
        super().__init__(feature_id, "shell", name)
        self.target_body_id = target_body_id
        self.thickness = float(thickness)
        self.open_faces = list(open_faces or [])
        self.direction = direction if direction in ("inside", "outside", "both") else "inside"
        self.thickness2 = float(thickness2)

    def wall_sizes(self):
        """(inward, outward) wall thickness in mm."""
        if self.direction == "outside":
            return 0.0, self.thickness
        if self.direction == "both":
            return self.thickness, self.thickness2
        return self.thickness, 0.0

    @staticmethod
    def _grow(m, t):
        """The body with every surface moved outward by t. Convex bodies keep sharp corners (planes moved out
        and intersected); anything else is grown with a ball, which rounds its outer edges."""
        from omacad.model.faces import compute_planar_faces
        try:
            hull = m.hull() if hasattr(m, "hull") else None
        except Exception:
            hull = None
        if hull is not None and not hull.is_empty() and abs(hull.volume() - m.volume()) < 1e-6 * max(1.0, m.volume()):
            bb = np.array(m.bounding_box())
            size = float(np.max(bb[3:] - bb[:3])) + 4 * t + 10
            ctr = (bb[:3] + bb[3:]) / 2.0
            out = m3d.Manifold.cube((size, size, size), True).translate(tuple(ctr))
            for f in compute_planar_faces(m):
                n = np.asarray(f.normal, dtype=float)
                d = float(n @ np.asarray(f.origin, dtype=float)) + t
                out = out.trim_by_plane(tuple(-n), -d)   # keeps the side where -n.x >= -d, i.e. n.x <= d
            if not out.is_empty():
                return out
        return m.minkowski_sum(m3d.Manifold.sphere(t, 24))

    @classmethod
    def compute_shell(cls, body, thickness: float, direction: str = "inside", thickness2: float = 2.0, open_faces: Optional[list] = None):
        """Hollows out a manifold body with wall thickness and optional open faces. Returns new Manifold or None."""
        if direction == "outside":
            t_in, t_out = 0.0, float(thickness)
        elif direction == "both":
            t_in, t_out = float(thickness), float(thickness2)
        else:
            t_in, t_out = float(thickness), 0.0

        if t_in <= 0.001 and t_out <= 0.001:
            return body

        # 1. The empty space: eroded by inside wall (or body itself for outside-only)
        cavity = body
        if t_in > 0.001:
            try:
                cavity = body.minkowski_difference(m3d.Manifold.sphere(t_in, 24))
            except Exception as e:
                print(f"ShellFeature Minkowski difference error: {e}")
                return None
            if cavity.is_empty() or cavity.volume() < 1e-6:
                return None

        # 2. Outer skin: grown by outside wall
        outer = body
        if t_out > 0.001:
            try:
                outer = cls._grow(body, t_out)
            except Exception as e:
                print(f"ShellFeature grow error: {e}")
                return None

        # 3. Open faces: sweep cavity out through open face
        open_faces = list(open_faces or [])
        for f in open_faces:
            nf = np.array(f.get("normal", [0, 0, 1]), dtype=float)
            ln = float(np.linalg.norm(nf))
            if ln > 1e-6 and t_out > 0.001:
                nf = nf / ln
                df = float(nf @ np.array(f.get("origin", [0, 0, 0]), dtype=float))
                outer = outer.trim_by_plane(tuple(-nf), -df)

        sweep = cavity
        total = t_in + t_out + 1.0
        for f in open_faces:
            norm = np.array(f.get("normal", [0, 0, 1]), dtype=float)
            ln = float(np.linalg.norm(norm))
            if ln < 1e-6:
                continue
            norm = norm / ln
            bb = np.array(cavity.bounding_box())
            ext = float(np.abs(norm) @ (bb[3:] - bb[:3]))
            step = max(0.25 * ext, 0.2)
            k = 1
            while k * step < total + step:
                sweep = sweep + cavity.translate(tuple(norm * min(k * step, total)))
                k += 1

        # 4. Wall = outer skin minus empty space
        try:
            shelled = outer - sweep
            if not shelled.is_empty() and shelled.volume() > 1e-6:
                return shelled
        except Exception as e:
            print(f"ShellFeature boolean subtraction error: {e}")
        return None

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        shelled = self.compute_shell(target.manifold, self.thickness, self.direction, self.thickness2, self.open_faces)
        if shelled is not None:
            target.manifold = shelled
            target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "thickness": self.thickness,
            "direction": self.direction,
            "thickness2": self.thickness2,
            "open_faces": self.open_faces,
        }
