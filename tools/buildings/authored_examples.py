"""Shared authored-building material/export helpers and the HPG entry point.

Run: blender --background --factory-startup --python tools/buildings/authored_examples.py
Uses the shared board materials and rigid GLB writer. The building_volumes group is
authoring data, not a visible LOD. Civic buildings use civic_buildings.py.
"""
import math
import json
import types
import sys
from pathlib import Path

import bpy
from mathutils import Vector

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import display, linear, write_glb
import building_lod
import weathering
# Use this checkout's shared material implementation even when Blender has an
# older installed add-on named mm_materials in sys.modules.
package = types.ModuleType('mm_building_materials')
package.__path__ = [str(TOOLS / 'blender/mm_materials')]
sys.modules.setdefault(package.__name__, package)
from mm_building_materials.tres import read_material
from mm_building_materials.preview import build_preview

DATA = TOOLS.parent / 'data'
DEST = DATA / 'models/buildings/authored'
SOURCE = TOOLS / 'buildings/authored'
TEXTURES = DATA / 'models/board/textures'
DEST.mkdir(parents=True, exist_ok=True)
SOURCE.mkdir(parents=True, exist_ok=True)

CREAM = (.93, .92, .85)
TEAL = (.36, .62, .65)
DARK = (.34, .39, .42)
METAL = (.52, .56, .57)
GLASS = (.16, .34, .43)
AMBER = (.95, .63, .22)
PAINT = 'structures/common/weathered-paint'
CONCRETE = 'structures/common/cast-concrete'
STEEL = 'structures/common/satin-steel'
ROOF = 'structures/buildings/fortress-roof'
FLAT = 'structures/buildings/debug-panels'
objects = []
volumes = []
role = ''
materials = {}


def material(key, colour):
    identity = key, colour
    if identity in materials:
        return materials[identity]
    # Authoring pigments are sRGB, as in write_glb; Blender shader inputs are linear.
    pigment = (*map(linear, colour), 1)
    mat = bpy.data.materials.new(key + '-' + str(len(materials)))
    mat.diffuse_color = pigment
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = pigment
    bsdf.inputs['Roughness'].default_value = .68
    bsdf.inputs['Metallic'].default_value = .55 if key == STEEL else .12
    if colour == AMBER:
        bsdf.inputs['Emission Color'].default_value = pigment
        bsdf.inputs['Emission Strength'].default_value = .35
    if key != FLAT:
        mat['_mm_surface'] = json.dumps({'baseColorFactor': pigment})
        build_preview(mat, TEXTURES / (key + '.tres'), TEXTURES, vertex_colors=False)
    materials[identity] = mat
    return mat


def finish(obj, key, colour, detail=False, helper=False):
    obj['board_material'] = key
    obj['pigment'] = colour
    obj['module'] = role
    obj['detail'] = detail
    obj.data.materials.append(material(key, colour))
    (volumes if helper else objects).append(obj)
    if helper:
        obj.display_type = 'WIRE'
        obj.hide_render = True
    return obj


def emissive(obj, colour, night=False):
    """Separate untintable lamp colour, shared by the live preview and GLB exporter."""
    assert not obj.get('building_paint', False), 'Lamp surfaces must not inherit building tint'
    colour = tuple(colour)
    obj['building_emission'] = colour
    obj['building_night_emission'] = night
    key = obj['board_material'], tuple(obj['pigment']), colour, night
    if key not in materials:
        mat = material(key[0], key[1]).copy()
        mat.name += ' lamp'
        factor = tuple(linear(c) for c in colour)
        mat['_mm_model_emission'] = True
        mat['_mm_emission_factor'] = factor
        mat['_mm_night_emission'] = night
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Emission Color'].default_value = (*factor, 1)
        bsdf.inputs['Emission Strength'].default_value = 0 if night else 1
        materials[key] = mat
    obj.data.materials[0] = materials[key]
    return obj


def emission_off(obj):
    """Keep the shared glass finish, but make this surface permanently dark."""
    obj['building_emission_off'] = True
    source = obj.data.materials[0]
    key = ('emission-off', source.name)
    if key not in materials:
        mat = source.copy()
        mat.name += ' emission off'
        mat['mmEmission'] = 'off'
        mat.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value = 0
        materials[key] = mat
    obj.data.materials[0] = materials[key]
    return obj


def box(name, center, size, key=PAINT, colour=CREAM, bevel=.35, detail=False, helper=False):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel and not helper:
        mod = obj.modifiers.new('Machined edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
    return finish(obj, key, colour, detail, helper)


def cylinder(name, a, b, radius, key=STEEL, colour=METAL, vertices=12, detail=False):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=(b-a).length, location=(a+b)*.5)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (b-a).to_track_quat('Z', 'Y').to_euler()
    return finish(obj, key, colour, detail)


