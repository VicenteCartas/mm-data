"""The lunar habitat, connected building kits (models/buildings/README.md) in both footprints.

    python tools/buildings/lunar_habitat.py

Writes data/models/buildings/lunar_habitat/lunar_habitat.glb (Angled) and lunar_habitat-square.glb (Square, the
rectangular blocks the printed lunar maps draw), from kit_geometry.footprint's walls and floors: a facade along every
wall, with dark steel piers at its corners and joints; on the ground a concrete base course and footings, on top a
parapet over light roof plating on the board's axes. Both kits are asymmetric (all six corners authored, never turned)
so the plating and Square facades keep the board's texture axes. Modules: base0 (the ground storey), floor0 (any storey above, its windows lit), and three roofs (plain
with vents, a skylight bank, tanks and a life support plant from multihex/lunar-equipment.glb). Piers stand whole in
the piece their foot is in; everything else is cut along the corner pieces' boundaries.
"""
import math
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import read_glb, write_glb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_geometry import (A, EXTEND, LEVEL, NOSE, R, H, ROOF_INSET, Geometry, clipped, footprint, node,  # noqa: E402
                          normal, rounded, sector, vertex)

MODELS = TOOLS.parent / 'data/models'
NAME = 'lunar_habitat'
OUT = MODELS / 'buildings' / NAME
TEXTURES = os.path.relpath(MODELS / 'board/textures', OUT).replace(os.sep, '/') + '/'
EQUIPMENT = MODELS / 'buildings/multihex/lunar-equipment.glb'
BOARD = {'wall': 'structures/lunar/habitat-wall', 'roof': 'structures/lunar/habitat-roof',
         'pier': 'structures/lunar/habitat-pier', 'concrete': 'structures/lunar/regolith-concrete'}

# Wall texture: two storeys per repeat up the wall; across, whole repeats per hex column on facades along x (a third
# of one) and per half hex on facades along y (a quarter hex), so Square facades continue across hexes, their three
# window bays about the cladding's own proportions. Roof plating: a hexside's width by half a hex.
REPEAT_UP = 2 * LEVEL
REPEAT_X = A
REPEAT_Y = H / 2
PARAPET, PARAPET_WIDTH = 4.2, 3.2
# Convex corners round off (the printed map's habitats are rounded blocks); the dark steel skirt round the ground
# storey, battered: out at its foot, against the wall at its top.
ROUND = 6.0
SKIRT, SKIRT_OUT = 3.0, 2.4
# The Angled lone hex (a block a hexside wide, short of its north and south hexsides) and a single link's band end.
LONE = [(-A, -34.25), (A, -34.25), (A, 34.25), (-A, 34.25)]
END = 1.75
CORNER_PIER, PIER_HALF, PIER_DEPTH, PIER_CHAMFER = 2.6, 1.8, 2.1, .75
FOOTING_GROW, FOOTING_DEPTH, FOOTING = .9, 3.2, 2.4
COURSE, COURSE_DEPTH = 1.6, .9

def face(geometry, material, p, q, n, z0, z1, u0, u1, shade=1.0):
    """A vertical face from p to q, facing n; its texture from u0 to u1, one repeat per two storeys up."""
    a0, b0 = vertex(*p, z0, (*n, 0), shade, u0, -z0 / REPEAT_UP), vertex(*q, z0, (*n, 0), shade, u1, -z0 / REPEAT_UP)
    b1, a1 = vertex(*q, z1, (*n, 0), 1.0, u1, -z1 / REPEAT_UP), vertex(*p, z1, (*n, 0), 1.0, u0, -z1 / REPEAT_UP)
    # a0, b0, b1 faces the right of p to q.
    if (q[1] - p[1]) * n[0] - (q[0] - p[0]) * n[1] > 0:
        geometry.polygon(material, [a0, b0, b1, a1])
    else:
        geometry.polygon(material, [b0, a0, a1, b1])


def deck(x, y, z, shade=1.0):
    return vertex(x, y, z, (0, 0, 1), shade, x / A, -y / (H / 2))


def flat(geometry, material, points, z, shade=1.0):
    """An upward polygon (counter-clockwise from above), textured along the board's axes."""
    area = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
               for i in range(len(points)))
    ordered = points if area > 0 else points[::-1]
    geometry.polygon(material, [deck(x, y, z, shade) for x, y in ordered])


def prism(geometry, material, outline, z0, z1, faces=None, top=True):
    """An upright prism over a convex outline: its sides (all, or the first `faces`) and its top."""
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    along = 0.0
    for i in range(faces if faces is not None else len(outline)):
        p, q = outline[i], outline[(i + 1) % len(outline)]
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        n = ((q[1] - p[1]) / length, -(q[0] - p[0]) / length)
        if n[0] * ((p[0] + q[0]) / 2 - cx) + n[1] * ((p[1] + q[1]) / 2 - cy) < 0:
            n = (-n[0], -n[1])
        face(geometry, material, p, q, n, z0, z1, along / 12, (along + length) / 12, .8)
        along += length
    if top:
        flat(geometry, material, outline, z1)


