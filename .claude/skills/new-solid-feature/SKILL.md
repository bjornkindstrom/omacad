---
name: new-solid-feature
description: Checklist for adding a new solid feature (Feature class, undoable Document method, dialog, preview) to Omacad. Use when building a new timeline feature such as Hole, Loft or Sweep.
---
# Ny solid-funktion i Omacad

1. `Feature`-klass i `omacad/model/timeline.py` med `execute(doc)` och `to_dict()`.
2. En rad i feature-fabriken i `exporter.apply_dict` (`omacad/io/exporter.py`).
3. `Document.add_*` med `@undoable("Namn")` i `omacad/model/document.py`. Skicka `exprs` hela vägen från dialog till `Document`.
4. En post i `Document.EDITABLE` om funktionen ska gå att redigera.
5. Ikon i `omacad/ui/timeline_bar.py`.
6. Dialog i `omacad/ui/dialogs.py` (fält tar ingen `doc`).
7. `prompt_*` i `omacad/ui/main_window.py` med live-förhandsvisning via `viewport.set_preview`.
8. Test i `tests/` med **exakt** förväntat värde (volym mot formel eller shapely).
9. Referera profiler/kanter geometriskt (`ProfileRefs`, `fuzzy_edge_from_ref`), aldrig med löpnummer. Jämför kanter med `same_as`.
10. Efteråt: rad överst i `docs/SOLUTIONS.md`, `CHANGELOG.md` (engelska), versionshöjning i `omacad/__init__.py`.
