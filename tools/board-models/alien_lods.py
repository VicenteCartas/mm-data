"""Run in Blender: blender -b --factory-startup --python tools/board-models/alien_lods.py -- <family> [names...] (or
exec it from the Blender MCP).

Rebuilds the alien plants' mesh levels from their original authored meshes, the Mars corals (`mars`) and the fungal
colonies (`fungus`): each source GLB's first level (the authored sculpt) is welded, weathered in its corner colours and
decimated in Blender to the alien budgets below, smooth-shaded, and written to data/models/board/<family>/<name>.glb
with its material and atlas unchanged. The impostor (the fourth level) is then baked by `prepare_tree_lods.py --
impostors <names>`. The fungal cliff's hanging mycelium (`RETEXTURED`) keeps its levels and takes the `mycelium`
material, whose emission map makes it glow.
The sources are the original GLBs as committed before the grown versions replaced them, read from git (`SOURCE`), never
the tool's own output, which is already decimated.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import read_glb, write_glb  # noqa: E402

BOARD = ROOT / 'data/models/board'
MANIFEST = ROOT / 'tools/board-models/manifest.json'
# The commit whose data/models/board/<family>/<name>.glb are the authored originals.
SOURCE = 'e5e46803e5^'
# Triangles per mesh level: twice the trees' near budgets (the user's allowance for alien plants), then the far level
# the trees use; the impostor bake adds the fourth.
BUDGETS = (3200, 820, 96)
# Per family: the plants; `flare`, how far a plant opens outward as it rises (a share of its reach added per unit of
# height, so sea fans and the lattice catch the sky and read as cover from above instead of dark upright sheets); the
# weathering in linear light: crevices (Blender's vertex dirt on the sculpt) darken toward `crevice`, sky-facing skin
# bleaches toward `bleach` and gathers `dust`, and the foot darkens toward `foot` at the ground over its lowest
# FOOT units; `tints`, linear factors for the corner colours of each atlas quadrant (left/right, top/bottom of the
# image), and `stalk`, the share of the height below which the top-left quadrant takes the second tint instead.
FAMILIES = {
    'mars': dict(names=('tube-grove', 'tube-crown', 'organ-pipes', 'finger-spires', 'finger-crown', 'antler-crown',
                        'lattice-spires', 'fan-scalloped', 'fan-folded', 'plate-terraces', 'spiral-whorls',
                        'brain-lobes'),
                 flare={'fan-scalloped': .15, 'fan-folded': .15, 'lattice-spires': .1},
                 crevice=.75, bleach=1.12, dust=(.62, .3, .18), foot=1, tints={}, stalk=None),
    # The concept art's orange-red cups: the skin (top left, lifted to burnt orange in the atlas) loses its mauve, a
    # warm brown on the stalks below the cups, darker at the foot; the bowls (bottom left) turn dark red-brown, the lips
    # (top right) a warm yellow-orange and the pods (bottom right) crimson. Corner colours stay within 1.
    'fungus': dict(names=('cup-chalice', 'cup-forked', 'cup-frilled', 'cup-trumpet', 'spore-cluster', 'spore-pear',
                          'spore-round'),
                   flare={}, crevice=.7, bleach=1, dust=None, foot=.5,
                   tints={(0, 0): (1, .95, .8), (0, 1): (2, 1.4, .7), (1, 0): (1, .95, .8), (1, 1): (1.3, .8, .75)},
                   stalk=(.4, (.85, .68, .45))),
}
RETEXTURED = {'fungus': ('cliff-mycelium',)}
MYCELIUM = {'id': 'mycelium', 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0, 'textures': [
    {'id': 'mycelium', 'type': 'DIFFUSE', 'filename': '../textures/vegetation/fungus/mycelium_albedo.png'}]}
FOOT = 4
# How many model units of strand one repeat of the mycelium texture covers.
MYCELIUM_REPEAT = 4


def flared(data, flare):
    """Open the mesh outward from its foot as it rises."""
    top = max(v.co.z for v in data.vertices)
    for vertex in data.vertices:
        share = 1 + flare * vertex.co.z / top
        vertex.co.x, vertex.co.y = vertex.co.x * share, vertex.co.y * share
    data.update()


def weathered(data, family):
    """Darken the sculpt's crevices and its foot, tint its atlas parts, and bleach and dust its sky-facing skin, in its
    corner colours."""
    obj = bpy.data.objects.new(data.name + '-dirt', data)
    bpy.context.scene.collection.objects.link(obj)
    dirt = data.color_attributes.new('Dirt', 'BYTE_COLOR', 'POINT')
    data.color_attributes.active_color = dirt
    for other in bpy.context.selected_objects:
        other.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='VERTEX_PAINT')
    bpy.ops.paint.vertex_color_dirt(blur_strength=1, blur_iterations=2, clean_angle=180, dirt_angle=0, dirt_only=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    colors, uvs = data.color_attributes['Color'], data.uv_layers['UV']
    crevice, bleach, dust, foot = family['crevice'], family['bleach'], family['dust'], family['foot']
    low, high = min(v.co.z for v in data.vertices), max(v.co.z for v in data.vertices)
    for loop in data.loops:
        occlusion = data.color_attributes['Dirt'].data[loop.vertex_index].color[0]
        up = max(0.0, data.vertices[loop.vertex_index].normal.z)
        ground = foot + (1 - foot) * min(1.0, (data.vertices[loop.vertex_index].co.z - low) / FOOT)
        u, v = uvs.data[loop.index].uv
        quadrant = (int(u >= .5), int(v >= .5))
        tint = family['tints'].get(quadrant, (1, 1, 1))
        stalk = family['stalk']
        if stalk and quadrant == (0, 0) and data.vertices[loop.vertex_index].co.z < low + stalk[0] * (high - low):
            tint = stalk[1]
        rgba = list(colors.data[loop.index].color)
        for c in range(3):
            value = rgba[c] * tint[c] * ground * (crevice + (1 - crevice) * occlusion) * (1 + (bleach - 1) * up)
            rgba[c] = min(1.0, value + (dust[c] - value) * .35 * up ** 2 if dust else value)
        colors.data[loop.index].color = rgba
    data.color_attributes.remove(data.color_attributes['Dirt'])
    bpy.data.objects.remove(obj)


def blender_mesh(level, name):
    """The level's interleaved vertices as a Blender mesh, corners welded so decimation keeps the surface closed."""
    mesh = level['meshes'][0]
    source = mesh['vertices']
    data = bpy.data.meshes.new(name)
    vertices = [source[i:i + 3] for i in range(0, len(source), 12)]
    faces = [part['indices'][i:i + 3] for part in mesh['parts'] for i in range(0, len(part['indices']), 3)]
    data.from_pydata(vertices, [], faces)
    colors = data.color_attributes.new('Color', 'FLOAT_COLOR', 'CORNER')
    uvs = data.uv_layers.new(name='UV')
    for loop in data.loops:
        index = loop.vertex_index * 12
        colors.data[loop.index].color = source[index + 6:index + 10]
        uvs.data[loop.index].uv = (source[index + 10], source[index + 11])
    work = bmesh.new()
    work.from_mesh(data)
    bmesh.ops.remove_doubles(work, verts=work.verts, dist=.002)
    work.to_mesh(data)
    work.free()
    return data


