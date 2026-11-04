"""Two-hex, two-height authored slicing demo. Run build() through Blender MCP.

The low wing is two levels, the notched tower four. Hollow walls contain no
baked interior floors: the runtime makes those from the two closed helpers.
"""
import math

import bpy
from mathutils import Vector

import authored_examples as shared
from hpg_headquarters import mesh, prism, inset_outline

NAME = 'debug-authored'
SCENE = 'Debug authored building'
EAST = (83.125 / 2, 0)
NORTH = (83.125 / 4, 36)
LOW = [(-24, -29), (22, -29), (32, -10), EAST, NORTH,
       (-24, 29), (-32, 15), (-14, 15), (-14, -4), (-32, -4)]
HIGH = [EAST, (76, 0), (94, 18), (94, 50), (80, 65), (66, 65),
        (66, 48), (52, 48), (52, 65), (40, 65), (27, 44), NORTH]


def wing(name, outline, levels, colour):
    height = levels * 18
    inside = inset_outline(outline, 1.25)
    wall_vertices, wall_faces, band_vertices, band_faces = [], [], [], []
    outside_band = inset_outline(outline, -.025)
    for i, (a, b) in enumerate(zip(outline, outline[1:] + outline[:1])):
        joint = {a, b} == {EAST, NORTH}
        bottom = 36 if joint else 0
        if bottom >= height:
            continue  # The lower storeys connect across the shared hexside.
        j = (i + 1) % len(outline)
        # The roof slab closes the top. End the walls at its underside, avoiding
        # coincident coloured faces around the roof edge.
        start = len(wall_vertices)
        wall_vertices += [(*p, z) for z in (bottom, height - 1) for p in (a, b, inside[j], inside[i])]
        wall_faces += [tuple(start + v for v in face) for face in
                       ((0, 1, 5, 4), (2, 3, 7, 6), (3, 2, 1, 0))]
        # Painted height markers are flat faces just outside the wall.
        for z in range(bottom + 18, height, 18):
            start = len(band_vertices)
            band_vertices += [(*p, zz) for zz in (z - .65, z + .65) for p in (outside_band[i], outside_band[j])]
            band_faces.append((start, start + 1, start + 3, start + 2))
    mesh(name + ' walls', wall_vertices, wall_faces, shared.FLAT, colour)['building_paint'] = True
    mesh(name + ' storey markings', band_vertices, band_faces, shared.FLAT, (.23, .27, .31))
    prism(name + ' roof', outline, height - 1, height, shared.FLAT, (.58, .63, .67))
    prism('building_volume-' + name, outline, 0, height, shared.FLAT, (.3, .8, .7), helper=True)
    # Flat seven-segment digits: 10/8 triangles instead of tessellated extruded text.
    segments = {'a': (-3, 5, 6, 1.2), 'b': (2.4, .6, 1.2, 4.4), 'c': (2.4, -5, 1.2, 4.4),
                'd': (-3, -6.2, 6, 1.2), 'e': (-3.6, -5, 1.2, 4.4), 'f': (-3.6, .6, 1.2, 4.4),
                'g': (-3, -.6, 6, 1.2)}
    cx, cy = (1, -7) if levels == 2 else (68, 29)
    vertices, faces = [], []
    for segment in ('abged' if levels == 2 else 'fgbc'):
        x, y, w, h = segments[segment]; start = len(vertices)
        vertices += [(cx + px, cy + py, height + .03) for px, py in ((x, y), (x+w, y), (x+w, y+h), (x, y+h))]
        faces.append(tuple(range(start, start + 4)))
    mesh(name + ' height number', vertices, faces, shared.FLAT, (.95, .96, .98))


def review_scene():
    scene = bpy.context.scene
    # Reference grid is a source-scene aid; it is added after the GLB export.
    grid_material = shared.material(shared.FLAT, (.5, .55, .6))
    for cx, cy in ((0, 0), (83.125 * .75, 36)):
        curve = bpy.data.curves.new('Review hex', 'CURVE'); curve.dimensions = '3D'; curve.bevel_depth = .22
        spline = curve.splines.new('POLY'); spline.points.add(5); spline.use_cyclic_u = True
        for point, (dx, dy) in zip(spline.points, ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))):
            point.co = (cx + dx * 83.125 / 4, cy + dy * 36, .1, 1)
        obj = bpy.data.objects.new('Review hex', curve); scene.collection.objects.link(obj)
        obj.data.materials.append(grid_material)
    bpy.ops.mesh.primitive_plane_add(size=500, location=(30, 15, -.1))
    bpy.context.object.name = 'Review ground'
    bpy.context.object.data.materials.append(shared.material(shared.FLAT, (.16, .19, .22)))
    camera_data = bpy.data.cameras.new('Debug review camera')
    camera = bpy.data.objects.new('Debug review camera', camera_data); scene.collection.objects.link(camera)
    camera.location = (190, -210, 205)
    camera.rotation_euler = (Vector((30, 17, 28)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'; camera_data.ortho_scale = 225; scene.camera = camera
    sun_data = bpy.data.lights.new('Debug review sun', 'SUN'); sun_data.energy = 2
    sun = bpy.data.objects.new('Debug review sun', sun_data); scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(25), math.radians(-30), math.radians(-25))
    light_data = bpy.data.lights.new('Debug review fill', 'AREA'); light_data.energy = 160000; light_data.size = 160
    light = bpy.data.objects.new('Debug review fill', light_data); scene.collection.objects.link(light)
    light.location = (-100, -100, 170)
    light.rotation_euler = (Vector((30, 15, 25)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1100; scene.render.resolution_y = 900; scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'Standard'
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            view = area.spaces.active
            view.shading.type = 'MATERIAL'; view.region_3d.view_location = (30, 17, 28)
            view.region_3d.view_distance = 230; view.region_3d.view_perspective = 'ORTHO'


def build():
    shared.fresh(SCENE)
    wing('low-wing', LOW, 2, (.82, .35, .18))
    wing('tower', HIGH, 4, (.16, .48, .67))
    bpy.context.view_layer.update()
    visible = shared.export_model(shared.objects, NAME + '-lod0')
    helpers = shared.export_model(shared.volumes, NAME, helper=True)
    for obj, node in zip(shared.volumes, helpers['nodes']):
        node['id'] = obj.name
    asset = shared.DATA / 'models/buildings/debug' / (NAME + '.glb')
    shared.write_glb(asset, levels={0: visible}, groups={'building_volumes': helpers})
    review_scene()
    scene = bpy.context.scene
    scene.render.filepath = str(shared.SOURCE / (NAME + '-hero.png'))
    bpy.ops.render.render(write_still=True)
    camera = scene.camera
    camera.location = (31, 18, 250); camera.rotation_euler = (0, 0, 0); camera.data.ortho_scale = 175
    scene.render.filepath = str(shared.SOURCE / (NAME + '-plan.png'))
    bpy.ops.render.render(write_still=True)
    camera.location = (190, -210, 205)
    camera.rotation_euler = (Vector((30, 17, 28)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = 225
    bpy.data.libraries.write(str(shared.SOURCE / (NAME + '.blend')), {scene}, fake_user=True, path_remap='RELATIVE_ALL', compress=True)
    return {'asset': str(asset), 'volumes': len(helpers['nodes']), 'heights': [36, 72], 'bytes': asset.stat().st_size}


if __name__ == '__main__':
    print(build())
