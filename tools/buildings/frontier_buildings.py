"""The Frontier colony's authored buildings, built from the modular kit's own pieces (theme_kits): each module a box with
every edge bevelled, its walls laid with the kit's bays, corner facets and roof borders, the kit's fittings on its roofs;
the parts the kit lacks (lanterns, masts, radiators, glass tunnels, gables, decks) modelled here in the same finishes.

Run: blender -b --factory-startup --python frontier_buildings.py -- <name> [sheet folder]
Writes data/models/buildings/authored/frontier-<name>.glb, its hexes those of the approved plan (hex centres 62.35 apart
across, 72 along a column, odd columns 36 up), front (the entrance) to -y.
"""
import math
import random
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
import authored_examples as shared
import civic_blocks as c
import civic_habitat as h
import theme_kits as k
import utopia_buildings as u
from civic_habitat import PAINT, STEEL, add, cuboid, deck
from glb_geometry import write_glb
from theme_kits import (BEVEL, BORDER, CHAMFER, DARK, DOOR_GREY, DUSTY_GLASS, FRAME, GREENS, LEVEL, ORANGE, PLATING, ROUND, SOLAR,
                        TEAL, W, facing)

EXTEND = 10.0  # How far a wall's pieces go on past its ends, for the mitre to trim.
RADIUS = 5.0  # Convex corners chamfered as the kit's: one facet, 5 back along each wall at a right angle.
HEX_X, HEX_Y = 62.35, 72.0
GLASS_TINT = (.92, .97, .97)
SKYLIGHT = 'structures/lunar/skylight-glass'  # Opaque roof-light glazing: the lantern's plating lies under it.
GROW_LIGHT = (.46, .52, .38)  # Grow lights always on, faint (user, 2026-11-08: "faint light in the serra").


def hexc(i, j):
    """A hex centre: column i, row j up the column (odd columns half a hex up)."""
    return HEX_X*i, HEX_Y*j+(36 if i % 2 else 0)


# -- Laying the kit's pieces ----------------------------------------------------------------------

def clip(poly, keep):
    """Sutherland-Hodgman: the part of polygon [(point, weight)] where keep(x, y) >= 0."""
    out = []
    for i, (p, w) in enumerate(poly):
        q, v = poly[(i+1) % len(poly)]
        a, b = keep(p[0], p[1]), keep(q[0], q[1])
        if a >= 0:
            out.append((p, w))
        if (a < 0) != (b < 0) and a != b:
            t = a/(a-b)
            out.append((tuple(p[n]+(q[n]-p[n])*t for n in range(3)), w+(v-w)*t))
    return out if len(out) >= 3 else []


def lay(builder, origin, along, z=0.0, scale=1.0, keeps=(), lift=1.0):
    """What builder adds, laid as a kit piece: its x along unit along from origin (stretched by scale), its -y out of the
    wall (along's right), z up from z (stretched by lift); its faces clipped to keeps (half planes, keep(x, y) >= 0); the
    fixtures and objects it adds moved with it."""
    marks = {key: (len(b['v']), len(b['f'])) for key, b in h.bins.items()}
    objects, fixtures = len(shared.objects), len(h.fixtures)
    builder()
    ux, uy = along
    nx, ny = uy, -ux

    def world(x, y, zz):
        x *= scale
        return origin[0]+ux*x-nx*y, origin[1]+uy*x-ny*y, z+zz*lift
    for key, b in h.bins.items():
        v0, f0 = marks.get(key, (0, 0))
        verts, weights, faces = b['v'][v0:], b['w'][v0:], b['f'][f0:]
        del b['v'][v0:], b['w'][v0:], b['f'][f0:]
        for face in faces:
            poly = [(world(*verts[i-v0]), weights[i-v0]) for i in face]
            for keep in keeps:
                poly = clip(poly, keep)
                if not poly:
                    break
            if poly:
                base = len(b['v'])
                b['v'].extend(p for p, _ in poly)
                b['w'].extend(w for _, w in poly)
                b['f'].append(tuple(range(base, base+len(poly))))
    for i in range(fixtures, len(h.fixtures)):
        h.fixtures[i] = world(*h.fixtures[i])
    frame = Matrix(((ux*scale, -nx, 0, origin[0]), (uy*scale, -ny, 0, origin[1]), (0, 0, lift, z), (0, 0, 0, 1)))
    for obj in shared.objects[objects:]:
        obj.matrix_world = frame @ obj.matrix_world


def unit(a, b):
    d = math.dist(a, b)
    return (b[0]-a[0])/d, (b[1]-a[1])/d


def cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def mitre(point, n1, n2, inside):
    """The half plane through point along the walls' mean outward normal, on inside's side."""
    b = (n1[0]+n2[0], n1[1]+n2[1])
    if math.hypot(*b) < 1e-9:
        b = (-n1[1], n1[0])
    sign = 1 if cross(b, (inside[0]-point[0], inside[1]-point[1])) >= 0 else -1
    return lambda x, y: sign*cross(b, (x-point[0], y-point[1]))


def outward(p, q):
    ux, uy = unit(p, q)
    return uy, -ux


def faceted(ring, radius=RADIUS):
    """A counter-clockwise outline with each convex corner cut by one facet, radius*tan(turn/2) back along both walls,
    as segments (p, q, edge): edge the outline's edge it lies on, None for a facet."""
    n = len(ring)
    cut = []
    for i in range(n):
        a, b, d = ring[i-1], ring[i], ring[(i+1) % n]
        u1, u2 = unit(a, b), unit(b, d)
        turn = math.atan2(cross(u1, u2), u1[0]*u2[0]+u1[1]*u2[1])
        reach = radius*math.tan(turn/2) if turn > 1e-6 and radius > 0 else 0.0
        cut.append(((b[0]-u1[0]*reach, b[1]-u1[1]*reach), (b[0]+u2[0]*reach, b[1]+u2[1]*reach), reach > 0))
    segments = []
    for i in range(n):
        start, end = cut[i][1], cut[(i+1) % n][0]
        segments.append((start, end, i))
        if cut[(i+1) % n][2]:
            segments.append((cut[(i+1) % n][0], cut[(i+1) % n][1], None))
    return segments


