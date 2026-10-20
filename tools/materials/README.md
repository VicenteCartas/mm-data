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
| Emission | `<name>_emission.png` | Lava heat. |
| SSS | `<name>_sss.png` | Ice cloudiness, foliage transmission. |

The Material node's parameters become the resource's factors (roughness, metallic,
normal strength, emission energy, depth scale). A Godot-literate artist can open the
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
  industrial plating. Each entry gives the width it was catalogued at (`pixels`). Terrain
  surfaces also give the metres one repeat spans at that width (`metres`).
- **Constrained** materials fit a footprint: facades, classic tiles, scars, scenery and
  plant cutouts.

The game keeps a loose material's texel density. Export grass, catalogued at 512 pixels and
4 m, at 1024 pixels and it covers 8 m before repeating. The pattern then also needs
to be twice as large in the project, for example by doubling its feature counts and
*Repeat (metres)*. Its maps must stay square. To change a density instead, change `metres`
in the catalogue; *Reload assets* in the game's Tuning panel re-reads it and shows the new
density at once. Catalogue every new material too: a loose one needs its entry to load,
and megamek's `GpuBoardMaterialsTest` requires every material to be listed.

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
node's Size, as the editor writes it. Sizes above 2048 need the editor's export. The script
then removes maps the material no longer has, and writes the `ShaderMaterial` of a material
with a shader beside it. For a loose material it prints the ground one repeat covers, and
warns when the project's *Repeat (metres)* disagrees with it. `--wrap` only restores
`ShaderMaterial`s an editor export replaced, and needs neither Material Maker nor Pillow.

megamek's `docs/gpu-board-materials.md` describes how the game reads these files.
