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
Display the modules as an assembled example or as a spaced library rack;
the loader derives module bases and centers from geometry and discards these display offsets when assembling
one base, N-1 floors and a roof. All variants preserve the same horizontal normalization center. For enterable buildings,
the full roof projection intersected with the selected modules' closed mid-storey wall sections defines generated
interior floors and struts. Keep notches and courtyards in those surfaces.

The four heavy-industrial terrain uses `BoardIndustrial` procedural generator. It assembles
different equipment families with independently chosen heights, distinct domed/conical/flat caps, and pipes
connected to actual neighboring industrial hexes. Industrial height is cover: there are no generated interior
floors, building cutaways, or elevated pointer selections. Ordinary buildings still use the modular contract above.

The active industrial materials are `models/board/textures/structures/industrial/paint.tres` and `steel.tres`
(Godot 4 Standard materials; a wider export widens their repeat). The shared `fan` material is an opaque 128x128
texture on a static quad, with mipmaps and no animation.
`tools/buildings/heavy-industrial/` preserves the first prototypes but are superseded by the runtime generator.
