"""Shared geometry of the connected corner kits (models/buildings/README.md): the regular board hex, triangles by
material, clipping, the corner pieces' sectors, the two footprints (Angled and Square) and their walls, and reading
and writing kit nodes. No Blender dependency.
"""
import math
import os
import sys
from collections import namedtuple
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import read_glb, write_glb  # noqa: E402

# The regular board hex (README): corners 41.5625 from the centre, edge midpoints 36.
R = 41.5625
A = R / 2
H = 36.0
LEVEL = 18.0
DIRECTIONS = ['n', 'ne', 'se', 's', 'sw', 'nw']
MIDPOINTS = [(0, H), (.75 * R, H / 2), (.75 * R, -H / 2), (0, -H), (-.75 * R, -H / 2), (-.75 * R, H / 2)]
HEX = [(R, 0), (A, H), (-A, H), (-R, 0), (-A, -H), (A, -H)]


class Geometry:
    """Triangles by material, each vertex (x, y, z, nx, ny, nz, r, g, b, a, u, v)."""

    def __init__(self):
        self.parts = {}

    def triangle(self, material, a, b, c):
        self.parts.setdefault(material, []).append((a, b, c))

    def polygon(self, material, points):
        for i in range(1, len(points) - 1):
            self.triangle(material, points[0], points[i], points[i + 1])

    def add(self, other):
        for material, triangles in other.parts.items():
            self.parts.setdefault(material, []).extend(triangles)


def vertex(x, y, z, n, shade, u, v):
    return (x, y, z, n[0], n[1], n[2], shade, shade, shade, 1.0, u, v)


def lerp(a, b, t):
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(len(a)))


def clip(points, keep):
    """Sutherland-Hodgman: the part of the polygon (vertices) where keep(x, y) >= 0, attributes interpolated."""
    result = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        da, db = keep(a[0], a[1]), keep(b[0], b[1])
        if da >= 0:
            result.append(a)
        if (da < 0) != (db < 0) and da != 0 and db != 0:
            result.append(lerp(a, b, da / (da - db)))
    return result if len(result) >= 3 else []


def inside_hex(x, y):
    """>= 0 inside the hex: the least distance inside any of its edges."""
    best = math.inf
    for i in range(6):
        (ax, ay), (bx, by) = HEX[i], HEX[(i + 1) % 6]
        best = min(best, (bx - ax) * (y - ay) - (by - ay) * (x - ax))
    return best


def clipped(geometry, keeps):
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            points = list(triangle)
            for keep in keeps:
                points = clip(points, keep)
                if not points:
                    break
            if points:
                result.polygon(material, points)
    return result


def cells(mask):
    """The cells over the hex for a connection mask: (x0, x1, y0, y1, whether a cell continues each edge S, E, N, W)."""
    linked = [bool(mask & 1 << d) for d in range(6)]
    n, ne, se, s, sw, nw = linked
    result = [(-A, A, 0, H, (True, ne, n, nw)), (-A, A, -H, 0, (s, se, True, sw))]
    if ne:
        result.append((A, 2 * A, 0, H, (se, True, True, True)))
    if se:
        result.append((A, 2 * A, -H, 0, (True, True, ne, True)))
    if sw:
        result.append((-2 * A, -A, -H, 0, (True, True, nw, True)))
    if nw:
        result.append((-2 * A, -A, 0, H, (sw, True, True, True)))
    return result


NORMALS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


def corners(cell):
    x0, x1, y0, y1, _ = cell
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def sector(direction):
    """The corner piece between direction and the next one clockwise: the keep functions of its two cut lines."""
    (ax, ay), (bx, by) = MIDPOINTS[direction], MIDPOINTS[(direction + 1) % 6]
    return [lambda x, y: -(ax * y - ay * x), lambda x, y: -(x * by - y * bx)]


def in_sector(direction, point):
    return all(keep(*point) >= 0 for keep in sector(direction))


