# Modular building kits

Store a modelled kit as `<family>/<name>.glb`, for example `fuel_tanks/fuel_tank_light.glb`, and a generated kit as
`<family>/<name>.json` beside its pieces, `<name>-pieces.glb`, for example `fortress_light/fortress_light_a.json`.
Do not nest this catalog under the source tileset's `saxarba` directory. Generic buildings select the kit by
gameplay weight and class, including when imported from a legacy `.board`. Old roof artwork is no longer a
3D design. Fuel-tank tileset keys such as `fuel_tank_light_NN` still resolve the shared
`fuel_tanks/fuel_tank_light.glb`; the kit follows the hex's connections.

Each file contains one building: an identity `<name>-lod0` group and, normally, optional `<name>-lod1`.
Author no more than two levels for this work; simple kits (especially under 200 triangles) can use just `lod0`.
This is an asset budget: if an existing kit supplies `<name>-lod2`, the loader uses that additional level.
Each group contains mesh nodes ending in `-base#`, `-floor#`, and `-roof#`, with at least one variant of each.
Number variants from 0; sparse numbers are also supported. Roles must match across LODs.
For N levels, the runtime chooses one base, N-1 independently chosen floors (including `floor0`), and one roof.
Choices are stable for each placement; changing height preserves the base, roof, and existing lower floors.

Base and floor meshes are exactly 18 units high in authoring Z-up space. Enterable buildings have hollow walls.
Author all modules and LODs relative to the same XY origin, with LODs superimposed rather than offset sideways.
The loader preserves authored XY coordinates and derives only each module's vertical base from geometry when
assembling one base, N-1 floors and a roof. Modules may be stacked vertically for display; their saved Z placement
is discarded. Asymmetric details do not change a module's horizontal placement. For enterable buildings,
the full roof projection intersected with the selected modules' closed mid-storey wall sections defines generated
interior floors and struts (a storey whose walls close nothing, a hex open towards connected neighbours, keeps the
roof projection). Keep notches and courtyards in those surfaces.

## Editor palette and legacy import

**Buildings**, **Fortresses**, **Hangars** and **Gun Emplacements** each expose Light, Medium, Heavy and
Hardened directly. **Walls** has Civilian, Light, Medium, Heavy, Hardened and Castle Brian. **Looks** holds
Lunar habitat, Glass dome and Biodome; **Specials** holds authored buildings; **Utilities** holds elevators.
All sixteen building class/weight combinations have kits, including the diagnostic placeholders described below.

Legacy `.board` import preserves a building's weight, class, height and construction factor while discarding
its old roof-art choice. Lunar buildings use the current lunar looks; the old Mars/volcano sealed look becomes
Glass dome. The seven retired DropShip selectors (`building:4:69` through `building:4:75`) are omitted entirely,
including their building rule state. Ground elevation, pavement and other terrain remain.
The removed legacy GLBs and artwork galleries are not required by this conversion.

## Connected kits

Generic buildings select a modular kit by gameplay weight and class even with no connections; single-hex artwork is
an explicit look. An isolated building can pivot about Z in the editor. Any incoming or outgoing building connection
disables the pivot. A core-only authored GLB (base/floor/roof nodes without side tags) switches to the generic modular
kit for that building's weight/class when connected. The editor keeps this change in the connection's undo step.
The authored example `debug/debug-authored.glb` appears under **Specials** and follows this same contract.

Building appearance stores a tint in colour slot 0, using the editor's existing colour picker. White restores the
original artwork; another colour multiplies its surfaces in linear light. This is a whole-building tint, including
roofs, and does not require recolour masks in existing kits. Connected hexes share the chosen tint. `.board2` version
3 stores rotation, tint, footprint and kit variant under `components.building.appearance`.

`tools/buildings/debug_placeholders.py` supplies flat diagnostic kits for the missing medium/heavy/hardened buildings
and fortresses, all hangars, and all gun emplacements. They use the light building's `bays` JSON layout and inexpensive
box panels: bay indices 0–5 are red, orange, yellow, green, cyan and violet; alternate base/floor modules are lighter.
Roofs are yellow and floor/sidewalk slabs grey. These are placeholders, not weight-specific finished artwork. Each
family has its own JSON and pieces GLB so artists can replace it independently. The script preserves existing asset
UIDs, and registers new kit IDs once. It leaves the original light building, light fortress and lunar habitat intact.

