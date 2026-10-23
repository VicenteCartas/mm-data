# Layered walls

24 GLBs across six wall families, used by the 3D board and editor.
Selection uses **pristine map CF** (`BLDG_CF`); combat damage does not change the family.
Editor CF changes select a new family when crossing a bracket. Explicit model overrides retain their appearance.

## Families

| Folder | Pristine CF | Design |
|---|---:|---|
| `civilian/` | 1–10 | Narrow scaffold frame, wire fencing, barbed wire and diamond-plate deck. |
| `light/` | 11–15 | Corrugated steel, light framing and cross braces. |
| `medium/` | 16–40 | Paneled concrete sides, flat concrete roofs, recessed buttresses and a central roof strip. |
| `heavy/` | 41–90 | Concrete and gunmetal armor, with two roof vent strips. |
| `hardened/` | 91–150 | Charcoal gunmetal body, alternating armor panels and deep pillars, with three roof strips. |
| `castle_brian/` | 151+ | Darkest gunmetal tier, with massive buttresses, broad pillar crowns and reinforced roof panels. |

Each folder contains:

- `straight.glb` — a repeating straight section.
- `half-bay.glb` — a short connector between a junction and a hex edge.
- `pier.glb` — a hexagonal junction.
- `terminal.glb` — a hexagonal endpoint.

All families have matching opposing faces and walkable roofs. Piers and terminals have no turret.
The five military families include red emissive fixtures.

## Layers, LODs and materials

Each GLB contains `<filename>-lod0` and `<filename>-lod1` roots, each with mesh children
ending in `-base0`, `-floor0` and `-roof0`. LOD0 is detailed; LOD1 reduces geometry.
Both groups occupy the same position; display one at a time.

Base and floor layers are **18 units high**. A height-N wall uses one base, N−1 repeating
floors and a roof at N×18. Roof rails, parapets and lights extend above that height.
Files store a height-2 assembly: base at 0, floor at 18 and roof at 36 along glTF's Y-up axis.
The runtime grounds each layer independently, preserving its texture scale.

Textures are embedded PNGs using glTF metallic/roughness, normal and emissive materials.
Civilian fence and barbed-wire surfaces use alpha masking at a 0.5 cutoff; other surfaces
are opaque. No external textures or required glTF extensions are needed.

## Dimensions and repetition

- Straight sections are 72 units long; half-bays are 18 units long.
- Military decks are 30 units wide; civilian decks are 21 units wide (70%).
- Military junctions measure 52 units across flats; civilian junctions measure 36.4.
  Civilian connectors therefore use a smaller junction offset.
- Civilian posts repeat every 18 units; joining half-posts form a full post.
  Straight-section width including foot pads is 22.5 units.
- Castle Brian straight sections have 14.4-unit-wide pillars at ±18 along their length.
  Repeating sections maintains a 36-unit pillar pitch across joins. Each half-bay has one centered buttress.
- Floor top and bottom profiles match for vertical repetition. Straight-section end profiles
  join without transverse roof caps.

## Geometry budgets

Triangle counts per height-2 component (base + one floor + roof), **LOD0 / LOD1**:

| Family | Half-bay | Pier | Straight | Terminal |
|---|---:|---:|---:|---:|
| Civilian | 1,068 / 492 | 2,852 / 1,244 | 2,796 / 852 | 2,872 / 1,264 |
| Light | 1,072 / 324 | 2,572 / 748 | 2,288 / 588 | 2,620 / 748 |
| Medium | 180 / 120 | 2,588 / 984 | 1,476 / 624 | 2,564 / 984 |
| Heavy | 496 / 228 | 2,160 / 984 | 1,624 / 588 | 2,208 / 984 |
| Hardened | 828 / 480 | 3,456 / 2,040 | 2,556 / 1,200 | 3,504 / 2,040 |
| Castle Brian | 1,004 / 544 | 2,848 / 1,864 | 2,152 / 968 | 2,860 / 1,876 |
