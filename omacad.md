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
| `omacad/model/faces.py` | Kompatibilitetsfasad för yt-/kantanalys, referensmatchning och träfftester |
| `omacad/model/faces_topology.py`, `faces_surfaces.py`, `faces_edges.py`, `faces_refs.py`, `faces_hit_tests.py`, `faces_types.py` | Topologiklassning, ytanalys, kant-/slingdetektion, kantreferenser, träfftester och geometriobjekt |
| `omacad/model/sketch.py` | `Sketch`, profiler, constraint-/dimensionsdata och kompatibla exports för skiss-API:t |
| `omacad/model/sketch_entities.py` | Skissplan, geometri-entiteter (linje, cirkel, båge, slot, text) och entitetsoperationer |
| `omacad/model/sketch_offset.py`, `sketch_trim.py`, `sketch_snap.py`, `sketch_solver.py` | Offset av linje/båge-kedjor, Trim, snäpp, SolveSpace-villkor |
| `omacad/model/expr.py` | Formler/parametrar i alla fält |
| `omacad/io/exporter.py` | `.omacad` (JSON), `document_to_dict`/`apply_dict`, STL/OBJ/STEP/3MF |
| `omacad/ui/viewport/viewport.py` | `Viewport3D`: OpenGL-vy och stabil publik widget; rendering, pickning och skissverktyg |
| `omacad/ui/viewport/events_mixin.py` | Tangentbordsflöde, zoomhjul och dubbelklick i viewporten; blandas in i `Viewport3D` |
| `omacad/ui/viewport/measure_mixin.py` | Mätverktygets val, avståndsberäkning, kommando och overlay |
| `omacad/ui/viewport/sketch_operation_mixin.py`, `dimension_overlay_mixin.py` | Trim/mirror/fillet-interaktion samt dimensionsritning och inmatning |
| `omacad/ui/viewport/context_menu_mixin.py` | Högerklicksmenyer för skisser, profiler, kanter, ytor och plan |
| `omacad/ui/viewport/sketch_tools_mixin.py` | Skissentiteters pickning/redigering, dynamiska mått och Smart Circle |
| `omacad/ui/viewport/pointer_mixin.py` | Mustryck och pekarrörelse för skiss-, plocknings- och kameraflöden |
| `omacad/ui/viewport/profile_mixin.py`, `sketch_move_mixin.py`, `sketch_dimensions_mixin.py` | Profilförhandsvisning, skissflytt och constraints/måttsättning |
| `omacad/ui/main_window.py`, `ribbon.py`, `browser.py`, `timeline_bar.py`, `side_panel.py`, `dialogs.py` | Fönster, band, träd, tidslinje, verktygspaneler |
| `omacad/ui/controllers/tool_prompts.py` | Kompatibilitetsfasad som samlar grupperade prompt mixins för MainWindow |
| `omacad/ui/controllers/*_prompts.py` | Separata promptflöden för skiss/plan, solider, primitiver, kroppar, mönster/round och canvas |
| `omacad/ui/controllers/file_session.py`, `menu_setup.py` | Fil-/sessionsflöden och uppbyggnad av huvudmenyn |
| `omacad/ui/theme.py`, `theme_icons.py`, `theme_styles.py` | Tema-state och Qt-styling, ikonrendering respektive återanvändbara QSS-strängar |
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
- **Redigera steg: förhandsvisning och Auto** (0.9.9.42): `feature_edit` byggde primitivernas förhandsvisning utan `translation`, läste tomt `doc.step_states` direkt efter `add_*` (ingen förhandsvisning), lät Auto i Extrude/Revolve-edit bestämma mot kropparna *efter* steget (med extrusionen själv: join blev cut) och svalde förhandsvisningsfel. Nu: `edit_feature` räknar om om tillstånden saknas, `_StateBefore` ger kropparna före steget (med ytor) till `resolve_operation`, extra profiler/hål följer med, fel loggas och visas. `refresh_parameters`/`edit_feature` avrundar heltalsfält och håller `sides >= 3`. Test: `test_edit_preview_ui.py`, `test_edit_step_values.py`.
- **Nya steg vid markören: fel steg fick formlerna** (0.9.9.41): efter 0.9.9.32 hamnar ett nytt steg vid markören, men prompterna satte `exprs` på `timeline.features[-1]`, Extrude läste Auto-resultatet därifrån, `build_jar` tog gängan därifrån och Shell/Pattern-förhandsvisningen räknade läget som `len(features)`. Nu används `Timeline.last_added` (steget före markören) och `marker_index`. Test: `test_insert_at_marker_ui.py`.
- **Text-sessionen tog med annat skissarbete** (0.9.9.40): `_TextSession` tog `sketch.to_dict()` vid start; Cancel körde `restore_from_dict(before)` (raderade linjer ritade under tiden) och OK la ett ångra-steg vars before föregick dem. Nu tar Cancel bort bara den placerade texten (eller återställer den redigerade textens inställningar, `orig`), OK:s ångra-steg byggs av nuläget med bara texten som före (`before_text`), och byte till ett annat skissverktyg efter placering gör OK först. Test: `test_text_tool.py`.
- **Delete, tidslinje och solidverktyg under ett öppet verktyg** (0.9.9.39): Delete raderade valda kroppar medan Shell/Move arbetade på dem (och i skissläge utan valda element), tidslinjens knappar och Edit byggde om kropparna under verktyget, och Extrude m.fl. öppnade i skissläge där profiler inte går att plocka. Nu stoppar `on_delete_selected` och `TimelineBar._blocked` (via `busy_reason` = `MainWindow._busy_reason`, utom stegplockningen `feature_pick_handler` och Rename) med en statusrad, hovring bygger inte om, och `prompt_guards.leaves_sketch` avslutar skissen före solidverktygen. Test: `test_busy_guards_ui.py`.
- **Esc i ytplockande verktyg** (0.9.9.38): Shell, Offset Face, Honeycomb och Move plockar ytor så länge panelen är öppen; Esc körde bara `end_plane_pick(cancelled=True)`, panelen blev kvar utan plockning och statusraden sa "Create Sketch cancelled.". Nu skickar Esc `tool_cancel` när `plane_pick_purpose` är i `events_mixin.SESSION_PICKS` och en panel är öppen; `on_plane_pick_cancelled` namnger verktyget efter syftet. Test: `test_escape_pick_tools_ui.py`.
- **Förhandsvisning kom tillbaka efter OK** (0.9.9.37): Shell, Offset Face och Thread hade en debounce-`QTimer` som inte stoppades i `on_finished`; OK inom 60–75 ms efter en ändring körde förhandsvisningen efter städningen, dolde den ombyggda kroppen och lämnade en förhandsvisning kvar. Nu stoppas timern först i `on_finished`, och `_connect_debounced_preview` stoppar sin timer på `dlg.finished` för alla som använder den. Test: `test_preview_timer_ui.py`.
- **M och F i skissen gick till fel verktyg** (0.9.9.36): menyns genvägar M (Move Body) och F (Fit View) gäller hela fönstret och tog tangenten före viewportens `keyPressEvent`. Nu accepterar `SketchToolsMixin.event` `ShortcutOverride` för skisstangenterna (`events_mixin.SKETCH_KEYS`) när en skiss är aktiv och varken Ctrl eller Alt hålls nere; utanför skissen gäller menyns genvägar som förut. Test: `test_sketch_keys_ui.py`.
- **Ett andra verktyg strandade det första** (0.9.9.35): `SidePanel.dock_tool` dolde bara den öppna panelen, så dess `on_finished` körde aldrig: förhandsvisning, dold kropp (Shell), plockläge och `_extrude_dlg`/`_round_dlg` låg kvar, `_busy_reason` blockerade ångra och verktyget kunde inte öppnas igen. Nu gör `dock_tool` `reject()` på det öppna verktyget (som Cancel). Korta värderutor (`prompt_dimension_value`, `dlg._nested`) avslutar inte verktyget utan dockar tillbaka det efteråt. `QTimer.singleShot(0, dlg, dlg.focus_primary)` har dialogen som kontext så en borttagen panel inte får anropet. Test: `test_tool_switch_ui.py`.
- **Formel kraschade appen** (0.9.9.34): `expr._eval` lät `(-8)^(1/3)` ge ett komplext tal (TypeError) och `(64^64)^64` ett jätteheltal (OverflowError vid `isfinite`); anroparna fångar bara ValueError. Nu ger båda ValueError och varje BinOp-resultat görs till float direkt. Test: `test_expr_errors.py`.
- **Kurvkvalitet byggde inte om** (0.9.9.33): stegcachens fingeravtryck saknade `quality.circle_segments()`, så `rebuild_for_curve_quality` återställde gamla kroppar (en cylinder byggd med 48 segment hade kvar 96 hörn efter byte till 192). Nu ingår värdet i fingeravtrycket (även interaktivt läge, så lågupplösta förhandsbyggen aldrig återanvänds), och `apply_dict` tömmer cachen så att nya stegobjekt efter ångra kör igen (`ThreadFeature._effective`, `PatternFeature.copies` ...). Test: `test_timeline_cache.py`.
- **Nytt steg raderade senare steg** (0.9.9.32): `Timeline.add_feature` klippte bort allt efter markören när man lade till ett steg i en bakåtrullad historik. Nu infogas steget vid markören (som Fusion), markören står efter det, senare steg ligger kvar bakom markören, och cacheposterna från den positionen töms. Test: `test_timeline_cache.py`.
