"""Author the one-way road signs as low-poly GLBs, without Blender.

Run from anywhere with plain Python 3: python3 tools/build_road_signs.py [name ...]

Writes scenery/road/give-way-sign.glb, no-entry-sign.glb and one-way-sign.glb beside the STOP sign
(tools/build_road_controls_blender.py), on the same conventions: physical metres here, 2.8 model units per
metre in the GLB, the readable face towards +Y, the base at Z=0, and a detailed `-lod0` with a simple `-lod1`.
The faces are geometry in flat sign colours, not artwork, so they need no texture and read at any distance:
- give way (yield): an inverted triangle, a red border round a white field;
- no entry (do not enter): a red disc crossed by a white bar;
- one-way road: a blue square with a white arrow pointing ahead.
The game places them where a single-lane, one-way road joins a two-lane one (BoardFeatures#roadControls and
#rampSigns): the give-way sign faces traffic merging from an entrance ramp, the no-entry sign faces the junction at
that ramp's mouth, and the one-way sign faces traffic turning into an exit ramp.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import write_glb  # noqa: E402

OUTPUT = ROOT / 'data/models/board/scenery/road'
MODEL_UNITS_PER_METRE = 2.8
# The plate's back and its face: the face sits a hair in front of the plate, its design a hair in front of that.
PLATE_BACK, PLATE_FRONT, DESIGN = .045, .095, .101

MATERIALS = {
    'metal': {'diffuse': [.53, .56, .58], 'metallic': .55, 'roughness': .5},
    'housing': {'diffuse': [.12, .135, .15], 'metallic': .1, 'roughness': .7},
    'sign red': {'diffuse': [.78, .05, .06], 'metallic': 0, 'roughness': .6},
    'sign white': {'diffuse': [.93, .93, .9], 'metallic': 0, 'roughness': .6},
    'sign blue': {'diffuse': [0, .26, .6], 'metallic': 0, 'roughness': .6},
}


class Mesh:
    """Flat-shaded triangles grouped by material, in authoring metres (Z up)."""

    def __init__(self):
        self.vertices = []
        self.groups = {}

    def triangle(self, material, a, b, c, normal):
        ab = [b[i] - a[i] for i in range(3)]
        ac = [c[i] - a[i] for i in range(3)]
        cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
        if sum(cross[i] * normal[i] for i in range(3)) < 0:
            b, c = c, b
        length = math.sqrt(sum(v * v for v in normal))
        normal = [v / length for v in normal]
        indices = self.groups.setdefault(material, [])
        for point in (a, b, c):
            indices.append(len(self.vertices) // 12)
            self.vertices.extend((*[v * MODEL_UNITS_PER_METRE for v in point], *normal, 1, 1, 1, 1, 0, 0))

    def fan(self, material, outline, normal):
        """A convex outline, in order, facing `normal`."""
        for i in range(1, len(outline) - 1):
            self.triangle(material, outline[0], outline[i], outline[i + 1], normal)

    def box(self, material, centre, size):
        cx, cy, cz = centre
        hx, hy, hz = (s / 2 for s in size)
        for axis in range(3):
            for sign in (-1, 1):
                normal = [0, 0, 0]
                normal[axis] = sign
                u, v = [a for a in range(3) if a != axis]
                corners = []
                for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    point = [cx, cy, cz]
                    half = (hx, hy, hz)
                    point[axis] += sign * half[axis]
                    point[u] += du * half[u]
                    point[v] += dv * half[v]
                    corners.append(point)
                self.fan(material, corners, normal)

    def cylinder(self, material, centre, radius, height, sides):
        cx, cy, cz = centre
        ring = [(cx + radius * math.cos(2 * math.pi * i / sides), cy + radius * math.sin(2 * math.pi * i / sides))
                for i in range(sides)]
        bottom, top = cz - height / 2, cz + height / 2
        self.fan(material, [(x, y, top) for x, y in ring], (0, 0, 1))
        self.fan(material, [(x, y, bottom) for x, y in ring], (0, 0, -1))
        for i in range(sides):
            (x0, y0), (x1, y1) = ring[i], ring[(i + 1) % sides]
            angle = 2 * math.pi * (i + .5) / sides
            normal = (math.cos(angle), math.sin(angle), 0)
            self.fan(material, [(x0, y0, bottom), (x1, y1, bottom), (x1, y1, top), (x0, y0, top)], normal)

    def plate(self, face, back, outline):
        """A sign plate from its convex face outline (x, z): the face towards +Y, its edges and back in `back`."""
        self.fan(face, [(x, PLATE_FRONT, z) for x, z in outline], (0, 1, 0))
        self.fan(back, [(x, PLATE_BACK, z) for x, z in outline], (0, -1, 0))
        count = len(outline)
        cx = sum(x for x, _ in outline) / count
        cz = sum(z for _, z in outline) / count
        for i in range(count):
            (x0, z0), (x1, z1) = outline[i], outline[(i + 1) % count]
            nx, nz = z1 - z0, -(x1 - x0)
            if nx * ((x0 + x1) / 2 - cx) + nz * ((z0 + z1) / 2 - cz) < 0:
                nx, nz = -nx, -nz
            self.fan(back, [(x0, PLATE_BACK, z0), (x1, PLATE_BACK, z1), (x1, PLATE_FRONT, z1), (x0, PLATE_FRONT, z0)],
                     (nx, 0, nz))

    def design(self, material, outline):
        """A convex part of the face's design, just in front of the plate."""
        self.fan(material, [(x, DESIGN, z) for x, z in outline], (0, 1, 0))

    def model(self, name):
        parts = [{'id': name + '/' + key, 'type': 'TRIANGLES', 'indices': indices} for key, indices in self.groups.items()]
        return {'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': self.vertices,
                            'parts': parts}],
                'nodes': [{'id': name, 'parts': [{'meshpartid': name + '/' + key, 'materialid': key}
                                                  for key in self.groups]}],
                'materials': [{'id': key, **MATERIALS[key]} for key in self.groups]}