# The Angled footprint (the classic exits art): a linked hexside opens from corner to corner, an unlinked one closes
# with two walls meeting on its axis NOSE from the centre, where the neighbouring arms' walls cross. A corner piece holds
# at most one wall, NOSE long, from an axis point to an axis point or a hex corner. The Square footprint stands on the
# cells. A kit is one footprint: <name>.glb Angled, <name>-square.glb Square.
NOSE = 2 * H / 3
# The corner pieces' cut lines: through the centre and the edge midpoints (the board hex is regular only to a 32nd, so
# they follow its midpoints, as sector() does, not exact sixths of a turn).
AXES = [(x / math.hypot(x, y), y / math.hypot(x, y)) for x, y in MIDPOINTS[:3]]
# A wall from p to q with the building on its left. Each end meets the next wall: 'cut' on a corner piece's cut line
# (the next wall stands in the next piece, at any angle: extend it and let the cut mitre it), 'joint' on a cut line
# within a whole-hex piece (the wall goes straight on), 'corner' at a turn to another wall of the piece (`keeps` hold
# its mitres), 'open' at a hexside the building continues across. `front`: on a whole-hex piece's front (its outline's
# first edge: the lone hex's south side, a band's far end), where an entrance belongs.
Wall = namedtuple('Wall', 'p q start end keeps front', defaults=(False,))


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def normal(p, q):
    """The outward normal of a wall from p to q: its right."""
    length = math.hypot(q[0] - p[0], q[1] - p[1])
    return (q[1] - p[1]) / length, -(q[0] - p[0]) / length


def turn_point(point, direction):
    """A point turned clockwise by `direction` sixths about the hex centre."""
    angle = -math.radians(60 * direction)
    c, s = math.cos(angle), math.sin(angle)
    return point[0] * c - point[1] * s, point[0] * s + point[1] * c


def close(a, b):
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


def on_axis(point):
    return math.hypot(*point) > 1e-6 and any(abs(cross(axis, point)) < 1e-6 for axis in AXES)


def mitre(corner, n1, n2, inside):
    """The keep function of the mitre at a corner between walls with outward normals n1 and n2, on `inside`'s side."""
    b = (n1[0] + n2[0], n1[1] + n2[1])
    sign = 1 if cross(b, (inside[0] - corner[0], inside[1] - corner[1])) >= 0 else -1
    return lambda x, y: sign * cross(b, (x - corner[0], y - corner[1]))


def split(p, q):
    """Segment p-q cut where it crosses the cut lines: its points in order."""
    d = (q[0] - p[0], q[1] - p[1])
    ts = sorted(-cross(axis, p) / cross(axis, d) for axis in AXES
                if abs(cross(axis, d)) > 1e-12 and 1e-6 < -cross(axis, p) / cross(axis, d) < 1 - 1e-6)
    return [p, *(lerp(p, q, t) for t in ts), q]


def segment_in_hex(p, q):
    """The part of segment p-q within the hex, or None."""
    t0, t1 = 0.0, 1.0
    for i in range(6):
        (ax, ay), (bx, by) = HEX[i], HEX[(i + 1) % 6]
        fp = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        fq = (bx - ax) * (q[1] - ay) - (by - ay) * (q[0] - ax)
        if fp < -1e-9 and fq < -1e-9:
            return None
        if fp < -1e-9:
            t0 = max(t0, fp / (fp - fq))
        elif fq < -1e-9:
            t1 = min(t1, fp / (fp - fq))
    return (lerp(p, q, t0), lerp(p, q, t1)) if t1 - t0 > 1e-6 else None


def hex_corner(direction):
    """The hex corner between `direction` and the next direction clockwise."""
    return HEX[(1 - direction) % 6]


