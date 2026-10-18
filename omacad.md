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
- **Combine Cut skar fel kropp** (0.9.9.14, via F9): Locket (cylinder ovanpå burken) skulle skäras av Burk med Keep tool, men Burk skars. `CombineDialog._active_field` blev aldrig `"target"`, så klick i vyn bytte bara verktyget och målet stod kvar på första kroppen i listan. Nu: utan förval är första klicket mål, nästa verktyg (som Fusion), med en rad som säger vad man ska klicka; mål-listan avslutar också målsteget. Ny Combine visar live-förhandsvisning (målet döljs, verktyget syns så det går att klicka); `CadKernel.boolean_op` fanns inte, så redigeringens förhandsvisning föll tyst i `except` – nu finns den och `CombineFeature` använder den. Test: `test_combine_pick_order.py`.
- **Shell av staplade cylindrar följde inte den inre formen** (0.9.9.13, via F9): R20 H40 + R16 H6 ovanpå (Combine), Shell 2 mm inåt med lilla toppen öppen. Genvägen `_convex_base` skalade bara stora cylindern och lade tillbaka den lilla massiv (en propp); dessutom svepte öppna ytan hela den breda kaviteten uppåt genom den smala väggen. Nu: `_thicker_than` släpper genvägen när tillägget själv skulle urholkas (konvexa delar eroderas exakt, andra V/A > t), `_stacked_cavity` eroderar bas och konvexa delar med egna facettplan plus en fog med båda delarnas plan utom de limmade ytorna (skarpa hörn, exakt vägg). Öppen yta = `_face_region` (kroppens snitt strax under planet minus strax över, bara delen under klickpunkten) ∩ kavitetens snitt, extruderat med `_prism`; ytterskalet skärs bara över ytan (offset t_out), inte längs hela planet. Test: `test_shell_cylinder.py::test_shell_of_stacked_cylinders_follows_the_step`.
- **F8/F9 och Spara slutade fungera** (0.9.9.12): Shell-dialogens ytval (`ShellDialog.toggle_face`) bär det levande `_face`-objektet (för markeringen i vyn) och det följde med in i `ShellFeature.open_faces`, så `json.dumps` i `feedback.build_bundle`/`save_project`/sessionen kastade TypeError (rapportmappen fick bara skärmbilder). `open_faces` är nu en property som bara sparar nycklar utan `_`, även när `edit_feature` sätter attributet direkt. Test: `test_shell_face_pick.py::test_shell_with_picked_open_face_can_be_saved`.
- **CI hängde / EXE byggdes inte** (0.9.9.11): Testjobbet dödades (runner shutdown, exit 143) i `test_fill_pattern_room` från 0.9.9.6: kroppen bar ~865k mesh-relation-runs efter mönstret och `decompose()` i `drop_slivers` åt 7+ GB (med `ulimit -v` passerade det, så lokalt syntes det inte alltid). `drop_slivers` gör `as_original()` först; bygger åter från solida delar och skär ut negativa delar (hålrum) vända (att subtrahera flagor lämnade fenor: `test_mirror_no_fins`). `clean_difference` växer bara när `a - b` har hinnor (`has_sheets`: två riktiga trianglar rygg mot rygg), annars hamnar ytor 2e-6 ur plan och kantplock splittras (`test_fillet_face_pick`, `test_loop_edge_pick`). Felsök CI: `gh run view <id> --log-failed`; utskriften är buffrad, så punkternas antal pekar inte exakt ut testet.
- **Hårfina strimmor efter mönster** (0.9.9.6): Circular pattern av en lindad emboss på en cylinder gav hundratals lodräta strimmor (genus 704). `after - before` innehöll cylinderytan två gånger (före och efter embossen, olika triangulering, motsatt riktning) som nollvolym-hinnor ihopsatta med spåret; `drop_slivers` tar bara lösa bitar och `set_tolerance`/`simplify` hjälper inte. Hård regel: alla mönster tar skillnaden med `CadKernel.clean_difference(a, b)` = a − `grown(b, 1e-6)`, sedan `grown(.., 2e-6) ^ a` (når fortfarande kroppen). `grown` flyttar varje hörn så att varje yta runt det flyttas utåt (dämpad minsta-kvadrat, nålformade trianglar räknas inte, ett hörn som skulle dra en yta inåt, t.ex. en fena i kroppen, står still). Test: `test_circular_feature_pattern.py::test_circular_pattern_of_wrapped_emboss_has_no_hair_strips`, `::test_clean_difference_drops_coincident_surface_sheets`.
