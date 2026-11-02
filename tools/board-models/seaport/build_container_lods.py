"""Build the container family from one detailed prop and the existing yard placements.

Individual props keep detailed LOD0 hardware and recessed LOD1 panels. Yard
compositions use simpler rail profiles with baked hardware at every level, so
their triangle budgets apply to the whole composition. LOD2 uses flat box faces.
The shared bake contains colour/normals/ORM, never directional lighting.
Run from any directory; --output can stage the models and textures for review.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import read_glb, write_glb

YARD = ROOT / 'data/models/board/scenery/seaport/yard'
MAPS = ROOT / 'data/models/board/textures/structures/common'
ATLAS = 'container-details'
PAINT = np.array([120, 59, 59]) / 255
TILE, PAD = 256, 4
YARD_TRIANGLE_BUDGETS = (3000, 2000, 1100)
# Outward U/V bases. The far mesh and bake use exactly the same projections.
FACES = {
    '-x': ((0, -1, 0), (0, 0, 1), (-2.9, 0, 3), (13.2, 6), 0),
    '+x': ((0, 1, 0), (0, 0, 1), (2.9, 0, 3), (13.2, 6), 0),
    '+y': ((-1, 0, 0), (0, 0, 1), (0, 6.6, 3), (5.8, 6), 1),
    '-y': ((1, 0, 0), (0, 0, 1), (0, -6.6, 3), (5.8, 6), 2),
    '+z': ((0, 1, 0), (-1, 0, 0), (0, 0, 6), (13.2, 5.8), 3),
    '-z': ((0, 1, 0), (1, 0, 0), (0, 0, 0), (13.2, 5.8), 3),
}


def linear(a):
    a = np.asarray(a)
    return np.where(a <= .04045, a / 12.92, ((a + .055) / 1.055) ** 2.4)


def display(a):
    a = np.maximum(a, 0)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def primitives(model):
    refs = {}
    def visit(node):
        assert not any(abs(v) > 1e-6 for v in node.get('translation', [0, 0, 0]))
        assert 'rotation' not in node and 'scale' not in node
        refs.update((p['meshpartid'], p['materialid']) for p in node.get('parts', []))
        for child in node.get('children', []):
            visit(child)
    for node in model['nodes']:
        visit(node)
    for mesh in model['meshes']:
        vertices = np.array(mesh['vertices']).reshape(-1, 12)
        slots = np.array(mesh.get('slots', [0] * len(vertices)))
        for part in mesh['parts']:
            yield refs[part['id']], vertices, slots, np.array(part['indices']).reshape(-1, 3)


def sample(image, uv):
    h, w = image.shape[:2]
    x = (np.floor(uv[..., 0] * w).astype(int)) % w
    # glTF and the board's image upload use V=0 at the image's top row.
    y = (np.floor(uv[..., 1] * h).astype(int)) % h
    return image[y, x]


def bake(source, output):
    """Orthographically rasterize the source's material channels, with edge padding."""
    textures = {}
    for mat in source['materials']:
        stem = Path(mat['textures'][0]['filename']).name.removesuffix('_albedo.png')
        textures[mat['id']] = {key: np.array(Image.open(MAPS / f'{stem}_{key}.png').convert('RGB')) / 255
                               for key in ('albedo', 'normal', 'orm')}
    atlas = {key: np.zeros((TILE*2, TILE*2, channels))
             for key, channels in [('albedo', 4), ('normal', 3), ('orm', 3)]}
    for face in ('-x', '+y', '-y', '+z'):
        u, v, origin, size, tile = FACES[face]
        u, v, origin, size = map(np.array, (u, v, origin, size))
        n = np.cross(u, v)
        dim = TILE - 2*PAD
        depth = np.full((dim, dim), -np.inf)
        maps = {'albedo': np.full((dim, dim, 4), [.14, .14, .14, 1.]),
                'normal': np.full((dim, dim, 3), [.5, .5, 1.]),
                'orm': np.full((dim, dim, 3), [.65, .6, 0.])}
        for material, vertices, _, triangles in primitives(source):
            tex = textures[material]
            for indices in triangles:
                tri = vertices[indices]
                if tri[0, 3:6] @ n < 1e-5:
                    continue
                relative = tri[:, :3] - origin
                xy = np.stack((relative @ u / size[0] + .5, .5 - relative @ v / size[1]), 1) * dim
                low = np.maximum(np.floor(xy.min(0)).astype(int), 0)
                high = np.minimum(np.ceil(xy.max(0)).astype(int), dim-1)
                if np.any(high < low):
                    continue
                xx, yy = np.meshgrid(np.arange(low[0], high[0]+1)+.5, np.arange(low[1], high[1]+1)+.5)
                matrix = np.array([xy[0]-xy[2], xy[1]-xy[2]]).T
                if abs(np.linalg.det(matrix)) < 1e-8:
                    continue
                ab = (np.stack((xx, yy), -1) - xy[2]) @ np.linalg.inv(matrix).T
                weights = np.concatenate((ab, 1-ab.sum(-1, keepdims=True)), -1)
                z = weights @ (tri[:, :3] @ n)
                region = np.s_[low[1]:high[1]+1, low[0]:high[0]+1]
                mask = (weights.min(-1) >= -1e-6) & (z > depth[region])
                if not mask.any():
                    continue
                uv = weights @ tri[:, 10:12]
                colour = weights @ linear(tri[:, 6:9])
                painted = material == 'containers'
                if painted:
                    colour /= linear(PAINT)
                rgb = display(linear(sample(tex['albedo'], uv)) * colour)
                albedo = np.concatenate((rgb, np.full((*rgb.shape[:2], 1), float(painted))), -1)
                # Transform the source tangent normal into this face's UV basis.
                edge = tri[1:3, :3] - tri[0, :3]
                delta_uv = tri[1:3, 10:12] - tri[0, 10:12]
                normal = tri[0, 3:6]
                if abs(np.linalg.det(delta_uv)) > 1e-9:
                    tangent, bitangent = np.linalg.solve(delta_uv, edge)
                    tangent /= np.linalg.norm(tangent)
                    bitangent /= np.linalg.norm(bitangent)
                    sampled = sample(tex['normal'], uv) * 2 - 1
                    world = sampled[..., :1]*tangent + sampled[..., 1:2]*bitangent + sampled[..., 2:3]*normal
                else:
                    world = np.broadcast_to(normal, (*uv.shape[:2], 3))
                world = world / np.maximum(np.linalg.norm(world, axis=-1, keepdims=True), 1e-8)
                baked_normal = np.stack((world @ u, -(world @ v), world @ n), -1) * .5 + .5
                for key, value in [('albedo', albedo), ('normal', baked_normal), ('orm', sample(tex['orm'], uv))]:
                    maps[key][region][mask] = value[mask]
                depth[region][mask] = z[mask]
        row, col = divmod(tile, 2)
        for key in atlas:
            atlas[key][row*TILE:(row+1)*TILE, col*TILE:(col+1)*TILE] = np.pad(maps[key], ((PAD, PAD), (PAD, PAD), (0, 0)), mode='edge')
    output.mkdir(parents=True, exist_ok=True)
    for key, pixels in atlas.items():
        Image.fromarray(np.round(np.clip(pixels, 0, 1)*255).astype('uint8')).save(output / f'{ATLAS}_{key}.png')
    (output / f'{ATLAS}.tres').write_text(f'''[gd_resource type="StandardMaterial3D" load_steps=4 format=2]
[ext_resource path="{ATLAS}_albedo.png" type="Texture" id=1]
[ext_resource path="{ATLAS}_orm.png" type="Texture" id=2]
[ext_resource path="{ATLAS}_normal.png" type="Texture" id=3]
[resource]
albedo_color = Color(1, 1, 1, 1)
albedo_texture = ExtResource( 1 )
metallic = 1.0
metallic_texture = ExtResource( 2 )
metallic_texture_channel = 2
roughness = 1.0
roughness_texture = ExtResource( 2 )
roughness_texture_channel = 1
normal_enabled = true
normal_scale = 1.0
normal_texture = ExtResource( 3 )
ao_enabled = true
ao_texture = ExtResource( 2 )
ao_texture_channel = 0
''')


