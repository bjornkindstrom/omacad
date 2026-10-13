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
- **Trädstruktur för kroppar/skisser, markering i 3D, samt Shell live preview och skissrensning** (0.7.3, via feedback):
  1. Skisser skapade på en yta av en viss solid kropp kopplas automatiskt med `parent_body_id` och grupperas under kroppen i Model Browser. Fristående skisser (på XY, XZ, YZ eller plan) stannar i skiss-grenen.
  2. Klick med vänster musknapp i 3D-viewporten markerar kroppen och aktiverar den i dialoger som Move, Split och Shell.
  3. Shell döljer förbrukade skisser och ger direkt interaktiv 3D-förhandsvisning med `compute_shell` och färgmarkering för öppna ytor. Test i `tests/test_shell_preview_and_sketches.py`.
- **Direktinmatning på Extrude** (0.7.2): Fokus och markering sätts direkt i avståndsfältet, numeriska tangenttryck i 3D-vyn vidarebefordras till dialogen. Test i `tests/test_extrude_direct_typing.py`.
- **Fillet skar genom motsatt vägg vid överdriven radie, måttbrickor skymde geometri, knappstorlek i inställningar** (0.7.1, via F8/F9):
  1. `FilletFeature._safe_edge_size` begränsar radien/fasningen på konvexa raka kanter till 99 % av minsta avståndet till angränsande ytors hål och väggar, så en överdriven fillet inte skär förbi intilliggande kanter. Test i `tests/test_fillet_clearance_limit.py`.
  2. Måttbrickor för cirkel-mot-linje förskjuts nu utanför cirkelns radie längs referenslinjen istället för att lägga brickan direkt över cirkelns omkrets.
  3. Smart cirkel: `Document._anchor_for` använde målpunkten istället för referenslinjen för `PT_LINE_DIST`, vilket ledde till att hela skissen flyttades från origo vid ändrat mått. Rättat och testat i `tests/test_smart_circle_tool.py`.
  4. Ny inställning `button_scale` i Settings (75 %, 100 %, 125 %, 150 %) med dynamisk omskalning av ikoner, text och knappar i menybandet.
  5. Tog bort onödig dubblerad "BROWSER"-rubrik inuti trädpanelen.
