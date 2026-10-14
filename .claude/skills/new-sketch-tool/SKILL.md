---
name: new-sketch-tool
description: Checklist for adding a new sketch tool to Omacad's viewport and ribbon. Use when creating a sketch tool such as a new rectangle, arc or slot variant.
---
# Nytt skissverktyg i Omacad

Viewportens kod ligger i mixins under `omacad/ui/viewport/*_mixin.py`.

1. `set_sketch_tool(NAMN)` i viewporten.
2. Press-block i `mousePressEvent`, **före** fillet-blocket.
3. Hovring i `mouseMoveEvent`.
4. Tangent i `keyPressEvent`.
5. Ribbonknapp i `omacad/ui/ribbon.py`.
6. Synk i `main_window.sync_sketch_tool_from_viewport`.
7. Geometrin som `Sketch.add_*` i `omacad/model/sketch.py`. Redigeringar går via `before = sketch.to_dict(); ...; doc.record_sketch_change(sketch, before)`.
8. Test med exakt värde (shapely-area eller koordinater).
9. Kör `uvx ruff check --select F821 omacad` (saknade importer i mixins är vanligt).
