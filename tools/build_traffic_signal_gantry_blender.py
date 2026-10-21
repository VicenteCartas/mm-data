"""Blender-authored cantilever traffic signals, using the existing board GLB LOD kit.

The shoulder footing is the origin, Z is up, +Y faces the approaching driver,
and +X reaches over the incoming lane. Dimensions below are metres.
"""
import importlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_road_controls_blender as kit
importlib.reload(kit)

NAME = 'traffic-signal-gantry'
REACH = 4.0
BEAM_HEIGHT = 6.25
CURVE_RADIUS = .80
BASE_WIDTH = .42
HEAD_X = (2.00, 3.20)
HEAD_Z = 5.63
REPEATER_Z = 2.70


def tube(name, points, radii, sides, material):
    """Connected swept steel tube: smooth sides, flat end caps, no floating joints."""
    points = [Vector(point) for point in points]
    vertices = []
    for i, (point, radius) in enumerate(zip(points, radii)):
        tangent = (points[min(i + 1, len(points) - 1)] - points[max(0, i - 1)]).normalized()
        across = Vector((0, 1, 0))
        other = tangent.cross(across).normalized()
        for side in range(sides):
            angle = side * 2 * math.pi / sides
            vertices.append(point + radius * (across * math.cos(angle) + other * math.sin(angle)))
    faces = []
    for ring in range(len(points) - 1):
        for side in range(sides):
            a, b = ring * sides + side, ring * sides + (side + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    faces.extend((tuple(reversed(range(sides))), tuple(range((len(points) - 1) * sides, len(points) * sides))))
    obj = kit.polygon(name, vertices, faces, material)
    for face in obj.data.polygons[:-2]:
        face.use_smooth = True
    return obj


def mast(level, material):
    segments, sides = (8, 10) if level == 0 else (4, 6)
    points = [(0, 0, .045), (0, 0, BEAM_HEIGHT - CURVE_RADIUS)]
    for i in range(1, segments + 1):
        angle = math.pi - i / segments * math.pi / 2
        points.append((CURVE_RADIUS + CURVE_RADIUS * math.cos(angle), 0,
                       BEAM_HEIGHT - CURVE_RADIUS + CURVE_RADIUS * math.sin(angle)))
    points.append((REACH, 0, BEAM_HEIGHT))
    radii = [.110, .090] + [.090 - .012 * i / segments for i in range(1, segments + 1)] + [.070]
    return tube('tapered curved steel mast', points, radii, sides, material)


def gusset(angle, material):
    vertices = [(x, y, z) for y in (-.010, .010) for x, z in ((.075, .045), (.180, .045), (.075, .355))]
    obj = kit.polygon('base stiffening gusset', vertices,
                      [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)], material)
    obj.rotation_euler.z = angle
    return obj


def head(level, position, scale, mats):
    parts = (kit.signal_head_lod0 if level == 0 else kit.signal_head_lod1)(mats)
    transform = Matrix.Translation(position) @ Matrix.Scale(scale, 4) @ Matrix.Translation((0, 0, -2.73))
    bpy.context.view_layer.update()
    for obj in parts:
        obj.matrix_world = transform @ obj.matrix_world
    return parts


def gantry(level, mats):
    parts = [kit.box('anchored steel baseplate', (0, 0, .0225), (BASE_WIDTH, BASE_WIDTH, .045), mats['metal']),
             mast(level, mats['metal'])]
    if level == 0:
        for x in (-.155, .155):
            for y in (-.155, .155):
                parts.append(kit.cylinder('anchor washer', (x, y, .049), .031, .008, mats['metal']))
                parts.append(kit.cylinder('hex anchor nut and stud', (x, y, .078), .022, .058,
                                          mats['fasteners'], sides=6))
        parts.extend(gusset(i * math.pi / 2, mats['metal']) for i in range(4))
        parts.append(kit.box('mast service cover', (0, .109, .82), (.100, .025, .24), mats['fasteners']))
        seam = kit.cylinder('curved arm connection sleeve', (.86, 0, BEAM_HEIGHT), .097, .055, mats['fasteners'])
        seam.rotation_euler.y = math.pi / 2
        parts.append(seam)
    for x in HEAD_X:
        if level == 0:
            clamp = kit.cylinder('overhead split clamp', (x, 0, BEAM_HEIGHT), .105, .11, mats['fasteners'])
            clamp.rotation_euler.y = math.pi / 2
            parts.append(clamp)
            parts.append(kit.box('overhead clamp lug', (x, .112, 6.20), (.160, .050, .160), mats['fasteners']))
            for dx in (-.045, .045):
                parts.append(kit.cylinder('clamp fastening bolt', (x + dx, .147, 6.22), .015, .030,
                                          mats['metal'], sides=6, front=True))
        parts.append(kit.box('overhead mounting bracket', (x, .105, 6.12), (.065, .210, .260), mats['metal']))
        parts.extend(head(level, (x, .10, HEAD_Z), .85, mats))
    for z in (REPEATER_Z - .28, REPEATER_Z + .28):
        if level == 0:
            parts.append(kit.cylinder('repeater clamp band', (0, 0, z), .126, .065, mats['fasteners']))
        parts.append(kit.box('repeater mounting bracket', (0, .145, z), (.070, .150, .065), mats['metal']))
    parts.extend(head(level, (0, .26, REPEATER_Z), .75, mats))
    return parts


