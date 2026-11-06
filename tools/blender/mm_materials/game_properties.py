"""The mm* glTF extras the engine reads, as Blender controls.

A material's and a mesh's extras stay their custom properties, read and written through the properties below, so what
the panel shows is what the GLB gets. The file's colour slots and night lights live in the scene state from Open to Save.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       StringProperty)
import numpy as np

from .preview import build_preview

SLOTS = 4  # BoardDecoration.Colours.SLOTS
COLOUR_SLOT = '_COLOUR_SLOT'
SNOW_TEXTURES = (('baseColor', 'Base Colour'), ('normal', 'Normal'), ('occlusion', 'Occlusion'), ('emissive', 'Emission'))
FILE_KEYS = ('mmColourSlots', 'mmNightLights')
EMISSION = (('MATERIAL', 'From Material', "No mmEmission: what the .tres says, else always", 0),
            ('ALWAYS', 'Always', 'mmEmission always: on by day and by night, even if its .tres is night-only', 1),
            ('NIGHT', 'Night Only', 'mmEmission night: fades out in daylight', 2),
            ('OFF', 'Off', 'mmEmission off: no emission at all', 3))


def copies(material):
    """The material and its copies on the selected meshes: assigning makes one per object, and they must stay alike."""
    from . import export_name

    def identity(item):
        return re.sub(r'\.\d{3}$', '', export_name(item))
    found = {material}
    for obj in bpy.context.selected_objects:
        if obj.type == 'MESH':
            found.update(slot.material for slot in obj.material_slots
                         if slot.material and identity(slot.material) == identity(material))
    return found


def refresh(material):
    from . import textures_root
    if material.get('_mm_tres'):
        textures = textures_root(bpy.context)
        build_preview(material, textures / material['_mm_tres'], textures)


def store(material, key, value, preview=False):
    """Sets an extra on the material's copies; None removes it, so a switched-off property leaves no trace in the GLB."""
    for item in copies(material):
        if value is None:
            item.pop(key, None)
        else:
            item[key] = value
        if preview:
            refresh(item)


def flag(key, name, description, preview=False):
    def read(material):
        return material.get(key) is True  # The engine ignores anything but a real true.

    def write(material, value):
        store(material, key, True if value else None, preview)
    return BoolProperty(name=name, description=description, get=read, set=write)


def read_emission(material):
    return {'always': 1, 'night': 2, 'off': 3}.get(material.get('mmEmission'), 0)


def write_emission(material, value):
    store(material, 'mmEmission', {'ALWAYS': 'always', 'NIGHT': 'night', 'OFF': 'off'}.get(EMISSION[value][0]), True)


def principled(material):
    nodes = material.node_tree.nodes if material.use_nodes else ()
    return next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)


def read_glow(material):
    """The GLB's emissive factor: a library material keeps it apart from its preview, any other in its Principled inputs."""
    if material.get('_mm_tres'):
        return tuple(material.get('_mm_emission_factor', (0, 0, 0)))
    node = principled(material)
    if node is None:
        return (0, 0, 0)
    strength = node.inputs['Emission Strength'].default_value
    return tuple(channel * strength for channel in node.inputs['Emission Color'].default_value[:3])


def glow_settable(material):
    """An image driving the emission socket hides the factor in its shader nodes, out of this panel's reach."""
    node = principled(material)
    return bool(material.get('_mm_tres')) or (node is not None and not node.inputs['Emission Color'].is_linked)


def write_glow(material, value):
    colour = [round(float(channel), 6) for channel in value]
    for item in copies(material):
        if item.get('_mm_tres'):
            item['_mm_emission_factor'] = colour
            if any(colour):
                item['_mm_model_emission'] = True
            elif not item.get('_mm_emission_image'):
                item.pop('_mm_model_emission', None)
            refresh(item)
        elif (node := principled(item)) is not None:
            node.inputs['Emission Color'].default_value = (*colour, 1)
            node.inputs['Emission Strength'].default_value = 1


def snow(material):
    return material.get('mmSnow')


def snow_paths(material):
    return json.loads(material.get('_mm_snow_paths', '{}'))


def write_snow(material, value):
    for item in copies(material):
        if value and snow(item) is None:
            item['mmSnow'] = {'textures': {}}
        elif not value and snow(item) is not None:
            del item['mmSnow']
            item['_mm_snow_paths'] = '{}'


def write_snow_name(material, value):
    for item in copies(material):
        group = snow(item)
        if group is not None:
            if value:
                group['name'] = value
            else:
                group.pop('name', None)