def facade_u(point, n):
    """Where a point lies along a facade facing n, from the viewer's left, in wall repeats."""
    return point[1] * n[0] / REPEAT_Y if n[0] else -point[0] * n[1] / REPEAT_X


def pier(geometry, x, y, n, half, z0, z1, footing, lod, top):
    """A dark steel pier facing n at (x, y), its back buried in the wall even at a corner; on a footing on the ground."""
    tx, ty = -n[1], n[0]
    back = -(.6 * half + .3)
    chamfer = PIER_CHAMFER if lod == 0 else 0
    profile = [(half, back), (half, PIER_DEPTH - chamfer), (half - chamfer, PIER_DEPTH), (-half + chamfer, PIER_DEPTH),
               (-half, PIER_DEPTH - chamfer), (-half, back)]
    if not chamfer:
        profile = [profile[0], (half, PIER_DEPTH), (-half, PIER_DEPTH), profile[-1]]
    ring = [(x + tx * a + n[0] * b, y + ty * a + n[1] * b) for a, b in profile]
    front = len(ring) // 2 - 1
    for i in range(len(ring) - 1):
        p, q = ring[i], ring[i + 1]
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        normal = ((q[1] - p[1]) / length, -(q[0] - p[0]) / length)
        if normal[0] * ((p[0] + q[0]) / 2 - x) + normal[1] * ((p[1] + q[1]) / 2 - y) < 0:
            normal = (-normal[0], -normal[1])
        # The front face takes the plate's whole width, the chamfers and sides its edge strip.
        face(geometry, 'pier', p, q, normal, z0, z1, 0, 1 if i == front else .12, .75 if z0 < .01 else 1)
    if top:
        flat(geometry, 'pier', ring, z1)
    if footing:
        grown = half + FOOTING_GROW
        base = [(x + tx * a + n[0] * b, y + ty * a + n[1] * b)
                for a, b in [(grown, back), (grown, FOOTING_DEPTH), (-grown, FOOTING_DEPTH), (-grown, back)]]
        prism(geometry, 'concrete', base, z0, z0 + FOOTING, faces=3)


def wall_u(wall, square):
    """A facade's texture across it: along the board's axes on a Square wall, so facades continue across hexes; from
    the wall's start on an Angled one, a repeat per wall."""
    n = normal(wall.p, wall.q)
    if square:
        return facade_u(wall.p, n), facade_u(wall.q, n)
    return 0.0, math.dist(wall.p, wall.q) / NOSE


def pier_at(wall, walls):
    """The pier at a wall's start: a corner pier facing out of a convex corner it turns in the piece, else a joint pier
    facing out of the wall (a wall's start holds the one pier of every corner and joint)."""
    n = normal(wall.p, wall.q)
    before = next((w for w in walls if wall.start == 'corner' and math.dist(w.q, wall.p) < 1e-6), None)
    if before is not None:
        m = normal(before.p, before.q)
        turn = ((before.q[0] - before.p[0]) * (wall.q[1] - wall.p[1])
                - (before.q[1] - before.p[1]) * (wall.q[0] - wall.p[0]))
        if turn > 0:
            px, py = n[0] + m[0], n[1] + m[1]
            length = math.hypot(px, py)
            return wall.p[0], wall.p[1], (px / length, py / length), CORNER_PIER
    return wall.p[0], wall.p[1], n, PIER_HALF


def storey(polygons, walls, z0, ground, lod, square):
    """A piece's storey from z0, one level high: an interior floor, facades, base course and footings on the ground.
    Returns the geometry to cut and its piers."""
    geometry, piers = Geometry(), []
    z1 = z0 + LEVEL
    for polygon in polygons:
        flat(geometry, 'concrete', polygon, z0 + .05, .8)
    for wall in walls:
        p, q, n = wall.p, wall.q, normal(wall.p, wall.q)
        u0, u1 = wall_u(wall, square)
        face(geometry, 'wall', p, q, n, z0, z1, u0, u1, .72 if ground else 1)
        if ground:
            skirt(geometry, wall, walls, z0)
        if wall.start == 'corner' or wall.start != 'round' and lod == 0:
            piers.append(pier_at(wall, walls))
    return geometry, piers


