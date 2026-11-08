# 3D board assets

This directory is the libGDX board's independent art source. Runtime never reads
terrain or water from the 2D board's images directory. The Java build stages this
directory with the game's data. Blender is an authoring dependency only.

## Model ids

A model's id is its path here without `.glb` (`vegetation/pine`, `scenery/military/cargo-crate`): the game, its code,
the editor and the catalogues name models by it. Models live in folders, none at this root. `uids.json` gives each
model a stable, opaque id, never reused, for saved boards alone: a `.board2` stores a model's path and its id and loads
it by its id (`BoardModelIds`), so a board saved before a model moved still finds it. Move or rename a model with
`tools/move_model.py <path> <new path>`: it rewrites the model's texture paths, keeps its id (its line now names the new
path) and renames its manifest entries; `tools/move_model.py --stamp` gives new models their ids.
`BoardModelIdsTest` fails while an id names no model or a model has no id: update a moved model's line, never give it a
new id. A tree's winter form `<path>-snow` without a file of its own is its bare species' file in its `snow` variant. A
model's levels are its root groups named `...-lod0` to `...-lod3`: only the ending counts, so `teapot.glb` may hold
`a-lod0` and `a-lod1`. Authored scenery may hold two more root groups, which the game reads as data: `cut`, triangles
of the ground it digs out of its hex (in Enhanced the hex's top gives way over them and they become the ground there),
and `stands`, empties where troops resting in its hex stand (`stand-N`, N the formation slot), facing their +Y, where a
platoon's transports park (`vehicle-N`) and where a tank waits to go hull down (`hide-N`). A model whose pieces show
one by one names them `part-N`, both its level nodes and the `cut` children: the game shows the parts a hex needs.
The model draws its own floor and walls and stands on its hex's ground as it was before the cut. The manifest
`tools/board-models/manifest.json` is tool data: budgets, levels and sources keyed by these paths. It is not
shipped and the game does not read it.

## Scenery folders

Scenery meshes live in topic folders under `scenery/`, with kebab-case names:

| Folder | Contents |
|---|---|
| `roofs/` | rooftop objects: bevel, ledge, roof grille, chimney stack, skylight, glass roof and dome, landing beacons |
| `parks/` | bench, picnic table, garden bed, pillar, hex plaza, fountain, plaza variants, formal gardens, grandstand; `tree-cluster-1`-`5.png`, the tree-cluster stamps' thumbnails, rendered from their rows |
| `pools/` | sport pools (deck, main and wading basins), rectangular, round and freeform pools; a pond is a pool in pond colours |
| `vehicles/` | the car (its paint is a colour slot), parking barrier, parking shelters |
| `road/` | stop sign, three-aspect pole signal and curved mast-arm signal gantry; facing +Y with pole bases at Z=0; generated road-junction controls; `roadside-trees.png`, the roadside-trees stamp's thumbnail, rendered from its rows over its half-transparent road |
| `construction/` | crawler crane, bulldozer, concrete debris, excavation site, concrete pipe |
| `farm/` | one mesh per animal and pose: cow, pig, horse, bison, hen and rooster; coats are colour slots |
| `seaport/yard/` | the container yard looks' ten compositions (`yard/<name>` in `layouts.json`) and the ten seaport props; all 17 container-bearing models have three LODs, with detailed individual props and budgeted yard shells using baked frames and door hardware; hidden neighbour faces are omitted |
| `maglev/` | route marker (the only rail mesh), station platform, city and colony vehicles, the city gangway coupler; `train.png` and `colony-train.png` are the stamps' thumbnails |
| `military/` | orbital gun, fortification (dug, and sandbags where paved), the trench of a dug-in platoon, an olive container of cargo set down on the ground |
| `rubble/` | a collapsed building by structure type, and (`-path`) its hex cleared: the debris collected into heaps, the salvage stacked |
| `geysers/` | dormant and erupting water geysers and the magma geyser, two looks each (`<state>` and `<state>-b`, one or the other per hex): one top-down photographic study (`textures/scenery/geyser-sinter`, `geyser-spatter` and their `-b`) mapped straight down over a heightfield of the feature's relief, cut along a smooth outline and easing down to the ground at it, its water or lava just under the rim, where `GpuGeysers.vent` starts the steam and the eruption; the study's flat apron around it is the look's `decal/geysers/` decal |

No mesh sits at a legacy key. A legacy key is `scenery/<2D tileset image path
without extension>`, which the Classic tileset names for the token it stands for
(`classic/`); it resolves only through `scenery/layouts.json`, so that
file is the complete legacy-to-mesh mapping. Its `yard/<name>` keys are no legacy
keys: they are the container yard looks' compositions, which a hex's woods draw.
A key that was one GLB at the base is a one-row entry at the origin on its
renamed mesh. Every mesh stands on Z=0 and
every row has Z=0. Two kinds of mesh stand above Z=0 by design: a crane's boom
segment (`seaport/yard/crane-boom`) keeps the boom height (41 px up), and the maglev vehicles ride the route's beam (their suspension shoes
1.3 px up, the coupler's shoe links 2.3 px; see Maglev). Blueprint IDs are the new mesh
paths; stamps still name legacy keys.
Decal rows (`decal/...`) name painted decals, not meshes (see Decals): each
car-park key `fluff/cars_*` places standard car-park decals, and its car rows
carry `"seat"`. The conversion (`BoardSceneryLayouts.convert`, run wherever a
legacy board is loaded) makes the lane a real `road:1` with the lane's exits on a
car park on plain ground without a road. The rows stand beside that road; the
conversion folds them back to back where no road is drawn.
A row may carry `"stretch": [x, y, z]`, positive factors on the mesh's own axes
before its turn (the narrow glass roof is `roofs/glass-roof-wide` stretched to
29/36 of its width), and `"colours": ["#rrggbb", null, ...]`, replacements for the
mesh's colour slots in slot order (null keeps a slot's own colour).

### Colour slots

A mesh may mark up to four colour slots: each vertex carries its slot in the
attribute `_COLOUR_SLOT` (0 none), and the file's extras `mmColourSlots` list each
slot's name, its default colour and preset colours (the colours of the family's
meshes at the base). A row's or a placed object's colour replaces a slot's default: each
channel keeps its ratio to the default in linear light, so shaded parts of a slot
stay shaded (`RigidGlb.recolour`). A slot's base vertices hold its default exactly, to the
8-bit step, so a replacement reproduces itself exactly there. The colour families
are one mesh each:

| Mesh (`scenery/...`) | Slots | Base meshes (as colours) |
|---|---|---|
| `vehicles/car` | Paint | 19 `car-<paint>` (red is the default) |
| `farm/hen` | Plumage | 6 hens (white is the default) |
| `farm/rooster` | Plumage, Wings | 3 roosters (red) |
| `farm/horse` | Coat, Mane and tail, Muzzle | chestnut, dun, sorrel |
| `farm/horse-relaxed` | Coat, Mane and tail, Muzzle | bay, grey (resting) |
| `farm/cow` | Patches | brown, black patches |
| `farm/pig` | Skin, Spots | pink spotted (default), pink, brown spotted |
| `farm/bison` | Coat | dark, light |
| `pools/*` | Wall, Coping, Deck, Water | `parks/pond-1`, `-2`, `-4` are `pools/freeform`, `sport-2`, `sport-4` in the 'Pond' colours |
| `seaport/yard/container`, `container-stack-2`, `container-stack-3`, `yard-truck` | Paint; Bottom, Top; Bottom, Middle, Top; Container | one mesh each, the 11 legacy container paints as presets |
| `military/cargo-crate` | Paint | olive (default), woodland, desert, grey, navy, winter, oxide red |

Every vertex whose colour differs between a family's coats belongs to the slot
that reproduces it for every coat; each car and pond row names its colours.
Coats that differ only in colour share one mesh with colour slots, so there are
12 animal meshes.

The containers use `textures/structures/common/corrugated-painted`: opaque dielectric satin paint, tinted by
vertex/slot colours, with subtle broad weathering. Their fittings use separate steel; there is no tiled chip mask.
The unpainted light walls use `corrugated`, the bare-metal finish. Both materials have the same profile, one repeat
to 6.5 m (18 units), so their 0.65 m corrugations read at play zoom.

Individual container props have formed frames, castings, hinges and locking bars at LOD0, and recessed panels with
four rim strips per face at LOD1. Yard compositions use simpler shells at every level: top/bottom rail profiles at
LOD0, top rails at LOD1 and flat faces at LOD2. Frames, door seams and hardware use the shared `container-details`
albedo, normal and ORM atlas. Its alpha masks paint tint on metal fittings, not visibility. The near/middle stacked
bodies have small physical joints; the far atlas preserves those boundaries. The single container uses 250/50/10
triangles; heavy rows use 1868/1264/660, ultra rows 2940/1980/1020, and ultra gantry containers 2316/1560/804.
Each yard container mesh is capped at 3000/2000/1100 triangles, excluding separately placed cranes/vehicles.
All levels retain colour slots, placement and existing machinery. The props' existing screen-size LOD selection
chooses the three levels.
Authoring sources and the reproducible build are in `tools/board-models/seaport/`; rerun that build after changing
the source container or exporting its underlying Material Maker materials.

