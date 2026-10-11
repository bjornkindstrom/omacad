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

**Solider**
- **Extrude** med dragbar pil i vyn *och* inskrivet värde, riktning (en sida, symmetriskt, två sidor), *To face…*, Auto / New Body / Join / Cut / Intersect. Förhandsvisning och profilval i vyn: inget väljs åt dig, klicka på en profil och **Shift+klick** lägger till eller tar bort fler (t.ex. ringen och cirkeln i den). Extrudera också en hel yta.
- Box, Cylinder, Sphere, Combine (Join/Cut/Intersect).
- **Fillet och Chamfer** på raka kanter, cirklar (skruvhål, försänkningar) och hela konturer med rundade hörn. Inre och yttre kanter, dubbelklick väljer hela loopen, förhandsvisning.
- **Pattern / Mirror**: jämnt fördelade kopior, speglade hörn (kopierar t.ex. hål med chamfers) eller runt en axel, med förhandsvisning.
- **Fill the face** (Pattern/Mirror → *Fill the face*): fyller en yta med kopior med exakt fast mellanrum (kant till kant, så hexagoner, cirklar och trianglar packas rätt), valfri ramkant (offset) mot kanten, rutnät eller förskjutet (bikake). Kopior som hamnar vid ramen klipps av mot den (halva hexagoner), med en minsta bitstorlek så att inga flisor blir kvar.
- **Offset Plane** i två klick: välj XY/XZ/YZ, peka på valfri yta (även cylindrar) – planet läggs tangent mot ytan.

**Se in i modellen**
- **Section View** (✂️ i bandet, View-menyn): välj XY/XZ/YZ, en yta eller ett eget plan, och skjut snittet genom modellen med reglage, inskrivet värde eller genom att dra i den blå pilen. Snittytan färgas, med "se från andra sidan". Sparas som en **Section View i trädet** (öga för av/på, högerklick: ändra, döp om, ta bort) och följer med i filen.

**Parametriskt**
- **Parametrar** med namn och formler (`bredd/2`, `10-1`, `2x(3+5)`) i alla fält.
- **Tidslinje**: klicka på ett steg för att ändra det, dubbelklick redigerar, rulla tillbaka/framåt, undertrycka steg.
- Sketcher döljs automatiskt när de använts; ögon i trädet.

**Gränssnitt**
- Ribbon, bläddrare (döp om med F2), tidslinje, ViewCube, all dialoger i en **högerpanel** som aldrig täcker modellen.
- Spara/öppna `.omacad` (JSON), export till **STL** och **OBJ**.

![Extrude](screenshots/11_extrude_arrow.png)
![Hela konturen](screenshots/12_fillet_whole_outline.png)
![Pattern](screenshots/13_pattern_preview.png)

## Köra

```bash
./run.sh
```
eller sök efter **Omacad** i Omarchys appmeny (`omacad.desktop`).

## Installation av skisslösaren

`python-solvespace` saknar wheel för Python 3.14, bygg så här:

```bash
CFLAGS="-std=gnu17" CXXFLAGS="-std=gnu++17" uv pip install --python .venv/bin/python python-solvespace
```

## Begränsningar

Fillet/chamfer gäller raka kanter mellan plana ytor, hela cirklar och konturer med raka stycken + bågar med räta väggar (inte koner eller delbågar). Mönster, ytskisser och offset-plan är inte associativa. Ändringar i tidslinjen går inte att ångra (skisser går). Bågar och slots finns inte i skisslösaren än.

## Färdplan

Revolve, Trim/Offset-fillet/Rotate/Scale i skiss, Project, STEP/IGES, sammanställningar, CAM.
