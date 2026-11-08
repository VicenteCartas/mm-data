"""Author the low-poly road-control GLBs in Blender, without changing its current scene.

Run with Blender's Python (including Blender MCP): exec(compile(Path(__file__).read_text(),
str(__file__), 'exec')). Creates a separate authoring scene, exports through the shared
board GLB writer and renders a preview. All dimensions here are physical metres; GLBs
use the established 2.8 model pixels per metre. Both fronts face +Y, bases stand at Z=0.
Call main(('stop-sign',)) to refresh only the STOP asset from road-stop-face.png.
"""
import json
import math
import struct
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import linear, write_glb

OUTPUT = ROOT / 'data/models/board/scenery/road'
REVIEW = ROOT / 'tools/board-models'
MODEL_UNITS_PER_METRE = 2.8
AMBER_ON = (1.0, .62, .04)
RED_OFF = (.22, .025, .02)


def material(name, colour, metallic=0, roughness=.65):
    value = bpy.data.materials.new('Road controls ' + name)
    value.diffuse_color = (*[linear(v) for v in colour], 1)
    value.use_nodes = True
    shader = value.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = value.diffuse_color
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Roughness'].default_value = roughness
    if name == 'Amber':
        shader.inputs['Emission Color'].default_value = value.diffuse_color
        shader.inputs['Emission Strength'].default_value = 1
    value['board_id'] = name
    value['display_colour'] = colour
    value['metallic'] = metallic
    value['roughness'] = roughness
    return value


def set_material(obj, name, value):
    obj.name = name
    obj.data.materials.append(value)
    return obj


def box(name, centre, size, value):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre)
    obj = bpy.context.object
    obj.scale = size
    return set_material(obj, name, value)


def polygon(name, vertices, faces, value):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return set_material(obj, name, value)


def cylinder(name, centre, radius, depth, value, sides=8, front=False):
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=radius, depth=depth,
                                      end_fill_type='NGON', location=centre)
    obj = bpy.context.object
    if front:
        obj.rotation_euler.x = math.pi / 2
    return set_material(obj, name, value)


def visor(name, z, value):
    arc = [(-.174, -.035), (-.174, .10), (-.115, .17),
           (.115, .17), (.174, .10), (.174, -.035)]
    vertices = [(x, y, z + h) for y in (.135, .265) for x, h in arc]
    faces = []
    for i in range(5):
        face = (i, i + 1, i + 7, i + 6)
        faces.extend((face, tuple(reversed(face))))
    return polygon(name, vertices, faces, value)


def detailed_pole(parts, height, mats):
    parts.extend((box('baseplate', (0, 0, .025), (.28, .28, .05), mats['metal']),
                  cylinder('pole', (0, 0, height / 2 + .05), .05, height, mats['metal']),
                  cylinder('base collar', (0, 0, .115), .073, .13, mats['housing'])))


def traffic_signal_lod0(mats):
    parts = []
    detailed_pole(parts, 2.35, mats)
    parts.extend(signal_head_lod0(mats))
    return parts


def signal_head_lod0(mats):
    parts = []
    parts.append(box('signal housing', (0, .015, 2.73), (.44, .24, 1.14), mats['housing']))
    parts.append(box('signal backplate', (0, -.11, 2.73), (.50, .028, 1.20), mats['housing']))
    for name, height in (('red', 3.08), ('Amber', 2.73), ('green', 2.38)):
        parts.append(cylinder(name + ' lens rim', (0, .145, height), .151, .03,
                              mats['housing'], sides=12, front=True))
        parts.append(cylinder(name + ' lens', (0, .166, height), .126, .016,
                              mats[name], sides=12, front=True))
        parts.append(visor(name + ' visor', height, mats['housing']))
    return parts


def traffic_signal_lod1(mats):
    return [box('signal pole', (0, 0, 1.175), (.10, .10, 2.35), mats['metal']), *signal_head_lod1(mats)]


def signal_head_lod1(mats):
    parts = [box('signal housing', (0, .015, 2.73), (.44, .24, 1.14), mats['housing'])]
    for name, height in (('red', 3.08), ('Amber', 2.73), ('green', 2.38)):
        vertices = [(math.cos(i * math.pi / 3) * .126, .137,
                     height + math.sin(i * math.pi / 3) * .126) for i in range(6)]
        parts.append(polygon(name + ' lens', vertices, [tuple(reversed(range(6)))], mats[name]))
    return parts


