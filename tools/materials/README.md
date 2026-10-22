# Board materials

Every material of the 3D board is a Material Maker project here, exported as a Godot 4
`StandardMaterial3D`: the stock **Godot/Godot 4 Standard** export, with no custom target.
The three materials with a map a standard material has no slot for (lava, crust and ice)
are Godot `ShaderMaterial`s instead, made from that same export ([below](#shadermaterials)).

| Project | Exports to |
| --- | --- |
| `<folder>/<name>/<name>.ptex` | `data/models/board/textures/<folder>/<name>.tres` and its maps |

For example, `terrain/surfaces/grass/grass.ptex` exports
`data/models/board/textures/terrain/surfaces/grass.tres`. A project's own images are in
its `sources/` folder.

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
  is its depth in UV times 100 (on a terrain surface, 100 × relief metres ÷ repeat metres; 0
  for none). Buildings, props and roads take Godot's deep parallax settings; the sculpted terrain,
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
| `terrain/lava/lava` | `ExportMask` | `lava_coverage.png`: exposed-melt coverage | `texture_coverage` |
| `terrain/lava/crust` | `ExportMask` | `crust_glow.png`: crack glow | `texture_glow` |
| `terrain/ice/sheet` | `ExportCracks` | `sheet_cracks.png`: cracks and bubbles | `texture_cracks` |

A stock **Export** node writes the extra map beside the others. Material Maker cannot write a
`ShaderMaterial`, so `export.py` makes it from Material Maker's `StandardMaterial3D`: the
standard maps and factors take the parameter names of Godot's own converted shaders
(`texture_albedo`, `texture_orm`, `roughness`, `emission_energy`, ...), and every other
`uniform sampler2D texture_<map>` the shader declares is the Export node's `<name>_<map>.png`.
A `<name>.gdshader` beside a material is what makes it a `ShaderMaterial`; adding a map to
another material means a shader for it, and code in the game that reads the map.

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
grain, smoother on raised grain. `tree-pit-mulch` uses a uniform 0.92 factor; mud and
scorch build their own roughness.

## Loose and constrained materials

`data/models/board/textures/materials.json` sorts every material:

- **Loose** materials repeat across the board: terrain surfaces, roads, lava, ice and
  industrial plating.
- **Constrained** materials fit a footprint: facades, classic tiles, scars, scenery and
  plant cutouts. Their texture size never changes what they cover.

A loose entry has up to two values:

| Value | What it is | What changing it does |
| --- | --- | --- |
| `pixels` | The texture width the entry describes: with `metres`, the texel density (`metres` ÷ `pixels` per texel). | Changes no pattern size by itself. A texture exported wider than `pixels` covers proportionally more ground before it repeats, at the same density (2048 pixels catalogued at 1024 cover twice `metres`); narrower, less. |
| `metres` | The ground one repeat covers at `pixels` wide. Terrain surfaces and roads; lava, ice and industrial plating repeat as the game sets, and give `pixels` alone. | Stretches or shrinks the material on the ground: its stones, cracks and grain grow or shrink with its repeat. |

A texture so covers `metres` × (its width ÷ `pixels`) before it repeats. Roads are 1024 pixels
over 12 m (11.7 mm a texel), grass 512 pixels over 4 m (7.8 mm).

To edit them safely:

- **Sharper or softer, same pattern:** export the same project at another size and set `pixels`
  to the new width; `metres` stays.
- **Longer before it repeats, features the same size:** the texture needs more content. Export
  wider from a project whose pattern is enlarged to match (more features, *RepeatMetres* times
  the same factor) and leave the catalogue as it is: the wider texture covers more ground. For a
  road, `road_maps.py --lengthen N` (below) makes that content at the same width; then multiply
  `metres` by N.
- **Bigger or smaller features:** change `metres`, and keep the project in step with it. A
  project's *RepeatMetres* is the ground its exported tile covers, `metres` × (its width ÷
  `pixels`), and must match it, or its normals come out too steep or too flat; *ReliefMetres* is
  the height range of its heightmap in metres. A road project's Material node takes
  *depth_scale* = 4 × *ReliefMetres* ÷ *RepeatMetres*, so the parallax depth is that relief too.
- Maps stay square, and must tile (below).

*Reload assets* in the game's Tuning panel re-reads the catalogue with the maps and shows a
change at once. Catalogue every new material: a loose one needs its entry to load, and megamek's
`GpuBoardMaterialsTest` requires every material to be listed, and `metres` for every terrain
surface and road.

A loose material repeats edge to edge, so every one of its maps must tile without a seam: what
leaves the right edge comes back on the left, and the bottom meets the top. The road projects
build their maps from images in `sources/` (pigment, and the two byte planes of their 16-bit
height fields); those images tile seamlessly, and an edit to them must keep them so, or every
road shows its tile grid. A road's 12 m also keeps its pattern of stones and patches from lining
up into a lattice along the road, as it did at 6 m.
`tools/materials/roads/road_maps.py` writes the road maps from their sources as the export does,
without Material Maker, and reports how much each map changes across its tile edge;
`--make-seamless` first makes sources that show their grid tile (`tools/materials/seamless.py`),
and `--lengthen N` quilts the sources into a tile covering N times their ground at the same size,
from pieces of themselves (`tools/materials/quilt.py`; the material must have no direction of its
own, such as baked light, as pieces are turned and mirrored). The road sources' 12 m came from
6 m ones with `--lengthen 2`. After it, multiply the project's *RepeatMetres* and the catalogue's
`metres` by N and divide its *depth_scale* by N (its *ReliefMetres* stays). Both scripts need
numpy and scipy.

## Exporting

From the editor: *File > Export material > Godot > Godot 4 Standard* into the folder in
the table above. In the game, *Reload assets* in the Tuning panel picks up the new export.

For lava, crust and ice, Material Maker asks whether to overwrite `<name>.tres`, the
`ShaderMaterial`. Choose **Keep existing file(s)** when only the maps changed. When the
Material node's factors changed, overwrite it, then run `python tools/materials/export.py
--wrap`, which turns Material Maker's `StandardMaterial3D` back into the `ShaderMaterial` with
the new factors, without Material Maker. Until then the game refuses the material and says so.

From the command line, run from the mm-data root (requires Material Maker and Pillow):

```text
python tools/materials/export.py
python tools/materials/export.py terrain/surfaces/grass/grass.ptex
python tools/materials/export.py --wrap
```

The script exports every project, or the one given. Material Maker's command line renders
every map at 2048 pixels whatever the Size, so the script resamples each map to its
node's Size, the size the editor writes; the pixels are close to the editor's, not identical.
Sizes above 2048, or exact pixels, need the editor's export. The script
then removes maps the material no longer has, and writes the `ShaderMaterial` of a material
with a shader beside it. For a loose material it prints the ground one repeat covers, and
warns when the project's *Repeat (metres)* disagrees with it. `--wrap` only restores
`ShaderMaterial`s an editor export replaced, and needs neither Material Maker nor Pillow.

megamek's `docs/gpu-board-materials.md` describes how the game reads these files.