class Mesh:
    def __init__(self):
        self.vertices, self.slots, self.parts = [], [], defaultdict(list)
        self.lookup = {}

    def add(self, material, vertices, slots, triangles):
        remap = {}
        for index in np.unique(triangles):
            vertex = vertices[index]
            key = (*np.round(vertex, 6), int(slots[index]))
            if key not in self.lookup:
                self.lookup[key] = len(self.slots)
                self.vertices.extend(map(float, vertex))
                self.slots.append(int(slots[index]))
            remap[index] = self.lookup[key]
        self.parts[material].extend(remap[i] for i in triangles.flat)

    def model(self, name, materials):
        assert 0 < len(self.slots) <= 65535, (name, 'vertex budget', len(self.slots))
        parts = [{'id': f'{name}-{mat}', 'type': 'TRIANGLES', 'indices': indices} for mat, indices in self.parts.items() if indices]
        return {'materials': materials,
                'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                            'vertices': self.vertices, 'slots': self.slots, 'parts': parts}],
                'nodes': [{'id': name, 'parts': [{'meshpartid': f'{name}-{mat}', 'materialid': mat}
                                               for mat, indices in self.parts.items() if indices]}]}


def visible(triangles, vertices, faces):
    centers = vertices[triangles, :3].mean(1)
    distances = np.stack((centers[:, 0]+2.9, 2.9-centers[:, 0], centers[:, 1]+6.6,
                          6.6-centers[:, 1], centers[:, 2], 6-centers[:, 2]), 1)
    names = ('-x', '+x', '-y', '+y', '-z', '+z')
    near = distances <= distances.min(1, keepdims=True) + .06
    return (near & np.array([face in faces for face in names])).any(1)