def render_preview(scene, levels, mats, comparison=False, suffix='preview'):
    for obj in levels[1]:
        obj.hide_render = not comparison
        obj.location.x += 4.65
    kit.box('preview ground', (0, 0, -.035), (200, 200, .07), mats['floor'])
    target = Vector((3.7 if comparison else 1.4, 0, 3.0))
    bpy.ops.object.camera_add(location=target + Vector((5, 15, 5)))
    camera = bpy.context.object
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 10.0 if comparison else 7.2
    scene.camera = camera
    for location, energy, size in [((2, 4, 10), 1900, 7), ((-4, -2, 6), 1450, 5)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy, light.data.shape, light.data.size = energy, 'DISK', size
        light.rotation_euler = (Vector((1, 0, 3)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('Traffic gantry preview world')
    world.use_nodes = True
    world.node_tree.nodes.get('Background').inputs['Color'].default_value = (.24, .26, .29, 1)
    world.node_tree.nodes.get('Background').inputs['Strength'].default_value = .6
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.render.resolution_x, scene.render.resolution_y = ((1800, 1300) if comparison else (1400, 1400))
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(kit.REVIEW / (NAME + '-' + suffix + '.png'))
    bpy.ops.render.render(write_still=True)


def render_connections(scene, far_objects):
    for obj in far_objects:
        obj.hide_render = True
    target = Vector((1.15, 0, 3.15))
    scene.camera.location = target + Vector((10, 7, 3))
    scene.camera.rotation_euler = (target - scene.camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera.data.ortho_scale = 7.1
    scene.render.resolution_x = scene.render.resolution_y = 1400
    scene.render.filepath = str(kit.REVIEW / (NAME + '-connections.png'))
    bpy.ops.render.render(write_still=True)


def main():
    old_scene = bpy.context.window.scene
    scene = bpy.data.scenes.new('Traffic signal gantry authoring')
    scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', 1
    bpy.context.window.scene = scene
    try:
        mats = {key: kit.material(key, colour, metallic, roughness) for key, colour, metallic, roughness in (
            ('metal', (.56, .60, .62), .65, .43), ('fasteners', (.30, .34, .36), .7, .43),
            ('housing', (.12, .135, .15), .1, .7), ('red', kit.RED_OFF, 0, .3),
            ('Amber', kit.AMBER_ON, 0, .4), ('green', (.025, .19, .075), 0, .4),
            ('floor', (.28, .30, .32), 0, .85))}
        levels = {}
        for level in (0, 1):
            collection = bpy.data.collections.new(f'Traffic signal gantry LOD{level}')
            scene.collection.children.link(collection)
            levels[level] = gantry(level, mats)
            for obj in levels[level]:
                for old_collection in list(obj.users_collection):
                    old_collection.objects.unlink(obj)
                collection.objects.link(obj)
        models = {level: kit.geometry(NAME, objects) for level, objects in levels.items()}
        counts = []
        for level, model in models.items():
            mesh = model['meshes'][0]
            triangles = sum(len(part['indices']) // 3 for part in mesh['parts'])
            assert triangles <= (2200, 450)[level], (level, triangles)
            counts.append({'node': f'{NAME}-lod{level}', 'triangles': triangles,
                           'vertices': len(mesh['vertices']) // 12,
                           'bounds': [[min(mesh['vertices'][axis::12]), max(mesh['vertices'][axis::12])]
                                      for axis in range(3)]})
        placement = {'units': 'model', 'front': '+Y', 'armDirection': '+X', 'base': 'Z=0',
                     'baseWidth': BASE_WIDTH * kit.MODEL_UNITS_PER_METRE,
                     'armReach': REACH * kit.MODEL_UNITS_PER_METRE,
                     'headX': [x * kit.MODEL_UNITS_PER_METRE for x in HEAD_X],
                     'headCentreZ': HEAD_Z * kit.MODEL_UNITS_PER_METRE,
                     'repeaterCentreZ': REPEATER_Z * kit.MODEL_UNITS_PER_METRE}
        path = kit.write_levels(NAME, models, 'tools/build_traffic_signal_gantry_blender.py',
                                extras={'mmRoadSignal': placement})
        report = {'file': str(path), 'lods': counts, 'bytes': path.stat().st_size,
                  'metres': {'base_width': BASE_WIDTH, 'reach': REACH, 'beam_height': BEAM_HEIGHT,
                             'head_x': HEAD_X, 'head_centre_z': HEAD_Z, 'repeater_z': REPEATER_Z}}
        (kit.REVIEW / (NAME + '-validation.json')).write_text(json.dumps(report, indent=2) + '\n')
        render_preview(scene, levels, mats, comparison=True)
        render_connections(scene, levels[1])
        return report
    finally:
        bpy.context.window.scene = old_scene


if __name__ == '__main__':
    result = main()
