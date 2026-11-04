# MegaMek Materials & GLB for Blender

Blender 5.2 add-on for assigning the shared Material Maker materials and editing the
rigid GLBs in `mm-data`. Tested with Blender 5.2.2 on Windows.

Version 1.4.1 keeps a white colour multiplier on meshes without vertex-colour attributes, including after refresh.
For materials marked `mmPaintMask`, albedo alpha selects the vertex paint and is never treated as transparency.

## Install

Run `python tools/blender/package_addon.py` from mm-data. In Blender choose **Edit →
Preferences → Add-ons → menu → Install from Disk**, choose the resulting
`tools/blender/mm_materials.zip`, and enable **MegaMek Materials & GLB**.

The 3D View sidebar (**N**) has two tabs: **MegaMek** for GLB files and tests, and
**MM Materials** for browsing and assignment. Under **MM Materials → Library Setup**,
set **mm-data** to your checkout (the folder containing `data`, not
`data/models/board/textures`). Click **Load Materials** in the browser. The add-on scans
`<mm-data folder>/data/models/board/textures/**/*.tres`; it never depends on an opened GLB
to discover the library. Changing folders clears the old list; Refresh loads the new one.
Click **Save as Default Folder** to remember the path for new scenes and future Blender
sessions. The default is also editable in the add-on preferences. A scene's chosen
folder is stored in its `.blend` and takes precedence over the default.

## Visual material palette

Open **N → MM Materials**, or click **Browse Materials** in the **MegaMek** tab.
Browse Materials loads the library automatically if needed. The browser shows **six
materials per page**, with previous/next arrows, name/path search and a folder filter.
Small thumbnails show 12 per page; Large shows four. Loading more materials adds pages,
so the browser stays bounded. Search, folder and thumbnail-size changes return to page 1.
The refresh icon beside Search refreshes the library and retains the chosen material.
Hover a material's name button to see its complete library path.

Click the **name below a thumbnail** to assign it to selected mesh objects' active
material slots, or to selected faces in Edit Mode. Disable **Assign on click** to
browse first, then use **Assign Chosen Material**. With no mesh selected, a click only
chooses the material. Expand **Material Slots** to choose the active slot. File controls
remain in the separate **MegaMek** tab and never move below the thumbnail grid.

**Library Setup → Build / Update Thumbnails** builds shaded sphere previews of the `.tres` materials,
including their tint, normal detail, roughness and emission. Until a sphere is ready,
its tile shows the albedo. Rendering runs in a separate background Blender process;
the working scene, objects, materials and selection are untouched. Stop it at any time
and retain the previews already finished. Previews are cached in
`mm-data/.tmp/blender-material-previews` and shared by scenes. After changing a material
or its maps, Refresh Library and render again; only missing or changed previews render.
The same preview limitations described below apply to these thumbnails.

## Create a new mesh

1. Model normally in Blender. No GLB import is required. UV unwrap your mesh (one UV set).
2. Select your mesh and use **MM Materials** to choose and assign a material.
   Selected faces in Edit Mode can receive different materials.
3. Select every object that belongs in the asset and click **MegaMek → Export Selected GLB**.
   Save under `mm-data/data/models`. Unselected meshes, cameras, and lights are omitted.
4. If the export has no LOD groups, the add-on adds an identity `<filename>-lod0` group
   around the selected geometry. Existing LOD groups are checked and preserved. Shared
   albedos are stored as relative image paths; the game finds the adjacent `.tres`.

This export does not bind the whole working scene to that file. Continue editing and
use **Export Selected GLB** again; its file dialog remembers the last export path.
It also works in Edit Mode (exports the selected objects' complete meshes, not just
selected faces). To include a hierarchy, select its objects, including any authored
LOD empties. Mesh transforms are retained; place the model around its intended origin.
Missing vertex colours use the game's white default. No rig, attachment descriptor,
manifest entry, or extra LOD geometry is invented for a new mesh.

## Work on a GLB

1. Click **Open MegaMek GLB**. It opens in a new scene and automatically builds material
   previews from the external albedos' adjacent `.tres` files. Existing scenes remain open.
2. Use **Preview LOD** to view one level. All levels are included when saving, including
   ones hidden in the viewport. Use the Outliner to select the mesh you want to edit.
