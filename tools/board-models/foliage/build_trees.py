"""python tools/board-models/foliage/build_trees.py [--out BOARD] [names]: the conifers' and broadleaf trees' LOD0-2
and their manifest counts.

Each species is grown from its botany instead of modelled by hand. Every card face has its back; every card carries
its crown's envelope normal (the game lights cards as proxies of the leaves around them, terrain-foliage.frag), and
vertex colours shade the crown dark inside and bright at its surface. Coarser levels keep the silhouette with fewer,
wider cards. Each level is scaled to the plants' common height of 30 units, standing at the origin.

Conifers: a straight, tapered trunk with a root flare and branches in whorls up the trunk, with smaller ones between,
their reach following the crown's cone. A branch is one card of the conifer-cutout spray, bent along its length (it
leaves the trunk at its whorl's angle, sags and turns its tip up) and folded along its stem so its side shoots hang
like the curtains of a spruce, which is what the board's iso and top views see. pine is a Norway spruce, pine-tall a
forest-grown spruce with a bare lower trunk, pine-broad a silver fir, pine-slender a subalpine fir (kept full enough
to read as cover) and pine-layered a fir with open tiers.

Broadleaf trees: a trunk forking into curved limbs (or, in excurrent species, a leader with limbs along it) and twigs,
all bark tubes, ending in clumps of crossed broadleaf-cutout cards inside the crown's ellipsoid. Each clump has its
own dome normal and shade, so the crown reads as clumps lit on top and dark beneath, with branches in the gaps.
tree is a linden, tree-broad an oak, tree-slender a Lombardy poplar, tree-layered a beech, tree-forked a twin-stemmed
maple, the birches silver birches with drooping clumps and the willows weeping willows: a dome of drooping clumps over
arched limbs, so the top view sees a closed crown, with curtains hanging below it.

The canopy's winter form is a material variant (mmVariants.snow): the snow cutout, with a colour scale that turns the
species' leaf tint grey. pine-tall-snow, tree-forked-snow and willow-snow are their species' geometry with that variant
applied, as files of their own. Afterwards refresh the impostors with Blender: tools/prepare_tree_lods.py -- impostors
<names>. --out writes the GLBs into another board folder (its textures must resolve as ../textures from its
vegetation folder) and leaves the manifest alone.
"""
import json
import math
import random
import sys
from pathlib import Path

MM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MM / 'tools'))
from glb_geometry import display, linear, read_glb, write_glb  # noqa: E402

BOARD = MM / 'data/models/board'
MANIFEST = MM / 'tools/board-models/manifest.json'
HEIGHT = 30.0
BUDGETS = (1000, 300, 96)
# Each cutout's stem: U at its base on the bottom edge; V from the base to the tip (V runs down the image).
STEMS = {'conifer': .55, 'broadleaf': .42}
BASE_V, TIP_V = .985, .02
WINTER = ('pine-tall-snow', 'tree-forked-snow', 'willow-snow')

# Conifers: crown base and widest radius as shares of the height, the envelope's exponent (1 a cone, less is fuller),
# whorls, branches per whorl and between whorls, branch angles at the top and the bottom of the crown (degrees), sag
# and tip upturn (shares of the reach), the side shoots' droop at the stem and the tip at the top and the bottom of the
# crown (degrees), the card's width over its reach, trunk radius at the foot, bark and leaf tints (display RGB) and
# dead branch stubs below the crown.
CONIFERS = {
    'pine': dict(seed=1, base=.05, radius=.32, exponent=.85, whorls=14, per_whorl=5, between=2, angles=(42, -18),
                 sag=(.05, .32), upturn=(0, .3), droop=((18, 30), (40, 62)), width=.85, trunk=.55,
                 bark=(.44, .37, .33), leaves=(.76, .92, .83), stubs=0),
    'pine-tall': dict(seed=2, base=.28, radius=.28, exponent=.8, whorls=12, per_whorl=5, between=2, angles=(45, -12),
                      sag=(.05, .28), upturn=(0, .28), droop=((18, 28), (36, 58)), width=.82, trunk=.55,
                      bark=(.47, .39, .34), leaves=(.79, .91, .72), stubs=14),
    'pine-broad': dict(seed=3, base=.04, radius=.4, exponent=.92, whorls=12, per_whorl=6, between=2,
                       angles=(38, -6), sag=(.04, .14), upturn=(0, .12), droop=((10, 18), (18, 32)), width=.9,
                       trunk=.62, bark=(.52, .49, .46), leaves=(.78, .92, .92), stubs=0),
    'pine-slender': dict(seed=4, base=.03, radius=.26, exponent=.75, whorls=16, per_whorl=4, between=1,
                         angles=(48, -26), sag=(.06, .3), upturn=(0, .18), droop=((22, 34), (40, 60)), width=.85,
                         trunk=.42, bark=(.5, .45, .41), leaves=(.76, .9, .84), stubs=0),
    'pine-layered': dict(seed=5, base=.2, radius=.37, exponent=.75, whorls=8, per_whorl=7, between=0,
                         angles=(30, -4), sag=(.03, .12), upturn=(.05, .22), droop=((10, 16), (16, 28)), width=.9,
                         trunk=.6, bark=(.48, .4, .35), leaves=(.82, .94, .74), stubs=8),
}
# How each level thins a conifer: whorls kept, branches per whorl and between whorls, card width, bends on the long
# branches, folded cards, trunk sides and rings, core cards, leader cards and stubs. A level with no branches per whorl
# spirals single branches up the trunk instead, so a few cards cover the whole crown without gaps between tiers.
CONIFER_LEVELS = (
    dict(whorls=1, per_whorl=1, between=1, width=1, segments=2, fold=True, sides=6, rings=7, core=3, leader=2,
         stubs=True),
    dict(whorls=.85, per_whorl=1, between=0, width=1.25, segments=1, fold=False, sides=5, rings=3, core=0, leader=1,
         stubs=False),
    dict(whorls=.3, per_whorl=0, between=0, width=1.75, segments=1, fold=False, sides=4, rings=2, core=0, leader=1,
         stubs=False))
