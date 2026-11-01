"""The lunar habitat, connected building kits (models/buildings/README.md) in both footprints.

    python tools/buildings/lunar_habitat.py

Writes data/models/buildings/lunar_habitat/lunar_habitat.glb (Angled) and lunar_habitat-square.glb (Square, the
rectangular blocks the printed lunar maps draw), from kit_geometry.footprint's walls and floors: a facade along every
wall, with dark steel piers at its corners and joints; on the ground a concrete base course and footings, on top a
parapet over light roof plating. Both kits are asymmetric (all six corners authored, never turned) so Square facades
and plating keep the board's texture axes; an Angled piece lays its plating along its building (a bend's or junction's
hub changes direction on the corner pieces' cut lines).
Modules: base0 (the ground storey, its windows lit), three storeys above it the runtime picks from per hex and level
(floor0 lit, floor1 dimmed, floor2 lit a window along, so the photographic windows do not stack in columns), and three
roofs with low fittings only (vents and hatches; round on an Angled roof, which cannot know which way its building
runs): as on the printed lunar map, a roof's equipment stands on it as board props (scenery/roofs/*). Piers stand
whole in the piece their foot is in; everything else is cut along the corner pieces' boundaries.
"""
import math
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import write_glb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kit_geometry import (A, DIRECTIONS, EXTEND, LEVEL, MIDPOINTS, NOSE, H, ROOF_INSET, Geometry, clipped,  # noqa: E402
                          footprint, node, normal, rounded, sector, vertex)

MODELS = TOOLS.parent / 'data/models'
NAME = 'lunar_habitat'
OUT = MODELS / 'buildings' / NAME
TEXTURES = os.path.relpath(MODELS / 'board/textures', OUT).replace(os.sep, '/') + '/'
BOARD = {'wall': 'structures/lunar/habitat-wall', 'roof': 'structures/lunar/habitat-roof',
         'pier': 'structures/lunar/habitat-pier', 'concrete': 'structures/lunar/regolith-concrete',
         'steel': 'structures/common/steel', 'grille': 'structures/common/grille'}

# Wall texture: two storeys per repeat up the wall; across, whole repeats per hex column on facades along x (a third
# of one) and per half hex on facades along y (a quarter hex), so Square facades continue across hexes, their three
# window bays about the cladding's own proportions. Roof plating: a hexside's width by half a hex.
REPEAT_UP = 2 * LEVEL
# Where a storey's foot lies in the wall texture: its upper storey's windows are lit, its lower storey's dimmed.
LIT, DIM = -.5, 0.0
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

def face(geometry, material, p, q, n, z0, z1, u0, u1, shade=1.0, v0=None):
    """A vertical face from p to q, facing n; its texture from u0 to u1, one repeat per two storeys up, from v0 at its
    foot (by default by height)."""
    v0 = -z0 / REPEAT_UP if v0 is None else v0
    v1 = v0 - (z1 - z0) / REPEAT_UP
    a0, b0 = vertex(*p, z0, (*n, 0), shade, u0, v0), vertex(*q, z0, (*n, 0), shade, u1, v0)
    b1, a1 = vertex(*q, z1, (*n, 0), 1.0, u1, v1), vertex(*p, z1, (*n, 0), 1.0, u0, v1)
    # a0, b0, b1 faces the right of p to q.
    if (q[1] - p[1]) * n[0] - (q[0] - p[0]) * n[1] > 0:
        geometry.polygon(material, [a0, b0, b1, a1])
    else:
        geometry.polygon(material, [b0, a0, a1, b1])


def deck(x, y, z, shade=1.0, axis=0):
    """A deck vertex, its texture a hexside's width across and half a hex along hex direction `axis` (0, the board's
    north, keeps the board's axes): a run of hexes that way continues, its neighbours whole repeats along."""
    ax, ay = MIDPOINTS[axis][0] / H, MIDPOINTS[axis][1] / H
    return vertex(x, y, z, (0, 0, 1), shade, (x * ay - y * ax) / A, -(x * ax + y * ay) / (H / 2))


def flat(geometry, material, points, z, shade=1.0, axis=0):
    """An upward polygon (counter-clockwise from above), textured along hex direction `axis` (deck)."""
    area = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
               for i in range(len(points)))
    ordered = points if area > 0 else points[::-1]
    geometry.polygon(material, [deck(x, y, z, shade, axis) for x, y in ordered])


def plating_axis(tags, direction):
    """The hex direction (0 n, 1 ne, 2 se) an Angled piece's plating runs along: its first link's; a corner piece
    without one is a hub's side, along the run that passes it (parallel to the chord between its two hexsides)."""
    states = tags[1:].split('-')
    links = [DIRECTIONS.index(states[i + 1]) for i in range(0, len(states), 2) if states[i] == 'link']
    if links:
        return links[0] % 3
    return 0 if direction is None else (direction - 1) % 3


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


