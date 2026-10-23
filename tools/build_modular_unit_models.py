"""Export reusable schema-2 assets, without baking any loadout or troop-count combinations.

Python authors art only. Unit selection, attachment fitting and formation assembly belong to Java.
Run with Python (Blender's bundled Python also works); no bpy or Blender process is required.
"""
from package_unit_lods import package_unit_lods

import argparse
import json
import re
from pathlib import Path

from unit_infantry_shapes import (person, infantry_vehicle, TROOP_SCALE, BATTLE_ARMOR_SIZE, elemental, elemental_far,
                                  elemental_ii, elemental_ii_far)
from unit_model_geometry import Geometry, LOD_TRIANGLE_BUDGETS, sub
from unit_weapon_shapes import draw, rule_for
from unit_equipment_models import build_equipment
from unit_mek_models import build_meks, fallback_recipes
from unit_family_models import build_families, scale_geometry
from unit_vehicle_models import build_vehicles

ROOT = Path(__file__).resolve().parents[1]
# One weapon or equipment piece: over the target is printed for review, over the limit fails the build. The pieces
# on a unit share its level budget with the body (LOD_TRIANGLE_BUDGETS), so heavy pieces should be a deliberate choice.
EQUIPMENT_TRIANGLE_TARGET = 250
EQUIPMENT_TRIANGLE_LIMIT = 1000


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def archive_superseded_modules(output, assets):
    """Only generated hash-named files in the deployed library; never touch custom meshes or scratch exports."""
    if output.resolve() != (ROOT / 'data/models/units/modular').resolve():
        return
    live = {Path(key).name for key in assets if key.startswith('equipment/library/')}

    def references(value):
        if isinstance(value, dict):
            for child in value.values():
                references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)
        elif isinstance(value, str) and value.startswith('units/modular/equipment/library/'):
            live.add(Path(value).stem)

    # Explicit canonical mappings can reuse an earlier exported asset; the manifest alone does not list those.
    references(json.loads((output / 'equipment.json').read_text(encoding='utf-8')))
    library = (output / 'equipment/library').resolve()
    archive = (ROOT / 'tools/unit-models/references/equipment-library').resolve()
    archive.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in library.iterdir():
        if not re.fullmatch(r'[0-9a-f]{20}(?:-lod0)?\.(json|glb)', path.name) or path.stem.removesuffix('-lod0') in live:
            continue
        if not path.resolve().is_relative_to(library):
            raise ValueError('Generated module link escapes its library: '+str(path))
        target = archive / path.name
        if target.exists():
            if target.read_bytes() != path.read_bytes():
                raise ValueError('Reference archive already has different contents: '+str(target))
            path.unlink()
        else:
            path.rename(target)
        count += 1
    print(f'Archived {count} superseded generated equipment files')


def export_asset(geometry, output, key, kind, family, rig, joints, hardpoints=(), *, leg_bends=None, detail=None):
    """Writes one asset's mesh and descriptor. A key ending in -lod1 or -lod2 is that level of its component and is
    held to that level's budget; `detail='lod0'` marks a body that has a LOD1 of its own. The build finishes by
    packaging levels into one GLB per component."""
    if kind == 'equipment' and len(geometry.faces) > EQUIPMENT_TRIANGLE_LIMIT:
        raise ValueError(f'{key}: equipment has {len(geometry.faces)} triangles; maximum {EQUIPMENT_TRIANGLE_LIMIT}')
    if kind == 'equipment' and len(geometry.faces) > EQUIPMENT_TRIANGLE_TARGET:
        print(f'Weapon review: {key} has {len(geometry.faces)} triangles (target {EQUIPMENT_TRIANGLE_TARGET}); '
              f'it shares its unit\'s budget with the body')
    level_suffix = re.search(r'-lod([0-9]+)$', key)
    level = int(level_suffix.group(1)) if level_suffix else 0
    descriptor = output / (key+'.json')
    mesh = descriptor.with_name(descriptor.stem + ('' if re.search(r'-lod[0-9]+$', descriptor.stem) else '-lod0') + '.glb')
    limit = LOD_TRIANGLE_BUDGETS[min(level, len(LOD_TRIANGLE_BUDGETS) - 1)]
    stats = geometry.export(mesh, key, z_scale=1, bare_unit=kind != 'equipment', paint_uv=True, limit=limit)
    emitters = [{**emitter, 'position': sub(emitter['position'], geometry.pivots[emitter['node']])}
                for emitter in geometry.emitters]
    locations = {node: node.split('-')[0].split('@')[0] for node in geometry.pivots
                 if node.split('-')[0].split('@')[0] in ('HD', 'CT', 'LT', 'RT', 'LA', 'RA', 'LL', 'RL',
                                                       'CL', 'FLL', 'FRL', 'RLL', 'RRL')}
    write_json(descriptor, {
        'schema': 2, 'kind': kind, 'family': family, 'mesh': mesh.name,
        'bounds': {'min': [axis[0] for axis in stats['bounds']], 'max': [axis[1] for axis in stats['bounds']]},
        'rig': rig, 'joints': joints, 'locations': locations,
        'hardpoints': list(hardpoints), 'emitters': emitters,
        **({'legBends': leg_bends} if leg_bends else {}),
        **({'landingSupports': geometry.landing_supports} if geometry.landing_supports else {}),
        **({'detail': detail} if detail else {}),
    })
    return stats