def inset(ring, by):
    """A convex counter-clockwise outline moved in by `by`."""
    n = len(ring)
    lines = []
    for i in range(n):
        p, q = ring[i], ring[(i+1) % n]
        nx, ny = outward(p, q)
        lines.append(((p[0]-nx*by, p[1]-ny*by), unit(p, q)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i-1], lines[i]
        den = cross(d1, d2)
        t = cross((p2[0]-p1[0], p2[1]-p1[1]), d2)/den
        out.append((p1[0]+d1[0]*t, p1[1]+d1[1]*t))
    return out


# -- Pieces -----------------------------------------------------------------------------------------

DOORS = {'airlock': 'plain', 'airlock-med': 'med', 'rollup': 'rollup'}


def piece(kind, base, rng):
    """The kit's bay of kind, as a builder: a window bay, a glass bay, an airlock (its amber light a night fixture), or
    a blank stretch of face."""
    if kind in DOORS:
        def door():
            k.airlock(rng, DOORS[kind])
            h.fixtures.append((W/2, -4, CHAMFER+12))
        return door
    if kind.startswith('glass'):
        return lambda: k.frontier_greenhouse(rng, 'vent' if 'vent' in kind else 'plain', base)
    if kind == 'blank':
        return lambda: (k.module_face(W, foot=k.FOOT if base else 0.0), k.feet((W/2,)) if base else None)
    return lambda: k.frontier_bay(rng, kind, base)


class Module:
    """One box of a building: its outline (counter-clockwise), its storeys from z0, its faces' bays per storey
    (faces[edge] a list of kinds, or a function (storey, count) -> kinds; missing edges plain), edges hidden inside
    another module, and its roof (a border along every exposed wall, its slab textured along `axis`); continuous, one tall
    box whose storeys run on without the groove stacked modules part in."""

    def __init__(self, name, ring, storeys=1, z0=0.0, faces=None, hidden=(), radius=RADIUS, roof=True, axis=None,
                 lift=1.0, default='pair', continuous=False, roof_key=PLATING, roof_colour=(1, 1, 1)):
        self.name, self.ring, self.storeys, self.z0 = name, ring, storeys, z0
        self.faces, self.hidden, self.radius, self.roof, self.lift = faces or {}, set(hidden), radius, roof, lift
        self.axis = axis or unit(ring[0], ring[1])
        self.default = default
        self.continuous = continuous  # One tall box: its storeys run on without a groove between them.
        self.roof_key, self.roof_colour = roof_key, roof_colour

    @property
    def top(self):
        return self.z0+self.storeys*LEVEL*self.lift


def bays_for(module, edge, storey, length):
    """An edge's bays as (kind, width): its spec a kind or a list of kinds, repeated to whole bays of W along it; or
    (kind, width) pairs, laid as given; or a function of the storey giving either; scaled to fit by the caller."""
    spec = module.faces.get(edge, module.default)
    if callable(spec):
        spec = spec(storey)
    if isinstance(spec, str):
        spec = [spec]
    if any(isinstance(item, tuple) for item in spec):
        return [item if isinstance(item, tuple) else (item, W) for item in spec]
    count = max(1, round(length/W))
    return [(spec[i % len(spec)], W) for i in range(count)]


def build_module(module, seed=0):
    """Lays a module's storeys and roof from the kit's pieces."""
    segments = faceted(module.ring, module.radius)
    shown = [s for s in segments if not (s[2] in module.hidden or s[2] is None and
                                          any(t[2] in module.hidden for t in (segments[segments.index(s)-1],
                                                                                segments[(segments.index(s)+1) % len(segments)])))]
    for i, (p, q, edge) in enumerate(segments):
        if (p, q, edge) not in shown:
            continue
        before, after = segments[i-1], segments[(i+1) % len(segments)]
        n = outward(p, q)
        keeps = [mitre(p, outward(before[0], before[1]), n, q), mitre(q, n, outward(after[0], after[1]), p)]
        along, length = unit(p, q), math.dist(p, q)
        rng = random.Random(seed*101+i)
        for storey in range(module.storeys):
            z = module.z0+storey*LEVEL*module.lift
            base = storey == 0 and module.z0 == 0
            k.EDGES.update(bottom=not module.continuous or storey == 0, top=not module.continuous or storey == module.storeys-1)
            if edge is None:
                lay(lambda: k.frontier_corner(rng, 'base' if base else 'plain', ROUND), (p[0]-along[0]*EXTEND, p[1]-along[1]*EXTEND),
                    along, z, (length+2*EXTEND)/ROUND, keeps, module.lift)
                continue
            bays = bays_for(module, edge, storey, length)
            scale = length/sum(width for _, width in bays)
            # A plain stretch more past each end, for the mitre to trim.
            starts = [-W]+[sum(width for _, width in bays[:i]) for i in range(len(bays))]+[length/scale]
            for at, (kind, width) in zip(starts, [('blank', W)]+bays+[('blank', W)]):
                start = (p[0]+along[0]*at*scale, p[1]+along[1]*at*scale)
                lay(piece(kind, base, rng), start, along, z, scale*width/W, keeps, module.lift)
        k.EDGES.update(top=True, bottom=True)
        if module.roof:
            lay(lambda: k.roof_border(W), (p[0]-along[0]*EXTEND-n[0]*k.ROOF_INSET, p[1]-along[1]*EXTEND-n[1]*k.ROOF_INSET), along,
                module.top, (length+2*EXTEND)/W, keeps)
    if module.roof:
        roof_slab(module.name, [s[0] for s in segments], module.top, module.axis, module.roof_key, module.roof_colour)


ROOF_LIFT = .28  # The roof slab's top above the walls' bevel, as the kit's.


def roof_slab(name, ring, z, axis, key=PLATING, colour=(1, 1, 1)):
    """A module's roof: plating kept CHAMFER off its walls (their top bevels reach it), its edge a short lip."""
    top = inset(ring, CHAMFER)
    n = len(top)
    obj_name = 'roof plating ' + name
    add(obj_name, key, colour, [(x, y, z+ROOF_LIFT) for x, y in top], [tuple(range(n))])
    roof_axes[obj_name] = axis
    for i in range(n):
        (ax, ay), (bx, by) = top[i], top[(i+1) % n]
        add('roof lip', key, colour, [(ax, ay, z-1), (bx, by, z-1), (bx, by, z+ROOF_LIFT), (ax, ay, z+ROOF_LIFT)], [(0, 1, 2, 3)])


roof_axes = {}


def fitting(builder, x, y, z, turn=0.0):
    """A kit roof fitting standing at (x, y) on a roof at z, turned (degrees) about its origin."""
    a = math.radians(turn)
    lay(lambda: builder(random.Random(round(x*7+y*13))), (x, y), (math.cos(a), math.sin(a)), z+ROOF_LIFT)


def plating_uvs(obj):
    """Plating textured along each face's own wall (18 a repeat, as the kit's planar runs), a roof along its module (30,
    as the kit's roofs)."""
    uv = obj.data.uv_layers.new(name='UVMap')
    axis = roof_axes.get(re.sub(r'\.\d+$', '', obj.name))
    verts = obj.data.vertices
    for face in obj.data.polygons:
        nx, ny, nz = face.normal
        for li in face.loop_indices:
            co = verts[obj.data.loops[li].vertex_index].co
            if abs(nz) > .7:
                ax, ay = axis or (1, 0)
                uv.data[li].uv = (co.x*ax+co.y*ay)/30, (co.y*ax-co.x*ay)/30
            else:
                length = math.hypot(nx, ny) or 1
                uv.data[li].uv = (co.x*-ny/length+co.y*nx/length)/18, co.z/18


# -- Shared custom parts -----------------------------------------------------------------------

def mast(x, y, z, height, rng, dish=True, beacon=True):
    """A lattice mast: four legs, cross braces, an orange beacon on top, a dish on one side."""
    s = 2.6
    for dx, dy in ((-s, -s), (s, -s), (s, s), (-s, s)):
        cuboid('mast leg', x+dx-.35, x+dx+.35, y+dy-.35, y+dy+.35, z, z+height, STEEL, (.30, .31, .32), omit='b')
    for level in range(1, int(height//6)+1):
        zz = z+level*6
        for a, b in (((-s, -s), (s, -s)), ((s, -s), (s, s)), ((s, s), (-s, s)), ((-s, s), (-s, -s))):
            u.tube('mast brace', [(x+a[0], y+a[1], zz-6), (x+b[0], y+b[1], zz)], .16, STEEL, (.30, .31, .32), sides=4)
        cuboid('mast ring', x-s-.3, x+s+.3, y-s-.3, y+s+.3, zz-.25, zz+.25, STEEL, (.30, .31, .32), omit='', detail=True)
    cuboid('mast cap', x-s-.6, x+s+.6, y-s-.6, y+s+.6, z+height, z+height+.8, PAINT, DARK, omit='b')
    if beacon:
        h.round_prism('mast beacon', x, y, z+height+.8, z+height+3, 1.0, PAINT, ORANGE, 8, light=c.AMBER_LIGHT)
    if dish:
        dish_at(x+s+4.5, y-1.5, z+height*.72, 7.0, (1, -.6))


def dish_at(x, y, z, radius, facing_xy):
    """A white parabolic dish facing facing_xy (tilted up a little), on a short arm, a feed horn at its focus."""
    fx, fy = facing_xy
    length = math.hypot(fx, fy)
    fx, fy = fx/length, fy/length
    rings, sides = 4, 16
    v, f = [], []
    for r in range(rings+1):
        rr = radius*r/rings
        depth = rr*rr/(4*radius*.9)
        for s_ in range(sides):
            a = math.tau*s_/sides
            px, pz = rr*math.cos(a), rr*math.sin(a)
            # Dish frame: forward (fx, fy, .25), across (-fy, fx, 0), up.
            v.append((x+fx*depth-fy*px, y+fy*depth+fx*px, z+pz+depth*.25))
    for r in range(rings):
        for s_ in range(sides):
            a, b = r*sides+s_, r*sides+(s_+1) % sides
            f.append((a, b, b+sides, a+sides))
    # Its dished face toward facing_xy, its back a little behind it.
    add('dish', PAINT, (.88, .88, .86), v, [face[::-1] for face in f])
    back = [(px-fx*.25, py-fy*.25, pz) for px, py, pz in v]
    add('dish back', PAINT, (.70, .70, .68), back, f)
    # The rim joining its face to its back.
    outer = len(v)-sides
    add('dish rim', PAINT, (.80, .80, .78), v[outer:]+back[outer:], [(i, (i+1) % sides, sides+(i+1) % sides, sides+i) for i in range(sides)])
    add('dish rim', PAINT, (.80, .80, .78), v[outer:]+back[outer:], [(sides+i, sides+(i+1) % sides, (i+1) % sides, i) for i in range(sides)])
    u.tube('dish feed', [(x+fx*radius*.2, y+fy*radius*.2, z), (x+fx*radius*.9, y+fy*radius*.9, z+.2)], .18, STEEL, (.30, .31, .32), sides=4)
    u.tube('dish arm', [(x-fx*.4, y-fy*.4, z), (x-fx*3, y-fy*3, z-1.5)], .35, STEEL, (.30, .31, .32), sides=6)


def rect(x0, x1, y0, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def regular(cx, cy, radius, sides, start=0.0):
    return [(cx+radius*math.cos(math.radians(start)+math.tau*i/sides), cy+radius*math.sin(math.radians(start)+math.tau*i/sides))
            for i in range(sides)]


def turned(ring, angle, about=(0, 0)):
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    return [(about[0]+(x-about[0])*ca-(y-about[1])*sa, about[1]+(x-about[0])*sa+(y-about[1])*ca) for x, y in ring]


def volume(name, ring, z0, z1, radius=RADIUS, behind=CHAMFER):
    """A building volume inside a module's walls: its corners faceted as the module's (`radius`) and its outline kept
    `behind` the wall line, clear of the bevels where stacked storeys meet. The runtime lays a floor at every level
    within it, which must not show past the walls; 0 for both keeps a ring that is not a module's (glass, panels)."""
    if radius > 0:
        ring = [segment[0] for segment in faceted(ring, radius)]
    if behind > 0:
        ring = inset(ring, behind)
    c.volume(name, ring, z0, z1)


# -- Medical Center: two long wards and a corridor between them (5 hexes, an H) ------------------

def medical_center():
    """Two wards two storeys tall (the sheet's tall containers: an airlock below, a row of windows above, one teal
    stripe), a raised corridor container between them, plant on the roofs."""
    ground = lambda door: [('med-blank', 5), (door, W), ('med-blank', 5)]
    modules = []
    for side, x in (('west', -52.0), ('east', 52.0)):
        ring = rect(x-23, x+23, -66, 66)
        door = 'airlock-med' if side == 'west' else 'airlock'
        faces = {0: lambda storey, door=door: ground(door) if storey == 0 else [('blank', 6), ('three', W), ('blank', 6)],
                 1: lambda storey: ['med-blank', 'med-box', 'med-blank'] if storey == 0 else 'big',
                 2: lambda storey: [('med-blank', 6), ('vent', W), ('med-blank', 6)] if storey == 0 else [('blank', 6), ('wide', W), ('blank', 6)],
                 3: lambda storey: ['med-box', 'med-blank', 'med-blank'] if storey == 0 else 'big'}
        modules.append(Module(side+' ward', ring, storeys=2, faces=faces, axis=(0, 1), continuous=True, radius=7))
        volume(side+' ward', ring, 0, 2*LEVEL, radius=7)
    # The corridor: a lower container on skids between the wards, its ends inside them.
    modules.append(Module('corridor', rect(-31, 31, -14, 14), z0=4.0, lift=.95, faces={0: 'four', 2: 'four'}, hidden={1, 3},
                          axis=(1, 0)))
    for seed, module in enumerate(modules):
        build_module(module, seed)
    for x in (-14, 14):
        for y in (-11, 11):
            cuboid('corridor leg', x-1.2, x+1.2, y-1.2, y+1.2, 0, 4.4, PAINT, DARK, omit='b')
    volume('corridor', rect(-29, 29, -14, 14), 4, LEVEL-.1)
    top = 2*LEVEL
    for x in (-52.0, 52.0):
        lay(lambda: k.frontier_hvac(random.Random(3)), (x, -6), (0, 1), top+ROOF_LIFT, 1.9)
        fitting(k.frontier_radome, x+4, 44, top)
        fitting(k.frontier_hatch, x-9, 30, top)
        fitting(k.frontier_hatch, x+9, -40, top)
        k.pipe_run([(x-11, 50, top+ROOF_LIFT), (x-11, 50, top+1.6), (x-11, -40, top+1.6), (x-11, -40, top+ROOF_LIFT)])
    corridor_top = 4+LEVEL*.95+ROOF_LIFT
    k.pipe_run([(-30, 6, corridor_top), (-30, 6, corridor_top+.9), (30, 6, corridor_top+.9), (30, 6, corridor_top)])


def wall_ring(name, ring, z0, z1, key=PLATING, colour=(1, 1, 1), **flags):
    """Upright faces round a counter-clockwise ring, facing out."""
    for i in range(len(ring)):
        (ax, ay), (bx, by) = ring[i], ring[(i+1) % len(ring)]
        add(name, key, colour, [(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], [(0, 1, 2, 3)], **flags)


def frustum(name, low, z0, high, z1, key=PLATING, colour=(1, 1, 1), **flags):
    """Faces between two counter-clockwise rings of one count, facing out and up."""
    for i in range(len(low)):
        j = (i+1) % len(low)
        add(name, key, colour, [(*low[i], z0), (*low[j], z0), (*high[j], z1), (*high[i], z1)], [(0, 1, 2, 3)], **flags)


def cap(name, ring, z, key=PLATING, colour=(1, 1, 1), **flags):
    """A flat counter-clockwise polygon facing up."""
    add(name, key, colour, [(x, y, z) for x, y in ring], [tuple(range(len(ring)))], **flags)


def scaled(ring, factor, about=(0, 0)):
    return [(about[0]+(x-about[0])*factor, about[1]+(y-about[1])*factor) for x, y in ring]


def along_edges(ring, builder):
    """builder(length) laid along each edge of a counter-clockwise ring, as a kit piece along its wall."""
    for i in range(len(ring)):
        p, q = ring[i], ring[(i+1) % len(ring)]
        lay(lambda length=math.dist(p, q): builder(length), p, unit(p, q))


def glazing(name, ring, z0, z1, pitch=6.0, lit=True, inset_by=.6):
    """A band of glass round a ring, set back, steel mullions every `pitch`, a steel sill and head."""
    def band(length):
        k.glass(name, 0, length, z0, z1, inset_by, lit)
        count = max(1, round(length/pitch))
        for i in range(count+1):
            x = length*i/count
            cuboid(name+' mullion', x-.3, x+.3, -.2, inset_by, z0, z1, k.MATTE, FRAME, omit='bk')
        cuboid(name+' sill', 0, length, -.3, inset_by, z0-.6, z0, k.MATTE, FRAME, omit='k')
        cuboid(name+' head', 0, length, -.3, inset_by, z1, z1+.6, k.MATTE, FRAME, omit='k')
    along_edges(ring, band)


def sloped_glazing(name, ring, z0, z1, out, lit=True):
    """A control room's glass: each pane leaning out by `out` at its top, steel mullions at the corners and between."""
    n = len(ring)
    top = inset(ring, -out)
    for i in range(n):
        j = (i+1) % n
        quad = [(*ring[i], z0), (*ring[j], z0), (*top[j], z1), (*top[i], z1)]
        add(name, h.DARK_GLASS, k.GLAZING, quad, [(0, 1, 2, 3)], light='night' if lit else 'off')
        for t in (0.0, .5):
            a = (ring[i][0]+(ring[j][0]-ring[i][0])*t, ring[i][1]+(ring[j][1]-ring[i][1])*t)
            b = (top[i][0]+(top[j][0]-top[i][0])*t, top[i][1]+(top[j][1]-top[i][1])*t)
            u.tube(name+' mullion', [(a[0], a[1], z0), (b[0], b[1], z1)], .3, k.MATTE, FRAME, sides=4)
    return top


def control_room(name, ring, z0, sill, glass, head, out):
    """A glazed control room on a roof: a plated sill, glass leaning out, a steel head bevelled to its plated roof."""
    outline = [s[0] for s in faceted(ring, 6)]
    wall_ring(name+' sill', outline, z0, z0+sill)
    add(name+' soffit', PLATING, (1, 1, 1), [(x, y, z0) for x, y in outline][::-1], [tuple(range(len(outline)))])
    sloped_glazing(name+' glass', outline, z0+sill, z0+sill+glass, out)
    top = z0+sill+glass
    wall_ring(name+' head', inset(outline, -out), top, top+head, k.MATTE, FRAME)
    frustum(name+' head', inset(outline, -out), top+head, inset(outline, .6), top+head+1.6, k.MATTE, BEVEL)
    cap('roof plating '+name, inset(outline, .6), top+head+1.6)
    roof_axes['roof plating '+name] = unit(ring[0], ring[1])
    cap(name+' floor', inset(outline, .5), z0+sill-.2, PAINT, DARK)
    return top+head+1.6


def plant_housing(x0, x1, y0, y1, z, height=4.5):
    """A roof plant housing: a plated box on a dark kerb, louvres round it, a grille deck and two fans on top."""
    cuboid('plant kerb', x0-.6, x1+.6, y0-.6, y1+.6, z, z+.8, PAINT, DARK, omit='b')
    cuboid('plant housing', x0, x1, y0, y1, z+.8, z+height, k.MATTE, (.58, .60, .62), omit='b')
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        ux, uy = unit((ax, ay), (bx, by))
        nx, ny = uy, -ux
        length = math.dist((ax, ay), (bx, by))
        quad = [(ax+ux*1+nx*.05, ay+uy*1+ny*.05, z+1.6), (bx-ux*1+nx*.05, by-uy*1+ny*.05, z+1.6),
                (bx-ux*1+nx*.05, by-uy*1+ny*.05, z+height-.8), (ax+ux*1+nx*.05, ay+uy*1+ny*.05, z+height-.8)]
        if length > 4:
            add('plant louvre', k.SLATS, k.LOUVRE, quad, [(0, 1, 2, 3)])
    deck('plant grille', x0+.8, x1-.8, y0+.8, y1-.8, z+height+.02, h.GRILLE, (.62, .64, .66))
    for fx in ((x0*2+x1)/3, (x0+x1*2)/3):
        h.round_prism('plant fan', fx, (y0+y1)/2, z+height, z+height+.5, min(x1-x0, y1-y0)/4, PAINT, DARK, 12)


def facade_pipe(points, radius=.45):
    """A pipe along walls, clamped in orange, its ends into them."""
    k.pipe_run(points, radius)


def deck_markings(cx, cy, z, radius):
    """A landing pad's ring, white, broken in four."""
    for quarter in range(4):
        a0, a1 = math.radians(quarter*90+8), math.radians(quarter*90+82)
        steps = 10
        for s_ in range(steps):
            t0, t1 = a0+(a1-a0)*s_/steps, a0+(a1-a0)*(s_+1)/steps
            pts = [(cx+r*math.cos(t), cy+r*math.sin(t)) for r, t in ((radius-.8, t0), (radius+.8, t0), (radius+.8, t1), (radius-.8, t1))]
            add('pad ring', PAINT, (.86, .86, .82), [(x, y, z) for x, y in pts], [(0, 1, 2, 3)])


def bracket(x, y, z, sx, sy, size=6.0, width=1.0):
    """An orange L mark on a deck, its arms toward +sx and +sy."""
    for x0, x1, y0, y1 in ((x, x+sx*size, y, y+sy*width), (x, x+sx*width, y, y+sy*size)):
        deck('pad bracket', min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), z, PAINT, ORANGE)


def radiator(x0, x1, y0, y1, height):
    """A heat radiator panel: a steel frame on a plinth, dense fins on both faces, orange clamp bands, lugs on top."""
    cuboid('radiator plinth', x0-1.5, x1+1.5, y0-2, y1+2, 0, 3, PAINT, DARK, omit='b')
    cuboid('radiator core', x0+1, x1-1, y0+.6, y1-.6, 3, height-2, PAINT, (.22, .23, .24), omit='b')
    quad = [(x0+1, y0+.5, 3.4), (x1-1, y0+.5, 3.4), (x1-1, y0+.5, height-2.4), (x0+1, y0+.5, height-2.4)]
    add('radiator fins', h.GRILLE, (.50, .52, .54), quad, [(0, 1, 2, 3)])
    quad = [(x1-1, y1-.5, 3.4), (x0+1, y1-.5, 3.4), (x0+1, y1-.5, height-2.4), (x1-1, y1-.5, height-2.4)]
    add('radiator fins', h.GRILLE, (.50, .52, .54), quad, [(0, 1, 2, 3)])
    for xa, xb in ((x0, x0+1.4), (x1-1.4, x1)):
        cuboid('radiator frame', xa, xb, y0, y1, 3, height, k.MATTE, FRAME, omit='b')
    cuboid('radiator frame', x0, x1, y0, y1, height-2, height, k.MATTE, FRAME, omit='b')
    cuboid('radiator frame', x0, x1, y0, y1, 3, 4.2, k.MATTE, FRAME, omit='b')
    for z in (height*.35, height*.7):
        for xa, xb in ((x0-.3, x0+1.7), (x1-1.7, x1+.3)):
            cuboid('radiator clamp', xa, xb, y0-.3, y1+.3, z, z+1.2, PAINT, ORANGE, omit='')
    cuboid('radiator header', x0+1.5, x1-1.5, y0+.3, y1-.3, height, height+2.4, k.MATTE, FRAME, omit='b')
    for x in (x0+1.5, x1-1.5):
        h.round_prism('radiator header cap', x, (y0+y1)/2, height+.2, height+2.2, 1.4, PAINT, DARK, 8)


def vault_profile(half, base, eave, ridge, top_half):
    """A glass tunnel's section (x, z) from one foot to the other: upright to the eave, chamfered to a flat top."""
    return [(-half, base), (-half, eave), (-top_half, ridge), (top_half, ridge), (half, eave), (half, base)]


def glass_tunnel(cx, y0, y1, half, base, rng):
    """A hydroponic tunnel along y: a plated base on skids, a glass vault of steel ribs, racks of greens under grow
    lights; its front a glazed gable over the base, an airlock in it. Its back end stands inside the service block."""
    eave, ridge, top_half = base+12.0, base+18.0, half-6.0  # Mostly upright glass: from iso the crops show through it.
    prof = vault_profile(half, base, eave, ridge, top_half)
    ring = rect(cx-half, cx+half, y0, y1)
    build_module(Module('tunnel base %d' % cx, ring, faces={1: 'blank', 3: 'blank'}, hidden={0, 2}, lift=base/LEVEL, roof=False,
                        radius=0), seed=int(cx))
    cap('tunnel floor', inset(ring, .2), base, PAINT, (.56, .57, .56))
    # The base's front, plated round the airlock.
    door = 5.4
    for a, b in ((cx-half, cx-door), (cx+door, cx+half)):
        add('tunnel front', PLATING, (1, 1, 1), [(a, y0, k.FOOT), (b, y0, k.FOOT), (b, y0, base), (a, y0, base)], [(0, 1, 2, 3)])
    cuboid('tunnel sill', cx-half, cx+half, y0-.4, y0+.4, base-.6, base+.4, k.MATTE, FRAME, omit='b')
    add('foot recess', PAINT, DARK, [(cx-half, y0+.8, 0), (cx+half, y0+.8, 0), (cx+half, y0+.8, k.FOOT), (cx-half, y0+.8, k.FOOT)], [(0, 1, 2, 3)])
    lay(lambda: k.airlock(rng, 'plain', face=False), (cx-W/2, y0), (1, 0), 0)
    h.fixtures.append((cx, y0-4, 12))
    # Glass along the vault, between ribs; the upright sides from the base's top.
    for side in range(1, len(prof)-2):
        (ax, az), (bx, bz) = prof[side], prof[side+1]
        add('tunnel glass', DUSTY_GLASS, (1, 1, 1), [(cx+ax, y0, az), (cx+ax, y1, az), (cx+bx, y1, bz), (cx+bx, y0, bz)], [(3, 2, 1, 0)])
    for sign in (-1, 1):
        x = cx+sign*half
        quad = [(x, y0, base), (x, y1, base), (x, y1, eave), (x, y0, eave)]
        add('tunnel glass', DUSTY_GLASS, (1, 1, 1), quad if sign > 0 else quad[::-1], [(0, 1, 2, 3)])
    gable = [(cx+x, y0, z) for x, z in prof]
    add('tunnel gable', DUSTY_GLASS, (1, 1, 1), gable, [tuple(range(len(gable)))[::-1]])
    ribs = max(2, round((y1-y0)/19))
    for i in range(ribs+1):
        y = y0+(y1-y0)*i/ribs
        u.tube('tunnel rib', [(cx+x, y, z) for x, z in prof], 1.1, k.MATTE, FRAME, sides=4)
        if i % 2:
            for x, z in prof[1:-1]:
                cuboid('rib clamp', cx+x-1.3, cx+x+1.3, y-1.3, y+1.3, z-1.3, z+1.3, PAINT, ORANGE, detail=True)
    for x, z in prof[1:-1]:
        u.tube('tunnel purlin', [(cx+x, y0, z), (cx+x, y1, z)], .45, k.MATTE, FRAME, sides=4)
    # Racks of greens and their lights, along the tunnel.
    for x in (-(half-3.5), 0.0, half-3.5):
        cuboid('grow rack', cx+x-2.2, cx+x+2.2, y0+3, y1-3, base, base+2.2, PAINT, (.42, .44, .46), omit='b')
        # A soil trough on the rack, two rows of leafy greens in it.
        cuboid('rack trough', cx+x-2.0, cx+x+2.0, y0+3.2, y1-3.2, base+2.2, base+2.8, PAINT, (.22, .19, .15), omit='b')
        for row in (-1.05, 1.05):
            yy = y0+4.4+rng.uniform(0, 1.2)
            while yy < y1-4.4:
                u.shrub(cx+x+row+rng.uniform(-.25, .25), yy, base+2.8, rng.uniform(2.4, 3.4), rng)
                yy += rng.uniform(2.2, 2.9)
        # Under the glass over its rack: the flat top, or the chamfer over an outer rack.
        glass_z = ridge if abs(x) <= top_half else eave+(half-abs(x)-.4)/(half-top_half)*(ridge-eave)
        cuboid('grow light', cx+x-.4, cx+x+.4, y0+3, y1-3, glass_z-1.8, glass_z-1.4, PAINT, (.90, .88, .80), light=GROW_LIGHT)
    h.fixtures.append((cx, (y0+y1)/2, ridge-2))
    u.flush_cards()


# -- Trade Exchange: a hexagonal hall, three wings (4 hexes) ------------------------------------------

def trade_exchange():
    """The hall in the centre hex, its roof hipped up to a glazed lantern; three shop wings into the north, south-east
    and south-west hexes, louvred at their ends; the airlock in the hall's south face between the south wings."""
    hall = regular(0, 0, 38, 6)
    faces = {0: 'wide', 1: 'wide', 2: 'wide', 3: 'wide', 4: [('wide', 4), ('airlock', W), ('wide', 4)], 5: 'wide'}
    lift = 1.3
    build_module(Module('hall', hall, faces=faces, roof=False, radius=4, lift=lift), seed=1)
    # The hipped roof from the walls' top bevels up to the lantern.
    outline = [s[0] for s in faceted(hall, 4)]
    wall = LEVEL*lift
    low = inset(outline, CHAMFER)
    high = scaled(outline, .45)
    frustum('roof plating hall', low, wall, high, LEVEL+12.5)
    roof_axes['roof plating hall'] = (1, 0)
    for i in range(0, len(low), 2):  # Hip ribs at the hexagon's corners.
        u.tube('hall hip rib', [(*low[i], LEVEL+6.8), (*high[i], LEVEL+12.9)], .6, k.MATTE, FRAME, sides=4)
    wall_ring('lantern', high, LEVEL+12.5, LEVEL+13.3, k.MATTE, FRAME)
    glazing('lantern glass', high, LEVEL+13.3, LEVEL+16.4, pitch=5, inset_by=0)
    cap('roof plating lantern', high, LEVEL+17.0)
    roof_axes['roof plating lantern'] = (1, 0)
    sky = scaled(high, .62)
    cap('skylight', sky, LEVEL+17.1, SKYLIGHT, GLASS_TINT)
    for corner in sky:
        u.tube('skylight rib', [(0, 0, LEVEL+17.2), (*corner, LEVEL+17.2)], .25, k.MATTE, FRAME, sides=4)
    add('lantern light', PAINT, (.90, .80, .55), [(x, y, LEVEL+16.3) for x, y in scaled(high, .9)][::-1], [tuple(range(len(high)))],
        light=c.AMBER_LIGHT)
    h.fixtures.append((0, 0, LEVEL+14))
    # A radome on a pad at the north-east of the roof, grilles on three facets.
    r_low, r_high = math.hypot(*low[1]), math.hypot(*high[1])
    on_roof = lambda r: wall+(r_low-r)/(r_low-r_high)*(LEVEL+12.5-wall)
    cuboid('radome pad', 17, 24, 9, 16, on_roof(28)-1.2, on_roof(21)-.2, PAINT, DARK)
    fitting(k.frontier_radome, 20, 12, on_roof(21)-.2-ROOF_LIFT)
    for angle in (150, 270, 30):
        a = math.radians(angle)
        lay(lambda angle=angle: k.frontier_hatch(random.Random(angle)), (24*math.cos(a), 24*math.sin(a)),
            (math.cos(a+math.pi/2), math.sin(a+math.pi/2)), on_roof(24)-.5)
    volume('hall', hall, 0, LEVEL+17, radius=4)
    # The wings: one storey, their inner ends inside the hall.
    wing = rect(-17, 17, 26, 70)
    wing_faces = {1: ['wide', 'boxes'], 2: [('blank', 5), ('louvre', W), ('blank', 5)], 3: ['vent', 'wide']}
    for seed, (name, angle) in enumerate((('north', 0), ('south-east', -120), ('south-west', 120))):
        a = math.radians(90+angle)
        build_module(Module(name+' wing', turned(wing, angle), faces=wing_faces, hidden={0}, axis=(math.cos(a), math.sin(a))),
                     seed=20+seed)
        volume(name+' wing', turned(rect(-17, 17, 33, 70), angle), 0, LEVEL)
        for t in (48, 62):
            x, y = turned([(0, t)], angle)[0]
            fitting(k.frontier_hatch, x, y, LEVEL, angle)
        x, y = turned([(-6, 54)], angle)[0]
        fitting(k.frontier_solar, x, y, LEVEL, 90+angle)


# -- Command & Comms: a two-storey block, a control room cantilevered at its front corner, a mast ------

def command_comms():
    """The ground storey's container (the airlock at its front left, a band of windows), the upper container over it,
    the control room standing out from the upper storey's front right, its glass leaning out; pipes along the storey
    line and down the side; on the roof a plant housing, grilles, pipes and a lattice mast with a dish, to about four
    levels."""
    x0, x1, y0, y1 = -5.0, 67.0, -18.0, 54.0
    ground = Module('ground', rect(x0, x1, y0, y1), axis=(1, 0),
                    faces={0: [('airlock', W), ('wide', W), ('boxes', 14)], 1: ['pair', 'vent', 'pair'], 2: ['four', 'pair', 'four'],
                           3: ['pair', 'single', 'pair']})
    upper = Module('upper', rect(x0, x1, y0, y1), z0=LEVEL, axis=(1, 0),
                   faces={0: ['pair', 'blank', 'blank'], 1: ['pair', 'four', 'pair'], 2: ['pair', 'pair', 'single'], 3: ['pair', 'vent', 'pair']})
    for seed, module in enumerate((ground, upper)):
        build_module(module, seed)
    control_room('control room', rect(28, 69, -34, 6), LEVEL, 2.0, 12.0, 2.5, 1.8)
    lay(lambda: k.chevrons(0, 0, 1.6), (56, -34), (1, 0), LEVEL+.4)
    h.fixtures.append((48, -32, LEVEL+8))
    volume('ground', rect(x0, x1, y0, y1), 0, LEVEL)
    volume('upper', rect(x0, x1, y0, y1), LEVEL, 2*LEVEL)
    volume('control room', rect(28, 69, -34, y0), LEVEL, 2*LEVEL-.1, radius=0, behind=0)
    # Pipes along the storey line and down the east side.
    facade_pipe([(x0+3, y0, LEVEL-3.6), (x0+3, y0-.8, LEVEL-3.6), (x1-4, y0-.8, LEVEL-3.6), (x1-4, y0-.8, LEVEL-6), (x1-4, y0, LEVEL-6)])
    facade_pipe([(x1, 30, 2*LEVEL-4), (x1+.8, 30, 2*LEVEL-4), (x1+.8, 30, 4), (x1+.8, 10, 4), (x1, 10, 4)])
    top = 2*LEVEL
    plant_housing(14, 36, 16, 34, top+ROOF_LIFT)
    fitting(k.frontier_hatch, 50, 42, top)
    fitting(k.frontier_hatch, 50, 30, top)
    mast(5, 44, top+ROOF_LIFT, 36, random.Random(4))
    k.pipe_run([(9, 36, top+ROOF_LIFT), (9, 36, top+1.4), (9, 4, top+1.4), (40, 4, top+1.4), (40, 14, top+1.4), (40, 14, top+ROOF_LIFT)])


# -- Power & Thermal Plant: an octagonal core, two modules, two tall radiators (3 hexes) ----------------

def power_plant():
    """The core in the back hex, its walls a storey and a third under a roof hipped to a flat top with grilles and a
    radome; a module against each of its front corners; a radiator behind each module, beside the core's flanks,
    piped from them."""
    core = regular(0, 0, 34, 8, 22.5)
    lift = 1.3
    faces = {5: [('blank', 2), ('airlock', W), ('blank', 2)], 4: 'vent', 6: 'vent', 3: 'louvre', 7: 'louvre', 0: 'blank', 1: 'blank', 2: 'blank'}
    build_module(Module('core', core, faces=faces, roof=False, radius=3, lift=lift), seed=2)
    outline = [s_[0] for s_ in faceted(core, 3)]
    wall = LEVEL*lift
    tiers = [(inset(outline, CHAMFER), wall), (scaled(outline, .86), wall+3), (scaled(outline, .68), wall+6), (scaled(outline, .46), wall+8)]
    for (low, z0), (high, z1) in zip(tiers, tiers[1:]):
        frustum('roof plating core', low, z0, high, z1)
    roof_axes['roof plating core'] = (0, 1)
    for i in range(0, len(outline), 2):  # Ribs up the octagon's corners.
        u.tube('core rib', [(*tier[i], z+.3) for tier, z in tiers], .55, k.MATTE, FRAME, sides=4)
    top = tiers[-1][0]
    frustum('core top rim', top, wall+8, scaled(top, .9), wall+8.6, k.MATTE, FRAME)
    cap('roof plating core top', scaled(top, .9), wall+8.6)
    roof_axes['roof plating core top'] = (0, 1)
    for x in (-6, 6):
        deck('core grille', x-3.2, x+3.2, -7, 7, wall+8.62, h.GRILLE, (.62, .64, .66))
    fitting(k.frontier_radome, 0, 10, wall+8.3)
    volume('core', core, 0, 2*LEVEL-.1, radius=3)
    for side in (-1, 1):
        ring = rect(-66, -24, -54, -24) if side < 0 else rect(24, 66, -54, -24)
        faces = {0: ['pair', 'pair'], 1 if side > 0 else 3: ['vent'], 2: ['blank', 'blank'], 3 if side > 0 else 1: 'blank'}
        build_module(Module('module %d' % side, ring, faces=faces, axis=(1, 0)), seed=5+side)
        volume('module %d' % side, ring, 0, LEVEL)
        lay(lambda: (deck('module grille', -6, 6, -4, 4, .62, h.GRILLE, (.62, .64, .66)),
                     cuboid('module grille kerb', -6.4, 6.4, -4.4, 4.4, 0, .6, PAINT, DARK, omit='b')), (side*45, -39), (1, 0), LEVEL+ROOF_LIFT)
        x0, x1 = (-64, -32) if side < 0 else (32, 64)
        radiator(x0, x1, -18, -12, 46)
        volume('radiator %d' % side, rect(x0+1, x1-1, -17.1, -12.9), 0, 46, radius=0, behind=0)
        # Two heavy pipes from the core's flank, out, back and up into the radiator's back at two thirds of its height.
        for i, y in enumerate((4, -3)):
            k.pipe_run([(side*30, y, 8+i*4), (side*38+side*i*5, y, 8+i*4), (side*38+side*i*5, -8, 8+i*4), (side*38+side*i*5, -8, 30),
                        (side*38+side*i*5, -12.5, 30)], radius=1.6)


# -- Hydroponics: two glass tunnels and a two-storey service block (4 hexes) ---------------------------

def hydroponics():
    """Two glass tunnels side by side from the front, a tall service block across their backs."""
    rng = random.Random(11)
    for cx in (6.0, 56.0):
        glass_tunnel(cx, -30, 104, 24, 8.0, rng)
        volume('tunnel %d' % cx, rect(cx-24, cx+24, -30, 102), 0, LEVEL-.1, radius=0, behind=0)  # One level: no floor through the glass.
    cuboid('tunnel spine', 29.4, 32.6, -30, 104, 0, 17.0, k.MATTE, FRAME, omit='b')
    block = rect(-19, 81, 102, 140)
    faces = {0: 'blank', 1: ['louvre', 'blank'], 2: ['vent', 'blank', 'louvre', 'blank'], 3: ['blank', 'vent']}
    build_module(Module('service block', block, storeys=2, continuous=True, faces=faces, axis=(1, 0), radius=6, lift=.8), seed=3)
    volume('service block', block, 0, 2*LEVEL*.8, radius=6)
    top = 2*LEVEL*.8
    for x in (8, 20, 32):
        lay(lambda x=x: k.frontier_hvac(random.Random(int(x))), (x, 128), (1, 0), top+ROOF_LIFT, 1.1)
    fitting(k.frontier_radome, 66, 128, top)
    k.pipe_run([(46, 132, top+ROOF_LIFT), (46, 132, top+1.4), (60, 132, top+1.4), (60, 116, top+1.4), (60, 116, top+ROOF_LIFT)])


# -- Fabrication Workshop: a gabled hall and a long annex (4 hexes) -----------------------------------

def fabrication_workshop():
    """The hall: plated walls under a chamfered roof, dark steel portal ribs across it, a roll-up door under an orange
    beam in its front gable; the annex along its east side, one storey, louvred, its airlock at the front."""
    x0, x1, y0, y1 = -15.0, 39.0, -24.0, 116.0
    wall, ridge, ridge_half = 24.0, 39.0, 9.0
    cx, half = (x0+x1)/2, (x1-x0)/2
    hall = rect(x0, x1, y0, y1)
    faces = {1: 'blank', 2: 'blank', 3: ['blank', 'louvre', 'blank', 'blank', 'louvre', 'blank']}
    build_module(Module('hall', hall, faces=faces, roof=False, lift=wall/LEVEL, hidden={0}, radius=0), seed=4)
    eave = half-CHAMFER  # The walls' top bevels reach the roof here.
    prof = [(-eave, wall), (-ridge_half, ridge), (ridge_half, ridge), (eave, wall)]
    for (ax, az), (bx, bz) in zip(prof, prof[1:]):
        add('roof plating hall', PLATING, (1, 1, 1), [(cx+ax, y0, az), (cx+bx, y0, bz), (cx+bx, y1, bz), (cx+ax, y1, az)], [(0, 1, 2, 3)])
    roof_axes['roof plating hall'] = (0, 1)
    for y, back in ((y0, False), (y1, True)):
        gable = [(cx-eave, y, wall), (cx+eave, y, wall), (cx+ridge_half, y, ridge), (cx-ridge_half, y, ridge)]
        add('gable plating', PLATING, (1, 1, 1), gable[::-1] if back else gable, [(0, 1, 2, 3)])
        u.tube('gable frame', [(cx-half, y-.6, wall), (cx-eave, y-.6, wall), (cx-ridge_half, y-.6, ridge), (cx+ridge_half, y-.6, ridge),
                               (cx+eave, y-.6, wall), (cx+half, y-.6, wall)], 1.6, k.MATTE, FRAME, sides=4)
    ribs = 5
    for i in range(ribs+1):
        y = y0+.8+(y1-y0-1.6)*i/ribs
        path = [(cx-half-1.4, y, 0), (cx-half-1.4, y, wall)]+[(cx+x*(1+1.4/eave), y, z+.8) for x, z in prof]+[(cx+half+1.4, y, wall), (cx+half+1.4, y, 0)]
        u.tube('portal rib', path, 1.2, PAINT, (.26, .27, .28), sides=4)
    # The front: plated round a roll-up door under an orange beam, louvres beside it, grilles high in the gable.
    door_w, door_h = 24.0, 19.0
    for a, b, za, zb in ((x0, cx-door_w/2-1.6, 0, wall), (cx+door_w/2+1.6, x1, 0, wall), (cx-door_w/2-1.6, cx+door_w/2+1.6, door_h+2.2, wall)):
        za = max(za, k.FOOT)
        add('hall front', PLATING, (1, 1, 1), [(a, y0, za), (b, y0, za), (b, y0, zb), (a, y0, zb)], [(0, 1, 2, 3)])
    add('foot recess', PAINT, DARK, [(x0, y0+.8, 0), (x1, y0+.8, 0), (x1, y0+.8, k.FOOT), (x0, y0+.8, k.FOOT)], [(0, 1, 2, 3)])
    for x in (x0, x1):
        cuboid('hall corner post', x-1.2, x+1.2, y0-1.2, y0+1.2, 0, wall, k.MATTE, FRAME, omit='b')
    for a, b in ((cx-door_w/2-1.6, cx-door_w/2), (cx+door_w/2, cx+door_w/2+1.6)):
        cuboid('door jamb', a, b, y0-1.2, y0, 0, door_h, PAINT, ORANGE, omit='k')
    cuboid('door beam', cx-door_w/2-3, cx+door_w/2+3, y0-1.6, y0, door_h, door_h+2.2, PAINT, ORANGE, omit='k')
    add('door shutter', k.SLATS, k.SHUTTER, [(cx-door_w/2, y0-.2, 0), (cx+door_w/2, y0-.2, 0), (cx+door_w/2, y0-.2, door_h),
                                            (cx-door_w/2, y0-.2, door_h)], [(0, 1, 2, 3)])
    for x in (cx-6, cx, cx+6):
        cuboid('door window', x-2.2, x+2.2, y0-.3, y0-.2, 11, 12.6, PAINT, DARK, omit='k')
    lay(lambda: k.chevrons(0, 0, 2.2, 4), (cx-3.5, y0-.32), (1, 0), 3)
    for x in (cx-door_w/2-6, cx+door_w/2+6):
        lay(lambda: (cuboid('louvre frame', -2.2, 2.2, -.3, 0, 3, 11, PAINT, DARK, omit='k'),
                     add('louvre', k.SLATS, k.LOUVRE, [(-1.8, -.32, 3.4), (1.8, -.32, 3.4), (1.8, -.32, 10.6), (-1.8, -.32, 10.6)], [(0, 1, 2, 3)])),
            (x, y0), (1, 0), 0)
    for x in (cx-4, cx+4):
        add('gable grille', h.GRILLE, (.62, .64, .66), [(x-3, y0-.3, 28), (x+3, y0-.3, 28), (x+3, y0-.3, 32), (x-3, y0-.3, 32)], [(0, 1, 2, 3)])
    for x in (cx-door_w/2+3, cx+door_w/2-3):
        add('door light', PAINT, (.9, .8, .5), [(x-2.5, y0-1.7, door_h-1.1), (x+2.5, y0-1.7, door_h-1.1), (x+2.5, y0-1.7, door_h-.3),
                                                (x-2.5, y0-1.7, door_h-.3)], [(0, 1, 2, 3)], light=c.AMBER_LIGHT)
    h.fixtures.append((cx, y0-6, door_h))
    # Two levels: the volume stops under the third's floor, or the runtime's floor there would stand through the roof.
    volume('hall', hall, 0, 2*LEVEL-.1, radius=0)
    # The annex.
    annex = rect(x1-2, 67, y0, y1)
    build_module(Module('annex', annex, faces={0: [('blank', 6), ('airlock', W), ('blank', 6)],
                                               1: ['louvre', 'blank', 'louvre', 'blank', 'louvre', 'blank'], 2: 'blank'},
                        hidden={3}, axis=(0, 1)), seed=6)
    volume('annex', rect(x1, 67, y0, y1), 0, LEVEL)
    top = LEVEL
    for y in (8, 64):
        lay(lambda y=y: k.frontier_hvac(random.Random(int(y))), (53, y), (0, 1), top+ROOF_LIFT, 1.2)
    fitting(k.frontier_radome, 56, 30, top)
    k.pipe_run([(59, 100, top+ROOF_LIFT), (59, 100, top+1.4), (59, -14, top+1.4), (59, -14, top+ROOF_LIFT)])
    facade_pipe([(67, 100, 3.5), (67.8, 100, 3.5), (67.8, -14, 3.5), (67, -14, 3.5)])


# -- Cargo Terminal: a loading block, its roof a landing deck, a control tower at its back corner (4 hexes) --

def cargo_terminal():
    """The block one storey, three roll-up doors in front, battered steel piers at its corners; its roof a standable
    deck of diamond plate with a pad ring and corner marks, lights along its rim, a rail along the back; the tower at
    the back right: a storey on the deck and a glazed control room."""
    x0, x1, y0, y1 = -26.0, 88.0, -6.0, 112.0
    block = rect(x0, x1, y0, y1)
    faces = {0: [('blank', 8), ('rollup', 30), ('rollup', 30), ('rollup', 30), ('blank', 8)], 1: ['blank', 'vent', 'blank', 'vent', 'blank'],
             2: ['blank', 'louvre', 'blank', 'louvre', 'blank'], 3: ['blank', 'vent', 'blank', 'blank', 'blank']}
    build_module(Module('block', block, faces=faces, radius=6, roof_key=k.MATTE, roof_colour=(.46, .47, .49)), seed=8)
    # The deck's heavy fascia standing out round the block, flush with the deck.
    outline = [s_[0] for s_ in faceted(block, 6)]
    fascia = inset(outline, -2.5)
    wall_ring('deck fascia', fascia, LEVEL-3.5, LEVEL+ROOF_LIFT, k.MATTE, FRAME)
    add('deck fascia soffit', PAINT, DARK, [(x, y, LEVEL-3.5) for x, y in fascia][::-1], [tuple(range(len(fascia)))])
    frustum('deck fascia', fascia, LEVEL+ROOF_LIFT, inset(outline, CHAMFER), LEVEL+ROOF_LIFT, k.MATTE, FRAME)
    top = LEVEL
    cx, cy = (x0+x1)/2-8, (y0+y1)/2-6
    deck_markings(cx, cy, top+ROOF_LIFT+.02, 26)
    for sx, sy, x, y in ((1, 1, x0+10, y0+10), (-1, 1, x1-10, y0+10), (1, -1, x0+10, y1-10)):
        bracket(x, y, top+ROOF_LIFT+.02, sx, sy)
    for p, q, edge in faceted(block, 6):
        if edge is None:
            continue
        n = max(1, int(math.dist(p, q)//24))
        nx, ny = outward(p, q)
        for i in range(n):
            t = (i+.5)/n
            x, y = p[0]+(q[0]-p[0])*t+nx*2.55, p[1]+(q[1]-p[1])*t+ny*2.55
            lay(lambda: add('deck light', PAINT, (.50, .42, .26), [(-2, 0, -1.1), (2, 0, -1.1), (2, 0, -.6), (-2, 0, -.6)], [(0, 1, 2, 3)],
                            light=c.AMBER_LIGHT), (x, y), unit(p, q), top)
    rail_y = y1-CHAMFER-2
    for x in range(int(x0+8), int(x1-36), 9):
        cuboid('rail post', x-.2, x+.2, rail_y-.2, rail_y+.2, top+ROOF_LIFT, top+3.6, k.MATTE, FRAME, omit='b', detail=True)
    cuboid('rail', x0+8, x1-36, rail_y-.15, rail_y+.15, top+3.4, top+3.7, PAINT, ORANGE, omit='')
    cuboid('rail mid', x0+8, x1-36, rail_y-.12, rail_y+.12, top+2, top+2.2, PAINT, ORANGE, omit='', detail=True)
    # Battered piers at the corners.
    for x, y, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        # Battered: wide on the ground, out past the corner, narrowing to meet the fascia.
        foot_ = rect(*sorted((x-sx*5, x+sx*12)), *sorted((y-sy*5, y+sy*12)))
        head = rect(*sorted((x-sx*2.5, x+sx*12)), *sorted((y-sy*2.5, y+sy*12)))
        frustum('pier', foot_, 0, head, LEVEL-3.5, PAINT, (.30, .31, .32))
        cap('pier top', head, LEVEL-3.5, PAINT, (.30, .31, .32))
        h.round_prism('pier light', x-sx*3.2, y-sy*3.2, 1.6, 2.2, .6, PAINT, (.50, .42, .26), 6, light=c.AMBER_LIGHT)
    volume('block', block, 0, LEVEL, radius=6)
    # The tower: a storey on the deck and the control room over it.
    tower = rect(54, 84, 78, 108)
    build_module(Module('tower', tower, z0=LEVEL, faces={0: ['pair'], 3: ['pair'], 1: ['vent'], 2: ['blank']}, roof=False, radius=4), seed=12)
    cap('tower top', inset(tower, .2), 2*LEVEL+.3, PAINT, DARK)
    roof = control_room('control room', rect(52, 86, 76, 110), 2*LEVEL, 2.5, 6.0, 2.5, 1.2)
    h.fixtures.append((69, 70, 2*LEVEL+6))
    fitting(k.frontier_radome, 76, 98, roof-ROOF_LIFT)
    fitting(k.frontier_hatch, 62, 92, roof-ROOF_LIFT)
    lay(lambda: (cuboid('mast antenna', -.2, .2, -.2, .2, 0, 9, k.MATTE, FRAME, omit='b'),
                 cuboid('mast antenna', -.12, .12, -1.4, 1.4, 6, 6.2, k.MATTE, FRAME, detail=True)), (64, 104), (1, 0), roof)
    volume('tower', rect(54, 84, 78, 108), LEVEL, roof, radius=4)


BUILDINGS = {'trade-exchange': trade_exchange, 'command-comms': command_comms, 'power-plant': power_plant,
             'hydroponics': hydroponics, 'fabrication-workshop': fabrication_workshop, 'cargo-terminal': cargo_terminal,
             'medical-center': medical_center}
FINE = ('marker light', 'chevron', 'clamp', 'mullion', 'window frame', 'antenna', 'marking', 'mast brace', 'mast ring',
        'dish feed', 'louvre', 'beacon post', 'planting')


def far_piece(obj):
    """Whether a part stays at the farthest level: all but the small fittings and marks."""
    name = re.sub(r'\.\d+$', '', obj.name)
    return not any(word in name for word in FINE)


def build_scene(name):
    full = 'frontier-'+name
    h.weathered_material.__defaults__[0].clear()
    shared.fresh(full)
    shared.role = ''
    h.bins.clear()
    h.fixtures.clear()
    roof_axes.clear()
    h.SHIFT_Y = 0
    k.NUMBERED = False
    BUILDINGS[name]()
    h.flush()
    for obj in shared.objects:
        if obj['board_material'] == PLATING and not obj.data.uv_layers:
            plating_uvs(obj)
    for obj in shared.volumes:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    for obj in shared.objects:
        shared.project_uvs(obj)
    bpy.context.scene['asset_id'] = 'buildings/authored/'+full
    bpy.context.scene['hex_width'], bpy.context.scene['hex_height'], bpy.context.scene['level_height'] = 83.125, 72, LEVEL
    return full


def build(name):
    full = build_scene(name)
    bpy.context.view_layer.update()
    levels = {i: shared.export_model([obj for obj in shared.objects if i < 2 or far_piece(obj)], f'{full}-lod{i}', level=i, exact=True)
              for i in (0, 1, 2)}
    helpers = shared.export_model(shared.volumes, full, helper=True)
    stats = {i: {'vertices': sum(len(m['vertices'])//12 for m in level['meshes']),
                 'triangles': sum(len(p['indices'])//3 for m in level['meshes'] for p in m['parts'])} for i, level in levels.items()}
    assert all(s['vertices'] < 65535 for s in stats.values()), stats
    lights = [{'position': [x, z, -y], 'color': [1, .64, .29], 'power': .65, 'size': 13} for x, y, z in h.fixtures]
    write_glb(shared.DEST/(full+'.glb'), levels=levels, groups={'building_volumes': helpers}, extras={'mmNightLights': lights})
    print('RESULT', full, stats, 'lights', len(lights))
    return stats


if __name__ == '__main__' and '--' in sys.argv:
    args = sys.argv[sys.argv.index('--')+1:]
    build(args[0])
    if len(args) > 1:
        u.sheet(args[0], args[1], see_through=(DUSTY_GLASS,))
