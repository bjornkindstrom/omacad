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
.venv/bin/python -m pytest tests -q        # testsviten, ca 20 s, måste vara grön före varje commit
```
- Version: `omacad/__init__.py` (0.x tills "komplett CAD" = 1.0). Höj patch för rättningar, minor för funktioner, skriv i `CHANGELOG.md` och uppdatera `README.md`/`ROADMAP.md`/`PLAN.md`.
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

## Testa GUI-saker
Kör på den riktiga skärmen (Wayland); offscreen ger ingen GL-kontext. Sätt `QSurfaceFormat` med depth 24 före `QApplication`, vänta ~1,5 s efter `show()`, använd små former (vyn är bara ca 410 px bred eftersom inspektören tar resten) och rikta vyn med `align_to_plane` före musklick. `QTest.mouseMove` är opålitlig här: anropa `mouseMoveEvent` direkt vid behov. Ändra aldrig det riktiga temat i tester (peka `theme.COLORS_FILE` på en tema-fil i stället). Modal dialog som blockerar: ersätt `prompt_dimension_value` med en lambda.

## Lösningslogg (rotorsak och rättning, nyast överst)
- **Rektangel med radie direkt** (0.6.2, önskemål via F9): fanns bara rektangel + Fillet i två steg. Nytt verktyg `ROUNDED_RECT` (`Sketch.add_rounded_rect` = `add_rect` + `fillet_corner` på de fyra hörnen, radien begränsas till under halva korta sidan; radien kommer från `spn_corner_radius` i skisspaletten). Förhandsvisningen använder `Sketch.rounded_rect_outline`.
- **Fillet vid foten av ett rundat block** (0.5.2): endast de raka bitarna fylldes, hörnbågen saknades. `_loop_edges` kände bara igen yttre kanter (väggen faller under ytan). Nu även inre (väggen reser sig): `LoopEdge.convex=False`, `loop_round_tool` fyller material.
- **Rutmarkering i skiss** (0.5.1): vänsterdrag på tom yta roterade vyn. Nu rutmarkering (vänster→höger fönster, höger→vänster korsande); Alt+drag roterar.
- **Hack vid foten av rundade hörn** (0.4.1): fillet-verktyget förlängdes 1 µm förbi kanten och skar in i underliggande block. `FilletFeature._free_ends` förlänger bara där det är fritt utrymme.
- **Inre hörn vid fasning av kontur** (0.4/0.5): två band mötte inte vid reflexhörn. Snittet av de två oändligt förlängda verktygen läggs till som hörnverktyg.
- **Kanter som hoppades över efter ändrad historik** (0.5): refererades med absoluta koordinater. `fuzzy_edge_from_ref` tar närmaste kant av samma slag.
- **Mild knyck lästes som kurva** (0.5): en yta med en enda grund granne räknades som kurvig, så väggarna blev varken valbara eller skissbara. Kräver nu minst två grunda grannar.
- **Cirkelfillet med dubbelt så många trianglar** (0.5): `revolve` använde 96 segment mot cylinderns 48. Verktyget följer nu kantens `nseg`.
- **Offset gav brutna streck vid bågar** (0.6.x): bågar och linjer offsettades var för sig. `sketch_offset.py` offsettar hela kedjor, bågarna behåller centrum och ändrar radie, fogarna räknas om.
- **Shift+klick i skiss panorerade** (0.5.0): navigeringsblocket sköttes före markeringen. Shift/Ctrl+klick växlar nu ett element (se `mousePressEvent`).
- **Shell kraschade på OK** (0.4.2): `add_shell` tog inte emot `exprs`. Parametrar måste föras hela vägen från dialog till `Document`.
- **Move Body-dialogen kraschade** (0.4.2): `ExprDoubleSpinBox(doc)` gav dokumentet som förälder. Fälten tar ingen `doc`.
- **Canvas-bilden blev kvar** (0.4): texturen cachades på id (`canvas_1`) och återanvändes. Cachen nycklas nu på bilddatan.
- **`delete_body` kom tillbaka** (0.6.0): kroppen togs bara bort ur `doc.bodies`; nästa omräkning byggde den igen. Nu ett eget steg i tidslinjen (`DeleteBodyFeature`).
- **`Manifold.revolve` ger tom kropp** om tvärsnittet går medurs. Vänd alltid till moturs.
- **Ångra ändrade bara skisser** (0.6.0): `Document.undo` var bara för skisser. Hela dokumentet ångras nu via `snapshot`/`restore` (på plats, lyssnarna behålls).

## Kända begränsningar
Fillet saknas för koner och delbågar. Mönster, ytskisser och offset-plan är absoluta (följer inte kroppen, se S8 i planen). Bågar och slots finns inte i skisslösaren. Hole har modell men ännu ingen dialog. Se `PLAN.md` för vad som kommer.