# Conifer branches reaching further than this share of the crown's widest radius bend twice.
LONG = .55

# Broadleaf trees: the fork's height and the crown ellipsoid's centre height, horizontal and vertical radii as shares
# of the height; trunk radius at the foot; limbs, their angle from the vertical (degrees) and how far above their
# origin they end (shares of the vertical radius); whether a leader runs to the top with the limbs along it; twigs per
# limb; leaf clumps at LOD0 and their size (share of the horizontal radius); how far the clumps hang (0 up, 1 down);
# how far the cards lie flat (0 any way, 1 level, beech sprays); whether curtains hang to near the ground; bark role,
# bark and leaf tints (display RGB).
# A willow's dome of clumps reaches down to this height on its crown's unit ellipsoid.
WILLOW_DOME = .4
BROADLEAF = {
    'tree': dict(seed=11, fork=.3, crown=(.6, .32, .32), trunk=.72, limbs=4, spread=(30, 65), rise=(.4, 1.1),
                 leader=False, twigs=3, clumps=100, leaf=.42, hang=0, flat=0, curtain=False, bark_role='bark',
                 bark=(.46, .42, .38), leaves=(.82, .95, .76)),
    'tree-broad': dict(seed=12, fork=.24, crown=(.58, .44, .3), trunk=.95, limbs=5, spread=(45, 78), rise=(.1, .8),
                       leader=False, twigs=3, clumps=92, leaf=.4, hang=0, flat=0, curtain=False, bark_role='bark',
                       bark=(.44, .41, .38), leaves=(.76, .9, .7)),
    'tree-slender': dict(seed=13, fork=.08, crown=(.55, .16, .45), trunk=.6, limbs=9, spread=(8, 22), rise=(.2, .6),
                         leader=True, twigs=1, clumps=110, leaf=.85, hang=0, flat=0, curtain=False, bark_role='bark',
                         bark=(.5, .47, .43), leaves=(.8, .94, .74)),
    'tree-layered': dict(seed=14, fork=.2, crown=(.55, .38, .38), trunk=.78, limbs=6, spread=(50, 82),
                         rise=(-.1, .7), leader=False, twigs=3, clumps=100, leaf=.4, hang=0, flat=.35,
                         curtain=False, bark_role='bark', bark=(.55, .53, .5), leaves=(.82, .96, .72)),
    'tree-forked': dict(seed=15, fork=.14, crown=(.6, .36, .34), trunk=.82, limbs=2, spread=(16, 26), rise=(1.1, 1.4),
                        leader=False, twigs=6, clumps=100, leaf=.4, hang=0, flat=0, curtain=False, bark_role='bark',
                        bark=(.47, .43, .39), leaves=(.8, .94, .74)),
    'birch': dict(seed=16, fork=.3, crown=(.6, .21, .38), trunk=.42, limbs=8, spread=(30, 55), rise=(.2, .7),
                  leader=True, twigs=1, clumps=100, leaf=.56, hang=.4, flat=0, curtain=False, bark_role='bark-birch',
                  bark=(.92, .92, .9), leaves=(.86, 1.0, .76)),
    'birch-tall': dict(seed=17, fork=.4, crown=(.66, .19, .33), trunk=.44, limbs=8, spread=(28, 50), rise=(.2, .6),
                       leader=True, twigs=1, clumps=100, leaf=.58, hang=.35, flat=0, curtain=False,
                       bark_role='bark-birch', bark=(.9, .9, .88), leaves=(.84, .98, .76)),
    'birch-young': dict(seed=18, fork=.22, crown=(.58, .17, .4), trunk=.3, limbs=7, spread=(25, 45), rise=(.2, .7),
                        leader=True, twigs=1, clumps=90, leaf=.6, hang=.3, flat=0, curtain=False,
                        bark_role='bark-birch', bark=(.9, .88, .84), leaves=(.88, 1.0, .74)),
    'birch-spreading': dict(seed=19, fork=.3, crown=(.6, .27, .36), trunk=.46, limbs=9, spread=(40, 65),
                            rise=(.1, .6), leader=True, twigs=1, clumps=100, leaf=.52, hang=.45, flat=0, curtain=False,
                            bark_role='bark-birch', bark=(.92, .91, .88), leaves=(.85, 1.0, .78)),
    'willow': dict(seed=20, fork=.26, crown=(.6, .38, .3), trunk=.95, limbs=6, spread=(30, 55), rise=(.7, 1.1),
                   leader=False, twigs=2, clumps=96, leaf=.3, hang=1, flat=0, curtain=True, bark_role='bark',
                   bark=(.44, .41, .37), leaves=(.86, 1.0, .72)),
    'willow-broad': dict(seed=21, fork=.24, crown=(.58, .47, .28), trunk=1.05, limbs=7, spread=(40, 65),
                         rise=(.6, 1.0), leader=False, twigs=2, clumps=96, leaf=.28, hang=1, flat=0, curtain=True,
                         bark_role='bark', bark=(.44, .41, .37), leaves=(.84, .98, .72)),
}
# How each level thins a broadleaf tree: clumps (share), crossed cards per clump, card size, twigs (share), limbs kept,
# limb and twig sides, limb segments, trunk sides and rings; with few clumps they spread evenly over the crown.
BROADLEAF_LEVELS = (
    dict(clumps=2, cards=1, size=1, twigs=1, limbs=99, limb_sides=4, twig_sides=3, segments=3, sides=6, rings=4,
         even=False),
    dict(clumps=.6, cards=1, size=1.45, twigs=0, limbs=5, limb_sides=3, twig_sides=3, segments=2, sides=5, rings=2,
         even=False),
    dict(clumps=.17, cards=1, size=2.1, twigs=0, limbs=3, limb_sides=3, twig_sides=3, segments=1, sides=4, rings=1,
         even=True))