def pole(mesh, height, detailed):
    """The STOP sign's post (build_road_controls_blender.detailed_pole), or one box in the distance."""
    if detailed:
        mesh.box('metal', (0, 0, .025), (.28, .28, .05))
        mesh.cylinder('metal', (0, 0, height / 2 + .05), .05, height, 8)
        mesh.cylinder('housing', (0, 0, .115), .073, .13, 8)
    else:
        mesh.box('metal', (0, 0, height / 2), (.10, .10, height))


def polygon(centre_z, radius, sides, start):
    return [(radius * math.cos(start + 2 * math.pi * i / sides), centre_z + radius * math.sin(start + 2 * math.pi * i / sides))
            for i in range(sides)]


def give_way(detailed):
    """An inverted equilateral triangle, 900 mm a side, its red border an eighth of its height."""
    mesh = Mesh()
    side, centre = .9, 2.2
    pole(mesh, 2.38, detailed)
    radius = side / math.sqrt(3)
    outline = polygon(centre, radius, 3, -math.pi / 2)
    rim = 'sign white' if detailed else 'metal'
    mesh.plate('sign red', rim, outline)
    mesh.design('sign white', polygon(centre, radius - .2, 3, -math.pi / 2))
    return mesh


def no_entry(detailed):
    """A red disc 750 mm across, crossed by a white bar."""
    mesh = Mesh()
    centre = 2.13
    pole(mesh, 2.08, detailed)
    mesh.plate('sign red', 'sign white' if detailed else 'metal', polygon(centre, .375, 24 if detailed else 12, 0))
    mesh.design('sign white', [(-.28, centre - .065), (.28, centre - .065), (.28, centre + .065), (-.28, centre + .065)])
    return mesh


def one_way(detailed):
    """A blue square 600 mm a side with a white arrow pointing ahead (up)."""
    mesh = Mesh()
    centre = 2.13
    pole(mesh, 2.08, detailed)
    half = .3
    mesh.plate('sign blue', 'sign white' if detailed else 'metal',
               [(-half, centre - half), (half, centre - half), (half, centre + half), (-half, centre + half)])
    mesh.design('sign white', [(-.055, centre - .22), (.055, centre - .22), (.055, centre + .04), (-.055, centre + .04)])
    mesh.design('sign white', [(-.16, centre + .03), (.16, centre + .03), (0, centre + .23)])
    return mesh


BUILDERS = {'give-way-sign': give_way, 'no-entry-sign': no_entry, 'one-way-sign': one_way}


def export(name):
    models = {level: BUILDERS[name](level == 0).model(name) for level in (0, 1)}
    path = OUTPUT / (name + '.glb')
    write_glb(path, levels=models, extras={'mmAuthoring': {
        'metresToModelUnits': MODEL_UNITS_PER_METRE, 'front': '+Y', 'base': 'Z=0', 'source': 'tools/build_road_signs.py'}})
    lods = []
    for level, model in models.items():
        mesh = model['meshes'][0]
        lods.append({'node': f'{name}-lod{level}',
                     'triangles': sum(len(part['indices']) // 3 for part in mesh['parts']),
                     'vertices': len(mesh['vertices']) // 12,
                     'height': round(max(mesh['vertices'][2::12]), 4)})
    return {'file': str(path.relative_to(ROOT)), 'lods': lods, 'bytes': path.stat().st_size}


def main(names=tuple(BUILDERS)):
    return [export(name) for name in names]


if __name__ == '__main__':
    print(json.dumps(main(tuple(sys.argv[1:]) or tuple(BUILDERS)), indent=2))