def volume(name, center, size):
    return box(name, center, size, FLAT, (.3, .8, .7), bevel=0, helper=True)


def shell(name, x, y, w, d, bottom, height, accent=TEAL, roof=True, windows=True):
    """Hollow external walls, with framed windows and independent armor belts."""
    z = bottom + height
    wall = 1.3
    for sign in (-1, 1):
        box(name + '-facade', (x, y + sign*(d-wall)/2, bottom+height/2), (w, wall, height), CONCRETE, CREAM, .2)['building_paint'] = True
        box(name + '-flank', (x + sign*(w-wall)/2, y, bottom+height/2), (wall, d-2*wall, height), CONCRETE, CREAM, .2)['building_paint'] = True
    floors = max(1, round(height/18))
    for level in range(floors):
        zz = bottom + level*18
        for sign in (-1, 1):
            box(name+'-belt', (x, y+sign*d/2, zz+1), (w+1.4, 1.5, 2), PAINT, DARK, .25)
            box(name+'-belt-side', (x+sign*w/2, y, zz+1), (1.5, d, 2), PAINT, DARK, .25)
            if windows:
                for xx in (-w*.27, w*.27):
                    box(name+'-window-frame', (x+xx, y+sign*(d/2+.32), zz+10), (w*.23, .9, 5), PAINT, DARK, 0)
                    box(name+'-window', (x+xx, y+sign*(d/2+.83), zz+10.2), (w*.20, .18, 3.2), FLAT, GLASS, .12)
                for yy in (-d*.27, d*.27):
                    box(name+'-side-window', (x+sign*(w/2+.2), y+yy, zz+10), (.4, d*.20, 4), FLAT, GLASS, .12)
        box(name+'-accent', (x-w*.08, y-d/2-.65, zz+10), (w*.12, .55, 13), PAINT, accent, .2)['building_paint'] = True
    for xx in (-w/2+1.2, w/2-1.2):
        for yy in (-d/2+1.2, d/2-1.2):
            box(name+'-corner', (x+xx, y+yy, bottom+height/2), (3, 3, height), PAINT, accent, .45)
    # Sloping armor shoulders and ribbed service panels give the envelope a military scale.
    for sign in (-1, 1):
        for xx in (-w*.35, w*.35):
            box(name+'-buttress', (x+xx, y+sign*(d/2+.9), bottom+4.5), (4.2, 3.4, 9), PAINT, accent, 1.4)
        for level in range(floors):
            zz = bottom+level*18
            box(name+'-service-inset', (x+w*.06, y+sign*(d/2+.7), zz+5.1), (w*.21, .6, 4.7), PAINT, DARK, 0)
            for k in range(3):
                box(name+'-service-rib', (x+w*.06, y+sign*(d/2+1.1), zz+3.8+k*1.1), (w*.17, .35, .45), STEEL, METAL, 0, True)
            box(name+'-status-light', (x-w*.33, y+sign*(d/2+.9), zz+15), (2.6, .35, .55), FLAT, AMBER, 0, True)
    if roof:
        box(name+'-roof', (x, y, z-.5), (w, d, 1), ROOF, (.65, .66, .65), .25)
        for sign in (-1, 1):
            box(name+'-roof-rim', (x, y+sign*(d/2-.9), z+.5), (w, 1.8, 1), PAINT, DARK, .2)
            box(name+'-roof-rim', (x+sign*(w/2-.9), y, z+.5), (1.8, d, 1), PAINT, DARK, .2)


def door(x, y, bottom, width=10):
    box('recessed-entry', (x, y-.7, bottom+7), (width+3, 1.6, 14), PAINT, DARK, .7)
    box('armored-door', (x, y-1.6, bottom+6.6), (width, .4, 12), STEEL, METAL, .3)
    box('entry-light', (x, y-2, bottom+13.5), (width*.7, .4, .65), FLAT, AMBER, .1)
    box('door-seam', (x, y-1.9, bottom+6.6), (.2, .1, 11), FLAT, DARK, 0, True)