SPECIES = {**CONIFERS, **BROADLEAF}


def family(name):
    return 'conifer' if name.removesuffix('-snow') in CONIFERS else 'broadleaf'


def snow_scale(spec):
    """The linear factor that turns the species' leaf tint grey on the snow cutout, its brightest channel kept."""
    tint = [linear(c) for c in spec['leaves']]
    return [round(max(tint) / c, 6) for c in tint]


def materials(kind, spec, snow):
    cutout = f'../textures/vegetation/{kind}{"-snow" if snow else ""}-cutout'
    canopy = {'id': 'canopy-snow-cutout' if snow else 'canopy-cutout', 'diffuse': [1, 1, 1], 'roughness': 1,
              'metallic': 0, 'alphaTest': .5, 'textures': [
                  {'id': 'canopy', 'type': role, 'wrapS': 33071, 'wrapT': 33071, 'filename': f'{cutout}_{suffix}.png'}
                  for role, suffix in (('DIFFUSE', 'albedo'), ('NORMAL', 'normal'), ('AMBIENT', 'orm'))]}
    if not snow:
        canopy['extras'] = {'mmVariants': {'snow': {
            'name': 'canopy-snow-cutout',
            'textures': {role: f'../textures/vegetation/{kind}-snow-cutout_{suffix}.png'
                         for role, suffix in (('baseColor', 'albedo'), ('normal', 'normal'), ('occlusion', 'orm'))},
            'colourScale': snow_scale(spec)}}}
    role = spec.get('bark_role', 'bark')
    texture = 'birch-bark' if role == 'bark-birch' else 'bark'
    bark = {'id': role, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
            'textures': [{'id': role, 'type': 'DIFFUSE', 'filename': f'../textures/vegetation/{texture}_albedo.png'}]}
    return [bark, canopy]


