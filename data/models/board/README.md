# 3D board assets

This directory is the libGDX board's independent art source. Runtime never reads
terrain or water from the 2D board's images directory. The Java build stages this
directory with the game's data. Blender is an authoring dependency only.

## Scenery folders

Scenery meshes live in topic folders under `scenery/`, with kebab-case names:

| Folder | Contents |
|---|---|
| `roofs/` | rooftop objects: bevel, ledge, roof grille, chimney stack, skylight, glass roof and dome, landing beacons |
| `parks/` | bench, picnic table, garden bed, pillar, hex plaza, fountain, plaza variants, formal gardens, grandstand |
| `pools/` | sport pools (deck, main and wading basins), rectangular, round and freeform pools; a pond is a pool in pond colours |
| `vehicles/` | the car (its paint is a colour slot), parking barrier, parking shelters |
| `road/` | stop sign, three-aspect pole signal and curved mast-arm signal gantry; facing +Y with pole bases at Z=0; generated road-junction controls |
| `construction/` | crawler crane, bulldozer, concrete debris, excavation site, concrete pipe |
| `farm/` | one mesh per animal and pose: cow, pig, horse, bison, hen and rooster; coats are colour slots |
| `seaport/` | the legacy container rows, gantry cranes and crane tips, decoded no more: objects of `.board2` files written before batch 12 |
| `seaport/yard/` | the container yard looks' ten compositions (`yard/<name>` in `layouts.json`) and the ten seaport props |
| `maglev/` | route marker (the only rail mesh), station platform, city and colony vehicles, the city gangway coupler; `train.png` and `colony-train.png` are the stamps' thumbnails |
| `military/` | orbital gun, fortification |
| `rubble/` | rubble by structure type, and the cleared paths through it |
| `geysers/` | dormant and erupting water geysers, magma geyser |

No mesh sits at a legacy key. A legacy key is `scenery/<tileset image path
without extension>`; it resolves only through `scenery/layouts.json`, so that
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

Every vertex whose colour differs between a family's coats belongs to the slot
that reproduces it for every coat; each car and pond row names its colours.
Coats that differ only in colour share one mesh with colour slots, so there are
12 animal meshes.

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

The track's rail top lies 1.4 px above its carrier plane (ballast top 0.6, sleepers 0.3, rails 0.5; gauge 4.2).
Every rail piece has its origin on the track centre line at rail-top height, the track along Y: a piece placed
1.4 px above the carrier plane rides the rails. Locomotive and power car noses and the buffer stop's buffers face
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
nothing. The six level crossings `rail_road01`-`06` (FLUFF 10:64-69) add three things: the marker on the rail's
axis, the `decal/rail/level-crossing` panel turned to the two axes, and four crossing signals. Each signal stands
beside the road, 10 px from its centre line and 8.5 px from the track's, and faces the road traffic that comes
towards it.

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
exits/6, `road/rounded`, `road/horizontal`, `woods/orchard`, `rough/obstacles`, `rough/felled-trees`, the 55
`building/legacy-art-N` building art designs, or the asset variant of the building model chosen beside the art),
or nothing (the transparent wildcard `saxarba/misc/blank.png`, `bldg_fluff:0`, quay art the fitted quay wall
replaces). Elevator plates and the cleared-rubble gravel stay rows of their rule terrain (below).

`scenery/layouts.json` and the meshes and decals it names are edited directly. The heli pads
(`fluff/heli1`-`3`) decode to their landing lights (`roofs/landing-light`, rows only) and the pad decal.
No layout may z-fight: within one mesh, and between the rows of a layout, no two upward faces that face the
same way and are shaded differently may lie within 0.1 px of each other where their outlines overlap. The
terrain-owned rubble meshes, which import and the editor never place, are the exception: their thin rebar and
beam flanges cross slabs at shallow angles. No two meshes that rows, palette props or the scatter kit reach may
be copies (the same vertex radii about Z, heights, colours and materials): a rotated or mirrored copy is a row
on the other mesh. `geysers/water-dormant` and `water-erupting` are the one accepted pair, because `GpuGeysers`
takes the eruption from the asset name.

## Decals

