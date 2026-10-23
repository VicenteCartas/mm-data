# 3D unit models

This folder holds the 3D models the GPU board draws for units: Meks, vehicles, aircraft, infantry, battle armour and
their weapons. There is no finished model per variant. There are reusable parts, a bare body and a library of weapon
pieces, and the game puts each unit together from its real loadout. An Atlas AS7-D and a custom Atlas refit share
the same `atlas` body; only the fitted weapons differ.

Python writes these files. The game reads them with its own Java loader and never launches Python or Blender.

## What is in this folder

- `modular/` holds everything the game loads for units, described below.
- `textures/` holds the shared damage images (`armor-worn.png`, `destroyed-armor.png`, the `body-damage-*.png`
  stages and others). They belong to the renderer, not to any one model.

## Parts and recipes

A part is a pair of files with the same name: a `.glb` that holds the shape, and a `.json` descriptor beside it.
`modular/bodies/atlas.glb` is the Atlas body; `modular/bodies/atlas.json` names its joints, says which node belongs
to which armour location, and lists the hardpoints where weapons may go. A part descriptor has `"kind"` set to
`body`, `troop` or `equipment`, and its `"mesh"` must be a `.glb` file. Every descriptor uses `"schema": 2`; the
game refuses any other.

A recipe is a `.json` with no shape of its own. It says which parts to combine and how to fit weapons.
`modular/meks/atlas.json` (`"kind": "mek"`) points at the Atlas body and the equipment catalog, and lists mounting
preferences such as which hardpoint takes a hand-held PPC. The game reads the unit's real equipment list and uses
the recipe to place each piece.

The contents of `modular/`:

- `meks/`: Mek recipes, one per named chassis (`atlas.json`, `phoenix-hawk.json`, `locust.json` and so on), plus the
  generic `fallback-<layout>-<weight class>.json` recipes for biped, quad, tripod and air-Mek layouts. A Mek with no
  named recipe uses the fallback for its layout and weight class.
- `bodies/`: bare bodies for the named Meks, the fallback Meks, the named vehicles (`manticore`, `manticore-ii`)
  and the generic families (`family-hover`, `family-vtol`, `family-spheroid` and so on).
- `families/`: recipes for everything that is not a Mek or a trooper: vehicles, aircraft, naval units, ProtoMeks,
  static structures and squadrons. `manticore.json` is the named Manticore; most others are generic by movement
  type, such as `hover.json`.
- `equipment.json`: the equipment catalog. It maps MegaMek equipment, by internal name, to a weapon piece, and gives
  fallbacks by weapon family (laser, missile, ballistic and so on) for anything unmapped.
- `equipment/library/`: the weapon and equipment pieces, several hundred of them, named by a short hash such as
  `6a7da3263b8f45066e0b.glb`. Only the catalog says which is which. `equipment/` also holds three named reference
  pieces (`ppc`, `srm-6`, `searchlight`) and `equipment/round/`, round-bodied laser variants the catalog does not
  currently use.
- `troops/`: single figures, such as the infantry trooper `rifle-standing`, the jump trooper `jump-standing` and the
  battle armour suit `elemental-standing`. Kneeling, walking and jumping are animated from the standing figure.
- `transports/`: the vehicles of motorized and mechanized infantry (`motorized`, `tracked`, `wheeled`, `hover`).
- `infantry.json`, `battle-armor.json` and `battle-armor/`: formation recipes. The game draws one figure per
  surviving battle armour trooper, and up to six figures for a conventional platoon, some replaced by transports
  when the platoon is motorized or mechanized.
- `meeples/`: the formations of the All Meeples display, named by the `meeple` field of each formation recipe.
  `infantry.json` and `battle-armor.json` assemble rigid silhouette figures (`infantry-trooper`,
  `battle-armor-trooper`) and the `apc` and `buggy` transports, extruded from `images/units/Infantry/mechanized_apc.png`
  and `motorized_buggy.png`, with the same counts and layout as the 3D formations.
- `manifest.json`: the inventory the build writes. For each part it records triangles, vertices, size, a checksum,
  and a `lods` list with each level's group name and triangle count. It also records the budgets below.

The game finds a unit's recipe through the fourth field of `data/images/units/mekset.txt`, relative to
`data/models`:

```text
chassis "Atlas" "meks/Atlas.png" "units/modular/meks/atlas.json"
chassis "Manticore Heavy Tank" "vehicles/Manticore.png" "units/modular/families/manticore.json"
exact "default_medium" "defaults/default_medium.png" "units/modular/meks/fallback-biped-{weightClass}.json"
```

## Levels of detail

A unit far away on screen does not need full detail, so one GLB can hold up to three versions of a part: LOD0 (full
detail), LOD1 (simpler) and LOD2 (simplest). Each version sits under its own top-level group, named after the file.
`atlas.glb` contains one group, `atlas-lod0`. `phoenix-hawk.glb` contains `phoenix-hawk-lod0` (1,824 triangles) and
`phoenix-hawk-lod1` (954 triangles).

The rules the game enforces:

- Every level must be a group named `<file name>-lod0`, `-lod1` or `-lod2`. A GLB exported from Blender without these
  groups is refused, with a message asking you to name them.
- `-lod0` is required; LOD1 and LOD2 are optional. A missing level falls back to the next more detailed one.
- The groups are empty nodes with no offset, rotation or scale. Put the rig under them.
- Each level is a complete copy of the part with the same joint names, so animation drives every level the same
  way. A level is never borrowed from another unit: the Phoenix Hawk IIC has its own file and its own levels.

The game picks the level by on-screen size. A Mek switches to LOD1 below about 96 pixels tall; infantry and battle
armour below about 48. The selected unit, and the attacker and target of an attack being played back, stay at LOD0.
Vehicles and other families always draw LOD0 for now. LOD2 is being added to the renderer, with switch points of 32
pixels for units and 16 for infantry, so author it where you can but do not expect to see it in game yet. Suggested
LOD2 sizes: a Mek body 150 to 250 triangles, a weapon 10 to 30, a battle armour suit 40 to 60, an infantry figure 20
to 40.

## The triangle budget

The budget is for the whole unit as drawn: bare body plus every fitted weapon, at each level.

| Level | Whole-unit budget |
|---|---:|
| LOD0 | 5,000 triangles |
| LOD1 | 2,000 triangles |
| LOD2 | 500 triangles |

- Aim for a LOD0 body under about 4,000 triangles, leaving roughly 1,000 for weapons. The Atlas body is 767
  triangles; the Phoenix Hawk body is 1,824.
- The exporter refuses a bare body over its level's whole budget: 5,000 for LOD0, 2,000 for a `-lod1` export, 500
  for a `-lod2` export.
- A single weapon or equipment piece over 250 triangles prints a `Weapon review:` line during the build. Over 1,000
  the build fails.
- In the game, a unit whose real loadout goes over budget is still drawn in full. MegaMek writes a `[UnitBudget]`
  warning to `megamek.log` naming the body and splitting the count between body and weapons. Formations and
  squadrons are not checked.
- Each level of a part loads as one mesh with 16-bit indices, so it can hold at most 65,535 vertices, about 21,000
  flat-shaded triangles. That is a hard technical limit; the budget keeps you far below it.

The numbers live in `tools/unit_model_geometry.py` (`LOD_TRIANGLE_BUDGETS`), `tools/build_modular_unit_models.py`
(`EQUIPMENT_TRIANGLE_TARGET`, `EQUIPMENT_TRIANGLE_LIMIT`) and MegaMek's `UnitModelDescriptor.UNIT_TRIANGLE_BUDGETS`.

## Axes and materials

- Author in Python with +x right, +y forward and +z up. The GLB is standard glTF with Y up; the exporter converts on
  the way out and MegaMek converts back. Colours are authored as seen on screen and stored as linear colour.
- Materials are named by role: `paint` takes the unit's camouflage, `detail` keeps its own colour, and `bark` takes
  the shared bark texture. Other names are refused. The main 3D board reads glTF roughness/metallic factors,
  optional packed metallic-roughness maps (linear G/B), normal maps and occlusion maps (linear R), all on UV0.
  Its direct reflection uses GGX; ambient reflection approximates the sky and ground, without an environment map.
- Opaque and alpha-tested materials are supported; double-sided faces duplicate reversed geometry on import.
  Skins, animation clips, morph targets, external geometry buffers and blended materials are refused;
  the game animates the named joints itself.

