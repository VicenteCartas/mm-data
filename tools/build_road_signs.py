"""Derive the road signs from the STOP sign's GLB, without Blender.

Run from anywhere with plain Python 3 and Pillow: python3 tools/build_road_signs.py [name ...]

Each sign reuses scenery/road/stop-sign.glb (tools/build_road_controls_blender.py) as it ships: its post, base plate and
collar unchanged in both levels of detail, and its plate as it is built, the same thickness and height, the same rim
material in each level, and the same textured face mapped the same way, with only the plate's outline and its artwork
changed. Their sizes follow the STOP plate's: a disc as wide as the octagon across its flats, a square inside that, and
a triangle a little larger, as give-way signs are. The faces are flat artwork in the STOP face's colours and resolution,
written beside its artwork in tools/board-models/:
- give way (yield): an inverted triangle, a red border round a white field;
- no entry (do not enter): a red disc crossed by a white bar;
- one-way road: a blue square with a white arrow pointing ahead;
- no left turn and no right turn: a red ring round a white disc, a black arrow turning that way and a red bar across
  it;
- keep right (pass this side, Vienna Convention D,2): a blue disc with a white arrow pointing down to the right at 45
  degrees;
- direction to be followed (Vienna Convention D,1): a blue disc with a white stem rising to its centre and, from there,
  a white arrow along each way out of a hex junction the sign allows, at its true heading from straight up: hard left
  (120 degrees left), left (60 degrees left), ahead, right (60 degrees right) and hard right (120 degrees right). There
  is one for each of the 31 sets of those ways, direction-sign-<arrows> listing its arrows from the left as hl, l, a, r
  and hr: direction-sign-a, direction-sign-l-a, direction-sign-hl-r, ..., direction-sign-hl-l-a-r-hr.
The game places the first ones where a single-lane, one-way road joins a two-lane one (BoardFeatures#roadControls and
#rampSigns): the give-way sign faces traffic merging from an entrance ramp, the no-entry sign faces the junction at
that ramp's mouth, and the one-way sign faces traffic turning into an exit ramp; a no-turn sign faces traffic that may
not take an exit before the junction. A direction sign tells traffic approaching a junction which of its ways out it
may take, and the keep-right sign which side of an obstacle to pass. The output is deterministic.
"""
import io
import itertools
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from glb_geometry import read_glb, write_glb  # noqa: E402

ROAD = ROOT / 'data/models/board/scenery/road'
ARTWORK = ROOT / 'tools/board-models'
STOP = ROAD / 'stop-sign.glb'
MODEL_UNITS_PER_METRE = 2.8
STRIDE = 12
# The STOP face's artwork: its red and the light ground round the octagon; its letters' white; a sign blue.
RED, GROUND, WHITE, BLUE = (184, 9, 6, 255), (235, 238, 235, 255), (255, 255, 255, 255), (0, 87, 160, 255)
BLACK = (28, 28, 28, 255)
TEXEL, SUPERSAMPLE = 128, 8
# The STOP face's light rim round its red octagon, a share of the face's width.
BORDER = .035
# The ways out of a hex junction from the viewer's left, each at its true heading in degrees clockwise from straight up
# (ahead): hard left, left, ahead, right and hard right.
DIRECTIONS = {'hl': -120, 'l': -60, 'a': 0, 'r': 60, 'hr': 120}
# A direction sign for each set of ways out an approach may take, its arrows listed from the left.
DIRECTION_SIGNS = tuple('direction-sign-' + '-'.join(kept) for count in range(1, len(DIRECTIONS) + 1)
                        for kept in itertools.combinations(DIRECTIONS, count))
BUILT = ('give-way-sign', 'no-entry-sign', 'one-way-sign', 'no-left-turn-sign', 'no-right-turn-sign',
         'keep-right-sign', *DIRECTION_SIGNS)
# The round signs: a disc as wide as the STOP octagon across its flats.
ROUND = ('no-entry-sign', 'no-left-turn-sign', 'no-right-turn-sign', 'keep-right-sign', *DIRECTION_SIGNS)
# The direction signs' arrows, in shares of the face's width: the branch point's height above the face's centre, the
# stem's foot below the centre and the reach of every arrow's tip from the branch point; the shafts' and the heads'
# widths and the heads' length. Neighbouring heads, 60 degrees apart, stay clear of each other and of the stem.
BRANCH, FOOT, REACH = 0, .37, .40
SHAFT, BARB, HEAD = .11, .24, .13


def bare(name):
    """The sign's name without "-sign": its face's file and material are named after it."""
    return name.replace('-sign', '', 1)


