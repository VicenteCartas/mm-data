"""Export forest.blend with Blender: --background --python build_forest.py -- [--out BOARD] [names].

One editable set of branch curves and attached foliage sprays supplies all three mesh levels.
The lower levels retain the woody scaffold and spatially distributed crown samples; they never regrow a tree.
Refresh the fourth level with tools/prepare_tree_lods.py after exporting. Palms, orchards and conifers use their
existing exporters. No authoring addon is required to rebuild this file.
"""
import copy
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import interpolate_bezier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'tools')]
from build_trees import materials, snow_scale
from glb_geometry import display, linear, read_glb, write_glb

BOARD = ROOT / 'data/models/board'
MANIFEST = ROOT / 'tools/board-models/manifest.json'
SOURCE = HERE / 'sources/forest.blend'
BUDGETS = (32000, 10000, 2600)
TINTS = {'tree': (.89, .97, .85), 'tree-broad': (.84, .94, .79), 'tree-slender': (.87, .96, .83),
         'tree-layered': (.91, .98, .86), 'tree-forked': (.90, .96, .80),
         'tree-volcano-crown': (.96, .90, .84), 'tree-volcano-forked': (.93, .88, .86),
         'tree-volcano-spire': (.98, .94, .89), 'willow': (.91, .97, .82), 'willow-broad': (.87, .95, .79),
         'birch': (.94, .99, .84), 'birch-tall': (.92, .99, .85), 'birch-young': (.95, 1, .86),
         'birch-spreading': (.92, .98, .81)}


def surface(name):
    volcanic, birch, willow = 'volcano' in name, name.startswith('birch'), name.startswith('willow')
    return dict(bark_role='bark-birch' if birch else 'bark-volcano' if volcanic else 'bark',
                bark_texture='forest-birch-bark' if birch else 'forest-cinder-bark' if volcanic else 'forest-bark',
                bark_maps=('albedo', 'normal', 'orm'), leaves=TINTS[name], winter=not volcanic,
                cutout='forest-cinder' if volcanic else 'forest-willow' if willow else 'forest-broadleaf',
                snow_cutout='forest-broadleaf')


def crown_order(polygons):
    """Nested farthest-point samples retain the same crown extremities at every distance."""
    points = np.array([p.center[:] for p in polygons])
    chosen = list(dict.fromkeys(int(func(points[:, a])) for a in range(3) for func in (np.argmin, np.argmax)))
    distances = np.min(np.sum((points[:, None] - points[chosen]) ** 2, axis=2), axis=1)
    distances[chosen] = -1
    while len(chosen) < min(len(points), 3000):
        k = int(np.argmax(distances))
        chosen.append(k)
        distances = np.minimum(distances, np.sum((points - points[k]) ** 2, axis=1))
        distances[chosen] = -1
    return chosen


def branch_paths(tree):
    paths = []
    for spline in tree.data.splines:
        source = spline.bezier_points
        points = []
        for a, b in zip(source, source[1:]):
            sample = interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, 4)
            points.extend((p, a.radius + (b.radius - a.radius) * i / 3) for i, p in enumerate(sample[:-1]))
        points.append((source[-1].co.copy(), source[-1].radius))
        paths.append(points)
    return paths


def tube(points, sides, vertex, indices, tint):
    """Parallel-transported rings give curved branches continuous bark UVs and circular cross sections."""
    rings, across, last, distance = [], None, points[0][0], 0
    for j, (point, radius) in enumerate(points):
        tangent = (points[min(j + 1, len(points) - 1)][0] - points[max(0, j - 1)][0]).normalized()
        if across is None:
            across = tangent.cross(Vector((0, 0, 1)))
            if across.length < .01:
                across = Vector((1, 0, 0))
        across = (across - tangent * across.dot(tangent)).normalized()
        side = tangent.cross(across).normalized()
        distance += (point - last).length
        last = point
        ring = []
        for k in range(sides + 1):
            angle = math.tau * k / sides
            radial = across * math.cos(angle) + side * math.sin(angle)
            # Broad shallow root flutes disappear up the stem rather than producing a regular cylinder.
            flute = 1 + .08 * math.sin(angle * 5 + point.z * .8) * max(0, 1 - point.z / 1.4)
            p = point + radial * radius * flute
            shade = .86 + .14 * min(1, point.z / 1.5)
            ring.append(vertex(p, radial, tuple(c * shade for c in tint), (k / sides * 1.3, -distance * 1.7)))
        if rings:
            a, b = rings[-1], ring
            for k in range(sides):
                indices.extend((a[k], a[k+1], b[k+1], a[k], b[k+1], b[k]))
        rings.append(ring)


