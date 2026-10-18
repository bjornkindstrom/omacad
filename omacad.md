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
Användaren trycker **F10 / "Report problem"** (F9 hör till Omarchy) i appen. `omacad/feedback.py` skriver en mapp i `~/.local/share/omacad/feedback/<tid>/` med skärmbilder, `document.omacad` + `document.json`, `report.json`, `log.txt` och `PROMPT.md`, och startar Omarchys standardagent via `omarchy agent prompt`. Gör så: titta på bilderna, reproducera från dokumentet, hitta rotorsaken, rätta, lägg ett regressionstest i `tests/`, kör testerna, skriv i lösningsloggen, commita.

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

## Hjälp i appen (Help > Help & Commands, F1)
Bildguiderna är borttagna (Björns beslut). Hjälpen är `ui/help_dialog.py` (`HelpWindow`, `MainWindow.show_help`): alla funktioner grupperade som bandet, hjälptext, genväg och var den finns, sök på nyckelord (början av ord: "hole" hittar hål, inte "whole"), Enter/Run kör vald funktion. Innehållet byggs i `ui/help_topics.py`: kommandona kommer från `ui/commands.py` (ett nytt kommando hamnar i hjälpen automatiskt; `test_help_window.py` kräver hjälp för varje bandkommando), `MORE` ger längre text och sökord per kommando, `EXTRA` det som inte är bandkommandon (fil, vy, tidslinje, constraints, arbetssätt). Lägg till i `MORE`/`EXTRA` när en funktion behöver förklaras. Menyerna Create/Modify/Inspect visar kommandots tips när man håller musen över en post.

## Testa GUI-saker
Kör på den riktiga skärmen (Wayland); offscreen ger ingen GL-kontext. Sätt `QSurfaceFormat` med depth 24 före `QApplication`, vänta ~1,5 s efter `show()`, använd små former (vyn är bara ca 410 px bred eftersom inspektören tar resten) och rikta vyn med `align_to_plane` före musklick. `QTest.mouseMove` är opålitlig här: anropa `mouseMoveEvent` direkt vid behov. Ändra aldrig det riktiga temat i tester (peka `theme.COLORS_FILE` på en tema-fil i stället). Modal dialog som blockerar: ersätt `prompt_dimension_value` med en lambda.