def angled(direction, first, second):
    """The Angled corner piece between `direction` and the next direction clockwise, linked across each or not: its
    floor polygons and walls, on the hex's own points (an unlinked side's walls meet two thirds of the way to its
    midpoint)."""
    following = (direction + 1) % 6
    mid0, mid1, corner = MIDPOINTS[direction], MIDPOINTS[following], hex_corner(direction)
    nose0 = (MIDPOINTS[direction][0] * 2 / 3, MIDPOINTS[direction][1] * 2 / 3)
    nose1 = (MIDPOINTS[following][0] * 2 / 3, MIDPOINTS[following][1] * 2 / 3)
    if first and second:
        return [[(0, 0), mid1, corner, mid0]], []
    if first:
        return [[(0, 0), nose1, corner, mid0]], [Wall(nose1, corner, 'cut', 'open', [])]
    if second:
        return [[(0, 0), mid1, corner, nose0]], [Wall(corner, nose0, 'open', 'cut', [])]
    return [[(0, 0), nose1, nose0]], [Wall(nose1, nose0, 'cut', 'cut', [])]


def square_walls(mask):
    """The Square footprint's walls for a hex's connections: each cell edge no cell continues, within the hex,
    collinear edges joined, cut on the cut lines."""
    runs = []
    for cell in cells(mask):
        outline = corners(cell)
        for edge in range(4):
            if not cell[4][edge]:
                inside = segment_in_hex(outline[edge], outline[(edge + 1) % 4])
                if inside:
                    runs.append(inside)
    joined = True
    while joined:
        joined = False
        for i, j in ((i, j) for i in range(len(runs)) for j in range(len(runs)) if i != j):
            (a, b), (c, d) = runs[i], runs[j]
            if close(b, c) and max(abs(x - y) for x, y in zip(normal(a, b), normal(c, d))) < 1e-9:
                runs[i] = (a, d)
                del runs[j]
                joined = True
                break
    segments = [(points[k], points[k + 1]) for a, b in runs for points in [split(a, b)] for k in range(len(points) - 1)]
    walls = []
    for p, q in segments:
        kinds, keeps = [], []
        for point, inside in ((p, q), (q, p)):
            other = next(((r, s) for r, s in segments if (r, s) != (p, q) and (close(r, point) or close(s, point))),
                         None)
            if on_axis(point):
                kinds.append('cut')
            elif other:
                kinds.append('corner')
                keeps.append(mitre(point, normal(p, q), normal(*other), inside))
            else:
                kinds.append('open')
        walls.append(Wall(p, q, kinds[0], kinds[1], keeps))
    return walls


def square(direction, first, second):
    """The Square corner piece between `direction` and the next direction clockwise: its floor polygons (the cells
    within it) and walls."""
    mask = first << direction | second << (direction + 1) % 6
    polygons = []
    for cell in cells(mask):
        points = corners(cell)
        for keep in [inside_hex, *sector(direction)]:
            points = clip(points, keep)
            if not points:
                break
        if points:
            polygons.append(points)
    walls = [w for w in square_walls(mask) if in_sector(direction, lerp(w.p, w.q, .5))]
    return polygons, walls


def outline_walls(points, open_edges):
    """The walls round a convex outline (counter-clockwise) but on its open edges (edge i runs from point i): joints
    on the cut lines, mitred at its corners."""
    count = len(points)
    walls = []
    for i in range(count):
        if i in open_edges:
            continue
        p, q = points[i], points[(i + 1) % count]
        n = normal(p, q)
        before, after = (i - 1) % count, (i + 1) % count
        pieces = split(p, q)
        for k in range(len(pieces) - 1):
            a, b = pieces[k], pieces[k + 1]
            start, end, keeps = 'joint', 'joint', []
            if k == 0:
                start = 'open' if before in open_edges else 'corner'
                if start == 'corner':
                    keeps.append(mitre(p, normal(points[before], p), n, b))
            if k == len(pieces) - 2:
                end = 'open' if after in open_edges else 'corner'
                if end == 'corner':
                    keeps.append(mitre(q, n, normal(q, points[(i + 2) % count]), a))
            walls.append(Wall(a, b, start, end, keeps, i == 0))
    return walls


