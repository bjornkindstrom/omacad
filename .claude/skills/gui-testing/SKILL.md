---
name: gui-testing
description: How to write and run GUI tests for Omacad (real Wayland screen, GL context, mouse events). Use when a test needs the viewport, dialogs or mouse input.
---
# Testa GUI-saker i Omacad

- Körs på den riktiga skärmen (Wayland). Offscreen ger ingen GL-kontext, och molnsessionen har ingen skärm.
- Sätt `QSurfaceFormat` med depth 24 före `QApplication`. Vänta ca 1,5 s efter `show()`.
- Använd små former: vyn är bara ca 410 px bred (inspektören tar resten).
- Rikta vyn med `align_to_plane` före musklick.
- `QTest.mouseMove` är opålitlig: anropa `mouseMoveEvent` direkt.
- Ändra aldrig det riktiga temat: peka `theme.COLORS_FILE` på en tema-fil.
- Modal dialog som blockerar: ersätt `prompt_dimension_value` med en lambda.
- Kör bara berörd fil: `.venv/bin/python -m pytest tests/test_x.py -q -x --tb=short`.