def read_snow_scale(material):
    group = snow(material)
    value = group.get('colourScale') if group is not None else None
    return tuple(float(channel) for channel in value) if value is not None else (1.0, 1.0, 1.0)


def write_snow_scale(material, value):
    for item in copies(material):
        group = snow(item)
        if group is not None:
            if all(channel == 1 for channel in value):
                group.pop('colourScale', None)
            else:
                group['colourScale'] = [round(float(channel), 6) for channel in value]


def snow_texture(role, name):
    def read(material):
        return snow_paths(material).get(role, '')

    def write(material, value):
        for item in copies(material):
            paths = snow_paths(item)
            if value:
                paths[role] = str(Path(bpy.path.abspath(value)).resolve())
            else:
                paths.pop(role, None)
            item['_mm_snow_paths'] = json.dumps(paths)
    return StringProperty(name=name, subtype='FILE_PATH', description=f'The snow form\'s {name.lower()} image, under data/models',
                          get=read, set=write)


MATERIAL_PROPERTIES = {
    'mm_building_paint': flag('mmBuildingPaint', 'Building Tint', 'mmBuildingPaint: takes the colour chosen for the building'),
    'mm_paint_mask': flag('mmPaintMask', 'Paint Mask', 'mmPaintMask: this GLB\'s own image: its alpha marks what a colour '
                          'slot paints, it is not transparency'),
    'mm_emission': EnumProperty(name='Emission', description='When this material glows', items=EMISSION,
                                get=read_emission, set=write_emission),
    'mm_glow': FloatVectorProperty(
        name='Colour', description="emissiveFactor, linear RGB; black keeps a library material's own glow", size=3,
        subtype='COLOR', min=0, max=1, get=read_glow, set=write_glow),
    'mm_label': flag('mmLabel', 'Label', 'mmLabel: each quad is one character of the unit number, from the label atlas'),
    'mm_snow': BoolProperty(name='Snow Form', description='mmSnow: what this material changes in the winter form',
                            get=lambda material: snow(material) is not None, set=write_snow),
    'mm_snow_name': StringProperty(
        name='Material Name', description='The material\'s name in the winter form; empty keeps its name',
        get=lambda material: str((snow(material) or {}).get('name', '')) if snow(material) is not None else '',
        set=write_snow_name),
    'mm_snow_scale': FloatVectorProperty(
        name='Colour Scale', description='Multiplies the vertex colours in the winter form', size=3, min=0, soft_max=2,
        get=read_snow_scale, set=write_snow_scale),
    **{f'mm_snow_{role.lower()}': snow_texture(role, name) for role, name in SNOW_TEXTURES},
}


def read_part(obj):
    from . import export_name
    if obj.type != 'MESH' or obj.active_material is None:
        return ''
    return json.loads(obj.data.get('_mm_parts', '{}')).get(export_name(obj.active_material), {}).get('mmPart', '')


def write_part(obj, value):
    from . import export_name
    if obj.type != 'MESH' or obj.active_material is None:
        return
    parts = json.loads(obj.data.get('_mm_parts', '{}'))
    name = export_name(obj.active_material)
    extras = parts.setdefault(name, {})
    if value:
        extras['mmPart'] = value
    else:
        extras.pop('mmPart', None)
    if not extras:
        del parts[name]
    obj.data['_mm_parts'] = json.dumps(parts)


def linear(colour):
    """Exact sRGB decoding, as the engine's GpuColor.linear: independent of Blender's colour management."""
    srgb = np.asarray(colour, dtype=np.float64)
    return np.where(srgb <= .04045, srgb / 12.92, ((srgb + .055) / 1.055) ** 2.4)


def scene_meshes(scene):
    return {obj.data for obj in scene.objects if obj.type == 'MESH'}


def slot_values(mesh):
    attribute = mesh.attributes.get(COLOUR_SLOT)
    if attribute is None:
        return None
    values = np.empty(len(mesh.vertices), dtype=np.float32)
    attribute.data.foreach_get('value', values)
    return np.rint(values)


def colour_layer(mesh):
    """The mesh's vertex colours, white where it had none."""
    layer = mesh.color_attributes.active_color
    if layer is None:
        layer = mesh.color_attributes.new('Color', 'FLOAT_COLOR', 'CORNER')
        layer.data.foreach_set('color', np.ones(len(layer.data) * 4, dtype=np.float32))
        mesh.color_attributes.active_color = layer
        mesh.color_attributes.render_color_index = 0
    return layer


