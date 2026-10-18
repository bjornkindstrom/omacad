# Omacad: guide för AI-agenter

Läs den här filen först. Den är minnet för alla agenter (Claude, Codex, OpenCode, ...) som arbetar i det här repot: vad programmet är, hur koden hänger ihop, reglerna, och **lösningsloggen** med varje fel vi redan rättat och varför. Håll den uppdaterad: efter varje rättning lägger du till en rad i lösningsloggen (se längst ned).

## Vad Omacad är
Ett native parametriskt 3D-CAD för Omarchy Linux (Python 3.14, PySide6/Qt6 + OpenGL, `manifold3d` för solider, `shapely` för 2D, SolveSpace för skissvillkor). Mål: bete sig som Fusion 360 där det går, och dessutom vara **smartast och snabbast**, inte störst (se `PLAN.md`). Användaren pratar svenska; kod, commit-meddelanden och `CHANGELOG.md` är på engelska, `README.md` på svenska.

**Principer (bryt dem inte):**
1. Inget får gå sönder och användaren ska alltid kunna backa. Allt som ändrar dokumentet är ett ångra-steg. Arbete får aldrig försvinna.
2. Lean, clean, unbreakable: små moduler, inga dubbletter, inga tysta `except: pass` som döljer fel, varje fel har ett test.
3. Efterlikna Fusion 360 (kolla dess hjälpsidor innan du bygger en funktion) och lägg gärna till en smart genväg som Fusion saknar.
4. Pusha, bygg eller publicera aldrig utan att användaren ber om det.

## Köra, testa, släppa
```bash
./run.sh                                   # kör appen (.venv/bin/python app.py)
.venv/bin/python -m pytest tests/test_<feature>.py -q --tb=short  # under arbetet: testet du skriver
.venv/bin/python tools/pick_tests.py       # före commit: 3-4 utvalda testfiler för ändringen (sekunder, inte minuter)
```
- **Kör inte helsviten** (118 filer, ~8 min). `tools/pick_tests.py` tar ändrade testfiler + de tester som nämner ändrade funktioner/moduler (`--list` visar bara valet, `<commit>` testar en commit). Helsviten körs av CI vid push; kör den lokalt bara om användaren ber om det.
- Kör GUI-tester en i taget; överlappande testfönster kan ge falska renderingsfel (hämta testets egen dialog med `w.window() is win`, inte första i `app.allWidgets()`). Upprepa inte gröna kontroller utan ny ändring eller kvarstående osäkerhet.
- Version: `omacad/__init__.py`. **Supersmå steg:** varje ändring, rättning som funktion, höjer bara sista siffran i fyrdelad version (0.9.9 → 0.9.9.1 → 0.9.9.2 …). Hoppa aldrig till 0.9.10, 0.10 eller **1.0**; det beslutar bara användaren ("ok"). Skriv i `CHANGELOG.md` och uppdatera `README.md`/`ROADMAP.md`/`PLAN.md`.
- Push till `main` kör CI: testjobb (`tests/`), sedan Windows-EXE och en release `v<version>` (+ `latest`). Push med `git -c credential.helper= -c credential.helper='!gh auth git-credential' push`.
- Sajtsidan `/omacad/` ligger i `~/Work/kindstrom-site` (databas + `Publicera`), uppdateras per minor-version.
- Commit-meddelanden slutar med de attribueringsrader som sessionen anger.

## Problemrapporter från appen
Användaren trycker **F9 / "Report problem"** i appen. `omacad/feedback.py` skriver en mapp i `~/.local/share/omacad/feedback/<tid>/` med skärmbilder, `document.omacad` + `document.json`, `report.json`, `log.txt` och `PROMPT.md`, och startar Omarchys standardagent via `omarchy agent prompt`. Gör så: titta på bilderna, reproducera från dokumentet, hitta rotorsaken, rätta, lägg ett regressionstest i `tests/`, kör testerna, skriv i lösningsloggen, commita.

## Omstart på ny version
`omacad/session.py` + `MainWindow.start_restart_watch/restart_app/restore_session`: appen jämför `git rev-parse HEAD` var 3:e sekund; ny commit => sparar dokument, öppen skiss och kamera i `~/.local/share/omacad/session.json`, startar `app.py --resume` och stänger sig. Efter en rättning (commit) startar alltså appen om av sig själv, så **commita först när testerna är gröna**. Inställningen `auto_restart` stänger av det.