def dish(name, center, radius, tilt=(0, 0, 0)):
    before = len(objects)
    rings, sectors = 6, 40
    verts, faces = [], []
    for ring in range(rings+1):
        r = radius * ring/rings
        for k in range(sectors):
            a = 2*math.pi*k/sectors
            verts.append((r*math.cos(a), r*math.sin(a), radius*.27*(r/radius)**2))
    for ring in range(rings):
        for k in range(sectors):
            a = ring*sectors+k
            b = ring*sectors+(k+1)%sectors
            faces.append((a, a+sectors, b+sectors, b))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    finish(obj, STEEL, (.79, .78, .71))
    # Give the reflector a proper back, retaining its shallow, concave front.
    solid = obj.modifiers.new('Reflector thickness', 'SOLIDIFY')
    solid.thickness = .8
    for k in range(16):
        a, b = 2*math.pi*k/16, 2*math.pi*(k+1)/16
        cylinder('dish-rim', (radius*math.cos(a), radius*math.sin(a), radius*.27),
                 (radius*math.cos(b), radius*math.sin(b), radius*.27), radius*.018, PAINT, DARK, 8)
        if k%2 == 0:
            for j in range(3):
                r0, r1 = radius*j/3, radius*(j+1)/3
                cylinder('reflector-rib', (r0*math.cos(a), r0*math.sin(a), radius*.27*(r0/radius)**2+.6),
                         (r1*math.cos(a), r1*math.sin(a), radius*.27*(r1/radius)**2+.6), radius*.008, STEEL, METAL, 6, True)
    for k in range(3):
        a = 2*math.pi*k/3
        cylinder('feed-arm', (radius*.82*math.cos(a), radius*.82*math.sin(a), radius*.20),
                 (0, 0, radius*.8), radius*.035, PAINT, DARK, 10)
    cylinder('feed-horn', (0, 0, radius*.4), (0, 0, radius*.8), radius*.065, STEEL, METAL, 16)
    from mathutils import Euler, Matrix
    frame = Matrix.Translation(Vector(center)) @ Euler(tuple(math.radians(a) for a in tilt)).to_matrix().to_4x4()
    for item in objects[before:]:
        item.matrix_world = frame @ item.matrix_world


def project_uvs(obj):
    """One projection per face, never per smooth corner; retain authored UVs."""
    if obj.data.uv_layers.active:
        return
    uv = obj.data.uv_layers.new(name='UVMap')
    normal_matrix = obj.matrix_world.to_3x3().inverted().transposed()
    for face in obj.data.polygons:
        normal = normal_matrix @ face.normal
        axis = max(range(3), key=lambda i: abs(normal[i]))
        cylindrical = obj.get('uv_projection') == 'cylinder' and len(face.vertices) == 4
        angles = [math.atan2(obj.data.vertices[i].co.y, obj.data.vertices[i].co.x) / math.tau % 1 for i in face.vertices]
        for li in face.loop_indices:
            co = obj.data.vertices[obj.data.loops[li].vertex_index].co
            if cylindrical:
                u = math.atan2(co.y, co.x) / math.tau % 1
                if max(angles)-min(angles) > .5 and u < .5:
                    u += 1
                uv.data[li].uv = (u * math.tau * math.hypot(co.x, co.y)/18, co.z/18)
                continue
            if obj.get('uv_projection') == 'cylinder':
                uv.data[li].uv = (co.x/18, co.y/18)
                continue
            if obj.get('uv_projection') == 'planar':
                local_axis = max(range(3), key=lambda i: abs(face.normal[i]))
                uv.data[li].uv = (co.y/18, co.z/18) if local_axis == 0 else (co.x/18, co.z/18) if local_axis == 1 else (co.x/18, co.y/18)
                continue
            co = obj.matrix_world @ co
            uv.data[li].uv = (co.y/18, co.z/18) if axis == 0 else (co.x/18, co.z/18) if axis == 1 else (co.x/18, co.y/18)


def material_id(key, paint, emission, night=False, off=False):
    suffix = '#emission-' + '-'.join(format(c, '.6g') for c in emission) if any(emission) else ''
    return key + ('#paint' if paint else '') + suffix + ('#night' if night else '') + ('#emission-off' if off else '')


CONCRETE_FINISHES = {'structures/common/cast-concrete', 'structures/common/concrete-panels', 'structures/buildings/fortress-concrete'}
# How rundown each building's concrete is on export (weathering.py), and the heights that shed soot onto the walls
# below them. The habitat builds its grime with its walls instead.
CONCRETE_WEATHER = {
    'civic-citadel': (1.15, (54, 252)),
    'civic-church': (1, (18, 36, 54)),
    'civic-arena': (1, (34,)),
    'civic-tower': (1.15, ()),
}


