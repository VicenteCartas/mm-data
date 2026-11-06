"""Blender --background --factory-startup --python-exit-code 1 --python tools/blender/test_game_properties.py

The Game Properties controls against the GLB JSON the engine reads, and every shipped file's lists through them.
"""
import addon_utils
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

import bpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
addon_utils.enable('mm_materials', default_set=True)
import mm_materials as addon
from mm_materials import game_properties as game

bpy.context.preferences.addons['mm_materials'].preferences.root = str(ROOT)
MODELS = ROOT / 'data/models'
STEEL = 'structures/common/painted-steel'


def meshes():
    return sorted((obj for obj in bpy.context.scene.objects if obj.type == 'MESH'), key=lambda obj: obj.name)


def select(objects):
    for obj in bpy.context.scene.objects:
        obj.select_set(obj in objects)
    bpy.context.view_layer.objects.active = objects[0]


def assign_faces(objects):
    select(objects)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.context.scene.mm_materials.material = STEEL + '.tres'
    assert bpy.ops.mm_materials.assign() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')


def alike(actual, expected):
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(alike(actual[key], expected[key]) for key in expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(alike(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, float):
        return math.isclose(actual, expected, abs_tol=1e-5)
    return actual == expected


# Every shipped file's colour slots and night lights come back as they were.
state = bpy.context.scene.mm_materials
files = 0
for path in MODELS.rglob('*.glb'):
    doc, _ = addon.glb.read_glb(path)
    addon.glb.check_part_names(doc)
    extras = doc.get('extras', {})
    if any(key in extras for key in game.FILE_KEYS):
        files += 1
        state.root_extras = json.dumps(extras)
        game.load_file_extras(state, extras)
        expected = {key: value for key, value in extras.items() if value != []}
        assert alike(game.file_extras(state), expected), path
state.colour_slots.clear()
state.night_lights.clear()
state.root_extras = '{}'
print('SHIPPED_LISTS_OK', files)

with tempfile.TemporaryDirectory(prefix='.mm-game-test-', dir=MODELS / 'buildings') as temp:
    temp = Path(temp)
    pieces = temp / 'test-pieces.glb'
    shutil.copy2(MODELS / 'buildings/building_hard/building_hard-pieces.glb', pieces)

    # A kit's pieces: Edit Mode makes one copy per object, and the flags reach them all.
    addon.open_glb(bpy.context, pieces)
    objects = meshes()
    assign_faces(objects)
    material = objects[0].active_material
    assert material.get('_mm_tres') == STEEL + '.tres' and material.mm_building_paint, 'Faces keep their tint'
    material.mm_emission = 'NIGHT'
    material.mm_glow = (.5, .25, .125)
    assert all(obj.active_material.mm_glow[0] == .5 for obj in objects)
    addon.save_glb(bpy.context, pieces)
    doc, _ = addon.glb.read_glb(pieces)
    assert all(item['extras'] == {'mmBuildingPaint': True, 'mmEmission': 'night'} and item['emissiveFactor'] == [.5, .25, .125]
               for item in doc['materials']), doc['materials']
    for choice, expected in (('ALWAYS', {'mmEmission': 'always'}), ('OFF', {'mmEmission': 'off'}),
                             ('NIGHT', {'mmEmission': 'night'}), ('MATERIAL', {})):
        material.mm_emission = choice
        assert material.mm_emission == choice
        assert all(obj.active_material.mm_emission == choice for obj in objects)
        addon.save_glb(bpy.context, pieces)
        saved = addon.glb.read_glb(pieces)[0]['materials'][0]
        extras = saved['extras']
        assert {key: extras[key] for key in extras if key != 'mmBuildingPaint'} == expected, extras
        assert saved['emissiveFactor'] == [.5, .25, .125], 'Every mode keeps its colour, so switching back restores it'
    material.mm_glow = (0, 0, 0)
    addon.save_glb(bpy.context, pieces)
    assert all('emissiveFactor' not in item for item in addon.glb.read_glb(pieces)[0]['materials']), 'Black keeps its own glow'
    material['mmEmission'] = 'not-a-mode'
    try:
        addon.save_glb(bpy.context, pieces)
        raise AssertionError('An unknown mmEmission saved')
    except ValueError as error:
        assert 'mmEmission must be always, night or off' in str(error)
    material.pop('mmEmission')
    print('MATERIAL_FLAGS_OK')

    # A kit's material is the one its albedo belongs to, whatever it is called; without one, Save refuses.
    material.name = 'renamed in blender'
    addon.save_glb(bpy.context, pieces)
    doc, _ = addon.glb.read_glb(pieces)
    assert 'renamed in blender' in [item['name'] for item in doc['materials']], doc['materials']
    plain = bpy.data.materials.new('no image')
    obj = objects[0]
    used = obj.material_slots[obj.active_material_index]
    used.material, kept = plain, used.material
    try:
        addon.save_glb(bpy.context, temp / 'plain-pieces.glb')
        raise AssertionError('A kit piece without a library image saved')
    except ValueError as error:
        assert 'library materials only' in str(error)
    used.material = kept
    print('KIT_MATERIALS_OK')

    # A rigid GLB: the rest, file lists included, and they come back on Open.
    rigid = temp / 'rigid.glb'
    albedo = MODELS / f'board/textures/{STEEL}_albedo.png'
    obj, other = objects[0], objects[1]
    select([obj])
    material = obj.active_material
    material.mm_label = True
    obj.mm_part = 'hull'
    material.mm_snow = True
    material.mm_snow_name = 'hull-snow'
    material.mm_snow_basecolor = str(albedo)
    material.mm_snow_scale = (1.25, 1, 1.5)
    for kind, count in (('SLOT', 2), ('LIGHT', 1)):
        for _ in range(count):
            assert bpy.ops.mm_materials.game_list(kind=kind) == {'FINISHED'}
    state = bpy.context.scene.mm_materials
    assert bpy.ops.mm_materials.game_list(kind='PRESET', slot=1) == {'FINISHED'}
    state.colour_slots[0].name, state.colour_slots[0].colour = 'Coat', (.25, .5, 1)
    state.colour_slots[1].name, state.colour_slots[1].colour = 'Trim', (1, .5, 0)
    state.colour_slots[1].presets[0].label = 'Orange'
    state.colour_slots[1].presets[0].colour = (1, .5, 0)
    state.night_lights[0].position = (1, 2, 3)
    state.night_lights[0].power = 2
    assert bpy.ops.mm_materials.colour_slot_assign(slot=1) == {'FINISHED'}
    select([other])
    assert bpy.ops.mm_materials.colour_slot_assign(slot=2) == {'FINISHED'}
    assert set(game.slot_values(other.data)) == {2}
    # A changed default keeps the vertices' shade (their ratio to it); here, its exact value.
    state.colour_slots[1].colour = (.5, .5, .5)
    grey = float(game.linear(.5))
    layer = other.data.color_attributes.active_color
    assert math.isclose(layer.data[0].color[1], grey, abs_tol=1e-5), layer.data[0].color[:]
    addon.save_glb(bpy.context, rigid)
    doc, binary = addon.glb.read_glb(rigid)
    assert alike(doc['extras']['mmColourSlots'], [
        {'name': 'Coat', 'colour': '#4080ff', 'presets': []},
        {'name': 'Trim', 'colour': '#808080', 'presets': [['Orange', '#ff8000']]}]), doc['extras']
    assert alike(doc['extras']['mmNightLights'],
                 [{'position': [1.0, 3.0, -2.0], 'color': [1.0, 1.0, 1.0], 'power': 2.0, 'size': 40.0}]), doc['extras']
    labelled = [item for item in doc['materials'] if item.get('extras', {}).get('mmLabel')]
    assert len(labelled) == 1
    variant = labelled[0]['extras']['mmSnow']
    assert variant['name'] == 'hull-snow' and variant['colourScale'] == [1.25, 1, 1.5]
    assert addon.glb.image_path(rigid, variant['textures']['baseColor']) == albedo.resolve()
    named = [primitive for mesh in doc['meshes'] for primitive in mesh['primitives']
             if primitive.get('extras', {}).get('mmPart') == 'hull']
    assert len(named) == 1
    accessors = {doc['accessors'][primitive['attributes']['_COLOUR_SLOT']]['componentType']
                 for mesh in doc['meshes'] for primitive in mesh['primitives'] if '_COLOUR_SLOT' in primitive['attributes']}
    assert accessors == {5126}, accessors

    addon.open_glb(bpy.context, rigid)
    state = bpy.context.scene.mm_materials
    assert [slot.name for slot in state.colour_slots] == ['Coat', 'Trim']
    assert game.hex_colour(state.colour_slots[1].presets[0].colour) == '#ff8000'
    assert alike(list(state.night_lights[0].position), [1.0, 2.0, 3.0])
    objects = meshes()
    painted = next(obj for obj in objects if obj.active_material and obj.active_material.mm_label)
    select([painted])
    material = painted.active_material
    assert painted.mm_part == 'hull' and material.mm_snow_name == 'hull-snow'
    assert Path(material.mm_snow_basecolor) == albedo.resolve() and tuple(material.mm_snow_scale) == (1.25, 1, 1.5)
    print('RIGID_AND_FILE_LISTS_OK')

    # Removing a slot renumbers the vertices of the ones after it.
    trim = next(obj for obj in objects if game.slot_values(obj.data) is not None and 2 in game.slot_values(obj.data))
    coat = next(obj for obj in objects if game.slot_values(obj.data) is not None and 1 in game.slot_values(obj.data))
    assert bpy.ops.mm_materials.game_list(kind='SLOT', remove=0) == {'FINISHED'}
    assert set(game.slot_values(trim.data)) == {1} and set(game.slot_values(coat.data)) == {0}

    # A repeated part name is refused at Save, where the game would draw a marked box.
    other = next(obj for obj in objects if obj is not painted and obj.active_material)
    other.mm_part = 'hull'
    try:
        addon.save_glb(bpy.context, temp / 'twice.glb')
        raise AssertionError('A repeated part saved')
    except ValueError as error:
        assert 'Part names must be unique' in str(error)
    other.mm_part = ''
    print('SLOT_REMOVAL_AND_PARTS_OK')