- **Mirror hittade inget att kopiera** (0.6.29, via F9): dialogen kryssar steg från senaste skissen, och när hålet ligger i profilen som skapar kroppen fanns ingen kropp före första steget (`before is None` => `compute` gav None). `PatternFeature._enclosed_voids` tar nu det som saknas i kroppens bounding box och inte når sidorna (hål, fasning) som det som ska kopieras. Test i `tests/test_mirror_first_extrude.py` (dokumentet från rapporten).
- **Fyllmönstret höll för stort avstånd till hål och kroppar** (0.6.27, via F9): `_fill_funcs` insatte hela ytan med `margin`, och hål/bossar är hål i ytan, så de fick marginalen också. Nu gäller `margin` bara ytterkanten (`outline.buffer(-margin)`); inre hål och hinder (`all_obs`) får bara `gap`. Test i `tests/test_fill_pattern_clearance.py` (dokumentet från rapporten).
- **Bredd på rundad rektangel ändrade bara en vägg** (0.6.26, via F9): bågar är inte solver-entiteter, så villkoren linje–båge hoppades över och bara väggen flyttades. `solve_sketch` anropar nu `Sketch.refit_fillets` som sätter hörnet till linjernas skärning och bygger om bågen (`_update_fillet_arc`) med bågens radie. Test i `tests/test_rounded_rect_outer_size.py`.
- **F9-skärmbilden saknade måtten** (0.6.24, via F9): `QWidget.grab()` ritar bara GL-scenen i en `QOpenGLWidget`, inte `QPainter`-överlägget (mått, banner, ViewCube). `MainWindow.grab_with_overlay` lägger `grabFramebuffer()` ovanpå fönsterbilden; `screenshot_view.png` hade alltid allt. Test i `tests/test_report_screenshot.py`.
- **Direkt inmatning av extrude-värde** (0.7.2, via F9): När Extrude startas eller en profil klickas i vyn behöll vyn eller dockningspanelen fokus så textrutan inte var aktiv för direkt skrivning. `ExtrudeDialog.focus_distance` sätter fokus på `spn_dist.lineEdit()` och väljer texten (`selectAll`); `MainWindow.prompt_extrude` anropar `dlg.focus_distance` direkt och via `singleShot(0)` efter visning och profilklick; och tangenttryckningar för siffror/formler i `Viewport3D.keyPressEvent` vidarebefordras direkt till verktygets avståndsfält. Test i `tests/test_extrude_direct_typing.py`.
- **Polygoner följde med vid extrude** (0.6.16, via F9, svar: skisser i samma plan, ska kunna väljas bort): fanns ingen automatik, men en profil med andra skisser inuti extruderades fylld och Shift+klick ville bara ha samma skiss. `ExtrudeFeature.detect_holes` hittar profiler i andra synliga skisser i samma plan som ligger inuti valet och sparar dem som `holes` (skiss, index, signatur), så synligheten påverkar inte ombyggnad; `extra_refs` är Shift+klickade profiler från andra skisser. `ExtrudeFeature.selection_parts` ger allt tre från markeringen, `Viewport3D._selection_fill` ritar markeringen utan hålen. Rapport 182106 (spretiga kanter överst på åttkanten) kunde inte avgöras ur bilden: topp-fillet ger enstaka sliverlösa trianglar (`area < 1e-5`), men inget som ger fel normaler; väntar på ritad markering.
- **Rundhet bröt modellen** (0.6.15, via F9): `ExtrudeFeature`/`RevolveFeature` pekar på `profile_idx`, och numreringen av en skisss profiler ändras med antal segment i cirklarna. `ProfileRefs` (timeline.py) sparar (centrum, area) per profil och hittar den igen i `resolve_profile_refs`, som körs först i `build_solid`. Äldre filer saknar signaturer: `Exporter._seed_profile_refs` läser dem vid sparat `curve_segments` (48 om nyckeln saknas) och sparar signaturerna, sen räknas skisserna om med dagens rundhet. Lärdom: en referens med löpnummer till något som räknas om är skör; spara alltid något geometriskt att matcha mot.
- **Rapporter 2026-10-12 kväll** (0.6.12): foten av en polygonvägg fylleteras med raka kanter (`FilletFeature._mitred_foot_tool`): grannkanter på samma golv förlängs förbi hörnet och kapas längs bisektrisen med `trim_by_plane`, annars blev det ett hack i varje hörn (bara konvexa hörn hade hörnlogik förut). Fyllmönstret (`_fill_funcs`) klippte kopior mot hål mitt på ytan; nu får bara ytterkanten klippa, kopior som rör ett hål utelämnas helt (`clear_of_holes`). Rundhet: `model/quality.py` styr segment för cirklar, bågar, cylinder och sfär; inställningen `curve_segments` skjuts in av `SettingsManager`, ändring bygger om modellen (`MainWindow.rebuild_for_curve_quality`). Tester som räknade med 48 segment läser nu `quality.circle_segments()`.
- **Rapporter 2026-10-12** (0.6.11): siffran på extrudepilen försvann vid släpp (ritades bara medan `_handle_drag`; nu `show_value` på handtaget, bara Extrude använder det, Move-pilens längd är ingen sträcka). Spinbox-knappar utan stil blev tomma rutor; `theme._BASE_CSS` har nu `::up-button/::down-button` och pilbilder som `theme._arrow_png` ritar i temats textfärg. Axelknapparna i Move hade långa etiketter ("X (Röd)") som klipptes; nu X/Y/Z i axelfärg. Esc: `MainWindow` har en QShortcut som skickar Esc till `Viewport3D.keyPressEvent` oavsett fokus. `Document.lay_face_on` använder `geometry.euler_xyz_degrees` (samma ordning som `Manifold.rotate`).
- **Tidslinjeklick visar stegets ändring** (0.6.8, önskemål): `Document.step_changes(i)` tar skillnaden mellan `step_states[i]` och `[i+1]` (tillagt/borttaget material); `TimelineBar.highlight_changed` skickar det till `viewport.set_preview` (grönt join, rött cut). Rensas vid nästa dokumentändring eller andra klicket. Test i `tests/test_step_highlight.py`.
- **Knasig kant när en fotfillet var för stor** (0.6.7, via F9): fillet vid foten av en vägg (`LoopEdge.convex=False`) fyller ovanför planet och räknar med plan yta under sig. Hade en kantfillet redan ätit upp hyllan hängde verktyget som en tunn list över rundningen. `CadKernel.foot_fill_tool` kontrollerar att verktyget vilar på kroppen och minskar annars radien (bisektion) till den största som får plats, så rundningarna löper ut i varandra. Test i `tests/test_foot_fillet.py` (dokumentet från rapporten). Gäller än så länge bara slingor, inte raka fotkanter.
- **Vyn ovanifrån hoppade vid orbit** (0.6.6): över 89° höjd byttes kamerans upp-vektor till världens Y oavsett azimut, så bilden rullade upp till 90° på en gång. `math3d.orbit_view` använder alltid Z som upp (höjden är begränsad till ±89,9°); test i `tests/test_orbit_view.py`.
- **Skiss på yta hade världsorigo och marknät** (0.6.5, önskemål via F9): `SketchPlane.from_face` lägger origo vid världsorigo projicerat på planet och rutnätet ritades alltid på marken. Ytskisser använder nu `SketchPlane.centered_on(face.tris)` (origo = ytans mitt, så ORIGIN-snäppet låser mitten; kanter/hörn/mittpunkter snäpptes redan) och `viewport.render_plane_grid` ritar ett nät på planet, centrerat och anpassat till ytans storlek.
- **Centrerad rounded rectangle + palett i inspektören** (0.6.4, önskemål via F9): nytt verktyg `CENTER_ROUNDED_RECT` (`Sketch.add_center_rounded_rect` speglar hörnet runt centrum och anropar `add_rounded_rect`; finns i `RECT_TOOLS`). Skisspaletten flyttades från flytande över vyn till toppen av `InspectorPanel` (`set_palette` + `SketchPalette.embed`, `place_default` gör inget när den är inbäddad).
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
- **Fill pattern med polygoner**: `_best_pattern` i timeline.py söker tätaste gitter via K=(hull−hull)+gap (u, v, v−u på randen); udda polygoner testar även par med en 180°-vänd kopia. Hull måste vara moturs (`orient`) för att kantnormalen ska peka ut.

## Kända begränsningar
Fillet saknas för koner och delbågar. Mönster, ytskisser och offset-plan är absoluta (följer inte kroppen, se S8 i planen). Bågar och slots finns inte i skisslösaren. Hole har modell men ännu ingen dialog. Se `PLAN.md` för vad som kommer.