The cargo crate's maps are baked, its olive paint worn to the metal, rusted and dirty. A
material whose extras set `mmPaintMask` (a library material's `.tres`: `metadata/mmPaintMask`)
keeps a paint mask in its albedo's alpha: the slot
colour (the vertex colour) tints only the paint, never the bare metal, rust and grime. Its
white vertices hold the slot's default as a ratio of 1. A material whose extras set `mmLabel`
draws a label: each quad is one character place (its U's integer part), mapped to the first,
blank cell of an 8 by 8 atlas of `RigidGlb.LABEL_CHARACTERS`, and the game writes the label's
characters there, centred (`RigidGlb.label`): the crate's two-digit number, in worn stencils from its
embedded stencil atlas.

### Old to new

| New mesh (`scenery/...`) | Old file or ID (`scenery/...`) | Legacy key decodes to it |
|---|---|---|
| `construction/concrete-pipe` | `components/concrete-pipe` | - |
| `construction/bulldozer`, `construction/debris-3` | `fluff/construction3` | yes, two rows |
| `construction/crawler-crane`, `construction/debris-1` | `fluff/construction1` | yes, two rows |
| `construction/site-excavation` | `fluff/construction2` | yes, one row |
| `farm/<animal>` (12 meshes; coats are colours) | `fluff/bison1`, `cattle1`-`3`, `chickens1`-`3`, `horses1`-`2`, `pigs1`-`2` | yes, one row per animal |
| `geysers/magma` | `saxarba/misc/geyser_magma` | yes, one row |
| `geysers/water-dormant` | `saxarba/misc/geyser_water_off` | yes, one row |
| `geysers/water-erupting` | `saxarba/misc/geyser_water_on` | yes, one row |
| `maglev/cab` | `components/maglev-cab` | - |
| `maglev/coupler` | `components/maglev-coupler` | - |
| `maglev/platform` | `components/maglev-platform` | - |
| `maglev/route` | `components/maglev-route` | - |
| `maglev/train` | `components/maglev-train` | layout ID of the train stamp, not a mesh |
| `maglev/wagon` | `components/maglev-wagon` | - |
| `military/fortification` | `saxarba/misc/fortified` | yes, one row |
| `military/orbital-gun` | `UlyssesSprites/orbitalguns/OrbitalGunE` | yes, one row |
| `parks/bench` | `components/bench` | - |
| `parks/formal-garden-hex` | `saxarba/SMV_Fluff/FluffSystem-07-Garden-03-Landscape-1-01` | yes, one row |
| `parks/formal-garden-round` | `saxarba/SMV_Fluff/FluffSystem-07-Garden-03-Landscape-1-02` | yes, one row |
| `parks/formal-garden-star` | `saxarba/SMV_Fluff/FluffSystem-07-Garden-03-Landscape-1-04` | yes, one row |
| `parks/garden-bed` | `components/garden-bed` | - |
| `parks/grandstand` | `components/grandstand` | - |
| `parks/picnic-table` | `components/picnic-table` | - |
| `parks/pillar` | `components/pillar` | - |
| `parks/plaza-flowers` | `fluff/square6` | yes, one row |
| `parks/plaza-flowers-pillars` | `fluff/square5` | yes, one row |
| `parks/plaza`, `parks/fountain` | `components/hex-plaza` | - |
| `parks/plaza-hedge` | `fluff/square3` | yes, one row |
| `parks/plaza-pillars` | `fluff/square2` | yes, one row |
| `parks/plaza-pond` | `fluff/square4` | yes, one row |
| `pools/freeform` in pond colours | `components/lake-freeform-01` | - |
| `pools/sport-2` in pond colours | `components/lake-freeform-02` | - |
| `pools/sport-4` in pond colours | `components/lake-freeform-04` | - |
| `pools/freeform` | `components/pool-garden-freeform` | - |
| `pools/rectangular` | `components/pool` | - |
| `pools/rectangular-no-deck` | `components/pool-rectangular-no-deck` | - |
| `pools/round-no-deck` | `components/pool-round-no-deck` | - |
| `pools/sport-1-deck` | `components/pool-sport-01-deck` | - |
| `pools/sport-1-main` | `components/pool-sport-01-main` | - |
| `pools/sport-1-wading` | `components/pool-sport-01-wading` | - |
| `pools/sport-2` | `components/pool-sport-02` | - |
| `pools/sport-3-deck` | `components/pool-sport-03-deck` | - |
| `pools/sport-3-main` | `components/pool-sport-03-main` | - |
| `pools/sport-3-wading` | `components/pool-sport-03-wading` | - |
| `pools/sport-4` | `components/pool-sport-04` | - |
| `pools/sport-5` | `components/pool-sport-05` | - |
| `roofs/bevel` | `components/bevel` | - |
| `roofs/glass-dome` | `saxarba/SMV_Fluff/FluffSystem-01-Building-07-GlassRoof-3-01` | yes, one row |
| `roofs/glass-roof-wide`, stretched to 29/36 of its width | `roofs/glass-roof-narrow`, `saxarba/SMV_Fluff/FluffSystem-01-Building-07-GlassRoof-1-01` | yes, one row with stretch |
| `roofs/glass-roof-wide` | `saxarba/SMV_Fluff/FluffSystem-01-Building-07-GlassRoof-2-01` | yes, one row |
| `roofs/landing-beacon-hex` | `fluff/beacon1` | yes, one row |
| `roofs/landing-beacon-round` | `fluff/beacon2` | yes, one row |
| `roofs/ledge` | `components/ledge` | - |
| `roofs/skylight` | `components/skylight` | - |
| `roofs/grille`, `roofs/chimney-stack` | `components/roof-vent` | - |
| `rubble/hardened` | `saxarba/misc/rubble_hardened` | yes, one row |
| `rubble/hardened-path` | `saxarba/rubble_hardened_path` | yes, one row |
| `rubble/heavy` | `saxarba/misc/rubble_heavy` | yes, one row |
| `rubble/heavy-path` | `saxarba/rubble_heavy_path` | yes, one row |
| `rubble/light` | `saxarba/misc/rubble_light` | yes, one row |
| `rubble/light-path` | `saxarba/rubble_light_path` | yes, one row |
| `rubble/medium` | `saxarba/misc/rubble_medium` | yes, one row |
| `rubble/medium-path` | `saxarba/rubble_medium_path` | yes, one row |
| `rubble/wall` | `saxarba/misc/rubble_wall` | yes, one row |
| `rubble/wall-path` | `saxarba/rubble_wall_path` | yes, one row |
| `seaport/yard/crane-boom`, turned 0, -60 and -120 degrees for tips 1 and 4, 2 and 5, 3 and 6 | `saxarba/SMV_Seaport/SeaportSystem-02-ShipToShoreGantryCrane-03-CraneTip-1-01`-`06` (a tip no converted crane reaches) | yes, one row each |
| `vehicles/car` (paint as a colour) | `components/car-<paint>` (19 paints) | - |
| `vehicles/parking-barrier` | `components/parking-barrier` | - |
| `vehicles/parking-shelter` | `components/shelter` | - |
| `vehicles/parking-shelter-no-floor` | `components/shelter-no-floor` | - |

## Maglev

The twelve `scenery/fluff/maglev*` keys decode through `scenery/layouts.json`
to a route marker row and the artwork's pieces: platform, passenger wagons,
driver cab, coupler and parked road cars (`scenery/vehicles/`). The marker row
(`scenery/maglev/route`) carries the route's sides as `connections`
(N=1, NE=2, SE=4, S=8, SW=16, NW=32): 9 for N/S, 18 for NE/SW and 36 for NW/SE.
The client draws the rail from the stored sides. Facts measured on the 84x72 sprites:

| Keys | Route | Platform | Train piece | Parked cars |
|---|---|---|---|---|
| `track1`-`3` | N/S, NE/SW, NW/SE | - | - | 0 |
| `station1`-`3` | N/S, NE/SW, NW/SE | W, NW, NE | - | 4, 2, 0 |
| `train1`-`3` | N/S | -, W, - | cab hex (nose N), middle, tail | 2, 4, 1 |
| `train4`-`6` | NE/SW | -, NW, - | cab hex (nose SW), middle, tail | 0, 3, 1 |

A three-hex train is a cab hex, a middle hex and a tail hex: maglevtrain1-3 from
north to south, maglevtrain4-6 from south-west to north-east (every shipped
maglevtrain4 has a maglevtrain5 to its north-east, every maglevtrain6 one to its
south-west). No baked composite and no second rail mesh remain.

The pieces ride the client's generated guideway (a concrete beam 4 px wide to Z 2.4 and a steel guide rail
1.4 px wide to Z 4): each has its origin on the beam's centre line at the marker's level, the track along Y and
the nose at +Y, and carries its ride height, so every row has Z=0. A body hovers 0.4 px over the guide rail
(underside at Z 4.4); a black suspension shoe near each end bridges the rail and wraps the beam's sides 0.4 px
off the concrete, down to Z 1.3, clear of the maglev pier cap. Every vehicle is 30 px long over its ends, so two
cars and their 4 px gap fill a hex as the legacy rows place them (y -17 and +17). Two families, each car with
Body and Trim colour slots (the car's colour convention: every livery colour is a preset of both):

- City ("Civitas", Body cream, Trim teal, a fixed orange stripe): `cab` (control car with a wraparound
  windscreen and destination sign), `wagon` (passenger car), `service-car`, `city-freight` (two boxes on a
  flat), and `coupler`, their gangway with the bars that link the two cars' shoes.
- Colony ("Vector", Body navy, Trim cream, amber lamps): `colony-cab` (armoured wedge nose), `colony-cargo`,
  `colony-tanker`, `colony-containers` and `colony-heavy` (a construction walker strapped to a flatbed). Each
  carries its own drawbars, so no coupler row is needed.

`platform` is a raised station deck at the cars' floor (Z 5.2) with edge lights, stairs at both ends and a
lens-shaped canopy on Y columns; it is symmetric across the track, so it serves either side, and its edge lights,
canopy fascia and pylon signs are a Trim slot. The stamps (`scenery/layouts.json`): `scenery/maglev/train`
("City maglev": a wagon, a cab and their coupler, the legacy pair) and `scenery/maglev/colony-train` ("Colony
maglev": cab, cargo car, tanker and heavy transport at 34 px); `train.png` and `colony-train.png` are their
thumbnails. Placed objects draw only their near mesh (LOD0), so each piece is one mesh of 140 to 740 triangles.
A platform on a fixed-level (elevated) route floats at the route's level; it has no supports of its own.

The Java `BoardSceneryMaglevTest` checks the decoded rows against the sprite facts above, the palette and the
import of two shipped boards.

## Rail pieces

The rail track (ballast, sleepers, rails) is generated by the client's route builder, shared with the maglev
beam. The pieces that never bend are GLBs under `scenery/rail/`, at real scale (2.8 px per metre): the
`buffer-stop` at dead ends, the level-crossing `crossing-signal` and the rolling stock of three families:
- Frontier Rail, armoured military-industrial (olive Body, orange Trim): `locomotive` (armoured freight
  locomotive, 56 px), `coach` (armoured transit coach, 62), `box-car` (cargo wagon, 46), `tank-car` (tanker, 42),
  `ore-hopper` (40) and `heavy-flatbed` (48, with a power unit as its load);
- the Express, a high-speed passenger train (white Body, blue Trim): `express-power-car` (64, nose tip included)
  and `express-car` (62);
- Ironline, colony mining freight (oxide red Body, cream Trim): `colony-locomotive` (56), `container-wagon` (46,
  two of the seaport's containers at real scale), `heavy-hopper` (42), `insulated-tanker` (42) and
  `equipment-carrier` (48, with an excavator chained down).

The client enlarges conventional track, rolling stock and buffer stops by 1.3 at runtime; the authored GLBs and
lengths above remain unchanged. The track's rail top lies 1.82 px above its carrier plane (ballast top 0.78,
sleepers 0.39, rails 0.65; gauge 5.46), with a ballast footprint 14.56 px wide. Every rail piece has its origin on
the track centre line at rail-top height, the track along Y: its runtime placement follows the rail top,
including the recessed rails through a road crossing. Maglev keeps its existing dimensions.
Locomotive and power car noses and the buffer stop's buffers face
+Y; the signal faces +Y from its footing's base. Vehicles are measured over their coupler faces (a power car over
its nose tip) and carry their own couplers, so coupled vehicles stand half their lengths apart and need no coupler
piece. Each vehicle has two colour slots, Body and Trim, in the parked car's convention (`mmColourSlots`), with the
same twelve livery presets; warning stripes, lamps, glass, ore and running gear are fixed colours. Placed objects
draw only a GLB's level 0, so every vehicle is one mesh of about 650 to 1,150 triangles. Three stamps, each in its
family's default livery with the lead nose at +Y: `scenery/rail/train` ("Freight train": locomotive, cargo wagon,
tanker, heavy flatbed), `scenery/rail/express-train` (power car, two cars, the second power car turned 180 degrees)
and `scenery/rail/colony-train` (colony locomotive, heavy hopper, insulated tanker, equipment carrier), with
`train.png`, `express-train.png` and `colony-train.png` as thumbnails.

The 64 legacy rail keys `scenery/hq_fluff/rail00`-`rail63` (FLUFF 10:0-63) decode to one route marker row,
`scenery/rail/route`, whose `connections` is the token value: the sprite's side mask. The client builds the track
from those sides. `rail00` has no sides; the conversion takes them from its neighbours, and an isolated one places
nothing. The six level crossings `rail_road01`-`06` (FLUFF 10:64-69) add the marker on the rail's axis and four
crossing signals. The native road stays continuous through the track, whose exposed rails and flange grooves
replace the old concrete decal. Each signal stands beside the widened road, 17 px from its centre line and
9.5 px from the track's, and faces the road traffic that comes towards it.
Native independent paved-road/rail crossings also derive a signal on each incoming road's right verge, from the
same track-clearance stop position as the road paint. These use the existing signal GLB, clear both travel
envelopes, and leave nearby saved crossing poles in place. Parallel corridors, maglev and different ground/deck
layers do not generate level-crossing signals.

How the client uses them (MegaMek `docs/3d-board-editor.md`, rails): a hex lays only gentle pieces, straights
between opposite sides and 60-degree arcs between sides two apart. A side without a gentle partner (two adjacent
sides, or the middle of three) ends in a short stub, and every dead end and stub gets a `buffer-stop`, placed by the
route builder and never stored. A legacy sprite always draws its sides' default pieces; the editor stores other
pieces only for the 18 side masks with a choice (`tracks`). A rail marker lies on the ground (`surface ground/top`)
and follows it and its ramps as a road does, or on a bridge deck (`bridge/deck`), whose drawn top it rides; a
vehicle row stands on the rail top. The Rail and Maglev routes are two palette choices in Transport.

## Legacy scenery decode

`scenery/layouts.json` is the decode table for legacy scenery keys: one row per
real object, placed on one canonical mesh. Rotated or baked duplicates are not
shipped. Bevel, ledge, roof grille, chimney stack, skylight, garden bed, pillar,
picnic table, hex plaza, fountain, crawler crane, bulldozer and concrete debris
are canonical components, recentred on their XY bounds and grounded at Z=0. A
legacy stack sprite is a grille and a chimney stack, square1 a plaza, a fountain
and trees, and construction sites 1 and 3 a vehicle and its debris. The fountain's
outer wall reaches the ground: the plaza hides that 0.9 px plinth, bare ground
shows it. Their rows use the same
angles and offsets that baked the old variants. GlassRoof-1-01..04 and
GlassRoof-2-02..04 are rows on the wide glass roof (the 1-0n rows stretch it to the
narrow roof's width), the six crane tips rows on the boom segment `seaport/yard/crane-boom`, OrbitalGun
N/S/W rows on the orbital gun and Landscape 1-03 rows on the round formal garden. The sport pool decks are separate components, so no
row names its own key. Rows carry no `kind`: `tree-broad` is the only tree.
Maglev decodes to a route marker and its pieces (see Maglev). Herds decode to one row per animal.
The legacy container yard and quay crane keys are gone: their art is a container yard look of the hex's woods.

The conversion takes every legacy art token (FLUFF and GROUND_FLUFF below the server values 2000+,
ROAD_FLUFF, WATER_FLUFF, BLDG_FLUFF), so a `.board2` holds none. A token becomes objects (these rows, or a legacy
decal id of `decals/decals.json`: runway, landing pads, letters, courts, rails), a hex design that draws exactly
its art (the blueprint variant whose `selectors` equal the token: `ground/blend/*` transitions at strength
exits/6, `road/rounded`, `road/horizontal`, `woods/orchard`, `rough/obstacles`, `rough/felled-trees`),
or nothing (the transparent wildcard `classic/tileset/blank.png`, old building artwork, quay art the fitted quay
wall replaces). Buildings select current modular kits from their gameplay class and weight. Elevator plates and the cleared-rubble gravel stay rows of their rule terrain (below).

`scenery/layouts.json` and the meshes and decals it names are edited directly. The heli pads
(`fluff/heli1`-`3`) decode to their landing lights (`roofs/landing-light`, rows only) and the pad decal.
No layout may z-fight: within one mesh, and between the rows of a layout, no two upward faces that face the
same way and are shaded differently may lie within 0.1 px of each other where their outlines overlap. The
terrain-owned rubble meshes, which import and the editor never place, are the exception: their thin rebar and
beam flanges cross slabs at shallow angles. No two meshes that rows, palette props or the scatter kit reach may
be copies (the same vertex radii about Z, heights, colours and materials): a rotated or mirrored copy is a row
on the other mesh. `geysers/water-dormant` and `water-erupting` (and their `-b` looks) are the accepted pairs, because
`GpuGeysers` takes the eruption from the asset name.

## Decals

A decal id `decal/<group>/<name>` is the image `decals/<group>/<name>.png`; no
catalog is needed to find it. Images are straight RGBA with north (+y) at the
top; transparent texels carry the colour of the nearest ink so filtering and
mipmaps do not darken edges. The groups:

| Folder | Decals | Source |
|---|---|---|
| `emblems/` | `red-cross`, `capellan-confederation`, `draconis-combine`, `federated-suns`, `free-worlds-league`, `lyran-commonwealth`, `terran-hegemony`, `magistracy-of-canopus`, `outworlds-alliance`, `rim-worlds-republic`, `taurian-concordat`, `star-league`, `comstar` | the seven pieces of the Saxarba 7-hex set stitched at their hex offsets: 144 x 144 px, 1 image px per model px, identical to the unused `-Medium` images |
| `car-park/` | `straight-4`, `-8`, `-12`; `parallel-3`, `-6`; `diagonal-3`, `-6`, `-9` | painted: 6.4 image px per model px; full-size car bays |
| `damage/` | `rubble-light-path`, `cleared-rubble-gravel` | copies of `images/hexes/saxarba/rubble_light_path.png` and `cleared_rubble_gravel.png` (84 x 72) |
| `runway/` | `centreline` (6 x 64), `threshold` (64 x 28), `number-36`, `-06`, `-12`, `-18`, `-24`, `-30`, each also with `l`, `c`, `r` (56 x 72) | redrawn from the legacy runway geometry at 8 image px per model px; designations in Noto Sans Regular (`data/fonts`, OFL); white paint at 95 % |
| `landing-pads/` | `vtol-`, `medic-`, `aero-`, `aero-lit-` each `concrete` and `asphalt` (72 x 72); `dropship-`, `dropship-ring-` each `concrete` and `asphalt` (144 x 144); `heli-pad` (60 x 60) | one-hex pads cut 1:1 from the -01 sprites; DropShip pads stitched from their 7 pieces as the emblems; the heli pad redrawn flat |
| `lettering/` | `letter-a` ... `letter-z`, `digit-0` ... `digit-9` (40 x 40) | the upright black sprite's shape, 4x bicubic, blurred and re-sharpened, white: the object's paint colour (`size` entry `"colour": "#ffffff"`) multiplies it |
| `sport/` | `tennis-court-green`, `-blue` (33 x 63); `basketball-court-green`, `-blue` (39 x 71) | redrawn at 8 image px per model px, 0.75 px lines |
| `elevator/` | `level-minus-10` ... `level-minus-1`, `level-0` ... `level-10` (665 x 576) | an up-and-down arrow and the level, painted by `tools/decals/elevator_levels.py` at 8 image px per model px in Exo 2 Bold (`data/fonts`, OFL), worn white paint at 95 %, over the elevator platform's diamond plate; rows of the elevator's rule terrain, not palette decals |
| `geysers/` | `magma`, `magma-b`, `water`, `water-b` (512 x 512) | each geyser look's photographic study at 8 image px per model px, centred on the model's origin: opaque under the model, fading out 3-9 px beyond it; rows of the geyser's rule terrain (the hex's look), not palette decals |
| `rail/` | `level-crossing` (16 x 27) | retained for standalone authored artwork; native crossings use the continuous road and embedded rails |

The 2D tileset's ground-symbol pieces stay for the 2D board, which draws a
converted board's kept tokens; the conversion matches the Classic tileset's
`decal/` keys; the palette uses the decals here.

`decals/decals.json`:

```json
{
  "format": "megamek-board-decals", "version": 1,
  "decals": {
    "decal/emblems/red-cross": {"size": [144, 144]},
    "decal/car-park/straight-4": {"size": [28.125, 11.5625],
      "slots": [{"position": [-10.3125, -0.09375], "heading": 0}, ...]}
  },
  "legacy": {
    "decal/saxarba/SMV_GroundSymbols/FluffSystem-05-Symbol-01-RedCross-1-04":
      {"decal": "decal/emblems/red-cross", "scale": 0.5, "rotation": 0},
    "decal/saxarba/SMV_GroundSymbols/FluffSystem-05-Symbol-01-RedCross-1-10":
      {"decal": "decal/emblems/red-cross", "set": true},
    "decal/saxarba/SMV_GroundSymbols/FluffSystem-05-Symbol-01-RedCross-1-12":
      {"decal": "decal/emblems/red-cross", "set": true, "direction": 2},
    "decal/saxarba/rubble_light_path": {"decal": "decal/damage/rubble-light-path"}
  }
}
```

- `size`: the decal's footprint at scale 1, model px (the board's hex is 83.125 x 72), centred on
  the object's position. Image px differ per group; only `size` sets the footprint.