def wood(paths, lod, vertex, indices, birch):
    cutoff = (.009, .05, .16)[lod] * (.65 if birch else 1)
    tint = (.96, .96, .94) if birch else (.88, .85, .80)
    # Ordered by thickness so a twig can be reattached to the already simplified parent geometry.
    ordered = sorted(paths, key=lambda p: max(r for _, r in p), reverse=True)
    drawn = []
    for ordinal, path in enumerate(ordered):
        radius = max(r for _, r in path)
        if (lod == 2 and ordinal >= 14) or (lod != 2 and radius < cutoff):
            continue
        stride = (3 if radius > .09 else 5, 5, 9)[lod]
        points = [path[i] for i in range(0, len(path) - 1, stride)] + [path[-1]]
        points = [(p.copy(), r) for p, r in points]
        if drawn and points[0][0].z > .01:
            root = points[0][0]
            nearest, best = None, float('inf')
            for parent in drawn:
                for (a, _), (b, _) in zip(parent, parent[1:]):
                    delta = b - a
                    t = max(0, min(1, (root - a).dot(delta) / max(delta.length_squared, 1e-12)))
                    candidate = a + delta * t
                    distance = (candidate - root).length_squared
                    if distance < best:
                        nearest, best = candidate, distance
            if best < (radius * 3 + .06) ** 2:
                points[0] = (nearest, points[0][1])
        sides = (10 if radius > .13 else 6 if radius > .045 else 4) if lod == 0 else (
            6 if radius > .13 else 4) if lod == 1 else 4
        tube(points, sides, vertex, indices, tint)
        drawn.append(points)


