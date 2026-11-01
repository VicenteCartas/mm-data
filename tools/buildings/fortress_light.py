"""The light fortress as connected kits (models/buildings/README.md), laid out from its hand-made art.

    python tools/buildings/fortress_light.py

Reads art/fortress_light_a_52.glb, the artist's fortress for exits 52 (modules base0, floor0, floor1, roof0), and
writes both footprints (kit_geometry.footprint) to data/models/buildings/fortress_light/: fortress_light_a.glb (Angled)
and fortress_light_a-square.glb (Square). Every wall has plain masonry at its ends and whole window bays between,
respaced to fit, so that no window is cut; a ground storey's door on a hub face or the front of a whole hex; the art's
crenellated parapet along the roof. The storeys are the art's wall rebuilt low-poly to its measurements: the art draws
each panel row as a box and every frame bar in the round (about 600 triangles a window bay), which at the board's scale
reads as the same paint as a panel face with its joints, band, window recess and frame (about 50). The far level of
detail keeps the art's own boxes. Roofs and floors are a board material on the board's axes, so they run on across
corner pieces and hexes; the walls' concrete runs on along each wall.
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kit_geometry import (ROOF_INSET, Geometry, LEVEL, R, clipped, facade, flat, inset, sector, slab_height,  # noqa: E402
                          to_facade, vertex, without_flats, write_kits)

SOURCE = HERE / 'art/fortress_light_a_52.glb'
FOLDER = HERE.parents[1] / 'data/models/buildings/fortress_light'
# The art's long wall, counter-clockwise (the building on its left): from the east corner towards the north-west one.
ORIGIN, ALONG, OUT = (R, 0), (-math.sqrt(3) / 2, .5), (.5, math.sqrt(3) / 2)
# Along it: a window bay (window to window), a stretch of plain masonry; a merlon bay of its parapet.
BAY, PLAIN = 9.67, 4.6
MERLON_BAY, MERLON = 13.54, 47.45
# The far parapet: its height, a stretch's width along the wall, how far it reaches in.
FAR_PARAPET = (1.75, 4.0, .8)
INSIDE, OUTSIDE = 4.5, 4.0
# The art's wall, measured (facade frame: d out of the band line, z up the storey): its panel face, the dark joints
# between its three panel rows, the band under the storey's top, a window's opening, glass and steel frame bars; on
# the ground storey the base course and a door with steel leaves.
FACE, GLASS, FRAME, BAR = 1.45, .75, 1.2, .24
WINDOW_HALF, WINDOW_LOW, WINDOW_HIGH = 1.19, 5.2, 13.8
JOINTS, JOINT_FACE = ((5.78, 5.86), (11.66, 11.74)), 1.5
BAND_LOW, BAND_FACE = 17.36, 1.55
COURSE_HIGH, COURSE_FACE = .5, 2.43
DOOR_HALF, DOOR_HIGH, DOOR_LEAF, DOOR_GAP = 3.5, 8.8, .8, .06
# Plain masonry kept at each end of a wall, before its first window; the concrete's repeat on the walls (two to an
# Angled wall, so it runs on across them); the roof deck's.
MARGIN = 2.3
CONCRETE = 12.0
REPEAT = 24.0
# The lone hex, from its front (the south side): the whole hex, a little inside its hexsides. A single link's band end.
LONE = [(39.837 * math.cos(math.radians(a)), 39.837 * math.sin(math.radians(a))) for a in (240, 300, 0, 60, 120, 180)]
END = 2.25
# Every material is the board's (tools/materials/structures/buildings): the art's on their own UVs (the walls' on the
# wall's), the roof deck on the board's axes.
BOARD = {'fortress-concrete': ('structures/buildings/fortress-concrete', None),
         'fortress-roof': ('structures/buildings/fortress-roof', None),
         'fortress-steel': ('structures/buildings/fortress-steel', None),
         'fortress-dark': ('structures/buildings/fortress-dark', None),
         'fortress-glass': ('structures/buildings/fortress-glass', None),
         'fortress-facade': ('structures/buildings/fortress-far', None),
         'roof': ('structures/buildings/fortress-roof', REPEAT)}
WALL_UV = {'fortress-concrete': CONCRETE, 'fortress-steel': CONCRETE, 'fortress-dark': CONCRETE,
           'fortress-glass': CONCRETE}


def stretch(geometry, start, width):
    """The art's long wall from `start`, `width` along it, in the facade frame from 0."""
    framed_ = to_facade(geometry, (ORIGIN[0] + ALONG[0] * start, ORIGIN[1] + ALONG[1] * start), ALONG, OUT)
    return without_flats(clipped(framed_, [lambda d, t: d + INSIDE, lambda d, t: OUTSIDE - d, lambda d, t: t,
                                           lambda d, t: width - t]))


