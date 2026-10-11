# Omacad ⚡

**Omacad** är ett native parametriskt 3D CAD-program för **Omarchy Linux** (Arch + Hyprland/Wayland), inspirerat av **Autodesk Fusion 360**.
Byggt med **Python 3.14**, **PySide6 (Qt6) + OpenGL**, **manifold3d** (vattentäta booleans), **shapely** och **SolveSpace** (skiss-villkor).
Fönstret följer Omarchys aktiva tema och typsnitt.

![Omacad](screenshots/10_overview.png)

## Funktioner

**Skissa**
- Skissa på origin-plan, på valfri plan yta (högerklick → *Create Sketch on this Face*) och på egna plan (Offset Plane).
- Linje, rektangel, centrumrektangel, cirkel, 3-punktsbåge, slot och **regelbunden polygon** (`P`: trianglar, hexagoner ... klicka mitten, Tab ger sidlängd och antal sidor). Snäpper mot hörn, kanter, mittpunkter, rutnät och kroppens kanter.
- **Tab-inmatning** medan du ritar (längd, vinkel, bredd/höjd, diameter) – Enter går vidare, Esc ångrar.
- **Mått och villkor** (SolveSpace): horisontell, vertikal, parallell, vinkelrät, lika, tangent, koncentrisk, fixerad, avstånd, längd, vinkel, diameter, punkt–linje. Guidad högerklicksmeny på varje element.
- Markera, flytta (dra eller `M` med dx/dy), ta bort, **Offset (`O`) med förhandsvisning**, ångra/gör om.
- **Skiss-Fillet**: Interaktiv bisektrispil med radie-bricka pekar in i hörnet för visuell kontroll vid avrundning.
- **Canvas / Referensbild**: Infoga ritningar och referensbilder på valfritt plan. Bildredigering (ljusstyrka, kontrast, invertering, gråskala, rotation, beskärning) och **kalibrering med virtuellt måttband** (klicka två punkter och ange mm) för att rita av i skala 1:1.

**Solider**
- **Extrude** med dragbar pil i vyn *och* inskrivet värde, riktning (en sida, symmetriskt, två sidor), *To face…*, Auto / New Body / Join / Cut / Intersect. Förhandsvisning och profilval i vyn: inget väljs åt dig, klicka på en profil och **Shift+klick** lägger till eller tar bort fler (t.ex. ringen och cirkeln i den). Extrudera också en hel yta.
- Box, Cylinder, Sphere, Combine (Join/Cut/Intersect).
- **Split Body**: Dela en solid kropp i två separata kroppar med ett offset-plan eller origin-plan.
- **Shell (Urholka)**: Skapa ihåliga solider med specificerad väggtjocklek. Klicka på ytor i 3D för att lämna dem öppna (t.ex. toppen på en låda).
- **Fillet och Chamfer** på raka kanter, cirklar (skruvhål, försänkningar) och hela konturer med rundade hörn. Inre och yttre kanter, dubbelklick väljer hela loopen, samt **interaktiv 3D-pil** direkt på kanten för att justera storleken.
- **Pattern / Mirror**: jämnt fördelade kopior, speglade hörn (kopierar t.ex. hål med chamfers) eller runt en axel, med förhandsvisning.
- **Fill the face** (Pattern/Mirror → *Fill the face*): fyller en yta med kopior med exakt fast mellanrum (kant till kant, så hexagoner, cirklar och trianglar packas rätt), valfri ramkant (offset) mot kanten, rutnät eller förskjutet (bikake). Undviker automatiskt utskjutande detaljer på ytan.
- **Offset Plane**: Välj valfritt plan (XY/XZ/YZ, konstruktionsplan eller plan yta på kropp). Ange avstånd exakt i mm, dra i den lila 3D-pilen, använd formler/parametrar, eller klicka *To surface…* för att tangera en yta.

**Se in i modellen**
- **Measure** (`I`, knappen i både SOLID och SKETCH): klicka på en linje, cirkel eller kant för längd/diameter, klicka på en andra för avstånd (parallella) eller vinkel och kortaste avstånd. Gäller skisselement i skissläge och kroppskanter i 3D.
- **Section View** (✂️ i bandet, View-menyn): välj XY/XZ/YZ, en yta eller ett eget plan, och skjut snittet genom modellen med reglage, inskrivet värde eller genom att dra i den blå pilen. Snittytan färgas, med "se från andra sidan". Sparas som en **Section View i trädet** (öga för av/på, högerklick: ändra, döp om, ta bort) och följer med i filen.

**Parametriskt**
- **Parametrar** med namn och formler (`bredd/2`, `10-1`, `2x(3+5)`) i alla fält.
- **Tidslinje**: klicka på ett steg för att ändra det, dubbelklick redigerar, rulla tillbaka/framåt, undertrycka steg.
- Sketcher döljs automatiskt när de använts; ögon i trädet.

**Gränssnitt**
- Ribbon, bläddrare (döp om med F2), tidslinje, ViewCube.
- **Högerpanel (Inspector)**: Verktygsdialoger (Extrude, Fillet, Shell, Offset Plane, Split Body) dockas prydligt i högerpanelen så de aldrig skymmer 3D-modellen, och visar geometri- och mätdata i realtid.
- Spara/öppna `.omacad` (JSON), export till **STL** och **OBJ**.

![Extrude](screenshots/11_extrude_arrow.png)
![Hela konturen](screenshots/12_fillet_whole_outline.png)
![Pattern](screenshots/13_pattern_preview.png)

## Köra

```bash
./run.sh
```
eller sök efter **Omacad** i Omarchys appmeny (`omacad.desktop`).

## Paketering för Windows

Omacad kan paketeras som en fristående `.exe` för Windows utan att mottagaren behöver ha Python installerat.

### Bygg med PyInstaller
Kör byggskriptet [`build_windows.bat`](build_windows.bat) eller i terminalen:
```powershell
pip install PySide6 numpy manifold3d trimesh PyOpenGL Pillow shapely pyinstaller
pyinstaller omacad.spec
```
Den färdiga appen hamnar i `dist/Omacad/` med `Omacad.exe`. Mappen kan zippas och delas direkt till andra användare (eller paketeras i en installationsguide med Inno Setup).

## Installation av skisslösaren

`python-solvespace` saknar wheel för Python 3.14, bygg så här:

```bash
CFLAGS="-std=gnu17" CXXFLAGS="-std=gnu++17" uv pip install --python .venv/bin/python python-solvespace
```

## Begränsningar

Fillet/chamfer gäller raka kanter mellan plana ytor, hela cirklar och konturer med raka stycken + bågar med räta väggar (inte koner eller delbågar). Mönster, ytskisser och offset-plan är inte associativa. Ändringar i tidslinjen går inte att ångra (skisser går). Bågar och slots finns inte i skisslösaren än.

## Färdplan

Revolve, Trim/Offset-fillet/Rotate/Scale i skiss, Project, STEP/IGES, sammanställningar, CAM.

## English summary

Omacad is a native parametric CAD program for Omarchy Linux. Sketch (lines, rects, circles, arcs, slots, regular polygons) with SolveSpace constraints and formula-driven dimensions; extrude with a draggable arrow, fillet/chamfer (including circles and whole outlines), pattern/mirror including a *fill the face* mode with fixed gaps and a frame, offset planes, section views saved in the tree, measuring, parameters and a timeline you can edit. See **`ROADMAP.md`** for the step-by-step list of what is done and what remains.