- `slots` (car parks only): parking places in the decal's frame, model px from its
  centre, +y toward the back of the bays (the bay centres); `heading` is the car's rotation in
  degrees (CCW, 0 = the car's front to +y, as object rotations). The slots fit
  the car mesh at scale 1 (4.8 x 9.2 px). All authored car placements use this
  native scale, including the suburb and maglev compositions; suburb2's closely
  parked trio is spaced farther apart to clear the larger bodies.
- `legacy`: old decal ids, which are also the legacy tileset images
  (`decal/` + the 2D tileset image path without extension, the Classic tileset's
  key for the token; `.board2` files saved
  before this change use them). `scale` (default 1) and `rotation` (default 0,
  CCW degrees) are the new decal's transform at the old object's position.
  `"set": true` marks a piece of a ground symbol's 7-hex set: import places ONE
  decal at scale 1 and rotation 0 on the set's centre hex, which is the piece's
  own hex for the centre piece (no `direction`) and its neighbour in direction
  `(direction + 3) % 6` otherwise (`direction` is the piece's hex direction from
  the centre: 0 N, 1 NE, 2 SE, 3 S, 4 SW, 5 NW). A set with
  pieces missing on the board paints exactly its present pieces: each gets the
  set's decal on the set centre, clipped to its own hex, one group per set; a set
  cut by the board edge still gets its full emblem at the inferred centre. The
  landing pads' DropShip sets follow the same rule. A legacy row may carry a
  paint `colour` (`"#000000"` on the black letters), which the converted decal
  object stores as its colour. The one-hex variants
  -01/-04 are upright, -02/-05 turned -30 deg and -03/-06 +30 deg; their scales
  were fitted to the legacy tiles (small 0.204-0.326, large 0.346-0.503 per emblem).

Car parks: each standard decal is only its row of bays (straight: 6.875 x 11.25 px
bays; parallel: 12.25 x 6.25 px; diagonal: 60 deg to the row, 6.875 px wide and 13.5 px
long along the car), open on its bottom (road) edge: the dividers reach that edge,
and the back line and the two end dividers lie on the other three edges, so no
asphalt shows beyond them and two rows laid back to back touch line to line.
Unmarked asphalt with white bay lines, no aisle, no road markings, fully opaque.
Two sides are the same decal twice, the second turned 180 deg, one on each side
of the road. In `scenery/layouts.json` each legacy key `fluff/cars_*` (1-8, 2b,
3b) has one decal row per side of its lane that has cars, beside the lane's road:
its road-side edge 14.8 px from the lane's centre line (the road's
15 px half width less about half its 0.45 px asphalt fade, so the decal hides the
road's gray verge and leaves its carriageway clear), the smallest standard of the
cars' layout (across the lane: straight; along it: parallel) with room for that
side's cars. Parking paint can span hex boundaries, so conversion leaves it unclipped
along with the full-size cars. No legacy car park is diagonal. Where no road is drawn (no lane, as
2b/3b; a roof, deck, industrial top, fuel tank, ice or liquid; a road level the
renderer does not draw), the conversion folds the same rows back to back on
the line through the hex centre, turned and mirrored, their closed sides touching.
Each car row carries `"seat": [n, slot]`: the conversion places that car on
`slots[slot]` of the key's n-th decal row (the decal row's transform, mirror
included, applied to the slot; the car keeps its asset, colour and scale). Cars
keep the order they had along the lane. The physical decal footprints and slots were
enlarged together by 1.25 for native-size cars; the existing paint images are reused.
The cars_7/2b shelter moves outward to keep its walkway behind the enlarged bays.
Seats and decal rows exist only for the conversion.

