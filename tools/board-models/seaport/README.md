# Container geometry and LODs

`source/container.glb` preserves the original editable detailed and medium container meshes, their paint slot and
valid links to the Material Maker exports. `container-placements.json` records the existing 17 models' container
positions, rotations, colours, slots and exposed faces. It was recovered from their original box geometry;
fully hidden interior containers need no geometry. The machinery remains in the deployed models and is preserved
when rebuilding their container parts.

Run from the mm-data root with Python, NumPy and Pillow:

```text
python tools/board-models/seaport/build_container_lods.py
```

Use `--output PATH` for a separate board-model directory and `--report FILE.json` for counts. The build uses the
existing rigid GLB exporter and writes only the 17 container-bearing GLBs and four shared `container-details` maps/material.

Individual containers, stacks and carried containers retain detailed LOD0 corner posts, rails, casting plates,
door leaves, locking rods, handles and hinges. Their LOD1 has a recessed panel and four connecting rim strips
per exposed face (10 triangles), with the frame, door gasket and hardware baked into the shared atlas.
The underside of a carried container stays one quad.

The ten yard compositions use budgets for the complete mesh, rather than repeating the detailed prop hundreds
of times. They are identified by their existing `yard/<name>` entries in `scenery/layouts.json`:

- LOD0: recessed walls with top and bottom rail profiles, six triangles per exposed wall and two per roof.
- LOD1: only the top rail profile remains, four triangles per exposed wall and two per roof.
- LOD2: the original flat exposed box faces, two triangles each.

All yard levels use the same padded 512-pixel atlas of sides, doors, back and roof. Vertical corner posts, castings
and door hardware use baked shading. The rail profiles meet at the corners with no gaps between adjoining faces.
The atlas bakes albedo, tangent normals and ORM from the detailed source without lighting. Its albedo alpha masks
paint tint on neutral metal hardware, never transparency. Individual props also use this atlas at LOD1/LOD2.

The build enforces whole-yard mesh ceilings of 3,000/2,000/1,100 triangles. Current counts:

| Asset | LOD0 | LOD1 | LOD2 |
| --- | ---: | ---: | ---: |
| Single container | 250 | 50 | 10 |
| Heavy rows | 1,868 | 1,264 | 660 |
| Ultra rows | 2,940 | 1,980 | 1,020 |
| Ultra yard gantry containers | 2,316 | 1,560 | 804 |

These yard mesh counts exclude cranes and vehicles placed separately by the layout.
The placement, paint slots/presets, and machinery survive all levels. Hidden neighbour faces are omitted; nearby
stacked bodies are slightly inset to expose physical joints. Existing runtime prop LOD selection uses all three
levels, and LOD3 falls back to LOD2. No runtime renderer changes are needed.

Re-export `corrugated-painted` and `steel` through Material Maker first when changing those surfaces, then rebuild
this atlas so its distant finish agrees with the near geometry. The unpainted wall material is independent.

Validation: `ContainerAssetLodTest` loads all 17 models through the game importer and checks distinct decreasing LODs,
whole-yard triangle ceilings (individual props' LOD1 container geometry remains at most one quarter of LOD0),
stable bounds, colour slots, opaque paint masks and the baked surface maps. Native render review additionally checks
close-up geometry and actual distance-based LOD selection.