def model(scene, lod, paths, order):
    name = scene['mm_asset']
    spec = json.loads(scene['mm_surface']) if 'mm_surface' in scene else surface(name)
    budgets = scene.get('mm_budgets', BUDGETS)
    leaves = next(o.data for o in scene.objects if o.type == 'MESH')
    height = max(v.co.z for v in leaves.vertices)
    scale, width = scene.get('mm_height', 30) / height, scene['mm_width']
    vertices, bark, canopy, unique = [], [], [], {}

    def vertex(point, normal, color, uv):
        normal = Vector((normal.x / width, normal.y / width, normal.z)).normalized()
        value = (point.x * scale * width, point.y * scale * width, max(0, point.z * scale),
                 *normal, *color, 1, *uv)
        key = tuple(round(v, 7) for v in value)
        if key not in unique:
            unique[key] = len(vertices) // 12
            vertices.extend(value)
        return unique[key]

    wood(paths, lod, vertex, bark, name.startswith('birch'))
    count = min(len(order), scene.get('mm_sprays', (2600, 1200, 360))[lod],
                (budgets[lod] - len(bark) // 3) // (8 if lod == 0 else 4))
    assert count > 0, (name, lod, 'Branch geometry exceeds the mesh budget')
    chosen = [leaves.polygons[order[i]] for i in range(count)]
    expansion = (len(leaves.polygons) / count) ** (.36 if lod == 2 else .44)
    bounds = [(min(v.co[a] for v in leaves.vertices), max(v.co[a] for v in leaves.vertices)) for a in range(3)]
    for poly in chosen:
        centre = poly.center
        envelope = Vector((centre.x, centre.y, (centre.z - height * .58) * 1.1 + height * .06)).normalized()
        normal = poly.normal.copy()
        if normal.dot(envelope) < 0:
            normal.negate()
        normal = (normal * .25 + envelope * .75).normalized()
        shade = .92 + .08 * math.sin(poly.index * 1.618)
        tint = tuple(v * shade for v in spec['leaves'])
        values = [(leaves.vertices[leaves.loops[i].vertex_index].co, leaves.uv_layers.active.data[i].uv)
                  for i in poly.loop_indices]
        base = sum((p for p, uv in values if uv.y < .01), Vector()) / 2
        # Limit the entire spray uniformly. Clamping each corner separately flattened upper sprays into roofs.
        spread = expansion
        for point, uv in values:
            delta = point - base
            for a in range(3):
                if abs(delta[a]) > 1e-8:
                    edge = bounds[a][1 if delta[a] > 0 else 0]
                    spread = min(spread, max(0, (edge - base[a]) / delta[a]))
        expanded_points = []
        for point, uv in values:
            # Keep the spray's twig base fixed. Larger coarse sprays retain the near model's outer bounds.
            expanded = base + (point - base) * spread
            expanded_points.append((expanded, uv.copy()))
        if lod == 0:
            # A shallow midrib fold makes the spray a small volume rather than a flat roof plate.
            a, b, c, d = expanded_points
            reach = ((b[0] + c[0] - a[0] - d[0]) / 2).length
            bottom = ((a[0] + d[0]) / 2, (a[1] + d[1]) / 2)
            folded = (b[0] + c[0]) / 2 + poly.normal * reach * .12
            folded = Vector([max(bounds[k][0], min(bounds[k][1], folded[k])) for k in range(3)])
            top = (folded, (b[1] + c[1]) / 2)
            quads = ((a, b, top, bottom), (bottom, top, c, d))
        else:
            quads = (expanded_points,)
        for quad in quads:
            ids = [vertex(p, normal, tint, (uv.x, .978 - .958 * uv.y)) for p, uv in quad]
            a, b, c, d = ids
            canopy.extend((a,b,c,a,c,d,a,c,b,a,d,c))
    assert len(vertices) // 12 < 65536, (name, lod, len(vertices) // 12)
    triangles = (len(bark) + len(canopy)) // 3
    assert triangles <= budgets[lod], (name, lod, triangles)
    asset = f'{name}-lod{lod}'
    mats = materials('broadleaf', spec, False)
    # The photographs cover about a third of each spray. Preserve those leaves under mip filtering.
    mats[1]['alphaTest'] = .3
    parts = [dict(id=role, type='TRIANGLES', indices=indices) for role, indices in [('bark',bark),('canopy',canopy)]]
    return dict(id=asset, meshes=[dict(attributes=['POSITION','NORMAL','COLOR','TEXCOORD0'],vertices=vertices,parts=parts)],
                materials=mats, nodes=[dict(id=asset,parts=[dict(meshpartid=p['id'],materialid=m['id'])
                                                          for p,m in zip(parts,mats)])])


def build(board=BOARD, names=None, source=SOURCE):
    previous = bpy.context.window.scene
    with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
        loaded.scenes = [s for s in available.scenes if s.startswith(('ForestSource-', 'ShrubSource-'))]
    manifest = json.loads(MANIFEST.read_text())
    counts = {}
    try:
        for scene in loaded.scenes:
            name = scene['mm_asset']
            if names and name not in names:
                continue
            bpy.context.window.scene = scene
            bpy.context.view_layer.update()
            tree = next(o for o in scene.objects if o.type == 'CURVE')
            leaves = next(o.data for o in scene.objects if o.type == 'MESH')
            paths, order = branch_paths(tree), crown_order(leaves.polygons)
            levels = {i:model(scene,i,paths,order) for i in range(3)}
            old = read_glb(BOARD/f'vegetation/{name}.glb',3)
            old['materials'] = [m for m in old['materials'] if m['id']=='impostor']
            old['materials'][0]['alphaTest'] = .35 if 'volcano' in name else .2
            levels[3] = old
            path = Path(board)/f'vegetation/{name}.glb'
            path.parent.mkdir(parents=True,exist_ok=True)
            write_glb(path,levels=levels)
            if name in ('tree-forked', 'willow'):
                # These two winter assets are explicit files in the runtime catalog.
                cold = copy.deepcopy(levels)
                for i in range(3):
                    m = cold[i]
                    m['id'] = m['nodes'][0]['id'] = f'{name}-snow-lod{i}'
                    m['materials'] = materials('broadleaf', surface(name), True)
                    m['materials'][1]['alphaTest'] = .3
                    m['nodes'][0]['parts'][1]['materialid'] = m['materials'][1]['id']
                    mesh = m['meshes'][0]
                    shade = snow_scale(surface(name))
                    for k in set(mesh['parts'][1]['indices']):
                        for channel in range(3):
                            slot = k * 12 + 6 + channel
                            mesh['vertices'][slot] = display(min(1, linear(mesh['vertices'][slot]) * shade[channel]))
                old = read_glb(BOARD/f'vegetation/{name}-snow.glb', 3)
                old['materials'] = [m for m in old['materials'] if m['id'] == 'impostor']
                old['materials'][0]['alphaTest'] = .2
                cold[3] = old
                write_glb(Path(board)/f'vegetation/{name}-snow.glb', levels=cold)
            counts[name]=[dict(node=f'{name}-lod{i}',triangles=sum(len(p['indices'])//3 for p in m['meshes'][0]['parts']),
                              vertices=len(m['meshes'][0]['vertices'])//12) for i,m in levels.items() if i<3]
            if Path(board).resolve()==BOARD.resolve():
                for key in (f'vegetation/{name}',f'vegetation/{name}-snow'):
                    if key not in manifest:
                        continue
                    entry=manifest[key]
                    stem=key.rsplit('/',1)[-1]
                    entry['lods'][:3]=[{**v,'node':f'{stem}-lod{i}'} for i,v in enumerate(counts[name])]
                    entry.update(source=scene.get('mm_exporter', 'tools/board-models/foliage/build_forest.py'),
                                 triangles=counts[name][0]['triangles'],vertices=counts[name][0]['vertices'])
                    entry.pop('texture',None)
            print(name,[v['triangles'] for v in counts[name]],flush=True)
        if Path(board).resolve()==BOARD.resolve():
            MANIFEST.write_text(json.dumps(manifest,indent=2)+'\n')
        return counts
    finally:
        bpy.context.window.scene=previous
        for scene in loaded.scenes:
            for obj in list(scene.objects):
                data,kind=obj.data,obj.type
                bpy.data.objects.remove(obj,do_unlink=True)
                if data.users==0:
                    (bpy.data.curves if kind=='CURVE' else bpy.data.meshes).remove(data)
            bpy.data.scenes.remove(scene)


if __name__=='__main__':
    arguments=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    board=BOARD
    if arguments[:1]==['--out']:
        board,arguments=Path(arguments[1]),arguments[2:]
    build(board,set(arguments))