def decimated(data, budget):
    """A smooth-shaded copy of the mesh collapsed to at most `budget` triangles, as interleaved vertices and indices.
    A lattice whose holes keep collapse above the budget is first remeshed (its small holes close, as they cannot show
    at that level's distance) and takes the original's texture coordinates and colours back from its nearest faces."""
    obj = bpy.data.objects.new(data.name + '-work', data.copy())
    bpy.context.scene.collection.objects.link(obj)
    # A coarser remesh for a smaller budget (about 1.6 voxels per triangle's edge across), coarser again if needed.
    cells = 1.6 * budget ** .5
    while collapsed(obj, budget) > budget:
        obj.modifiers.clear()
        obj.data = data.copy()
        remesh = obj.modifiers.new('remesh', 'REMESH')
        remesh.mode, remesh.voxel_size = 'VOXEL', max(obj.dimensions) / cells
        apply(obj)
        obj.data.color_attributes.new('Color', 'FLOAT_COLOR', 'CORNER')
        obj.data.uv_layers.new(name='UV')
        source = bpy.data.objects.new(data.name + '-source', data)
        bpy.context.scene.collection.objects.link(source)
        for kind in ('UV', 'COLOR_CORNER'):
            transfer = obj.modifiers.new(kind, 'DATA_TRANSFER')
            transfer.object, transfer.use_loop_data = source, True
            transfer.data_types_loops = {kind}
            transfer.loop_mapping = 'POLYINTERP_NEAREST'
        apply(obj)
        bpy.data.objects.remove(source)
        cells *= .75
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    mesh.shade_smooth()
    colors, uvs = mesh.color_attributes['Color'], mesh.uv_layers['UV']
    vertices, indices = [], []
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            loop = mesh.loops[loop_index]
            normal = mesh.corner_normals[loop_index].vector
            indices.append(len(vertices) // 12)
            vertices.extend([*mesh.vertices[loop.vertex_index].co, *normal, *colors.data[loop_index].color,
                             *uvs.data[loop_index].uv])
    obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    bpy.data.objects.remove(obj)
    return vertices, indices


def apply(obj):
    """Bake the object's modifiers into a mesh of its own."""
    bpy.context.view_layer.update()
    obj.data = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    obj.modifiers.clear()


def collapsed(obj, budget):
    """Collapse the object's mesh (a decimate modifier) toward `budget` triangles; returns the count it reached."""
    modifier = obj.modifiers.new('decimate', 'DECIMATE')
    modifier.decimate_type, modifier.use_collapse_triangulate = 'COLLAPSE', True
    modifier.ratio = min(1.0, budget / max(1, sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    count = 0
    for _ in range(8):
        bpy.context.view_layer.update()
        count = len(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh().polygons)
        obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
        if count <= budget:
            break
        modifier.ratio *= budget / count * .995
    return count


def authored(family_name, name, index=0):
    """A level of the authored GLB, from git."""
    blob = subprocess.run(['git', '-C', str(ROOT), 'show', f'{SOURCE}:data/models/board/{family_name}/{name}.glb'],
                          capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / f'{name}.glb'
        path.write_bytes(blob)
        return read_glb(path, index, linear_colors=True)


def retextured(family_name, name):
    """The authored levels with their untextured mycelium as the `mycelium` material: its strands take texture
    coordinates from their position, the fibres running down the hanging strands."""
    levels = {}
    for index in range(3):
        level = authored(family_name, name, index)
        materials = {part['meshpartid']: part['materialid'] for node in level['nodes'] for part in node['parts']}
        mesh = level['meshes'][0]
        for part in mesh['parts']:
            if materials[part['id']] == 'mycelium':
                for i in set(part['indices']):
                    x, y, z = mesh['vertices'][i * 12:i * 12 + 3]
                    mesh['vertices'][i * 12 + 10:i * 12 + 12] = [(x + y) / MYCELIUM_REPEAT, -z / MYCELIUM_REPEAT]
        level['materials'] = [MYCELIUM if material['id'] == 'mycelium' else material for material in level['materials']]
        levels[index] = level
    write_glb(BOARD / f'{family_name}/{name}.glb', levels=levels, linear_colors=True, preserve_groups=('spores',))
    return [sum(len(part['indices']) for part in levels[index]['meshes'][0]['parts']) // 3 for index in range(3)]


def build(family_name, name):
    family = FAMILIES[family_name]
    original = authored(family_name, name)
    data = blender_mesh(original, name)
    if name in family['flare']:
        flared(data, family['flare'][name])
    weathered(data, family)
    material = original['materials'][0]
    levels = {}
    heights = original['meshes'][0]['vertices'][2::12]
    low, high = min(heights), max(heights)
    for index, budget in enumerate(BUDGETS):
        vertices, indices = decimated(data, budget)
        # Collapse moves the roots and tips a little: every level keeps the original's ground and height exactly.
        bottom, top = min(vertices[2::12]), max(vertices[2::12])
        for i in range(2, len(vertices), 12):
            vertices[i] = low + (vertices[i] - bottom) * (high - low) / (top - bottom)
        node = f'{name}-lod{index}'
        part = f'{node}-{material["id"]}'
        levels[index] = {'id': node, 'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                                                  'vertices': vertices, 'parts': [{'id': part, 'type': 'TRIANGLES',
                                                                                   'indices': indices}]}],
                         'nodes': [{'id': node, 'parts': [{'meshpartid': part, 'materialid': material['id']}]}],
                         'materials': [material]}
    bpy.data.meshes.remove(data)
    write_glb(BOARD / f'{family_name}/{name}.glb', levels=levels, linear_colors=True, preserve_groups=('spores',))
    counts = [{'node': f'{name}-lod{index}', 'triangles': len(levels[index]['meshes'][0]['parts'][0]['indices']) // 3,
               'vertices': len(levels[index]['meshes'][0]['vertices']) // 12} for index in range(3)]
    manifest = json.loads(MANIFEST.read_text())
    entry = manifest.setdefault(f'{family_name}/{name}', {'mesh': f'{family_name}/{name}.glb', 'lods': []})
    entry['lods'][:3] = counts
    entry.update(source='tools/board-models/alien_lods.py', triangles=counts[0]['triangles'],
                 vertices=counts[0]['vertices'])
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    return [c['triangles'] for c in counts]


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    family = arguments[0]
    names = arguments[1:] or FAMILIES[family]['names'] + RETEXTURED.get(family, ())
    for name in names:
        print(name, (retextured if name in RETEXTURED.get(family, ()) else build)(family, name), flush=True)
