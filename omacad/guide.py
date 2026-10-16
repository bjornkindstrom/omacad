"""In-app guides: a folder `omacad/guides/<id>/` with `guide.json` and small JPEG pictures (see tools/guide_image.py).

guide.json: {"id": "...", "title": "...", "steps": [{"text": "...", "image": "1.jpg"}, ...]}
Add one by making the folder; Help > Guides lists it. tests/test_guides.py keeps the pictures within the size budget.
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class GuideStep:
    text: str
    image: Optional[Path]


@dataclass
class Guide:
    guide_id: str
    title: str
    steps: List[GuideStep]


def guides_root() -> Path:
    """The guides folder next to the sources, or inside the packaged app."""
    here = Path(__file__).resolve().parent / "guides"
    frozen = Path(getattr(sys, "_MEIPASS", "")) / "omacad" / "guides" if getattr(sys, "_MEIPASS", None) else None
    return frozen if frozen is not None and frozen.is_dir() else here


def load_guide(folder: Path) -> Guide:
    data = json.loads((folder / "guide.json").read_text(encoding="utf-8"))
    steps = [GuideStep(s["text"], (folder / s["image"]) if s.get("image") else None) for s in data["steps"]]
    return Guide(data["id"], data["title"], steps)


def list_guides() -> List[Guide]:
    root = guides_root()
    if not root.is_dir():
        return []
    return [load_guide(d) for d in sorted(root.iterdir()) if (d / "guide.json").is_file()]


def find_guide(guide_id: str) -> Optional[Guide]:
    return next((g for g in list_guides() if g.guide_id == guide_id), None)
