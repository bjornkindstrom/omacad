import json

from omacad import applog, feedback
from omacad.model.document import Document


def test_bundle_has_everything_the_agent_needs(tmp_path):
    d = Document()
    d.add_box(10, 20, 30)
    applog.log("test", "something happened")
    folder = feedback.build_bundle(d, "the corner looks wrong", {"screenshot_view.png": b"\x89PNG"}, {"camera": {"azimuth": 40}}, base_dir=tmp_path)
    names = {p.name for p in folder.iterdir()}
    assert {"screenshot_view.png", "document.json", "document.omacad", "report.json", "log.txt", "PROMPT.md"} <= names
    rep = json.loads((folder / "report.json").read_text())
    assert rep["note"] == "the corner looks wrong" and rep["camera"] == {"azimuth": 40}
    assert rep["undo_history"] == ["Box"] and list(rep["bodies"].values())[0]["volume"] == 6000.0
    assert "something happened" in (folder / "log.txt").read_text()
    prompt = (folder / "PROMPT.md").read_text()
    assert "the corner looks wrong" in prompt and "omacad.md" in prompt and str(folder) in prompt


def test_bundle_survives_a_document_that_cannot_be_saved(tmp_path, monkeypatch):
    from omacad.io.exporter import Exporter
    d = Document()
    d.add_box(1, 1, 1)
    monkeypatch.setattr(Exporter, "save_project", staticmethod(lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))))
    folder = feedback.build_bundle(d, "x", base_dir=tmp_path)
    assert (folder / "document.json").exists() and (folder / "PROMPT.md").exists()


def test_agent_command_points_at_the_prompt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback.shutil, "which", lambda name: "/usr/bin/omarchy")
    cmd = feedback.agent_command(tmp_path)
    assert cmd[:3] == ["omarchy", "agent", "prompt"] and f"{tmp_path}/PROMPT.md" in cmd[3]
    monkeypatch.setattr(feedback.shutil, "which", lambda name: None)
    assert feedback.agent_command(tmp_path) is None


def test_bundle_is_small_for_the_agent(tmp_path):
    d = Document()
    d.add_box(10, 20, 30)
    for i in range(200):
        applog.log("test", f"line {i}")
    applog.log("ERROR", "Traceback (most recent call last):\n  boom")
    folder = feedback.build_bundle(d, "x", base_dir=tmp_path)
    assert len((folder / "log.txt").read_text().splitlines()) <= 80
    errors = (folder / "errors.txt").read_text()
    assert "boom" in errors and "line 1" not in errors
    assert "\n " not in (folder / "document.json").read_text()      # compact, not indented
    prompt = (folder / "PROMPT.md").read_text()
    assert "errors.txt" in prompt and "Do NOT open `document.json`" in prompt