def far_face(face):
    u, v, center, size, tile = FACES[face]
    u, v, center = map(np.array, (u, v, center))
    normal = np.cross(u, v)
    row, col = divmod(tile, 2)
    vertices = []
    for a, b in [(0, 0), (1, 0), (1, 1), (0, 1)]:
        p = center + u*(a-.5)*size[0] + v*(b-.5)*size[1]
        uv = [(col*TILE + PAD + a*(TILE-2*PAD))/(2*TILE),
              (row*TILE + PAD + (1-b)*(TILE-2*PAD))/(2*TILE)]
        vertices.append([*p, *normal, 1, 1, 1, 1, *uv])
    return np.array(vertices), np.array([[0, 1, 2], [0, 2, 3]])


def middle_face(face):
    """Ten triangles per exposed face: one recessed panel and four connecting rim strips.

    Hardware and rail shading use the existing atlas, so there are no tiny bars,
    separate frame boxes or overlapping faces. The underside stays a single quad.
    """
    outer, triangles = far_face(face)
    if face == '-z':
        return outer, triangles
    size = np.array(FACES[face][3])
    inset = np.array((.28, .28) if face == '+z' else (.44, .5)) / size
    inner = outer.copy()
    for i, corner in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        a, b = inset + np.array(corner) * (1 - 2*inset)
        inner[i] = outer[0] + a*(outer[1]-outer[0]) + b*(outer[3]-outer[0])
        inner[i, :3] -= outer[i, 3:6] * (.08 if face == '+z' else .12)
    # Keep the face's tangent basis: the atlas already contains the frame's normals.
    triangles = [[4, 5, 6], [4, 6, 7]]
    for i in range(4):
        j = (i+1) % 4
        triangles.extend(([i, j, j+4], [i, j+4, i+4]))
    return np.concatenate((outer, inner)), np.array(triangles)