def stop_face_texture():
    """The user-maintained artwork is a required input, never generated or overwritten."""
    path = REVIEW / 'road-stop-face.png'
    if not path.is_file():
        raise FileNotFoundError(f'Required STOP artwork: {path}')
    return path


def stop_sign_lod0(mats):
    parts = []
    detailed_pole(parts, 2.08, mats)
    parts.extend(stop_plate(mats, mats['white']))
    return parts


def stop_sign_lod1(mats):
    return [box('stop pole', (0, 0, 1.04), (.10, .10, 2.08), mats['metal']),
            *stop_plate(mats, mats['metal'])]


def stop_plate(mats, rim_material):
    """Both LODs share one octagonal face and identical artwork UV coordinates."""
    centre_z, radius = 2.13, .455
    outline = [(math.cos(math.pi / 8 + i * math.pi / 4),
                math.sin(math.pi / 8 + i * math.pi / 4)) for i in range(8)]
    vertices = [(x * radius, y, centre_z + z * radius) for y in (.045, .095) for x, z in outline]
    faces = [tuple(range(8))]
    faces.extend((i, i + 8, (i + 1) % 8 + 8, (i + 1) % 8) for i in range(8))
    parts = [polygon('sign sides and back', vertices, faces, rim_material)]
    face = polygon('STOP face', vertices[8:], [tuple(reversed(range(8)))], mats['stop face'])
    uv = face.data.uv_layers.new(name='UVMap')
    for loop in face.data.loops:
        x, y, z = face.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = (.5 - x / (2 * radius), .5 + (z - centre_z) / (2 * radius))
    parts.append(face)
    return parts