Buildings and fuel tanks connect across the hexsides their exits name. A neighbour of the same structure (building or
fuel tank) that connects back and stands lower ends the connection at its top. A kit that changes shape with its
connections tags its mesh nodes after the module:
`<name>-lod0-<module>[-<tag>[-<tag>]]`, each tag `link-<dir>` or `end-<dir>`, `dir` one of `n`, `ne`, `se`, `s`,
`sw`, `nw` (clockwise from north), for example `pier-lod0-floor0-link-n`.

- A node without tags is the core and always draws. `link-<dir>` draws where the hex connects towards `dir`,
  `end-<dir>` where it does not; both tags of a two-tag node must hold. A module may have tagged nodes only.
- A whole-hex node tags all six directions: it stands alone, in place of its module's other pieces, for exactly those
  connections, on the levels that keep the ground level's connections (above, the corner pieces follow the falling
  connections). Every module carries the kit's whole-hex nodes; a symmetric kit authors each once, turned for the rest.
- A linkless corner roof node (two `end-` tags) may have a `-bend` twin, for example
  `kit-lod0-roof0-end-s-end-sw-bend`: it stands in for the plain one where the hex connects across just the two
  hexsides opposite it (behind a 60-degree bend), so a roof's plating can mitre along the bend's two arms.
- Each piece stacks through the levels where its tags hold: a base on the ground (a floor where it starts higher),
  then its own roof where it stops, below the top or on it.
- A symmetric kit tags `n` only (one-tag pieces) or `n` and `ne` (corner pieces, in all four link/end states);
  the runtime turns them by exact 60-degree steps for the other directions. Any other kit tags all six directions
  for every piece.
- A material whose glTF extras hold `mmBoardUV` (units a repeat) is textured from the board position, along the
  board's axes, whatever its UVs: a turned or neighbouring piece's floors and roofs run on without a seam.
- Every variant of a module type (base, floor, roof) and every LOD has the same tagged pieces. A type may have none:
  a fuel tank's ground pipes stand in its base only. Base and floor modules, tagged pieces included, are exactly
  18 units high; a module stands on its lowest point over all its pieces.
- The board's hex is regular: 72 across its flats, 83.125 across its corners (the regular 83.138 to a 32nd), every
  edge midpoint 36 from the centre within 0.005 (Blender: X east, Y north, Z up, one unit per board unit). Every kit
  is drawn as authored on it. A one-tag `link` piece ends on its edge line, within one unit.
- Names are checked when the kit loads: Blender's `.001` suffixes and unknown tags are errors.

Walls (`walls/README.md`), fuel tanks (`fuel_tanks/`), the lunar habitat (`lunar_habitat/`), the light building
(`building_light/`) and the light fortress (`fortress_light/`) are connected kits.

A building kit comes in two footprints, chosen per connected building in the board editor's Footprint row and stored
as the hex appearance `footprint` (`HexAppearance.Footprint`):

- **Angled**, the default and the classic exits art's: a linked hexside opens from corner to corner; an unlinked one
  closes with two walls meeting two thirds of the way to its midpoint, where the neighbouring arms' walls cross. Every
  wall of a corner piece runs 24 from an axis point to an axis point or a hex corner. A lone hex and a hex with one
  link are whole-hex pieces: the kit's lone block, and a band a hexside wide running through.
- **Square** (generated kits): right-angled blocks. A hex's core, the rectangle between its north and south hexsides
  as wide as a hexside, always stands; the cell beside each slanted hexside fills where the hex connects that way, so
  connected neighbours' cells meet in one rectangle.

A generated kit (`GeneratedKit`) builds both footprints from its JSON spec: an array of named variants, the first the
default (one without variants lists one, `default`); each variant's `style` dresses the footprint's walls, `habitat` or
`bays`. The walls are split where they cross a corner piece's cut, each end a cut, joint, corner (mitred), round or
open end; bands along a wall (sidewalk, skirt, parapet, eave) are mitred where it turns.