The 64 `saxarba/roads/road_trees00`-`63` layouts keep their 336 scale-0.4
trees. Their anchors are fitted against the actual plain `BoardRoad.clearance`
shape with 1.5 px between pavement and each row's rotated GLB bounds. The broad-tree
bounds at this scale are 6.76 x 7.77 px; alternate park species can overhang the verge.
The straight-road trunks stand 18.57–23.01 px from the axis, with their original along-road spacing.
Conversion and stamps use the union of road and ground-rail exits; only hexes with
conventional ground rail receive extra displacement, measured against the existing `RailRoute`
courses and the centered/beside corridor union, including the track's 1.3 runtime scale.
Maglev receives no conventional-ballast displacement.
Crowns can extend into neighboring hexes. Tree scales and each layout's count stay unchanged.

## Editor palette, import and stamps

The rows serve one reader, the conversion (`BoardSceneryLayouts.convert`, 
wherever a legacy `.board` is loaded (a game's sheets on the server, old
saves, map previews, the editor) it turns a key's rows into separate placed
objects once, with the rows of one key in one group. Stamps in
`data/board-editor/blueprint.json` name a key in their `layout` field and place
its rows the same way; `{exits}` in a stamp's layout becomes the painted hex's
road exits. Beside them, the 3D board draws the rows of the terrain-owned keys
directly: geysers, rubble 1-6, fortified and the cleared-rubble paths (FLUFF
2001-2005), and the elevator plates (`saxarba/misc/elevator_<n>`,
following the elevator's level) and the cleared-rubble gravel (GROUND_FLUFF 2000),
whose decal rows become decals of their hex that are never stored or picked. The
conversion never takes them, and they change during play. So
editing a row changes future conversions, stamps and the terrain-owned keys'
drawing, but never objects already on a converted board or saved in a `.board2`.

Palette rules, checked by `BoardSceneryDecodeDataTest`:

- A visible entry is one real object a user places, or a stamp: 226 props.
- A mesh that only imported objects use is `palette: false` and keeps its
  label (sport-pool parts, plaza ornaments, the second debris pile, the rooster
  and the other animal poses: one visible animal per species). Coats and paints
  are colours, not entries. An entry may place another `model` in `colours`: the
  three ponds are pools in the pond colours. The five `-snow` trees that keep their
  own GLB are `palette: false` too: a tree takes its winter form on a snow surface,
  and its Snow toggle keeps it bare.
- No visible ID is a layouts key. Transport shows the two routes, Maglev and Rail, the crossing signal and the
  roadside-trees stamp (and the level crossing among the decals). Maglev and wagons (28) shows the station
  platform, the city and colony maglev cars, the thirteen rail vehicles and five train stamps: City maglev,
  Colony maglev, Freight train, Express train and Colony train (see Maglev and Rail pieces); the city gangway
  coupler is `palette: false`. Airfield shows the landing light.
- Rotated or baked duplicates are not shipped; terrain-owned scenery (rubble,
  geysers, fortifications) has no prop entry, though its GLBs stay.
- Every decode row's mesh has a blueprint entry, so imported objects have a
  readable name.
- Decals: 102 visible entries, all from `decals/`: the 13 full emblems
  ("Emblems"), the 8 standard car parks ("Car park, straight 12", ... in
  "Ground details"), the light rubble path ("Damage and debris"), the 26 runway
  markings and 13 landing pads ("Airfield"), 36 letters and digits ("Lettering"),
  4 courts ("Sport and pools") and the level crossing ("Transport"). The
  emblem pieces and one-hex variants have no entry; they only decode
  (`decals/decals.json` `legacy`). The elevator plates and the cleared-rubble
  gravel have none either: they belong to their rule terrain.
- Designs include `rough/felled-trees` ("Felled trees", Designs), with the selectors of its legacy token.
  Old building art choices are discarded on import; their gameplay buildings use current kits.

Industry > Seaport holds the container
yard looks and the ten `seaport/yard/` props; import gives a hex with container yard
or quay crane art the container yard look of its woods at its rotation. Imported and placed trees store their
bare species; the renderer draws the `-snow` form on a snow surface unless the
object is marked `"bare": true`.

For 19 species the `-snow` form is a material variant of the bare GLB, not a file:
the six `orchard-*`, `pine`, `pine-broad`, `pine-slender`, `pine-layered`,
`tree-broad`, `birch`, `willow-broad`, `tree-layered`, `birch-spreading`,
`birch-young`, `tree-slender`, `tree` and `birch-tall`. Their materials' extras
`mmSnow` give the snow canopy material and textures, a linear factor on
the crown's vertex colours (the snow cards drop the species' pigment) and the
winter impostor's textures and quad colours; the manifest points their `-snow`
entry at the bare file (`"variant": "snow"`). The runtime builds the winter form
from it (`RigidGlb.source`). `pine-tall`, `tree-dead`, `willow`, `tree-forked` and
`foliage-snow` keep their own winter GLB: their snow geometry or bark differs.

## Rock and scatter meshes

- `rocks/block-N.glb` and `rocks/boulder-N.glb` (N = 0..7) are sixteen independently
  editable rock variants. Each contains three root nodes named `block-N-lod0`,
  `block-N-lod1`, `block-N-lod2` (or `boulder-N-lod0`, etc.). The library has 48
  meshes and 1,572 triangles. Rough terrain, rims, slopes and cliffs share these files.
- `rocks/outcrop-N.glb` (N = 0..7) are bedrock formations used by zero-gravity
  rough and dry natural rough on exposed ridges, in the same layout (`outcrop-N-lod0` to `-lod2`; 92, 44
  and 22 triangles).
- `scatter/` contains 25 independently editable GLBs: `stone-block-N.glb` and
  `stone-boulder-N.glb` (N = 0..7, eight triangles each, open base), `bush-N.glb`
  (N = 0..7, shrub masses, 660 triangles dry and 792 green) and `grass.glb` (six
  triangles). The small scatter plant is the first bush of its biome (`bush-0`
  dry, `bush-4` green).
  Each file contains only its `<shape>-lod0` root mesh (for example, `grass-lod0`)
  and that mesh's vertices.
  The complete scatter kit has 5,942 triangles. Grass and bushes have explicit
  back faces; green and dry grass share geometry.

For terrain rocks, LOD0 is the most detailed version. LOD1 and LOD2 are optional;
the loader resolves missing levels once as LOD2 -> LOD1 -> LOD0, sharing the
existing mesh. LOD0 is required. Fallback stays within one shape and file,
so a scatter stone can never select a larger terrain rock. Scatter uses only
LOD0 and does not load additional levels. Terrain's first two sampling bands use
rock LOD0; subsequent bands use rock LOD1 and LOD2, preserving the established
screen-size thresholds.

These files are the editable mesh source, baked from the original Java shapes.
Import/export one file in Blender as uncompressed GLB, preserving names, triangle
budgets and flat normals. Each shape is a root node. After Y-up to Z-up import,
rocks have their base at zero and a largest horizontal extent of one. There
are no textures or embedded animation clips. Their material is named `geometry`;
the renderer chooses colors and terrain shading. The importer restores shared
corners for CPU ground sampling. Placement, picking and batching share the meshes;
no rock or scatter geometry is generated in-game.

## Contents and editing

- `classic/`: the Classic graphics' art and its tileset, used whatever the player's 2D
  tileset (edit it without affecting 2D). `tileset/classic.tileset` holds the rules in
  one file (the 2D tilesets' format, read in order); the art lies by kind in
  `terrain/` (ground, themes, water and liquid animations, pavement, transitions),
  `vegetation/`, `effects/` (fire, smoke, limbs) and `scenery/` (terrain-owned sprites
  at their layout keys), with the wildcards' transparent `tileset/blank.png`. Each
  image is the level-0 art; `tileset/levels.json` names each ground image's recipe,
  which turns it for the hex's level as the old per-level copies were: a hue turn and
  saturation and value curves, `1 - (1 - x)^k`, from the recipe's table (levels -3 to
  10, fitted to those copies). A level past the table starts from its nearest end and
  adds the recipe's formula, `up` and `down` rates per level eased as Enhanced eases
  heights (`ease`); an empty table leaves the formula alone. Marks, cracks and grass
  tufts can take their own recipe, and fungus ground keeps its own level-0 art.
  Entries for art the 3D board never draws name a key
  instead of an image (`buildings/`, `scenery/`, `decal/`, `quay/`, and `route` for
  roads, `bridge` for bridges, `design` for container yards, `water` for water and
  rapids, which show the water animation (tinted or toned; frozen, its still first
  frame under Enhanced's ice), `space` for transparent space and `magma` for molten
  magma, whose animated surface covers its column); roads, rails, bridges and drops
  have no art here, since the 3D board draws its own in both graphics.
- Buildings use the current kits in `data/models/buildings`, selected by class and weight. The old Saxarba
  per-tile GLBs and their inspection PNGs have been removed. `.board` import keeps building gameplay data
  while dropping the old artwork selection. Selectors `building:4:69` through `building:4:75` are omitted,
  including their building state; the underlying terrain remains. Fuel tanks use connected kits and heavy
  industrial terrain uses generated structures; their retained tileset keys do not refer to old GLBs.
- Foliage GLB files. Counts and the imported Blender source
  names are in `tools/board-models/manifest.json`. Bridge spans are generated at runtime;
  reusable terminal and pier kits remain GLBs.
- Each tree GLB contains `-lod0`, `-lod1`, and `-lod2` groups, with budgets
  of 1000, 300 and 96 triangles including explicit back faces (authored broadleaf,
  volcanic, willow and birch trees 32000, 10000 and 2600; conifers 1200 on the near level; authored shrubs
  24000, 8000 and 2200; desert shrubs 20000, 7000 and 2000; ferns 480, 240 and 96;
  cacti 3600, 950 and 420; apple trees 34000, 10000 and 3200;
  bare trees 12000, 1800 and 180).
  The authored trees spend more geometry on curved, tapered branches and small
  foliage sprays at close range. These are asset ceilings, not measured frame-time guarantees. The conifers,
  palms, saguaros,
  the dead tree and ferns (`foliage-jungle`, with
  `-2` and `-3` variants), and the winter files `pine-tall-snow`
  and `tree-dead-snow`, are grown from each
  species' botany by `tools/board-models/foliage/build_trees.py`:
  conifers as whorls of bent spray cards folded along their stems on a straight
  trunk; palms as a curved trunk under a spiral of folded fronds with dead
  fronds hanging beneath (`palm` a date palm, `palm-bent` a coconut palm). The additional
  `palm-compact` has an upright, compact date-palm crown; `palm-arching` has a medium crown of arching fronds
  on a gently curved trunk. Their independent parameters live in `build_trees.py`, with editable meshes in
  `sources/palm-density.blend`. Their
  fronds arch, sweep and twist individually, with the same crown sampled at each
  mesh level. Saguaros have tapered, ribbed columns, uneven elbowed arms and small
  growing tips, with corking concentrated at their feet; `cactus-flowers`
  with white blossoms on them; the dead tree as a bleached oak snag whose limbs
  have connected bare branches instead of a shell of twig cards; ferns grow as
  trunkless palms. The bare tree's branches are grown from its seed (`bare_skeleton`): a low fork into crooked
  limbs within a crown half as wide as the tree is tall, with side branches and twigs. The generator rounds those
  paths and retains their hierarchy at each mesh level, drawing the wood it keeps thicker at the coarser levels;
  pruning a branch removes its children. Change a species or its source there and rebuild it rather than editing
  its GLB. The nineteen broadleaf, volcanic, willow and birch forms use editable branch curves and
  attached foliage in `sources/forest.blend` and `sources/forest-density.blend`, exported by `build_forest.py`.
  The latter adds mature and forked birches, an arching willow, and upright and spreading cinder crowns;
  birches and willow also carry snow material variants. Rebuild that source with
  `build_forest.py --source tools/board-models/foliage/sources/forest-density.blend`, then bake its impostors.
  Their near sprays fold about
  the midrib. Coarser levels simplify the same branch paths and use nested spatial crown samples with
  fixed twig anchors, normals, pigmentation and crown bounds. Major limbs remain at the far mesh level.
  Crown limits reduce a whole spray uniformly; individual corners are never clipped into flat canopy plates.
  The cinder forms leave a clear lower trunk and gaps between the main limbs, with smaller sprays of the new
  photographic leaves and a restrained red/rust tint in their Material Maker graph.
  Level-one barren, highland, rocky, snow, temperate, volcanic and wetland cover uses 21 shrub forms
  in `sources/shrubs.blend`, exported by `build_shrubs.py` through the shared forest exporter.
  Three desert forms use `sources/desert-shrubs.blend` and the same exporter, with smaller narrow-leaf
  sprays instead of whole-bush cards. Their isolated `desert-shrub-cutout` Material Maker graph adapts
  the existing photographed twig source to muted foliage and a rougher surface.
  Their basal forks, tapered branches and attached foliage retain the same source at every mesh level;
  stems grow above the ground rather than flattening below-ground branches into the root plane.
  They reuse the verified Material Maker bark and photographic leaf materials, including the new cinder leaves.
  These are live level-one woods assets, separate from taller forest trees. Planted fields use `BoardFields`
  and the instanced wheat/maize in `GpuGroundCover`; the obsolete field prop and its fallback have been removed.
  The summer and winter forms share this geometry; each distant impostor is baked from its near model.
  Their isolated `forest-*` Material Maker projects supply bark relief, roughness and leaf transmission.
  The six apple orchard trees use editable Blender curves and photographic
  fruiting sprays in `tools/board-models/foliage/sources/orchards.blend`.
  `build_orchards.py` exports their rounded crowns and tapered branches, preserving
  dense foliage at all three mesh levels. Rounded apples hang by short stems from
  retained outer twigs, up to 144 per mature tree (72 on the young tree), with 96/48
  fruit retained at coarser levels (48/24 on the young tree). The distant meshes retain 900 and 360
  distributed sprays respectively, with the same crown bounds as the close tree.
  The fungus theme's woods (`fungus/cup-*`, `fungus/spore-*`, fluted
  cup fungi and pitted spore pods on the fungus atlas) and the Mars corals
  (`mars/*`) are modelled in Blender; `tools/board-models/alien_lods.py` builds
  their mesh levels from the original meshes (in git history), weathering their
  corner colours; it gives the cliffs' hanging mycelium the
  `textures/vegetation/fungus/mycelium` material, whose emission makes it glow.
  Standard glTF `MASK` materials use a 0.5 alpha threshold. The authored forest and orchard sprays use
  0.3 to retain their sparse photographed leaves under mip filtering at distance.
  Each material's threshold is identical in color, depth and shadow passes. The bake uses each source material's own
  cutoff when rendering its leaves and computing its lighting.
  A `-lod3` group holds the plant's impostor, standing for its far mesh (LOD2): one quad (2 triangles, stored as a
  horizontal square about the crown's centre on the plant's axis, as wide as the sphere there that holds the far mesh)
  that the game turns toward the camera. `textures/vegetation/impostors/<name>.png` holds unlit renders of the far
  mesh from 8 directions around it at 10, 35.26 (the board's isometric view), 60 and 90 degrees above the horizon,
  48 by 48 texels each (384 by 192), with edge colours dilated for the cutout; `<name>_normal.png` holds the mean
  normal of the surfaces each texel shows, in the plant's own axes, as short as they face different ways (a thin
  branch's sides), and their depth along the render's view: the game lights each texel with that normal and its
  spread, and takes its shadow and writes its depth at that surface, as the mesh's. Each pixel shows the render nearest its view (impostor-frames.glsl must match the
  bake). The quad's vertex colour carries the plant's mean occlusion, its share of bark, cactus or snow (lit as
  solid), and its leaves' roughness and scatter. `<name>_crown.png` is the far mesh's coverage from straight above,
  which the game measures crown cover from. `prepare_tree_lods.py -- impostors` re-bakes them (see Editing and
  checks); `calibrate_impostors.py` then fits each impostor's coverage and colour, per row of frames, so that it
  covers what the far mesh covers and is as bright where the game switches to it, seen from that row's height,
  measured in the game.
  The manifest records every level; screen-pixel thresholds live in Java's
  `TreeLod`, so no camera or game state is baked into these assets.