def export_model(items, label, level=0, helper=False, exact=False):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    groups = {}
    for obj in items:
        if level and obj['detail']:
            continue
        groups.setdefault(obj.name if helper else obj['module'], []).append(obj)
    modules = []
    for index, (module, members) in enumerate(groups.items()):
        if helper:
            module = members[0]['module']
        name = ('building_volume-'+str(index) + ('-'+module if module else '-whole')) if helper else label+'-'+(module or 'shell')
        vertices, parts, dedup = [], {}, {}
        for obj in members:
            if not helper:
                project_uvs(obj)
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            matrix = obj.matrix_world
            normal_matrix = matrix.to_3x3().inverted().transposed()
            emission = tuple(obj.get('building_emission', (0, 0, 0))) if not helper else (0, 0, 0)
            night = bool(obj.get('building_night_emission', False)) and not helper
            off = bool(obj.get('building_emission_off', False)) and not helper
            key = (obj['board_material'], bool(obj.get('building_paint', False)) and not helper, emission, night, off)
            pigment = list(obj['pigment'])
            weather = mesh.color_attributes.get('weather') if not helper else None
            indices = parts.setdefault(key, [])
            for tri in mesh.loop_triangles:
                for li in tri.loops:
                    vi = mesh.loops[li].vertex_index
                    co = matrix @ mesh.vertices[vi].co
                    # Optional per-vertex grime (linear grey) darkens the object's pigment.
                    colour = [c*display(weather.data[vi].color[0]) for c in pigment] if weather else pigment
                    normal = (normal_matrix @ mesh.corner_normals[li].vector).normalized()
                    if mesh.uv_layers.active and not helper:
                        u, v = mesh.uv_layers.active.data[li].uv
                        uv = (u, 1-v)  # Blender bottom-left UV origin -> glTF top-left.
                    else:
                        axis = max(range(3), key=lambda i: abs(normal[i]))
                        uv = (co.y/18, co.z/18) if axis == 0 else (co.x/18, co.z/18) if axis == 1 else (co.x/18, co.y/18)
                    vertex = (*co, *normal, *colour, 1, *uv)
                    vk = tuple(round(v, 5) for v in vertex)
                    if vk not in dedup:
                        dedup[vk] = len(vertices)//12
                        vertices.extend(vertex)
                    indices.append(dedup[vk])
            evaluated.to_mesh_clear()
        modules.append((name, vertices, parts))
    cell = 0
    if level and not exact:
        modules, cell = building_lod.simplify(modules, level, lambda key: building_lod.is_lit(material_id(*key)))
    building = label.split('-lod')[0]
    meshes, nodes, used = [], [], set()
    for name, vertices, parts in modules:
        used.update(parts)
        if not helper and building in CONCRETE_WEATHER:
            amount, ledges = CONCRETE_WEATHER[building]
            selected = [p for k, p in parts.items() if k[0] in CONCRETE_FINISHES]
            if level == 2:
                weathering.average_weather(vertices, selected, amount, display)
            else:
                # A far level's stains are as coarse as its merged geometry.
                weathering.weather_vertices(vertices, selected, [p for k, p in parts.items() if k[0] not in CONCRETE_FINISHES],
                                            amount, ledges, display, *((6*cell, 30*cell) if level else ()))
        mesh_parts, node_parts = [], []
        for i, (key, indices) in enumerate(parts.items()):
            part = name+'-'+str(i)
            mesh_parts.append({'id':part, 'type':'TRIANGLES', 'indices':indices})
            node_parts.append({'meshpartid':part, 'materialid':material_id(*key)})
        meshes.append({'attributes':['POSITION','NORMAL','COLOR','TEXCOORD0'], 'vertices':vertices, 'parts':mesh_parts})
        nodes.append({'id':name, 'parts':node_parts})
    mats = []
    for key, paint, emission, night, off in sorted(used):
        # All sliced and unsliced views use exactly the same shared board finishes.
        path = TEXTURES/(key+'.tres')
        import re
        # FLAT keeps the GLB's own factors: <name>_albedo.png would make it the board material of that name.
        albedo = 'debug-white.png' if key == FLAT else re.search(r'path="([^"]+)"', path.read_text()).group(1)
        filename = '../../board/textures/'+str((Path(key).parent/albedo).as_posix())
        mat = {'id':material_id(key, paint, emission, night, off), 'diffuse':[1,1,1], 'roughness':.7, 'metallic':.1,
               'textures':[{'type':'DIFFUSE','filename':filename}]}
        if any(emission):
            assert not paint, 'Lamp surfaces must not inherit building tint'
            mat['emissive'] = list(emission)
        if paint:
            mat['extras'] = {'mmBuildingPaint': True}
        if night:
            assert any(emission), 'Night emission needs an emissive colour'
            mat.setdefault('extras', {})['mmEmission'] = 'night'
        if off:
            mat.setdefault('extras', {})['mmEmission'] = 'off'
        if key != FLAT:
            spec = read_material(path, TEXTURES)
            mat.update(roughness=spec['roughness'], metallic=spec['metallic'])
            if key.endswith('-cutout'):
                mat.update(alphaTest=.5, doubleSided=True)
            for kind, image in [('NORMAL', spec['normal']), ('AMBIENT', spec['ao_map'])]:
                if image:
                    mat['textures'].append({'type':kind, 'filename':'../../board/textures/'+image.relative_to(TEXTURES).as_posix()})
            # Managed finishes store glTF's G=roughness/B=metallic ORM layout.
            if spec['roughness_map'] and (spec['roughness_map'] == spec['metallic_map']
                                         or key == 'structures/common/steel'
                                         or (spec['metallic'] == 0 and spec['metallic_map'] is None
                                             and spec['roughness_channel'] == 1)):
                # Steel's ORM has B=1 throughout; its constant metallic factor
                # therefore survives reuse of the existing roughness-only map.
                # For nonmetallic finishes, factor0 makes B immaterial; retain G.
                assert spec['roughness_channel'] == 1
                assert spec['metallic_map'] is None or spec['metallic_channel'] == 2
                mat['textures'].append({'type':'METALLIC_ROUGHNESS', 'filename':'../../board/textures/'+spec['roughness_map'].relative_to(TEXTURES).as_posix()})
            if spec['emission'] and not any(emission):
                # Shared window maps already isolate illuminated pixels.
                mat['emissive'] = [1, 1, 1]
                mat['textures'].append({'type':'EMISSIVE',
                    'filename':'../../board/textures/'+spec['emission'].relative_to(TEXTURES).as_posix()})
        mats.append(mat)
    return {'meshes':meshes, 'nodes':nodes, 'materials':mats}