A decal id `decal/<group>/<name>` is the image `decals/<group>/<name>.png`; no
catalog is needed to find it. Images are straight RGBA with north (+y) at the
top; transparent texels carry the colour of the nearest ink so filtering and
mipmaps do not darken edges. The groups:

| Folder | Decals | Source |
|---|---|---|
| `emblems/` | `red-cross`, `capellan-confederation`, `draconis-combine`, `federated-suns`, `free-worlds-league`, `lyran-commonwealth`, `terran-hegemony`, `magistracy-of-canopus`, `outworlds-alliance`, `rim-worlds-republic`, `taurian-concordat`, `star-league`, `comstar` | the seven pieces of the Saxarba 7-hex set stitched at their hex offsets: 144 x 144 px, 1 image px per model px, identical to the unused `-Medium` images |
| `car-park/` | `straight-4`, `-8`, `-12`; `parallel-3`, `-6`; `diagonal-3`, `-6`, `-9` | painted: 8 image px per model px |
| `damage/` | `rubble-light-path`, `cleared-rubble-gravel` | copies of `images/hexes/saxarba/rubble_light_path.png` and `cleared_rubble_gravel.png` (84 x 72) |
| `runway/` | `centreline` (6 x 64), `threshold` (64 x 28), `number-36`, `-06`, `-12`, `-18`, `-24`, `-30`, each also with `l`, `c`, `r` (56 x 72) | redrawn from the legacy runway geometry at 8 image px per model px; designations in Noto Sans Regular (`data/fonts`, OFL); white paint at 95 % |
| `landing-pads/` | `vtol-`, `medic-`, `aero-`, `aero-lit-` each `concrete` and `asphalt` (72 x 72); `dropship-`, `dropship-ring-` each `concrete` and `asphalt` (144 x 144); `heli-pad` (60 x 60) | one-hex pads cut 1:1 from the -01 sprites; DropShip pads stitched from their 7 pieces as the emblems; the heli pad redrawn flat |
| `lettering/` | `letter-a` ... `letter-z`, `digit-0` ... `digit-9` (40 x 40) | the upright black sprite's shape, 4x bicubic, blurred and re-sharpened, white: the object's paint colour (`size` entry `"colour": "#ffffff"`) multiplies it |
| `sport/` | `tennis-court-green`, `-blue` (33 x 63); `basketball-court-green`, `-blue` (39 x 71) | redrawn at 8 image px per model px, 0.75 px lines |
| `elevator/` | `level-minus-10` ... `level-minus-1`, `level-0` ... `level-10` (84 x 72) | copies of `images/hexes/saxarba/misc/elevator_<n>.png`; rows of the elevator's rule terrain, not palette decals |
| `rail/` | `level-crossing` (16 x 27) | redrawn: two 15 px strips (road and rail) at 60 degrees, concrete, yellow dashed edges; placed by the level-crossing rows |

The 2D tileset's ground-symbol pieces and their copies under `tileset/` stay for
the 2D board, which draws a converted board's kept tokens, and for the conversion,
which matches the `tileset/` copy; the palette uses the decals here.

`decals/decals.json`:

