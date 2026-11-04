# MegaMek GLB Viewer for VS Code

A 3D viewer and surface-material editor for the GLBs in `mm-data`. The viewport
stays separate from the View, Materials, Palette, Parts, Test and Info tabs.

## Install

1. In VS Code, open **Extensions**, choose **⋯ → Install from VSIX…** and select
   `tools/vscode-glb/megamek-glb-viewer.vsix`.
2. Open a `.glb`. If another extension owns the file, right-click its editor tab,
   choose **Reopen Editor With… → MegaMek GLB Viewer**, and optionally configure it
   as the default for `.glb`.
3. Open the `mm-data` folder as a workspace. Normally no configuration is needed.
   **Settings** in the viewer opens the extension's settings. `mmDataPath` accepts
   the checkout folder containing `data/models`; it is useful when viewing a GLB
   outside that checkout.

Command-line installation is also available:

```powershell
code --install-extension tools/vscode-glb/megamek-glb-viewer.vsix
```

## View and inspect

- Source Control and Git diffs open the **Staged**, **Working copy**, or named Git
  revision. Git views load the mesh, textures, `.tres` files and descriptors from
  that revision; missing dependencies never silently use working-copy files.
  Staged views refresh when the index changes. **Open working copy** opens its
  editable-on-disk counterpart beside the revision.
- **Sync views** is on by default for open versions of the same GLB. Orbit, pan,
  zoom, framing, LOD, projection, shading, wireframe, lighting, helpers, variants,
  labels and colour selections follow in both directions. Turn it off in a view
  to inspect that version independently. A missing LOD or variant is reported
  in that view; its existing selection is retained. Parts visibility, selection,
  animations and engine-test assemblies remain independent.
- Orbit with left drag, pan with right drag, zoom with the wheel, and press **F**
  over the viewport to fit. Orthographic is the default projection; perspective
  and four camera presets are available. Camera clipping follows the visible model as you orbit and zoom to
  preserve depth precision between nearby surfaces. The grid includes a board
  hex footprint.
- **Geometry by LOD** shows referenced vertices, triangles and primitives for
  each authored LOD. Hover a row for mesh-instance, material and node counts;
  click it to switch and fit. Helper geometry has a separate row. Vertices count
  unique POSITION-accessor/index pairs; triangles and primitives include repeated
  scene instances. These are authored counts, not engine-generated back faces,
  floors or rendering passes. An assembled kit's visible triangle/mesh counts
  appear in the header.
- Display materials, wireframe, clay, normals or UVs; adjust exposure, environment
  illumination and background. Toggle bloom and model bounds. **Gameplay geometry & markers**
  shows `cut` geometry, `building_volumes` and `stand-N`, `vehicle-N`, `hide-N` direction markers.
  These guides are hidden by default and shown as wireframes, separately from the visible model.
- **Measure two points** reports distance and axis differences in model units.
  **Save PNG** exports the viewport to a location you choose.
- Click geometry to edit that surface in **Materials**. In **Parts**, click geometry
  to inspect its hierarchy. Search nodes, hide them, solo a part,
  double-click its name to frame it, or reset visibility. Selection details show
  geometry counts and original node metadata, including joints and hardpoints.
- **Materials** edits surface assignments and lists this GLB's materials, with search, map previews,
  factors, channel choices and links to their source `.tres` and images.
- **Info** lists dependencies, diagnostics, file extras and adjacent JSON
  descriptors that reference this mesh. Nothing in those files is executed.

## MegaMek materials and metadata

External `_albedo.png` images under `data/models/board/textures` discover their
adjacent `.tres`. StandardMaterial3D tint, roughness, metallic, selected map
channels, normal strength, occlusion and emission are previewed alongside ordinary
glTF materials, embedded PNG/JPEG textures, vertex colours, alpha cutouts and
double-sided surfaces. Walls retain their separate emissive lamp materials.

Colour-slot presets and custom colours, paint masks, label atlases and seasonal
`mmVariants` such as snow have preview controls. Standard glTF animation playback
is available for inspection; the engine's rigid loader rejects animation tracks
and skins. The Info panel points out that distinction and unsupported engine
extensions, including `KHR_materials_emissive_strength`.

Save changes in Blender or Material Maker and the viewer refreshes its GLB and
material dependencies while keeping the camera. **Reload** is available for an
explicit refresh. A file change invalidates any previous engine-test snapshot.
View controls do not save geometry, colour-slot previews or label previews.

## Material palette and saving

1. Open **Palette**. It reads `data/models/board/textures/materials.json` from the
   detected mm-data checkout (or `mmDataPath` in Settings), including both loose
   and constrained materials. Search by name/path and filter by folder or type.
   Eight albedo thumbnails per page keep the palette bounded; maps load only for
   the displayed page. Unavailable materials show their error instead of silently
   disappearing. **Refresh** re-reads the catalogue and maps.
