"""Blender preview nodes. Never write material definitions or texture pixels."""
from pathlib import Path
import json

import bpy
from mathutils import Color

from .tres import read_material


def linear_rgba(colour):
    """Godot resource RGB is sRGB; alpha and glTF factors are already linear."""
    return (*Color(colour[:3]).from_srgb_to_scene_linear(), colour[3])


def build_preview(material, path, textures):
    spec = read_material(path, textures)  # Validate before replacing any nodes.
    images = {}
    for key in ('albedo', 'normal', 'roughness_map', 'metallic_map', 'ao_map', 'emission', 'sss'):
        file = spec.get(key)
        if file:
            image = bpy.data.images.load(str(file), check_existing=True)
            image.colorspace_settings.name = 'sRGB' if key in ('albedo', 'emission') else 'Non-Color'
            image.reload()
            images[key] = image
    # A GLB may combine a shared board albedo with its own lamp emission.
    model_emission = material.get('_mm_model_emission')
    if model_emission:
        images.pop('emission', None)
        if material.get('_mm_emission_image'):
            images['emission'] = material['_mm_emission_image']
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (700, 150)
    principled = tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (400, 150)
    tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    sampler = json.loads(material.get('_mm_sampler', '{}'))
    nodes = {}

    def texture(role, location):
        if role not in images:
            return None
        image = images[role]
        if image.name in nodes:
            return nodes[image.name]
        node = tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.label = role.replace('_map', '').title()
        node.location = location
        node.extension = 'EXTEND' if sampler.get('wrapS') == sampler.get('wrapT') == 33071 else 'REPEAT'
        nodes[image.name] = node
        return node

    def multiply(socket, factor, location):
        node = tree.nodes.new('ShaderNodeMath')
        node.operation = 'MULTIPLY'
        node.location = location
        node.inputs[1].default_value = factor
        tree.links.new(socket, node.inputs[0])
        return node.outputs[0]

    def mix(a, b, operation, location):
        node = tree.nodes.new('ShaderNodeMix')
        node.data_type = 'RGBA'
        node.blend_type = operation
        node.inputs[0].default_value = 1
        node.location = location
        for socket, value in zip(node.inputs[6:8], (a, b)):
            if isinstance(value, (tuple, list)):
                socket.default_value = value
            else:
                tree.links.new(value, socket)
        return node.outputs[2]

    albedo = texture('albedo', (-900, 600))
    tint = linear_rgba(spec['tint'])
    color = mix(albedo.outputs['Color'], tint, 'MULTIPLY', (-400, 600))
    original = json.loads(material.get('_mm_surface', '{}'))
    if original.get('baseColorFactor', [1, 1, 1, 1]) != [1, 1, 1, 1]:
        color = mix(color, original['baseColorFactor'], 'MULTIPLY', (-200, 750))
    vertex = tree.nodes.new('ShaderNodeVertexColor')
    vertex.label = 'Mesh vertex colours (white when absent)'
    vertex.location = (-400, 400)
    color = mix(color, vertex.outputs['Color'], 'MULTIPLY', (0, 600))
    tree.links.new(color, principled.inputs['Base Color'])
    material.diffuse_color = tint
    material.roughness = max(0, min(1, spec['roughness']))
    material.metallic = max(0, min(1, spec['metallic']))
    for i, role in enumerate(('roughness', 'metallic', 'ao')):
        node = texture(role + '_map', (-900, 100 - i * 250))
        if role != 'ao':
            principled.inputs[role.title()].default_value = spec[role]
        if node is None:
            continue
        channel = spec[role + '_channel']
        if channel == 3:
            value = node.outputs['Alpha']
        elif channel == 4:
            gray = tree.nodes.new('ShaderNodeRGBToBW')
            tree.links.new(node.outputs['Color'], gray.inputs[0])
            value = gray.outputs[0]
        else:
            split = tree.nodes.new('ShaderNodeSeparateColor')
            split.mode = 'RGB'
            split.location = (-550, 100 - i * 180)
            tree.links.new(node.outputs['Color'], split.inputs[0])
            value = split.outputs[channel]
        if role == 'ao':
            # Keep AO available for inspection; multiplying albedo would bake lighting into pigment.
            node.label = 'ORM / AO (AO is not a Principled input)'
        else:
            value = multiply(value, spec[role], (-150, 100 - i * 180))
            tree.links.new(value, principled.inputs[role.title()])
    normal = texture('normal', (-900, -700))
    if normal:
        node = tree.nodes.new('ShaderNodeNormalMap')
        node.location = (-150, -500)
        node.inputs['Strength'].default_value = spec['normal_scale']
        tree.links.new(normal.outputs['Color'], node.inputs['Color'])
        tree.links.new(node.outputs['Normal'], principled.inputs['Normal'])
    emission = texture('emission', (-900, -1000))
    emission_color = tuple(material['_mm_emission_factor']) + (1,) if model_emission else linear_rgba(spec['emission_color'])
    if emission:
        emission_color = mix(emission.outputs['Color'], emission_color,
                             'MULTIPLY' if model_emission or spec['emission_operator'] else 'ADD', (-150, -800))
        tree.links.new(emission_color, principled.inputs['Emission Color'])
    else:
        principled.inputs['Emission Color'].default_value = emission_color
    principled.inputs['Emission Strength'].default_value = 1 if model_emission else spec['emission_energy']
    sss = texture('sss', (-900, -1300))
    principled.inputs['Subsurface Weight'].default_value = spec['sss_strength']
    if sss:
        tree.links.new(multiply(sss.outputs['Color'], spec['sss_strength'], (-150, -1100)),
                       principled.inputs['Subsurface Weight'])
    cutout = original.get('alphaMode', 'MASK' if spec['transparent'] else 'OPAQUE') == 'MASK'
    if material.get('mmPaintMask'):
        cutout = False
    if cutout:
        mask = tree.nodes.new('ShaderNodeMath')
        mask.operation = 'GREATER_THAN'
        mask.inputs[1].default_value = original.get('alphaCutoff', spec['alpha_cutoff'])
        mask.location = (100, 300)
        tree.links.new(albedo.outputs['Alpha'], mask.inputs[0])
        tree.links.new(mask.outputs[0], principled.inputs['Alpha'])
    material.use_backface_culling = not original.get('doubleSided', spec['double_sided'])
    material['_mm_tres'] = Path(path).relative_to(textures).as_posix()
    return spec


def show_materials(context):
    if context.screen:
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