def inset(polygon, walls, by):
    """A floor polygon kept `by` inside each wall that stands on one of its edges."""
    for wall in walls:
        mid = lerp(wall.p, wall.q, .5)
        n = normal(wall.p, wall.q)
        on = any(abs(cross((b[0] - a[0], b[1] - a[1]), (mid[0] - a[0], mid[1] - a[1]))) < 1e-4 * math.dist(a, b)
                 and min(a[0], b[0]) - 1e-6 <= mid[0] <= max(a[0], b[0]) + 1e-6
                 and min(a[1], b[1]) - 1e-6 <= mid[1] <= max(a[1], b[1]) + 1e-6
                 for a, b in zip(polygon, polygon[1:] + polygon[:1]))
        if on:
            polygon = clip(polygon, lambda x, y, p=wall.p, n=n: -((x - p[0]) * n[0] + (y - p[1]) * n[1]) - by)
            if not polygon:
                return []
    return polygon


def rounded(polygons, walls, radius, segments=4):
    """A piece's walls with every convex corner within it rounded to `radius`: both walls stop short and an arc of
    `segments` walls ('round' ends) turns between them; the floor polygon holding the corner is cut to the arc."""
    result = list(walls)
    for first in walls:
        second = next((w for w in walls if first.end == 'corner' and close(w.p, first.q)), None)
        if second is None:
            continue
        u1, u2 = direction_of(first), direction_of(second)
        turn = cross(u1, u2)
        if turn <= 1e-6:
            continue
        angle = math.atan2(turn, u1[0] * u2[0] + u1[1] * u2[1])
        reach = radius * math.tan(angle / 2)
        corner = first.q
        a = (corner[0] - u1[0] * reach, corner[1] - u1[1] * reach)
        b = (corner[0] + u2[0] * reach, corner[1] + u2[1] * reach)
        centre = (a[0] - u1[1] * radius, a[1] + u1[0] * radius)
        start = math.atan2(a[1] - centre[1], a[0] - centre[0])
        arc = [(centre[0] + radius * math.cos(start + angle * k / segments),
                centre[1] + radius * math.sin(start + angle * k / segments)) for k in range(segments + 1)]
        arc[0], arc[-1] = a, b
        index = result.index(first)
        result[index] = Wall(first.p, a, first.start, 'round', [], first.front)
        index = result.index(second)
        result[index] = Wall(b, second.q, 'round', second.end, [], second.front)
        result += [Wall(arc[k], arc[k + 1], 'round', 'round', []) for k in range(segments)]
        keeps = [lambda x, y, p=arc[k], q=arc[k + 1]: cross((q[0] - p[0], q[1] - p[1]), (x - p[0], y - p[1]))
                 for k in range(segments)]
        polygons = [clipped_polygon(polygon, keeps) if any(close(point, corner) for point in polygon) else polygon
                    for polygon in polygons]
    return polygons, result


def direction_of(wall):
    length = math.dist(wall.p, wall.q)
    return (wall.q[0] - wall.p[0]) / length, (wall.q[1] - wall.p[1]) / length


def clipped_polygon(points, keeps):
    for keep in keeps:
        points = clip(points, keep)
        if not points:
            return []
    return points


