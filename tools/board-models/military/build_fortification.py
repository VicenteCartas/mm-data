"""Builds scenery/military/fortification.glb: a fortified hex's strongpoint (TO:AUE p.153), dug into its hex's ground.

Run: blender -b --factory-startup --python tools/board-models/military/build_fortification.py [-- <out.glb> [lod0 earth
triangles] [lod1 earth triangles]]; it writes data/models/board/scenery/military/fortification.glb by default.
Built to last, where a dug-in platoon's trench (build_trench.py) is scraped out in a turn: a vehicle pit 1.8 m deep at
the centre, which takes a vehicle at any heading, its ramp running out to the +X corner, and round it a fire trench
2.2 m deep with five revetted fire bays whose fire steps stand 0.6 m higher and duckboards along its floor. The trench
is open where the ramp leaves, and on the side behind the pit, at 150 degrees, the hide: level ground where a vehicle
that could go hull down in the pit, but has not, waits. The trench's floor is trodden (biome-mud); the pit, ramp and
hide keep the dirt. Earthwork, timber and sandbags as earthworks.py describes; stands `stand-0`..`stand-4` on the fire
steps, in the pit `vehicle-0` and `vehicle-1` side by side for a platoon's transports, facing in from the ramp, and
`hide-0` at the hide. The model fills a level hex's top; the game shrinks it to the room a hex beside steps and cliffs
has (BoardGroundCut#fitted).
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import earthworks as ew  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGS[0] if ARGS else ew.MM / 'data/models/board/scenery/military/fortification.glb'
TARGETS = [int(t) for t in ARGS[1:]] or [6500, 2000]
DEPTH = 2.2  # the fire trench's floor below the ground, metres
FIRE_STEP = 1.6  # a fire bay's step below the ground
W = 1.5  # the fire trench's width at the floor
RING = 9.0  # the fire trench's apothem
EARTH_BATTER = .45  # how far an earth wall leans back from the floor's edge to its rounded top
BAY_BATTER = .12  # a revetted bay's wall, near upright behind its planks
BAY_ALONG, BAY_OUT = 1.1, 1.0  # a fire bay's half width along the trench and its depth out of it
# The vehicle pit: its floor's radius, which a tank turns in (drawn 11.4 x 6.1 m), its depth and its earth walls' lean.
PIT, PIT_DEPTH, PIT_BATTER = 6.6, 1.8, .7
RAMP_W, RAMP_END = 3.3, 11.5  # the ramp's half width at its floor, and where along +X its floor meets the ground
GAP = 5.6  # the fire trench's ends either side of its opening, off the +X axis
PARK = 2.6  # a transport's stand off the pit's centre, either side of the ramp's axis
HIDE, HIDE_AT = 150, 12.5  # the hide's bearing, degrees, and how far out a waiting vehicle may go
# The fire steps' stands, facing out. Their order follows the figures' formation slots (InfantryVisual.FOOT_SLOTS, by
# direction from the formation's centre) as the bays lie unturned.
SLOTS = [143, 37, 270, 215, 325, 90]


def toward(a, b, y):
    """The point on a to b whose |y| is {@code y}."""
    t = (abs(a[1]) - y) / (abs(a[1]) - abs(b[1]))
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class Bay:
    """A fire bay off the middle of a fire trench side: a box out of its outer wall, its frame along and out."""

    def __init__(self, a, b):
        a, b = np.array(a), np.array(b)
        self.middle = (a + b) / 2
        self.along = (b - a) / np.linalg.norm(b - a)
        self.out = np.array([self.along[1], -self.along[0]])
        if self.out @ self.middle < 0:
            self.out = -self.out
        self.centre = self.middle + self.out * (W / 2 + BAY_OUT / 2)

    def point(self, along, out, z=0.0):
        """A point in the bay's frame: along its side, out from the fire trench's centreline, and up."""
        p = self.middle + self.along * along + self.out * out
        return np.array([p[0], p[1], z])

    def beyond(self, x, y):
        """Signed distance outside the bay's box over the grid."""
        px, py = x - self.centre[0], y - self.centre[1]
        qa = np.abs(px * self.along[0] + py * self.along[1]) - BAY_ALONG
        qo = np.abs(px * self.out[0] + py * self.out[1]) - BAY_OUT / 2
        return np.hypot(np.maximum(qa, 0), np.maximum(qo, 0)) + np.minimum(np.maximum(qa, qo), 0)

    def slot(self):
        bearing = math.degrees(math.atan2(self.out[1], self.out[0]))
        return SLOTS.index(min(SLOTS, key=lambda s: abs((bearing - s + 180) % 360 - 180)))