## Lösningslogg (5 senaste; äldre historik i `SOLUTIONS_LOG.md` — sök med `grep_search`, läs inte hela!)
- **CI-testerna tog över 22 min + Extrude-pilen** (0.9.9.59): `MainWindow.apply_theme_font` satte appens font och stilmall vid varje nytt fönster, och Qt stylade då om alla widgets i alla levande fönster; testerna skapar ~150 fönster, så det femtionde tog 15 s (0,08 s per befintligt fönster). Nu sätts de bara när de ändras (temabyte gör fortfarande om dem), och hela sviten offscreen gick från 25 till 8 min. Hittat på vägen: `events_mixin.py` saknade `from omacad.model import quality` sedan uppdelningen av vyn, så släppet av Extrude-pilen kastade NameError (`test_no_undefined_names` föll). Test: `test_extrude_handle_release.py`.
- **Text In Box** (0.9.9.58, Björns önskemål): `SketchText.box` (bredd, höjd, centrerad på `anchor`) och `text_layout.fit_in_box` skalar texten (lagd vid höjd 1) så att bokstävernas egen kontur fyller rutan och centreras, så font-, text- och stilbyten passas in direkt (geometricachen har `box` i nyckeln). Två klick i vyn (`TextToolMixin._text_box_start`, rutan följer markören), panelen får typen "Text In Box" med höjdfältet skrivskyddat och visande `fitted_height`; rutan ritas streckad (`_render_text_boxes`). Sparas via `PARAMS`. Test: `test_text_tool.py`.
- **Close i hjälprutan** (0.9.9.57): Björn ville ha Close bredvid Run i Help & Commands (F1); `HelpWindow.btn_close` döljer fönstret. Test: `test_help_window.py`.
- **Hjälp & kommandon ersätter bildguiderna** (0.9.9.56, Björns beslut): `omacad/guides`, `guide.py`, `ui/guide_dialog.py`, `tools/guide_image.py`, Help > Guides och Offset Face-panelens guideruta borttagna. `ui/help_dialog.py` (`HelpWindow`, F1) visar `ui/help_topics.py`: kommandona ur registret med `MORE`-text och sökord plus `EXTRA` (fil, vy, tidslinje, constraints, arbetssätt). Sökningen matchar början av ord ("hole" träffade först "whole") och rangordnar namn, sökord, text; bästa träffen markeras så att Enter kör den, och skissverktyg kräver en öppen skiss. Menyerna har `setToolTipsVisible`. Test: `test_help_window.py`.
- **Report problem på F10** (0.9.9.55): Omarchy använder F9, så genvägen för Help > Report problem är nu F10 (meny, inställningstexter, README, guiden här). Test: `test_status_in_view.py`.
- **Fix Sketch** (0.9.9.54, Björns önskemål): `model/sketch_fix.py` hittar fria ändar (`free_ends`: ingen annan ände inom 1e-4 mm och inte på en annan kurva) och lagar i ordning, minsta ändring först: tar bort nollånga/dubbla linjer; fogar ihop ändar inom `_gap_tolerance` (3 % av ritningens storlek, minst 0,5 mm) — två linjer förlängs/kortas till sitt verkliga hörn (`_corner`), parallella flyttar den ände som rör sig längs sin linje (att mötas halvvägs snedställde hörnet), en båges ände står kvar — och lägger Coincident; förlänger en linjeände längs sin linje till en kurva den nästan når; stänger kvarvarande öppningar med linjer, närmaste par först, men inte svansar på kurvor som redan begränsar en yta (`_bounding_entities`). Ett ångra-steg via `record_sketch_change`. Test: `test_sketch_fix.py`.
- **Hjälptext för formler** (0.9.9.53, Björns önskemål): `ParameterList` har en grå, ej valbar hjälprad (`formula_hint`) med användarens eget parameternamn; ett helt utskrivet namn visar bara den raden med värdet. Bara när det finns namn att välja tar listan pilar/Enter/Tab (`has_choices`), så Enter efter ett helt namn trycker OK som vanligt; Esc stänger hjälpraden först. Samma i de dynamiska måttfälten. Tooltip och parameterdialogen har exempel (radius+2, test1+5*test3). Test: `test_parameter_typing_ui.py`.
- **Kors av fem punkter på cylindrar** (0.9.9.52, Björns önskemål): `body_points` gav bara centrum för en hel cirkel. Nu ger `circle_quadrants` fyra punkter (`kind "quadrant"`) där cirkeln korsar de två världsaxlar som ligger närmast dess plan (X och Y för en liggande cirkel), så de bildar ett kors med centrum. Rang efter kantändar och före dolda hörn (`_RANK`); punktvalet visar dem i gulgrönt och "circle quarter" i panelen. De hittas igen efter ombyggnad som andra punkter. Test: `test_body_points.py`.
- **Text som inte fick plats i panelerna** (0.9.9.51, Björn såg det i Move): panelen är ca 360 px bred men knappar, rullistor och kryssrutor hade långa (ibland svenska) texter, t.ex. "Lay a face on the ground…", "Body Center (Kroppens mitt)", "Välj yta / cylinder (Attach…)" (87 px mot 265). Nu korta namn och förklaringen i tooltip (`_add_placements` i `primitives_dlg.py`, `ToolTipRole` per val i Thread/Shell), och etiketter som kan bli långa radbryts. `test_panel_texts_fit_ui.py` öppnar alla femton verktygspaneler och mäter varje knapp, kryssruta, etikett och *varje* val i rullistorna (inte bara det som visas).
- **Move räknas om direkt** (0.9.9.50, Björns önskemål): förut flyttades bara förhandsvisningen tills OK, så nästa drag eller plockning utgick från kroppens gamla läge. Nu gör `apply_pending` i `prompt_move_body` ett riktigt Move-steg (`doc.move_body`, eget ångra-steg) när gizmon släpps och innan Point to point, Face to face eller Lay on ground börjar, nollställer panelen (`MoveBodyDialog.reset_motion`, en från-punkt som bara var pivot behålls) och fortsätter med kroppen där den är; en flyttad kopia läggs till i listan (`add_body`) och blir målet. Cancel/Esc behåller inlagda flyttar (ett slarvigt Esc ska inte radera arbete) och OK utan något kvar lägger inget tomt steg. Test: `test_move_applies_at_once_ui.py`.
- **Parameternamn startade genvägar + parameterlista + ƒx-markering** (0.9.9.49): menyns genvägar (E = Extrude, M, F, I) gäller hela fönstret; bokstäver som skrevs i 3D-vyn med en panel öppen (bara siffror skickades vidare) eller i de dynamiska måttfälten tog genvägen, så "e" i "depth" startade Extrude (och avslutade skissen). Nu avgör `EventsMixin._owns_key` (via `ShortcutOverride` i `SketchToolsMixin.event`) att vyn behåller skisstangenterna, alla bokstäver när måttfälten är öppna och bokstäver för panelens fält (`_types_into_panel`, X är fortfarande genomsikt vid kantval). `QCompleter` i `ExprDoubleSpinBox` matchade hela texten med " mm" och visades aldrig; nu filtrerar `ParameterList` på ordet före markören, får aldrig fokus, och fältet styr den (Upp/Ned, Enter/Tab väljer utan att trycka OK, Esc stänger). Samma lista under de dynamiska fälten (`_dyn_suggest`). Formelstyrda fält har egenskapen `formula` (blå text), skissmått `ƒx namn = värde` i blå ram, och tidslinjens chip "ƒx". Test: `test_parameter_typing_ui.py`.