def geometry(name, objects):
    bpy.context.view_layer.update()
    vertices, grouped_indices, materials = [], {}, {}
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        value = mesh.materials[0]
        material_id = value['board_id']
        materials[material_id] = {'id': material_id, 'diffuse': list(value['display_colour']),
                                  'metallic': value['metallic'], 'roughness': value['roughness']}
        if 'texture_file' in value:
            texture = Path(value['texture_file'])
            materials[material_id]['textures'] = [{'id': material_id, 'type': 'DIFFUSE',
                'filename': texture.name, 'data': texture.read_bytes(), 'wrapS': 33071, 'wrapT': 33071}]
        indices = []
        normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
        for triangle in mesh.loop_triangles:
            for index, loop_index in zip(triangle.vertices, triangle.loops):
                source_normal = (mesh.corner_normals[loop_index].vector
                                 if mesh.polygons[triangle.polygon_index].use_smooth else triangle.normal)
                normal = (normal_matrix @ source_normal).normalized()
                position = obj.matrix_world @ mesh.vertices[index].co
                indices.append(len(vertices) // 12)
                uv = mesh.uv_layers.active.data[loop_index].uv if mesh.uv_layers.active else (0, 1)
                vertices.extend((*[v * MODEL_UNITS_PER_METRE for v in position], *normal, 1, 1, 1, 1, uv[0], 1 - uv[1]))
        grouped_indices.setdefault(material_id, []).extend(indices)
    parts = [{'id': name + '/' + key, 'type': 'TRIANGLES', 'indices': indices}
             for key, indices in grouped_indices.items()]
    references = [{'meshpartid': name + '/' + key, 'materialid': key} for key in grouped_indices]
    model = {'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                          'vertices': vertices, 'parts': parts}],
             'nodes': [{'id': name, 'parts': references}], 'materials': list(materials.values())}
    return model


def export(name, objects_by_level):
    models = {level: geometry(name, objects) for level, objects in objects_by_level.items()}
    counts = []
    for level, model in models.items():
        mesh = model['meshes'][0]
        triangles = sum(len(part['indices']) // 3 for part in mesh['parts'])
        expected = {'traffic-signal': (416, 36), 'stop-sign': (96, 40)}[name][level]
        assert triangles == expected, (name, level, triangles)
        counts.append({'node': f'{name}-lod{level}', 'triangles': triangles,
                       'vertices': len(mesh['vertices']) // 12, 'height': max(mesh['vertices'][2::12])})
    path = write_levels(name, models)
    return {'file': str(path), 'lods': counts, 'bytes': path.stat().st_size}


def write_levels(name, models):
    """Shared native LOD packaging for pole and gantry signal variants."""
    path = OUTPUT / (name + '.glb')
    write_glb(path, levels=models)
    if any(material['id'] == 'Amber' for model in models.values() for material in model['materials']):
        # The shared rigid writer has no emissive-material input. Keep the standard
        # glTF emission on this one lamp, without changing its neutral white vertices.
        data = path.read_bytes()
        json_length = struct.unpack_from('<I', data, 12)[0]
        document = json.loads(data[20:20 + json_length])
        lamp = next(value for value in document['materials'] if value['name'] == 'Amber')
        lamp['emissiveFactor'] = [linear(v) for v in AMBER_ON]
        encoded = json.dumps(document, separators=(',', ':'), allow_nan=False).encode('utf-8')
        encoded += b' ' * (-len(encoded) % 4)
        binary_chunk = data[20 + json_length:]
        path.write_bytes(struct.pack('<III', 0x46546c67, 2, 20 + len(encoded) + len(binary_chunk))
                         + struct.pack('<II', len(encoded), 0x4e4f534a) + encoded + binary_chunk)
    return path


def render_preview(scene, assets, mats):
    stops_only = set(assets) == {'stop-sign'}
    for level in (0, 1):
        if 'traffic-signal' in assets:
            for obj in assets['traffic-signal'][level]:
                obj.location.x += 2.4 - 3.2 * level
        if 'stop-sign' in assets:
            for obj in assets['stop-sign'][level]:
                obj.location.x += .65 - 1.3 * level if stops_only else .8 - 3.2 * level
    box('preview floor', (0, 0, -.04), (200, 200, .08), mats['floor'])
    bpy.ops.object.camera_add(location=(1, 12, 3.5) if stops_only else (4, 18, 7))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0, 0, 2.12 if stops_only else 1.6)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 2.5 if stops_only else 7.3
    scene.camera = camera
    for location, energy, size in [((1, 4, 7), 950, 5), ((-4, 0, 4), 650, 4)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = energy, 'DISK', size
        light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('Road controls preview world')
    world.use_nodes = True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value = (.25, .25, .25, 1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value = .5
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.render.resolution_x, scene.render.resolution_y = 1600, 950
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(REVIEW / ('stop-sign-preview.png' if stops_only else 'road-controls-preview.png'))
    bpy.ops.render.render(write_still=True)


def main(names=('traffic-signal', 'stop-sign')):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)
    old_scene = bpy.context.window.scene
    scene = bpy.data.scenes.new('Road controls authoring')
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    bpy.context.window.scene = scene
    try:
        mats = {key: material(key, colour, metallic, roughness) for key, colour, metallic, roughness in (
            ('metal', (.53, .56, .58), .55, .5), ('housing', (.12, .135, .15), .1, .7),
            ('red', RED_OFF, 0, .3), ('Amber', AMBER_ON, 0, .4),
            ('green', (.025, .19, .075), 0, .4), ('stop face', (1, 1, 1), 0, .65),
            ('white', (.9, .92, .9), .1, .55),
            ('floor', (.27, .29, .30), 0, .8))}
        texture = stop_face_texture()
        face = mats['stop face']
        face['texture_file'] = str(texture)
        node = face.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(texture), check_existing=False)
        face.node_tree.links.new(node.outputs['Color'], face.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
        builders = {'traffic-signal': (traffic_signal_lod0, traffic_signal_lod1),
                    'stop-sign': (stop_sign_lod0, stop_sign_lod1)}
        assets = {name: {} for name in names}
        for level in (0, 1):
            collection = bpy.data.collections.new(f'Road controls LOD{level}')
            scene.collection.children.link(collection)
            for name in assets:
                assets[name][level] = builders[name][level](mats)
                for obj in assets[name][level]:
                    for old_collection in list(obj.users_collection):
                        old_collection.objects.unlink(obj)
                    collection.objects.link(obj)
        report = [export(name, levels) for name, levels in assets.items()]
        render_preview(scene, assets, mats)
        report_path = REVIEW / 'road-controls-validation.json'
        previous = json.loads(report_path.read_text()) if report_path.is_file() else []
        by_file = {entry['file']: entry for entry in previous}
        by_file.update({entry['file']: entry for entry in report})
        report_path.write_text(json.dumps(list(by_file.values()), indent=2) + '\n')
        return report
    finally:
        bpy.context.window.scene = old_scene


if __name__ == '__main__':
    result = {'assets': main()}
