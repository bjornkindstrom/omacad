"""Jar with Lid: builds a threaded jar and its screw lid as ordinary history steps (cylinders, Combine, Shell, Thread,
Offset Face, Move), the way they are made by hand, so every step can be edited afterwards in the timeline.

The lid is the jar's neck and thread cut out of a cylinder (Combine cut, keep tool); Offset Face on the thread then
gives the lid its tolerance (minus = looser), and the neck's bore is cut away so no plug is left in the lid."""

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, List

PROFILES = ("trapezoidal_45", "round", "iso_60")
UP = dict(plane_normal=[0.0, 0.0, 1.0], plane_u=[1.0, 0.0, 0.0], plane_v=[0.0, 1.0, 0.0])
GAP_BESIDE = 10.0     # mm between the jar and the lid laid out for printing


@dataclass
class JarSpec:
    diameter: float = 40.0        # outside of the jar and the lid
    height: float = 40.0          # the jar up to its shoulder (the neck comes on top)
    wall: float = 2.0             # jar wall and bottom
    neck_diameter: float = 32.0   # the neck the thread sits on
    neck_height: float = 10.0     # also the thread's length
    pitch: float = 4.0
    profile: str = "trapezoidal_45"
    tolerance: float = -0.2       # Offset Face on the lid's thread: minus = more room (looser)
    lid_top: float = 2.0          # thickness of the lid's top
    lid_beside: bool = True       # the lid upside down beside the jar, ready to print; off: screwed on

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JarSpec":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def lid_wall(self, tooth: float = 0.0) -> float:
        """The lid's wall outside the thread (and its tolerance). `tooth` is the thread's radial height."""
        return (self.diameter - self.neck_diameter) / 2.0 - tooth - max(0.0, -self.tolerance)

    def problems(self, tooth: float = 0.0) -> List[str]:
        """What makes this jar impossible or fragile (empty: fine). `tooth` is the thread's radial height."""
        out = []
        if self.neck_diameter / 2.0 - self.wall < 0.5:
            out.append("The neck is too narrow for the wall: no opening is left.")
        lid_wall = self.lid_wall(tooth)
        if lid_wall < 0.8:
            out.append(f"The lid's wall outside the thread is only {lid_wall:.1f} mm: "
                       "make the jar wider or the neck narrower.")
        if self.height <= self.wall:
            out.append("The jar is not taller than its bottom.")
        return out


def thread_tooth(spec: JarSpec) -> float:
    """Radial height of the thread on the neck."""
    from omacad.model.kernel import CadKernel
    coil = CadKernel.create_thread(spec.neck_diameter, spec.pitch, spec.neck_height, profile=spec.profile,
                                   include_core=False, attached_to_cylinder=True)
    lo, hi = coil.bounding_box()[:3], coil.bounding_box()[3:]
    return max(0.0, max(hi[0] - lo[0], hi[1] - lo[1]) / 2.0 - spec.neck_diameter / 2.0)


def build_jar(doc, spec: JarSpec) -> Dict[str, str]:
    """Adds the steps to `doc` (call it inside one undoable Document method). {"jar": body id, "lid": body id}."""
    h, top = spec.height, spec.height + spec.neck_height
    jar = doc.add_cylinder(spec.diameter / 2.0, h, name="Jar")
    neck = doc.add_cylinder(spec.neck_diameter / 2.0, spec.neck_height, name="Neck", plane_origin=[0.0, 0.0, h], **UP)
    doc.combine_bodies(jar.body_id, neck.body_id, "join")
    doc.add_shell(jar.body_id, spec.wall, open_faces=[{"normal": [0.0, 0.0, 1.0], "origin": [0.0, 0.0, top],
                                                     "body_id": jar.body_id}])
    doc.add_thread(spec.neck_diameter, spec.pitch, spec.neck_height, profile=spec.profile, clearance=0.0, target_body_id=jar.body_id,
                   operation="join", name="Jar thread", plane_origin=[0.0, 0.0, h], host_length=spec.neck_height, **UP)
    thread = doc.timeline.features[-1]
    lid = doc.add_cylinder(spec.diameter / 2.0, spec.neck_height + spec.lid_top, name="Lid", plane_origin=[0.0, 0.0, h], **UP)
    doc.combine_bodies(lid.body_id, jar.body_id, "cut", keep_tool=True)
    # the neck is hollow, so the cut leaves its bore standing in the lid: cut it away (inside the neck's wall, so
    # no face of it coincides with the lid's)
    bore = doc.add_cylinder(spec.neck_diameter / 2.0 - spec.wall / 2.0, spec.neck_height, name="Lid bore",
                            plane_origin=[0.0, 0.0, h], **UP)
    doc.combine_bodies(lid.body_id, bore.body_id, "cut")
    if abs(spec.tolerance) > 1e-9:
        doc.add_offset_face(lid.body_id, [{"kind": "thread", "thread_id": thread.feature_id, "sign": -1,
                                           "shift": [0.0, 0.0, 0.0]}], spec.tolerance)
    if spec.lid_beside:   # upside down (its top on the bed) beside the jar
        doc.move_body(lid.body_id, dx=spec.diameter + GAP_BESIDE, dz=-h, rx=180.0)
    return {"jar": jar.body_id, "lid": lid.body_id}