def revetments(props, detailed, lines, bays):
    """Each bay's plank walls between posts, its sandbags along the lip, and the fire trench's duckboards."""
    top, bottom = ew.LIP - .03, -FIRE_STEP
    for bay in bays:
        back, side, start = W / 2 + BAY_OUT - .02, BAY_ALONG - .02, W / 2 + .3
        walls = [(bay.point(-side, back), bay.point(side, back), -bay.out),
                 (bay.point(-side, start), bay.point(-side, back), bay.along),
                 (bay.point(side, back), bay.point(side, start), -bay.along)]
        for a, b, facing in walls:
            facing = [*facing, 0]
            if not detailed:
                props.quad([a + [0, 0, bottom], b + [0, 0, bottom], b + [0, 0, top], a + [0, 0, top]], facing,
                           props.weathered(-1, DEPTH), props.atlas(ew.WOOD, np.linalg.norm(b - a), top - bottom))
                continue
            rows = 9
            for row in range(rows):
                z0 = bottom + (top - bottom) * row / rows
                z1 = z0 + (top - bottom) / rows - .015
                # Each plank a little off true: proud or sunk, and its ends at slightly different heights.
                proud = np.array(facing) * props.rng.uniform(-.008, .012)
                tilt = props.rng.uniform(-.012, .012)
                props.quad([a + proud + [0, 0, z0 - tilt], b + proud + [0, 0, z0 + tilt], b + proud + [0, 0, z1 + tilt],
                            a + proud + [0, 0, z1 - tilt]], facing, props.weathered(z0, DEPTH),
                           props.atlas(ew.WOOD, np.linalg.norm(b - a), z1 - z0))
        # Posts hold the planks at the back corners and where the sides start.
        if detailed:
            for along, out in ((-side + .05, back - .05), (side - .1, back - .05), (-side + .05, start - .05),
                               (side - .1, start - .05)):
                props.box(bay.point(along, out, bottom - .05), [*bay.along * .1, 0], [*bay.out * .1, 0],
                          [0, 0, top - bottom + .2], props.weathered(-1, DEPTH), ew.WOOD)
        # Sandbags along the lip, laid like bricks: four along the back, three on them, two on each side.
        bags = [(along, W / 2 + BAY_OUT + .12, 0, True) for along in (-.84, -.28, .28, .84)]
        bags += [(along, W / 2 + BAY_OUT + .14, 1, True) for along in (-.56, 0, .56)]
        bags += [(sign * (BAY_ALONG + .12), out, 0, False) for sign in (-1, 1) for out in (W / 2 + .45, W / 2 + .98)]
        if not detailed:
            bags = [(0, W / 2 + BAY_OUT + .12, 0, True, 4.2)]
        for bag in bags:
            along, out, layer, across = bag[:4]
            length = bag[4] if len(bag) > 4 else .55
            jitter = props.rng.uniform(-.04, .04)
            a, o = (bay.along, bay.out) if across else (bay.out, bay.along)
            corner = bay.point(along + jitter, out) - [*a * length / 2, 0] - [*o * .16, 0]
            corner[2] = ew.LIP - .05 + layer * .15
            tint = props.rng.uniform(.78, 1.0)
            props.box(corner, [*a * length, 0], [*o * .32, 0], [0, 0, .16], [tint, tint * .96, tint * .9], ew.HESSIAN)
    # Duckboards along each side of the fire trench, clear of its corners and ends.
    for a, b in ((a, b) for line in lines for a, b in zip(line, line[1:])):
        a, b = np.array(a), np.array(b)
        length = np.linalg.norm(b - a)
        along = (b - a) / length
        across = np.array([-along[1], along[0]]) * .31
        z = -DEPTH + .1
        start, end = 1.0, length - 1.0
        if not detailed:
            p, q = a + along * start, a + along * end
            props.quad([[*p - across, z], [*q - across, z], [*q + across, z], [*p + across, z]], [0, 0, 1],
                       props.weathered(z, DEPTH), props.atlas(ew.WOOD, end - start, .62))
            continue
        for s in np.arange(start, end - .2, .3):
            p = a + along * s
            props.box([*p - across, z - .03], [*along * .24, 0], [*across * 2, 0], [0, 0, .03],
                      props.weathered(z, DEPTH), ew.WOOD)
        for offset in (-.7, .7):
            p = a + along * start + across * offset
            props.box([*p, z - .1], [*along * (end - start), 0], [*across * .15, 0], [0, 0, .07],
                      props.weathered(z - .1, DEPTH), ew.WOOD, top=False)