- Every plant's origin is the foot of its trunk, where the board places, grounds and
  clears roads for it; a leaning crown (bent palm, willow) overhangs to one side.
  The maintained GLBs keep that origin and their bark projection. Cactus skin
  wraps around each stem, following bent arms.
  The compact `cactus-young` form has four unequal arms; the veteran has six main arms and two secondary forks,
  and the organ cactus has nine unequal stems. Geometry levels preserve these branches.
  Ordinary woods and jungle aim for 30%, 75% and 100% crown coverage inside each hex. Coverage uses the union of
  the crown masks' silhouettes with only small gaps closed; cacti use rotated model XY boxes at 85% width and depth
  (about 72% of their full box area), without resizing the model. Bare `tree-dead`
  contributes 15% visual cover at normal width, scaled by horizontal area, rather than filling gaps between twig pixels.
  Ordinary canopy plants are capped at 3/6/9, including palms and height-one cover shrubs. Bare trees are spread
  apart and capped at 2/4/6; cacti have their own 3/8/12 caps. Each cap also applies in mixed stands and takes
  priority over the coverage target. Ordinary plants retain their natural size. For level-two/three trees, the regional
  family is selected before its crown form. Light favours medium crowns, reserves its widest forms for heavy/ultra,
  and permits sparse accents only after two canopy plants. Heavy/ultra favour fuller forms within that same family.
  Size classes use the existing LOD0 crown mask at the normal level-two scale; families with no medium form use their
  fuller available forms. Terrain density edits may change these variants and their placement; camera and LOD never do.
  The added forms broaden the variant choices after the regional family draw, preserving biome family frequencies.
  Palms choose among four crowns after the unchanged regional family draw; light excludes the largest form
  (crowns above 85% of that family's widest measured area), while heavy/ultra favour fuller forms.
  Low shrubs, cacti, bare trees and rigid colonies retain their existing selection rules. Orchards use 4/6/9 trees in
  rows, and yard/container skins are excluded. Rigid fungal and Martian tiers use 30%/75%/100% of a common
  collision-safe packing, bounded by their separate 8/20/36 safety limits, rather than literal ground coverage.
  Fungal spore bodies use a dedicated species pool, with at most one/two/three bodies in light/heavy/ultra cover.
  They supplement a required cup at the hex's cover height and share its collision checks and stable packing. All
  solid bodies remain inside the hex and do not intersect. Cacti share these geometry-based checks, including after
  terrain support moves their roots; empty space between arms is available for packing. Connected cross-sections derived from all three mesh LODs
  test collision at matching heights, keeping separate cups and branches separate. Each component has a conservative
  twelve-plane enclosure; concavities inside one connected component remain filled. There is no extra trunk-spacing rule.
  Compact members and limited width fitting help fill gaps. Searches reuse prepared orientations locally; no placement
  cache outlives a capture. Ultra targets all of that packing's coverage. Whole-body increments make the
  percentage targets approximate. Existing terrain support settles roots onto the actual cliff top; crowns may overhang
  that top. Rigid colonies recheck intersections after settling. All natural plant anchors use canonical full-detail
  terrain geometry, so camera movement and LOD changes cannot move them. Terrain edits refresh that geometry.
  Each fungal cup GLB also has a data-only `spores` root containing named Empty nodes, one inside each bowl, below its rim.
  X/Y scale gives the radius of the upward wisp. These nodes render no geometry and are independent of the four LOD
  groups. Import a GLB in Blender to move or resize them. Both the alien mesh rebuild and impostor exporter preserve
  the nodes. The renderer applies each installed plant's full transform to them; plume width follows horizontal
  scale and its rise follows vertical scale. Porous round, pear and clustered spore forms emit no individual mist;
  the shared fungal-hex cloud remains independent of the cups' wisps.
  The leading colony member reaches the rules' cover height. Level-three forest crowns are 20% wider than
  level-two crowns; tropical understory remains a separate low layer.
- `textures/vegetation/*-cutout`: eight shared 512 by 512 cutout materials
  for broadleaf/conifer and their snow variants, palm fronds, cactus flowers, ferns and shrubs. Near, medium and far crowns
  share these clamped images; impostors are baked from the same alpha-tested
  geometry. The Material Maker projects under `tools/materials/vegetation/` generate them.
  Bark textures are shared.
- `textures/vegetation/cactus-skin`: 512-square photographic albedo, shallow normal
  relief and packed roughness, shared by all five cactus variants at all three mesh
  levels. Its Material Maker graph combines the photographic epidermis and areoles
  with restrained procedural weathering: the same field varies pigmentation and
  roughness (0.74–0.94). Near meshes carry the major ribs in their silhouettes;
  coarser meshes retain the normal detail. Basal corking is vertex color, so it
  never repeats up the arms. The normal-map tuning switch applies to these maps too.
- `textures/vegetation/`: five shared 64 by 64 detail albedos for palm fronds,
  ordinary bark, birch bark, ringed palm bark and snow. Source material boundaries keep snow caps separate
  from green foliage and preserve the birch's pale trunk and dark scars. Existing
  vertex colors tint the pale maps; dominant-axis UVs follow the tree's original
  proportions. Snow variants use their own authored geometry.
- `orchard-*.glb`: six pruned apple tree forms (their winter files are the snow
  variant). Near foliage sprays meet real twigs at the photographed stem's
  U=0.5, V=0.978 endpoint. Rounded fruit and its stems share source twig anchors
  across detail levels. Overlapping sprays and normals following the whole
  crown avoid separately lit, detached-looking caps. Coarser levels retain
  the same scaffold and a wider subset of its sprays. The Material Maker
  `orchard-cutout` graph supplies leaf roughness, relief and transmission;
  `apple-skin` supplies the fruit's red blush, lenticels and waxy surface.
- `tree-dead.glb` and `tree-dead-snow.glb`: opaque, tapered branch geometry, with
  weathered ends and bark grain following each limb. The snow form keeps the same
  branching and adds snow to upward-facing surfaces. Their Material Maker
  `dead-wood` graph supplies the shared wood surface; they no longer use twig cards.
- `textures/vegetation/marsh-sedge_albedo.png`: the editable 1254 by 1254 RGBA sedge/cattail
  cutout for marsh vegetation. The renderer filters it to one shared 512 by 512
  texture with mipmaps; all three plant LODs use this same image. Ground peat,
  moss and pools are shaded separately using the existing sculpt earth maps.
- `textures/structures/facades/`: shared 128 by 128 facade maps retained as material resources. Current
  modular buildings use the authored panels and materials documented in `../buildings/README.md`.
- `textures/terrain/classic/`: Classic mode's 128 by 128 column wall maps (concrete, dirt, rock,
  sand, snow, lunar, fungus, mars and volcano; each repeats once per 96 world units), the
  `water-bed` map for liquid banks and beds, and the two 84 by 72 incline rim masks
  (`incline-dark`, `high-incline-dark`). The Material Maker projects under
  `tools/materials/structures/facades/` and `tools/materials/terrain/classic/`
  generate both folders.