def stop_plate():
    """The STOP plate's measures in model units: its face's front and centre, its octagon's radius, its back."""
    model = read_glb(STOP, 0)
    mesh = model['meshes'][0]
    vertices = mesh['vertices']
    face = next(part for part in mesh['parts'] if part['id'].endswith('/stop face'))
    rim = next(part for part in mesh['parts'] if part['id'].endswith('/white'))
    corners = {tuple(vertices[i * STRIDE:i * STRIDE + 3]) for i in face['indices']}
    centre = sum(z for _, _, z in corners) / len(corners)
    return {'front': max(y for _, y, _ in corners), 'back': min(vertices[i * STRIDE + 1] for i in rim['indices']),
            'centre': centre, 'radius': max(math.hypot(x, z - centre) for x, _, z in corners)}


def post(level, measures):
    """The STOP sign's post, base plate and collar at one level, its plate taken away: its triangles by material."""
    model = read_glb(STOP, level)
    mesh = model['meshes'][0]
    if mesh['attributes'] != ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0']:
        raise ValueError('Unexpected STOP sign vertex layout')
    vertices = mesh['vertices']
    bottom = measures['centre'] - measures['radius']
    kept, removed = {}, 0
    for part in mesh['parts']:
        material = part['id'].split('/', 1)[1]
        triangles = [part['indices'][t:t + 3] for t in range(0, len(part['indices']), 3)]
        if material in ('stop face', 'white'):
            removed += len(triangles)
            continue
        # The far level draws its plate's edges and back in the post's metal: those lie in the plate's slab.
        on_plate = [all(vertices[i * STRIDE + 1] >= measures['back'] - 1e-4 and vertices[i * STRIDE + 2] >= bottom - 1e-3
                        for i in triangle) for triangle in triangles]
        removed += sum(on_plate)
        kept[material] = [triangle for triangle, plate in zip(triangles, on_plate) if not plate]
    # The octagon's face (6 triangles), edges (16) and back (6).
    if removed != 28:
        raise ValueError(f'STOP plate at level {level}: removed {removed} triangles, expected 28')
    return vertices, kept, {material['id']: material for material in model['materials']}


def outline(name, measures):
    """The plate's outline (x, z) and the half-width of the square its face's artwork covers, from the STOP plate."""
    centre, radius = measures['centre'], measures['radius']
    flats = radius * math.cos(math.pi / 8)
    if name == 'give-way-sign':
        # About 900 mm a side, point down: the triangle inscribed in the artwork's circle.
        half = radius * 1.14
        points = [(half * math.cos(math.radians(a)), centre + half * math.sin(math.radians(a))) for a in (270, 30, 150)]
    elif name in ROUND:
        half = flats
        points = [(half * math.cos(2 * math.pi * i / 24), centre + half * math.sin(2 * math.pi * i / 24))
                  for i in range(24)]
    else:
        half = flats * .72
        points = [(-half, centre - half), (half, centre - half), (half, centre + half), (-half, centre + half)]
    return points, half