def footprint(mode, lone=None, end=None, turned=True):
    """Every piece a kit of footprint `mode` ('angled' or 'square') authors: (tags, corner direction or None for a
    whole hex, floor polygons, walls). An Angled kit adds its whole-hex pieces: alone (the kit's `lone` outline,
    counter-clockwise from its front) and with one link (a hexside wide band, ending `end` short of the far hexside,
    its front). Turned (the default), it is symmetric: its north/north-east corner pieces and a band linked north,
    which the runtime turns to every corner and link, its floors on the board's axes at runtime (mmBoardUV). A kit
    whose pieces hold something placed in the hex (roof gear) is not turned: its pieces stand in all six corners, its
    bands in all six directions, as the Square cells' always do."""
    symmetric = mode == 'angled' and turned
    result = []
    for direction in range(1 if symmetric else 6):
        following = (direction + 1) % 6
        for state in range(4):
            first, second = state & 1, state >> 1
            tags = (f"-{'link' if first else 'end'}-{DIRECTIONS[direction]}"
                    f"-{'link' if second else 'end'}-{DIRECTIONS[following]}")
            polygons, walls = (angled if mode == 'angled' else square)(direction, first, second)
            result.append((tags, direction, polygons, walls))
    if mode == 'angled':
        result.append((''.join(f'-end-{d}' for d in DIRECTIONS), None, [lone], outline_walls(lone, set())))
        band = [(-A, -H + end), (A, -H + end), (A, H), (-A, H)]
        for direction in range(1 if symmetric else 6):
            # Its open side on the hex's own corners, where the neighbour's walls meet it.
            outline = [turn_point(p, direction) for p in band[:2]] + [hex_corner(direction),
                                                                      hex_corner((direction + 5) % 6)]
            tags = ''.join(f"-{'link' if d == direction else 'end'}-{DIRECTIONS[d]}" for d in range(6))
            result.append((tags, None, [outline], outline_walls(outline, {2})))
    return result


def flat(geometry, material, polygon, z, repeat):
    """An upward polygon on the board's texture axes (board_uv), shading 1."""
    if len(polygon) < 3:
        return
    area = sum(polygon[i][0] * polygon[(i + 1) % len(polygon)][1] - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
               for i in range(len(polygon)))
    ordered = polygon if area > 0 else polygon[::-1]
    geometry.polygon(material, [(x, y, z, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, *board_uv(x, -y, repeat))
                                for x, y in ordered])


def board_uv(x, y, repeat):
    """Texture coordinates along the board's axes that continue across every hexside of every hex: about `repeat`
    units a repeat, whole repeats per hex column across and per half hex up."""
    across, up = max(1, round(1.5 * R / repeat)), max(1, round(H / repeat))
    return x * across / (1.5 * R), y * up / H


def to_facade(geometry, origin, along, out):
    """Geometry moved into a facade frame (framed's inverse): x out of the facade at `origin`, y along it."""
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            placed = []
            for v in triangle:
                rx, ry = v[0] - origin[0], v[1] - origin[1]
                placed.append((rx * out[0] + ry * out[1], rx * along[0] + ry * along[1], v[2],
                               v[3] * out[0] + v[4] * out[1], v[3] * along[0] + v[4] * along[1], v[5], *v[6:]))
            result.triangle(material, *placed)
    return result


# How far a facade goes on past a cut or corner end, for its mitre to trim.
EXTEND = 10.0


# A roof's parapet stands this far inside its wall line: where a storey goes on above it (a whole hex's run stops
# under the corner pieces' hub), that storey's facade stands in front of it, never in one plane with it.
ROOF_INSET = .12


def facade(wall, run, planar=None, inset=0.0):
    """A wall's facade: `run(length, before, after)` gives the modules it lays, [(start along the wall, geometry in the
    facade frame, stretch)]. A cut or corner end goes on EXTEND past (the corner piece's cut or the wall's mitre trims
    it), an open or joint end stops square. `planar`, {material: units a repeat}: those materials textured along the
    wall from its start, so their texture runs on across the modules. Returns the facade and how far it goes on before
    and after the wall. `inset`: how far inside the wall line the modules stand.
    """
    length = math.dist(wall.p, wall.q)
    along = ((wall.q[0] - wall.p[0]) / length, (wall.q[1] - wall.p[1]) / length)
    out = normal(wall.p, wall.q)
    before = EXTEND if wall.start in ('cut', 'corner') else 0.0
    after = EXTEND if wall.end in ('cut', 'corner') else 0.0
    laid = Geometry()
    for start, geometry, scale in run(length, before, after):
        laid.add(framed(geometry, (wall.p[0] + along[0] * start - out[0] * inset,
                                   wall.p[1] + along[1] * start - out[1] * inset), along, out, scale))
    # Textured along the wall's line from the hex centre's foot on it, so collinear walls run on.
    foot = (wall.p[0] - along[0] * (wall.p[0] * along[0] + wall.p[1] * along[1]),
            wall.p[1] - along[1] * (wall.p[0] * along[0] + wall.p[1] * along[1]))
    for material, repeat in (planar or {}).items():
        laid.parts[material] = [tuple(planar_uv(v, foot, along, out, triangle, repeat) for v in triangle)
                                for triangle in laid.parts.get(material, [])]
    ends = [lambda x, y: (x - wall.p[0]) * along[0] + (y - wall.p[1]) * along[1] + before,
            lambda x, y: length + after - (x - wall.p[0]) * along[0] - (y - wall.p[1]) * along[1]]
    return clipped(laid, ends + wall.keeps), before, after