- `textures/terrain/surfaces/`: the sculpted terrain's 512 by 512 materials (ground,
  debris, wall and mantle maps for every surface family): `NAME_albedo.png` is sRGB
  albedo, `NAME_heightmap.png` normalized height, `NAME_normal.png` a tangent normal
  (OpenGL convention) and `NAME_orm.png` ambient occlusion and optional authored
  roughness. `textures/materials.json` gives the metres each repeat spans at the
  catalogued width. The Material Maker projects under
  `tools/materials/terrain/surfaces/` generate them; their relief is an artistic
  estimate, not a measured scan. See `tools/terrain-realism/README.md` for the
  stone sources and visual references.
- Liquid artwork comes from `classic/terrain/water/anim_water_N.gif`,
  `classic/terrain/ground/base_magma_anim.gif`, and `classic/terrain/water/rapids_anim.gif` /
  `torrent_anim.gif`, copies of the original 32-frame, 3.2-second animations. Mars
  and volcano water play the water animation in their theme's tone (`BoardLiquid.Tone`),
  hazardous liquid tinted green. The
  runtime selects these images (`BoardLiquid.textures`), so they stay even where
  the tileset omits them.
  `GpuWaterShader.USE_PROCEDURAL_WATER` selects shader-generated water patterns
  and palettes matched to this artwork, using the renderer's shared noise field.
  Set it to `false` and rebuild for the authored water GIFs. Both paths share
  wave/rain normals, lighting, reflection, downstream currents and waterfall foam/spray.
  Magma retains its original artwork. `GpuLiquidShader.USE_SHADER_ANIMATION`
  interpolates the original GIF frames; set it to `false` for discrete frame timing.
  In the GIF path, transparent foam is composed onto the water image. Hazardous
  liquid shares the water material with a green tint in both paths.
  The renderer constructs curved banks and actual depth; the static
  `Structured_Water` art is a shoreline reference, not a baked replacement.
  Two nonadjacent water openings form a continuous channel. Elevation drops
  use vertically scrolling, animated water on the waterfall face.
