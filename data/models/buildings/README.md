# Modular building kits

Store kits as `<family>/<name>.glb`, for example `fortress_light/fortress_light_a_52.glb`.
Do not nest this catalog under the source tileset's `saxarba` directory. The selected tileset artwork remains
the key for legacy fallback under `models/board/buildings`.

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
interior floors and struts. Keep notches and courtyards in those surfaces.

## Connected kits

A structure that changes shape with the hexsides it connects across tags its mesh nodes after the module:
`<name>-lod0-<module>[-<tag>[-<tag>]]`, each tag `link-<dir>` or `end-<dir>`, `dir` one of `n`, `ne`, `se`, `s`,
`sw`, `nw` (clockwise from north), for example `pier-lod0-floor0-link-n`.

- A node without tags is the core and always draws. `link-<dir>` draws where the hex connects towards `dir`,
  `end-<dir>` where it does not; both tags of a two-tag node must hold. A module may have tagged nodes only.
- Each piece stacks through the levels where its tags hold: a base on the ground (a floor where it starts higher),
  then its own roof where it stops, below the top or on it.
- A symmetric kit tags `n` only (one-tag pieces) or `n` and `ne` (corner pieces, in all four link/end states);
  the runtime turns them by exact 60-degree steps for the other directions. Any other kit tags all six directions
  for every piece.
- Every module variant and LOD has the same tagged pieces. Base and floor modules, tagged pieces included, are
  exactly 18 units high; a module stands on its lowest point over all its pieces.
- The board's hex is regular: 72 across its flats, 83.125 across its corners (the regular 83.138 to a 32nd), every
  edge midpoint 36 from the centre within 0.005 (Blender: X east, Y north, Z up, one unit per board unit). A one-tag
  `link` piece ends on its edge line, within one unit.
- Names are checked when the kit loads: Blender's `.001` suffixes and unknown tags are errors.

Walls (`walls/README.md`) are connected kits.

The four heavy-industrial terrain uses `BoardIndustrial` procedural generator. It assembles
different equipment families with independently chosen heights, distinct domed/conical/flat caps, and pipes
connected to actual neighboring industrial hexes. Industrial height is cover: there are no generated interior
floors, building cutaways, or elevated pointer selections. Ordinary buildings still use the modular contract above.

The active industrial materials are `models/board/textures/structures/industrial/paint.tres` and `steel.tres`
(Godot 4 Standard materials; a wider export widens their repeat). The shared `fan` material is an opaque 128x128
texture on a static quad, with mipmaps and no animation.
`tools/buildings/heavy-industrial/` preserves the first prototypes but are superseded by the runtime generator.
