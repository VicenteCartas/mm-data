# Board materials

Every material of the 3D board is a Material Maker project here, exported as a Godot 4
`StandardMaterial3D`: the stock **Godot/Godot 4 Standard** export, with no custom target.

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
`.tres` and its maps in Godot directly.

Three materials need one map that a standard material has no slot for. A stock **Export**
node writes it beside the others, under a plain file name:

| Project | Export node | Map |
| --- | --- | --- |
| `terrain/lava/lava` | `ExportMask` | `lava_coverage.png`: exposed-melt coverage |
| `terrain/lava/crust` | `ExportMask` | `crust_glow.png`: crack glow |
| `terrain/ice/sheet` | `ExportCracks` | `sheet_cracks.png`: cracks and bubbles |

Most projects quantize each map with a `…PNG8` group before the Material node, so the
exported bytes are exact codes. The nodes after those groups only undo what the Material
node applies on export: the normal's conversion, and the heightmap's 1 − depth.

### Sculpted terrain roughness

Sculpted terrain (`terrain/surfaces`) normally takes the game's contextual roughness, from
its role, hardness and distance. Most of its projects keep the Roughness input white
through a `RoughnessOverride` switch. Set **Override contextual roughness** to 1 to export
the authored roughness instead. A roughness map that varies replaces the context. A
Material Roughness factor below 1 over a white map is a scalar, like `tree-pit-mulch`'s
0.92. Mud and scorch always export their roughness.

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
in the catalogue. Catalogue every new material too: a loose one needs its entry to load,
and megamek's `GpuBoardMaterialsTest` requires every material to be listed.

## Exporting

From the editor: *File > Export material > Godot > Godot 4 Standard* into the folder in
the table above. In the game, *Reload assets* in the Tuning panel picks up the new export.

From the command line, run from the mm-data root (requires Material Maker and Pillow):

```text
python tools/materials/export.py
python tools/materials/export.py terrain/surfaces/grass/grass.ptex
```

The script exports every project, or the one given. Material Maker's command line renders
every map at 2048 pixels whatever the Size, so the script resamples each map to its
node's Size, as the editor writes it. Sizes above 2048 need the editor's export. The script
then removes maps the material no longer has. For a loose material it prints the ground
one repeat covers, and warns when the project's *Repeat (metres)* disagrees with it.

megamek's `docs/gpu-board-materials.md` describes how the game reads these files.