def paint(mesh, chosen, change):
    """Changes the linear RGB of the vertices flagged in chosen."""
    layer = colour_layer(mesh)
    values = np.empty(len(layer.data) * 4, dtype=np.float32)
    layer.data.foreach_get('color', values)
    values = values.reshape(-1, 4)
    if layer.domain == 'CORNER':
        vertices = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get('vertex_index', vertices)
        chosen = chosen[vertices]
    values[chosen, :3] = change(values[chosen, :3])
    layer.data.foreach_set('color', values.reshape(-1))
    mesh.update()


def sync_colours(scene):
    """A slot's vertices follow its default colour, keeping their shade (colour over default), as RigidGlb.recolour reads it."""
    for index, slot in enumerate(scene.mm_materials.colour_slots, 1):
        old, new = linear(slot.applied), linear(slot.colour)
        if (old == new).all():
            continue
        slot.applied = slot.colour
        for mesh in scene_meshes(scene):
            values = slot_values(mesh)
            if values is not None and (values == index).any():
                paint(mesh, values == index, lambda rgb: np.where(old > 1e-6, rgb / np.maximum(old, 1e-6), 1) * new)


def colour_changed(slot, context):
    # Edit Mode would overwrite mesh data on exit; Save and Assign catch up.
    if context.mode != 'EDIT_MESH':
        sync_colours(context.scene)


def hex_colour(colour):
    return '#' + ''.join(f'{round(channel * 255):02x}' for channel in colour)


def rgb(text):
    return [int(text[at:at + 2], 16) / 255 for at in (1, 3, 5)]


class MMColourPreset(bpy.types.PropertyGroup):
    label: StringProperty(name='Label')
    colour: FloatVectorProperty(name='Colour', size=3, subtype='COLOR_GAMMA', min=0, max=1, default=(1, 1, 1))


class MMColourSlot(bpy.types.PropertyGroup):
    colour: FloatVectorProperty(name='Default Colour', size=3, subtype='COLOR_GAMMA', min=0, max=1, default=(1, 1, 1),
                                update=colour_changed)
    applied: FloatVectorProperty(size=3, default=(1, 1, 1), options={'HIDDEN'})
    presets: CollectionProperty(type=MMColourPreset)


class MMNightLight(bpy.types.PropertyGroup):
    position: FloatVectorProperty(name='Position', size=3, subtype='TRANSLATION')
    colour: FloatVectorProperty(name='Colour', description='Linear RGB', size=3, subtype='COLOR', min=0, soft_max=1,
                                default=(1, 1, 1))
    power: FloatProperty(name='Power', min=.001, default=1)
    size: FloatProperty(name='Size', min=.001, default=40)


GROUPS = (MMColourPreset, MMColourSlot, MMNightLight)


def load_file_extras(state, extras):
    """The file's colour slots and night lights, into the state that edits them until file_extras writes them back."""
    state.colour_slots.clear()
    state.night_lights.clear()
    try:
        for entry in extras.get('mmColourSlots', []):
            slot = state.colour_slots.add()
            slot.name = entry['name']
            slot.applied = slot.colour = rgb(entry['colour'])
            for label, colour in entry['presets']:
                preset = slot.presets.add()
                preset.label, preset.colour = label, rgb(colour)
        for entry in extras.get('mmNightLights', []):
            light = state.night_lights.add()
            x, y, z = entry['position']  # glTF's Y up; the panel shows Blender's, which is the board's.
            light.position = (x, -z, y)
            light.colour, light.power, light.size = entry['color'], entry['power'], entry['size']
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'Invalid colour slots or night lights in this GLB: {error!r}') from error


def file_extras(state):
    extras = json.loads(state.root_extras or '{}')
    for key in FILE_KEYS:
        extras.pop(key, None)

    def rounded(values):
        return [round(float(value), 6) for value in values]
    if state.colour_slots:
        extras['mmColourSlots'] = [{'name': slot.name, 'colour': hex_colour(slot.colour),
                                    'presets': [[preset.label, hex_colour(preset.colour)] for preset in slot.presets]}
                                   for slot in state.colour_slots]
    if state.night_lights:
        extras['mmNightLights'] = [{'position': rounded((light.position[0], light.position[2], -light.position[1])),
                                    'color': rounded(light.colour), 'power': round(light.power, 6),
                                    'size': round(light.size, 6)} for light in state.night_lights]
    return extras


@contextmanager
def object_mode(context):
    """Edit Mode holds its own copy of the mesh: attributes are written from Object Mode."""
    edit = context.mode == 'EDIT_MESH'
    if edit:
        bpy.ops.object.mode_set(mode='OBJECT')
    try:
        yield edit
    finally:
        if edit:
            bpy.ops.object.mode_set(mode='EDIT')


