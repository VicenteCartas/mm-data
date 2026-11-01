# Board materials

Every material of the 3D board is a Material Maker project here, exported as a Godot 4
`StandardMaterial3D`: the stock **Godot/Godot 4 Standard** export, with no custom target.
The three materials with a map a standard material has no slot for (lava, crust and ice)
are Godot `ShaderMaterial`s instead, made from that same export ([below](#shadermaterials)).

| Project | Exports to |
| --- | --- |
| `<folder>/<name>/<name>.ptex` | `data/models/board/textures/<folder>/<name>.tres` and its maps |

For example, `terrain/surfaces/grassland-ground/grassland-ground.ptex` exports
`data/models/board/textures/terrain/surfaces/grassland-ground.tres`. A project's own images are in
its `sources/` folder.

Terrain surfaces are named `<surface>-<role>`: the ground type, then what the material does there:
`ground` (the hex surface), `debris` (loose stones at cliff feet, rims and slopes), `cliff` (walls and
bedrock), `bank` (soil on banks), `cap` (mesa cap plates) or `floor` (what gathers in sunken ground,
in place of the ground from level -1 down: every natural family but sand has one; sand and concrete keep their ground).
`temperate-*` is shared by grassland, dirt, rock, concrete, snow and tropical ground, `arid-*` by sand
and desert; `biome-*` serve fields, marsh and mud, and a few name their one use (`sand-verge`,
`concrete-mulch`, `ground-scorch`, `scatter-stone`). A surface made from a photographic study reads
its `sources/` from `terrain_sources.py` (its header gives the recipe) and clones a sibling project;
`snow-floor` reads a smoothed copy of `snow-ground`'s sources.

## The material

Each project ends in the stock **Material** node, and its Size is the export size. Connect
only what the material has; the export writes a map for each connected input:

| Material input | Map | Content |
| --- | --- | --- |
| Albedo (with Opacity when the material is a cutout) | `<name>_albedo.png` | sRGB colour; alpha is opacity. |
| Ambient occlusion, Roughness, Metallic | `<name>_orm.png` | R occlusion, G roughness, B metallic. |
| Normal | `<name>_normal.png` | Tangent normal, OpenGL convention (+Y up). |
| Depth | `<name>_heightmap.png` | Height, white highest (the node writes 1 − depth). |
| Emission | `<name>_emission.png` | sRGB glow colour. |
| SSS | `<name>_sss.png` | Subsurface scattering strength. |

The Material node's parameters become the resource's factors (roughness, metallic,
normal strength, emission energy, depth scale, SSS strength).

**Every input works on every material**, with Godot's meaning, wherever the game draws it:
terrain, grass, roads, buildings, props, trees, shrubs and fungus alike. Connect Emission to
make grass glow, raise Metallic to make sand metallic, connect SSS to make a rock or a shrub
let light through: export, then Reload assets. Nothing in the game decides a material's
finish for it:

- **Roughness** and **Metallic** are the ORM map's G and B channels times their factors.
- **Emission** glows at (map + Godot's emission colour) times its energy, in linear light, and
  is not lit by the sun. The game keeps it at every distance.
- **SSS** is how much light a material lets through: thick bodies (ground, rock, shrubs) soften
  their shading past the terminator by that share, leaves pass it through to their far side.
- **Depth** is height, for the terrain's height blending and for Godot's parallax: Depth scale
  is its depth in UV times 100 (on a terrain surface, its project's *Relief*, a percentage of the
  repeat; 0 for none). Buildings, props and roads take Godot's deep parallax settings; the sculpted terrain,
  which blends several materials in a pixel, takes one step. In the GPU tuning panel, Normal maps
  turns buildings', props' and roads' parallax off with the normal maps, and Terrain Parallax
  turns the terrain's off on its own.
- Ground damage, scorch and mud bury a material: they show none of its metal, glow or
  scattering.

The exceptions: lava, crust and ice draw with their own shaders ([below](#shadermaterials));
GLB materials without a board texture are their GLB's own glTF material. A Godot-literate artist can open the
`.tres` and its maps in Godot directly: open `data/models/board/textures` as the Godot
project, so its `res://` paths match the game's. Godot's own files there (`project.godot`,
`.godot/`, `.import`) are git-ignored.

### ShaderMaterials

Three materials need one map that a standard material has no slot for, and colour data a
standard material would misread (linear lava emission, grey crust heat, an ice tint). Godot
adds maps to a material with a shader, so each of these is a `ShaderMaterial` of the
`<name>.gdshader` beside it in `data/models/board/textures`:

| Project | Export node | Map | Shader parameter |
| --- | --- | --- | --- |
| `terrain/lava/lava-flow` | `ExportMask` | `lava-flow_coverage.png`: exposed-melt coverage | `texture_coverage` |
| `terrain/lava/lava-crust` | `ExportMask` | `lava-crust_glow.png`: crack glow | `texture_glow` |
| `terrain/ice/ice-sheet` | `ExportCracks` | `ice-sheet_cracks.png`: cracks and bubbles | `texture_cracks` |

A stock **Export** node writes the extra map beside the others. Each of these projects'
Material node carries its own export target, *Godot > Godot 4 ShaderMaterial*: the stock
Godot 4 Standard maps, and a `<name>.tres` written as the `ShaderMaterial` of `<name>.gdshader`,
with the parameter names of Godot's own converted shaders (`texture_albedo`, `texture_orm`,
`roughness`, `emission_energy`, ...) and `texture_<map>` for the Export node's `<name>_<map>.png`.
`export.py` uses that target. Exporting these with *Godot 4 Standard* instead leaves a
`StandardMaterial3D` the game refuses. A `<name>.gdshader` beside a material is what makes it a
`ShaderMaterial`; adding a map to another material means a shader for it, its own target in the
project, and code in the game that reads the map.

The shaders are previews for Godot only: the game reads their parameters, and renders these
materials with its own shaders. Their declared defaults count, as in Godot: a parameter a
resource omits takes them.

Most projects quantize each map with a `…PNG8` group before the Material node, so the
exported bytes are exact codes. The nodes after those groups only undo what the Material
node applies on export: the normal's conversion, and the heightmap's 1 − depth.

### Sculpted terrain roughness

The game renders every material with the roughness it exports, as Godot would: the ORM
map's G channel times the Material node's Roughness factor. Roughness 1 is fully rough;
the game estimates none of its own.

Most sculpted terrain projects (`terrain/surfaces`) make their roughness in the
`SurfaceResponse` group: *Base roughness* plus up to ±*Roughness variation*/2 from the
grain, smoother on raised grain. `concrete-mulch` uses a uniform 0.92 factor; mud and
scorch build their own roughness.

## Loose and constrained materials

`data/models/board/textures/materials.json` sorts every material:

- **Loose** materials repeat across the board: terrain surfaces, roads, lava, ice and
  industrial plating.
- **Constrained** materials fit a footprint: facades, turret plating, classic tiles, scars,
  scenery and plant cutouts. Their texture size never changes what they cover.

`structures/common/` holds the materials several models share: `steel` (turrets, the Solaris
elevator's lift, container fittings, the cargo crate's metal), `iron` (cast parts: the lift's hubs
and clevises, the cargo crate's corner castings), `corrugated` (bare satin corrugated steel for unpainted light walls,
metallic across the sheet), `corrugated-painted` (opaque dielectric satin paint for seaport containers, with subtle
weathering and no repeated chip pattern; fittings use separate steel),
`container-details` (all yard LODs and individual container LOD1/LOD2, baked from the shared geometry and exported materials
by `tools/board-models/seaport/build_container_lods.py`; its alpha separates paint tint from metal fittings),
`chrome` (hydraulic rods and axles), `hazard-stripes`,
`safety-yellow` (heavy machinery's paint, lightly chipped: models add wear where it gathers), `diamond-plate`
(steel diamond plate: the Solaris elevator's platform and pit), `worn-diamond-plate` (the wall decks) and
`aluminium-plate` (no model uses it at present). The fuel tanks take `weathered-paint` (glossy off-white enamel
with dried stains, rain-streaked dirt, rust specks and blotches, chips and rust drips) and `rusted-steel` (weathered
steel with rust patches); both read their maps from `sources/`, which `photo_sources.py` makes from a photographic
study (its header gives the recipe). The hard tank's vents take `vent-slots` (pressed louvre slots, two across and
eight down per repeat). The layered walls
also take `satin-steel`, `matte-steel`, `painted-steel`, `grille`, `cast-concrete`, `concrete-panels`,
`chain-link` and `barbed-wire`; their projects without a Material Maker graph of their own read
their maps from `sources/`. The cargo crate's maps are baked from steel, iron and the hazard stripes. The corrugated
finish, the three wall steels, the grille, the worn plate, the weathered paint and the vent slots are near white or
flat: each model tints them with its vertex colours or colour slots.

The plant cutouts made from photographic studies (`creosote-cutout`, `sagebrush-cutout`, `twig-cutout`,
`date-palm-frond-cutout`, `willow-cutout`, `cactus-flower-cutout`, `orchard-cutout`, `volcano/cinder-cutout`) and the
dead tree's `dead-wood` read their `sources/` from `plant_sources.py` (its header gives the recipe): `cutout` keys a
study shot on magenta, `bark` tiles one that fills the frame.

Keep corrugated weathering broad and its finish variation small: fine, high-contrast metallic and roughness streaks
turn into bright trails under grazing light. Its graph limits weathering's metallic blend to 0.10 and roughness blend
to 0.15, with three noise octaves across 12 by 2 features per repeat; the ten straight ribs remain in normal and height.
The painted variant has metallic zero throughout. Do not add randomly tiled bright chips: convincing wear belongs
on the model's corners, seams and handling points and needs geometry-aware placement.

A loose entry has up to two values:

| Value | What it is | What changing it does |
| --- | --- | --- |
| `pixels` | The texture width the entry describes: with `metres`, the texel density (`metres` ÷ `pixels` per texel). | Changes no pattern size by itself. A texture exported wider than `pixels` covers proportionally more ground before it repeats, at the same density (2048 pixels catalogued at 1024 cover twice `metres`); narrower, less. |
| `metres` | The ground one repeat covers at `pixels` wide. Terrain surfaces and roads; lava, ice and industrial plating repeat as the game sets, and give `pixels` alone. | Stretches or shrinks the material on the ground: its stones, cracks and grain grow or shrink with its repeat. |

A texture so covers `metres` × (its width ÷ `pixels`) before it repeats. Roads are 1024 pixels
over 12 m (11.7 mm a texel), grass 512 pixels over 12 m (23.4 mm).

To edit them safely:

- **Sharper or softer, same pattern:** export the same project at another size and set `pixels`
  to the new width; `metres` stays.
- **Longer before it repeats, features the same size:** the texture needs more content. Export
  wider from a project whose pattern holds N times the features and leave the catalogue as it is:
  the wider texture covers more ground. A terrain surface's project measures per repeat, so divide
  its *Relief* by N and multiply its two cavity strengths by N. For a road, `road_maps.py
  --lengthen N` (below) makes that content at the same width; then multiply `metres` by N.
- **Bigger or smaller features:** change `metres`. No project knows metres: its *Relief* is the
  heightmap's height range as a percentage of the repeat (Godot's `heightmap_scale`; the Material
  node's Depth scale is *Relief* ÷ 25), and its crack shading strengths are per repeat, so its
  maps fit any size. Road, lava and crust normals round their *Relief* to a whole code of the 8-bit
  heightmap (*Relief* × 25.5, rounded, in their `ReliefCodes` or `Relief_code` node), so their
  *Relief* stays a multiple of 10 ÷ 255 and the parallax depth is the relief the normals have
  (asphalt: code 4, 0.157 %, 1.88 cm at 12 m; dirt 11, 0.431 %, 5.18 cm; gravel 18, 0.706 %,
  8.47 cm; lava 13, 0.510 %; crust 202, 7.92 %).
- Maps stay square, and must tile (below).

*Reload assets* in the game's Tuning panel re-reads the catalogue with the maps and shows a
change at once. Catalogue every new material: a loose one needs its entry to load, and megamek's
`GpuBoardMaterialsTest` requires every material to be listed, and `metres` for every terrain
surface and road.

A loose material repeats edge to edge, so every one of its maps must tile without a seam: what
leaves the right edge comes back on the left, and the bottom meets the top. The road projects
build their maps from images in `sources/` (pigment, and the two byte planes of their 16-bit
height fields); those images tile seamlessly, and an edit to them must keep them so, or every
road shows its tile grid. A road's 12 m repeat also keeps its stones and patches from lining up
into a lattice along the road, which they did at 6 m.
`tools/materials/roads/road_maps.py` writes the road maps from their sources as the export does,
without Material Maker, and reports how much each map changes across its tile edge;
`--make-seamless` first makes sources that show their grid tile (`tools/materials/seamless.py`),
and `--lengthen N` quilts the sources into a tile covering N times their ground at the same size,
from pieces of themselves (`tools/materials/quilt.py`; the material must have no direction of its
own, such as baked light, as pieces are turned and mirrored). The road sources' 12 m came from
6 m ones with `--lengthen 2`. Set the project first, as `road_maps.py` writes the maps from it in
the same run: *Relief* divided by N, as a whole code, and *depth_scale* = *Relief* ÷ 25; then
multiply the catalogue's `metres` by N. Running it again lengthens again; to rewrite
only the maps, run it without `--lengthen`. Both scripts need numpy and scipy.

## Exporting

From the editor: *File > Export material > Godot > Godot 4 Standard* into the folder in
the table above; for lava, crust and ice, *Godot > Godot 4 ShaderMaterial* (below). In the game,
*Reload assets* in the Tuning panel picks up the new export.

From the command line, run from the mm-data root (requires Material Maker 1.8-mm.2 or later, and
Pillow):

```text
python tools/materials/export.py
python tools/materials/export.py terrain/surfaces/grassland-ground/grassland-ground.ptex
```

The script exports every project, or the one given. Material Maker's command line writes each map
at its node's Size, the same pixels as the editor. The script writes a map only when its pixels
change, in the PNG mode of the file it replaces, and the `.tres` only when a value changes, so
exporting an unchanged project changes no file; it prints which files changed. It removes the
project's maps it no longer writes, an Export node's included. For a loose material it prints the
ground one repeat covers.

megamek's `docs/gpu-board-materials.md` describes how the game reads these files.