def planar_uv(v, origin, along, out, triangle, repeat):
    """A vertex textured in its wall's frame (t along it from `origin`, d out of it, z up), projected along the
    triangle's main axis there: faces out or in take (t, z), faces up or down (t, d), faces along the wall (d, z)."""
    rx, ry = v[0] - origin[0], v[1] - origin[1]
    t, d, z = rx * along[0] + ry * along[1], rx * out[0] + ry * out[1], v[2]
    nx, ny, nz = (sum(w[k] for w in triangle) for k in (3, 4, 5))
    nd, nt = abs(nx * out[0] + ny * out[1]), abs(nx * along[0] + ny * along[1])
    a, b = (t, z) if nd >= max(nt, abs(nz)) else (t, d) if abs(nz) >= nt else (d, z)
    return (*v[:10], a / repeat, -b / repeat)


def framed(geometry, origin, along, out, scale=1.0):
    """Geometry moved from a facade frame (x out of the facade, y along it) to a facade at `origin` running along
    `along` with its outside towards `out`, stretched by `scale` along it."""
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            placed = []
            for v in triangle:
                d, t = v[0], v[1] * scale
                nx, ny = v[3], v[4]
                placed.append((origin[0] + along[0] * t + out[0] * d, origin[1] + along[1] * t + out[1] * d, v[2],
                               along[0] * ny + out[0] * nx, along[1] * ny + out[1] * nx, v[5], *v[6:]))
            result.triangle(material, *placed)
    return result


def modules(path, level):
    """A kit file's modules at a level of detail: {node id: Geometry of its triangles (node-local)}, and materials."""
    model = read_glb(path, level)
    mesh = model['meshes'][0]
    vertices = mesh['vertices']
    parts = {part['id']: part for part in mesh['parts']}
    result = {}
    for node in model['nodes']:
        geometry = Geometry()
        for reference in node['parts']:
            indices = parts[reference['meshpartid']]['indices']
            for i in range(0, len(indices), 3):
                geometry.triangle(reference['materialid'],
                                  *(tuple(vertices[k * 12:k * 12 + 12]) for k in indices[i:i + 3]))
        result[node['id']] = (geometry, node.get('translation'))
    return result, model['materials']


def levels(path):
    """The levels of detail a kit file holds."""
    found = []
    for level in range(4):
        try:
            read_glb(path, level)
            found.append(level)
        except ValueError:
            break
    return found


def turned(geometry, steps):
    """The geometry turned counter-clockwise by `steps` sixths (60 degrees each) about the hex centre."""
    angle = math.radians(60 * steps)
    c, s = math.cos(angle), math.sin(angle)
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            result.triangle(material, *((v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2],
                                         v[3] * c - v[4] * s, v[3] * s + v[4] * c, v[5], *v[6:]) for v in triangle))
    return result


def moved(geometry, dx, dy):
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            result.triangle(material, *((v[0] + dx, v[1] + dy, *v[2:]) for v in triangle))
    return result


