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

## Guider i appen (Help > Guides)
En guide = mappen `omacad/guides/<id>/` med `guide.json` (`id`, `title`, `steps`: `text` + `image`) och små JPEG:er. Läses av `omacad/guide.py`, visas av `ui/guide_dialog.py` (`GuideWindow`: eget fönster, `MainWindow.show_guide(id)`; `GuideBox`: liten ruta inbäddad i en verktygspanel med Back/Next/Hide och knappen Bigger som öppnar `GuideWindow` (900 px) vid samma steg, se `OffsetFaceDialog.guide_box`; använd text på knapparna, inga ◀▶⤢-tecken: de ritas som tomma rutor i appens typsnitt), Help > Guides listar alla automatiskt, och en knapp i ett verktyg anropar `show_guide("<id>")` (se `OffsetFaceDialog.btn_guide`). Texten är engelska (appens språk). **Bildbudget (bryt den inte):** max 900 px bred, JPEG, högst 120 KB per bild, högst 2,5 MB totalt; gör bilderna med `tools/guide_image.py SRC.png omacad/guides/<id>/N.jpg [--crop x,y,w,h]` (skalar och sänker kvaliteten själv), aldrig PNG eller skärmdumpar i full storlek. `tests/test_guides.py` vaktar budgeten. `omacad.spec` packar mappen. Bra guidebild = riktiga appen i full skärm, `vp.grabFramebuffer()`/`w.grab()`; för "klicka här"-bilder: prova klick på ett rutnät med `vp._offset_face_click` och rita färgade prickar (grönt = fungerar). Skriv en kort rad i lösningsloggen när en guide läggs till.

## Testa GUI-saker
Kör på den riktiga skärmen (Wayland); offscreen ger ingen GL-kontext. Sätt `QSurfaceFormat` med depth 24 före `QApplication`, vänta ~1,5 s efter `show()`, använd små former (vyn är bara ca 410 px bred eftersom inspektören tar resten) och rikta vyn med `align_to_plane` före musklick. `QTest.mouseMove` är opålitlig här: anropa `mouseMoveEvent` direkt vid behov. Ändra aldrig det riktiga temat i tester (peka `theme.COLORS_FILE` på en tema-fil i stället). Modal dialog som blockerar: ersätt `prompt_dimension_value` med en lambda.

## Lösningslogg (5 senaste; äldre historik i `SOLUTIONS_LOG.md` — sök med `grep_search`, läs inte hela!)
- **Guide lines (konstruktionslinjer) ritades heldragna** (0.7.9.59, via F9): `render_mixin` ritade `construction_lines` med `draw_thick_lines` rakt av. Nu skärs de upp i streck av konstant pixelstorlek med `dash_lines` (fasen fortsätter över korta segment så cirklar/bågar blir jämna). Test: `tests/test_dashed_construction.py`.
- **Bokstavsdelar (e, o, a, å, ä, ö) föll bort vid redigering av skiss-text + anti-frys + Arc/Slot-mått + SplitBody-edit** (0.7.9.57, request #44): När höjd, typsnitt eller text i en `SketchText` ändrades kunde `solve_profiles()` byta plats på ytterprofilen och innerhålet i t.ex. `e`, så `Emboss`/`Extrude` valde hålet. `ProfileRefs` i `model/features/base.py` spårar nu `_follows_text` och synkroniserar automatiskt med `sketch.text_profile_indices()` när en `SketchText` redigerats. Dessutom: 50–60 ms `QTimer`-debounce + `quality.set_interactive_mode(True)` i `feature_edit.py` och `tool_prompts.py`, förberäknade kanter i `_preview_fillet`, snabb Ray–AABB-filtrering i `picker_mixin.py`, VAO/VBO-cache-städning i `render_mixin.py`, `EQUAL`-radie-writeback för `SketchCircle` i `sketch_solver.py`, måttsättning av `SketchArc` (`RADIUS`) och `SketchSlot` (`LENGTH`/`DIAMETER`), full timeline-edit för `SplitBody`/`Shell`/`Combine`/`Thread`, samt rename av `cplane` i Browser. Test: `tests/test_improvement_plan.py`.
- **Start Offset i mm för Extrude, Smart Box/Cylinder, full 360° cylinder-wrap i Emboss, enklare textredigering & live 3D-preview i Timeline** (0.7.9.55–0.7.9.56, #31/#35/#38/#40/#42/#43): `ExtrudeFeature.start_offset` förskjuter extruderingens startplan längs skissnormalen; `BoxFeature`/`CylinderFeature` fick `wall_thickness`, `outer_round`/`inner_round` (fillet/chamfer); `EmbossFeature` fick `wrap` (båglängdsmappning runt cylindrar >180°/360°); `SketchText` kan klickas inne i bokstäver/bbox, har Edit Text-knapp i Sketch Palette och egna rader i Browser; `feature_edit._exec_with_preview` ger live 3D-förhandsvisning för alla steg i tidslinjen. Test: `tests/test_improvement_plan.py`.
- **Svart tooltip i tidslinjen, klippta knappar och städad Settings** (0.7.9.53–0.7.9.54, #39/#41): `TimelineBar.scroll_area`, `BrowserWidget` och `InspectorPanel` hade selektorlösa `style(..., "border: none; background: transparent;")`. I Qt gäller en selektorlös QSS-regel på *alla* underliggande widgets — även `QTipLabel` (tooltip-fönstret skapas med den hovrade widgeten som parent) — vilket gav `RGBA(0,0,0,0)` på en top-level popup och därmed en kolsvart ruta. Scopade till `QScrollArea`, `QWidget#BrowserWidget`, `QWidget#InspectorPanel`, `QFrame#TimelineChip` och `QWidget#TimelineBar`, samt lade `QToolTip` i `_MENU_CSS`/`_BASE_CSS`. Minskade `QPushButton`-padding så dialogknappar inte klipps vid hög DPI, tog bort dubletten av `Toolbar button size` i `SettingsDialog` och gjorde *Theme Editor* till en knapp (`ThemeEditorDialog`) under *Appearance*.
- **Egen bild i RFC/F9-dialogen** (0.7.9.52, önskemål): `FeedbackDialog.choose_own_image/use_builtin_image/own_image` (+ `MarkableImage.set_pixmap`); `MainWindow.on_request_change` och rapportfunktionen skickar då bara `screenshot_own.png` (med ritade markeringar) i stället för de inbyggda skärmbilderna. Test: `tests/test_feedback_own_image.py`.
- **Emboss omslöt inte cylindern** (0.7.9.51, via F9): `EmbossFeature` extruderade från skissplanet, så text på ett plan framför en cylinder (23,5 mm från YZ, R=20) hängde i luften. Nu `_surface_behind` strålar från texten mot skissnormalen (`faces.ray_mesh_hit` mot alla kroppar) och hittar yttre cylinder (`detect_cylinder_surface`) eller plan yta parallell med skissen. Cylinder: `_wrapped` = prisma från axelns nivå ∩ koaxial cylinder r+djup (Emboss) eller skalet r+marginal..r-djup (Deboss); plan yta: bokstäverna startar på ytan. Gäller inte flip och inte hål (invändig cylinder) eller sneda ytor: de faller tillbaka på gamla beteendet. Test: `tests/test_emboss_wrap.py`.
