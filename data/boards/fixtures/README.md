# Road grading fixtures

Open **Road Grades - Grassland.board2** or **Road Grades - Concrete.board2** in the board editor. These are native,
editable board documents. The `.board2` format preserves the beside-rail choices, bridge appearance and case notes;
legacy `.board` export discards that information.

Each 63 × 84 map contains the same 36 cases in three panels, for 108 cases per map:

| Panel | Board columns | Contents |
| --- | --- | --- |
| ROAD | 01–21 | Road only |
| CENTERED | 22–42 | The same roads with centered conventional railway |
| BESIDE | 43–63 | The same railway with the editor's propagated beside-road placement |

Within each panel, cases occupy 7 × 7 cells, three across. Read left to right, then down. The centre hex has an
annotation with the panel, case ID and purpose. `road-grades-cases.csv` lists all 216 cells across both maps, their
centre coordinates, inclusive cell bounds and the actual saved route masks/heights. Board coordinates and CSV cell
bounds are one-based. Route entries use `hex@ground-level`; `deck=` is an absolute deck level, and the remaining
entries are native exit masks. Bits 1, 2, 4, 8, 16, 32 mean N, NE, SE, S, SW, NW.

| Cell row | Case IDs |
| --- | --- |
| 1 | straight-0, straight-1, straight-2 |
| 2 | straight-3, straight-4, straight-5 |
| 3 | turn60-0, turn60-1, turn60-2 |
| 4 | turn60-3, turn60-4, turn60-5 |
| 5 | turn120-0, turn120-1, turn120-2 |
| 6 | turn120-3, turn120-4, turn120-5 |
| 7 | t-mixed, x-mixed, bridge-straight |
| 8 | bridge-curved, bridge-bent, bridge-overpass |
| 9 | cliff-curve, cut-valley, apron-flat |
| 10 | apron-slope, grade-straight, grade-curve |
| 11 | grade-high-bank, grade-low-bank, grade-transition |
| 12 | bridge-graded, level-toe-straight, level-toe-curve |

The first eighteen cases rotate through all six directions. Their middle hex changes relative to the surrounding
level-3 terrain by **+1, −2, +3, −1, +2, −3**, respectively. This puts both upward and downward changes directly in a
straight or bend. The later cases cover mixed-height junction arms, a lower/higher bank at each end of a bridge,
a curved descending landing, an angled deck, independent routes above and below an overpass, explicit three-level
cliffs, and a level-0 road cut between level-6 cliffs. The apron examples deliberately end one road arm in roadless
concrete; the main road and railway continue past that entrance.

Six ordinary cases have routes with successively higher centers, rather than isolated rises or dips.
They cover a continuous straight incline, a gentle curve, higher and lower ground inside that curve, a transition
between centered and beside railway, and a bent bridge with graded banks and decks. Each hex shares its ramps with
its neighbours over the outer 30% of its width and keeps a level middle.

The final two cases put a straight or curved incline beside two equal lower plateaus. Outside the road/rail
footprint, their common corner should keep its lower level instead of growing a ridge toward the road mouth.
These have another 144 focused combinations across direction, column parity, surface and corridor layout.
The corresponding source regressions check Mines 1 at 0406/0508 and City Hills Residential 1 at 1506.

The rails use `RailRoute`'s supported native pieces and connected ground/deck layers. A sharp 120° road bend gets a
short outside railway bypass made from gentle pieces; it is not an impossible rail hairpin. Beside placement uses
the existing corridor-run propagation and applies only where road and railway actually share a corridor. These
large height changes exercise rendering and picking; they do not promise that every unit can traverse a route.

The road reserves its ground: level across its width, graded only along its course, with junction cores level.
Enhanced natural slopes ease into the road as banks; concrete is cut vertically. Classic keeps sharp hex columns
and cuts each ramp into them with vertical faces, never Enhanced banks. Enhanced concrete uses its fitted boundary
and respects the author's straightening override.

## Regeneration and review

The deterministic generator is `RoadGradeFixture.java` in MegaMek's GPU test package, alongside the existing
`RoadJunctionFixture`. With that class compiled on the test runtime classpath, run:

```text
java -cp <test-runtime-classpath> megamek.client.ui.clientGUI.boardview.gpu.RoadGradeFixture <mm-data>/data/boards/fixtures <runtime>/data/boards/fixtures
```

The second directory is optional. The exporter writes both boards and the CSV, reloads the native documents,
and rejects unsupported rail hairpins or unjoined rail exits before copying the runtime mirrors.

`GpuRoadGradeFixtureSmokeTest` reads these saved files. Its default run saves a top overview of both surfaces in
Classic and Enhanced. Add comma-separated case IDs for close top/45°/225° views, and optionally restrict the panel
or surface:

```text
gradlew :megamek:gpuBoardSmoke --tests *GpuRoadGradeFixtureSmokeTest -Dmegamek.gpu.gradeCases=turn60-1,bridge-curved -Dmegamek.gpu.gradePanels=road,centered,beside -Dmegamek.gpu.gradeSurfaces=grassland,concrete
```

Images are saved under `gpu-board-review/grade-fixture` in the selected build directory. Detailed captures are
opt-in so an ordinary fixture run does not produce hundreds of images.

## Reported source-map checks

`GpuRoadRampSourceSmokeTest` keeps close top/45°/225° views in Classic and Enhanced for these reported locations.
Use its comma-separated `megamek.gpu.rampSources` selectors to repeat a focused review.

| Map | Locations | Selectors |
| --- | --- | --- |
| militarybase2 | 1013/0914 graded concrete join; 0817/0917 flat joins | `military-base-slope`, `military-base-flat` |
| Park District | 1408/1507/1607/1508 roundabout and concrete edges | `park-district` |
| Mines 1 | 0407/0408/0507/0508/0509 bends and descending banks | `mines` |
| Observatory Hill | 0812/0813/0814/0913/0914 junction banks | `observatory-junction` |
| Large Mountain 2 | 0803/0904/1004/1105/1205 rocky road supports | `large-mountain-road` |
| City Hills Residential 2 | 1312/1412/1313/1413 fork; 0810/0710 bridge approach | `city-hills-2-junction`, `city-hills-2-bridge` |
| City Hills Residential 2 (with Structures) | 0902 barrier; 1214/1315/1215 corners; 0814/0914/0915 junction; 0306/0206/0307 inclines | `city-hills-structures-barrier`, `city-hills-structures-corner`, `city-hills-structures-junction`, `city-hills-structures-double-incline` |
| MesaCity1 N - Mesas (64 × 51) | 2722/2821 bend and 2820/2921/2721 cliff supports | `mesa-city-climb` |

The suite also retains Plaine 1, City Hills Residential 1 and Fire And Ice 2 as earlier regression cases.
