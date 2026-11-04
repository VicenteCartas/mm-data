# Authored buildings

An authored building is a GLB containing visible geometry and invisible structural volumes. The game assembles it,
slices it by hex and generates its interior floors. There are two supported forms.

## Fixed building

Model the complete exterior at its intended height. Add separate structural solids for wings, towers and terraces
at different heights. Do not use base/floor/roof module names for this form.

Start from [debug_authored.py](debug_authored.py): a small, hollow building covering two hexes, with two- and
four-level sections. [hpg_headquarters.py](hpg_headquarters.py) is a larger fixed example with decorative machinery.
[civic_buildings.py](civic_buildings.py) builds the two-hex church and the oval arena with an open center.

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
- **Tint:** mark only intended walls and panels. The example exporter reads `obj['building_paint'] = True` and writes
  material extras `mmBuildingPaint: true`. Windows, machinery and other fixed finishes use separate, unmarked
  materials. For a mixed atlas, also use `mmPaintMask: true`, with albedo alpha storing paint coverage, not opacity.
- **LOD:** optional roots are `<name>-lod0`, `<name>-lod1`, etc., with identity transforms; an ungrouped model also works.
  Keep module names, placement, material finishes and tint regions consistent between LODs. Export helpers once,
  outside the visible LOD roots. Stay within 65,535 visible vertices per LOD, including duplicated double-sided faces.

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
