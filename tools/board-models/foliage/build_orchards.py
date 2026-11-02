"""Export the authored apple trees: blender --background --python build_orchards.py -- [--out BOARD] [names].

The editable branch curves and fruiting sprays live in sources/orchards.blend. No addon is needed to rebuild.
The two coarse mesh levels retain the same scaffold and distributed samples of its crown. Refresh LOD3 afterwards
with prepare_tree_lods.py. All positions use the board's Z-up convention; the shared writer handles glTF conversion.
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'tools')]
from build_trees import materials  # noqa: E402
from glb_geometry import read_glb, write_glb  # noqa: E402

BOARD = ROOT / 'data/models/board'
MANIFEST = ROOT / 'tools/board-models/manifest.json'
SOURCE = HERE / 'sources/orchards.blend'
BUDGETS = (34000, 10000, 3200)
LEAF_TINT = (.88, .96, .81)
MATERIAL = dict(bark_role='bark', bark_maps=('albedo', 'normal', 'orm'), leaves=LEAF_TINT,
                cutout='orchard', snow_cutout='broadleaf')


def crown_sample(polygons, count, position=lambda p: p.center):
    """Farthest-point sampling keeps the crown's outer lobes and fills its volume at coarser levels."""
    if len(polygons) <= count:
        return polygons
    centres = [position(p).copy() for p in polygons]
    chosen = set()
    for axis in range(3):
        chosen.add(min(range(len(centres)), key=lambda i: centres[i][axis]))
        chosen.add(max(range(len(centres)), key=lambda i: centres[i][axis]))
    distance = [min((point - centres[i]).length_squared for i in chosen) for point in centres]
    while len(chosen) < count:
        index = max(range(len(distance)), key=distance.__getitem__)
        chosen.add(index)
        for i, point in enumerate(centres):
            distance[i] = min(distance[i], (point - centres[index]).length_squared)
    return [polygons[i] for i in sorted(chosen)]


def branch_splines(source, height, lod):
    kept = []
    for spline in source.data.splines:
        points = spline.bezier_points
        low = points[0].co.z > height * .1 and points[-1].co.z < height * .34
        low &= max(p.co.z for p in points) < height * .44
        if not low and max(p.radius for p in points) >= (.025, .09, 0)[lod]:
            kept.append(spline)
    if lod == 2:
        kept.sort(key=lambda s: max(p.radius for p in s.bezier_points), reverse=True)
        kept = kept[:6]
    return kept


def branch_mesh(scene, source, height, lod):
    """Tessellate whole branch curves, without triangle decimation that can break narrow fork junctions."""
    kept = branch_splines(source, height, lod)
    data = bpy.data.curves.new('OrchardExport-branches', 'CURVE')
    data.dimensions = '3D'
    data.bevel_depth = source.data.bevel_depth
    data.bevel_resolution = 1 if lod == 0 else 0
    data.resolution_u = 1
    data.twist_mode = source.data.twist_mode
    for ordinal, original in enumerate(kept):
        points = original.bezier_points
        if lod == 0:
            spline = data.splines.new('BEZIER')
            spline.bezier_points.add(len(points) - 1)
            for a, b in zip(spline.bezier_points, points):
                a.co, a.radius = b.co, b.radius
                a.handle_left_type = a.handle_right_type = 'FREE'
                a.handle_left, a.handle_right = b.handle_left, b.handle_right
        else:
            # Coarse curves use intact centre lines and taper, never flattened triangles across a fork.
            count = min(len(points), 4 if lod == 1 or ordinal == 0 else 3)
            sampled = [points[round(i * (len(points) - 1) / (count - 1))] for i in range(count)]
            spline = data.splines.new('POLY')
            spline.points.add(count - 1)
            for a, b in zip(spline.points, sampled):
                a.co = (*b.co, 1)
                a.radius = b.radius
    obj = bpy.data.objects.new('OrchardExport-branches', data)
    scene.collection.objects.link(obj)
    try:
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), preserve_all_data_layers=True,
                                               depsgraph=graph)
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        mesh.update()
        mesh.calc_loop_triangles()
        return mesh
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.curves.remove(data)


