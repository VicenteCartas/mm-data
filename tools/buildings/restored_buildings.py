"""The levels of classic-church and neo-futurist-arena, the earlier designs restored from history.

Run: python tools/buildings/restored_buildings.py
They exist only as GLBs, so ORIGINALS names the commit whose geometry and pigments each starts from. Materials, extras and
helpers stay as the file under data/models holds them; only the visible levels are written again.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS/'buildings'))
sys.path.insert(0, str(TOOLS/'blender/mm_materials'))
import building_lod
import glb
import weathering
from glb_geometry import display, linear

AUTH = ROOT/'data/models/buildings/authored'
ORIGINALS = {'classic-church': '2a3caa33cc', 'neo-futurist-arena': '5c10055fbc'}
# Neo's concrete pigments, by the display colour its original holds: its own palette, for walls of about .30 on the finish.
NEO_CONCRETE = {
    (.52, .55, .54): (.559, .591, .580),
    (.86, .88, .88): (.922, .943, .943),
    (.88, .87, .80): (.943, .933, .858),
    (.84, .87, .82): (.901, .933, .879),
    (.62, .64, .62): (.666, .687, .666),
    (.58, .61, .59): (.623, .655, .634),
    (.51, .54, .53): (.548, .580, .570),
    (.30, .44, .38): (.324, .473, .409),
    (.71, .74, .73): (.762, .794, .783),
    (.69, .71, .70): (.740, .762, .751),
}
# Neo's LOD2 from the foot to the field, on its 69 x 99 ellipse: building_lod.lathe, with (material, display colour) as finish.
# The roof stands at the top of the ribs it replaces: the shadow map picks its casters' level by its own texel.
CONCRETE, ROOF, GLASS = 'structures/common/cast-concrete', 'structures/common/painted-steel', 'structures/buildings/fortress-glass#emission-night'
NEO_PLAIN = ((1.05, 0, None), (1, 14, (CONCRETE, (.82, .82, .77))), (.985, 20, (GLASS, (.85, .89, .92))), (.97, 28.5, (CONCRETE, (.82, .82, .77))),
             (.88, 36.2, (ROOF, (.72, .76, .75))),
             (.66, 36.2, (ROOF, (.75, .78, .77))), (.64, 18, (CONCRETE, (.60, .63, .63))), (.48, 4, (CONCRETE, (.26, .29, .29))),
             (.44, 1.3, (CONCRETE, (.52, .58, .55))), (0, 1.3, (CONCRETE, (.33, .48, .41))))
# How rundown the classic church's concrete is, and the heights that shed soot: weathering.weather_vertices.
CLASSIC_WEATHER = .35, (18, 54)
COUNT = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
DTYPE = {5126: '<f4', 5123: '<u2', 5125: '<u4', 5121: 'u1'}
POSED = {'translation', 'rotation', 'scale', 'matrix'}


def read(doc, binary, index):
    a = doc['accessors'][index]
    v = doc['bufferViews'][a['bufferView']]
    n = COUNT[a['type']]
    data = np.frombuffer(binary, dtype=DTYPE[a['componentType']], count=a['count']*n, offset=v.get('byteOffset', 0)+a.get('byteOffset', 0))
    return data.reshape(-1, n) if n > 1 else data


def original(stem):
    raw = subprocess.check_output(['git', 'show', f'{ORIGINALS[stem]}:data/models/buildings/authored/{stem}.glb'], cwd=ROOT)
    length = int.from_bytes(raw[12:16], 'little')
    return json.loads(raw[20:20+length]), raw[28+length:]


def level_root(doc, stem, level):
    return next((i for i, n in enumerate(doc['nodes']) if n.get('name') == f'{stem}-lod{level}'), None)


def modules(doc, binary, stem, level, materials):
    """A stored level as [(node name, flat Z-up vertices, {material index in the file written: indices})]."""
    result = []
    root = level_root(doc, stem, level)
    assert not POSED & set(doc['nodes'][root])
    for k in doc['nodes'][root]['children']:
        node = doc['nodes'][k]
        assert not POSED & set(node)
        primitives = doc['meshes'][node['mesh']]['primitives']
        at = primitives[0]['attributes']
        assert all(p['attributes'] == at for p in primitives)
        p, n, c, t = (read(doc, binary, at[key]) for key in ('POSITION', 'NORMAL', 'COLOR_0', 'TEXCOORD_0'))
        # glTF Y up to the model's Z up, and back in Writer.stored.
        vertices = np.column_stack((p[:, 0], -p[:, 2], p[:, 1], n[:, 0], -n[:, 2], n[:, 1], c, t)).astype(float).ravel().tolist()
        parts = {materials[doc['materials'][q['material']]['name']]: [int(i) for i in read(doc, binary, q['indices'])] for q in primitives}
        assert len(parts) == len(primitives)
        result.append((node['name'], vertices, parts))
    return result


class Writer:
    """The file's buffer laid out again, one view per accessor."""

    def __init__(self, doc, binary):
        self.source, self.binary = doc, binary
        self.doc = copy.deepcopy(doc)
        self.doc['accessors'], self.doc['bufferViews'] = [], []
        self.blob = bytearray()
        self.copied = {}

    def add(self, array, kind, component, target, bounds=False):
        payload = array.astype(DTYPE[component]).tobytes()
        self.doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(self.blob), 'byteLength': len(payload), 'target': target})
        self.blob += payload
        self.blob += b'\0'*(-len(self.blob) % 4)
        accessor = {'bufferView': len(self.doc['bufferViews'])-1, 'componentType': component, 'count': len(array), 'type': kind}
        if bounds:
            accessor['min'], accessor['max'] = [float(x) for x in array.min(0)], [float(x) for x in array.max(0)]
        self.doc['accessors'].append(accessor)
        return len(self.doc['accessors'])-1

    def keep(self, index):
        if index not in self.copied:
            a = self.source['accessors'][index]
            target = self.source['bufferViews'][a['bufferView']].get('target', 34962)
            self.copied[index] = self.add(read(self.source, self.binary, index), a['type'], a['componentType'], target, 'min' in a)
            if a.get('normalized'):
                self.doc['accessors'][self.copied[index]]['normalized'] = True
        return self.copied[index]

    def stored(self, name, vertices, parts):
        """A new mesh of the given parts, its primitives named as the exporter names them."""
        v = np.asarray(vertices).reshape(-1, weathering.STRIDE)
        attributes = {
            'POSITION': self.add(np.column_stack((v[:, 0], v[:, 2], -v[:, 1])), 'VEC3', 5126, 34962, True),
            'NORMAL': self.add(np.column_stack((v[:, 3], v[:, 5], -v[:, 4])), 'VEC3', 5126, 34962),
            'COLOR_0': self.add(v[:, 6:10], 'VEC4', 5126, 34962),
            'TEXCOORD_0': self.add(v[:, 10:12], 'VEC2', 5126, 34962),
        }
        component = 5125 if len(v) > 65535 else 5123
        return {'primitives': [{'attributes': attributes, 'indices': self.add(np.asarray(indices), 'SCALAR', component, 34963),
                                'mode': 4, 'extras': {'mmPart': name+'-'+str(i)}, 'material': key}
                               for i, (key, indices) in enumerate(parts.items())]}