def yard_face(face, level):
    """Six/four/two triangles per wall; frames and doors use the shared atlas.

    Near walls retain a recessed panel between the top and bottom rails. Middle
    walls retain only the top rail. Inset corners meet the adjacent walls, keeping
    the shell closed without separate corner-post or hardware meshes.
    """
    outer, triangles = far_face(face)
    if level == 2 or face in ('+z', '-z'):
        return outer, triangles
    height = FACES[face][3][1]
    rows = [(0, 0), (.5 / height, .12), (1 - .5 / height, .12), (1, 0)] if level == 0 else [
        (0, .12), (1 - .5 / height, .12), (1, 0)]
    vertices = []
    for b, inset in rows:
        for a in (0, 1):
            vertex = outer[0] + a*(outer[1]-outer[0]) + b*(outer[3]-outer[0])
            # Recess both coordinates so adjoining face edges coincide.
            vertex[:2] -= np.sign(vertex[:2]) * inset
            vertices.append(vertex)
    triangles = []
    for i in range(len(rows) - 1):
        bottom, top = 2*i, 2*i + 2
        triangles.extend(((bottom, bottom+1, top+1), (bottom, top+1, top)))
    return np.array(vertices), np.array(triangles)


def near_model(full, medium):
    """Keep the formed frame, with readable castings/hinges instead of subpixel casting cavities."""
    mesh = Mesh()
    for model, wanted in [(full, 'containers'), (medium, 'containers-steel')]:
        for material, vertices, slots, triangles in primitives(model):
            if material == wanted:
                mesh.add(material, vertices, slots, triangles)
    def plate(center, u, v, width, height, shade=.62):
        u, v, center = map(np.array, (u, v, center))
        normal = np.cross(u, v)
        vertices = np.array([[*(center + u*a*width/2 + v*b*height/2), *normal,
                              shade, shade, shade, 1, (a+1)*.015, (b+1)*.015]
                             for a, b in [(-1, -1), (1, -1), (1, 1), (-1, 1)]])
        mesh.add('containers-steel', vertices, np.zeros(4), np.array([[0, 1, 2], [0, 2, 3]]))
    for x in (-1, 1):
        for y in (-1, 1):
            for top in (False, True):
                z = 5.84 if top else .16
                plate((x*2.905, y*6.38, z), (0, x, 0), (0, 0, 1), .44, .32)
                plate((x*2.68, y*6.605, z), (-y, 0, 0), (0, 0, 1), .44, .32)
                plate((x*2.68, y*6.38, 6.005 if top else 0), (1, 0, 0), (0, 1 if top else -1, 0), .44, .44)
        for z in (1.2, 3., 4.8):
            plate((x*2.24, 6.69, z), (-1, 0, 0), (0, 0, 1), .48, .16, .53)
    return mesh.model('container', full['materials'])


def door_seam(model):
    mesh = Mesh()
    for material, vertices, slots, triangles in primitives(model):
        mesh.add(material, vertices, slots, triangles)
    # Two door leaves, divided by a recessed dark gasket behind the locking gear.
    vertices = np.array([[x, 6.532, z, 0, 1, 0, *(PAINT*.24), 1, .025, .025]
                         for x, z in [(.045, .554), (-.045, .554), (-.045, 5.557), (.045, 5.557)]])
    mesh.add('containers', vertices, np.ones(4), np.array([[0, 1, 2], [0, 2, 3]]))
    return mesh.model('container', model['materials'])