A pieces GLB holds the modelled pieces, edited in Blender: each level of detail a root `<name>-pieces-lod<n>` holding
nodes `<piece>-lod<n>`; a node's position only lays the pieces out side by side, its rotation and scale apply. Board
units, Z up in the board's terms (glTF Y up), materials named as board materials, vertex colours linear shades. A
piece's x runs along its wall, left to right seen from outside, from the piece's start; its facade faces -y (Blender's
front view), the wall line at y 0; z up from its storey's floor.

- `building_light/building_light.json` (`bays`): the light building, its pieces the hand-made art's window bays
  (`tools/buildings/art/building_light_00.glb`), six per module (`base0`, `base1`, `floor0`, `floor1`, `roof0`, the
  roof's carrying the cornice), one pier to pier per 24 of wall; a sidewalk along the ground storey.
- `fortress_light/fortress_light_a.json` (`bays`): the light fortress, its storeys' stretches the art's wall rebuilt
  low-poly to its measurements (`tools/buildings/art/fortress_light_a_52.glb`: panel face, joints, band, window recess
  and frame, door, base course) in the dark wall concrete (`structures/buildings/fortress-wall`, the art's far facade's
  tone), plain masonry at each wall's ends, the art's merlons along the roof in the light concrete; far away one panel
  face per wall with its windows, and a plain parapet.

A `bays` variant: its `pieces`; the Angled `lone` outline (counter-clockwise from its front) and `bandEnd`; the `roof`
and `floors` slabs (a board material on the board's axes, its `repeat`, an `inset` off the walls, `heights` per level
of detail); the ground storey's `sidewalk` (`width`, `kerb`; none without); and its `modules` by role, one run per level
of detail (the last for any further). A run lays whole `bay`s of its `bays` pieces (several: chosen by the wall's place)
stretched to fit between a `margin` at each end, a ground storey's `door` piece in a hub face's first bay and next to
the middle of a whole hex's front; with no margin a bay more goes on past an end where the wall goes on. Whole `ends`
stretches (`piece`, `length`) fill the margins, one `under` stretch lies along the whole wall, and `planar` materials
are textured along the wall's line (units a repeat). Bay kits are turned: their Angled corner pieces are built once and
turned by the runtime.
- `lunar_habitat/lunar_habitat.json`: the lunar habitat, a kit the game generates from this spec (`HabitatKit`, both
  footprints): facades, steel piers at corners and joints, a battered steel skirt, the roof's edge rounded down into
  the walls (variant `rounded`) or a parapet (`parapet`); convex corners rounded. The spec is an array of named
  variants, the first the default: the editor's Variant row (shown where a kit has more than one) gives a connected
  building one, stored in its hexes' appearance (`kitVariant`); a name the spec no longer lists draws the first. Each
  variant's look is data: its `name`, `style` (`habitat`), board materials by role, `pieces` (the GLB of its modelled pieces, below),
  `cornerRadius` and `cornerSegments` (plan rounding), `parapet` (`height`, `width`, or `null`), `eave` (the roof's
  rounded edge: `radius` and `segments` per level of detail; with a parapet it rounds the parapet's outer top edge,
  without one a rim curves from the wall onto the roof; `null` square), `skirt`, the pieces at walls' joints and convex
  corners (`piers`, their roof `tops`, `footings`: a `joint` and a `corner` piece name each, or `null` for none), the
  Angled `lone` hex and single link band, the `storeys` above the ground (`windows` lit or dim, `shift` along) and the
  roofs' `fittings` per footprint (a `hatch` and a `vent` piece, and the `layouts` placing them). Its pieces stand in
  all six corners (not turned) because its roof fittings stand in the hex's middle; an Angled piece lays its plating
  along its building, mitred where arms meet (its linkless roof corners have `-bend` twins). The game reads a kit's
  JSON where no GLB of its name exists; the asset's `-square` names the Square footprint.
- `lunar_habitat/lunar_habitat-pieces.glb`: the habitat's pieces. A pier stands on its storey's floor at the wall line
  and is stretched to the storey (18 high); a pier top likewise on the roof, stretched to the parapet (or eave) and .6
  over it; a footing likewise on the ground, as modelled; a hatch or vent on the roof surface at its centre, as
  modelled.

Isolated generated kits use a compact square for Square and an inset hex for Angled, with facade details and curbs
contained inside the hex. Optional editor padding shrinks isolated buildings horizontally; connected pieces retain
their full joining reach. Bay and habitat kits share solid inward wall backing, closed exposed wall ends and roof
slabs. Bay specs may supply `wallInsets` per LOD when their facade skins sit behind the nominal wall line (default 0). Generated interior floors are solid slabs below their gameplay standing height, including authored multi-hex
buildings. No-floors and sealed buildings omit intermediate floor surfaces from drawing and picking.

Every surface is a board material (`structures/buildings/`, `structures/lunar/`, Material Maker projects in
`tools/materials/structures/`): the hand-made art's atlases as image projects, the roofs, floors and sidewalks
tileable on the board's axes (`mmBoardUV`). The fuel tanks are generated:
`python tools/buildings/fuel_tanks.py [weight ...]`, after the designer's kits (sizes, paint, roof rings). Each kit is
authored stacked as built (floor at 18, roof at 36) with no coincident surfaces between its pieces. At full detail
the base carries a nozzle in all six directions; a `link-n` pipe runs from the north one to the edge, and an `end-n`
blind flange closes it where no pipe leaves. Painted pieces take the board's `weathered-paint`, the hard tank's
vents `vent-slots`, both tinted by vertex colour, and steel `rusted-steel`, by image URI; vertex colours also carry
contact shading and grime. Three levels of detail follow the props' rule (above 80 pixels on screen, down to 24,
below).

## Multi-hex buildings

The `buildings/multihex/dome` and `biodome` looks are generated over a whole building (`BoardMultiHexBuilding`), with
no model per hex: a dome is fitted into its footprint and cut along the hexsides, and a domed building's hexes outside
its podiums stand as rectangular blocks at their own heights, joined to the podium by wings. The lunar habitat look is
the connected kit generated from `lunar_habitat/lunar_habitat.json` (above). Their surfaces are board materials in `structures/lunar/` (Material Maker
projects in `tools/materials/structures/lunar/`); the dome glass is transparent by its `.tres`.

`multihex/lunar-equipment.glb` holds their support pieces, one node per piece and level (`<piece>-lod0`, `<piece>-lod1`),
each standing on its origin, its front towards +Y: `tanks`, `plant`, `airlock` (its back on y = 0, against a facade)
and `pylon` (a dome podium's corner block). It is modelled in Blender:
`blender -b --factory-startup --python tools/buildings/lunar_equipment.py`. The same script writes board objects, one
file each: roof props in `board/scenery/roofs/` (`radar-dish`, `capsule-tanks`, `generator-ring`, `radar-station`,
`light-well`, `light-strip`, `solar-array`, `dish-antenna`, `sawtooth-skylight`), the editor's Buildings > Rooftop
section, and colony details in `board/scenery/colony/` (`pipe-run`, `vent-unit`, `wall-tanks`, `ladder-cage`,
`light-mast`, `airlock`, `radiator`, `vehicle-gate`; wall-mounted ones with their back on y = 0), the editor's
Buildings > Colony section. The 32x17 Lunar Base stands them
against its habitats' walls and on their roofs to break the blocks' outlines.

The four heavy-industrial terrain uses `BoardIndustrial` procedural generator. It assembles
different equipment families with independently chosen heights, distinct domed/conical/flat caps, and pipes
connected to actual neighboring industrial hexes. Industrial height is cover: there are no generated interior
floors, building cutaways, or elevated pointer selections. Ordinary buildings still use the modular contract above.

The active industrial materials are `models/board/textures/structures/industrial/paint.tres` and `steel.tres`
(Godot 4 Standard materials; a wider export widens their repeat). The shared `fan` material is an opaque 128x128
texture on a static quad, with mipmaps and no animation.
`tools/buildings/heavy-industrial/` preserves the first prototypes but are superseded by the runtime generator.