## Kodkarta
| Modul | Ansvar |
|---|---|
| `omacad/model/document.py` | `Document`: bodies, sketches, timeline, parametrar, plan, snitt, canvases, **ångra/gör om** (`snapshot`/`restore`, `@undoable`), alla `add_*`/`edit_*` |
| `omacad/model/timeline.py` | `Feature`-klasser (Box, Extrude, Revolve, Fillet, Pattern, Shell, Hole, Move, Split, DeleteBody, ImportMesh ...) och `Timeline.recompute` som bygger om allt från början |
| `omacad/model/kernel.py` | `CadKernel`: bool-operationer, fillet/chamfer-verktyg (`edge_round_tool`, `circle_round_tool`, `loop_round_tool`), render-mesh |
| `omacad/model/faces.py` | Plana ytor/kanter ur en mesh: `PlanarEdge`, `CircularEdge`, `LoopEdge`, `compute_planar_edges`, `match_edge`, `fuzzy_edge_from_ref` |
| `omacad/model/sketch.py` | `Sketch` och entiteter (linje, cirkel, båge, slot, ...), profiler (`solve_profiles`), offset, mirror, `include_reference_edges` |
| `omacad/model/sketch_offset.py`, `sketch_trim.py`, `sketch_snap.py`, `sketch_solver.py` | Offset av linje/båge-kedjor, Trim, snäpp, SolveSpace-villkor |
| `omacad/model/expr.py` | Formler/parametrar i alla fält |
| `omacad/io/exporter.py` | `.omacad` (JSON), `document_to_dict`/`apply_dict`, STL/OBJ/STEP/3MF |
| `omacad/ui/viewport.py` | OpenGL-vyn, all musstyrning, skissverktygen (stor fil, ska delas upp, se `PLAN.md`) |
| `omacad/ui/main_window.py`, `ribbon.py`, `browser.py`, `timeline_bar.py`, `side_panel.py`, `dialogs.py` | Fönster, band, träd, tidslinje, verktygspaneler |
| `omacad/feedback.py`, `applog.py` | Problemrapporter och loggen som följer med dem |
| `tests/` | pytest: exakta volymer, ångra, offset, rapporter |

## Mönster att följa
- **En ny solid-funktion** = en `Feature`-klass i `timeline.py` med `execute(doc)` och `to_dict()`, en rad i feature-fabriken i `exporter.apply_dict`, en `Document.add_*` med `@undoable("Namn")`, en post i `Document.EDITABLE` om den ska gå att redigera, en ikon i `timeline_bar.py`, en dialog (`dialogs.py`) och en `prompt_*` i `main_window.py` som visar live-förhandsvisning via `viewport.set_preview`.
- **Ett nytt skissverktyg**: `set_sketch_tool(NAMN)` i viewporten, ett press-block i `mousePressEvent` (före fillet-blocket), hovring i `mouseMoveEvent`, tangent i `keyPressEvent`, ribbonknapp i `ribbon.py` och synk i `main_window.sync_sketch_tool_from_viewport`.
- **Ångra**: allt som ändrar dokumentet går genom en `Document`-metod med `@undoable`. Redigeringar inne i en skiss använder `before = sketch.to_dict(); ...; doc.record_sketch_change(sketch, before)`.
- **Historiken är sanningen**: kroppar byggs om av `Timeline.recompute`; efter varje ändring byts `Body`-objekten ut, hämta dem på nytt. Kanter lagras som koordinatreferenser och hittas igen med `edge_from_ref`/`fuzzy_edge_from_ref`.
- Ytor och profiler: en yta är "kurvig" först när den har minst två grunda grannar (en mild knyck mellan två väggar är fortfarande plan).
- Nya funktioner ska ha ett test med **exakt** förväntat värde (volym mot formel eller shapely), inte bara "ser rätt ut".

## Guider i appen (Help > Guides)
En guide = mappen `omacad/guides/<id>/` med `guide.json` (`id`, `title`, `steps`: `text` + `image`) och små JPEG:er. Läses av `omacad/guide.py`, visas av `ui/guide_dialog.py` (`GuideWindow`: eget fönster, `MainWindow.show_guide(id)`; `GuideBox`: liten ruta inbäddad i en verktygspanel med Back/Next/Hide och knappen Bigger som öppnar `GuideWindow` (900 px) vid samma steg, se `OffsetFaceDialog.guide_box`; använd text på knapparna, inga ◀▶⤢-tecken: de ritas som tomma rutor i appens typsnitt), Help > Guides listar alla automatiskt, och en knapp i ett verktyg anropar `show_guide("<id>")` (se `OffsetFaceDialog.btn_guide`). Texten är engelska (appens språk). **Bildbudget (bryt den inte):** max 900 px bred, JPEG, högst 120 KB per bild, högst 2,5 MB totalt; gör bilderna med `tools/guide_image.py SRC.png omacad/guides/<id>/N.jpg [--crop x,y,w,h]` (skalar och sänker kvaliteten själv), aldrig PNG eller skärmdumpar i full storlek. `tests/test_guides.py` vaktar budgeten. `omacad.spec` packar mappen. Bra guidebild = riktiga appen i full skärm, `vp.grabFramebuffer()`/`w.grab()`; för "klicka här"-bilder: prova klick på ett rutnät med `vp._offset_face_click` och rita färgade prickar (grönt = fungerar). Skriv en kort rad i lösningsloggen när en guide läggs till.