2. Click a surface in the viewport while **Palette** or **Materials** is open,
   or choose it from **Surface**. A surface is one authored glTF primitive, not
   an arbitrary face selection. The list distinguishes each node, LOD and surface.
3. Select a palette card and click **Assign to surface**. **This surface only**
   isolates shared material/mesh instances. Choose **All using this material** to
   replace every use, including other LODs. **Keep model emission** retains
   authored lamp emission; shared emission still comes from the chosen `.tres`.
   Textured assignment requires existing UV coordinates; unwrap missing UVs in Blender.
4. In **Materials**, use **Assign a different material** to reuse an existing GLB
   material (including embedded textures). Tint is directly visible; expand
   **Emission & surface properties** to change opacity, emission, alpha
   cutoff and double-sided rendering. Ordinary GLB materials also expose roughness
   and metallic; shared ones use their `.tres`. These edits do not modify library files.
5. Use **Save GLB** / **Ctrl+S**, or **Save as…**. Normal VS Code dirty tabs,
   Undo/Redo, close prompts, File: Revert File and hot-exit backups are supported.
   Save As rebases external image/buffer and `mmVariants` paths for its new folder.

Material assignment and factor edits rewrite only GLB JSON. Placement and vertex
paint edits append UV/colour attributes while retaining the original binary data,
embedded images and other chunks. Positions, normals, triangle indices, node
metadata, animations and untouched materials remain intact. A selected surface may
get a separate mesh/material record to avoid changing another instance. Files are
replaced through an adjacent temporary file.
If the disk file changed since it was loaded/saved, Save refuses to overwrite it;
use Save As to retain the edits or File: Revert File to load the disk version.
Reload preserves unsaved material edits while refreshing their dependencies.

Edits affect the base material; select **Default** under Season / variant first.
Existing seasonal overrides are preserved. Save before running engine tests, which
read the disk file. Git views have a revision-specific palette and remain read-only;
**Open working copy** opens the editable file. Linked comparisons synchronize viewing
controls, not material edits. Mesh construction and UV unwrapping stay in Blender; View-tab colour
slots and labels remain previews. Alpha blending is available for glTF previews but
is not supported by MegaMek's rigid loader.

## Placement, tint and authored paint

Click a surface to open **Materials**, or choose one from its **Surface** list.
Offset, scale, rotation and tint are at the top, without an accordion or Apply button.
The Palette's **Edit offset, scale, rotation & tint** button opens these controls.
After installing an update, run **Developer: Reload Window** in VS Code to load the new UI.

- **Offset, scale & rotation** has U/V offset, scale/repeat, rotation in degrees, a U/V pivot,
  ratio locking, quarter turns and flips. Repeat 2 halves the pattern size; one
  offset unit is one texture tile. Scale is applied around the pivot, then rotated,
  then offset. **Fit one tile** fits the referenced UVs into 0–1. **UV checker**
  shows eight checks per tile and orange tile borders; **Show material** returns to PBR.
  Changes preview live on all maps without reloading the model or moving the camera.
  Tint and the advanced surface properties also preview live. They update the unsaved
  document immediately; **Ctrl+S** saves the latest value even while a control is focused.
  Adjustments within a control share an undo step and replace that gesture's UV data.
  Invalid or incomplete numbers retain the last valid preview. The controls retain
  their absolute values after saving/reopening; edits do not compound the transform.
  **Restore original UVs** returns to the coordinates before this editor's first
  placement edit, even after reopening. Undo/Redo also works normally.
- **Material tint** includes the picker, a hex entry,
  and **Reset white**. Tint multiplies the texture, shared `.tres` tint and any
  authored vertex colour; it cannot remove an existing red vertex tint by itself.
- **Vertex paint (authored tint)** handles models such as the fuel tanks, whose
  red/yellow bands, grey rings, contact shading and grime are vertex colours.
  Click an authored swatch to select that paint across its shaded variations, then
  change **New colour** to preview immediately. There is no Apply step; **Ctrl+S**
  saves the latest preview, even while the colour control is focused. Colour, mode
  and tolerance adjustments within the paint controls share an Undo step.
  Swatches and matching use the original authored colours, so a red band stays
  selected after turning blue, saving and reopening. **Recolour, keep shading**
  also uses the original shading, including after a solid, black or white edit.
  Selecting another swatch starts a separate adjustment and preserves the earlier
  paint group. The match compares RGB proportions;
  tolerance controls how similar a colour must be. Unmatched colours and vertex
  alpha are retained. Disable matching to affect the whole selected surface.
  With **All using this material**, parts without matching paint remain unchanged.
  **Solid colour** replaces the selected paint without retaining shade variation;
  **White / remove tint** neutralizes it. **Restore original paint** restores the
  attribute before the first paint edit. A surface with no colour attribute can
  receive paint, and restoration removes that newly added attribute.
