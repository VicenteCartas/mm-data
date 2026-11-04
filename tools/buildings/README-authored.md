# Authored multi-hex examples

`authored_examples.py` creates the GLBs in `data/models/buildings/authored`, editable Blender sources and studio
renders in `tools/buildings/authored`. The HPG implementation is in `hpg_headquarters.py`; the example generator
delegates to it. The research station continues to use the shared procedural board finishes. Run both with Blender 5.2:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python tools/buildings/authored_examples.py
```

- HPG headquarters: fixed whole model with one-, two- and three-level structural sections. The main reflector,
  elevated mount, secondary radar and rooftop machinery are decoration. They create no additional floors.
- Xenobiology research station: U-shaped `base0`, `floor0`, `floor1`, `roof0`; floor variants repeat for the chosen
  height. Its courtyard stays empty. This is a research facility, not a hangar.

## Structural helpers in GLB

Use a separate `building_volumes` group with closed, outward-facing helper meshes. Each helper is one solid;
overlapping solids are unioned. Helpers can instead be children of a visible module. They never render or affect
visual bounds or palette thumbnails. Model in Blender Z-up; GLB exports use glTF Y-up. One game level is 18 model
units, one hex about 83.125 by 72. Use horizontal, level-aligned structural tops.

For a whole building, helper names begin `building_volume`, for example `building_volume-command`. For an assembled
building, associate helpers with their module by nesting them beneath it or ending their names in `-base0`, `-floor0`,
`-roof0`, etc. `level0` is an alias for `floor0`. Supply closed solids for base and each repeated floor. Visible modules
can have nested transforms. A set containing base, floor/level and roof is assembled; without that pattern the model
is fixed-height. Optional visible LOD roots use `name-lod0`, `name-lod1`, etc.; an authored model with no LOD groups is
also supported. These examples export two LODs, omitting small details from the second.

Module placement aligns each visible module's bottom to its storey's level. Its helper uses the same transform.
Roof ornamentation does not belong in a structural helper. Keep wall modules hollow: the engine generates interior
floors from horizontal sections of helpers, preserving courtyards and changing outlines. These solids also determine
coverage, dominant height and roof supports. Sloped tops are not a gameplay-volume contract here; represent usable
roofs with flat stepped helper solids.

Assembly precedes vertical slicing into stable hex-owned shares. Interior policy affects access and generated floors,
not exterior assembly. Remaining shares survive anchor collapse. The editor exposes arbitrary rotation about Z and
precision XY movement for structural buildings.

## HPG reference and scale

The current model follows the supplied HexTech interstellar communications facility and the joined overhead map,
not the earlier generated concept. `references/hpg-joined-map.png` is imported into the Blender scene as two
calibrated planes. The halves have a small horizontal join offset; both use the same real hex dimensions:

- Hex corners span 83.125 units horizontally; flat edges span 72 vertically.
- Columns advance 62.34375 units and alternate a 36-unit vertical offset. Rows advance 72 units.
- A building level is 18 units. The reference map's level-three ground is not part of the model.
- Source 1717 is the authoring origin. Lower-board row 01 follows upper-board row 17.

The upper service bays are centered on 1014/1214/1414. Their lower counterparts at 1002/1202/1402 are reconstructed
symmetrically: the main dish obscures them in the overhead art, so they are not independently traceable there.
The command hall is three levels; service bays and operations roofs are two; galleries, front terraces and the
secondary-radar platform are one. The main and auxiliary power banks are two and one levels respectively.
The rectangular radar is centered on 2116: twelve receiver cartridges on a driven azimuth/elevation cradle,
with rear cooling ribs and an actuator. The smaller northern sensor on 2315 is an angled relay with a recessed
blue aperture, a machined collar, cooling stack and vented base. Both remain props above their original structures.
The game model has continuous roofs: the tabletop reference's hex placement markings are not modeled.

`references/hpg-right-outline.png` preserves the user's green-base/red-roof correction. Its grid measures 77 pixels
per column and 89 pixels per row. The right end is symmetric about Y=0, with separate base and upper outlines joined
by real sloped walls. Its helper follows that slope; the flat structural top remains 36 units high. Rear heatsink
fins are decoration. The dish keeps a circular silhouette; its visual height is not a building level.

To rebuild in the running Blender instance, execute through Blender MCP:

```python
import sys, importlib
sys.path.insert(0, r'C:/Projects/megamek/mm-data/tools/buildings')
import hpg_headquarters as hpg
importlib.reload(hpg)
hpg.build()
hpg.export()
hpg.view('hero', 'review')
```

The script replaces only its own `HPG reference facility` scene and saves the live Blender workspace as
`authored/hpg-headquarters.blend`, preserving other user scenes. `view('overlay', 'review')` renders structural
outlines over the registered map; `view('plan', 'review')` hides the main reflector to expose the base. The packed
reference images, review grid and outline markers are saved in the blend and excluded from the runtime GLB.
`view('sensors', 'review')` gives a close view of the receiver and relay for material and construction review.
`view('base', 'review')` hides the reflector and frames the command hall, galleries and terminal arms.

The palette follows the supplied overhead map: warm grey reflector panels, charcoal framing, grey metal cladding
and painted metal roofs, with blue power-cell accents. It reuses the library's `structures/common/satin-steel`,
`matte-steel` and `painted-steel` finishes, inspected in Material Maker through MCP. Their native graphs are under
`tools/materials/structures/common`, and their exported PBR maps are under `data/models/board/textures/structures/common`.
The Blender preview reads their exported roughness and metallic maps and factors. Near and simplified far LODs share
these materials; colour pigments belong to the HPG mesh, so the shared library finishes are not changed.
Pigment constants use the shared exporter's sRGB convention. The preview decodes them with the same `linear()`
function before multiplying the texture, so Blender and the GLB receive matching linear colour factors.

Perimeter moldings and the receiver frame use closed solids with shared mitered corners. Metal blocks and
architectural bands keep sharp edges and flat normals; attached hatches, grilles and terminal rings meet their
supporting surfaces. The relay connector's side curbs sit beneath its bearing cap to avoid coincident top faces.

The near LOD has 49,444 triangles and 64,860 exported vertices; the far LOD has 14,130 triangles and 27,428 vertices.
Curved machinery shares smooth normals, while architectural parts and armour plates retain hard normals. Export
checks the renderer's 65,535-vertex limit for each LOD before writing the GLB. The example board is now
`data/boards/examples/32x24 Authored Buildings.board2`, large enough for the reference-scale facility and research station.