3. Click **Browse Materials** to switch to the material browser.
   In **Object Mode**, assignment replaces the active slot on selected meshes.
   Choose the slot under **Material Slots**. In **Edit Mode**, assignment adds a new slot
   only to selected faces. UV unwrap new geometry; adjust texture size in the UV Editor.
4. After exporting changes from Material Maker, use **Library Setup → Reload Assigned Materials**.
5. Click **Save GLB** to update the source, or **Save As…** for a copy under `data/models`.
   Normal Blender **Ctrl+S** still saves the `.blend`; it does not save your GLB.

The GLB is exported to a temporary file, checked, then replaced atomically. Existing files
are backed up under `mm-data/.tmp/blender-backups/data/models/...`, with timestamps.
Saving refuses to overwrite a source changed by another program since Open/Save.
Use Save As or reopen in that case. Save your `.blend` separately for editable history.

## Material contract

The `.tres` and its images are the source of truth. The add-on reads them; it does not
write them. A managed material exports the relative path of its shared `_albedo.png`;
the game discovers the adjacent `.tres` and supplies the remaining maps and factors.
Blender shader edits to these managed materials are preview-only and are replaced by
Reload. Change their finish in Material Maker.

Previews include albedo/tint, roughness/metallic map channels and factors, OpenGL normal
maps and strength, emission, approximate SSS, vertex colour, and alpha cutouts. AO is
loaded for inspection; Principled has no AO input. Height/parallax and custom Godot
shaders (including lava and ice effects) are not reproduced. Combined GLB and `.tres`
emission is an approximate preview; the original GLB emission remains in the export. Compare final appearance
in the game. Blender lighting and colour management also differ.

Unmanaged materials use Blender's normal glTF exporter. Existing external PNG/JPEG
images under `data/models` stay external when their channels can be used directly.
Packed images, including per-model roof/crate textures, stay embedded. A shader that
requires channel repacking may produce an embedded image. Missing dependencies stop
library material loading and failed exports leave the existing GLB untouched.
You can mix shared and embedded materials in the same mesh/GLB. For a custom embedded
texture, use an ordinary Blender material with an Image Texture connected to Principled,
and pack that image (Image Editor → Image → Pack). Assign it to a slot or selected faces
normally. Library materials stay linked to their `.tres` regardless of image packing.

Custom lamp materials export Principled's Emission Color and its image. The wall kits
use shared external body textures plus separate, untextured red emissive lamp materials;
both survive Open/Save. Imported GLB emission on a material with a shared albedo is also
retained. Library emission comes from the `.tres`. For ordinary GLB emission, keep the
result within 0–1: the engine does not read `KHR_materials_emissive_strength`, which Blender
uses for brighter emission. Export rejects that unsupported extension rather than losing
brightness. Higher emission energy belongs in a shared `.tres`. Emissive surfaces are
materials; this tool does not export Blender lights. Bloom and game lighting are not
reproduced by Material Preview.

Save texture-paint edits to their images before saving a managed GLB; the add-on checks
for unsaved image edits. Reload discards those edits and reads the images from disk.

## Test an asset inside Blender

Open **N → MegaMek → Asset Test**. The test runs on a temporary export of your current
edits; it does not save over the source GLB or change the authoring scene. This works
for newly created meshes too. Enable **Selected objects only** when your working scene
also contains unrelated objects; include every LOD and mesh belonging to the asset.

The Asset Test panel starts collapsed. Under **Engine Setup**, set **Checkout** to the repository
containing `gradlew` (automatically finds sibling `megamek_temp` or `megamek`). Click
**Build / Refresh Engine** once and again after engine changes. This requires the JDK and
Gradle dependencies used to build the game. It runs in the background and reports errors
in the panel. The setting is also in add-on preferences; save preferences to retain it.

- **Building / Connected Kit**: select LOD, building height, six connection heights
  (0 = disconnected), clockwise rotation in 60° steps, and a variant seed. Click
  **Test Current Edits**. The engine checks module names, dimensions, matching pieces
  across roles/LODs, symmetric/directional pieces, and corner completeness. It assembles
  core, `link`, and `end` pieces, including two-tag conditions, repeating symmetric
  pieces, and roofs where a connection stops below the building's top.
- **Rigid Asset / Scenery**: runs the GLB loader and displays the requested LOD, using
  the engine's fallback when that LOD is absent. `cut` geometry is shown as wire helpers;
  `stands` children show direction arrows. These helpers remain in the source asset.