def offsets(wall, walls):
    """A wall's ends for an offset band along it (skirt, parapet): the outward direction at each end, joined with the
    next round wall's (scaled so the bands meet), and each end moved on past a cut or corner end, which the piece's cut
    or the wall's mitre trims."""
    n = normal(wall.p, wall.q)
    u = ((wall.q[0] - wall.p[0]) / math.dist(wall.p, wall.q), (wall.q[1] - wall.p[1]) / math.dist(wall.p, wall.q))
    ends = []
    for point, kind, sign in ((wall.p, wall.start, -1), (wall.q, wall.end, 1)):
        other = next((w for w in walls if kind == 'round' and math.dist(w.q if sign < 0 else w.p, point) < 1e-6
                      and w is not wall), None)
        if other is not None:
            m = normal(other.p, other.q)
            half = (n[0] + m[0], n[1] + m[1])
            scale = 2 / (half[0] ** 2 + half[1] ** 2)
            ends.append((point, (half[0] * scale, half[1] * scale)))
        elif kind in ('cut', 'corner'):
            ends.append(((point[0] + u[0] * sign * EXTEND, point[1] + u[1] * sign * EXTEND), n))
        else:
            ends.append((point, n))
    return ends


def skirt(geometry, wall, walls, z0):
    """The ground storey's battered dark steel skirt along a wall: from SKIRT_OUT out at its foot up to the wall."""
    n = normal(wall.p, wall.q)
    (p, a), (q, b) = offsets(wall, walls)
    foot = [(p[0] + a[0] * SKIRT_OUT, p[1] + a[1] * SKIRT_OUT), (q[0] + b[0] * SKIRT_OUT, q[1] + b[1] * SKIRT_OUT)]
    slope = math.hypot(SKIRT_OUT, SKIRT)
    facing = (n[0] * SKIRT / slope, n[1] * SKIRT / slope, SKIRT_OUT / slope)
    along = math.dist(p, q) / 12
    geometry.polygon('pier', [vertex(*foot[0], z0, facing, .8, 0, 0), vertex(*foot[1], z0, facing, .8, along, 0),
                              vertex(*q, z0 + SKIRT, facing, 1.0, along, .25), vertex(*p, z0 + SKIRT, facing, 1.0, 0, .25)])


def roof(polygons, walls, z0, lod, variant, equipment, square):
    """A piece's roof at z0: plating, a parapet along every wall with its cap, the piers' tops, and the variant's gear
    in the hex's middle."""
    geometry, piers = Geometry(), []
    for polygon in polygons:
        flat(geometry, 'roof', polygon, z0)
    for wall in walls:
        n = normal(wall.p, wall.q)
        # Its outer face a hair inside the wall line (a storey going on above stands in front of it).
        (p, a), (q, b) = offsets(wall, walls)
        p, q = (p[0] - a[0] * ROOF_INSET, p[1] - a[1] * ROOF_INSET), (q[0] - b[0] * ROOF_INSET, q[1] - b[1] * ROOF_INSET)
        c = (p[0] - a[0] * PARAPET_WIDTH, p[1] - a[1] * PARAPET_WIDTH)
        d = (q[0] - b[0] * PARAPET_WIDTH, q[1] - b[1] * PARAPET_WIDTH)
        u0, u1 = wall_u(wall, square)
        face(geometry, 'wall', p, q, n, z0, z0 + PARAPET, u0, u1)
        face(geometry, 'wall', c, d, (-n[0], -n[1]), z0, z0 + PARAPET, u0, u1)
        flat(geometry, 'roof', [p, q, d, c], z0 + PARAPET)
        if wall.start == 'corner' or wall.start != 'round' and lod == 0:
            piers.append(pier_at(wall, walls))
    geometry.add(gear(variant, z0, equipment, square))
    return geometry, piers


def vents(geometry, z0, square):
    for x, y in ((-9.0, 18.0), (9.0, -16.0)) if square else ((-8.0, 8.0), (8.0, -8.0)):
        prism(geometry, 'steel', [(x - 3, y - 2.2), (x + 3, y - 2.2), (x + 3, y + 2.2), (x - 3, y + 2.2)], z0, z0 + 1.6)
        prism(geometry, 'grille', [(x - 2.4, y - 1.6), (x + 2.4, y - 1.6), (x + 2.4, y + 1.6), (x - 2.4, y + 1.6)],
              z0 + 1.6, z0 + 1.8)
    # A hatch: a raised frame, its lid in steel.
    prism(geometry, 'concrete', [(-4.0, -4.0), (4.0, -4.0), (4.0, 4.0), (-4.0, 4.0)], z0, z0 + .8)
    prism(geometry, 'steel', [(-3.2, -3.2), (3.2, -3.2), (3.2, 3.2), (-3.2, 3.2)], z0 + .8, z0 + 1.0)