- A Classic column's exposed top edges take the lightness masks
  `textures/terrain/classic/incline-dark` (drops up to two levels) and
  `high-incline-dark`, oriented per edge, leaving road approaches open.

Each building GLB embeds its processed RGB roof texture: the source roof's opaque
pixels at their UV locations, with RGB extended only outside the roof mask to
prevent filtering fringes. Each `buildings/<name>.png` is an exact copy of the
original tile artwork, including transparency and shadows, for inspection beside
`<name>.glb`. Edit the facade Material Maker projects under
`tools/materials/structures/facades/` to change windows/walls.

Models are indexed GLB with positions, flat normals, vertex colors and UVs.
The importer converts glTF Y-up and linear colors back to the board convention.
In the runtime representation Z is up; X/Y use the 2D art's 84 by 72 pixel hex. The 3D board's hex is regular,
83.125 by 72, and placement narrows these hex-filling models along X to fit it.
Plants preserve their original proportions at local height 30. Buildings,
including tanks and industrial structures, stand at Z=0 with their roof at
Z=18: one default board level, visible at useful proportions in ordinary GLB
viewers. Placement fits their actual bounds to the game's feature height;
interior floors/columns share the shell's coordinates and placement. Wall UVs
and facade repetition remain independent of these authored coordinates.
Crops retain their legacy height-one convention. Bridge decks, kerbs and trusses
are generated and cached at runtime by `BoardBridgeMesh` and `BoardBridgeTruss`.
Their outlines follow the shared road footprint and the actual railway routes
on the deck. Kerbs and trusses follow the outside of the joined deck and leave
connected exits open. Five- and six-way road junctions retain their roundabout
islands; railway junctions have clear centres. No per-pattern span GLBs are used.
The runtime places each span at the bridge elevation plus the road surface
clearance. Board scale applies uniformly; terrain-level height affects only
elevation, never slab thickness or rail height.
The deck uses shared road asphalt and the road's normal/surface maps, lighting
and world-space texture phase. Sides and underside use shared repeating concrete.