def artwork(name):
    """The face's flat artwork in the STOP face's square, drawn large and reduced so its edges are smooth."""
    size = TEXEL * SUPERSAMPLE
    image = Image.new('RGBA', (size, size), GROUND)
    draw = ImageDraw.Draw(image)

    def at(u, v):
        return u * size, v * size

    # Each design stops a little short of the plate's edge, which keeps the light rim the STOP face has.
    rim = BORDER

    def inset(points, share):
        return [((x - size / 2) * share + size / 2, (y - size / 2) * share + size / 2) for x, y in points]

    def heading(origin, angle, along, across=0.):
        """The point {@code along} from {@code origin} (x right, y up from the face's centre) on a heading
        {@code angle} degrees clockwise from straight up, {@code across} to its right."""
        bearing = math.radians(angle)
        x = origin[0] + along * math.sin(bearing) + across * math.cos(bearing)
        y = origin[1] + along * math.cos(bearing) - across * math.sin(bearing)
        return at(.5 + x, .5 - y)

    def arrow(origin, angle, start, tip, shaft, barb, head):
        """A white arrow from {@code origin} along a heading: its shaft from {@code start} to its head's base, then its
        head out to {@code tip}."""
        base = tip - head
        draw.polygon([heading(origin, angle, start, -shaft / 2), heading(origin, angle, base, -shaft / 2),
                      heading(origin, angle, base, shaft / 2), heading(origin, angle, start, shaft / 2)], fill=WHITE)
        draw.polygon([heading(origin, angle, tip), heading(origin, angle, base, barb / 2),
                      heading(origin, angle, base, -barb / 2)], fill=WHITE)

    if name == 'give-way-sign':
        # Point down, inscribed in the circle the plate's corners lie on (#outline); image rows run downwards.
        corners = [at(.5 + .5 * math.cos(math.radians(a)), .5 - .5 * math.sin(math.radians(a))) for a in (270, 30, 150)]
        draw.polygon(inset(corners, 1 - 2 * rim), fill=RED)
        draw.polygon(inset(corners, .58), fill=WHITE)
    elif name == 'no-entry-sign':
        draw.ellipse([*at(rim, rim), *at(1 - rim, 1 - rim)], fill=RED)
        draw.rectangle([*at(.16, .41), *at(.84, .59)], fill=WHITE)
    elif name in ('no-left-turn-sign', 'no-right-turn-sign'):
        draw.ellipse([*at(rim, rim), *at(1 - rim, 1 - rim)], fill=RED)
        draw.ellipse([*at(.16, .16), *at(.84, .84)], fill=WHITE)
        turn = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        pen = ImageDraw.Draw(turn)
        # Drawn turning left, then mirrored for the right turn: up the middle, then off to the left under an arrowhead.
        pen.rectangle([*at(.53, .40), *at(.63, .78)], fill=BLACK)
        pen.rectangle([*at(.36, .33), *at(.63, .43)], fill=BLACK)
        pen.polygon([at(.20, .38), at(.38, .22), at(.38, .54)], fill=BLACK)
        if name == 'no-right-turn-sign':
            turn = turn.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        image.alpha_composite(turn)
        # The bar runs from top left to bottom right across the arrow, as on each of these signs.
        draw.line([at(.27, .27), at(.73, .73)], fill=RED, width=round(.1 * size))
    elif name == 'one-way-sign':
        draw.rectangle([*at(rim, rim), *at(1 - rim, 1 - rim)], fill=BLUE)
        draw.rectangle([*at(.42, .4), *at(.58, .86)], fill=WHITE)
        draw.polygon([at(.5, .12), at(.78, .44), at(.22, .44)], fill=WHITE)
    elif name == 'keep-right-sign':
        # Pass this side: one arrow pointing down to the right across the disc's centre.
        draw.ellipse([*at(rim, rim), *at(1 - rim, 1 - rim)], fill=BLUE)
        arrow((0, 0), 135, -.35, .35, .13, .38, .22)
    elif name in DIRECTION_SIGNS:
        # Direction to be followed: a stem up from the disc's foot to a branch point at its centre, and from there an
        # arrow along each way out the sign allows, at its true heading.
        draw.ellipse([*at(rim, rim), *at(1 - rim, 1 - rim)], fill=BLUE)
        branch = (0, BRANCH)
        draw.polygon([heading(branch, 0, -FOOT - BRANCH, -SHAFT / 2), heading(branch, 0, 0, -SHAFT / 2),
                      heading(branch, 0, 0, SHAFT / 2), heading(branch, 0, -FOOT - BRANCH, SHAFT / 2)], fill=WHITE)
        # A round joint where the arrows leave the stem.
        draw.ellipse([*at(.5 - SHAFT / 2, .5 - BRANCH - SHAFT / 2), *at(.5 + SHAFT / 2, .5 - BRANCH + SHAFT / 2)],
                     fill=WHITE)
        for code in name.removeprefix('direction-sign-').split('-'):
            arrow(branch, DIRECTIONS[code], 0, REACH, SHAFT, BARB, HEAD)
    else:
        raise ValueError(name)
    buffer = io.BytesIO()
    image.resize((TEXEL, TEXEL), Image.LANCZOS).save(buffer, format='PNG')
    return buffer.getvalue()


def wound(triangle, vertices, normal):
    """A triangle's corners in the order that faces {@code normal}."""
    a, b, c = ([vertices[i * STRIDE + k] for k in range(3)] for i in triangle)
    ab = [b[k] - a[k] for k in range(3)]
    ac = [c[k] - a[k] for k in range(3)]
    cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
    return list(triangle) if sum(cross[k] * normal[k] for k in range(3)) >= 0 else [triangle[0], triangle[2], triangle[1]]