def rect(geometry, material, axis, at, a0, a1, b0, b1, facing):
    """A rectangle in the facade frame: across `axis` ('d', 't' or 'z') at `at`, spanning the other two from a0 to a1
    and b0 to b1 (in d, t, z order), facing +1 or -1 along `axis`."""
    if a1 - a0 < 1e-6 or b1 - b0 < 1e-6:
        return
    def point(a, b):
        return {'d': (at, a, b), 't': (a, at, b), 'z': (a, b, at)}[axis]
    n = {'d': (facing, 0, 0), 't': (0, facing, 0), 'z': (0, 0, facing)}[axis]
    corners = [point(a0, b0), point(a1, b0), point(a1, b1), point(a0, b1)]
    # Counter-clockwise seen from the facing side.
    e1 = [corners[1][k] - corners[0][k] for k in range(3)]
    e2 = [corners[2][k] - corners[0][k] for k in range(3)]
    cross = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
    if sum(c * m for c, m in zip(cross, n)) < 0:
        corners.reverse()
    geometry.polygon(material, [vertex(*c, n, 1.0, 0, 0) for c in corners])


def storey(width, ground, opening=None, door=False):
    """A stretch of the storey's wall `width` along it, with a window or door `opening` (t0, t1) or none."""
    g = Geometry()
    low = COURSE_HIGH if ground else 0.0
    if opening:
        t0, t1 = opening
        z0, z1 = (low, DOOR_HIGH) if door else (WINDOW_LOW, WINDOW_HIGH)
        rect(g, 'fortress-concrete', 'd', FACE, 0, t0, low, BAND_LOW, 1)
        rect(g, 'fortress-concrete', 'd', FACE, t1, width, low, BAND_LOW, 1)
        rect(g, 'fortress-concrete', 'd', FACE, t0, t1, low, z0, 1)
        rect(g, 'fortress-concrete', 'd', FACE, t0, t1, z1, BAND_LOW, 1)
        back = DOOR_LEAF if door else GLASS
        # The reveal: its sides, sill and head.
        rect(g, 'fortress-concrete', 't', t0, back, FACE, z0, z1, 1)
        rect(g, 'fortress-concrete', 't', t1, back, FACE, z0, z1, -1)
        rect(g, 'fortress-concrete', 'z', z0, back, FACE, t0, t1, 1)
        rect(g, 'fortress-concrete', 'z', z1, back, FACE, t0, t1, -1)
        middle = (t0 + t1) / 2
        if door:
            rect(g, 'fortress-steel', 'd', DOOR_LEAF, t0, middle - DOOR_GAP, z0, z1, 1)
            rect(g, 'fortress-steel', 'd', DOOR_LEAF, middle + DOOR_GAP, t1, z0, z1, 1)
            rect(g, 'fortress-dark', 'd', DOOR_LEAF - .05, middle - DOOR_GAP, middle + DOOR_GAP, z0, z1, 1)
        else:
            rect(g, 'fortress-glass', 'd', GLASS, t0, t1, z0, z1, 1)
            for b0, b1, c0, c1 in ((t0, t1, z0, z0 + BAR), (t0, t1, z1 - BAR, z1), (t0, t0 + BAR, z0 + BAR, z1 - BAR),
                                   (t1 - BAR, t1, z0 + BAR, z1 - BAR),
                                   (middle - BAR / 2, middle + BAR / 2, z0 + BAR, z1 - BAR)):
                rect(g, 'fortress-steel', 'd', FRAME, b0, b1, c0, c1, 1)
    else:
        rect(g, 'fortress-concrete', 'd', FACE, 0, width, low, BAND_LOW, 1)
    # The dark joints between the panel rows, broken by a window that crosses them.
    for z0, z1 in JOINTS:
        crossed = opening and not door and WINDOW_LOW < z1 and z0 < WINDOW_HIGH or opening and door and z0 < DOOR_HIGH
        for t0, t1 in ((0, opening[0]), (opening[1], width)) if crossed else ((0, width),):
            rect(g, 'fortress-dark', 'd', JOINT_FACE, t0, t1, z0, z1, 1)
    # The band under the storey's top, and the ground storey's base course.
    rect(g, 'fortress-concrete', 'd', BAND_FACE, 0, width, BAND_LOW, LEVEL, 1)
    rect(g, 'fortress-concrete', 'z', BAND_LOW, FACE, BAND_FACE, 0, width, -1)
    if ground:
        rect(g, 'fortress-concrete', 'd', COURSE_FACE, 0, width, 0, COURSE_HIGH, 1)
        rect(g, 'fortress-concrete', 'z', COURSE_HIGH, FACE, COURSE_FACE, 0, width, 1)
    return g


def far_storey(ground):
    """The far storey: a panel face PLAIN long with its band (and base course), and a window bay and a door bay that
    are only their openings, laid just proud of it."""
    low = COURSE_HIGH if ground else 0.0
    face = Geometry()
    rect(face, 'fortress-concrete', 'd', FACE, 0, PLAIN, low, BAND_LOW, 1)
    rect(face, 'fortress-concrete', 'd', BAND_FACE, 0, PLAIN, BAND_LOW, LEVEL, 1)
    if ground:
        rect(face, 'fortress-concrete', 'd', COURSE_FACE, 0, PLAIN, 0, COURSE_HIGH, 1)
    window, door = Geometry(), Geometry()
    rect(window, 'fortress-glass', 'd', FACE + .03, BAY / 2 - WINDOW_HALF, BAY / 2 + WINDOW_HALF, WINDOW_LOW,
         WINDOW_HIGH, 1)
    rect(door, 'fortress-steel', 'd', FACE + .03, BAY / 2 - DOOR_HALF, BAY / 2 + DOOR_HALF, low, DOOR_HIGH, 1)
    return face, window, door if ground else window