`tools/model_surfaces.py` holds the reviewed selection and its material values. Atlas and Warhammer paint has
roughness 0.68 and metalness zero: a metal object covered in paint still reflects like paint. The `detail` role mixes bare metal,
rubber, glazing and other small parts, so it remains roughness one / metalness zero until that art has a mask or
separate surfaces. The generic GLB writer still defaults to roughness one / metalness zero for other callers.

The calibration covers the **Atlas and Warhammer bodies**: a complete rebuild applies that selection to all LODs
of the reviewed bodies. Other bodies, equipment, troops and vehicles keep the defaults; the camouflage role alone
does not identify a physical material (it can include clothing). These are artistic starting values, not
measured scans.

## Rebuilding

Everything in `modular/` is generated. Change the builders or recipes and rebuild; do not hand-edit the output.

1. From a MegaMek checkout, export the equipment catalog:
   `gradlew :megamek:exportEquipmentModelCatalog -PunitModelDataRoot=<this mm-data folder>`.
   It writes `.work/modular-models/equipment.json` here (without the property, into the `../mm-data` next to
   MegaMek).
2. From this repository's root, run `python tools/build_modular_unit_models.py`. Plain Python is enough. Use
   `--output <folder>` to write elsewhere and `--catalog <file>` to read another catalog. The build makes the Meks
   (recipes in `tools/unit-models/chassis.json`, builders in `tools/unit_mek_chassis.py`), the generic families,
   the named vehicles (`tools/unit-models/vehicles.json`, `tools/unit_vehicle_chassis.py`), troops, battle armour,
   transports and every equipment piece. Its last step, `tools/package_unit_lods.py`, packs each part's levels into
   one GLB and writes `manifest.json`. A full rebuild reproduces the committed Manticore and Manticore II exactly.
3. For a separate Mek LOD1 body, set `"bodyLod1": true` on the chassis in `chassis.json` and have its builder draw
   the simpler body. It is exported as `bodies/<id>-lod1` and packed into `bodies/<id>.glb`, as the Phoenix Hawk and
   Phoenix Hawk IIC show.
4. To see it in game, run `gradlew :megamek:stageDataFiles` in MegaMek. It copies from the `../mm-data` next to that
   checkout. In a worktree that may be a link to another mm-data checkout on a different branch, so stage and then
   copy your models over, or use checkouts on matching branches.

To reuse or replace a weapon model everywhere, map its equipment internal name in `tools/unit-models/weapons.json`
and rebuild. Retired equipment pieces are moved to `tools/unit-models/references/equipment-library/`, not deleted.

## Tools and guides

- [MODELLING_GUIDE.md](../../../tools/unit-models/MODELLING_GUIDE.md): the main specification, including
  proportions, joints, hardpoints, levels of detail and the budget.
- [NEW_CHASSIS_BRIEF.md](../../../tools/unit-models/NEW_CHASSIS_BRIEF.md): the brief for modelling a new chassis.
- [PRE_BUILD_CHECKLIST.md](../../../tools/unit-models/PRE_BUILD_CHECKLIST.md): what to check before a build.
- [UNIT_REVIEW_PROCESS.md](../../../tools/unit-models/UNIT_REVIEW_PROCESS.md): how a finished chassis is reviewed.
- `MODULAR_MODELS_PLAN.md`, `MODULAR_MODELS_PLAYBACK.md` and `MODULAR_MODELS_REVIEW_FIXES.md` in the same folder are
  historical records with older budgets and formats.
- In `tools/`: `render_modular_body.py` renders a body from its GLB, `render_fallback_catalog.py` draws contact
  sheets of the generic meshes in Blender, and `build_unit_review_gallery.py`, `render_weapon_chart.py` and
  `audit_unit_model_equipment.py` help review galleries, weapons and equipment coverage.

The old baked-model tools (`build_unit_models.ps1`, `build_unit_models.py`, `render_unit_variants.py`,
`validate_unit_models.py`) were removed on 2026-09-28. G3DJ is no longer written or read anywhere.

MegaMek's `docs/unit-models.md` explains how the game loads and assembles these files. The BattleTech Unit Viewer, a
separate tool outside this repository, reads the same GLBs and can build and deploy one chassis through this
repository's exporter.
