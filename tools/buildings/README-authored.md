# Authored buildings

An authored building is a GLB containing visible geometry and invisible structural volumes. The game assembles it,
slices it by hex and generates its interior floors. There are two supported forms.

## Fixed building

Model the complete exterior at its intended height. Add separate structural solids for wings, towers and terraces
at different heights. Do not use base/floor/roof module names for this form.

Start from [debug_authored.py](debug_authored.py): a small, hollow building covering two hexes, with two- and
four-level sections. [hpg_headquarters.py](hpg_headquarters.py) is a larger fixed example with decorative machinery.
[civic_buildings.py](civic_buildings.py) builds the brutalist `civic-church` and `civic-arena`, with an open roof
above a closed playing court. The earlier designs remain separate catalog assets: `classic-church` and `neo-futurist-arena`,
whose pigments, weathering and levels [restored_buildings.py](restored_buildings.py) writes from their GLBs in git.
[civic_citadel.py](civic_citadel.py) builds a 14-level tower with a lower podium and annexes. Its glazed shoulder
bays are decorative exterior geometry; the closed helpers define the occupied floors.
[civic_habitat.py](civic_habitat.py) builds a residential block with a 12-level slab, 80m
service cores, three stepped wings and a low rear annex. Its approximately 3.4m facade storeys are visual detail;
generated gameplay floors remain 18 units high. Its walls use `concrete-panels` with per-vertex grime: an object's
optional `weather` colour attribute darkens its pigment at each vertex, so stains never repeat with the texture.
[civic_blocks.py](civic_blocks.py) builds `civic-habitat2`, `civic-commercial-center`, `civic-offices`, `civic-industrial-works` and
`civic-medical-center` from their sheets, with civic-habitat's helpers. Each is a closed box with its facade laid on it. Where a sheet's
views disagree its ISO view wins. A hex with paving but no volume, like a courtyard, holds no floors.
[utopia_buildings.py](utopia_buildings.py) builds the seven `utopia-*` buildings from their sheets in `references/`, in
`white-stone`. Walls with openings are cut flat and then wrapped on the wall (`wrapped_skin`), plants are cutout cards, and
every level comes from the same code at its own detail. Its sheet shows faces the game culls in magenta.
The game draws a floor at every level inside `building_volume` solids, so they stay behind the glass; a solid one unit
tall at a level's top gives a roof its hexes without adding a floor.

## Building with repeated floors

Create visible modules named `base0`, `floor0` and `roof0`, or names ending in `-base0`, `-floor0` and `-roof0`.
Additional numbered variants are supported; `level0` is an alias for `floor0`.

For N levels, the game chooses one base, N-1 floor modules and one roof. Base and floor modules each represent
18 units of height. All modules share the same XY origin; the game aligns each module's lowest visible point to
its storey's elevation. Keep decorative parts within that alignment convention.

Associate each helper with its module by parenting it beneath that module or naming it, for example,
`building_volume-west-floor0`. Supply closed structural volumes for the base and every floor variant.
The base/floor/roof set enables assembly automatically.

Use the shared `role` field and `export_model()` in [authored_examples.py](authored_examples.py) to assign modules.

## Requirements for both

- **Scale:** Blender Z-up, one Blender unit per model unit. A hex is **83.125 units across corners and 72 across
  flats**; columns advance 62.34375, rows 72, with alternating columns offset by 36. One building level is **18**.
  Ground-relative Z=0 is the building's base; do not bake the map's terrain elevation into the model.
- **Structural helpers:** export a `building_volumes` group containing closed, outward-facing solids. Individual
  helper names begin with `building_volume`. Overlapping solids are unioned; leave courtyards and openings empty.
  Use horizontal, level-aligned structural tops. Helpers must be included in the GLB even though they never render.
- **Exterior:** use hollow walls and omit baked interior floors. Put antennas, dishes and rooftop equipment only
  in the visible geometry unless they form usable building space. Do not model tabletop hex markings.
  Grass clearance follows the visible mesh near the ground, so include real foundations and low overhangs.
- **Gameplay footprint:** at least half a hex must be structurally covered. The roof covering the largest area in
  that hex determines its height; ties choose the taller roof. Interior policy controls access and generated floors.
  Placement supports X/Y/Z rotation. X/Y tilt forces no interior floors; upward structural faces supply per-hex
  roofs in 18-unit height bands. Buried portions do not contribute coverage. Full turns count as upright.
- **Materials:** reuse [existing finishes](../../data/models/board/textures/structures/common). New textures must be
  **512x512 or smaller**. Use Blender MCP for modeling and Material Maker MCP for procedural material work;
  existing material graphs are in [tools/materials](../materials).
- **Brightness:** concrete walls average about 0.30 linear albedo in the exported GLB, texture times pigment and grime,
  in the range of real weathered concrete. The shared concrete finishes are bright enough for that with pigments at 1 or
  below. `CONCRETE_WEATHER` in [authored_examples.py](authored_examples.py) sets how rundown each building is:
  [weathering.py](weathering.py) cuts concrete along a grid of planes on export and darkens the vertices. Fully metallic
  finishes read near black under the board's light, so keep them off large faces.