def rewrite(stem, levels):
    """Writes the given {level: modules} over the file's levels; the file's other content stays."""
    path = AUTH/(stem+'.glb')
    doc, binary = glb.read_glb(path)
    writer = Writer(doc, binary)
    out = writer.doc
    written = {doc['nodes'][k]['mesh'] for level in levels if level_root(doc, stem, level) is not None
               for k in doc['nodes'][level_root(doc, stem, level)]['children']}
    for index, mesh in enumerate(out['meshes']):
        if index not in written:
            for p in mesh['primitives']:
                p['attributes'] = {k: writer.keep(a) for k, a in p['attributes'].items()}
                p['indices'] = writer.keep(p['indices'])
    scene = out['scenes'][out.get('scene', 0)]
    for level, parts in sorted(levels.items()):
        nodes = []
        for name, vertices, indices in parts:
            out['meshes'].append(writer.stored(name, vertices, indices))
            out['nodes'].append({'name': name, 'mesh': len(out['meshes'])-1})
            nodes.append(len(out['nodes'])-1)
        root = level_root(out, stem, level)
        if root is None:
            out['nodes'].append({'name': f'{stem}-lod{level}', 'children': nodes})
            scene['nodes'].insert(scene['nodes'].index(level_root(out, stem, level-1))+1, len(out['nodes'])-1)
        else:
            out['nodes'][root]['children'] = nodes
    # What the scene no longer reaches goes.
    live, pending = set(), list(scene['nodes'])
    while pending:
        i = pending.pop()
        live.add(i)
        pending += out['nodes'][i].get('children', [])
    order = sorted(live)
    new_node = {old: new for new, old in enumerate(order)}
    used = sorted({out['nodes'][i]['mesh'] for i in live if 'mesh' in out['nodes'][i]})
    new_mesh = {old: new for new, old in enumerate(used)}
    for i in order:
        node = out['nodes'][i]
        if 'mesh' in node:
            node['mesh'] = new_mesh[node['mesh']]
        if 'children' in node:
            node['children'] = [new_node[c] for c in node['children']]
    out['nodes'] = [out['nodes'][i] for i in order]
    out['meshes'] = [out['meshes'][i] for i in used]
    scene['nodes'] = [new_node[i] for i in scene['nodes']]
    out['buffers'] = [{'byteLength': len(writer.blob)}]
    glb.validate(out, path, ROOT/'data/models')
    glb.write_glb(path, out, bytes(writer.blob))
    for level, parts in sorted(levels.items()):
        print(stem, 'lod', level, sum(len(i) for _, _, indices in parts for i in indices.values())//3, 'triangles')


def repaint(parts, concrete):
    """Gives the concrete of each stored module its authored pigment; a vertex no other finish shares."""
    for _, vertices, indices in parts:
        other = {i for key, part in indices.items() if key not in concrete for i in part}
        for i in {i for key, part in indices.items() if key in concrete for i in part}:
            assert i not in other, 'shared vertex would change another finish'
            at = i*weathering.STRIDE+6
            pigment = NEO_CONCRETE[tuple(round(display(c), 2) for c in vertices[at:at+3])]
            vertices[at:at+3] = [linear(c) for c in pigment]


def weather(parts, concrete, level, cell=0):
    amount, ledges = CLASSIC_WEATHER
    for _, vertices, indices in parts:
        selected = [part for key, part in indices.items() if key in concrete]
        if level == 2:
            weathering.average_weather(vertices, selected, amount, float)
        else:
            weathering.weather_vertices(vertices, selected, [part for key, part in indices.items() if key not in concrete],
                                        amount, ledges, float, *((6*cell, 30*cell) if level else ()))


def add_surface(vertices, parts, points, faces, material, colour):
    """Appends a plain surface: faces smooth among themselves, projected from above, in a display colour."""
    points = np.asarray(points, dtype=float)
    normals = np.zeros_like(points)
    triangles = []
    for face in faces:
        for b, c in zip(face[1:], face[2:]):
            triangles.append((face[0], b, c))
            cross = np.cross(points[b]-points[face[0]], points[c]-points[face[0]])
            normals[[face[0], b, c]] += cross
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    offset = len(vertices)//weathering.STRIDE
    pigment = [linear(c) for c in colour]
    for p, n in zip(points.tolist(), normals.tolist()):
        vertices.extend([*p, *n, *pigment, 1, p[0]/54, p[1]/54])
    parts.setdefault(material, []).extend(offset+i for triangle in triangles for i in triangle)


def plain_neo(materials, far):
    """Neo's LOD2: the ellipse as bare surfaces, plain portals, and the two spires as stored on LOD1."""
    vertices, parts = [], {}
    around = lambda a: (69*np.cos(a), 99*np.sin(a))
    for points, faces, (material, colour) in building_lod.lathe(NEO_PLAIN, 20, around):
        add_surface(vertices, parts, points, faces, materials[material], colour)
    for end in (-1, 1):
        ys = sorted((end*88, end*113))
        corners = [(x, y, z) for z in (0, 20) for y in ys for x in (-16.5, 16.5)]
        for face in ((4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (1, 3, 7, 5), (0, 4, 6, 2)):
            add_surface(vertices, parts, [corners[i] for i in face], [(0, 1, 2, 3)], materials[CONCRETE], (.82, .82, .77))
    for _, stored, indices in far:
        data = np.asarray(stored).reshape(-1, weathering.STRIDE)
        pieces = building_lod.connected_pieces(data[:, :3], np.concatenate([np.asarray(part).reshape(-1, 3) for part in indices.values()]))
        spires = set(np.unique(pieces[data[:, 2] > 55]).tolist())
        for key, part in indices.items():
            triangles = np.asarray(part).reshape(-1, 3)
            kept = triangles[[int(pieces[t[0]]) in spires for t in triangles]]
            if len(kept):
                offset = len(vertices)//weathering.STRIDE
                vertices.extend(data.ravel().tolist())
                parts.setdefault(key, []).extend((kept.ravel()+offset).tolist())
    return [('neo-futurist-arena-lod2-shell', *compact(vertices, parts))]


def compact(vertices, parts):
    """Vertices no part uses go."""
    data = np.asarray(vertices).reshape(-1, weathering.STRIDE)
    used, inverse = np.unique(np.concatenate([np.asarray(part) for part in parts.values()]), return_inverse=True)
    result, start = {}, 0
    for key, part in parts.items():
        result[key] = inverse[start:start+len(part)].tolist()
        start += len(part)
    return data[used].ravel().tolist(), result


def build(stem, paint=False, weathered=False):
    current, _ = glb.read_glb(AUTH/(stem+'.glb'))
    source, data = original(stem)
    materials = {m['name']: i for i, m in enumerate(current['materials'])}
    concrete = {i for name, i in materials.items() if 'cast-concrete' in name}
    near, far = (modules(source, data, stem, level, materials) for level in (0, 1))
    if paint:
        repaint(near, concrete)
        repaint(far, concrete)
    if weathered:
        weather(near, concrete, 0)
    levels = {0: near}
    for level in (1, 2):
        simple, cell = building_lod.simplify(far, level, lambda key: building_lod.is_lit(current['materials'][key]['name']))
        if weathered:
            weather(simple, concrete, level, cell)
        levels[level] = [(name.replace('-lod1', f'-lod{level}'), vertices, parts) for name, vertices, parts in simple]
    if stem == 'neo-futurist-arena':
        levels[2] = plain_neo(materials, far)
    rewrite(stem, levels)


if __name__ == '__main__':
    build('classic-church', weathered=True)
    build('neo-futurist-arena', paint=True)