def node(name, geometry, translation):
    """One kit node: its parts by material (ids kept), welded vertices."""
    vertices, welded, parts, references = [], {}, [], []
    for index, (material, triangles) in enumerate(sorted(geometry.parts.items())):
        indices = []
        for triangle in triangles:
            for v in triangle:
                key = tuple(round(k, 5) for k in v)
                if key not in welded:
                    welded[key] = len(vertices)
                    vertices.append(list(v))
                indices.append(welded[key])
        parts.append({'id': f'{name}-{index}', 'type': 'TRIANGLES', 'indices': indices})
        references.append({'meshpartid': f'{name}-{index}', 'materialid': material})
    mesh = {'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
            'vertices': [float(x) for v in vertices for x in v], 'parts': parts}
    reference = {'id': name, 'parts': references}
    if translation:
        reference['translation'] = translation
    return mesh, reference


def without_flats(geometry):
    """Facade-frame geometry less the art's floors, roof slab and sidewalk, which a kit lays over its footprint instead:
    upward faces inside the wall line, or low ones out of it."""
    result = Geometry()
    for material, triangles in geometry.parts.items():
        for triangle in triangles:
            up = min(v[5] for v in triangle) > .9
            inside = max(v[0] for v in triangle) < -.5
            low = max(v[2] for v in triangle) < .5 and min(v[0] for v in triangle) > -.01
            if not (up and (inside or low)):
                result.triangle(material, *triangle)
    return result


def slab_height(geometry):
    """The height of a module's largest upward face: the art's roof slab."""
    def area(t):
        return abs((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1]))
    return max((area(t), t[0][2]) for triangles in geometry.parts.values() for t in triangles
               if min(v[5] for v in t) > .9)[1]


def write_kits(source, folder, name, module, lone, end, board):
    """Both footprints of a kit laid out from hand-made art, at the art's levels of detail: <name>.glb (Angled) and
    <name>-square.glb (Square). `module(role, geometry, polygons, walls, direction, level)` lays one piece of an art
    module at that level of detail.
    `board`: every material as the board's, {id: (texture path under models/board/textures, units a repeat on the
    board's axes, or None for the authored UVs)}: the art's own materials and those the kit adds."""
    textures = os.path.relpath(TOOLS.parent / 'data/models/board/textures', folder).replace(os.sep, '/') + '/'
    for mode, suffix in (('angled', ''), ('square', '-square')):
        result = {}
        for level in levels(source):
            nodes, _ = modules(source, level)
            meshes, references = [], []
            for node_name, (geometry, translation) in nodes.items():
                role = node_name.rsplit('-', 1)[1]
                for tags, direction, polygons, walls in footprint(mode, lone, end):
                    piece = module(role, geometry, polygons, walls, direction, level)
                    if not piece.parts:
                        raise ValueError(f'Empty piece {name}-lod{level}-{role}{tags}')
                    mesh, reference = node(f'{name}{suffix}-lod{level}-{role}{tags}', piece, translation)
                    meshes.append(mesh)
                    references.append(reference)
            used = {material for mesh in references for material in (part['materialid'] for part in mesh['parts'])}
            missing = used - set(board)
            if missing:
                raise ValueError(f'No board material for {sorted(missing)}')
            # A board material is found by its albedo image (its .tres beside it); one on the board's axes says so.
            result[level] = {'materials': [
                {'id': kind, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
                 **({'extras': {'mmBoardUV': repeat}} if repeat else {}),
                 'textures': [{'type': 'DIFFUSE', 'filename': f'{textures}{path}_albedo.png'}]}
                for kind, (path, repeat) in board.items() if kind in used], 'meshes': meshes, 'nodes': references}
            print(f'{name}{suffix} lod{level}: {len(references)} pieces')
        path = Path(folder) / f'{name}{suffix}.glb'
        write_glb(path, levels=result)
        print('written', path, path.stat().st_size, 'bytes')