A successful test opens a separate snapshot scene. **Return to Authoring** removes it
and returns to your editable objects. Change controls and retest to update the snapshot.
The add-on refuses to export the test scene, so repeated pieces cannot accidentally
become authored geometry. Full errors are available in the Text Editor as **MegaMek
Asset Test Report**. A failed retest removes an old successful preview.

The preview uses engine assembly with Blender shading. It does not run the board,
choose wall families from terrain, generate building interiors, or simulate unit rigs,
weapon attachments, labels, paint masks, recolouring, or seasonal material changes.
Those metadata are preserved, but their runtime behavior still needs the game. Adjacent
unit/turret JSON descriptors and manifests are not validated by this panel.

## Preserved data and limits

- LOD hierarchy and node names, material roles/custom properties, mesh/primitive
  metadata (`mmPart`), root extras (`mmColourSlots`), UVs, vertex colours, and
  `_COLOUR_SLOT` are carried through the supported import/export path. Variant texture
  paths are rebased on Save As. Use this add-on's Open command to retain file-level data.
- Building `-baseN`, `-floorN`, `-roofN`, `-link-<dir>`, `-end-<dir>` and two-tag names
  stay intact, as do `cut`, `stands`, `stand-N`, `vehicle-N`, `hide-N`, `part-N`, and
  unit joint/hardpoint node names. These are documented in `data/models/buildings/README.md`,
  `data/models/board/README.md` and `data/models/units/README.md`. The add-on does not
  rename these nodes into a new convention. New authored duplicate suffixes such as
  `.001` are reported by the engine's building test.
- Reversed duplicate foliage triangles are prepared in an import copy so Blender
  does not discard the back faces. The source is never changed by Open.
- Blender rebuilds split normals and may reorganize vertices/accessors. This is a mesh
  editor, not a byte-for-byte GLB editor. Inspect shading after geometry edits.
- Supports the game's rigid triangle meshes with one UV set and one colour layer.
  Skinning, animation tracks, shape keys, required glTF extensions, texture transforms,
  and degenerate indexed triangles are rejected. Unsupported distinct primitive extras
  sharing one material are rejected rather than silently discarded.
- If two separately edited copies of one gameplay material role have different
  definitions, give them distinct material names before saving. Identical definitions
  are merged. Material names can have gameplay meaning (for example `shell`).
- Face assignment to linked mesh data requires making that mesh single-user first.
- Geometry edits can require updates to the existing asset manifests, triangle budgets,
  or attachment descriptors. This add-on does not rewrite those files.
- Ordinary Blender export is unaffected. Its default GLB export can still embed images;
  use **Save GLB** from the MegaMek panel for this pipeline.

## Development

The add-on uses Blender's glTF import/export extension hooks. They are active only
during its own Open/Save operations. It adds no renderer or runtime format.

Run the integration check with:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python-exit-code 1 --python tools/blender/test_roundtrip.py
```

The check uses temporary assets and covers a tunnel round trip, slot/face assignment,
concurrent-change rejection, LOD/cutout foliage, embedded textures, and the material
catalog, plus game metadata/colour slots and variant path rebasing. It does not overwrite
shipped GLBs. `render_preview.py` provides an optional visual check. Blender may need `TEMP`/`TMP` set to a
writable directory when running inside a restricted shell.

Run `test_new_mesh.py` with the same Blender arguments for the fresh-scene workflow:
preferences-based library discovery, assigning to a new cube, selection-only export
from Edit Mode, automatic LOD0, external textures, white colour defaults, and re-import.

`test_palette.py` checks bounded pagination with every material reachable, filter/page
resets, selection retention on refresh, visual-library discovery, optional
click assignment in Object/Edit Mode, independent thumbnail rendering, cache invalidation,
switching library roots, missing-map reporting and preview cleanup.

Run `gradlew :megamek:prepareBlenderPreview` in the engine checkout, then run
`test_asset_testing.py` with Blender for the wall/scenery and engine bridge integration
checks. It covers all 18 walls, their lamp emission and hierarchy, `cut`/`stands`,
connection heights and rotation, LOD selection, invalid tags, synthetic two-tag link/end
corners, mixed embedded/shared materials and model emission on a shared albedo.
For a rendered wall assembly check, run `render_preview.py -- --kit` with the same
Blender arguments. It writes `.tmp/blender-kit-preview.png`.
