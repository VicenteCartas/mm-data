"""Run in Blender: python tools/board-models/mars_lods.py <source folder> [names...] (or exec it from the Blender MCP).

Rebuilds the Mars corals' mesh levels from their original authored meshes: each source GLB's first level (the 16000
triangle sculpt) is welded and decimated in Blender to the coral budgets below, smooth-shaded, and written to
data/models/board/mars/<name>.glb with its material and atlas unchanged. The impostor (the fourth level) is then baked
by `prepare_tree_lods.py -- impostors <names>`. The sources are the originals as committed before 3ed7866fe4's parent
(git show <commit>:data/models/board/mars/<name>.glb); never run it on its own output, which is already decimated.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import read_glb, write_glb  # noqa: E402

BOARD = ROOT / 'data/models/board'
MANIFEST = ROOT / 'tools/board-models/manifest.json'
# Coral triangles per mesh level: twice the trees' near budgets (the user's allowance for alien plants), then the far
# level the trees use; the impostor bake adds the fourth.
BUDGETS = (3200, 820, 96)
NAMES = ('tube-grove', 'tube-crown', 'organ-pipes', 'finger-spires', 'finger-crown', 'antler-crown',
         'lattice-spires', 'fan-scalloped', 'fan-folded', 'plate-terraces', 'spiral-whorls', 'brain-lobes')


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


def build(source, name):
    original = read_glb(source, 0, linear_colors=True)
    data = blender_mesh(original, name)
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
    write_glb(BOARD / f'mars/{name}.glb', levels=levels, linear_colors=True)
    counts = [{'node': f'{name}-lod{index}', 'triangles': len(levels[index]['meshes'][0]['parts'][0]['indices']) // 3,
               'vertices': len(levels[index]['meshes'][0]['vertices']) // 12} for index in range(3)]
    manifest = json.loads(MANIFEST.read_text())
    entry = manifest.setdefault(f'mars/{name}', {'mesh': f'mars/{name}.glb', 'lods': []})
    entry['lods'][:3] = counts
    entry.update(source='tools/board-models/mars_lods.py', triangles=counts[0]['triangles'],
                 vertices=counts[0]['vertices'])
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    return [c['triangles'] for c in counts]


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    folder, names = Path(arguments[0]), arguments[1:] or NAMES
    for name in names:
        print(name, build(folder / f'{name}.glb', name), flush=True)