def gear(variant, z0, equipment, square):
    """A roof variant's gear in the hex's middle: 0 vents and a hatch, 1 a skylight bank, 2 tanks and a life support
    plant. A Square roof spreads it over its core; an Angled one keeps it within the hub every Angled hex has."""
    geometry = Geometry()
    if variant == 0:
        vents(geometry, z0, square)
    elif variant == 1:
        place(geometry, equipment, 'skylight', 0, 6.0, z0, .78)
        place(geometry, equipment, 'antenna', *((11.0, -22.0) if square else (9.0, -8.0)), z0, .8)
    else:
        place(geometry, equipment, 'tanks', 0, -10.0 if square else -7.0, z0, .72, turn=True)
        place(geometry, equipment, 'plant', 0, 20.0 if square else 8.0, z0, .85)
    return geometry


def place(geometry, equipment, piece, x, y, z, scale, turn=False):
    """A piece of the equipment kit, scaled about its foot, at (x, y, z); turned a quarter where `turn`."""
    for material, triangles in equipment[piece].items():
        for triangle in triangles:
            placed = []
            for v in triangle:
                px, py, nx, ny = v[0], v[1], v[3], v[4]
                if turn:
                    px, py, nx, ny = -py, px, -ny, nx
                placed.append((x + px * scale, y + py * scale, z + v[2] * scale, nx, ny, v[5], *v[6:]))
            geometry.triangle(material, *placed)


def load_equipment(level):
    """The equipment kit's pieces at a level of detail: triangles by material, vertices as read."""
    model = read_glb(EQUIPMENT, level)
    mesh = model['meshes'][0]
    vertices = mesh['vertices']
    parts = {part['id']: part for part in mesh['parts']}
    result, materials = {}, {}
    for node in model['nodes']:
        piece = node['id'].rsplit('-lod', 1)[0]
        triangles = result.setdefault(piece, {})
        for reference in node['parts']:
            indices = parts[reference['meshpartid']]['indices']
            items = triangles.setdefault(reference['materialid'], [])
            for i in range(0, len(indices), 3):
                items.append(tuple(tuple(vertices[k * 12:k * 12 + 12]) for k in indices[i:i + 3]))
    for material in model['materials']:
        materials[material['id']] = material
    return result, materials


def main():
    for mode, suffix in (('angled', ''), ('square', '-square')):
        square = mode == 'square'
        levels = {}
        for lod in (0, 1):
            # Roof gear at the equipment's simpler level: small on a roof, it needs no more.
            equipment, equipment_materials = load_equipment(1)
            meshes, nodes, used, total = [], [], set(), 0
            modules = [('base0', 0, lambda polygons, walls: storey(polygons, walls, 0, True, lod, square)),
                       ('floor0', LEVEL, lambda polygons, walls: storey(polygons, walls, LEVEL, False, lod, square))]
            modules += [(f'roof{variant}', 2 * LEVEL, lambda polygons, walls, variant=variant: roof(
                polygons, walls, 2 * LEVEL, lod, variant, equipment, square)) for variant in range(3)]
            for role, z0, build in modules:
                for tags, direction, polygons, walls in footprint(mode, LONE, END, turned=False):
                    polygons, walls = rounded(polygons, walls, ROUND)
                    geometry, piers = build(polygons, walls)
                    piece = clipped(geometry, sector(direction)) if direction is not None else geometry
                    for x, y, n, half in piers:
                        if role.startswith('roof'):
                            pier(piece, x, y, n, half, z0, z0 + PARAPET + .6, False, lod, True)
                        else:
                            pier(piece, x, y, n, half, z0, z0 + LEVEL, role == 'base0', lod, False)
                    count = sum(len(triangles) for triangles in piece.parts.values())
                    if not count:
                        raise ValueError(f'Empty piece {NAME}-lod{lod}-{role}{tags}')
                    mesh, reference = node(f'{NAME}{suffix}-lod{lod}-{role}{tags}', piece, None)
                    meshes.append(mesh)
                    nodes.append(reference)
                    used |= set(piece.parts)
                    total += count
            materials = []
            for kind in sorted(used):
                if kind in BOARD:
                    materials.append({'id': kind, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
                                      'textures': [{'type': 'DIFFUSE',
                                                    'filename': f'{TEXTURES}{BOARD[kind]}_albedo.png'}]})
                else:
                    source = equipment_materials[kind]
                    materials.append({'id': kind, 'diffuse': source.get('diffuse', [1, 1, 1]), 'roughness': 1,
                                      'metallic': 0, 'textures': [{'type': 'DIFFUSE', 'filename': t['filename']}
                                                                  for t in source.get('textures', [])
                                                                  if t['type'] == 'DIFFUSE']})
            levels[lod] = {'materials': materials, 'meshes': meshes, 'nodes': nodes}
            print(f'{mode} lod{lod}: {len(nodes)} pieces, {total} triangles')
        path = OUT / f'{NAME}{suffix}.glb'
        write_glb(path, levels=levels)
        print('written', path, path.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