- **Tint:** mark only intended walls and panels. The example exporter reads `obj['building_paint'] = True` and writes
  material extras `mmBuildingPaint: true`. Windows, machinery and other fixed finishes use separate, unmarked
  materials. For a mixed atlas, its `.tres` sets `metadata/mmPaintMask = true`, with albedo alpha storing paint
  coverage, not opacity. An image embedded in the GLB uses material extras `mmPaintMask: true` instead.
- **Lights:** set `obj['building_emission'] = (r, g, b)` on separate lamp/display surfaces, using display-space RGB
  values in 0..1. Keep them outside tint regions. Shared window emission maps are exported with their material.
  For windows that illuminate after dusk, use `emissive(obj, colour, night=True)` or also set
  `obj['building_night_emission'] = True`. The exporter writes `mmEmission: "night"`; the game fades that
  emission with daylight while preserving the unlit glass colour. Ordinary lights remain independent.
  Shared window materials can instead set `metadata/mmEmission = "night"` in their `.tres`; this also works
  on generated modular kits and mixed atlases whose emission image contains only the windows. A GLB material's
  `mmEmission` (`always`, `night` or `off`) overrides that, and its emissive factor replaces the shared glow's colour
  (linear RGB: warm, cold or anything), tinting its emission map or glowing evenly without one. A night light's colour is
  a uniform, so this needs no new program and no light per pixel: use it freely for lights in numbers.
  The material exporter preserves this metadata.
  For a permanently dark surface, use `emission_off(obj)` (or `obj['building_emission_off'] = True`).
  This exports material extras `mmEmission: "off"` without duplicating textures or erasing the original glow.
  In the GLB editor, **Materials → Emission** changes the same override for the selected surface. Inherit removes it
  and restores the material's normal day/night behaviour.
  To illuminate nearby surfaces, fixed buildings may also export root extras `mmNightLights`: a list of
  `{position: [x,y,z], color: [r,g,b], power: number, size: number}`. Positions use **glTF Y-up** model units;
  colours are linear RGB. These finite point lights fade with daylight and reach zero at twice `size`.
  Use a few emitters at real fixtures; they illuminate terrain and models but do not cast obstacle shadows.
  [civic_night_lighting.py](civic_night_lighting.py) supplies the arenas' fixtures and metadata. Lights follow
  scaling, clipping and hex ownership, and wait for the final installed position during dragging.
- **LOD:** optional roots are `<name>-lod0`, `<name>-lod1`, etc., with identity transforms; an ungrouped model also works.
  Keep module names, placement, material finishes and tint regions consistent between LODs. Export helpers once,
  outside the visible LOD roots. Stay within 65,535 visible vertices per LOD, including duplicated double-sided faces.
  The game picks a level from the object's larger side on screen, counting at most five hexes of it (`TreeLod.prop`): LOD1
  under 80 pixels, LOD2 under 24. So every level of a giant shows at about 16 pixels a hex, with parts it must keep readable.
  `export_model(level=1 or 2)` derives both through [building_lod.py](building_lod.py): each connected piece merges with
  itself on a grid, thin pieces go and leave their colour on what they sat on, sheets keep both faces, windows and lamps stay. Overlapping
  plates and lattices shred that way, so author their far shapes; `hpg_headquarters.py` does for its dish, antenna and generators,
  `civic_buildings.py` for its arena. An authored far shape must enclose the finer levels: the shadow map picks its casters'
  level by its own texel, so a finer part standing above the shape would shade it.
- **Floors:** a volume more than one level tall gets the game's own tan floor at each level, 18 units apart. Keep visible
  decks above a floor that falls inside their volume, or the floor lies over the deck and buries what stands on it.

## Export and register

Use `export_model()` in [authored_examples.py](authored_examples.py) and `write_glb()` in
[glb_geometry.py](../glb_geometry.py) as the export reference. They preserve the helper groups, material metadata,
UVs and colour-space conversion. Export the visible LODs through `levels` and helpers through
`groups={'building_volumes': helpers}`.

Save the GLB under `data/models/buildings/<folder>/<name>.glb`; its asset ID is `buildings/<folder>/<name>`.
Keep editable Blender sources under `tools/buildings/authored/`.
Add a stable ID in [uids.json](../../data/models/board/uids.json) and an entry in
[blueprint.json](../../data/board-editor/blueprint.json) with `kind: "prop"` and `section: "buildings/authored"`
to expose it under **Specials**. Follow the existing authored entries.

Check the exported model in the editor: hex alignment, generated floors at each height, every LOD, selective tint,
rotation and scaling. Also check partial placement beyond the map edge: at least 10% of the structural footprint
must remain inside; the game clips and seals the exterior at the boundary.