Two concrete kits complete the deck; each is a set of root meshes named `<part>-lod0`/`-lod1`, outside
the manifest. `bridges/bridge-terminal.glb` is the bank end block. `bridges/bridge-pier.glb` is the hammerhead
pier that stands under a deck joint, on the edge two bridge hexes share, never at a hex centre (56 triangles
at LOD0, 40 at LOD1). Its origin is the edge midpoint; X runs along the edge (across the deck), Y along the
deck. Three parts keep the pier undistorted at any height: `bridge-pier-cap` (17 by 9, Z=0 at the deck
underside, top 0.75 up inside the slab, tapered soffit at Z=-6), `bridge-pier-shaft` (11 by 8 with chamfered
corners, unit height Z=0..1, no end faces; stretched between footing and cap) and `bridge-pier-footing`
(16 by 13, Z=0 at the floor, a 1-unit lip, buried 6). The runtime (`BoardBridgeFooting`) places one pier under
each joint of a bridge whose Pillars toggle is on: each of the two hexes builds the half on its own side of the
edge, cut at the kit's mirror plane and closed by its section there, so the pier must stay mirror-symmetric in X
and Y and each part convex. `bridges/maglev-pier.glb` is the same kit for the elevated maglev's pillars, with
parts named `maglev-pier-*`: cap 6 by 4 under the 4 wide beam (soffit at Z=-2.5), shaft 3.2 square, footing 7 by
7 (a 0.6 lip, buried 4). The same runtime code places it: one pier on each shared edge of two hexes of a maglev
route whose Pillars toggle is on (the marker's `"pillars": true`, set for the whole connected route), from below
the floor up to the beam's underside, and none where the beam is less than a level up or a road, ground rail or
bridge deck crosses the edge beneath.

Textures and meshes are shared;
translucency changes instance materials, not the assets. Snow trees have their
own snow materials, as variants of the bare tree where it shares their shape.
Rough terrain places the shared GLB rock templates in its terrain mesh.
Enhanced draws its own ground materials; the Classic art has no normal maps.

## Materials

Every material under `textures/` is a Godot 4 `StandardMaterial3D`, as Material Maker's Godot 4 Standard export
writes it: `NAME.tres` with its `NAME_albedo.png` and, as it needs them, `NAME_orm.png` (occlusion, roughness,
metallic), `NAME_normal.png` (OpenGL convention), `NAME_heightmap.png`, `NAME_emission.png` and `NAME_sss.png`.
Models name these maps directly. `textures/materials.json` sorts the materials: loose ones repeat across the board
at a fixed texel density, so a wider export covers more ground before repeating; constrained ones fit their
footprint. `tools/materials/README.md` describes the export, and megamek's `docs/gpu-board-materials.md` how the
game reads the files. `scenery/fortified-sandbag` is made from two photographic studies instead
(`tools/board-models/military/sandbag_atlas.py`, its studies in `sources/` beside it), into the same files.

## Editing and checks

The GLB, PNG and JSON files here are the source: edit them directly. Run the tools from the mm-data root
(Python requires Pillow; `tools/materials/export.py` requires Material Maker):

```text
python tools/materials/export.py
python tools/board-models/foliage/build_trees.py [names...]
blender --background --factory-startup --python tools/board-models/foliage/build_forest.py -- [forest-names...]
blender --background --factory-startup --python tools/board-models/foliage/build_orchards.py -- [orchard-names...]
blender --background --factory-startup --python tools/prepare_tree_lods.py -- impostors [names...]
python tools/calibrate_impostors.py [--megamek PATH] [names...]
python tools/validate_board_assets.py
```

`export.py` exports every Material Maker project under `tools/materials/` into `textures/`. After editing a
plant GLB, `prepare_tree_lods.py` re-bakes its LOD3 impostor and crown mask (every plant's without names; plants
whose fourth level is a mesh, the crystals, keep it); the bake preserves the three mesh levels and the impostor's
cutoff and tints, owns a temporary Blender scene and preserves the active scene. For the 19 species whose `-snow` form lives
in the bare file it also renders the winter impostor (`<name>-snow*.png` and its quad colours, `mmSnow` on the
impostor material) from the far mesh in that form. `calibrate_impostors.py` then runs megamek's
GpuImpostorCalibrationSmokeTest through Gradle in a megamek checkout (default: `../megamek`), which compares each
plant's far mesh and impostor at the switch in the board's own frame at 8, 13 and 17 h, from each row's height
(10, 35.26 and 60 degrees, and straight above), and writes each file's alpha cutoff into its GLB and, per atlas row,
a colour factor and a coverage exponent into the atlas and its fits (`mmImpostorTint`: by atlas, per row
[r, g, b, exponent], which a rebake applies); later runs refine them, and the same test without its property checks
the result.

`validate_board_assets.py` checks each manifest entry against its GLB: the plant levels `-lod0` to `-lod3` and
their family-specific triangle budgets, the triangle counts (at most 500 per other model),
understory and orchard grounding, LOD0 height and every coarser
mesh level's height from 10% below to 1% above it,
embedded images and that every external texture exists inside this directory. It refuses G3DJ meshes.
Native Java integration tests additionally check transparency, lighting,
water animation and representative model loading.

## Provenance

Roof/terrain/water art comes from the existing MegaMek data tileset; its license
headers and original paths are retained. The repository license remains at
`../../../LICENSE`.

The crop model, the grown plants and the bridge terminal and pier kits are original work. The plant cutouts and
the dead tree's wood are photographic studies made with the built-in image_gen tool and keyed into their Material
Maker projects by `../../../tools/materials/plant_sources.py`.
Dirt, sandstone, rock, concrete and windowed facade albedos were generated with
the built-in image_gen tool; exact prompts are in
`../../../tools/board-texture-prompts.json`. The seven contextual facade albedos
also used built-in image_gen. Only the 128 by 128 runtime maps are shipped.

## Plant GLB packaging

Each plant has one GLB, for example `vegetation/pine.glb`, containing
identity groups `pine-lod0`, `pine-lod1`, `pine-lod2` and the impostor `pine-lod3`. Their authored geometry,
UVs and material roles are preserved. The runtime chooses one level and resolves
missing optional levels toward LOD0 once while loading. Foliage PNGs are
external, under `textures/vegetation`, shared by all variants and levels.
All levels have natural proportions and a base at zero, including when inspected
in an ordinary GLB viewer. Export and LOD preparation never flatten the height.
LOD coverage checks compare the shipped near mesh with its coarser levels.

## Building GLBs and textures

Current modular and authored building assets live in `data/models/buildings`; see
`../buildings/README.md` for their assembly, footprint and interior contracts. The retired per-tile Saxarba
GLBs and their dedicated roof images are no longer used.

`RigidGlb` supports embedded PNG/JPEG diffuse images and local image references.
`ModelTextures` caches images with their sampler state, releases native pixels
after upload, retains encoded bytes for context restoration and gives texture
disposal to the owning asset library. Unit and plant models use the same path.
A texture used only by one model may be embedded in its GLB; textures shared by several models or board
materials stay external under `textures/`. There is no measured runtime performance gain claimed from embedding.

Deployed `data/` and authoring/reference `tools/` meshes are GLB; there are no G3DJ files.

See the glTF image specification:
https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#images