def add(a, b, s=1.0):
    return [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def length(v):
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def normalized(v):
    size = length(v) or 1
    return [v[0] / size, v[1] / size, v[2] / size]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def bezier(a, b, c, t):
    return [(1 - t) ** 2 * a[i] + 2 * (1 - t) * t * b[i] + t * t * c[i] for i in range(3)]


class Tree:
    """One level's geometry: interleaved vertices and the bark and canopy index lists."""

    def __init__(self, kind, spec, rng):
        self.kind, self.spec, self.rng = kind, spec, rng
        self.vertices, self.parts = [], {'bark': [], 'canopy': []}
        self.lean = [rng.uniform(-.25, .25), rng.uniform(-.25, .25)]
        if kind == 'conifer':
            self.crown_base = spec['base'] * HEIGHT
        else:
            centre, rx, rz = spec['crown']
            self.centre = [0, 0, centre * HEIGHT]
            self.radii = (rx * HEIGHT, rz * HEIGHT)
            self.fork = spec['fork'] * HEIGHT

    def vertex(self, p, n, color, uv):
        self.vertices.extend([*p, *n, *color, 1.0, *uv])
        return len(self.vertices) // 12 - 1

    def axis(self, z):
        """The trunk's centre at height z: straight, with a slight lean that grows toward the top."""
        t = (z / HEIGHT) ** 2
        return [self.lean[0] * t, self.lean[1] * t, z]

    def trunk_radius(self, z):
        foot = self.spec['trunk']
        if self.kind == 'conifer':
            return foot * max(0.0, 1 - z / (HEIGHT * .97)) ** 1.25 * (1 + .55 * math.exp(-z / .7)) + .03
        return foot * (1 - .4 * min(1, z / max(self.fork, 1))) * (1 + .55 * math.exp(-z / .7))

    def surface(self, grid, normals, colors, uvs):
        """Both faces of a canopy grid of rows of points, each cell two triangles a face."""
        for face in (1, -1):
            ids = [[self.vertex(p, normals[i][j], colors[i][j], uvs[i][j]) for j, p in enumerate(row)]
                   for i, row in enumerate(grid)]
            for i in range(len(grid) - 1):
                for j in range(len(grid[0]) - 1):
                    a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                    self.parts['canopy'].extend((a, b, c, a, c, d) if face == 1 else (a, c, b, a, d, c))

    def trunk(self, sides, rings, top, shade_from):
        """The trunk up to `top`, rings crowding at the flare; above `shade_from` it stands in the crown's shade."""
        spec = self.spec
        heights = [top * (k / rings) ** 1.6 for k in range(rings + 1)]
        lobes = self.rng.uniform(0, math.tau)
        circumference = math.tau * spec['trunk']
        ids = []
        for z in heights:
            centre, radius = self.axis(z), self.trunk_radius(z)
            flare = math.exp(-z / .7)
            # The root collar is darker with soil and moss.
            shade = (.8 + .2 * min(1, z / 2.5)) * (1 - .4 * min(1, max(0, z - shade_from) / 3))
            row = []
            for k in range(sides + 1):
                angle = math.tau * k / sides
                # The flare spreads into root buttresses.
                r = radius * (1 + .22 * flare * math.cos(3 * angle + lobes))
                direction = [math.cos(angle), math.sin(angle), 0]
                row.append(self.vertex([centre[0] + direction[0] * r, centre[1] + direction[1] * r, z],
                                       normalized([direction[0], direction[1], .15 + .6 * flare]),
                                       [c * shade for c in spec['bark']], [k / sides * 2, -z / (circumference * 1.6)]))
            ids.append(row)
        # The trunk is closed: its outside faces alone.
        for i in range(rings):
            for j in range(sides):
                a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                self.parts['bark'].extend((a, b, c, a, c, d))

    def tube(self, points, radii, sides, shade):
        """A bark tube along points, its rings turned by a parallel frame so it never twists."""
        circumference = math.tau * self.spec['trunk']
        tangent = normalized(sub(points[1], points[0]))
        side = normalized(cross(tangent, [0, 0, 1] if abs(tangent[2]) < .9 else [1, 0, 0]))
        travelled, ids = 0.0, []
        for i, (point, radius) in enumerate(zip(points, radii)):
            if i:
                travelled += length(sub(point, points[i - 1]))
                tangent = normalized(sub(points[min(i + 1, len(points) - 1)], points[i - 1]))
                side = normalized(cross(cross(tangent, side), tangent))
            other = cross(tangent, side)
            row = []
            for k in range(sides + 1):
                angle = math.tau * k / sides
                direction = add([c * math.cos(angle) for c in side], other, math.sin(angle))
                row.append(self.vertex(add(point, direction, radius), direction,
                                       [c * shade for c in self.spec['bark']],
                                       [k / sides, -travelled / (circumference * 1.6)]))
            ids.append(row)
        for i in range(len(points) - 1):
            for j in range(sides):
                a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                self.parts['bark'].extend((a, b, c, a, c, d))

    def stubs(self, count):
        """Dead branch stubs on the trunk below the crown: thin three-sided spikes angled down."""
        rng = self.rng
        for _ in range(count):
            z = rng.uniform(2.5, self.crown_base * 1.05)
            azimuth = rng.uniform(0, math.tau)
            direction = [math.cos(azimuth), math.sin(azimuth), 0]
            centre, radius = self.axis(z), self.trunk_radius(z)
            reach = rng.uniform(.8, 2.0) * (1 - .4 * z / max(self.crown_base, 1))
            tip = add(add(centre, direction, radius + reach), [0, 0, -reach * rng.uniform(.2, .6)])
            side = [-direction[1], direction[0], 0]
            thick = .07 + .03 * rng.random()
            ring = [add(add(add(centre, direction, radius * .7), side, thick * math.cos(a)),
                        [0, 0, thick * math.sin(a)]) for a in (0, math.tau / 3, 2 * math.tau / 3)]
            color = [c * .82 for c in self.spec['bark']]
            for k in range(3):
                a, b = ring[k], ring[(k + 1) % 3]
                n = normalized(cross(sub(b, a), sub(tip, a)))
                self.parts['bark'].extend(self.vertex(p, n, color, uv)
                                          for p, uv in ((a, (0, 0)), (b, (.25, 0)), (tip, (.12, -.4))))

    # Conifers

    def reach(self, z):
        """The conifer crown's radius at height z."""
        t = (HEIGHT - z) / (HEIGHT - self.crown_base)
        if t <= 0:
            return 0
        t = min(t, 1)
        # Open-grown crowns round off a little at their lowest whorls.
        return self.spec['radius'] * HEIGHT * t ** self.spec['exponent'] * (1 - .18 * max(0, t - .88) / .12)

    def cone_normal(self, p):
        """The conifer crown's outward normal at p: the cone's normal near its surface, turning up toward the trunk."""
        centre = self.axis(p[2])
        dx, dy = p[0] - centre[0], p[1] - centre[1]
        r = math.hypot(dx, dy)
        slope = self.spec['radius'] * HEIGHT / (HEIGHT - self.crown_base)
        w = min(1, r / max(self.reach(p[2]), 1e-3))
        cone = normalized([dx / (r or 1), dy / (r or 1), slope + .25])
        return normalized([cone[0] * w, cone[1] * w, cone[2] * w + (1 - w)])

    def branch(self, z, azimuth, reach, t, segments, width, fold):
        """One branch card from the trunk at height z, its relative crown depth t (0 at the top, 1 at the base)."""
        spec, rng = self.spec, self.rng
        lerp = lambda pair: pair[0] + (pair[1] - pair[0]) * t  # noqa: E731
        elevation = math.radians(lerp(spec['angles']) + rng.uniform(-6, 6))
        sag, upturn = lerp(spec['sag']) * rng.uniform(.8, 1.2), lerp(spec['upturn']) * rng.uniform(.7, 1.3)
        droop = [math.radians(lerp((a, b)) + rng.uniform(-5, 5)) for a, b in zip(*spec['droop'])]
        if not fold:
            # A flat card keeps a little of the droop as a lowered stem line.
            droop = [angle * .35 for angle in droop]
        roll = math.radians(rng.uniform(-10, 10))
        mirror = rng.random() < .5
        direction = [math.cos(azimuth), math.sin(azimuth), 0]
        # The spray's narrow base passes behind the trunk, so its full width starts at the trunk.
        start = add(self.axis(z), direction, -.1 * reach)
        reach *= 1.1
        half = reach * width * spec['width'] * .5
        tint = self.tint()
        # The inner crown is dark: shade by the distance from the trunk and the depth in the crown.
        inner = .66 + .1 * (1 - t)
        stem = STEMS['conifer'] if not mirror else 1 - STEMS['conifer']
        edges = (0.0, 1.0) if not mirror else (1.0, 0.0)
        rows, normals, colors, uvs = [], [], [], []
        for i in range(segments + 1):
            s = i / segments
            rise = reach * (math.tan(elevation) * s - sag * s * s + upturn * s ** 3)
            point = add(add(start, direction, reach * s), [0, 0, rise])
            slope = math.tan(elevation) - 2 * sag * s + 3 * upturn * s * s
            tangent = normalized(add(direction, [0, 0, slope]))
            side = normalized(cross([0, 0, 1], tangent))
            up = normalized(cross(tangent, side))
            side = add([c * math.cos(roll) for c in side], up, math.sin(roll))
            up = normalized(cross(tangent, side))
            angle = droop[0] + (droop[1] - droop[0]) * s
            left = add(add(point, side, half * math.cos(angle)), up, -half * math.sin(angle))
            right = add(add(point, side, -half * math.cos(angle)), up, -half * math.sin(angle))
            # The lowest branches rest on the ground rather than passing through it.
            row = [[p[0], p[1], max(p[2], .05)] for p in ([left, point, right] if fold else [left, right])]
            rows.append(row)
            normals.append([self.cone_normal(p) for p in row])
            shade = inner + (1 - inner) * s ** .8
            # New growth lightens the tips.
            shade *= 1 + .08 * s ** 2
            colors.append([[c * shade for c in tint]] * len(row))
            v = BASE_V + (TIP_V - BASE_V) * s
            uvs.append([[edges[0], v], [stem, v], [edges[1], v]] if fold else [[edges[0], v], [edges[1], v]])
        self.surface(rows, normals, colors, uvs)

    def upright(self, z0, z1, width, azimuth, shade):
        """A vertical card standing on the axis (the leader and the dark core), the spray pointing up."""
        side = [math.cos(azimuth), math.sin(azimuth), 0]
        stem = STEMS['conifer']
        rows, normals, colors, uvs = [], [], [], []
        for z, v in ((z0, BASE_V), (z1, TIP_V)):
            centre = self.axis(z)
            row = [add(centre, side, width * stem), add(centre, side, -width * (1 - stem))]
            rows.append(row)
            normals.append([normalized(add([0, 0, 1], self.cone_normal(p), .5)) for p in row])
            colors.append([[c * shade for c in self.spec['leaves']]] * 2)
            uvs.append([[0, v], [1, v]])
        self.surface(rows, normals, colors, uvs)

    def conifer(self, level, thinning):
        spec, rng = self.spec, self.rng
        self.trunk(level['sides'], level['rings'], HEIGHT * .96, self.crown_base)
        if level['stubs']:
            self.stubs(spec['stubs'])
        if level['per_whorl']:
            whorls = max(3, round(spec['whorls'] * level['whorls'] * thinning ** .6))
            per_whorl = max(3, round(spec['per_whorl'] * level['per_whorl'] * thinning ** .4))
        else:
            whorls, per_whorl = max(6, round(spec['whorls'] * spec['per_whorl'] * level['whorls'] * thinning)), 1
        between = round(spec['between'] * level['between'])
        leader = HEIGHT * .07
        top = HEIGHT - leader * .7
        widest = spec['radius'] * HEIGHT
        # Internodes shorten toward the top, where the newest whorls sit.
        span = top - self.crown_base
        heights = [self.crown_base + span * (1 - (1 - k / whorls) ** 1.25) for k in range(whorls)]
        phase = rng.uniform(0, math.tau)

        def grow(z, azimuth, scale):
            t = (top - z) / span
            reach = (self.reach(z) * rng.uniform(.82, 1.06) + .4) * scale
            segments = level['segments'] if reach > LONG * widest else 1
            self.branch(z, azimuth, reach, t, segments, level['width'], level['fold'])

        for k, z in enumerate(heights):
            z += rng.uniform(-.15, .15) * span / whorls
            phase += 2.39996
            count = per_whorl if (top - z) / span > .12 or per_whorl == 1 else max(3, per_whorl - 1)
            for b in range(count):
                grow(z, phase + math.tau * (b + rng.uniform(-.18, .18)) / count, 1)
            # Smaller branches grow between the whorls.
            gap = (heights[k + 1] if k + 1 < whorls else top) - z
            for b in range(between):
                grow(z + gap * rng.uniform(.35, .65), phase + rng.uniform(0, math.tau), rng.uniform(.6, .78))
        # A dark core of upright cards fills the crown between the branches.
        cores = level['core']
        for k in range(cores):
            z0 = self.crown_base + span * k / max(cores, 1) * .8
            z1 = z0 + span * .38
            for turn in (0, math.pi / 2):
                self.upright(z0, z1, self.reach(z0) * 1.1, phase + k * 1.1 + turn, .5)
        # The leader: the top shoot, crossed upright sprays reaching exactly the full height.
        for k in range(level['leader']):
            self.upright(HEIGHT - leader, HEIGHT, leader * .55, phase + k * math.pi / 2, 1.0)

    def tint(self):
        """The species' leaf tint, varied in value alone: the snow variant's colour scale must turn every card grey."""
        value = self.rng.uniform(.94, 1.06)
        return [c * value for c in self.spec['leaves']]

    # Broadleaf trees

    def depth(self, p):
        """How far p lies from the crown's centre toward its ellipsoid: 0 at the centre, 1 on it."""
        rx, rz = self.radii
        q = sub(p, self.centre)
        return math.sqrt((q[0] / rx) ** 2 + (q[1] / rx) ** 2 + (q[2] / rz) ** 2)

    def ellipsoid_normal(self, p):
        rx, rz = self.radii
        q = sub(p, self.centre)
        return normalized([q[0] / rx ** 2, q[1] / rx ** 2, q[2] / rz ** 2])

    def inside(self, p, limit):
        """p pulled toward the crown's centre until it lies within `limit` of the ellipsoid."""
        d = self.depth(p)
        return p if d <= limit else add(self.centre, sub(p, self.centre), limit / d)

    def shell(self, azimuth, z, share):
        """The point at `share` of the ellipsoid's horizontal radius at height z, toward azimuth."""
        rx, rz = self.radii
        h = max(0.0, 1 - ((z - self.centre[2]) / rz) ** 2)
        r = rx * math.sqrt(h) * share
        return [self.centre[0] + math.cos(azimuth) * r, self.centre[1] + math.sin(azimuth) * r, z]

    def skeleton(self, level):
        """Limbs from the fork (or along a leader) and their twigs: lists of points with radii and ends for clumps."""
        spec, rng = self.spec, self.rng
        rx, rz = self.radii
        top = self.centre[2] + rz * .92
        fork = self.axis(self.fork)
        branches, tips = [], []
        phase = rng.uniform(0, math.tau)
        count = spec['limbs']
        limbs = []
        if spec['leader']:
            points = [self.axis(self.fork + (top - self.fork) * k / 3) for k in range(4)]
            radius = self.trunk_radius(self.fork)
            branches.append((points, [radius * (1 - .85 * k / 3) for k in range(4)], 'limb'))
        for i in range(count):
            phase += 2.39996
            azimuth = phase + rng.uniform(-.3, .3)
            if spec['leader']:
                origin = self.axis(self.fork + (top - self.fork) * (i + rng.uniform(.1, .7)) / count * .85)
            else:
                origin = fork
            lift = rz * rng.uniform(*spec['rise'])
            z = min(origin[2] + lift, self.centre[2] + rz * .8)
            end = self.shell(azimuth, z, rng.uniform(.72, .92))
            span = length(sub(end, origin))
            angle = math.radians(rng.uniform(*spec['spread']))
            start = [math.sin(angle) * math.cos(azimuth), math.sin(angle) * math.sin(azimuth), math.cos(angle)]
            control = add(origin, start, span * .5)
            if spec['curtain']:
                # Willow limbs arch up and over before their curtains fall.
                control = add(control, [0, 0, span * .3])
            radius = self.trunk_radius(self.fork) * (.62 if count > 2 else .78) * (.5 if spec['leader'] else 1)
            limbs.append((origin, control, end, radius, span))
        limbs.sort(key=lambda limb: -limb[3] * limb[4])
        for origin, control, end, radius, span in limbs[:level['limbs']]:
            segments = level['segments']
            points = [bezier(origin, control, end, k / segments) for k in range(segments + 1)]
            radii = [max(.06, radius * (1 - .8 * k / segments)) for k in range(segments + 1)]
            branches.append((points, radii, 'limb'))
            tips.append((end, 1.0))
            twigs = round(spec['twigs'] * level['twigs'])
            for _ in range(twigs):
                s = rng.uniform(.35, .85)
                base = bezier(origin, control, end, s)
                azimuth = math.atan2(end[1] - self.centre[1], end[0] - self.centre[0]) + rng.uniform(-1.2, 1.2)
                z = base[2] + rz * rng.uniform(-.25, .45)
                z = max(self.centre[2] - rz * .7, min(z, self.centre[2] + rz * .85))
                tip = self.inside(self.shell(azimuth, z, rng.uniform(.82, .98)), .95)
                middle = add(bezier(base, base, tip, .5), [0, 0, length(sub(tip, base)) * .12])
                twig = max(.04, radius * (1 - .8 * s) * .5)
                branches.append(([base, middle, tip], [twig, twig * .6, .03], 'twig'))
                tips.append((tip, .8))
        return branches, tips

    def clump(self, centre, size, cards, hang, curtain):
        """A clump of leaf cards around centre, facing out of the crown so the iso and top views see their faces, the
        twig in each running up (or, as clumps hang, down) the crown's surface; shaded as a dome. A curtain hangs
        straight down from centre instead."""
        spec, rng = self.spec, self.rng
        out = self.ellipsoid_normal(centre)
        if spec['flat']:
            # Beech sprays lie level.
            out = normalized(add(out, [0, 0, 1], spec['flat'] * 2))
        facing = normalized(add(out, [rng.gauss(0, .3) for _ in range(3)]))
        if curtain:
            facing = normalized([out[0], out[1], 0]) if math.hypot(out[0], out[1]) > .1 else [1, 0, 0]
        # The twig runs along the card: up the surface, or down it as the clumps hang.
        along = add([0, 0, 1 - 2 * hang], [rng.gauss(0, .5) for _ in range(3)])
        along = sub(along, [c * sum(a * b for a, b in zip(along, facing)) for c in facing])
        if length(along) < 1e-3:
            along = cross(facing, [1, 0, 0])
        along = normalized(along)
        if curtain:
            along = [0, 0, -1]
        tint = self.tint()
        depth = self.depth(centre)
        rz = self.radii[1]
        # Inner and lower clumps are darker; each clump varies a little, so the clumps read apart.
        shade = (.66 + .4 * min(1, max(0, (depth - .35) / .65)) ** 1.2) * rng.uniform(.9, 1.08)
        shade *= 1 - .15 * min(1, max(0, (self.centre[2] - centre[2]) / rz))
        dome = sub(centre, [c * size * .45 for c in out])
        tall = size
        if curtain:
            # A curtain falls from the shell toward the ground, never touching it.
            tall = min(size * 2.6 * rng.uniform(.8, 1.5), centre[2] - HEIGHT * .08)
        stem = STEMS['broadleaf']
        for k in range(cards):
            # Further cards of a clump turn about the twig, giving it depth.
            turn = k * math.radians(rng.uniform(50, 70))
            across = normalized(add([c * math.cos(turn) for c in cross(facing, along)], facing, math.sin(turn)))
            base = add(centre, along, 0 if curtain else -tall * .5)
            rows, normals, colors, uvs = [], [], [], []
            mirror = rng.random() < .5
            for s, v in ((0, BASE_V), (1, TIP_V)):
                middle = add(base, along, tall * s)
                row = [add(middle, across, size * stem), add(middle, across, -size * (1 - stem))]
                rows.append(row)
                normals.append([normalized(add(self.ellipsoid_normal(p), normalized(sub(p, dome)))) for p in row])
                lit = shade * (1 - .12 * (1 - s) if not curtain else .85 + .15 * (1 - s))
                colors.append([[tint[0] * lit, tint[1] * lit, tint[2] * lit]] * 2)
                uvs.append([[1, v], [0, v]] if mirror else [[0, v], [1, v]])
            self.surface(rows, normals, colors, uvs)

    def broadleaf(self, level, thinning):
        spec, rng = self.spec, self.rng
        branches, tips = self.skeleton(level)
        trunk_top = self.fork + (1.5 if not spec['leader'] else 0)
        self.trunk(level['sides'], level['rings'], trunk_top, self.fork)
        for points, radii, role in branches:
            sides = level['limb_sides'] if role == 'limb' else level['twig_sides']
            self.tube(points, radii, sides, .72)
        count = max(8, round(spec['clumps'] * level['clumps'] * thinning))
        size = spec['leaf'] * self.radii[0] * level['size']
        rx, rz = self.radii
        # Clumps cover the crown's shell in lobes around the branches' directions, and its top.
        lobes = [(normalized([(tip[0] - self.centre[0]) / rx, (tip[1] - self.centre[1]) / rx,
                              (tip[2] - self.centre[2]) / rz]), weight) for tip, weight in tips]
        lobes.append(([0, 0, 1], 1.5))
        weights = [w for _, w in lobes]
        phase = rng.uniform(0, math.tau)
        for k in range(count):
            # A willow's top is a dome of larger drooping clumps over its arched limbs, spread evenly so the top view
            # sees a closed crown; every other clump hangs from the shell below as a curtain.
            curtain = spec['curtain'] and k % 2 == 1
            dome = spec['curtain'] and not curtain
            if dome:
                # A Fibonacci spiral over the dome.
                j = k // 2
                z = 1 - (1 - WILLOW_DOME) * (j + .5) / ((count + 1) // 2)
                ring = math.sqrt(1 - z * z)
                direction = [ring * math.cos(phase + j * 2.39996), ring * math.sin(phase + j * 2.39996), z]
            elif level['even']:
                # A Fibonacci spiral over the crown, from its top down to its flattened base.
                z = 1 - 1.6 * (k + .5) / count
                ring = math.sqrt(1 - z * z)
                direction = [ring * math.cos(phase + k * 2.39996), ring * math.sin(phase + k * 2.39996), z]
            else:
                lobe = rng.choices(lobes, weights)[0][0]
                direction = normalized(add(lobe, [rng.gauss(0, .45) for _ in range(3)]))
            # Open-grown crowns are flatter beneath; excurrent crowns reach down their leader.
            direction[2] = max(direction[2], -.95 if spec['leader'] else -.7)
            depth = rng.uniform(.72, 1.0) if rng.random() < .85 else rng.uniform(.4, .72)
            centre = add(self.centre, [direction[0] * rx, direction[1] * rx, direction[2] * rz], depth)
            if curtain:
                centre[2] = max(centre[2], self.centre[2] - rz * .2)
            scale = (1.6 if dome else 1) * rng.uniform(.85, 1.15)
            self.clump(centre, size * scale, level['cards'], spec['hang'], curtain)

    # Levels

    def fit(self):
        """Scale the level to the common height, its foot at the origin."""
        scale = HEIGHT / max(self.vertices[i] for i in range(2, len(self.vertices), 12))
        for i in range(0, len(self.vertices), 12):
            for c in range(3):
                self.vertices[i + c] *= scale


def grow(kind, spec, index, thinning):
    tree = Tree(kind, spec, random.Random(spec['seed'] * 101 + index))
    if kind == 'conifer':
        tree.conifer(CONIFER_LEVELS[index], thinning)
    else:
        tree.broadleaf(BROADLEAF_LEVELS[index], thinning)
    tree.fit()
    return tree


def model(name, index):
    kind, snow = family(name), name.endswith('-snow')
    spec = SPECIES[name.removesuffix('-snow')]
    # A crown over its level's budget loses branches or clumps until it fits.
    thinning = 1.0
    tree = grow(kind, spec, index, thinning)
    while sum(map(len, tree.parts.values())) // 3 > BUDGETS[index]:
        thinning *= .95
        if thinning < .1:
            raise ValueError(f'{name}-lod{index} cannot fit {BUDGETS[index]} triangles')
        tree = grow(kind, spec, index, thinning)
    vertices = tree.vertices
    # Canopy shades scale the species' tint in linear light, so its winter colour scale greys every card exactly.
    tint = spec['leaves']
    for i in set(tree.parts['canopy']):
        value = min(linear(vertices[i * 12 + 7] / tint[1]), 1 / linear(max(tint)))
        for c in range(3):
            vertices[i * 12 + 6 + c] = display(linear(tint[c]) * value)
    if snow:
        # The winter file applies its variant's colour scale (linear) to the canopy's vertex colours.
        scale = snow_scale(spec)
        vertices = list(vertices)
        for i in set(tree.parts['canopy']):
            for c in range(3):
                vertices[i * 12 + 6 + c] = display(min(1.0, linear(vertices[i * 12 + 6 + c]) * scale[c]))
    asset = f'{name}-lod{index}'
    parts = [{'id': f'{asset}-{role}', 'type': 'TRIANGLES', 'indices': tree.parts[role]} for role in ('bark', 'canopy')]
    bark, canopy = materials(kind, spec, snow)
    return {'id': asset, 'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                                     'vertices': vertices, 'parts': parts}],
            'nodes': [{'id': asset, 'parts': [{'meshpartid': parts[0]['id'], 'materialid': bark['id']},
                                              {'meshpartid': parts[1]['id'], 'materialid': canopy['id']}]}],
            'materials': [bark, canopy]}


def build(name, board):
    levels = {index: model(name, index) for index in range(3)}
    # The impostor (LOD3) stays until the impostor bake refreshes it.
    shipped = BOARD / f'vegetation/{name}.glb'
    if shipped.exists():
        old = read_glb(shipped, 3)
        old['materials'] = [material for material in old['materials'] if material['id'] == 'impostor']
        levels[3] = old
    write_glb(Path(board) / f'vegetation/{name}.glb', levels=levels)
    counts = [{'node': f'{name}-lod{index}',
               'triangles': sum(len(p['indices']) // 3 for p in levels[index]['meshes'][0]['parts']),
               'vertices': len(levels[index]['meshes'][0]['vertices']) // 12} for index in range(3)]
    if Path(board).resolve() == BOARD.resolve():
        manifest = json.loads(MANIFEST.read_text())
        # The bare file's entry and its winter variant's (which reads the same file) share its levels.
        for key in (f'vegetation/{name}', f'vegetation/{name}-snow'):
            entry = manifest.get(key)
            if entry and entry['mesh'] == f'vegetation/{name}.glb':
                stem = key.rsplit('/', 1)[-1]
                entry['lods'][:3] = [{**lod, 'node': f'{stem}-lod{index}'} for index, lod in enumerate(counts)]
                entry.update(source='tools/board-models/foliage/build_trees.py', triangles=counts[0]['triangles'],
                             vertices=counts[0]['vertices'])
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    print(name, [lod['triangles'] for lod in counts])


if __name__ == '__main__':
    arguments = sys.argv[1:]
    board = BOARD
    if arguments[:1] == ['--out']:
        board, arguments = Path(arguments[1]), arguments[2:]
    for name in arguments or [*SPECIES, *WINTER]:
        build(name, board)