def build(output):
    source = [read_glb(HERE / 'source/container.glb', level) for level in (0, 1)]
    for model in source:
        for material in model['materials']:
            for texture in material.get('textures', []):
                texture['filename'] = '../../../textures/structures/common/' + Path(texture['filename']).name
    source[0] = near_model(*source)
    source[0] = door_seam(source[0])
    placements = json.loads((HERE / 'container-placements.json').read_text())
    layouts = json.loads((ROOT / 'data/models/board/scenery/layouts.json').read_text())
    materials = source[0]['materials'] + [{'id': 'containers-far', 'diffuse': [1, 1, 1],
        'roughness': 1, 'metallic': 1, 'extras': {'mmPaintMask': True},
        'textures': [{'id': 'containers-far', 'type': 'DIFFUSE',
                      'filename': f'../../../textures/structures/common/{ATLAS}_albedo.png'}]}]
    bake(source[0], output / 'textures/structures/common')
    report = {}
    for name, boxes in placements.items():
        composition = f'yard/{name}' in layouts
        original = read_glb(YARD / f'{name}.glb')
        other_materials = [m for m in original['materials'] if not m['id'].startswith('containers')]
        levels, counts = {}, []
        for level in range(3):
            detailed = level == 0 and not composition
            mesh = Mesh()
            # Machinery is independent of container detail and is preserved exactly.
            for material, vertices, slots, triangles in primitives(original):
                if not material.startswith('containers'):
                    mesh.add(material, vertices, slots, triangles)
            for box in boxes:
                angle = np.radians(box['rotation'])
                c, s = np.cos(angle), np.sin(angle)
                rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
                if detailed:
                    pieces = list(primitives(source[0]))
                else:
                    pieces = [('containers-far', v, np.zeros(len(v)), t) for f in box['faces']
                              for v, t in [yard_face(f, level) if composition else
                                           middle_face(f) if level == 1 else far_face(f)]]
                for material, vertices, _, triangles in pieces:
                    if detailed:
                        triangles = triangles[visible(triangles, vertices, box['faces'])]
                    if not len(triangles):
                        continue
                    vertices = vertices.copy()
                    # Inset the body very slightly between neighbours: the frame makes a real joint.
                    # The ground stays grounded and stack/prop bounds differ by less than one percent.
                    if name != 'container' and level < 2:
                        vertices[:, :2] *= .995
                        vertices[:, 2] = vertices[:, 2] * .99 + (.03 if box['center'][2] > 0 else 0)
                    vertices[:, :3] = vertices[:, :3] @ rotation.T + box['center']
                    vertices[:, 3:6] = vertices[:, 3:6] @ rotation.T
                    painted = material in ('containers', 'containers-far')
                    if painted:
                        if material == 'containers':
                            vertices[:, 6:9] = display(linear(vertices[:, 6:9]) * linear(box['colour']) / linear(PAINT))
                        else:
                            vertices[:, 6:9] = box['colour']
                    slots = np.full(len(vertices), box['slot'] if painted else 0)
                    mesh.add(material, vertices, slots, triangles)
                if '-z' in box['faces'] and detailed:
                    vertices, triangles = far_face('-z')
                    vertices[:, :3] = vertices[:, :3] @ rotation.T + box['center']
                    vertices[:, 3:6] = vertices[:, 3:6] @ rotation.T
                    vertices[:, 6:9] = box['colour']
                    mesh.add('containers-far', vertices, np.full(4, box['slot']), triangles)
            levels[level] = mesh.model(name, materials + other_materials)
            counts.append({'triangles': sum(len(i)//3 for i in mesh.parts.values()), 'vertices': len(mesh.slots)})
            if composition:
                assert counts[-1]['triangles'] <= YARD_TRIANGLE_BUDGETS[level], (name, level, counts[-1])
        assert counts[0]['triangles'] > counts[1]['triangles'] > counts[2]['triangles'], (name, counts)
        write_glb(output / f'scenery/seaport/yard/{name}.glb', levels=levels, extras=original.get('extras'))
        report[name] = counts
        print(name, [c['triangles'] for c in counts])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/models/board')
    parser.add_argument('--report', type=Path, help='Optional triangle/vertex count report, outside deployed assets')
    args = parser.parse_args()
    report = build(args.output)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