def temporary(build):
    """What build adds to the scene for far levels only, kept out of the other levels: shapes a grid would shred."""
    start = len(objects)
    build()
    added = objects[start:]
    del objects[start:]
    bpy.context.view_layer.update()
    return added


def discard(items):
    for obj in items:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(data)


def together(*models):
    """One level out of models exported apart."""
    materials = {m['id']: m for model in models for m in model['materials']}
    return {'meshes': [m for model in models for m in model['meshes']], 'nodes': [n for model in models for n in model['nodes']],
            'materials': list(materials.values())}


def save_asset(name):
    bpy.context.view_layer.update()
    near = export_model(objects, name+'-lod0')
    far = export_model(objects, name+'-lod1', level=1)
    data = export_model(volumes, name, helper=True)
    write_glb(DEST/(name+'.glb'), levels={0:near, 1:far}, groups={'building_volumes':data})
    for obj in objects:
        if obj['module'] == 'floor1':
            obj.hide_render = True
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE/(name+'.blend')))
    render(name)
    print(name, 'vertices', sum(len(m['vertices'])//12 for m in near['meshes']), 'GLB bytes', (DEST/(name+'.glb')).stat().st_size)


def render(name):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.world.color = (.26, .26, .26)
    bpy.ops.object.camera_add(location=(255,-330,245))
    camera = bpy.context.object
    camera.rotation_euler = (Vector((0,0,47))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 285
    scene.camera = camera
    for location, energy, size in [((40,-140,260),240000,180),((-180,20,130),110000,130),((80,160,180),180000,120)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = 'DISK'
        light.data.size = size
        light.rotation_euler = (Vector((0,0,35))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.mesh.primitive_plane_add(size=2000, location=(0,0,-.3))
    plane = bpy.context.object
    plane.data.materials.append(material(FLAT, (.12,.15,.17)))
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(SOURCE/(name+'.png'))
    bpy.ops.render.render(write_still=True)


def fresh(name):
    global objects, volumes, role, materials
    old = bpy.data.scenes.get(name)
    scene = bpy.data.scenes.new(name + '.new' if old else name)
    bpy.context.window.scene = scene
    if old:
        for obj in list(old.objects):
            if len(obj.users_scene) == 1:
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(old)
        scene.name = name
    bpy.context.scene.world = bpy.data.worlds.new('Studio')
    objects, volumes, materials, role = [], [], {}, ''


def hpg():
    # The reference-scale facility has its own authoring source. Keep one definition.
    import hpg_headquarters
    hpg_headquarters.build()
    hpg_headquarters.export()
    hpg_headquarters.view()


if __name__ == '__main__':
    hpg()