def storey(polygons, walls, z0, ground, lod, square, axis, v0=LIT, shift=0.0):
    """A piece's storey from z0, one level high: an interior floor, facades from v0 in the wall texture (LIT or DIM),
    shifted `shift` repeats along, base course and footings on the ground. Returns the geometry to cut and its piers."""
    geometry, piers = Geometry(), []
    z1 = z0 + LEVEL
    for polygon in polygons:
        flat(geometry, 'concrete', polygon, z0 + .05, .8, axis)
    for wall in walls:
        p, q, n = wall.p, wall.q, normal(wall.p, wall.q)
        u0, u1 = wall_u(wall, square)
        face(geometry, 'wall', p, q, n, z0, z1, u0 + shift, u1 + shift, .72 if ground else 1, v0)
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


def roof(polygons, walls, z0, lod, variant, square, axis):
    """A piece's roof at z0: plating and parapet caps along hex direction `axis`, a parapet along every wall, the
    piers' tops, and the variant's fittings in the hex's middle."""
    geometry, piers = Geometry(), []
    for polygon in polygons:
        flat(geometry, 'roof', polygon, z0, axis=axis)
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
        flat(geometry, 'roof', [p, q, d, c], z0 + PARAPET, axis=axis)
        if wall.start == 'corner' or wall.start != 'round' and lod == 0:
            piers.append(pier_at(wall, walls))
    geometry.add(fittings(variant, z0, square))
    return geometry, piers


def outline(x, y, half_x, half_y, round_):
    """A fitting's outline about (x, y): a rectangle, or round (a circle of radius half_x)."""
    if round_:
        return [(x + half_x * math.cos(math.tau * k / 12), y + half_x * math.sin(math.tau * k / 12)) for k in range(12)]
    return [(x - half_x, y - half_y), (x + half_x, y - half_y), (x + half_x, y + half_y), (x - half_x, y + half_y)]


def vent(geometry, z0, x, y, round_=False):
    """A low air vent: a steel box (or drum) under a grille."""
    prism(geometry, 'steel', outline(x, y, 3.0, 2.2, round_), z0, z0 + 1.6)
    prism(geometry, 'grille', outline(x, y, 2.4, 1.6, round_), z0 + 1.6, z0 + 1.8)


def hatch(geometry, z0, x, y, round_=False):
    """A roof hatch: a raised frame, its lid in steel."""
    prism(geometry, 'concrete', outline(x, y, 4.0, 4.0, round_), z0, z0 + .8)
    prism(geometry, 'steel', outline(x, y, 3.2, 3.2, round_), z0 + .8, z0 + 1.0)


def fittings(variant, z0, square):
    """A roof variant's low fittings in the hex's middle, none higher than a vent. A Square roof spreads them over its
    core on the board's axes: 0 two vents and a hatch, 1 a hatch and a vent, 2 a row of three vents. An Angled hex's
    pieces cannot know which way its building runs, so its fittings are round and set without a main axis, within the
    hub every Angled hex has: 0 a hatch ringed by three vents, 1 three vents close together, 2 a hatch."""
    geometry = Geometry()
    if square:
        if variant == 0:
            for x, y in ((-9.0, 18.0), (9.0, -16.0)):
                vent(geometry, z0, x, y)
            hatch(geometry, z0, 0.0, 0.0)
        elif variant == 1:
            hatch(geometry, z0, 6.0, -10.0)
            vent(geometry, z0, -10.0, 14.0)
        else:
            for y in (-14.0, 0.0, 14.0):
                vent(geometry, z0, 0.0, y)
        return geometry
    if variant != 1:
        hatch(geometry, z0, 0.0, 0.0, True)
    if variant != 2:
        radius, start = (10.0, 90.0) if variant == 0 else (5.5, 30.0)
        for k in range(3):
            angle = math.radians(start + 120 * k)
            vent(geometry, z0, radius * math.cos(angle), radius * math.sin(angle), True)
    return geometry


def main():
    for mode, suffix in (('angled', ''), ('square', '-square')):
        square = mode == 'square'
        levels = {}
        for lod in (0, 1):
            meshes, nodes, used, total = [], [], set(), 0
            modules = [('base0', 0, lambda polygons, walls, axis: storey(polygons, walls, 0, True, lod, square, axis))]
            modules += [(f'floor{k}', LEVEL, lambda polygons, walls, axis, v0=v0, shift=shift: storey(
                polygons, walls, LEVEL, False, lod, square, axis, v0, shift))
                for k, (v0, shift) in enumerate(((LIT, 0.0), (DIM, 0.0), (LIT, 1 / 3)))]
            modules += [(f'roof{variant}', 2 * LEVEL, lambda polygons, walls, axis, variant=variant: roof(
                polygons, walls, 2 * LEVEL, lod, variant, square, axis)) for variant in range(3)]
            for role, z0, build in modules:
                for tags, direction, polygons, walls in footprint(mode, LONE, END, turned=False):
                    polygons, walls = rounded(polygons, walls, ROUND)
                    geometry, piers = build(polygons, walls, 0 if square else plating_axis(tags, direction))
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
                materials.append({'id': kind, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
                                  'textures': [{'type': 'DIFFUSE', 'filename': f'{TEXTURES}{BOARD[kind]}_albedo.png'}]})
            levels[lod] = {'materials': materials, 'meshes': meshes, 'nodes': nodes}
            print(f'{mode} lod{lod}: {len(nodes)} pieces, {total} triangles')
        path = OUT / f'{NAME}{suffix}.glb'
        write_glb(path, levels=levels)
        print('written', path, path.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