class MM_OT_game_list(bpy.types.Operator):
    bl_idname = 'mm_materials.game_list'
    bl_label = 'Edit Game List'
    bl_description = 'Add or remove a colour slot, preset or night light'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    kind: EnumProperty(items=[('SLOT', 'Slot', ''), ('PRESET', 'Preset', ''), ('LIGHT', 'Light', '')])
    slot: IntProperty(description="A preset's slot, from 0")
    remove: IntProperty(default=-1, description='The item to remove, or -1 to add one')

    def execute(self, context):
        state = context.scene.mm_materials
        items = {'SLOT': state.colour_slots, 'LIGHT': state.night_lights}.get(self.kind)
        if items is None:
            items = state.colour_slots[self.slot].presets
        if self.remove >= 0:
            items.remove(self.remove)
            if self.kind == 'SLOT':
                with object_mode(context):
                    for mesh in scene_meshes(context.scene):
                        values = slot_values(mesh)
                        if values is not None:
                            values[values == self.remove + 1] = 0
                            values[values > self.remove + 1] -= 1
                            mesh.attributes[COLOUR_SLOT].data.foreach_set('value', values)
            return {'FINISHED'}
        if self.kind == 'SLOT' and len(items) >= SLOTS:
            self.report({'ERROR'}, f'At most {SLOTS} colour slots')
            return {'CANCELLED'}
        item = items.add()
        if self.kind == 'SLOT':
            item.name = f'Slot {len(items)}'
        elif self.kind == 'PRESET':
            item.label = 'Preset'
            item.colour = state.colour_slots[self.slot].colour
        else:
            item.position = context.scene.cursor.location
        return {'FINISHED'}