def masonry(plain, start, end):
    """Plain masonry from `start` to `end` along a wall: the plain stretch repeated, each stretched a little to fit."""
    count = max(1, math.ceil((end - start) / PLAIN - 1e-6))
    width = (end - start) / count
    return [(start + index * width, plain, width / PLAIN) for index in range(count)]


def storey_run(window, door, plain, doors):
    """Lays a storey's wall: plain masonry at its ends (and on past an end that goes on), whole bays respaced between;
    `doors(count)`, the bays that are doors."""
    def lay(length, before, after):
        usable = length - 2 * MARGIN
        count = max(1, round(usable / BAY))
        scale = usable / (count * BAY)
        entrances = doors(count)
        placed = masonry(plain, -before, MARGIN) + masonry(plain, length - MARGIN, length + after)
        placed += [(MARGIN + index * BAY * scale, door if index in entrances else window, scale)
                   for index in range(count)]
        return placed
    return lay


def roof_run(merlon):
    """Lays a parapet: whole merlon bays fitted to the wall, one more past each end that goes on."""
    def lay(length, before, after):
        count = max(1, round(length / MERLON_BAY))
        scale = length / (count * MERLON_BAY)
        placed = [(index * MERLON_BAY * scale, merlon, scale) for index in range(count)]
        if before:
            placed.append((-MERLON_BAY * scale, merlon, scale))
        if after:
            placed.append((length, merlon, scale))
        return placed
    return lay


def entrances(wall, ground):
    """The ground storey's door bay on a hub face (both ends on cut lines) and on a whole hex's front, next to its
    middle."""
    def doors(count):
        if not ground:
            return set()
        if wall.front:
            return {count - 1} if wall.end == 'joint' else {0}
        return {0} if wall.start == wall.end == 'cut' else set()
    return doors


def module(role, geometry, polygons, walls, direction, level):
    """One piece of a module: its walls (or parapets), its floor or roof slab, cut to its corner."""
    ground, top = role.startswith('base'), role.startswith('roof')
    result = Geometry()
    if top and level == 0:
        merlon = stretch(geometry, MERLON - MERLON_BAY / 2, MERLON_BAY)
        for wall in walls:
            result.add(facade(wall, roof_run(merlon), inset=ROOF_INSET)[0])
    elif top:
        # Far away a plain parapet, the height of the art's between its merlons, along each wall.
        parapet = Geometry()
        rect(parapet, 'fortress-concrete', 'd', BAND_FACE, 0, FAR_PARAPET[1], 0, FAR_PARAPET[0], 1)
        rect(parapet, 'fortress-concrete', 'z', FAR_PARAPET[0], -FAR_PARAPET[2], BAND_FACE, 0, FAR_PARAPET[1], 1)
        rect(parapet, 'fortress-concrete', 'd', -FAR_PARAPET[2], 0, FAR_PARAPET[1], 0, FAR_PARAPET[0], -1)
        for wall in walls:
            result.add(facade(wall, lambda length, before, after: [
                (-before, parapet, (length + before + after) / FAR_PARAPET[1])], inset=ROOF_INSET)[0])
    else:
        if level == 0:
            window = storey(BAY, ground, (BAY / 2 - WINDOW_HALF, BAY / 2 + WINDOW_HALF))
            door = storey(BAY, ground, (BAY / 2 - DOOR_HALF, BAY / 2 + DOOR_HALF), True) if ground else window
            plain = storey(PLAIN, ground)
            for wall in walls:
                result.add(facade(wall, storey_run(window, door, plain, entrances(wall, ground)), WALL_UV)[0])
        else:
            # The far level of detail: one panel face along each wall, the windows and doors laid on it in the same
            # bays as near.
            face, window, door = far_storey(ground)
            for wall in walls:
                bays = storey_run(window, door, Geometry(), entrances(wall, ground))
                result.add(facade(wall, lambda length, before, after, bays=bays: [
                    (-before, face, (length + before + after) / PLAIN)] + bays(length, 0, 0), WALL_UV)[0])
    # The roof's slab where the art has it; a storey's floor (all a piece open on both sides holds), kept off its walls.
    height = slab_height(geometry) if top else min(v[2] for t in geometry.parts.values() for f in t for v in f) + .05
    for polygon in polygons:
        flat(result, 'roof', polygon if top else inset(polygon, walls, 3.0), height, REPEAT)
    return clipped(result, sector(direction)) if direction is not None else result


if __name__ == '__main__':
    write_kits(SOURCE, FOLDER, 'fortress_light_a', module, LONE, END, BOARD)