def apples(scene, tree, height, lod, vertex, bark):
    """Hang rounded fruit along retained outer twigs, with the same anchors across LODs."""
    tips = [p for s in branch_splines(tree, height, 0)
            if max(p.radius for p in s.bezier_points) < .18 for p in s.bezier_points[-3:]]
    tips = [p for p in tips if height * .46 < p.co.z < height * .88
            and math.hypot(p.co.x, p.co.y) > height * .14]
    count = 72 if scene['mm_asset'].endswith('young') else 144
    tips = crown_sample(tips, count, lambda p: p.co)
    if lod:
        tips = crown_sample(tips, count * (3 - lod) // 3, lambda p: p.co)
    indices = []
    sides, rings = ((10, 6), (8, 4), (6, 3))[lod]
    for tip in tips:
        # Position-derived seeds keep size, skin tint and rotation identical between mesh levels.
        rng = random.Random(round(tip.co.x * 1000) + 17 * round(tip.co.y * 1000))
        radius = height * .013 * rng.uniform(.88, 1.16)
        turn = rng.uniform(0, math.tau)
        outward = Vector((tip.co.x, tip.co.y, 0)).normalized()
        centre = tip.co + outward * radius * .22 - Vector((0, 0, radius * 1.45))
        tint = (rng.uniform(.88, 1), rng.uniform(.92, 1), rng.uniform(.88, .98))
        grid = []
        for row in range(rings + 1):
            theta = math.pi * row / rings
            sine, cosine = math.sin(theta), math.cos(theta)
            z = .88 * cosine - .14 * math.exp(-(theta / .3) ** 2)
            z += .08 * math.exp(-((math.pi - theta) / .25) ** 2)
            ring = []
            for column in range(sides + 1):
                angle = math.tau * column / sides + turn
                r = sine * (1 + .045 * math.cos(5 * angle) * sine) * (1 + .06 * cosine)
                normal = Vector((sine * math.cos(angle), sine * math.sin(angle), cosine))
                point = centre + Vector((r * math.cos(angle), r * math.sin(angle), z)) * radius
                ring.append(vertex(point, normal, tint, (column / sides, row / rings)))
            grid.append(ring)
        for row in range(rings):
            for column in range(sides):
                a, b = grid[row][column:column + 2]
                d, c = grid[row + 1][column:column + 2]
                if row:
                    indices.extend((a, d, b))
                if row < rings - 1:
                    indices.extend((b, d, c))
        # A short stalk starts exactly on the source curve, so no apple floats below a missing support.
        end = centre + Vector((0, 0, radius * .74))
        axis = (end - tip.co).normalized()
        across = axis.cross(Vector((1, 0, 0))).normalized()
        side = axis.cross(across).normalized()
        stalk = []
        for along, point in enumerate((tip.co, end)):
            row = []
            for column in range(4 if lod == 0 else 3):
                angle = math.tau * column / (4 if lod == 0 else 3)
                normal = across * math.cos(angle) + side * math.sin(angle)
                row.append(vertex(point + normal * radius * .055, normal, (.66, .58, .4),
                                  (column / 3, along * .12)))
            stalk.append(row)
        for column in range(len(stalk[0])):
            other = (column + 1) % len(stalk[0])
            a, b, c, d = stalk[0][column], stalk[0][other], stalk[1][other], stalk[1][column]
            bark.extend((a, b, c, a, c, d))
    return indices


def model(scene, lod):
    name = scene['mm_asset']
    tree = next(obj for obj in scene.objects if obj.type == 'CURVE')
    leaves = next(obj.data for obj in scene.objects if obj.type == 'MESH')
    height = max(v.co.z for v in leaves.vertices)
    scale, width, lean = 30 / height, scene['mm_width'], scene.get('mm_lean', 0)
    vertices, bark, canopy = [], [], []
    # Index shared bark vertices by all attributes so the game stays within its 16-bit vertex limit.
    unique = {}

    def vertex(point, normal, color, uv):
        normal = Vector((normal.x / width, normal.y / width, normal.z - lean * normal.x / width)).normalized()
        value = (point.x * scale * width + point.z * scale * lean, point.y * scale * width,
                 max(0, point.z * scale), *normal, *color, 1, *uv)
        key = tuple(round(v, 7) for v in value)
        if key not in unique:
            unique[key] = len(vertices) // 12
            vertices.extend(value)
        return unique[key]

    mesh = branch_mesh(scene, tree, height, lod)
    try:
        for triangle in mesh.loop_triangles:
            for loop in triangle.loops:
                v = mesh.vertices[mesh.loops[loop].vertex_index]
                u, across = mesh.uv_layers.active.data[loop].uv
                shade = .8 + .2 * min(1, v.co.z / 1.5)
                bark.append(vertex(v.co, v.normal, (.92 * shade, .88 * shade, .8 * shade), (across * 1.5, -u * 5)))
    finally:
        bpy.data.meshes.remove(mesh)
    polygons = [p for p in leaves.polygons if p.center.z >= height * .40
                and min(leaves.vertices[i].co.z for i in p.vertices) >= height * .34]
    chosen = crown_sample(polygons, (len(polygons), 900, 360)[lod])
    spread = max(1, .85 * (len(polygons) / len(chosen)) ** .5) if lod else 1
    bounds = [(min(leaves.vertices[i].co[axis] for p in polygons for i in p.vertices),
               max(leaves.vertices[i].co[axis] for p in polygons for i in p.vertices)) for axis in range(3)]
    expanded = [(p, [p.center + (leaves.vertices[i].co - p.center) * spread for i in p.vertices]) for p in chosen]
    expanded_bounds = [(min(v[axis] for _, points in expanded for v in points),
                        max(v[axis] for _, points in expanded for v in points)) for axis in range(3)]
    for poly, points in expanded:
        centre = poly.center
        crown = Vector((centre.x, centre.y, (centre.z - height * .52) * 1.2)).normalized()
        normal = poly.normal.copy()
        if normal.dot(crown) < 0:
            normal.negate()
        normal = (normal * .35 + crown * .65 + Vector((0, 0, .2))).normalized()
        ids = []
        for loop, point in zip(poly.loop_indices, points):
            # Retain the exact near crown bounds despite the larger, fewer photographic sprays.
            point = Vector([bounds[a][0] + (point[a] - expanded_bounds[a][0])
                            * (bounds[a][1] - bounds[a][0]) / (expanded_bounds[a][1] - expanded_bounds[a][0])
                            for a in range(3)])
            u, along = leaves.uv_layers.active.data[loop].uv
            ids.append(vertex(point, normal, LEAF_TINT, (u, .978 - (.978 - .02) * along)))
        a, b, c, d = ids
        canopy.extend((a, b, c, a, c, d, a, c, b, a, d, c))
    fruit = apples(scene, tree, height, lod, vertex, bark)
    assert len(vertices) // 12 <= 65535, (name, lod, len(vertices) // 12)
    triangles = (len(bark) + len(canopy) + len(fruit)) // 3
    assert 0 < triangles <= BUDGETS[lod], (name, lod, triangles, BUDGETS[lod])
    asset = f'{name}-lod{lod}'
    mats = materials('broadleaf', MATERIAL, False)
    # The photographic spray covers less than half its card. Keep the filtered
    # leaves visible when mipmaps average that coverage into a subpixel footprint.
    mats[1]['alphaTest'] = .3
    mats.append(dict(id='fruit', diffuse=[1, 1, 1], roughness=1, metallic=0, textures=[
        dict(id='fruit', type=role, filename=f'../textures/vegetation/apple-skin_{suffix}.png')
        for role, suffix in [('DIFFUSE', 'albedo'), ('NORMAL', 'normal'), ('AMBIENT', 'orm')]]))
    parts = [dict(id=role, type='TRIANGLES', indices=indices)
             for role, indices in [('bark', bark), ('canopy', canopy), ('fruit', fruit)]]
    return dict(id=asset, meshes=[dict(attributes=['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                                       vertices=vertices, parts=parts)], materials=mats,
                nodes=[dict(id=asset, parts=[dict(meshpartid=p['id'], materialid=m['id'])
                                              for p, m in zip(parts, mats)])])


def build(board=BOARD, names=None):
    previous = bpy.context.window.scene if bpy.context.window else None
    with bpy.data.libraries.load(str(SOURCE), link=False) as (available, loaded):
        loaded.scenes = [name for name in available.scenes if name.startswith('OrchardSource-')]
    scenes = list(loaded.scenes)
    counts = {}
    manifest = json.loads(MANIFEST.read_text())
    try:
        for scene in sorted(scenes, key=lambda s: s['mm_asset']):
            name = scene['mm_asset']
            if names and name not in names:
                continue
            if bpy.context.window:
                bpy.context.window.scene = scene
            with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                levels = {lod: model(scene, lod) for lod in range(3)}
            shipped = BOARD / f'vegetation/{name}.glb'
            if shipped.exists():
                old = read_glb(shipped, 3)
                old['materials'] = [mat for mat in old['materials'] if mat['id'] == 'impostor']
                levels[3] = old
            path = Path(board) / f'vegetation/{name}.glb'
            path.parent.mkdir(parents=True, exist_ok=True)
            write_glb(path, levels=levels)
            counts[name] = [dict(node=f'{name}-lod{i}', vertices=len(m['meshes'][0]['vertices']) // 12,
                                triangles=sum(len(p['indices']) // 3 for p in m['meshes'][0]['parts']))
                            for i, m in levels.items() if i < 3]
            if Path(board).resolve() == BOARD.resolve():
                for key in (f'vegetation/{name}', f'vegetation/{name}-snow'):
                    entry = manifest[key]
                    stem = key.rsplit('/', 1)[-1]
                    entry['lods'][:3] = [{**lod, 'node': f'{stem}-lod{i}'} for i, lod in enumerate(counts[name])]
                    entry.update(source='tools/board-models/foliage/build_orchards.py',
                                 triangles=counts[name][0]['triangles'], vertices=counts[name][0]['vertices'])
                    entry.pop('texture', None)
        if Path(board).resolve() == BOARD.resolve():
            MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
        return counts
    finally:
        if previous:
            bpy.context.window.scene = previous
        for scene in scenes:
            for obj in list(scene.objects):
                data, kind = obj.data, obj.type
                bpy.data.objects.remove(obj, do_unlink=True)
                if data.users == 0:
                    (bpy.data.curves if kind == 'CURVE' else bpy.data.meshes).remove(data)
            bpy.data.scenes.remove(scene)


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    board = BOARD
    if arguments[:1] == ['--out']:
        board, arguments = Path(arguments[1]), arguments[2:]
    print(json.dumps(build(board, set(arguments)), indent=2))
