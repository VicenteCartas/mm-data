"""Builds scenery/military/sandbags.glb: a fortified hex's emplacement where its ground is paved (TO:AUE p.153), built of
sandbags on the pavement, which cannot be dug.

Run: blender -b --factory-startup --python tools/board-models/military/build_sandbags.py [-- <out.glb>]; it writes
data/models/board/scenery/military/sandbags.glb by default.
The strongpoint (build_fortification.py) above ground: sandbag walls 1.83 m high and 1.5 m thick at the base, six
courses of bags at the board's figure scale, battered on both faces, round the hex, open at the +X corner and on the
side behind, at 150 degrees, the hide; a firing notch (a top bag left out) at each of its five fire positions; and round
the centre a vehicle revetment of the same walls, wide enough for a tank at any heading, open toward the entrance and
the hide, curving bag by bag. Near (level 0) a wall is one shell of whole bags, each a photographed bag of its course
(COURSES, sandbag_atlas.py) projected onto it: the bags whose outline shows modelled as pillows (the top course, the
ends, a notch's), the rest flat under the material's strong relief; bags turn round its corners, and at its ends one bag
sags over the shorter course below it before the courses above rake back; about 12,000 triangles. Further out (levels 1
and 2) it is a battered prism under a crowned top that dips at its top course's joints, its ends sloped alike, the
photographs on its faces. Stands as the strongpoint's: `stand-N` behind the notches for the formation slots nearest
them, `vehicle-0` and `vehicle-1` in the revetment, `hide-0`.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import earthworks as ew  # noqa: E402
from glb_geometry import write_glb  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGS[0] if ARGS else ew.MM / 'data/models/board/scenery/military/sandbags.glb'
M = ew.M
HEIGHT = 1.83  # six courses
BASE, TOP = 1.5, 1.15  # the walls' thickness at the ground and at the top
SPAN = 4.172  # the texture's repeat along a wall (sandbag_atlas.py)
# The photographed wall's courses, bottom first (sandbag_atlas.py): each one's bottom and top (metres) and its joints
# along a repeat (fractions of it).
COURSES = [(0.0, 0.319, (0.0458, 0.2804, 0.5284, 0.7813)), (0.319, 0.614, (0.1643, 0.4136, 0.6567, 0.9133)),
           (0.614, 0.923, (0.0415, 0.2944, 0.5418, 0.7947)), (0.923, 1.221, (0.1521, 0.405, 0.6549, 0.9035)),
           (1.221, 1.529, (0.0403, 0.2822, 0.5308, 0.8002)), (1.529, 1.83, (0.1503, 0.4044, 0.6567, 0.9151))]
JOINTS = COURSES[-1][2]  # the top course's
PITCH = SPAN / 4  # a bag's length along the wall, laid
RAKE = 1.5 * PITCH  # how far in from a wall's end its top course begins
FACE_V, TOP_V = 1152 / 2048, 768 / 2048  # the atlas's face rows, then its top's
RING = 10.5  # the perimeter wall's apothem
GAP = 5.0  # its ends either side of the entrance, off the +X axis
REVETMENT = 7.3  # the vehicle revetment's radius: its inner face clears a tank's corners (6.5 m)
NOTCH, NOTCH_DEPTH = .52, .3  # a firing notch's half length along the wall (a top bag left out), and its depth
EDGE = .14  # how far the top's edges round down from its crown: the top course's bags, pillowed
DIP, SHOULDER = .08, .12  # how much lower the top is at its bags' joints, and how far from a joint its bag rounds over
WOBBLE, SLUMP = .035, .05  # each top bag's give across the wall, and how much lower it may sit
PILLOW, CROWN = .13, .1  # how far a bag's front stands out of the grooves round it, and a top bag's crown over them
END = .1  # how far a bag's tied end bulges out where its course stops
TURN = .5  # the radius a bag turns round a corner of the wall on
ALONG = (0, .15, .5, .85, 1)  # where a bag's pillow is sampled from joint to joint (its normal map rounds it between)
UP = (0, .5, 1)  # and from groove to groove up its course
ACROSS = (0, .5, 1)  # and across a top bag, from the wall's edge to its middle
PARK = 2.6
HIDE, HIDE_AT = 150, 12.5
SLOTS = [143, 37, 270, 215, 325, 90]
SANDBAG = {'id': 'fortified-sandbag', 'textures': [{'type': 'DIFFUSE',
                                                     'filename': '../../textures/scenery/fortified-sandbag_albedo.png'}]}
ATTRIBUTES = ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0']


def toward(a, b, y):
    """The point on a to b whose |y| is {@code y}."""
    t = (abs(a[1]) - y) / (abs(a[1]) - abs(b[1]))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def joints_along(length, joints=JOINTS):
    """A course's joints (the top's by default) from a wall's start to {@code length} along it, where its texture
    starts."""
    return [(k + j) * SPAN for k in range(int(length / SPAN) + 1) for j in joints if (k + j) * SPAN < length]


def arc(start, end, radius):
    """An arc of wall from bearing {@code start} to {@code end} (degrees): straight whole bags of its top course
    turning at their joints, each joint a corner of the line, as a curved sandbag wall is laid."""
    count = max(1, round(radius * math.radians(end - start) / PITCH))
    return [(radius * math.cos(a), radius * math.sin(a)) for a in np.radians(np.linspace(start, end, count + 1))]


corners = ew.hexagon(RING)[:6]
PERIMETER = [[toward(corners[1], corners[0], GAP), corners[1], corners[2]],
             [corners[3], corners[4], corners[5], toward(corners[5], corners[0], GAP)]]
REVETMENTS = [arc(35, 115, REVETMENT), arc(185, 325, REVETMENT)]


def slot(bearing):
    return SLOTS.index(min(SLOTS, key=lambda s: abs((bearing - s + 180) % 360 - 180)))


# The fire positions: the middle of each perimeter side, behind its notch, facing out.
POSITIONS = []
for line in PERIMETER:
    for a, b in zip(line, line[1:]):
        a, b = np.array(a), np.array(b)
        middle = (a + b) / 2
        along = (b - a) / np.linalg.norm(b - a)
        out = np.array([along[1], -along[0]])
        if out @ middle < 0:
            out = -out
        POSITIONS.append((middle, out))


class Mesh:
    def __init__(self):
        self.vertices, self.indices = [], []

    def grid(self, points, uvs, outward, shade=(1, 1, 1, 1)):
        """A smooth patch through a grid of (x, y, z) metre points (rows x columns x 3) with their uvs, wound to face
        {@code outward} (a direction from the patch's middle)."""
        rows, cols = points.shape[:2]
        du = np.gradient(points, axis=0)
        dv = np.gradient(points, axis=1)
        normals = np.cross(du, dv)
        if (normals.reshape(-1, 3).sum(0) @ outward) < 0:
            normals = -normals
            flip = True
        else:
            flip = False
        normals /= np.maximum(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-9)
        base = len(self.vertices) // 12
        for point, normal, uv in zip(points.reshape(-1, 3), normals.reshape(-1, 3), uvs.reshape(-1, 2)):
            self.vertices.extend([*(point * M), *normal, *shade, *uv])
        for i in range(rows - 1):
            for j in range(cols - 1):
                a, b, c, d = (base + i * cols + j, base + (i + 1) * cols + j, base + (i + 1) * cols + j + 1,
                              base + i * cols + j + 1)
                self.indices.extend([a, c, b, a, d, c] if flip else [a, b, c, a, c, d])

    def face(self, corners, uvs, normals=None, shade=(1, 1, 1, 1)):
        """A convex face through (x, y, z) metre corners, counter-clockwise seen from outside: flat shaded, or smooth
        with {@code normals} at its corners."""
        p = [np.array(c, float) for c in corners]
        n = np.cross(p[1] - p[0], p[-1] - p[0])
        n /= np.linalg.norm(n)
        base = len(self.vertices) // 12
        for corner, normal, uv in zip(p, normals or [n] * len(p), uvs):
            self.vertices.extend([*(corner * M), *normal, *shade, *uv])
        for i in range(1, len(p) - 1):
            self.indices.extend([base, base + i, base + i + 1])


def pillow(across, slopes, sides):
    """Normals for half the wall's top: tilted along the wall by the top's slope at each corner, so each top bag rounds
    down into its joints, and level across the wall on its crown (side 0), rounding over at its edge (side -1 the outer,
    +1 the inner) as the top course's bags do. {@code across} is each corner's unit vector to the wall's left."""
    normals = []
    for left, slope, side in zip(across, slopes, sides):
        along = np.array([left[1], -left[0], 0.0])
        up = np.array([0, 0, 1.0]) - along * slope
        bent = up / np.linalg.norm(up) + np.array([*left, 0.0]) * side * 1.2
        normals.append(bent / np.linalg.norm(bent))
    return normals


def offsets(points):
    """Each polyline point's mitred unit normal (to the polyline's left) and its arc length."""
    points = [np.array(p, float) for p in points]
    lengths = [0.0]
    for a, b in zip(points, points[1:]):
        lengths.append(lengths[-1] + float(np.linalg.norm(b - a)))
    normals = []
    for i, p in enumerate(points):
        dirs = []
        if i > 0:
            dirs.append((p - points[i - 1]) / np.linalg.norm(p - points[i - 1]))
        if i < len(points) - 1:
            dirs.append((points[i + 1] - p) / np.linalg.norm(points[i + 1] - p))
        lefts = [np.array([-d[1], d[0]]) for d in dirs]
        mean = sum(lefts) / len(lefts)
        mean /= np.linalg.norm(mean)
        # Mitre: keep the wall's thickness through the bend.
        normals.append(mean / max(.5, float(mean @ lefts[0])))
    return points, normals, lengths


def along_line(points, lengths, point):
    """The arc length of the point on a polyline nearest {@code point}."""
    return min(((float(np.linalg.norm(np.array(point) - (points[i] + (points[i + 1] - points[i]) * t))),
                 lengths[i] + t * (lengths[i + 1] - lengths[i]))
                for i in range(len(points) - 1) for t in np.linspace(0, 1, 41)))[1]


def point_at(points, normals, lengths, s):
    """A polyline's point and mitred left normal at arc length {@code s}."""
    i = min(int(np.searchsorted(lengths, s, side='right')) - 1, len(points) - 2)
    t = (s - lengths[i]) / (lengths[i + 1] - lengths[i])
    return points[i] + (points[i + 1] - points[i]) * t, normals[i] * (1 - t) + normals[i + 1] * t


def half(z):
    """The wall's half thickness at height z: its faces' batter."""
    return BASE / 2 - (BASE - TOP) / 2 * z / HEIGHT


def rounded(t, power=.45):
    """A pillow's rise across its width t (0..1 between two grooves): full over its middle, rounding off to nothing at
    its edges, as a filled bag's boxy section does."""
    return np.sin(np.pi * np.clip(t, 0, 1)) ** power


def raked(s, total):
    """The top of a wall's end, s along a wall {@code total} long, as its bags lie (bags()): the sagging third
    course's end, a course down, at its end, rising to the full height where the top course begins."""
    return COURSES[1][1] + (HEIGHT - COURSES[1][1]) * min(1.0, min(s, total - s) / RAKE)


def top_height(s, joints, notches):
    """The wall's top along its length: each bag of its top course a rounded hump between two of {@code joints},
    dipping into them, lowered through a firing notch."""
    i = min(max(int(np.searchsorted(joints, s, side='right')) - 1, 0), len(joints) - 2)
    t = min(max((s - joints[i]) / (joints[i + 1] - joints[i]), 0.0), 1.0)
    z = HEIGHT - DIP * (1 - math.sin(math.pi * t) ** .5)
    for centre in notches:
        d = abs(s - centre)
        if d < NOTCH + .3:
            z -= NOTCH_DEPTH * ew.smooth((NOTCH + .3 - d) / .3)
    return z


def wall(mesh, line, seed, notches_at=(), detailed=True):
    """A sandbag wall along {@code line}: battered faces and a crowned top; where detailed, the top dips at its joints
    and each of its bags gives a little across the wall and sits a little lower, from {@code seed}. Capped at its ends.
    {@code notches_at} are points along it, each the middle of a firing notch."""
    points, normals, lengths = offsets(line)
    total = lengths[-1]
    rng = np.random.default_rng(seed)
    # The top course's joints, one repeat past either end so every bag has two.
    joints = np.array([(j - 1) * SPAN for j in JOINTS] + joints_along(total + SPAN))
    middles = (joints[:-1] + joints[1:]) / 2
    shifts, slumps = rng.uniform(-WOBBLE, WOBBLE, len(middles)), rng.uniform(0, SLUMP, len(middles))

    def give(s, values):
        """A top bag's value at its middle, blended across its joints."""
        return float(np.interp(s, middles, values))

    # Samples along the wall: at the top course's joints, its bags' shoulders either side of them and their middles
    # where detailed, else only at the bends.
    bags = np.concatenate([joints, joints[:-1] + SHOULDER, middles, joints[1:] - SHOULDER])
    rake = {x for x in (RAKE, total - RAKE) if 0 < x < total}
    samples = sorted(set(lengths) | rake | (set(bags[(bags > 0) & (bags < total)]) if detailed else set()))
    # An arc's corners are its joints: one sample each.
    samples = [x for i, x in enumerate(samples) if i == 0 or x - samples[i - 1] > 1e-6]
    notches = [along_line(points, lengths, point) for point in notches_at]

    def at(s):
        return point_at(points, normals, lengths, s)

    def face_v(corner):
        """A face's v at a corner: the face rows run down from the wall's full height."""
        return (1 - corner[2] / HEIGHT) * FACE_V

    def top(s):
        return min(raked(s, total), top_height(s, joints, notches) - give(s, slumps) if detailed else HEIGHT)

    def slope(s, ahead):
        """The top's slope just ahead of or behind {@code s}: a joint's dip is a crease between its bags."""
        step = SHOULDER / 3 * (1 if ahead else -1)
        return (top(s + step) - top(s)) / step

    rows = []
    for s in samples:
        centre, left = at(s)
        across = left / np.linalg.norm(left)
        z = top(s)
        if detailed:
            centre = centre + across * give(s, shifts)
        # Across the wall: the outer foot, the outer edge of the top, its crown, the inner edge, the inner foot.
        rows.append((s, across, [(*(centre - left * BASE / 2), 0), (*(centre - left * TOP / 2), z - EDGE),
                                 (*centre, z), (*(centre + left * TOP / 2), z - EDGE), (*(centre + left * BASE / 2), 0)]))
    out_v, crown_v, in_v = FACE_V + TOP_V * .96, FACE_V + TOP_V / 2, FACE_V + TOP_V * .04
    for (s0, n0, a), (s1, n1, b) in zip(rows, rows[1:]):
        u0, u1 = s0 / SPAN, s1 / SPAN
        # The outer face (right of the line), the top's halves either side of its crown, the inner face.
        mesh.face([a[0], b[0], b[1], a[1]], [(u0, FACE_V), (u1, FACE_V), (u1, face_v(b[1])), (u0, face_v(a[1]))])
        slopes = [slope(s0, True), slope(s1, False), slope(s1, False), slope(s0, True)]
        mesh.face([a[1], b[1], b[2], a[2]], [(u0, out_v), (u1, out_v), (u1, crown_v), (u0, crown_v)],
                  pillow([n0, n1, n1, n0], slopes, [-1, -1, 0, 0]))
        mesh.face([a[2], b[2], b[3], a[3]], [(u0, crown_v), (u1, crown_v), (u1, in_v), (u0, in_v)],
                  pillow([n0, n1, n1, n0], slopes, [0, 0, 1, 1]))
        mesh.face([b[4], a[4], a[3], b[3]], [(u1, FACE_V), (u0, FACE_V), (u0, face_v(a[3])), (u1, face_v(b[3]))])
    # The ends: the start faces back along the wall, the end forward; the bags' ends from the face's rows.
    width = BASE / SPAN
    for (s, _, ring), start in ((rows[0], True), (rows[-1], False)):
        uvs = [(u, face_v(corner)) for u, corner in zip((0, width * .18, width * .5, width * .82, width), ring)]
        mesh.face(ring if start else ring[::-1], uvs if start else uvs[::-1])


def rounded_corners(line):
    """A wall's line with each corner sharper than a bag's own give rounded off on TURN, as the bag crossing it turns;
    and where each corner's middle falls along it."""
    points = [np.array(p, float) for p in line]
    out, middles = [points[0]], []
    for a, v, b in zip(points, points[1:], points[2:]):
        d1, d2 = (v - a) / np.linalg.norm(v - a), (b - v) / np.linalg.norm(b - v)
        angle = math.acos(max(-1.0, min(1.0, float(d1 @ d2))))
        if angle < math.radians(20):
            out.append(v)
            continue
        reach = TURN * math.tan(angle / 2)
        p1, p2 = v - d1 * reach, v + d2 * reach
        for u in np.linspace(0, 1, 7):
            out.append((1 - u) ** 2 * p1 + 2 * u * (1 - u) * v + u * u * p2)
        middles.append(len(out) - 4)
    out.append(points[-1])
    return out, middles


def bags(mesh, line, seed, notches_at=()):
    """A wall near: one shell of pillows, its courses (COURSES) of whole straight bags, each a photographed bag of its
    course standing out of the grooves between them on both faces and rounding over into a pillowed top where nothing
    lies on it. Only what shows is modelled: a face sinks to its grooves between courses and to a seam at each joint,
    nothing lies behind it. Only the bags whose outline shows are modelled so (the top course, a course's end bags,
    those a notch uncovers); the rest are their faces' plane, the material's relief maps all their shape. Each straight
    run of the wall holds whole bags; the bottom course's joints fall on the wall's corners, every other course's half a
    bag on, so the bag across a corner turns round it. At the wall's ends the third course's end bag sags over the
    shorter second onto the bottom one, and above it each course stops half a bag short of the one below, raking
    back. A firing notch is a top bag left out. The face photograph is projected onto the faces and
    the ends' ties, the top's onto the tops."""
    line, corners = rounded_corners(line)
    points, normals, lengths = offsets(line)
    rng = np.random.default_rng(seed + 50)
    notches = [along_line(points, lengths, point) for point in notches_at]
    top = len(COURSES) - 1
    # The bottom course's joints (and every other course's): whole bags in each run between the corners; the others'
    # halfway between.
    runs = [0.0] + [lengths[i] for i in corners] + [lengths[-1]]
    full = [0.0]
    for l0, l1 in zip(runs, runs[1:]):
        count = max(1, round((l1 - l0) / PITCH))
        full += [l0 + (l1 - l0) * (k + 1) / count for k in range(count)]
    full = np.array(full)
    # Each course's bags: (from, to, which of its course's photographed bags, fullness). At the wall's ends the lowest
    # three run out alike, the middle one half a bag short, so the third's end bag sags over it; above, each course
    # stops half a bag short of the one below, the ends raking back.
    courses = []
    for c in range(len(COURSES)):
        joints = full if c % 2 == 0 else (full[:-1] + full[1:]) / 2
        spans = list(zip(joints, joints[1:]))
        short = max(0, (c - 2) // 2)
        spans = spans[short:len(spans) - short]
        first = rng.integers(4)
        laid = [(a, b, 0, (first + k) % 4, rng.uniform(.85, 1.1)) for k, (a, b) in enumerate(spans)]
        if c == top:
            laid = [bag for bag in laid if not any(abs((bag[0] + bag[1]) / 2 - n) < NOTCH for n in notches)]
        courses.append(laid)

    def missing(c, a, b):
        """The parts of a..b where course c has no bag (all of it past the bottom or the top)."""
        parts = [(a, b)]
        for a1, b1, *_ in courses[c] if 0 <= c <= top else ():
            parts = [piece for p0, p1 in parts for piece in ((p0, min(p1, a1)), (max(p0, b1), p1))
                     if piece[1] - piece[0] > 1e-3]
        return parts

    def open_above(c, s):
        """Whether nothing lies on course c at s (a bag above ending exactly there counts as nothing)."""
        return c == top or not any(a + 1e-4 < s < b - 1e-4 for a, b, *_ in courses[c + 1])

    def sag(c, a, b, S):
        """How far a bag sags where it overhangs the course below, at S: from that course's end, where it still lies
        flat, to its own, resting on the course under that."""
        drop = np.zeros(len(S))
        for e0, e1 in missing(c - 1, a, b) if c > 0 else ():
            d = np.clip((e1 - S) / (e1 - e0) if e0 <= a + 1e-6 else (S - e0) / (e1 - e0), 0, 1)
            drop = np.maximum(drop, (COURSES[c - 1][1] - COURSES[c - 1][0]) * d * d * (3 - 2 * d))
        return drop

    def samples(c, a, b, within=None):
        """Where a bag's surface is sampled along the wall, within a part of it: its pillow's, the line's turns and,
        where it sags over an end, its bend."""
        e0, e1 = within or (a, b)
        bend = {x for g0, g1 in (missing(c - 1, a, b) if c > 0 else ()) for x in np.linspace(g0, g1, 5)}
        along = {a + (b - a) * f for f in ALONG} | set(lengths) | {e0, e1} | bend
        along = sorted(x for x in along if e0 - 1e-6 <= x <= e1 + 1e-6)
        return np.array([x for i, x in enumerate(along) if i == 0 or x - along[i - 1] > 1e-4])

    def frame(c, k, a, b, S):
        """Points and mitred left normals along the wall's line at S."""
        centres, lefts = zip(*(point_at(points, normals, lengths, x) for x in S))
        return np.array(centres), np.array(lefts)

    def fullness(S, a, b, amount):
        """A bag's pillow along it: rounding into its seams at its ends, where its neighbours meet it alike."""
        t = rounded((S - a) / (b - a), .3)
        return (.3 + .7 * t) * (1 + (amount - 1) * t)

    def face_points(c, k, S, a, b, amount, side):
        """Up a bag's face from the groove below: back into the groove above, or, where nothing lies on it, rounding
        over toward its top."""
        z0, z1 = COURSES[c][:2]
        t = np.array(UP)
        full_ = fullness(S, a, b, amount)[:, None]
        open_ = np.array([open_above(c, x) for x in S], float)[:, None]
        over = np.clip((t - .5) / .5, 0, 1) ** 2
        rise = (1 - open_) * rounded(t) + open_ * np.where(t <= .5, rounded(t), 1 - .55 * over)
        out = half(z0 + (z1 - z0) * t)[None, :] - PILLOW + PILLOW * rise * full_
        Z = z0 + (z1 - z0) * t[None, :] + open_ * CROWN * .35 * full_ * over
        centres, lefts = frame(c, k, a, b, S)
        xy = centres[:, None, :] + side * lefts[:, None, :] * out[..., None]
        return np.concatenate([xy, Z[..., None]], -1)

    def top_points(c, k, S, a, b, amount):
        """Across a bag's top from the outer edge to the inner: two rows' pillows meeting in the middle, their edges
        where its faces round over."""
        z1 = COURSES[c][1]
        x = np.concatenate([-1 + np.array(ACROSS), 1 - np.array(ACROSS[::-1][1:])])
        full_ = fullness(S, a, b, amount)[:, None]
        edge = half(z1) - PILLOW + .45 * PILLOW * full_
        Z = z1 + CROWN * full_ * rounded(.969 * np.abs(x))[None, :]
        centres, lefts = frame(c, k, a, b, S)
        xy = centres[:, None, :] + lefts[:, None, :] * (edge * x[None, :])[..., None]
        return np.concatenate([xy, Z[..., None]], -1), x

    def photo_u(S, a, b, joints, which):
        """Along a bag, its photographed bag's u: from that bag's joint to the next."""
        u0 = joints[which]
        u1 = joints[(which + 1) % 4] + (1 if which == 3 else 0)
        return u0 + (S - a) / (b - a) * (u1 - u0)

    def stops(laid, i):
        """Whether course's bag i ends its run at its start, and at its end."""
        a, b = laid[i][:2]
        return i == 0 or laid[i - 1][1] < a - 1e-6, i == len(laid) - 1 or laid[i + 1][0] > b + 1e-6

    def shaped(c, i):
        """Whether a bag is modelled, its outline showing: the top course's, those ending a run and those with nothing
        on part of them."""
        if not 0 <= i < len(courses[c]):
            return True
        a, b = courses[c][i][:2]
        return (c == top or any(stops(courses[c], i)) or bool(missing(c + 1, a, b))
                or (c > 0 and bool(missing(c - 1, a, b))))

    def flat_bag(c, i, a, b, k, which):
        """A bag that is no more than its faces' plane, its photograph's relief maps all its shape; a ledge closes its
        top where the modelled bag above stands back from that plane, and a strip its end where a modelled bag goes
        on."""
        z0, z1, joints = COURSES[c]
        S = np.array(sorted({a, b} | {x for x in lengths if a < x < b}))
        Z = np.array([z0, z1])
        u = photo_u(S, a, b, joints, which)
        centres, lefts = frame(c, k, a, b, S)
        middle = frame(c, k, a, b, np.array([(a + b) / 2]))[1][0]
        for side in (-1, 1):
            xy = centres[:, None, :] + side * lefts[:, None, :] * half(Z)[None, :, None]
            P = np.concatenate([xy, np.broadcast_to(Z, (len(S), 2))[..., None]], -1)
            uv = np.stack([np.broadcast_to(u[:, None], P.shape[:2]),
                           np.broadcast_to((1 - Z / HEIGHT) * FACE_V, P.shape[:2])], -1)
            mesh.grid(P, uv, np.array([*(side * middle), 0]))
            for e0, e1 in covered_by_shaped(c + 1, a, b):
                T = np.array(sorted({e0, e1} | {x for x in lengths if e0 < x < e1}))
                tc, tl = frame(c, k, a, b, T)
                ledge = np.stack([tc + side * tl * (half(z1) - PILLOW), tc + side * tl * half(z1)], 1)
                P = np.concatenate([ledge, np.full((len(T), 2, 1), z1)], -1)
                # The top photograph's bag edges on it, as the course's tops show there.
                x = side * np.array([1 - PILLOW / half(z1), 1.0])
                v = np.broadcast_to(FACE_V + TOP_V * (.5 - .46 * x), P.shape[:2])
                uv = np.stack([np.broadcast_to(photo_u(T, a, b, COURSES[top][2], which)[:, None], P.shape[:2]), v], -1)
                mesh.grid(P, uv, np.array([0, 0, 1.0]))
            for neighbour, s_end, along in ((i - 1, a, -1), (i + 1, b, 1)):
                if not (0 <= neighbour < len(courses[c]) and shaped(c, neighbour)):
                    continue
                na, nb, nk, _, namount = courses[c][neighbour]
                if abs((nb if along < 0 else na) - s_end) > 1e-6:
                    continue
                # From this plane back to the modelled bag's seam, up the course: the joint between them.
                end = np.array([s_end])
                seam = face_points(c, nk, end, na, nb, namount, side)[0]
                ec, el = frame(c, k, a, b, end)
                plane = np.concatenate([ec[0] + side * el[0] * half(seam[:, 2])[:, None], seam[:, 2:]], -1)
                P = np.stack([plane, seam], 1)
                uv = np.stack([np.full(P.shape[:2], photo_u(end, a, b, joints, which)[0]),
                               np.clip(1 - P[..., 2] / HEIGHT, 0, 1) * FACE_V], -1)
                direction = np.array([el[0][1], -el[0][0], 0.0]) * along
                mesh.grid(P, uv, direction)

    def covered_by_shaped(c, a, b):
        """The parts of a..b that course c's modelled bags lie over."""
        return [(max(a, a1), min(b, b1)) for j, (a1, b1, *_) in enumerate(courses[c] if c <= top else ())
                if min(b, b1) - max(a, a1) > 1e-3 and shaped(c, j)]

    for c, laid in enumerate(courses):
        z0, z1, joints = COURSES[c]
        for i, (a, b, k, which, amount) in enumerate(laid):
            if not shaped(c, i):
                flat_bag(c, i, a, b, k, which)
                continue
            S = samples(c, a, b)
            middle = frame(c, k, a, b, np.array([(a + b) / 2]))[1][0]
            u = photo_u(S, a, b, joints, which)
            # The photograph's own course on the face, however its top rounds over: up the course's rows.
            v = (1 - (z0 + (z1 - z0) * np.array(UP)) / HEIGHT) * FACE_V
            for side in (-1, 1):
                P = face_points(c, k, S, a, b, amount, side)
                uv = np.stack([np.broadcast_to(u[:, None], P.shape[:2]), np.broadcast_to(v, P.shape[:2])], -1)
                P[..., 2] -= sag(c, a, b, S)[:, None]
                mesh.grid(P, uv, np.array([*(side * middle), 0]))
            # Its top where nothing lies on it, and its flat underside where it overhangs the course below.
            for e0, e1 in missing(c + 1, a, b):
                T = samples(c, a, b, (e0, e1))
                P, x = top_points(c, k, T, a, b, amount)
                v = np.broadcast_to(FACE_V + TOP_V * (.5 - .46 * x), P.shape[:2])
                tu = photo_u(T, a, b, COURSES[top][2], which)
                P[..., 2] -= sag(c, a, b, T)[:, None]
                mesh.grid(P, np.stack([np.broadcast_to(tu[:, None], P.shape[:2]), v], -1), np.array([0, 0, 1.0]))
            for e0, e1 in (missing(c - 1, a, b) if c > 0 else ()):
                T = samples(c, a, b, (e0, e1))
                P = np.stack([face_points(c, k, T, a, b, amount, side)[:, 0] for side in (-1, 1)], 1)
                uv = np.stack([np.broadcast_to(photo_u(T, a, b, joints, which)[:, None], P.shape[:2]),
                               np.full(P.shape[:2], (1 - z0 / HEIGHT) * FACE_V)], -1)
                P[..., 2] -= sag(c, a, b, T)[:, None]
                mesh.grid(P, uv, np.array([0, 0, -1.0]))
            # Its rounded end where the course stops (the wall's ends and a notch's sides) or a flat bag goes on.
            start, finish = stops(laid, i)
            start = start or not shaped(c, i - 1)
            finish = finish or not shaped(c, i + 1)
            for ends, s_end, outward, tie in ((start, a, -1, joints[which]), (finish, b, 1, joints[(which + 1) % 4])):
                if ends:
                    end = np.array([s_end])
                    bag_end(mesh, face_points(c, k, end, a, b, amount, -1)[0],
                            face_points(c, k, end, a, b, amount, 1)[0],
                            top_points(c, k, end, a, b, amount)[0][0] if open_above(c, s_end) else None,
                            frame(c, k, a, b, end)[1][0], outward, tie, sag(c, a, b, end)[0])


def bag_end(mesh, outer, inner, crown, left, outward, tie, drop):
    """The ends of a course's two bags (one each side of the wall's middle) where it stops: from its outer face's
    profile to its inner's, each bag's end bulging out along the wall, up to its top's profile where nothing lies on it.
    The face photograph's ties at {@code tie} (u) on them, squeezed across the wall; all lowered by {@code drop} where
    the bags sag over the course below."""
    direction = np.array([left[1], -left[0], 0.0]) * outward
    x = np.concatenate([-1 + np.array(ACROSS), 1 - np.array(ACROSS[::-1][1:])])
    t = np.array(UP)
    rows = outer[:, None, :] + (inner - outer)[:, None, :] * ((x + 1) / 2)[None, :, None]
    rows = rows + direction * (END * rounded(t)[:, None] * rounded(np.abs(x))[None, :])[..., None]
    if crown is not None:
        rows = np.concatenate([rows, crown[None]], 0)
    uv = np.stack([np.broadcast_to(tie + .05 * x, rows.shape[:2]),
                   np.clip(1 - rows[..., 2] / HEIGHT, 0, 1) * FACE_V], -1)
    rows[..., 2] -= drop
    mesh.grid(rows, uv, direction)


def level(kind):
    """The emplacement at one level: its walls as bags (near), detailed prisms or simple ones."""
    mesh = Mesh()
    lines = [(line, [p for p, _ in POSITIONS]) for line in PERIMETER] + [(line, ()) for line in REVETMENTS]
    for seed, (line, notches) in enumerate(lines):
        if kind == 'bags':
            bags(mesh, line, seed, notches)
        else:
            wall(mesh, line, seed, notches, kind == 'detailed')
    print('LEVEL', kind, len(mesh.indices) // 3, 'TRIS')
    return {'materials': [SANDBAG],
            'meshes': [{'attributes': ATTRIBUTES, 'vertices': mesh.vertices,
                        'parts': [{'id': 'sandbags', 'type': 'TRIANGLES', 'indices': mesh.indices}]}],
            'nodes': [{'id': 'sandbags', 'parts': [{'meshpartid': 'sandbags', 'materialid': SANDBAG['id']}]}]}


places = []
for middle, out in POSITIONS:
    bearing = math.degrees(math.atan2(out[1], out[0]))
    places.append((f'stand-{slot(bearing)}', (*(middle - out * (BASE / 2 + .75)), 0), out))
places += [(f'vehicle-{i}', (0, side * PARK, 0), (-1, 0)) for i, side in enumerate((-1, 1))]
hide = (math.cos(math.radians(HIDE)), math.sin(math.radians(HIDE)))
places.append(('hide-0', (hide[0] * HIDE_AT, hide[1] * HIDE_AT, 0), hide))
write_glb(OUT, levels={0: level('bags'), 1: level('detailed'), 2: level('simple')},
          groups={'stands': ew.stands(places)})
print('WROTE', OUT)