- **Texture wrapping & filtering** offers repeat, mirrored repeat and clamp for
  U/V, plus nearest/linear filtering and mipmap choices. Every selection previews
  live, without Apply; **Ctrl+S** saves the latest settings. Adjustments inside the
  sampling controls share an Undo step. These apply to the material's
  maps; shared `.tres` maps follow the albedo sampler. Other materials sharing the
  original texture/sampler are isolated.

The **Apply to** selector scopes all these edits to one surface or every use of
its material. Seasonal overrides remain intact and may replace colours in a
non-default variant. Library files are never changed by these controls.

Placement is baked into `TEXCOORD_0`, because the engine and Blender add-on do not
support `KHR_texture_transform`. Normal maps follow those same UVs. Stale authored
tangents are removed on the edited primitive so the viewer derives its tangent basis
from the new UVs; restoring UVs restores the original tangent accessor. Original
attribute references and placement values are retained in primitive extras for Reset.
UV unwrapping, decompression, extra UV sets, per-map texture transforms and label-atlas
placement require the corresponding Blender/label tools. These cases report an error
instead of saving an adjustment that the engine would ignore.

## Engine validation and connected kits

**Test** reuses the same Java bridge as `tools/blender`; it does not implement a
second set of connection rules. A sibling `megamek_temp` or `megamek` checkout is
detected automatically. Otherwise set `enginePath` to the folder containing
`gradlew` and `gradle/wrapper`.

1. Trust the workspace, then choose **Build / Refresh Engine** once, and again
   after engine changes. The build needs the engine's JDK and Gradle dependencies.
   `javaPath` defaults to `java`; the bridge runs with the JDK recorded by Gradle.
2. Choose **Building / connected kit** or **Rigid asset / scenery**.
3. For kits, set building levels, six connected heights (0 means disconnected),
   rotation and variant seed. Straight/corner/all-side presets fill those inputs.
4. **Validate / Assemble** runs the existing engine loader and displays its returned
   placements. This covers `base`, `floor`, `roof`, `link`, `end`, two-tag corners,
   symmetric rotation, early connection roofs and LOD fallback.
5. **Show authored** returns to the source geometry. **Logs** opens the full engine
   output. A failed test removes a previous successful assembly.

The bridge uses `megamek/build/blender-preview.json`, created by the existing
`:megamek:prepareBlenderPreview` Gradle task. It writes only temporary requests and
results, never the GLB. Engine processes require a trusted workspace. Viewing is
available without running Java or Gradle.

Engine tests run on the working copy. Git revision views disable these actions
so an older/staged model is never accidentally validated against a different
file on disk; use **Open working copy** for engine validation and assembly.

## Preview boundaries

Three.js PBR lighting is an authoring preview, not the game renderer. Custom Godot
shader code is not executed. Lava/ice effects, game parallax, subsurface lighting,
foliage response, generated interiors, terrain fitting and cutaways require the
game. Height/SSS maps remain inspectable; height has a bump approximation when no
normal map is present. Combined GLB and shared-material emission is approximate.
Bloom can also catch bright highlights.

The viewer displays unit meshes, rigs, hardpoint nodes and adjacent descriptor
metadata; it does not assemble equipment loadouts or simulate gameplay animation.
Draco/KTX2/meshopt decoders are not bundled: the shipped MegaMek rigid assets do
not use them, and unsupported compressed GLBs report a load error. Models and
texture dependencies must be local; network image URIs and escaping paths are
rejected. An invalid/missing required dependency produces a visible error.

## Develop and package

Requires Node.js 22 or newer and npm. Dependencies are pinned in `package-lock.json`.

```powershell
cd tools/vscode-glb
npm ci
npm run build
npm test
npm run test:browser
npm run test:extension
npm run audit
npm run package
```

The VSIX includes bundled Three.js and works offline. It contains no game assets,
no telemetry and no CDN dependency. Use **F5** with this folder open in VS Code
for an Extension Development Host. Browser tests use installed Microsoft Edge;
extension tests use a separate VS Code profile. Set `VSCODE_EXECUTABLE` to select
a particular VS Code executable. `test-output` and build/dependency directories
are ignored by Git.

`npm test` exercises GLB parsing, accurate per-LOD counts, path restrictions,
Godot material parsing, shipped asset metadata, and the existing engine bridge
when a sibling checkout is available. Browser tests exercise the actual bundled
viewer and save captures, including a pixel regression for nearly touching
surfaces in both camera modes while orbiting and zooming. The extension-host test
checks registration and the real webview's local resources, materials, statistics
and engine assembly. Git fixtures verify separate staged/working geometry and
materials, index refresh, linked controls, and bidirectional camera movement
without update loops. They use disposable repositories and do not stage project
files.
`npm run audit` reads every shipped GLB and writes a detailed report; warnings
about shading approximations are separate from actual load errors.

The extension code is GPL-3.0-or-later. Bundled Three.js is MIT licensed (see
`dist/THREE-LICENSE.txt`). The separate `mm-data` assets retain their own license.
