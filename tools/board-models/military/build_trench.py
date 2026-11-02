"""Builds scenery/military/trench.glb: the fighting holes a platoon scrapes out of its hex's ground when it digs in
(TO:AR p.106).

Run: blender -b --factory-startup --python tools/board-models/military/build_trench.py [-- <out.glb> [lod0 earth
triangles] [lod1 earth triangles]]; it writes data/models/board/scenery/military/trench.glb by default.
Quick and temporary, where a fortified hex's strongpoint (build_fortification.py) is built to last: six holes round the
hex centre, each dug in a hurry 1.4 m deep and roomy enough for a battle-armoured trooper or a soldier lying down, its
earth thrown forward into a low parapet and scattered round it; no timber, no steps, no trodden floor. The holes lie
far enough apart that a battle armour squad's meeples, the widest figures that dig in, stand clear of each other.
Earthwork as earthworks.py describes. Each hole is a numbered part, N for the formation slot whose figure dug it, with
its stand `stand-N`, facing out: the game shows the holes of the figures that dug in. The centre stays uncut. The model
fills a level hex's top; the game shrinks it to the room a hex beside steps and cliffs has (BoardGroundCut#fitted).
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import earthworks as ew  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = ARGS[0] if ARGS else ew.MM / 'data/models/board/scenery/military/trench.glb'
DEPTH = 1.4  # a hole's floor below the ground, metres
LENGTH, WIDTH = 3.0, 1.8  # a hole's floor, out from the hex centre and across
BATTER = .3  # how far its raw earth wall leans back from its floor's edge to its top
RADIUS = 6.4  # the holes' distance from the hex centre: about as far from each other
# Their bearings, evenly round the hex, each nearest one of the figures' formation slots (InfantryVisual.FOOT_SLOTS, by
# direction from the formation's centre: 143, 37, 270, 215, 325, 90), so each figure has the hole nearest its own place.
SLOTS = [150, 30, 270, 210, 330, 90]

ground = ew.Ground(11.0, DEPTH, 11, 10.2)
gx, gy = ground.gx, ground.gy
places, centres = [], []
# Hand-dug: walls a little off true.
rough = .06 * ground.noise(.5)
for i, bearing in enumerate(SLOTS):
    turn = math.radians(bearing + ground.rng.normal(0, 3))
    centre = (RADIUS + ground.rng.uniform(-.25, .25)) * np.array([math.cos(turn), math.sin(turn)])
    facing = turn + math.radians(ground.rng.normal(0, 12))
    out = np.array([math.cos(facing), math.sin(facing)])
    a, b = centre - out * (LENGTH - WIDTH) / 2, centre + out * (LENGTH - WIDTH) / 2
    beyond = ew.segment_distance(gx, gy, a, b) - WIDTH / 2
    # The earth thrown forward into a parapet, little to the sides and back.
    dx, dy = gx - centre[0], gy - centre[1]
    ahead = (dx * out[0] + dy * out[1]) / np.maximum(np.hypot(dx, dy), 1e-6)
    ground.dig(beyond + rough, DEPTH, BATTER, .12 + .38 * np.clip(ahead, 0, 1) ** 1.5)
    reach = WIDTH / 2 + BATTER + .1
    across = np.array([-out[1], out[0]]) * reach
    ground.flat([a - across, b - across, b + across, a + across], DEPTH, i)
    for end in (a, b):
        ground.flat(ew.polygon(end, reach), DEPTH, i)
    places.append((f'stand-{i}', (*centre, -DEPTH), out))
    centres.append(centre)
# Earth fallen back in at the back of two holes.
slumps = [((p[0] - o[0] * (LENGTH / 2 + .1), p[1] - o[1] * (LENGTH / 2 + .1)), DEPTH)
          for _, p, o in (places[i] for i in ground.rng.choice(6, 2, replace=False))]
ground.finish(slumps)
obj = ground.mesh(np.zeros(gx.shape, bool))
TARGETS = [int(t) for t in ARGS[1:]] or [3000, 1000]


def hole(x, y):
    """The hole whose earth lies at (x, y): the nearest."""
    return int(np.argmin([math.hypot(x - c[0], y - c[1]) for c in centres]))


levels = {index: ew.level(ground, obj, target, None, 60 if index == 0 else 0, hole) for index, target in enumerate(TARGETS)}
ew.write(OUT, levels, ground, places)