```json
{
  "format": "megamek-board-decals", "version": 1,
  "decals": {
    "decal/emblems/red-cross": {"size": [144, 144]},
    "decal/car-park/straight-4": {"size": [22.5, 9.25],
      "slots": [{"position": [-8.25, -0.075], "heading": 0}, ...]}
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

- `size`: the decal's footprint at scale 1, model px (a hex is 84 x 72), centred on
  the object's position. Image px differ per group; only `size` sets the footprint.
- `slots` (car parks only): parking places in the decal's frame, model px from its
  centre, +y toward the back of the bays (the bay centres); `heading` is the car's rotation in
  degrees (CCW, 0 = the car's front to +y, as object rotations). The slots fit
  the car mesh at its car-park scale 0.8 (3.84 x 7.36 px) with at least 0.33 px to
  every bay line.
- `legacy`: old decal ids, which are also the legacy tileset images
  (`decal/` + the tileset image path without extension; `.board2` files saved
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

Car parks: each standard decal is only its row of bays (straight: 5.5 x 9 px
bays; parallel: 9.8 x 5 px; diagonal: 60 deg to the row, 5.5 px wide and 10.8 px
long along the car), open on its bottom (road) edge: the dividers reach that edge,
and the back line and the two end dividers lie on the other three edges, so no
asphalt shows beyond them and two rows laid back to back touch line to line.
Unmarked asphalt with white bay lines, no aisle, no road markings, fully opaque.
Two sides are the same decal twice, the second turned 180 deg, one on each side
of the road. In `scenery/layouts.json` each legacy key `fluff/cars_*` (1-8, 2b,
3b) has one decal row per side of its lane that has cars, beside the lane's road:
its road-side edge 7.3 px from the lane's centre line (`ROAD_EDGE`: the road's
7.5 px half width less half its 0.45 px asphalt fade, so the decal hides the
road's gray verge and leaves its carriageway clear), the smallest standard of the
cars' layout (across the lane: straight; along it: parallel) with room for that
side's cars. No legacy car park is diagonal. Where no road is drawn (no lane, as
2b/3b; a roof, deck, industrial top, fuel tank, ice or liquid; a road level the
renderer does not draw), the conversion folds the same rows back to back on
the line through the hex centre, turned and mirrored, their closed sides touching.
Each car row carries `"seat": [n, slot]`: the conversion places that car on
`slots[slot]` of the key's n-th decal row (the decal row's transform, mirror
included, applied to the slot; the car keeps its asset, colour and scale). Cars
keep the order they had along the lane; beside the road they move up to 22.0 px
(mean 3.7-12.5 px per key) from their legacy spots, back to back up to 23.0 px
(mean 8.7-13.4 px). Seats and decal rows exist only for the conversion.

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
- Designs: `rough/felled-trees` ("Felled trees", Designs) and the 55
  `building/legacy-art-N` variants ("Legacy building art N", 100: "Legacy roof
  outline"; group "Legacy building art"), each with the `selectors` of the
  legacy token it stands for.

The 78 legacy seaport pieces are off the palette; objects of `.board2` files written
before batch 12 keep them and their labels. Industry > Seaport holds the container
yard looks and the ten `seaport/yard/` props; import gives a hex with container yard
or quay crane art the container yard look of its woods at its rotation. Imported and placed trees store their
bare species; the renderer draws the `-snow` form on a snow surface unless the
object is marked `"bare": true`.

For 19 species the `-snow` form is a material variant of the bare GLB, not a file:
the six `orchard-*`, `pine`, `pine-broad`, `pine-slender`, `pine-layered`,
`tree-broad`, `birch`, `willow-broad`, `tree-layered`, `birch-spreading`,
`birch-young`, `tree-slender`, `tree` and `birch-tall`. Their materials' extras
`mmVariants.snow` give the snow canopy material and textures, a linear factor on
the crown's vertex colours (the snow cards drop the species' pigment) and the
winter impostor's texture and card colours; `manifest.json` points their `-snow`
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

- `tileset/saxarba.tileset`: the forced 3D tileset, with all recursive includes
  and referenced images, including references outside the Saxarba subdirectory.
  The 7,295 files are independent copies. Edit these without affecting 2D.
- `buildings/`: 3,295 structure models with roofs derived from the exact selected
  tile image. Simplified outlines retain diagonal walls, curves, disconnected
  parts and courtyards; no runtime pixel extrusion or generic substitutions.
- `building-manifest.json`: each structure's source, facade family, wall tint,
  outline, vertex and triangle counts. The largest has 499 triangles. Fuel tanks
  and industrial structures use their selected Saxarba artwork too; there are no
  generic cylinder/factory substitutes.
- `field.glb` and foliage GLB files. Counts and the imported Blender source
  names are in `manifest.json`. Bridge spans are generated at runtime;
  reusable terminal and pier kits remain GLBs.
- Each tree GLB contains `-lod0`, `-lod1`, and `-lod2` groups, with budgets
  of 480, 240 and 96 triangles including explicit back faces. Sixteen leafy
  variants retain their authored trunks and crown envelopes but replace closed
  leaf shells with cutout branch clusters. Standard glTF `MASK` materials use
  a 0.5 alpha threshold in color, depth and shadow passes. Pine branch roots
  follow the authored curved trunk. Palms use curved, folded cutout fronds;
  cacti retain their stem silhouettes with smooth normals, mapped ribs and
  cutout flowers. Dead trees keep their existing near meshes and decimated or
  component-hull distant meshes. These runtime GLBs are the maintained tree
  meshes.
  A `-lod3` group holds the plant's impostor: two crossed vertical cards and a
  horizontal cap through the crown, 12 triangles with their backs, textured by
  `textures/vegetation/impostors/<name>.png` (three 128 by 128 unlit renders of
  LOD0 from the front and the side, both 30 degrees above the plant, and from
  above: the game's raw albedo before lighting, the detail texel times the
  display-space vertex colour, with edge colours dilated for the cutout). Each
  card side's normal is the mean normal of the surfaces its render shows, so the
  cards take the light as the plant does. The cards' vertex colour carries how
  the plant takes the sun: red, the share of direct light its own leaves let
  through; green, the share of bark, cactus or snow the card shows. Shrubs and
  orchard trees carry the same level; `prepare_tree_lods.py -- impostors`
  re-bakes it (see Editing and checks).
  The manifest records every level; screen-pixel thresholds live in Java's
  `TreeLod`, so no camera or game state is baked into these assets.
- Every plant's origin is the foot of its trunk, where the board places, grounds and
  clears roads for it; a leaning crown (bent palm, willow) overhangs to one side.
  The maintained GLBs keep that origin and their bark projection. Cactus skin
  wraps around each stem, following bent arms.
- `textures/vegetation/*-cutout`: eight shared 512 by 512 cutout materials
  for broadleaf/conifer and their snow variants, palm fronds, cactus flowers, ferns and shrubs. Near, medium and far crowns
  share these clamped images; impostors are baked from the same alpha-tested
  geometry. The Material Maker projects under `tools/materials/vegetation/` generate them.
  Bark textures are shared.
- `textures/vegetation/cactus-skin`: 512-square albedo and estimated shallow normal
  relief, shared by both cactus variants
  at all three mesh levels. Standard glTF `normalTexture` supplies the normal
  detail; the instanced foliage shader uses the existing dielectric light model
  for waxy skin. The normal-map tuning switch applies to these maps too.
- `textures/vegetation/`: five shared 64 by 64 detail albedos for palm fronds,
  ordinary bark, birch bark, ringed palm bark and snow. Source material boundaries keep snow caps separate
  from green foliage and preserve the birch's pale trunk and dark scars. Existing
  vertex colors tint the pale maps; dominant-axis UVs follow the tree's original
  proportions. Snow variants use their own authored geometry.
- `orchard-*.glb`: six fruit-tree forms and their snow variants, with cutout leaf
  cards. Their authored branch and apple counts stay intact at
  each level; leaf cards use the remaining budget (480/240/84/12 triangles per
  tree). Bark and fruit retain their orchard atlases.
- `textures/vegetation/marsh-sedge_albedo.png`: the editable 1254 by 1254 RGBA sedge/cattail
  cutout for marsh vegetation. The renderer filters it to one shared 512 by 512
  texture with mipmaps; all three plant LODs use this same image. Ground peat,
  moss and pools are shaded separately using the existing sculpt earth maps.
- `textures/structures/facades/`: 128 by 128 runtime facade maps. Light buildings retain
  windows; medium uses concrete, hard reinforced concrete, and heavy armored
  panels. Fortresses/gun emplacements use massive sci-fi walls, hangars use
  large shutter bays, fuel tanks use metal courses, and industry uses service
  panels/vents. Sealed structures and dropships use closed armored panels.
  Source names select the family; opaque roof colors tint each model's walls.
  Ordinary facade courses repeat once per four stories. Hangar doors and
  fortress buttresses span the full height instead of stacking per story.
  Eight light-building windows span 128 world units; other families have fewer,
  larger structural bays at that width.
- `textures/terrain/classic/`: Classic mode's 128 by 128 column wall maps (concrete, dirt, rock,
  sand, snow, lunar, fungus, mars and volcano; each repeats once per 96 world units), the
  `water_bed` map for liquid banks and beds, and the two 84 by 72 incline rim masks
  (`incline_dark`, `high_incline_dark`). The Material Maker projects under
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
- Liquid artwork comes from this directory's own `tileset/saxarba/anim_water_N.gif`,
  `theme_mars/water_anim_mars_N.gif`, `theme_volcano/water_anim_volcano_N.gif`,
  `base/base_magma_anim_N.gif`, and `water/rapids_anim.gif` / `water/torrent_anim.gif`.
  The latter paths are relative to `tileset/saxarba/`. All are independent copies
  of the original 32-frame, 3.2-second animations. The runtime selects these
  images, so they stay even where the static tileset omits them.
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
- Exposed top edges reuse the single south-facing `08` patches under
  `tileset/High_Incline/`, oriented per edge. Edit these to change cliff-top
  detail without affecting 2D. The renderer avoids mixing their baked lighting
  with the brighter north-facing variants and leaves road approaches open.
  `normals/High_Incline/` supplies their matching normal maps. Runtime rotates
  these directions with the edge, combines color and normals with the ground
  before lighting, and caches the resulting paired atlas material. The source
  images remain separate. Riverbanks keep the undecorated ground artwork.

Each building GLB embeds its processed RGB roof texture: the source roof's opaque
pixels at their UV locations, with RGB extended only outside the roof mask to
prevent filtering fringes. Each `buildings/<name>.png` is an exact copy of the
original tile artwork, including transparency and shadows, for inspection beside
`<name>.glb`. Edit the facade Material Maker projects under
`tools/materials/structures/facades/` to change windows/walls.

Models are indexed GLB with positions, flat normals, vertex colors and UVs.
The importer converts glTF Y-up and linear colors back to the board convention.
In the runtime representation Z is up; X/Y use the 84 by 72 pixel hex dimensions.
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
`manifest.json`. `bridge-terminal.glb` is the bank end block. `bridges/bridge-pier.glb` is the hammerhead
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
Ground image normal maps remain a separate surface detail. `normals/` mirrors ground image paths
under `tileset/`, appending `.png` to the complete source name (including its
original extension and any crop). Runtime selects each map through the chosen
albedo image and composites both in the same order, then packs aligned atlases.
No height estimation or normal-map generation runs in the game. Missing maps
for custom art fall back to flat shading.

The maps hold constant normals over alternating 4-pixel triangles, baked from the
albedo's smoothed, alpha-weighted brightness. Painted brightness
is only an approximation to height; baked highlights can also produce relief.
Rubble/rough use the strongest relief, rocky themes are next, and grass, dirt,
sand, snow, mud/swamp, tundra, fields and ice use gentler detail. Pavement and
paved roads have neutral maps, including their opaque coverage over grass.
South-edge cliff-top patches use restrained relief at strength 3. Their alpha
masks control both color and normal coverage; reoriented normal mapping retains
the base relief under the rim. These derived maps retain the same limitation as
other painted sources: authored height/normal maps would give more accurate
relief. Missing custom rim normals preserve the base normal map.
F9 opens Tuning, where the Normal maps checkbox switches this shading live.
It starts enabled, and Defaults re-enables it; switching needs no atlas,
geometry or shadow rebuild.
Animated water keeps its separate rendering. These maps affect ground lighting
and bank slopes, not silhouettes, picking, movement or cast-shadow geometry.

## Materials

Every material under `textures/` is a Godot 4 `StandardMaterial3D`, as Material Maker's Godot 4 Standard export
writes it: `NAME.tres` with its `NAME_albedo.png` and, as it needs them, `NAME_orm.png` (occlusion, roughness,
metallic), `NAME_normal.png` (OpenGL convention), `NAME_heightmap.png`, `NAME_emission.png` and `NAME_sss.png`.
Models name these maps directly. `textures/materials.json` sorts the materials: loose ones repeat across the board
at a fixed texel density, so a wider export covers more ground before repeating; constrained ones fit their
footprint. `tools/materials/README.md` describes the export, and megamek's `docs/gpu-board-materials.md` how the
game reads the files.

## Editing and checks

The GLB, PNG and JSON files here are the source: edit them directly. Run the tools from the mm-data root
(Python requires Pillow; `tools/materials/export.py` requires Material Maker):

```text
python tools/materials/export.py
blender --background --factory-startup --python tools/prepare_tree_lods.py -- impostors [names...]
python tools/validate_board_assets.py
```

`export.py` exports every Material Maker project under `tools/materials/` into `textures/`. After editing a
plant GLB, `prepare_tree_lods.py` re-bakes its LOD3 impostor (every plant's without names); the bake preserves
the three mesh levels, owns a temporary Blender scene and preserves the active scene. The 19 species whose
`-snow` form is a material variant keep their winter impostor (`mmVariants.snow` on the impostor material) as
it is: the bake does not re-render it.

`validate_board_assets.py` checks each manifest entry against its GLB: the plant levels `-lod0` to `-lod3` and
their triangle budgets (480, 240, 96 and 12), the triangle counts (at most 500 per model), one-level building
heights, roof winding and facade assignments, understory and orchard grounding, LOD0 height and every coarser
level's height from 10% below to 1% above it,
embedded images and that every external texture exists inside this directory. It refuses G3DJ meshes.
Native Java integration tests additionally check transparency, lighting,
water animation and representative model loading.

## Provenance

Roof/terrain/water art comes from the existing MegaMek data tileset; its license
headers and original paths are retained. The repository license remains at
`../../../LICENSE`.

Trees are simplified derivatives of Quaternius's **Ultimate Nature
Pack (June 2019)**: `CommonTree_1/2/4`, `CommonTree_Dead_2`, `PineTree_1/2/3`,
`BirchTree_2`, `Willow_2`, their corresponding snow models, `PalmTree_1/2`,
`Cactus_2` and `CactusFlowers_2`. The supplied CC0 notice is preserved
in `QUATERNIUS-LICENSE.txt`.

The crop model and the bridge terminal and pier kits are original work.
Dirt, sandstone, rock, concrete and windowed facade albedos were generated with
the built-in image_gen tool; exact prompts are in
`../../../tools/board-texture-prompts.json`. The seven contextual facade albedos
also used built-in image_gen. Only the 128 by 128 runtime maps are shipped.

## Plant GLB packaging

Each of the 22 plant variants has one GLB, for example `pine.glb`, containing
identity groups `pine-lod0`, `pine-lod1`, `pine-lod2` and the impostor `pine-lod3`. Their authored geometry,
UVs and material roles are preserved. The runtime chooses one level and resolves
missing optional levels toward LOD0 once while loading. Foliage PNGs are
external, under `textures/vegetation`, shared by all variants and levels.
All levels have natural proportions and a base at zero, including when inspected
in an ordinary GLB viewer. Export and LOD preparation never flatten the height.
LOD coverage checks compare the shipped near mesh with its coarser levels.

## Building GLBs and textures

All 3,295 Saxarba buildings use one GLB each, with an identity
`<building>-lod0` group. Each embeds its dedicated roof PNG without changing
the image bytes, and uses a relative URI for one of eight shared facade PNGs.
Roof and wall are separate material groups, not two layers over the same mesh.
Runtime wall materials still scale vertical UVs with building height; `shell`
materials retain full-height UVs. Roof samplers clamp; facade samplers repeat.

`RigidGlb` supports embedded PNG/JPEG diffuse images and local image references.
`ModelTextures` caches images with their sampler state, releases native pixels
after upload, retains encoded bytes for context restoration and gives texture
disposal to the owning asset library. Unit and plant models use the same path.
Only the roof belongs inside each building package; the facade stays shared.
Each building keeps `<building>.png` beside `<building>.glb`: a byte-for-byte
copy of its original tileset image, retaining alpha and shadows. This is for
inspection and is not a runtime texture dependency. The processed roof PNG
stays embedded, with no loose `*-roof.png` under deployed buildings. There is no measured
runtime performance gain claimed from embedding.

`field.glb` also contains a single LOD0 group. Deployed `data/` and
authoring/reference `tools/` meshes are GLB; there are no G3DJ files.

See the glTF image specification:
https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#images