def build(output, catalog):
    assets = {}
    recipes = json.loads((ROOT / 'tools/unit-models/chassis.json').read_text(encoding='utf-8'))['chassis']
    assets.update(build_meks(recipes+fallback_recipes(), output, export_asset, write_json))
    assets.update(build_families(output, export_asset, write_json))
    assets.update(build_vehicles(output, export_asset, write_json))

    joints = {role: node for role, node in [('root', 'root'), ('hips', 'hips'), ('torso', 'torso'), ('head', 'head')]}
    for side in ('left', 'right'):
        joints.update({side+'Arm': side+'Arm', side+'Forearm': side+'ArmForearm', side+'Leg': side+'Leg',
                       side+'Shin': side+'LegShin', side+'Foot': side+'LegFoot'})
    for kind, armored, jump in (('rifle', False, False), ('jump', False, True), ('battle-armor', True, False)):
        key = 'troops/'+kind+'-standing'
        troop = person('standing', armored=armored, jump=jump, modular=True)
        scale_geometry(troop, TROOP_SCALE*(BATTLE_ARMOR_SIZE if armored else 1))
        assets[key] = export_asset(troop, output, key, 'troop', 'battle-armor' if armored else 'infantry',
                                   'trooper-v1', joints)
    # Chassis-specific battle armour: its own suit on the trooper rig, named by mekset.txt's chassis line, plus a
    # simpler suit on the same rig that MegaMek shows while the squad is small on screen.
    bare, bare_far = (lambda: elemental(launchers=False)), (lambda: elemental_far(launchers=False))
    for name, suit, far_suit in (('elemental', elemental, elemental_far), ('elemental-no-launchers', bare, bare_far),
                                 ('elemental-ii', elemental_ii, elemental_ii_far)):
        key, far_key = 'troops/'+name+'-standing', 'troops/'+name+'-standing-lod1'
        near, far = suit(), far_suit()
        # Drawn beside the armoured figure's old 31.5-unit height; TROOP_SCALE keeps that proportion in metres.
        for figure in (near, far):
            scale_geometry(figure, TROOP_SCALE)
        assets[key] = export_asset(near, output, key, 'troop', 'battle-armor', 'trooper-v1', joints)
        assets[far_key] = export_asset(far, output, far_key, 'troop', 'battle-armor', 'trooper-v1', joints)
        write_json(output / ('battle-armor/'+name+'.json'), {'schema': 2, 'kind': 'formation', 'family': 'battle-armor',
                                                             'trooper': 'units/modular/'+key+'.json',
                                                             'trooperLod1': 'units/modular/'+far_key+'.json',
                                                             'meeple': 'units/modular/meeples/battle-armor.json'})
    for kind in ('motorized', 'tracked', 'wheeled', 'hover'):
        key = 'transports/'+kind
        transport = infantry_vehicle(kind, modular=True)
        scale_geometry(transport, TROOP_SCALE)
        joints = {'root': 'root', 'hull': 'vehicle', 'boarding': 'boarding', 'exit': 'boarding', 'cabin': 'cabin'}
        joints.update({node: node for node in transport.pivots if node.startswith('wheel-')})
        assets[key] = export_asset(transport, output, key, 'body', 'infantry-transport', 'transport-v1', joints)

    equipment = {item['internalName']: item for item in catalog['equipment']}
    for key, internal_name in (('ppc', 'PPC'), ('srm-6', 'SRM 6'), ('searchlight', 'Searchlight')):
        mount = dict(equipment[internal_name], location='mount', rear=False)
        rule = rule_for(mount)
        if rule is None:
            raise ValueError('Missing reference equipment recipe: '+internal_name)
        module = Geometry(modular=True)
        module.joint('mount', (0, 0, 0))
        draw(module, mount, rule, (0, 0, 0), 1)
        assets['equipment/'+key] = export_asset(module, output, 'equipment/'+key, 'equipment',
                                                mount['family'], 'module-v1', {'root': 'root', 'aim': 'mount'})
    assets.update(build_equipment(catalog, output, export_asset))
    package_unit_lods(output, assets)
    write_json(output / 'manifest.json', {'schema': 2, 'triangleBudgets': list(LOD_TRIANGLE_BUDGETS),
                                         'triangleBudgetScope': 'assembled unit per level: body plus fitted equipment',
                                         'equipmentTriangleTarget': EQUIPMENT_TRIANGLE_TARGET,
                                         'equipmentTriangleLimit': EQUIPMENT_TRIANGLE_LIMIT, 'assets': assets,
                                         'note': 'Reusable components; the Java renderer assembles formations/loadouts.'})
    for family, prefix in (('infantry', 'rifle'), ('battle-armor', 'battle-armor')):
        descriptor = {'schema': 2, 'kind': 'formation', 'family': family,
                      'trooper': 'units/modular/troops/'+prefix+'-standing.json'}
        if family == 'infantry':
            descriptor['jumpTrooper'] = 'units/modular/troops/jump-standing.json'
            descriptor['vehicles'] = {mode: 'units/modular/transports/'+kind+'.json' for mode, kind in
                                      (('INF_MOTORIZED', 'motorized'), ('TRACKED', 'tracked'),
                                       ('WHEELED', 'wheeled'), ('HOVER', 'hover'))}
        # The All Meeples display's formation; meeples/ holds hand-made GLBs this build does not write.
        descriptor['meeple'] = 'units/modular/meeples/'+family+'.json'
        write_json(output / (family+'.json'), descriptor)
    archive_superseded_modules(output, assets)
    print(f'Exported {len(assets)} independent assets; maximum {max(a["triangles"] for a in assets.values())} triangles')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/models/units/modular')
    parser.add_argument('--catalog', type=Path, default=ROOT / '.work/modular-models/equipment.json')
    args = parser.parse_args()
    build(args.output, json.loads(args.catalog.read_text(encoding='utf-8')))