def plate(name, measures, level):
    """The plate built as the STOP plate is: its textured face at the front, its edges and back in the rim material."""
    points, half = outline(name, measures)
    if name in ROUND and level == 1:
        points = points[::2]
    centre, front, back = measures['centre'], measures['front'], measures['back']
    vertices, rim, face = [], [], []

    def vertex(x, y, z, normal, u=0, v=1):
        vertices.extend((x, y, z, *normal, 1, 1, 1, 1, u, v))
        return len(vertices) // STRIDE - 1

    count = len(points)
    cx, cz = sum(x for x, _ in points) / count, sum(z for _, z in points) / count
    # Mapped as the STOP face is: u = .5 - x / 2r, v = .5 + (z - c) / 2r, stored as 1 - v.
    ring = [vertex(x, front, z, (0, 1, 0), .5 - x / (2 * half), .5 - (z - centre) / (2 * half)) for x, z in points]
    for i in range(1, count - 1):
        face.extend(wound((ring[0], ring[i], ring[i + 1]), vertices, (0, 1, 0)))
    ring = [vertex(x, back, z, (0, -1, 0)) for x, z in points]
    for i in range(1, count - 1):
        rim.extend(wound((ring[0], ring[i], ring[i + 1]), vertices, (0, -1, 0)))
    for i in range(count):
        (x0, z0), (x1, z1) = points[i], points[(i + 1) % count]
        nx, nz = z1 - z0, -(x1 - x0)
        if nx * ((x0 + x1) / 2 - cx) + nz * ((z0 + z1) / 2 - cz) < 0:
            nx, nz = -nx, -nz
        length = math.hypot(nx, nz)
        normal = (nx / length, 0, nz / length)
        quad = [vertex(x0, back, z0, normal), vertex(x1, back, z1, normal), vertex(x1, front, z1, normal),
                vertex(x0, front, z0, normal)]
        rim.extend(wound((quad[0], quad[1], quad[2]), vertices, normal))
        rim.extend(wound((quad[0], quad[2], quad[3]), vertices, normal))
    return vertices, rim, face


def model(name, level, measures, image, face_file):
    source, kept, materials = post(level, measures)
    vertices, parts, remap = [], {}, {}
    for material, triangles in kept.items():
        indices = []
        for triangle in triangles:
            for i in triangle:
                if i not in remap:
                    remap[i] = len(vertices) // STRIDE
                    vertices.extend(source[i * STRIDE:(i + 1) * STRIDE])
                indices.append(remap[i])
        parts[material] = indices
    plate_vertices, rim, face = plate(name, measures, level)
    offset = len(vertices) // STRIDE
    vertices.extend(plate_vertices)
    # The STOP sign's rim: white near, its post's metal far.
    parts.setdefault('white' if level == 0 else 'metal', []).extend(i + offset for i in rim)
    face_id = bare(name).replace('-', ' ') + ' face'
    parts[face_id] = [i + offset for i in face]
    stop_face = materials['stop face']
    texture = {key: value for key, value in stop_face['textures'][0].items() if key != 'data'}
    texture.update(id=face_id, filename=face_file, data=image)
    used = {key: materials[key] for key in parts if key in materials}
    used[face_id] = {'id': face_id, 'diffuse': stop_face['diffuse'], 'metallic': stop_face['metallic'],
                     'roughness': stop_face['roughness'], 'textures': [texture]}
    return {'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': vertices,
                        'parts': [{'id': f'{name}/{key}', 'type': 'TRIANGLES', 'indices': indices}
                                  for key, indices in parts.items()]}],
            'nodes': [{'id': name, 'parts': [{'meshpartid': f'{name}/{key}', 'materialid': key} for key in parts]}],
            'materials': list(used.values())}


def export(name):
    measures = stop_plate()
    image = artwork(name)
    face_file = f'road-{bare(name)}-face.png'
    (ARTWORK / face_file).write_bytes(image)
    models = {level: model(name, level, measures, image, face_file) for level in (0, 1)}
    path = ROAD / (name + '.glb')
    write_glb(path, levels=models, extras={'mmAuthoring': {
        'metresToModelUnits': MODEL_UNITS_PER_METRE, 'front': '+Y', 'base': 'Z=0',
        'source': 'tools/build_road_signs.py', 'derivedFrom': 'scenery/road/stop-sign.glb'}})
    lods = []
    for level, built in models.items():
        mesh = built['meshes'][0]
        lods.append({'node': f'{name}-lod{level}', 'triangles': sum(len(part['indices']) // 3 for part in mesh['parts']),
                     'vertices': len(mesh['vertices']) // STRIDE, 'height': round(max(mesh['vertices'][2::STRIDE]), 4)})
    return {'file': str(path.relative_to(ROOT)), 'lods': lods, 'bytes': path.stat().st_size}


def main(names=BUILT):
    return [export(name) for name in names]


if __name__ == '__main__':
    print(json.dumps(main(tuple(sys.argv[1:]) or BUILT), indent=2))