def ramp_depth(x):
    return PIT_DEPTH * ew.smooth((RAMP_END - x) / (RAMP_END - PIT))


def build(out):
    ground = ew.Ground(14.0, DEPTH, 7, 12.6)
    gx, gy = ground.gx, ground.gy
    corners = ew.hexagon(RING)[:6]
    # Round from the opening on one side of the +X corner to the opening on its other side, apart at the hide: the side
    # between the corners at 120 and 180 degrees.
    ring = ground.dug([toward(corners[1], corners[0], GAP), *corners[1:], toward(corners[5], corners[0], GAP)], .12)
    lines = [ring[:3], ring[3:]]
    bays = sorted((Bay(a, b) for line in lines for a, b in zip(line, line[1:])), key=Bay.slot)
    for line in lines:
        ground.line(line, W, DEPTH, EARTH_BATTER, .9, .35)
    for bay in bays:
        ground.dig(bay.beyond(gx, gy), FIRE_STEP, BAY_BATTER, .9)
        # From the fire trench's floor edge, where the step rises out of it, to past the bay's walls.
        reach = BAY_BATTER + .02
        box = [bay.point(-BAY_ALONG - reach, W / 2), bay.point(BAY_ALONG + reach, W / 2),
               bay.point(BAY_ALONG + reach, W / 2 + BAY_OUT + reach),
               bay.point(-BAY_ALONG - reach, W / 2 + BAY_OUT + reach)]
        ground.flat([p[:2] for p in box], FIRE_STEP)
    ramp = np.maximum(np.abs(gy) - RAMP_W, np.maximum(-gx, gx - RAMP_END))
    # The pit's spoil is its berm all round, the vehicle's cover, low toward the hide, where a waiting vehicle's nose may
    # reach over it; the ramp's runs low along its sides and out at its mouth.
    off_hide = np.abs((np.degrees(np.arctan2(gy, gx)) - HIDE + 180) % 360 - 180)
    ground.dig(np.hypot(gx, gy) - PIT, PIT_DEPTH, PIT_BATTER, .7 - .55 * ew.smooth(1 - off_hide / 45))
    ground.flat(ew.polygon((0, 0), PIT + PIT_BATTER + .02, 24), PIT_DEPTH)
    ground.dig(ramp, ramp_depth(gx), PIT_BATTER, .4 * np.clip((RAMP_END - 1 - gx) / 2, 0, 1))
    reach = RAMP_W + PIT_BATTER + .02
    for x0, x1 in zip(np.arange(PIT, RAMP_END, 1.0), np.append(np.arange(PIT + 1, RAMP_END, 1.0), RAMP_END)):
        ground.piece([(x0, -reach, -ramp_depth(x0)), (x1, -reach, -ramp_depth(x1)),
                      (x1, reach, -ramp_depth(x1)), (x0, reach, -ramp_depth(x0))])
    # Earth slumped off the fire trench's outer wall at three of its corners.
    slumps = [(np.array(corners[c]) * (1 + .55 / RING), DEPTH) for c in ground.rng.choice([1, 4, 5], 3, replace=False)]
    ground.finish(slumps)
    inside = (np.hypot(gx, gy) < PIT + PIT_BATTER + 1.0) | (ramp < PIT_BATTER + .5)
    obj = ground.mesh(ground.trodden(FIRE_STEP - .1) & ~inside)
    levels = {}
    for index, target in enumerate(TARGETS):
        props = ew.Props(ground.rng)
        revetments(props, index == 0, lines, bays)
        levels[index] = ew.level(ground, obj, target, props, 140 if index == 0 else 0)
    # Each bay's stand is numbered for the formation slot nearest it, as a fighting hole's is.
    places = [(f'stand-{bay.slot()}', bay.point(0, W / 2 + BAY_OUT / 2 + .1, -FIRE_STEP), bay.out) for bay in bays]
    places += [(f'vehicle-{i}', (0, side * PARK, -PIT_DEPTH), (-1, 0)) for i, side in enumerate((-1, 1))]
    out_of_hide = (math.cos(math.radians(HIDE)), math.sin(math.radians(HIDE)))
    places.append(('hide-0', (out_of_hide[0] * HIDE_AT, out_of_hide[1] * HIDE_AT, 0), out_of_hide))
    ew.write(out, levels, ground, places)


build(OUT)