class MM_OT_colour_slot_assign(bpy.types.Operator):
    bl_idname = 'mm_materials.colour_slot_assign'
    bl_label = 'Assign Colour Slot'
    bl_description = 'Mark the selected vertices (all of the selected meshes in Object Mode) with this slot, in its default colour'
    bl_options = {'REGISTER', 'UNDO'}

    slot: IntProperty(min=0, max=SLOTS, description='The slot, from 1; 0 for none')

    def execute(self, context):
        from . import refresh_materials
        try:
            state = context.scene.mm_materials
            objects = list(context.objects_in_mode) if context.mode == 'EDIT_MESH' else context.selected_objects
            objects = [obj for obj in objects if obj.type == 'MESH']
            if not objects:
                raise ValueError('Select a mesh first')
            if any(obj.data.users > 1 for obj in objects):
                raise ValueError('Make linked meshes single-user before assigning colour slots')
            uncoloured = False
            with object_mode(context) as edit:
                sync_colours(context.scene)
                for obj in objects:
                    mesh = obj.data
                    chosen = np.ones(len(mesh.vertices), dtype=bool)
                    if edit:
                        mesh.vertices.foreach_get('select', chosen)
                    attribute = mesh.attributes.get(COLOUR_SLOT) or mesh.attributes.new(COLOUR_SLOT, 'FLOAT', 'POINT')
                    values = slot_values(mesh)
                    values[chosen] = self.slot
                    attribute.data.foreach_set('value', values)
                    if self.slot:
                        uncoloured |= mesh.color_attributes.active_color is None
                        default = linear(state.colour_slots[self.slot - 1].colour)
                        paint(mesh, chosen, lambda colours: default)
            if uncoloured:
                refresh_materials(context)  # The previews now multiply in vertex colours.
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_PT_game_properties(bpy.types.Panel):
    bl_label = 'Game Properties'
    bl_idname = 'MM_PT_game_properties'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MegaMek'
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return not context.scene.mm_asset_test.source_scene

    def draw(self, context):
        state = context.scene.mm_materials
        self.draw_material(context)
        self.draw_advanced(context, state)
        self.draw_slots(state)
        self.draw_lights(state)
        kept = [key for key in json.loads(state.root_extras or '{}') if key not in FILE_KEYS]
        if kept:
            self.layout.label(text='Kept, unused by the game: ' + ', '.join(kept))

    def draw_material(self, context):
        header, body = self.layout.panel('mm_game_material')
        header.label(text='Material')
        if not body:
            return
        obj = context.object
        if not obj or obj.type != 'MESH':
            body.label(text='Select a mesh.')
            return
        body.template_list('MATERIAL_UL_matslots', '', obj, 'material_slots', obj, 'active_material_index', rows=2)
        material = obj.active_material
        if material is None:
            body.label(text='This slot has no material.')
            return
        body.label(text='Copies on selected meshes follow.', icon='INFO')
        column = body.column(align=True)
        column.prop(material, 'mm_building_paint')
        if not material.get('_mm_tres'):
            column.prop(material, 'mm_paint_mask')
        elif material.get('_mm_paint_mask'):
            column.label(text='Its .tres makes the albedo alpha a paint mask.', icon='INFO')
        body.prop(material, 'mm_emission')
        if material.mm_emission != 'OFF':
            if glow_settable(material):
                body.prop(material, 'mm_glow')
            else:
                body.label(text='Its emission image sets the colour: edit it in the shader nodes.', icon='INFO')
        elif not material.get('_mm_tres'):
            body.label(text='The viewport still shows its glow; the game switches it off.', icon='INFO')

    def draw_advanced(self, context, state):
        header, body = self.layout.panel('mm_game_advanced', default_closed=True)
        header.label(text='Advanced')
        obj = context.object
        material = obj.active_material if obj and obj.type == 'MESH' else None
        if not body or material is None:
            return
        # GeneratedKit passes on the Material section, but not this.
        kit = Path(state.source).name.endswith('-pieces.glb')
        rigid = body.column(align=True)
        rigid.active = not kit
        rigid.prop(material, 'mm_label')
        if kit:
            rigid.label(text="Not read from a kit's pieces.", icon='INFO')
        body.prop(obj, 'mm_part')
        box = body.box()
        box.prop(material, 'mm_snow')
        group = snow(material)
        if group is not None:
            box.prop(material, 'mm_snow_name')
            for role, _ in SNOW_TEXTURES:
                box.prop(material, f'mm_snow_{role.lower()}')
            box.prop(material, 'mm_snow_scale')
            if group.get('colours') is not None:
                box.label(text=f"Per-vertex winter colours kept: {len(group['colours'])}")

    def draw_slots(self, state):
        header, body = self.layout.panel('mm_game_slots', default_closed=True)
        header.label(text=f'Colour Slots ({len(state.colour_slots)}/{SLOTS})')
        if not body:
            return
        for index, slot in enumerate(state.colour_slots):
            box = body.box()
            row = box.row(align=True)
            row.prop(slot, 'name', text='')
            row.prop(slot, 'colour', text='')
            operator = row.operator('mm_materials.game_list', text='', icon='X')
            operator.kind, operator.remove = 'SLOT', index
            box.operator('mm_materials.colour_slot_assign', text='Assign Selected', icon='BRUSH_DATA').slot = index + 1
            for at, preset in enumerate(slot.presets):
                row = box.row(align=True)
                row.prop(preset, 'label', text='')
                row.prop(preset, 'colour', text='')
                operator = row.operator('mm_materials.game_list', text='', icon='X')
                operator.kind, operator.slot, operator.remove = 'PRESET', index, at
            operator = box.operator('mm_materials.game_list', text='Add Preset', icon='ADD')
            operator.kind, operator.slot = 'PRESET', index
        row = body.row(align=True)
        add = row.row(align=True)
        add.enabled = len(state.colour_slots) < SLOTS
        add.operator('mm_materials.game_list', text='Add Slot', icon='ADD').kind = 'SLOT'
        row.operator('mm_materials.colour_slot_assign', text='Clear Selected', icon='X').slot = 0

    def draw_lights(self, state):
        header, body = self.layout.panel('mm_game_lights', default_closed=True)
        header.label(text=f'Night Lights ({len(state.night_lights)})')
        if not body:
            return
        for index, light in enumerate(state.night_lights):
            box = body.box()
            row = box.row(align=True)
            row.label(text=f'Light {index + 1}')
            row.prop(light, 'colour', text='')
            operator = row.operator('mm_materials.game_list', text='', icon='X')
            operator.kind, operator.remove = 'LIGHT', index
            box.prop(light, 'position', text='')
            row = box.row(align=True)
            row.prop(light, 'power')
            row.prop(light, 'size')
        body.operator('mm_materials.game_list', text='Add at 3D Cursor', icon='ADD').kind = 'LIGHT'


_classes = (MM_OT_game_list, MM_OT_colour_slot_assign, MM_PT_game_properties)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    for name, value in MATERIAL_PROPERTIES.items():
        setattr(bpy.types.Material, name, value)
    bpy.types.Object.mm_part = StringProperty(
        name='Part Name', description='mmPart: names this material\'s part of the mesh for the game; unique in a level of detail',
        get=read_part, set=write_part)


def unregister():
    del bpy.types.Object.mm_part
    for name in MATERIAL_PROPERTIES:
        delattr(bpy.types.Material, name)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