## Testa GUI-saker
Kör på den riktiga skärmen (Wayland); offscreen ger ingen GL-kontext. Sätt `QSurfaceFormat` med depth 24 före `QApplication`, vänta ~1,5 s efter `show()`, använd små former (vyn är bara ca 410 px bred eftersom inspektören tar resten) och rikta vyn med `align_to_plane` före musklick. `QTest.mouseMove` är opålitlig här: anropa `mouseMoveEvent` direkt vid behov. Ändra aldrig det riktiga temat i tester (peka `theme.COLORS_FILE` på en tema-fil i stället). Modal dialog som blockerar: ersätt `prompt_dimension_value` med en lambda.

## Lösningslogg (5 senaste; äldre historik i `SOLUTIONS_LOG.md` — sök med `grep_search`, läs inte hela!)
- **Chamfer-kanten gick inte att markera** (0.9.9.23, via F9): skalad burk med hals, gänga och Circular pattern av inpressade slitsar; insidans kanter vid halsens ansats (z 38, r 18 och r 14) gick inte att klicka. Booleanerna lämnade nollyte-trianglar längs fogen, så `_circular_edges` fick ett dussin korta bågar med luckor (och brusiga centrum/`s1` ur enskilda tunna trianglar). Nu röstar alla segment om `s1`, och `_join_arcs` slår ihop bågar av samma cirkel när meshens punkter på cirkeln täcker luckan (inte glesare än en facett, så ett riktigt hak förblir en lucka) och passar om cirkeln mot dem. Att läsa topologin ur `Manifold.simplify(1e-6)` gav också hela cirklar men slog ihop andra modellers ytor (två kanttester föll). Test: `test_shoulder_edge_slivers.py`.
- **Circular pattern raderade gängan** (0.9.9.22, via F9): burk med gänga, 12 inpressade slitsar (Emboss + Chamfer) i Circular pattern. Kroppen räknades som rund (`_round_about` mäter medeltjockleken på det en rotation lämnar, och hundratals facettflisor drog ned gängans 0,22 mm till 0,03), så hela kroppen skars ned till snittet av alla rotationer, och en helix är inte rund. Att bara skärpa gränsen hjälpte inte: vanlig cut-väg ger hårstrimmor, och att lägga tillbaka det icke-runda fastnade på hinnor med noll volym. Nu gäller avskärningen bara höjdbandet som kopiorna upptar (`PatternFeature._outside_band`). Test: `test_circular_pattern_on_threaded_jar_keeps_the_thread`.
- **Primitive flyttas före placering** (0.9.9.20): vänsterdrag på förhandsvisningen flyttar primitive i kamerans plan; måtthandtagen behåller sin dimensionering. Förskjutningen sparas i Box/Cylinder/Hexagon/Sphere-featuret och följer spara/ladda och ångra.
- **Move förbättrat** (0.9.9.20): Move Feature har `copy_body`, som skapar en separat kopia i historiken utan att flytta originalet; den följer spara/ladda och undo. Preview med Activate copy visar originalet bredvid den flyttade kopian. Point to point snappar även till centrum på kroppens över- och undersida (plana ytor eller kurviga extrempunkter) och hittar punkterna igen efter ombyggnad. Face-to-face visar originalet medan sidorna väljs så källsidan går att klicka, döljer gizmon under valet och accepterar båda klickordningarna. Lay on ground döljer gizmon, visar kroppen under face-pick och lägger klickad sida plant mot XY. Högerklick i Move väljer kroppen som target; högerklick på plan yta kan även starta Move för hela kroppen. Dialogen saknar redundant Active handle-rad och döljer gizmon under punktplockning.
- **CI röd: fillet/chamfer hittade inte sina kanter** (0.9.9.19): 0.9.9.16 växte *varje* cut-verktyg 1 nm, så vanliga snitt fick nanometersteg (14 kanter i stället för 13) och `test_fill_face_chamfer`, `test_fillet_face_pick`, `test_wrapped_fillet` föll i CI (ingen EXE). Nu gör `combine_with_bodies` exakt snitt och 1 nm-snitt och tar 1 nm-varianten bara om den har färre trianglar (remsor upplösta) eller exakta snittet har hinnor; trådfallets remsor är inte hinnor, så `has_sheets` räcker inte ensam. Bisecta med en `git worktree` när CI fallerar efter flera commits.
