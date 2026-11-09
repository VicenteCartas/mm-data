"""The Utopia buildings: flowing cream stone, planted terraces, oval louvres. One builder per sheet in references/utopia-*.png.

Run: blender -b --factory-startup --python utopia_buildings.py -- <name> [<sheet folder>]
Writes data/models/buildings/authored/utopia-<name>.glb, and with a folder a four-view sheet laid out like the reference's.
Every level is built by the same code at its own detail (LOD), so far levels keep the outlines and need no merging.
Plan rings come from the reference's top view; one storey is one level (18 units, 6 m); doors stay 1.4 x 2.6 m.
"""
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import authored_examples as shared
from glb_geometry import write_glb

STONE = 'structures/common/white-stone'
STONE_TINT = (1, .985, .96)
STONE_SHADE = (.88, .87, .85)
SLAT = (.94, .93, .91)
PAVE = STONE
PAVE_TINT = (.93, .92, .88)
DECK_TINT = (.98, .86, .70)
TURF, TURF_TINT = 'terrain/surfaces/grassland-ground', (1, 1, 1)  # Lawn, as the modular kit's roofs (theme_kits.LAWN).
LAWN_REPEAT = 36  # Units one lawn texture repeat covers: the board's own grass scale.
GLASS = 'structures/buildings/tower-glass'
GLASS_TINT = (.94, .94, .80)
DOME_GLASS = 'structures/buildings/tower-glass'
FRAME = 'structures/common/painted-steel'
FRAME_TINT = (.30, .27, .24)
RAIL = 'structures/common/satin-steel'
RAIL_TINT = (.62, .62, .60)
FLAT = shared.FLAT
BUSH = 'vegetation/forest-willow-cutout'
BUSH2 = 'vegetation/creosote-cutout'
SPIKE = 'vegetation/desert-shrub-cutout'
FLOWER = 'vegetation/cactus-flower-cutout'
BARK = 'vegetation/forest-bark'
LILAC = (.60, .48, .72)
BUSH_TINTS = ((1, 1, .9), (.94, 1, .82), (1, .98, .8), (.88, .98, .76))
LOBBY = (.80, .80, .68)
NIGHT, NIGHT_GLASS = (.50, .38, .22), (.14, .11, .065)
FIN = (.62, .63, .60)
LOUVRE = {'back': 2.2, 'front': 1.4, 'half': .25, 'pitch': 3}
LOUVRE_BACK = (.10, .09, .08)
DARK_INSET = {0: 4.2, 1: 7.0, 2: 9.0}
FAR_GREEN = (.60, .64, .37)
REPEAT = 54  # Units one stone texture repeat covers: its panels are 27 units, 9 m.

LOD = 0
near_plants = []  # The near level's plants and trees, in order.
near_rooms, strips_seen = {}, {}  # The near level's lit rooms per strip of glass, by name and order, as shares of its length.
SAMPLES = {0: 120, 1: 40, 2: 20}


# Rings: plan outlines as N x 2 arrays, counter-clockwise, sampled at even angles round one centre so that any two can blend.
def spline(points, dense=24):
    """A closed Catmull-Rom curve through points."""
    p = np.array(points, float)
    out = []
    for i in range(len(p)):
        a, b, c, d = p[i-1], p[i], p[(i+1) % len(p)], p[(i+2) % len(p)]
        for t in np.linspace(0, 1, dense, endpoint=False):
            out.append(.5*(2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(3*b-a-3*c+d)*t*t*t))
    return np.array(out)


def polar_ring(points, centre, n=None):
    """A closed curve through points, as the ring of n points at even angles round centre (it must be star-shaped)."""
    n = n or SAMPLES[LOD]
    curve = spline(points)-np.array(centre)
    angle, radius = np.arctan2(curve[:, 1], curve[:, 0]), np.hypot(curve[:, 0], curve[:, 1])
    order = np.argsort(angle)
    angle, radius = angle[order], radius[order]
    wanted = np.linspace(-math.pi, math.pi, n, endpoint=False)
    r = np.interp(wanted, np.r_[angle-math.tau, angle, angle+math.tau], np.r_[radius, radius, radius])
    return np.c_[centre[0]+r*np.cos(wanted), centre[1]+r*np.sin(wanted)]


def arc_ring(points, n=None):
    """A closed curve through points at even spacing along it, for outlines that are not star-shaped."""
    n = n or SAMPLES[LOD]
    curve = spline(points)
    step = np.hypot(*(np.roll(curve, -1, 0)-curve).T)
    s = np.r_[0, np.cumsum(step)]
    wanted = np.linspace(0, s[-1], n, endpoint=False)
    loop = np.r_[curve, curve[:1]]
    return np.c_[np.interp(wanted, s, loop[:, 0]), np.interp(wanted, s, loop[:, 1])]


def normals(ring):
    tangent = np.roll(ring, -1, 0)-np.roll(ring, 1, 0)
    tangent /= np.maximum(np.hypot(*tangent.T), 1e-6)[:, None]
    return np.c_[tangent[:, 1], -tangent[:, 0]]


def offset(ring, distance):
    """The ring moved outward by distance (an array gives each point its own)."""
    return ring+normals(ring)*np.reshape(np.asarray(distance, float), (-1, 1))


def add_mesh(name, key, colour, verts, faces, smooth=32, uvs=None, stone_uv=True, shade=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata([tuple(map(float, v)) for v in verts], [], faces)
    data.update()
    if smooth:
        data.shade_smooth()
        data.set_sharp_from_angle(angle=math.radians(smooth))
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    shared.finish(obj, key, colour)
    if uvs is not None:
        layer = data.uv_layers.new(name='UVMap')
        for loop in data.loops:
            layer.data[loop.index].uv = uvs[loop.vertex_index]
    elif stone_uv:
        wrap_uv(obj)
    return obj


def wrap_uv(obj, repeat=REPEAT):
    """Each face takes the two axes it faces most, so the stone never stretches on a wall that turns away."""
    data = obj.data
    if data.uv_layers.get('UVMap'):
        data.uv_layers.remove(data.uv_layers['UVMap'])
    layer = data.uv_layers.new(name='UVMap')
    for face in data.polygons:
        n = face.normal
        u, v = (0, 1) if abs(n.z) > .72 else (1, 2) if abs(n.x) > abs(n.y) else (0, 2)
        for li, i in zip(face.loop_indices, face.vertices):
            co = data.vertices[i].co
            layer.data[li].uv = (co[u]/repeat, co[v]/repeat)


def loft(name, rings, key=STONE, colour=STONE_TINT, closed=True, caps=(False, False), smooth=32, flip=False, weld=False, **kw):
    """Quads between rings [(ring, z)], z a number or one height per point. Going up, a counter-clockwise ring faces out.
    weld joins points that meet, so rings closing to a point shade smoothly across it."""
    n = len(rings[0][0])
    verts = []
    for ring, z in rings:
        z = np.broadcast_to(z, (n,))
        verts += [(ring[i, 0], ring[i, 1], z[i]) for i in range(n)]
    faces = []
    for r in range(len(rings)-1):
        for i in range(n if closed else n-1):
            j = (i+1) % n
            a, b, c, d = r*n+i, r*n+j, (r+1)*n+j, (r+1)*n+i
            faces.append((d, c, b, a) if flip else (a, b, c, d))
    if caps[0]:
        faces.append(tuple(range(n-1, -1, -1)))
    if caps[1]:
        faces.append(tuple((len(rings)-1)*n+i for i in range(n)))
    obj = add_mesh(name, key, colour, verts, faces, smooth=smooth, **kw)
    if weld:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-3)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-4)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.shade_smooth()
        obj.data.set_sharp_from_angle(angle=math.radians(smooth))
    return obj


def cap(name, ring, z, key=STONE, colour=STONE_TINT, **kw):
    n = len(ring)
    z = np.broadcast_to(z, (n,))
    return add_mesh(name, key, colour, [(ring[i, 0], ring[i, 1], z[i]) for i in range(n)], [tuple(range(n))], smooth=None, **kw)


def tube(name, path, radius, key=RAIL, colour=RAIL_TINT, sides=4, closed=False, smooth=60):
    """A round section along a 3D path."""
    path = np.asarray(path, float)
    n = len(path)
    verts, faces = [], []
    side = np.array((1., 0, 0))
    for i, p in enumerate(path):
        t = path[(i+1) % n if closed else min(i+1, n-1)]-path[(i-1) % n if closed else max(i-1, 0)]
        t = t/max(np.linalg.norm(t), 1e-6)
        across = np.cross(t, (0, 0, 1))
        # Straight up, the last section's side carries on, and a path turning back keeps its side, so a riser does not twist.
        if np.linalg.norm(across) >= 1e-3:
            side = -across if np.dot(across, side) < 0 and i else across
        side /= np.linalg.norm(side)
        up = np.cross(side, t)
        verts += [tuple(p+radius*(math.cos(k*math.tau/sides)*side+math.sin(k*math.tau/sides)*up)) for k in range(sides)]
    for i in range(n if closed else n-1):
        j = (i+1) % n
        for k in range(sides):
            m = (k+1) % sides
            faces.append((i*sides+k, j*sides+k, j*sides+m, i*sides+m))
    if not closed:
        faces += [tuple(range(sides)), tuple((n-1)*sides+k for k in range(sides-1, -1, -1))]
    return add_mesh(name, key, colour, verts, faces, smooth=smooth, stone_uv=False, uvs=[(v[0]/18, v[2]/18) for v in verts])


def block(name, centre, size, key=FRAME, colour=FRAME_TINT, turn=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre, rotation=(0, 0, turn))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return shared.finish(obj, key, colour)


def carve(obj, cutter_verts, cutter_faces):
    """Cuts a closed shape out of obj and rebuilds its stone UVs."""
    data = bpy.data.meshes.new('cutter')
    data.from_pydata([tuple(map(float, v)) for v in cutter_verts], [], cutter_faces)
    data.update()
    fixed = bmesh.new()
    fixed.from_mesh(data)
    bmesh.ops.recalc_face_normals(fixed, faces=fixed.faces)
    fixed.to_mesh(data)
    fixed.free()
    cutter = bpy.data.objects.new('cutter', data)
    bpy.context.collection.objects.link(cutter)
    solid_mesh = bmesh.new()
    solid_mesh.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(solid_mesh, faces=solid_mesh.faces)
    solid_mesh.to_mesh(obj.data)
    solid_mesh.free()
    before = obj.data.copy()
    for solver in ('EXACT', 'FLOAT'):
        mod = obj.modifiers.new('carve', 'BOOLEAN')
        mod.operation, mod.solver, mod.object = 'DIFFERENCE', solver, cutter
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        if len(obj.data.vertices) >= len(before.vertices)/2:
            break
        print('carve: solver', solver, 'left', len(obj.data.vertices), 'of', len(before.vertices), 'on', obj.name)
        obj.data = before.copy()
    else:
        print('carve: gave up on', obj.name)
        obj.data = before.copy()
    bpy.data.meshes.remove(before)
    bpy.data.objects.remove(cutter)
    bpy.data.meshes.remove(data)
    obj.data.shade_smooth()
    obj.data.set_sharp_from_angle(angle=math.radians(32))
    wrap_uv(obj)


def prism(outline, along, depth):
    """A closed extrusion of a 3D outline along a direction."""
    n = len(outline)
    verts = [tuple(p) for p in outline]+[tuple(np.asarray(p)+np.asarray(along)*depth) for p in outline]
    faces = [tuple(range(n-1, -1, -1)), tuple(range(n, 2*n))]
    faces += [(i, (i+1) % n, (i+1) % n+n, i+n) for i in range(n)]
    return verts, faces


def arch_outline(width, height, centre, bottom=0, sides=16):
    """An arch in the XZ plane: straight legs under a half ellipse that takes the top half of its height."""
    x, y = centre
    spring = bottom+height*.45
    pts = [(x-width/2, y, bottom-2), (x+width/2, y, bottom-2)]
    for k in range(sides+1):
        a = k*math.pi/sides
        pts.append((x+width/2*math.cos(a), y, spring+(height-height*.45)*math.sin(a)))
    return pts


# Planting. Cards are whole plants from the shared cutouts: crossed quads, batched per material and tint.
cards = {}
kept_clear = []


def keep_clear(x, y, half_x, half_y, z, turn=0.0):
    """No plant may stand on this oval at about this height: skylights, plant rooms, pergolas."""
    kept_clear.append((x, y, half_x, half_y, math.radians(turn), z))


def keep_path(points, half, z):
    """No plant may stand on this path or walkway."""
    for x, y in points:
        keep_clear(float(x), float(y), half, half, z)


def blocked(x, y, z, reach):
    """Whether a plant of this reach rooted here would stand on something kept clear."""
    for cx, cy, half_x, half_y, turn, height in kept_clear:
        if abs(z-height) <= 14:
            dx, dy = x-cx, y-cy
            along, across = dx*math.cos(turn)+dy*math.sin(turn), -dx*math.sin(turn)+dy*math.cos(turn)
            if (along/(half_x+reach))**2+(across/(half_y+reach))**2 < 1:
                return True
    return False


def card(key, tint, corners):
    verts, faces, uvs, crown = cards.setdefault((key, tint), ([], [], [], []))
    base = len(verts)
    verts.extend(corners)
    faces.append((base, base+1, base+2, base+3))
    uvs.extend(((0, 0), (1, 0), (1, 1), (0, 1)))
    c = np.array(corners, float)
    foot, head = (c[0]+c[1])/2, (c[2]+c[3])/2
    root = foot-np.array((0, 0, np.linalg.norm(head-foot)*.7))
    for corner in c:
        d = corner-root
        crown.append(tuple(d/max(np.linalg.norm(d), 1e-6)))


def upright(key, tint, x, y, z, width, height, turn, lean=0):
    dx, dy = math.cos(turn)*width/2, math.sin(turn)*width/2
    lx, ly = -math.sin(turn)*lean, math.cos(turn)*lean
    card(key, tint, [(x-dx, y-dy, z), (x+dx, y+dy, z), (x+dx+lx, y+dy+ly, z+height), (x-dx+lx, y-dy+ly, z+height)])


def tilted(key, tint, x, y, z, width, length, turn, tilt):
    """A card rooted at a point, leaning outward along turn by tilt from upright."""
    sx, sy = -math.sin(turn)*width/2, math.cos(turn)*width/2
    ox, oy = math.cos(turn)*math.sin(tilt)*length, math.sin(turn)*math.sin(tilt)*length
    up = math.cos(tilt)*length
    card(key, tint, [(x-sx, y-sy, z), (x+sx, y+sy, z), (x+sx+ox, y+sy+oy, z+up), (x-sx+ox, y-sy+oy, z+up)])


def shrub(x, y, z, size, rng, key=BUSH, tint=None, look=None):
    """A fan of leaning cards round an upright pair: as full from above as from the side. Gives its look (tint, material, turn), which look repeats."""
    if look:
        tint, key, spin = look
    else:
        tint = tint or rng.choice(BUSH_TINTS)
        key = BUSH2 if key == BUSH and rng.random() < .22 else key
        spin = rng.uniform(0, math.tau)
    fans = 5 if LOD == 0 else 3
    for i in range(fans):
        tilted(key, tint, x, y, z-.3, size*1.05, size*.82, spin+i*math.tau/fans, math.radians(rng.uniform(48, 66)))
    upright(key, tint, x, y, z-.3, size*1.0, size*.95, spin, lean=rng.uniform(-.1, .1)*size)
    if LOD == 0:
        upright(key, tint, x, y, z-.3, size*1.0, size*.9, spin+math.pi/2)
    return tint, key, spin


def lump(x, y, z, width, height, tint, rng, sides=7):
    """An opaque green mass that gives a crown body and stands in for plants on far levels."""
    verts, faces = [], []
    spin = rng.uniform(0, math.tau)
    for r, h in ((.72, 0), (1, .4), (.72, .82)):
        for i in range(sides):
            a = spin+i*math.tau/sides
            k = rng.uniform(.88, 1.1)
            verts.append((x+width/2*r*k*math.cos(a), y+width/2*r*k*math.sin(a), z+height*h))
    verts.append((x, y, z+height))
    for ring in range(2):
        for i in range(sides):
            j = (i+1) % sides
            faces.append((ring*sides+i, ring*sides+j, (ring+1)*sides+j, (ring+1)*sides+i))
    for i in range(sides):
        faces.append((2*sides+i, 2*sides+(i+1) % sides, 3*sides))
    add_mesh('planting mass', STONE, tint, verts, faces, smooth=70, stone_uv=False, uvs=[(v[0]/30, v[1]/30) for v in verts])


def tree(x, y, z, height, spread, rng):
    """A small tree on the near level, whose far levels repeat it (far_plants)."""
    if LOD or blocked(x, y, z, spread*.6):
        return
    tint = rng.choice(BUSH_TINTS)
    top = x+rng.uniform(-.5, .5), y+rng.uniform(-.5, .5)
    near_plants.append(('tree', x, y, z, height, spread, tint, top))
    tree_parts(x, y, z, height, spread, tint, top, rng)


def tree_parts(x, y, z, height, spread, tint, top, rng):
    """A tapered trunk, a body and tiers of leafy cards that hide it."""
    trunk = [(x, y, z), (*top, z+height*.6)]
    if LOD < 2:
        tube('tree trunk', trunk, max(.45, height*.03), BARK, (.7, .62, .55), sides=5 if LOD == 0 else 3)
    cx, cy, cz = trunk[1][0], trunk[1][1], z+height*.5
    if LOD == 2:
        lump(cx, cy, z, spread*.9, height*.95, FAR_GREEN, rng, sides=4)
        return
    lump(cx, cy, cz, spread*.62, height*.4, (.56, .66, .34), rng, sides=6 if LOD == 0 else 5)
    tiers = ((.0, 72, 7, .62), (.14, 52, 7, .56), (.26, 24, 5, .46)) if LOD == 0 else ((.05, 58, 5, .7),)
    for rise, tilt, count, length in tiers:
        spin = rng.uniform(0, math.tau)
        for k in range(count):
            tilted(BUSH, tint, cx, cy, cz+height*rise, spread*.72, spread*length, spin+k*math.tau/count, math.radians(tilt))


def hanging(x, y, z, out, length, width, tint):
    """A trailing plant over a rim: a willow card hung outwards."""
    nx, ny = out
    tx, ty = -ny*width/2, nx*width/2
    card(BUSH, tint, [(x+nx*1.2+tx, y+ny*1.2+ty, z-length), (x+nx*1.2-tx, y+ny*1.2-ty, z-length), (x-tx, y-ty, z+.8), (x+tx, y+ty, z+.8)])


def flush_cards():
    if LOD:
        far_plants()
    for (key, tint), (verts, faces, uvs, crown) in cards.items():
        obj = add_mesh('planting', key, tint, verts, faces, smooth=None, uvs=uvs)
        obj.data.normals_split_custom_set_from_vertices(crown)
    cards.clear()


def flower_fan(x, y, z, s, spin):
    for f in range(3):
        tilted(SPIKE, (.70, .78, .66), x, y, z-.2, s*.8, s*.75, spin+f*math.tau/3, math.radians(35))
        tilted(FLOWER, LILAC, x, y, z+s*.25, s*.28, s*.28, spin+.8+f*math.tau/3, math.radians(62))


def plant_band(name, ring, z, indices, rng, spacing=3.4, size=(5, 9), flowers=.06, hang=.0, deep=2.2, rim=4.2, farthest=True):
    """Plants along the ring's points in indices, by arc length: mixed shrubs, lilac flowers and trailing ferns. On the near level only: the far levels repeat them (far_plants)."""
    if LOD:
        return
    out = normals(ring)
    heights = np.broadcast_to(z, (len(ring),))
    step = np.hypot(*(np.roll(ring, -1, 0)-ring).T)
    run = rng.uniform(0, spacing)
    for i in indices:
        run += step[i]
        if run < spacing:
            continue
        run = rng.uniform(-1, .4)*spacing
        x, y = ring[i]
        jitter = rng.uniform(-deep, deep)
        x, y = x+out[i, 0]*jitter, y+out[i, 1]*jitter
        s = rng.uniform(*size)
        z = heights[i]
        if blocked(x, y, z, s*.7):
            continue
        r = rng.random()
        if r < flowers:
            look = rng.uniform(0, math.tau)
            flower_fan(x, y, z, s, look)
        elif r < flowers+.14:
            look = shrub(x, y, z, s, rng, key=SPIKE, tint=(.80, .92, .66))
        else:
            look = shrub(x, y, z, s, rng)
        fern = None
        if rng.random() < hang:
            fern = ring[i, 0]+out[i, 0]*rim, ring[i, 1]+out[i, 1]*rim, z, out[i], rng.uniform(5, 9), rng.uniform(6, 9), (1, 1, .86)
            hanging(*fern)
        near_plants.append(('plant', x, y, z, s, look, fern, farthest))


def far_plants():
    """The far levels' plants are the near level's, in their places: fewer and larger, and those of the farthest level among those of the middle one."""
    rng = random.Random(3)
    middle, farthest = 0.0, 0.0
    for plant in near_plants:
        if plant[0] == 'tree':
            tree_parts(*plant[1:], rng)
            continue
        _, x, y, z, s, look, fern, reaches = plant
        middle += 1/1.7
        if middle < 1:
            continue
        middle -= 1
        farthest += 1.7/9 if reaches else 0
        if LOD == 2:
            if farthest >= 1:
                farthest -= 1
                lump(x, y, z, s*2.1, s, FAR_GREEN, rng, sides=4)
            continue
        s *= 1.25
        if blocked(x, y, z, s*.7):
            continue
        if isinstance(look, float):
            flower_fan(x, y, z, s, look)
        else:
            shrub(x, y, z, s, rng, look=look)
        if fern:
            hanging(*fern)


def rocks(points, z, rng, size=(1.4, 3)):
    for x, y in points:
        s = rng.uniform(*size)
        lump(x, y, z-.3, s*1.5, s, rng.choice(((.62, .58, .50), (.50, .47, .42))), rng, sides=5)


# Shared parts of the terraced buildings.
def slab_edge(name, ring, z, ids=None, rise=3.0, nose=.7, under=5.5, drop=1.8, floor_to=None):
    """A deck's rounded edge along the ring's points in ids: in under the deck, out round the nose, up to a planter's lip, and on to floor_to if given."""
    ids = list(range(len(ring))) if ids is None else list(ids)
    z = np.broadcast_to(z, (len(ring),))[ids]
    at = lambda d: offset(ring, d)[ids]
    closed = len(ids) == len(ring)
    if floor_to is not None:
        lip, back = at(-1.3), floor_to[ids]
        loft(name+' floor', [(lip, z+rise-.25), (back, z+rise-.25)], PAVE, DECK_TINT, closed=closed, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for row in (lip, back) for q in row])
    if LOD == 2:
        rows = [(at(0), z-drop), (at(0), z+rise)]
    elif LOD == 1:
        rows = [(at(-under), z-drop), (at(nose), z+.2), (at(-.1), z+rise), (at(-1.3), z+rise-.2)]
    else:
        rows = [(at(-under), z-drop), (at(-.6), z-drop+.3), (at(nose), z+.2), (at(nose*.6), z+rise-.5), (at(-.1), z+rise), (at(-1.3), z+rise-.2)]
    obj = loft(name, rows, closed=closed)
    if not closed and LOD < 2:
        # Each end is one upright polygon through the rows' last points, facing along the run.
        for k, sign in ((0, -1), (len(ids)-1, 1)):
            points = [(row[k, 0], row[k, 1], float(h[k])) for row, h in ((r, np.broadcast_to(q, (len(ids),))) for r, q in rows)]
            along = (ring[ids[min(k+1, len(ids)-1)]]-ring[ids[max(k-1, 0)]])*sign
            a, b, c = (np.array(q) for q in points[:3])
            facing = np.cross(b-a, c-a)
            order = points if facing[0]*along[0]+facing[1]*along[1] > 0 else points[::-1]
            add_mesh(name+' end', STONE, STONE_TINT, order, [tuple(range(len(order)))], smooth=None)
    return obj


def strips(name, key, colour, placed, width):
    """Upright flat strips in one mesh: placed holds each one's (x, y, normal x, normal y, bottom, top)."""
    verts, faces = [], []
    for x, y, nx, ny, bottom, top in placed:
        tx, ty = -ny*width/2, nx*width/2
        base = len(verts)
        verts += [(x-tx, y-ty, bottom), (x+tx, y+ty, bottom), (x+tx, y+ty, top), (x-tx, y-ty, top)]
        faces.append((base, base+1, base+2, base+3))
    return add_mesh(name, key, colour, verts, faces, smooth=None, stone_uv=False, uvs=[(v[0]/18, v[2]/18) for v in verts]) if verts else None


def room_strip(name, inside, low, high, t0, t1, lit):
    """A lit room on a strip of glass, between two shares of the strip's length, following its points."""
    along = np.concatenate(((0,), np.cumsum(np.hypot(*(inside[1:]-inside[:-1]).T))))
    a, b = t0*along[-1], t1*along[-1]
    at = np.concatenate(((a,), along[(along > a+1e-6) & (along < b-1e-6)], (b,)))
    points = np.column_stack((np.interp(at, along, inside[:, 0]), np.interp(at, along, inside[:, 1])))
    foot, head = np.interp(at, along, low)+.1, np.interp(at, along, high)-.3
    room = loft(name+' room', [(points, foot), (points, head)], GLASS, (1, .93, .74) if lit else (.92, .88, .72), closed=False, smooth=40, stone_uv=False,
                uvs=[(float(q[0])/18, float(h)/18) for row in (foot, head) for q, h in zip(points, row)])
    shared.emissive(room, NIGHT, night=True)


def glazing(name, ring, z0, z1, indices, rng, bay=4.6, warm=.4, lit=False, line=False, closed=False):
    """A storey of glass following the ring's points in indices, with mullions, a head, a line at mid-height and lit rooms; the far levels light the near level's rooms."""
    ids = list(indices)
    part = ring[ids]
    low, high = np.broadcast_to(z0, (len(ring),))[ids], np.broadcast_to(z1, (len(ring),))[ids]
    loft(name, [(part, low), (part, high)], GLASS, GLASS_TINT, closed=closed, smooth=40, stone_uv=False,
         uvs=[(p[0]/18, h/18) for row in (low, high) for p, h in zip(part, row)])
    inside = offset(part, .03)
    if LOD:
        strips_seen[name] = strips_seen.get(name, -1)+1
        for t0, t1 in near_rooms[name][strips_seen[name]]:
            room_strip(name, inside, low, high, t0, t1, lit)
        return
    framed = slice(2, -2) if line else slice(None)
    tube(name+' head', [(p[0], p[1], h-.2) for p, h in zip(part, high)][framed], .35, FRAME, FRAME_TINT, sides=3)
    if line:
        tube(name+' floor line', [(p[0], p[1], (a+b)/2) for p, a, b in zip(offset(part, .05), low, high)][framed], .2, FRAME, FRAME_TINT, sides=3)
    run = 0
    steps = np.hypot(*(part[1:]-part[:-1]).T)
    start = 0
    facing = normals(part)
    along = np.concatenate(((0,), np.cumsum(np.hypot(*(inside[1:]-inside[:-1]).T))))
    rooms = near_rooms.setdefault(name, [])
    rooms.append([])
    if not closed and len(part) > 2:
        facing[0], facing[-1] = facing[1], facing[-2]
    mullions, lights = [], []
    for k in range(1, len(part)):
        run += steps[k-1]
        if run >= bay:
            run = 0
            mullions.append((part[k, 0]+facing[k, 0]*.12, part[k, 1]+facing[k, 1]*.12, facing[k, 0], facing[k, 1], low[k], high[k]))
            if rng.random() < warm:
                share = (along[start]/along[-1], along[k]/along[-1])
                rooms[-1].append(share)
                room_strip(name, inside, low, high, *share, lit)
                if rng.random() < .5:
                    mid = (start+k)//2
                    lights.append((inside[mid, 0]+facing[mid, 0]*.1, inside[mid, 1]+facing[mid, 1]*.1, facing[mid, 0], facing[mid, 1], high[mid]-1.8, high[mid]-1.4))
            start = k
    strips(name+' mullion', FRAME, FRAME_TINT, mullions, .45)
    glow = strips(name+' ceiling light', FLAT, (.9, .75, .5), lights, 1.6)
    if glow:
        shared.emissive(glow, (1, .82, .55))


def terrace(name, ring, above, height, next_height, arc, ids, rng, phase=0.0, hang=.1, warm=.4, lit=False, line=False, plants=3.6, bay=4.6, planted=None):
    """A planted deck along the ring's points in arc: rounded edge, a planter of varying width, a walkway to the glass, plants, a rail and the storey's glass under the next deck."""
    slab_edge(name+' edge', ring, height, arc)
    closed = len(arc) == len(ring)
    glass_foot = offset(above, -3.2)
    depth = np.maximum(np.hypot(*(ring-glass_foot).T), .1)
    inward = lambda d: ring+(glass_foot-ring)*np.minimum(np.asarray(d, float)/depth, 1)[:, None]
    wave = .5+.5*np.sin(np.linspace(0, math.tau*5, len(ring), endpoint=False)+phase)
    width = np.maximum(depth-2.5-2*wave, 4.5)
    planter = (inward(width) if LOD < 2 else glass_foot)[arc]
    lip = inward(np.full(len(ring), 1.3))[arc]
    everywhere = np.broadcast_to(height, (len(ring),))
    lifted = everywhere[arc]
    flat_uv = lambda *rings: [(float(q[0])/30, float(q[1])/30) for row in rings for q in row]
    loft(name+' planter', [(lip, lifted+2.8), (planter, lifted+2.8)], TURF, TURF_TINT, closed=closed, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for row in (lip, planter) for q in row])
    if LOD == 0:
        loft(name+' planter wall', [(planter, lifted+.3), (planter, lifted+2.8)], closed=closed, flip=True)
    room = [i for i in arc if depth[i] > width[i]+.3]
    if len(room) > 1 and LOD < 2:
        walk_in, walk_out = inward(width)[room], glass_foot[room]
        loft(name+' walkway', [(walk_in, everywhere[room]+.3), (walk_out, everywhere[room]+.3)], PAVE, DECK_TINT, closed=closed and len(room) == len(ring), stone_uv=False, uvs=flat_uv(walk_in, walk_out))
    planted = ids if planted is None else planted
    plant_band(name+' plants', inward(np.full(len(ring), 2.9)), everywhere+2.6, [i for i in planted if depth[i] > 6], rng, spacing=plants, size=(4, 7), hang=hang, deep=.8)
    plant_band(name+' plants inner', inward(np.minimum(width-1.6, depth-5)), everywhere+2.6, [i for i in planted if width[i] > 6.6 and depth[i] > 9], rng, spacing=plants*1.3, size=(4.5, 7.5), deep=.8, farthest=False)
    plant_band(name+' plants middle', inward(width*.5), everywhere+2.6, [i for i in planted if width[i] > 11], rng, spacing=plants*1.3, size=(5, 8), flowers=.1, deep=1.2, farthest=False)
    glazing(name+' storey', offset(above, -3.4), everywhere+.3, np.broadcast_to(next_height, (len(ring),))-1.9, ids, rng, warm=warm, lit=lit, line=line, closed=closed, bay=bay)
    rail(name+' rail', inward(width), everywhere+2.8, ids)


def plinth(ring):
    """The paved ground a building stands on, with its kerb."""
    if LOD == 0:
        loft('plinth kerb', [(offset(ring, .3), 0), (offset(ring, .3), .9), (offset(ring, -.5), 1.4)], PAVE, PAVE_TINT)
        ring = offset(ring, -.5)
    else:
        loft('plinth kerb', [(ring, 0), (ring, 1.4)], PAVE, PAVE_TINT)
    cap('plinth paving', ring, 1.4, PAVE, PAVE_TINT)


def rail(name, ring, z, indices, height=3.3, posts=13.0):
    ids = list(indices)
    part = ring[ids]
    heights = np.broadcast_to(z, (len(ring),))[ids]
    if LOD:
        return
    tube(name, [(p[0], p[1], h+height) for p, h in zip(part, heights)], .16, sides=3)
    run = 0
    steps = np.hypot(*(part[1:]-part[:-1]).T)
    facing = normals(part)
    placed = []
    for k in range(1, len(part)):
        run += steps[k-1]
        if run >= posts:
            run = 0
            placed.append((part[k, 0], part[k, 1], facing[k, 0], facing[k, 1], heights[k], heights[k]+height))
    strips(name+' post', RAIL, RAIL_TINT, placed, .25)


def louvre(name, wall, centre, normal, width, height, slat=3.0):
    """An oval of level slats laid on a wall object: a dark back, curved slats standing off it and a round frame."""
    n = Vector(normal).normalized()
    side = Vector((0, 0, 1)).cross(n).normalized()
    up = n.cross(side).normalized()
    c = Vector(centre)
    bpy.context.view_layer.update()
    tree = BVHTree.FromObject(wall, bpy.context.evaluated_depsgraph_get())

    def on_wall(x, y, lift=0.0):
        origin = c+side*x+up*y+n*60
        hit, _, _, _ = tree.ray_cast(origin, -n, 120)
        return (hit if hit is not None else c+side*x+up*y)+n*lift
    ring = 44 if LOD == 0 else 16
    angles = np.linspace(0, math.tau, ring, endpoint=False)
    edge = [(width/2*math.cos(a), height/2*math.sin(a)) for a in angles]
    rows, across = {0: (26, 12), 1: (10, 5), 2: (8, 4)}[LOD]
    back = []
    for r in range(rows+1):
        y = -height/2+height*r/rows
        half = width/2*math.sqrt(max(0, 1-(2*y/height)**2))
        back += [tuple(on_wall(-half+2*half*i/across, y, 1.0 if LOD == 2 else .25)) for i in range(across+1)]
    line = across+1
    faces = [(r*line+i, r*line+i+1, (r+1)*line+i+1, (r+1)*line+i) for r in range(rows) for i in range(across)]
    add_mesh(name+' back', FLAT, LOUVRE_BACK, back, faces, smooth=None, stone_uv=False, uvs=[(0, 0)]*len(back))
    count = int(height/slat)
    steps = {0: 8, 1: 3, 2: 2}[LOD]
    above_back = .75 if LOD == 2 else 0  # The farthest level's back stands off its coarse wall.
    for k in range(1, count):
        y = -height/2+k*height/count
        half = width/2*math.sqrt(max(0, 1-(2*y/height)**2))
        if half < 2:
            continue
        verts, faces = [], []
        for i in range(steps+1):
            x = -half+2*half*i/steps
            verts.append(tuple(on_wall(x, y-.25, 1.5+above_back)))
            verts.append(tuple(on_wall(x, y+.25, .9+above_back)))
        for i in range(steps):
            faces.append((2*i, 2*i+2, 2*i+3, 2*i+1))
        add_mesh(name+' slat', STONE, SLAT, verts, faces, smooth=None)
    if LOD < 2:
        tube(name+' frame', [tuple(on_wall(x*1.02, y*1.02, .6)) for x, y in edge], 1.0, STONE, STONE_TINT, sides=6 if LOD == 0 else 4, closed=True, smooth=70)


def skylight(name, x, y, z, rx, ry, rise=None, ribs=12, rings=4, slope=0.0, turn=0.0):
    """A shallow glass dome in a stone ring, with ribs and hoops, on a floor rising northward by slope, its long axis turned by turn degrees."""
    keep_clear(x, y, rx+2, ry+2, z, turn)
    ct, st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
    swing = lambda a, b: (x+a*ct-b*st, y+a*st+b*ct)
    rise = rise or min(rx, ry)*.38
    sides = {0: 40, 1: 16, 2: 12}[LOD]
    rings = rings if LOD < 2 else 2
    if LOD:
        rx, ry, rise = rx/math.cos(math.pi/sides), ry/math.cos(math.pi/sides), rise*(1.03 if LOD == 1 else 1.16)
    levels = [math.sin(k/(rings+1)*math.pi/2) for k in range(rings+1)]
    circle = lambda s: np.array([swing(rx*s*math.cos(a), ry*s*math.sin(a)) for a in np.linspace(0, math.tau, sides, endpoint=False)])
    floor = lambda ring: z+slope*(ring[:, 1]-y)
    rows = [(circle(math.cos(k*math.pi/2/(rings+1))), rise*l) for k, l in enumerate(levels)]
    rows = [(ring, floor(ring)+lift) for ring, lift in rows]
    obj = loft(name, rows, DOME_GLASS, (1, .97, .88), caps=(False, True), smooth=60, stone_uv=False,
               uvs=[(float(p[0])/18, float(p[1])/18) for row, _ in rows for p in row])
    shared.emissive(obj, NIGHT_GLASS, night=True)
    kerb = (offset(circle(1), 2.0), offset(circle(1), 2.0), offset(circle(1), .4), circle(1))
    lifts = (-.6 if LOD == 0 else -2.5, .5, 1.0, .2)
    loft(name+' kerb', [(ring, floor(ring)+lift) for ring, lift in zip(kerb, lifts)])
    if LOD:
        return
    for k in range(ribs):
        a = k*math.tau/ribs
        points = [(*swing(rx*math.cos(t*math.pi/2)*math.cos(a), ry*math.cos(t*math.pi/2)*math.sin(a)), rise*math.sin(t*math.pi/2)+.05) for t in np.linspace(0, 1, 6)]
        tube(name+' rib', [(px, py, lift+z+slope*(py-y)) for px, py, lift in points], .16, FRAME, FRAME_TINT, sides=3)
    for k, l in enumerate(levels[1:-1], 1):
        ring = circle(math.cos(k*math.pi/2/(rings+1)))
        tube(name+' hoop', [(px, py, z+slope*(py-y)+rise*l+.05) for px, py in ring], .14, FRAME, FRAME_TINT, sides=3, closed=True)


def indices_between(ring, centre, start, end):
    """The ring's points from angle start counter-clockwise to end (degrees round centre), in order."""
    angles = (np.degrees(np.arctan2(ring[:, 1]-centre[1], ring[:, 0]-centre[0]))-start) % 360
    span = (end-start) % 360
    chosen = sorted((i for i in range(len(ring)) if angles[i] <= span), key=lambda i: angles[i])
    rest = [i for i in range(len(ring)) if angles[i] > span]
    if LOD and len(rest) > 1 and chosen:
        # A coarser ring's points miss the ends: take the nearer point at each, or a span's end moves further at a level switch.
        before, after = max(rest, key=lambda i: angles[i]), min(rest, key=lambda i: angles[i])
        if 360-angles[before] < angles[chosen[0]]:
            chosen.insert(0, before)
        if angles[after]-span < span-angles[chosen[-1]]:
            chosen.append(after)
    return chosen


def volume_prism(name, ring, z0, z1):
    n = len(ring)
    verts = [(p[0], p[1], z0) for p in ring]+[(p[0], p[1], z1) for p in ring]
    faces = [tuple(range(n-1, -1, -1)), tuple(range(n, 2*n))]+[(i, (i+1) % n, (i+1) % n+n, i+n) for i in range(n)]
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return shared.finish(obj, FLAT, (.3, .8, .7), helper=True)


def door_pair(x, y, z=0):
    """Two 1.4 x 2.6 m glass leaves in a dark frame, on a wall facing -Y."""
    block('door frame', (x, y, z+4.05), (9.2, .5, 8.1))
    for side in (-1, 1):
        leaf = block('door leaf', (x+side*2.2, y-.2, z+3.85), (4.2, .3, 7.7), GLASS, LOBBY)
        shared.emissive(leaf, NIGHT, night=True)
        block('door pull', (x+side*.55, y-.45, z+3.8), (.25, .2, 2.4), RAIL, RAIL_TINT)


# Walls with openings. A boolean on a curved wall is fragile; cut flat in (angle, height), the outlines stay smooth and the wall stays whole.
def outline(points):
    """A smooth closed curve through (angle in degrees, height) points, at this level's detail."""
    return spline(np.array(points, float), dense={0: 5, 1: 3, 2: 2}[LOD])


def wrapped_skin(name, surface, top, openings, reach=math.pi, depth=4.0, key=STONE, colour=STONE_TINT, lip=.9, keep_back=False, columns=None):
    """Stone over the angles -reach..reach from the ground up to top(angles), with the openings cut through it.

    surface(angles, heights) gives each point on the wall and its outward direction, both N x 3. A lip runs round each opening.
    columns, if given, are the sheet's upright lines (angles from -reach to reach), for walls that turn tighter in places.
    """
    if columns is None:
        across = max(6, int({0: 96, 1: 36, 2: 16}[LOD]*reach/math.pi))
        us = np.linspace(-reach, reach, across+1)
    else:
        us = np.asarray(columns, float)
        across = len(us)-1
    scale = 60  # Units per radian in the flat sheet: only proportions matter.
    tops = np.asarray(top(us), float)
    rows = max(2, int(tops.max()/{0: 7, 1: 24, 2: 48}[LOD]))
    shares = [j/rows for j in range(rows+1)]
    if LOD == 1 and tops.max() > 40:
        shares = sorted({*shares, 5/float(tops.max()), 12/float(tops.max())})
        rows = len(shares)-1
    verts = []
    for share in shares:
        verts += [(u*scale, 0, t*share) for u, t in zip(us, tops)]
    verts += [(x, depth, z) for x, _, z in verts]
    line, count = across+1, (across+1)*(rows+1)
    faces = []
    for j in range(rows):
        for i in range(across):
            a, b, c, d = j*line+i, j*line+i+1, (j+1)*line+i+1, (j+1)*line+i
            faces.append((a, b, c, d))
            faces.append((count+d, count+c, count+b, count+a))
    for i in range(across):
        faces.append((count+i, count+i+1, i+1, i))
        t = rows*line
        faces.append((t+i, t+i+1, count+t+i+1, count+t+i))
    for j in range(rows):
        faces.append((count+j*line, j*line, (j+1)*line, count+(j+1)*line))
        e = across
        faces.append((j*line+e, count+j*line+e, count+(j+1)*line+e, (j+1)*line+e))
    obj = add_mesh(name, key, colour, verts, faces, smooth=None, stone_uv=False, uvs=[(0, 0)]*len(verts))
    for points in openings:
        curve = outline(points)
        carve(obj, *prism([(math.radians(a)*scale, -2, z) for a, z in curve], (0, 1, 0), depth+4))
    data = obj.data
    co = np.array([v.co for v in data.vertices])
    if not keep_back:
        # The sheet's back is not seen.
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(v.co.y > depth-.01 for v in f.verts)], context='FACES')
        bm.to_mesh(data)
        bm.free()
    co = np.array([v.co for v in data.vertices])
    at, out = surface(co[:, 0]/scale, co[:, 2])
    placed = at-out*co[:, 1:2]
    data.vertices.foreach_set('co', placed.ravel())
    data.update()
    data.shade_smooth()
    data.set_sharp_from_angle(angle=math.radians(40 if LOD == 0 else 72))
    wrap_uv(obj)
    if LOD == 0:
        # The lip is sunk into the wall and moved off the opening's edge: a corner hovering over the wall, or lying on the
        # opening's cut face, shows as a dotted line at grazing angles. Round an opening cut from below the ground it runs
        # straight down into the ground, where its ends are hidden.
        for points in openings:
            curve = outline(points)
            keep = curve[curve[:, 1] > .5]
            closed = len(keep) == len(curve)
            if not closed:
                keep = np.r_[[(keep[0, 0], -1.5)], keep, [(keep[-1, 0], -1.5)]]
            where, facing = surface(np.radians(keep[:, 0]), keep[:, 1])
            away = np.cross(np.roll(where, -1, 0)-np.roll(where, 1, 0) if closed else np.gradient(where, axis=0), facing)
            away /= np.linalg.norm(away, axis=1)[:, None]
            middle = surface(np.radians(curve[:, 0].mean(keepdims=True)), curve[:, 1].mean(keepdims=True))[0]
            away *= np.sign(np.sum((where-middle)*away))  # Away from the opening, into the stone.
            tube(name+' lip', where+(away-facing)*lip/8, lip, key, colour, sides=4, closed=closed, smooth=70)
    return obj


def oval_surface(cx, cy, a, b, flare=0.0):
    """A tapering oval wall, its angle 0 at the south and growing towards the east. a and b give the half widths at each height."""
    def surface(angles, heights):
        grow = flare*np.exp(-heights/7)
        ax, by = a(heights)+grow, b(heights)+grow
        at = np.c_[cx+ax*np.sin(angles), cy-by*np.cos(angles), heights]
        out = np.c_[np.sin(angles)/ax, -np.cos(angles)/by, np.zeros(len(angles))]
        return at, out/np.linalg.norm(out, axis=1)[:, None]
    return surface


def ring_on(surface, angles, heights, inset=0.0):
    """Plan points on the wall at these angles and heights, moved inward by inset."""
    at, out = surface(angles, np.broadcast_to(heights, angles.shape).astype(float))
    return (at-out*np.reshape(inset, (-1, 1)))[:, :2]


def fins(name, wall, angles, openings, heights, back=2.6, front=1.9, half=.15, colour=FIN, pitch=4.5):
    """Pale fins behind a wrapped skin, only over the angles where an opening shows them: thin over glass, deep as a louvre."""
    curves = [outline(points) for points in openings]
    bolder = float(heights[1]-heights[0])/pitch
    half, back = half*bolder, front+(back-front)*bolder
    for z in heights:
        shown = np.zeros(len(angles), bool)
        for curve in curves:
            x, y = np.radians(curve[:, 0]), curve[:, 1]
            x2, y2 = np.roll(x, -1), np.roll(y, -1)
            crossing = (y > z) != (y2 > z)
            if crossing.any():
                at = x[crossing]+(z-y[crossing])*(x2[crossing]-x[crossing])/(y2[crossing]-y[crossing])
                shown |= (np.count_nonzero(at[:, None] > angles, axis=0) % 2) == 1
        ids = np.flatnonzero(shown | np.roll(shown, 1) | np.roll(shown, -1))
        if len(ids) == 0:
            continue
        for run in np.split(ids, np.flatnonzero(np.diff(ids) > 1)+1):
            if len(run) > 1:
                loft(name, [(ring_on(wall, angles[run], z, inset=back), z+half), (ring_on(wall, angles[run], z, inset=front), z-half)], STONE, colour, closed=False, smooth=None, flip=True)


def office_tower(rng):
    """Sheet 'Office Tower', 2 x 2 hexes, 12 levels: an oval stone skin with almond openings over a louvred glass core, a sky garden in a notch.

    The sheet's top view is longer than its other views; the plan takes the length the four hexes need.
    """
    cx, cy = 31, -54
    a = lambda z: 57-8*(np.asarray(z, float)/216)**2
    b = lambda z: 86-12*(np.asarray(z, float)/216)**2
    wall = oval_surface(cx, cy, a, b, flare=5)
    inside = oval_surface(cx, cy, a, b)
    n = SAMPLES[LOD]
    around = np.linspace(-math.pi, math.pi, n, endpoint=False)
    plaza = ring_on(wall, around, 1.4, inset=-16)
    plinth(plaza)
    rim = lambda u: 214-9*np.cos(u)
    plane = lambda y: 210.5+.122*(y-cy)
    door = [(-37, -2), (-37, 20), (-25, 36), (0, 45), (25, 36), (37, 20), (37, -2)]
    lower = [(-32, 52), (-22, 66), (10, 68), (50, 66), (54, 54), (40, 50), (5, 52), (-25, 48)]
    notch = [(-32, 76), (-30, 107), (10, 104), (50, 101), (84, 103), (86, 76), (25, 74)]
    upper = [(-28, 120), (-24, 178), (0, 198), (40, 203), (76, 182), (84, 124), (50, 112), (10, 116)]
    west = [(-55, 30), (-72, 90), (-74, 140), (-66, 192), (-44, 178), (-36, 125), (-37, 75), (-42, 42)]
    east = [(158, 15), (125, 34), (94, 70), (90, 100), (94, 150), (120, 182), (152, 165), (170, 115), (170, 55)]
    low = [(55, 30), (60, 70), (72, 74), (76, 36)]
    rear = [(-150, 30), (-165, 100), (-150, 170), (-125, 150), (-112, 90), (-125, 40)]
    glazed = [lower, upper, west, east, low, rear]
    wrapped_skin('tower skin', wall, rim, [door, notch]+glazed)
    # The glass core behind the skin, drawn in at the door and at the sky garden.
    degrees = np.degrees(around)
    span = np.clip(1-np.abs((degrees-25)/62), 0, 1)
    pull = 4+20*np.minimum(span*3.5, 1)
    entry = 5.5
    core = [(ring_on(inside, around, 1.4, inset=entry), 1.4), (ring_on(inside, around, 47, inset=entry), 47), (ring_on(inside, around, 47, inset=4), 47)]
    for z, inset in ((71.5, 4), (71.5, pull), (108, pull), (108, 4)):
        core.append((ring_on(inside, around, z, inset=inset), z))
    near_top = rim(around)-3
    core.append((ring_on(inside, around, near_top, inset=4), near_top))
    obj = loft('tower core', core, GLASS, GLASS_TINT, smooth=40, stone_uv=False,
               uvs=[(float(q[0])/18, float(h)/18) for ring, z in core for q, h in zip(ring, np.broadcast_to(z, (n,)))])
    shared.emissive(obj, NIGHT_GLASS, night=True)
    if LOD < 2:
        fins('core fin', inside, around, glazed, np.arange(10.0, 203, 4.5))
    # The lobby behind the door.
    wide = np.radians(np.linspace(-37, 37, 18 if LOD == 0 else 6))
    pane = ring_on(inside, wide, 20, inset=4.6)
    lobby = loft('lobby glass', [(pane, 1.4), (pane, 46)], GLASS, LOBBY, closed=False, smooth=40, stone_uv=False,
                 uvs=[(float(q[0])/18, z/18) for z in (1.4, 46) for q in pane])
    shared.emissive(lobby, NIGHT, night=True)
    if LOD == 0:
        where = np.radians(np.linspace(-33, 33, 15))
        q = ring_on(inside, where, 20, inset=4.45)
        out = normals(q)
        out[0], out[-1] = out[1], out[-2]
        strips('lobby mullion', FRAME, FRAME_TINT, [(a[0], a[1], b[0], b[1], 1.4, 46) for a, b in zip(q, out)], .4)
        tube('lobby transom', [(a[0], a[1], 24) for a in q], .25, FRAME, FRAME_TINT, sides=3)
        door_pair(cx, float(ring_on(inside, np.array([0.]), 10, inset=4.3)[0, 1]), 1.4)
    # The sky garden: its deck, its ceiling, a nose that stands proud and plants on it.
    deck_ids = [i for i in range(n) if -27 <= degrees[i] <= 81]
    edge = ring_on(inside, around, 72, inset=-3)
    inner = ring_on(inside, around, 72, inset=pull)
    loft('sky deck', [(edge[deck_ids], 72.2), (inner[deck_ids], 72.2)], PAVE, DECK_TINT, closed=False, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for ring in (edge[deck_ids], inner[deck_ids]) for q in ring])
    overhead = ring_on(inside, around, 108, inset=1)
    loft('sky ceiling', [(inner[deck_ids], 107.8), (overhead[deck_ids], 107.8)], closed=False)
    slab_edge('sky edge', edge, 72, deck_ids, rise=2.4, nose=.8, under=4)
    rail('sky rail', offset(edge, -.8), 74.4, deck_ids)
    mid = ring_on(inside, around, 72, inset=pull*.55)
    plant_band('sky plants', mid, 72.4, deck_ids, rng, spacing=3, size=(6, 10.5), deep=3)
    for u in (-5, 25, 55):
        q = ring_on(inside, np.radians(np.array([float(u)])), 72, inset=14)[0]
        tree(q[0], q[1], 72.4, rng.uniform(24, 29), rng.uniform(16, 21), rng)
    # The roof: one plane rising to the north inside a low rim, a long skylight, planted crescents and a plant room.
    tops = rim(around)
    at_inset = lambda inset: ring_on(wall, around, tops, inset=inset)
    rim_rows = [(at_inset(inset), tops+lift) for inset, lift in (((0, -2), (-.4, 0), (.8, 1.2), (3, 1.4), (6, .4), (7, -.8)) if LOD == 0 else ((0, -2), (.8, 1.2), (6, .4), (7, -.8)))]
    floor_ring = at_inset(7.5)
    rim_rows.append((floor_ring, plane(floor_ring[:, 1])))
    loft('tower rim', rim_rows)
    cap('roof paving', floor_ring, plane(floor_ring[:, 1]), PAVE, PAVE_TINT)
    skylight('roof skylight', cx, cy, plane(cy)+.2, 15, 28, slope=.122)
    keep_clear(cx, cy+52, 17, 9, float(plane(cy+52)))
    outer, inmost, mid = at_inset(8), at_inset(22), at_inset(15)
    for ids in ([i for i in range(n) if -155 <= degrees[i] <= -35], [i for i in range(n) if 25 <= degrees[i] <= 120]):
        loft('roof bed', [(outer[ids], plane(outer[ids, 1])+.5), (inmost[ids], plane(inmost[ids, 1])+.5)], TURF, TURF_TINT, closed=False, stone_uv=False,
             uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for ring in (outer[ids], inmost[ids]) for q in ring])
        plant_band('roof plants', mid, plane(mid[:, 1])+.5, ids, rng, spacing=3.2, size=(6, 10), flowers=.1, deep=4.5)
    for u in (-90, -130, 60, 95):
        k = int(np.argmin(np.abs(degrees-u)))
        tree(mid[k, 0], mid[k, 1], float(plane(mid[k, 1]))+.5, rng.uniform(13, 17), rng.uniform(12, 16), rng)
    room_z = float(plane(cy+52))
    block('roof plant room', (cx, cy+52, room_z+4), (34, 18, 9), STONE, STONE_SHADE)
    block('roof plant vents', (cx, cy+52, room_z+8.8), (30, 15, .8), 'structures/common/grille', (.66, .66, .64))
    # Beds round the foot, open at the door.
    foot = ring_on(wall, around, 1.4, inset=-6)
    ids = [i for i in range(n) if abs(degrees[i]) > 42]
    plant_band('ground plants', foot, 1.4, ids, rng, spacing=3, size=(5, 9), deep=2.4)
    if LOD == 0:
        rocks([foot[i] for i in ids[::9]], 1.4, rng)
    flush_cards()
    return inside, around, entry, pull


def office_volumes(inside, around, entry, pull):
    """The game draws a floor at every level inside the volumes: they stay behind the glass, the lobby and the notch. The thin top gives the whole roof its hexes."""
    volume_prism('building_volume lobby', ring_on(inside, around, 18, inset=entry+1), 0, 36)
    volume_prism('building_volume low', ring_on(inside, around, 72, inset=5), 36, 72)
    volume_prism('building_volume sky garden', ring_on(inside, around, 72, inset=pull+1), 72, 108)
    volume_prism('building_volume high', ring_on(inside, around, 216, inset=5), 108, 215)
    volume_prism('building_volume roof', ring_on(inside, around, 60), 215, 216)


def ring_surface(low, high, z0, z1, reach, closed=False, profile=lambda t: t, away_from=None, along=None, facing=None):
    """A wall between two plan rings of equal length, for wrapped_skin: angle -reach..reach runs along them, their right side outward (or away from a point).
    along gives each point's angle where they are not evenly spaced; facing gives each point's outward direction."""
    count = len(low)
    plain = normals(low) if facing is None else facing
    if not closed and facing is None:
        plain[0], plain[-1] = plain[1], plain[-2]

    def surface(angles, heights):
        grid = np.arange(count)
        f = np.interp(angles, along, grid) if along is not None else (np.asarray(angles)+reach)/(2*reach)*(count if closed else count-1)
        pick = lambda ring, axis: np.interp(f, grid, ring[:, axis], period=count) if closed else np.interp(f, grid, ring[:, axis])
        t = profile(np.clip((np.asarray(heights)-z0)/(z1-z0), 0, 1))[:, None]
        a, b = np.c_[pick(low, 0), pick(low, 1)], np.c_[pick(high, 0), pick(high, 1)]
        at = a+(b-a)*t
        out = at-away_from if away_from is not None else np.c_[pick(plain, 0), pick(plain, 1)]
        out /= np.maximum(np.hypot(*out.T), 1e-6)[:, None]
        return np.c_[at, heights], np.c_[out, np.zeros(len(out))]
    return surface


def tilted_oval(u, z, wide, tall, lean=0.0, count=10):
    """An oval opening's points: wide in degrees, tall in units, rising by lean towards growing angle."""
    return [(u+wide*math.cos(a), z+tall*math.sin(a)+lean*math.cos(a)) for a in np.linspace(0, math.tau, count, endpoint=False)]


def pill(u0, u1, z0, z1):
    """A long rounded opening's points."""
    mid, h = (z0+z1)/2, (z1-z0)/2
    r = min(h*1.1, (u1-u0)/4)
    bend = lambda u, a0, a1: [(u+r*math.cos(a), mid+h*math.sin(a)) for a in np.radians(np.linspace(a0, a1, 5 if LOD == 0 else 3))]
    straight = lambda z, a, b: [(a+(b-a)*t, z) for t in ((.25, .5, .75) if LOD == 0 else (.5,))]
    return bend(u1-r, -90, 90)+straight(z1, u1-r, u0+r)+bend(u0+r, 90, 270)+straight(z0, u0+r, u1-r)


def line_through(points, dense=8):
    """A smooth open curve through points, as an array."""
    p = np.array(points, float)
    knots = np.r_[p[:1], p, p[-1:]]
    out = []
    for i in range(1, len(knots)-2):
        a, b, c, d = knots[i-1], knots[i], knots[i+1], knots[i+2]
        for t in np.linspace(0, 1, dense, endpoint=False):
            out.append(.5*(2*b+(c-a)*t+(2*a-5*b+4*c-d)*t*t+(3*b-a-3*c+d)*t*t*t))
    out.append(p[-1])
    return np.array(out)


def round_bench(x, y, z, r, a0, a1):
    if LOD == 0:
        tube('bench', [(x+r*math.cos(math.radians(a)), y+r*math.sin(math.radians(a)), z+1.5) for a in np.linspace(a0, a1, 8)], 1.4, STONE, STONE_TINT, sides=6)


def round_bed(name, x, y, z, radius, rng, tree_height=0.0, spread=0.0):
    """A low round planter in the paving, with a tree."""
    count = {0: 32, 1: 16, 2: 10}[LOD]
    ring = np.array([(x+radius*math.cos(a), y+radius*math.sin(a)) for a in np.linspace(0, math.tau, count, endpoint=False)])
    loft(name+' kerb', [(ring, z), (ring, z+2.4), (offset(ring, -1), z+2.6)])
    soil = offset(ring, -1)
    cap(name+' soil', soil, z+2.6, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in soil])
    plant_band(name+' plants', offset(ring, -radius*.3), z+2.4, range(count), rng, spacing=3, size=(3.5, 6), flowers=.15, deep=radius*.2)
    if tree_height:
        tree(x, y, z+2.4, tree_height, spread, rng)


def market_pavilion(rng):
    """Sheet 'Market Pavilion', 3 x 3 hexes, 3 levels: a horseshoe round an open courtyard, shops under a balcony inside, big louvred ovals outside, three oval roof lights."""
    tp = lambda points: [((x-372)*.40, (715-y)*.40+12) for x, y in points]
    hub = np.array(tp([(372, 800)])[0])
    n = {0: 240, 1: 80, 2: 32}[LOD]
    plaza = polar_ring(tp([(372, 470), (500, 505), (590, 595), (640, 700), (640, 800), (610, 900), (560, 950), (372, 950), (190, 950), (130, 900), (100, 790), (110, 690), (160, 580), (245, 505)]), hub, n//2)
    plaza = offset(plaza, 5)
    plinth(plaza)
    far = polar_ring(tp([(372, 480), (495, 515), (580, 600), (628, 700), (630, 790), (590, 880), (548, 935), (372, 960), (190, 935), (140, 870), (115, 780), (125, 690), (170, 590), (250, 515)]), hub, n)
    near = polar_ring(tp([(372, 660), (450, 680), (495, 730), (503, 800), (500, 925), (372, 955), (240, 925), (238, 800), (255, 730), (295, 680)]), hub, n)
    ids = indices_between(far, hub, -36, 214)
    span = np.linspace(-125, 125, len(ids))
    pick = lambda ring, u: np.c_[np.interp(u, span, ring[ids, 0]), np.interp(u, span, ring[ids, 1])]
    # The arm runs to cap_u; each foot then closes in chords at even turns round a round end, carrying on the arm's taper.
    cap_u = 114
    turn = np.radians(np.linspace(0, 90, {0: 14, 1: 5, 2: 3}[LOD]+1))[1:]
    k = len(turn)
    end = cap_u+(125-cap_u)*np.sin(turn)
    us = np.r_[-end[::-1], np.linspace(-cap_u, cap_u, 2*int(round(cap_u/(span[1]-span[0])))+1), end]
    m = len(us)
    centre, half = (pick(far, us)+pick(near, us))/2, (pick(far, us)-pick(near, us))/2
    half_width = lambda u: np.hypot(*(pick(far, u)-pick(near, u)).T)/2
    side = np.sign(us)*cap_u
    held = half_width(side)+(half_width(side)-half_width(side-2*np.sign(us)))/2*(np.abs(us)-cap_u)
    shut = np.sqrt(1-np.sin(turn)**2)
    closing = np.r_[shut[::-1], np.ones(m-2*k), shut]
    capped = np.abs(us) > cap_u
    half[capped] *= (held*closing/np.hypot(*half.T))[capped, None]
    outer, inner = centre+half, centre-half
    # Outward directions round the whole outline, the round ends included: out of the outer ring, and into the courtyard from the inner one.
    facing = normals(np.r_[outer, inner[-2:0:-1]])
    out_n, in_n = facing[:m], np.r_[facing[:1], facing[m:][::-1], facing[m-1:m]]
    ease = lambda t: np.clip(t, 0, 1)**2*(3-2*np.clip(t, 0, 1))
    foot = lambda u: ease((125-np.abs(u))/26)
    lift = {0: 0, 1: .4, 2: 1.0}[LOD]
    roof_z = lambda u: 34+18*foot(u)+lift
    edge_z = lambda u: roof_z(u)-8*np.exp(-(np.asarray(u)/48)**2)*foot(u)
    kerb = lambda u: ease((106-np.abs(u))/7)  # The planted roof's raised rim, gone on the slopes.
    eave = lambda u: ease((110-np.abs(u))/14)  # The roof's overhang over the courtyard face, gone at the feet.
    bend = 2.0  # The rounded rim's radius.
    rim_z = lambda u: roof_z(u)+.9*kerb(u)
    court_z = lambda u: eave(u)*edge_z(u)+(1-eave(u))*(roof_z(u)-bend)
    # The outer wall wraps round both ends to the courtyard face. Along it, s runs -250+cap_u..250-cap_u: u on the outer ring, 250-|u| on an end's inner half.
    wrap = np.r_[inner[k:0:-1], outer, inner[m-2:m-2-k:-1]]
    wrap_n = np.r_[in_n[k:0:-1], out_n, in_n[m-2:m-2-k:-1]]
    wrap_s = np.r_[-250-us[k:0:-1], us, 250-us[m-2:m-2-k:-1]]
    unwrap = lambda s: np.where(np.abs(s) > 125, np.sign(s)*(250-np.abs(s)), s)
    seam = 250-cap_u
    batter = 3*ease((seam-np.abs(wrap_s))/(seam-cap_u))  # Out at the foot of the outer wall, none where it meets the courtyard face.
    outside = ring_surface(wrap+wrap_n*batter[:, None], wrap, 0, 40, math.radians(seam), along=np.radians(wrap_s), facing=wrap_n, profile=lambda t: 1-(1-t)**2)
    density = {0: 96, 1: 36, 2: 16}[LOD]*cap_u/180
    ovals = [tilted_oval(-92, 31, 20, 15, 9), tilted_oval(-62, 14, 10, 8, 1), tilted_oval(92, 31, 20, 15, -9)]
    # Narrow last columns keep the wall's shading true where it meets the courtyard face.
    columns = np.unique(np.r_[np.linspace(-cap_u, cap_u, int(density)+1), wrap_s[np.abs(wrap_s) > cap_u], .15-seam, seam-.15])
    wrapped_skin('outer wall', outside, lambda a: rim_z(unwrap(np.degrees(a)))-bend, ovals, reach=math.radians(seam), columns=np.radians(columns))
    around = np.radians(us)
    backed = np.abs(us) < 113
    dark = [(ring_on(outside, around[backed], z, inset=DARK_INSET[LOD]), z) for z in (1, rim_z(us[backed])-bend-.5)]
    loft('louvre dark', dark, FLAT, LOUVRE_BACK, closed=False, smooth=None, stone_uv=False, uvs=[(0, 0)]*(2*int(backed.sum())))
    fins('louvre', outside, around, ovals, np.arange(5.0, 52, 3), **LOUVRE, colour=SLAT)
    if LOD == 0:
        at, out = outside(np.radians(np.array([-48.])), np.array([5.2]))
        turn = math.atan2(out[0, 1], out[0, 0])+math.pi/2
        block('service door', (at[0, 0]+out[0, 0]*.2, at[0, 1]+out[0, 1]*.2, 5.25), (4.6, .5, 8), FRAME, (.44, .42, .38), turn=turn)
    # The courtyard face: shop arches below, long windows above, deep piers between them.
    front = inner[::-1]
    face = slice(m-1-k, k-1, -1)  # The inner ring between the ends, from u = cap_u down to -cap_u.
    court = ring_surface(inner[face], inner[face], 0, 60, math.radians(cap_u), facing=in_n[face])
    width = 11
    arches = []
    windows = []
    for u in (-100, -68, -34, 0, 34, 68, 100):
        arches.append([(u-width, -2), (u-width, 10), (u-width*.68, 19), (u, 23), (u+width*.68, 19), (u+width, 10), (u+width, -2)])
        if abs(u) < 90:
            top = float(edge_z(u))
            windows.append([(u-16, 30), (u-16, top-5), (u-12, top-2.4), (u+12, top-2.4), (u+16, top-5), (u+16, 30)])
    if LOD == 2:
        arches, windows = [pill(-104, 104, 3, 22)], [pill(-84, 84, 31, 42)]
    plain = np.linspace(-cap_u, cap_u, int(density)+1)
    wrapped_skin('courtyard face', court, lambda a: court_z(np.degrees(a)), arches+windows, reach=math.radians(cap_u), depth=6,
                 columns=np.radians(np.unique(np.r_[plain, .15-cap_u, cap_u-.15])))
    glass = offset(front, -6.4)
    every = range(m)
    glazing('shops', glass, 1.3, 26, [i for i in every if abs(us[i]) < 113], rng, bay=4, warm=.85, lit=True)  # Its end behind the last pier.
    glazing('upper floor', glass, 29, np.maximum(edge_z(us)-3, 29.5), [i for i in every if abs(us[i]) < 98], rng, bay=4.6, warm=.6, lit=True)
    if LOD == 0:
        door_pair(float(glass[m//2, 0]), float(glass[m//2, 1])-.1, 1.4)
    # The balcony on the courtyard face; its ends curve back into the wall.
    gallery = [i for i in every if abs(us[i]) < 104]
    reach_out = 7.5*ease((104-np.abs(us))/12)-1.5  # Its edge's nose ends inside the wall.
    rim = offset(front, reach_out)
    slab_edge('gallery edge', rim, 26.6, gallery, rise=1.8, nose=.7, under=4)
    walk = offset(front, -6)
    loft('gallery deck', [(rim[gallery], 28.3), (walk[gallery], 28.3)], PAVE, DECK_TINT, closed=False, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for ring in (rim[gallery], walk[gallery]) for q in ring])
    rail('gallery rail', offset(front, reach_out-.6), 28.4, gallery)
    plant_band('gallery plants', offset(front, reach_out-1.8), 28.4, [i for i in gallery if abs(us[i]) < 95], rng, spacing=4, size=(4.5, 8), hang=.45, deep=.5, rim=2.9)
    # The roof: a stone ribbon inside and out, planted between them; three oval lights on stone pads.
    # Chords across the arm, outer edge first. A rounded rim rises from both walls' tops; over the courtyard face it grows into the overhanging eave.
    mix = lambda t: inner+(outer-inner)*t
    flat = roof_z(us)
    dip = edge_z(us)
    p, e = kerb(us), eave(us)
    rim_top = flat+.9*p
    outer_top = outside(around, rim_top-bend)[0][:, :2]  # The outer wall leans out below 40: its top, where the rim starts.
    inner_top = inner.copy()
    inner_top[capped] = outside(np.radians(np.sign(us[capped])*(250-np.abs(us[capped]))), (flat-bend)[capped])[0][:, :2]
    up = np.radians({0: (0, 22.5, 45, 67.5, 90), 1: (0, 45, 90), 2: (0, 90)}[LOD])
    down = np.radians({0: (-45, -90), 1: (-90,), 2: (-90,)}[LOD])
    rows = [(outer_top-out_n*bend*(1-math.cos(t)), rim_top-bend+bend*math.sin(t)) for t in up]
    if LOD == 0:
        rows.append((outer_top-out_n*(bend+.4), flat+.75*p))
    rows.append((outer_top-out_n*(bend+1), flat+.2*p))
    blend = lambda eaved, plain: plain+(eaved-plain)*(e[:, None] if np.ndim(plain) == 2 else e)
    inside = [(mix(.25), flat+.2, bend+1), (mix(.12), dip+(flat-dip)*.35+.8, bend+.7), (mix(.03), dip+.9, bend+.4), (inner, dip+.6, bend+.15)]
    rows += [(blend(at, inner_top-in_n*d), blend(z, flat)) for at, z, d in (inside if LOD == 0 else inside[::3])]
    out, radius, top = 5*e, bend*(1-e)+.8*e, flat*(1-e)+(dip+.2)*e
    rows += [(inner_top+in_n*(out-radius*(1-math.cos(t)))[:, None], top-radius+radius*math.sin(t)) for t in np.r_[up[::-1], down]]
    rows.append((inner_top-in_n*.3, top-2*radius-.2))  # Back under the eave into the wall.
    loft('roof', rows, closed=False, smooth=40, weld=True)
    lawn = np.abs(us) < 99
    a, b = mix(.9)[lawn], mix(.2)[lawn]
    loft('roof planting', [(a, flat[lawn]+.55), (b, flat[lawn]+.55)], TURF, TURF_TINT, closed=False, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for ring in (a, b) for q in ring])
    lights = [(tp([(378, 560)])[0], 26, 11, 0), (tp([(188, 695)])[0], 11, 19, -22), (tp([(555, 680)])[0], 11, 22, 22)]
    pad_sides = {0: 28, 1: 14, 2: 10}[LOD]
    pads = []
    for (x, y), rx, ry, turn in lights:
        ct, st = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        ring = np.array([(x+(rx+5)*math.cos(a)*ct-(ry+5)*math.sin(a)*st, y+(rx+5)*math.cos(a)*st+(ry+5)*math.sin(a)*ct) for a in np.linspace(0, math.tau, pad_sides, endpoint=False)])
        if LOD == 0:
            loft('light pad', [(ring, 52.2), (ring, 53), (offset(ring, -1.4), 53.2)])
        cap('light pad top', offset(ring, -1.4), 53.2+lift)
        skylight('roof light', x, y, 53.3+lift, rx, ry, rise=2.8, turn=turn)
        pads.append((x, y, max(rx, ry)+8))
    clear = lambda ring: [i for i in every if foot(us[i]) > 11/12 and all(math.hypot(ring[i, 0]-x, ring[i, 1]-y) > r for x, y, r in pads)]
    for t, spacing in ((.8, 2.8), (.58, 3), (.36, 3)):
        ring = mix(t)
        plant_band('roof plants', ring, flat+.5, clear(ring), rng, spacing=spacing, size=(6, 10.5), flowers=.08, deep=3)
    count = len(span)  # Trees stand at fixed angles, clear of the roof lights.
    for t, i in ((.5, count//5), (.5, count*4//5), (.62, count//2+6), (.4, count//2-16), (.6, count*3//10), (.6, count*7//10)):
        ring = mix(t)
        tree(np.interp(span[i], us, ring[:, 0]), np.interp(span[i], us, ring[:, 1]), roof_z(span[i])+.5, rng.uniform(10, 13), rng.uniform(10, 13), rng)
    # The courtyard: a round bed with a tree, two curved benches, and beds at the feet.
    cx, cy = tp([(372, 810)])[0]
    round_bed('court bed', cx, cy, 1.4, 22, rng, 27, 22)
    round_bench(cx, cy, 1.4, 31, 115, 175)
    round_bench(cx, cy, 1.4, 31, -65, -5)
    if LOD == 0:
        rocks([(cx+rng.uniform(-14, 14), cy+rng.uniform(-14, 14)) for _ in range(6)], 3.8, rng)
    base = outer+out_n*6
    plant_band('ground plants', base, 1.4, [i for i in every if abs(us[i]) > 84 or abs(us[i]) < 40], rng, spacing=3.6, size=(5, 9), deep=1.6)
    flush_cards()
    return outer, inner, us


def market_volumes(outer, inner, us):
    """Behind the shop glass and the outer wall; the feet stop lower than the middle. A thin top gives the roof its hexes."""
    band = lambda limit: (lambda keep: np.r_[offset(outer, -5)[keep], offset(inner, 8)[keep][::-1]])(np.abs(us) <= limit)
    volume_prism('building_volume ground', band(104), 0, 18)
    volume_prism('building_volume feet', np.r_[outer, inner[::-1]], 35, 36)
    volume_prism('building_volume upper', band(104), 18, 36)
    volume_prism('building_volume top', band(98), 36, 53)
    volume_prism('building_volume roof', np.r_[outer[np.abs(us) <= 108], inner[np.abs(us) <= 108][::-1]], 53, 54)


def civic_conservatory(rng):
    """Sheet 'Civic Conservatory', 3 x 2 hexes and a bulge: a stone roof of three arms round a glass dome; a great arch under the southern one; planted tiers between them."""
    tp = lambda points: [((x-385)*.44-30, (745-y)*.44-30) for x, y in points]
    hub = np.array(tp([(385, 745)])[0])
    n = {0: 240, 1: 80, 2: 40}[LOD]
    plaza = polar_ring(tp([(95, 545), (108, 490), (150, 460), (205, 465), (265, 505), (320, 555), (385, 590), (470, 590), (550, 595), (625, 625), (660, 680), (640, 755), (585, 810), (525, 870),
                           (490, 925), (385, 938), (280, 925), (235, 880), (190, 820), (130, 700)]), hub, n//2)
    plinth(plaza)
    base = polar_ring(tp([(110, 545), (122, 500), (155, 475), (200, 478), (258, 520), (315, 570), (385, 605), (470, 605), (548, 610), (615, 637), (642, 685), (625, 745), (575, 797), (515, 858),
                          (480, 905), (385, 918), (285, 905), (245, 870), (205, 810), (148, 695)]), hub, n)
    roof = polar_ring(tp([(130, 520), (165, 490), (205, 498), (250, 545), (305, 592), (370, 622), (405, 628), (470, 678), (520, 655), (575, 632), (625, 660), (635, 700), (605, 740), (545, 768),
                          (497, 790), (490, 830), (497, 880), (440, 915), (385, 925), (330, 917), (272, 900), (262, 850), (292, 790), (295, 740), (275, 700), (220, 660), (170, 610), (130, 560)]), hub, n)
    bearing = np.degrees(np.arctan2(*(roof-hub).T[::-1]))
    ease = lambda t: np.clip(t, 0, 1)**2*(3-2*np.clip(t, 0, 1))
    off_south = np.abs(((bearing+90+180) % 360)-180)
    tiers_z = 52+10*np.exp(-((bearing-138)/28)**2)+2*np.exp(-((bearing-5)/30)**2)
    arch_z = 50*np.maximum(1-np.minimum(off_south/40, 1)**2.4, 0)**.6
    edge_z = np.where(off_south < 40, np.maximum(arch_z, 2), 2+(tiers_z-2)*ease((off_south-40)/32))
    fan_ids = indices_between(roof, hub, -130, -50)
    arc = indices_between(roof, hub, -30, 210)
    ids = indices_between(roof, hub, -28, 208)
    # Towards the arch the tiers close into the stone; the plinth keeps its beds there.
    closing = ease(np.minimum(((bearing+30) % 360), ((210-bearing) % 360))/34)
    closing[off_south < 60] = 0
    plinth_edge = base
    base = roof+(base-roof)*closing[:, None]
    arc = [i for i in arc if closing[i] > .6]
    ids = [i for i in ids if closing[i] > .64]
    decks = [base, base+(roof-base)*.5]
    # The great arch: the fan's edge, deep enough that the openings have a soffit. Its flanks climb from the feet to the tiers.
    fan = roof[fan_ids]
    reach = math.radians(40)
    fan_z = edge_z[fan_ids]
    fan_u = np.linspace(-40, 40, len(fan))
    proud = lambda ring: ring+(ring-hub)/np.hypot(*(ring-hub).T)[:, None]*.3
    wall = ring_surface(offset(fan, 2.5), proud(fan), 0, 30, reach, away_from=hub)
    openings = [[(-27, -2), (-27, 6), (-23, 20), (-12, 32), (0, 36), (12, 32), (23, 20), (27, 6), (27, -2)],
                [(-37, -2), (-37, 5), (-33.5, 10), (-30, 5), (-30, -2)], [(30, -2), (30, 5), (33.5, 10), (37, 5), (37, -2)]]
    wrapped_skin('great arch', wall, lambda a: np.maximum(np.interp(np.degrees(a), fan_u, fan_z)-.6, 2), openings, reach=reach, depth=8)
    for a0, a1 in ((-52, -26.5), (-165, -128)):
        flank = indices_between(roof, hub, a0, a1)
        loft('arch flank', [(roof[flank], 0), (roof[flank], edge_z[flank]-.5)], closed=False)
    # The lobby's glass stays under the roof as the fan comes down.
    dome_rx, dome_ry = 26, 38
    angle = np.radians(bearing)
    kerb_r = (dome_rx+1.5)*(dome_ry+1.5)/np.hypot((dome_ry+1.5)*np.cos(angle), (dome_rx+1.5)*np.sin(angle))
    kerb = hub+np.c_[kerb_r*np.cos(angle), kerb_r*np.sin(angle)]
    top_z = 53.0
    reach_in = np.hypot(*(fan-kerb[fan_ids]).T)
    lobby_ring = fan+(hub-fan)/np.hypot(*(hub-fan).T)[:, None]*9
    lobby_top = np.minimum(38, fan_z+1+(top_z-fan_z-1)*ease(9/reach_in)-2.5)
    glazing('lobby', lobby_ring, 1.3, np.maximum(lobby_top, 3), [i for i in range(len(fan)) if abs(fan_u[i]) < 36], rng, bay=5, warm=.9, lit=True)
    if LOD == 0:
        door_pair(float(hub[0]), float(lobby_ring[:, 1].min())-.2, 1.4)
    # The eastern louvre, one long oval between the first tier and the roof.
    east = indices_between(roof, hub, -28, 48)
    span = math.radians(38)
    low = decks[1][east]
    louvre_wall = ring_surface(proud(low), proud(roof[east]), 18, 54, span)
    oval = [tilted_oval(-2, 36, 24, 11, 4, 12)]
    east_z = edge_z[east]
    east_u = np.linspace(-38, 38, len(east))
    wrapped_skin('east wall', louvre_wall, lambda a: np.interp(np.degrees(a), east_u, east_z)-.6, oval, reach=span)
    around = np.radians(east_u)
    near_oval = np.abs(east_u) < 29
    backing = [(ring_on(louvre_wall, around[near_oval], z, inset=DARK_INSET[LOD]), z) for z in (22, east_z[near_oval]-2)]
    loft('louvre dark', backing, FLAT, LOUVRE_BACK, closed=False, smooth=None, stone_uv=False, uvs=[(0, 0)]*(2*int(near_oval.sum())))
    fins('louvre', louvre_wall, around, oval, np.arange(20.0, 54, 3), **LOUVRE, colour=SLAT)
    # Tiers on every other side.
    past_east = (bearing > 44) | (bearing < -150)
    keep = [i for i in ids if past_east[i]]
    keep_arc = [i for i in arc if past_east[i]]
    glazing('ground storey', offset(base, -5), 1.3, 16.5, ids, rng, bay=4.6, warm=.75, lit=True)
    settled = [i for i in ids if closing[i] > .7 and not 30 < bearing[i] < 50]
    grown = ease((((bearing-44+180) % 360)-180)/14)
    upper = decks[1]+(roof-decks[1])*(.5*(1-grown)*past_east)[:, None]
    past_wall = (bearing > 47) | (bearing < -150)
    terrace('tier 0', decks[0], upper, 18, 36, arc, [i for i in ids if past_wall[i]], rng, phase=.4, hang=.14, warm=.5, lit=True, planted=settled)
    terrace('tier 1', upper, roof, 36, np.minimum(edge_z, 54), keep_arc, keep, rng, phase=2.1, hang=.1, warm=.5, lit=True, planted=[i for i in settled if past_east[i]])
    wall_end = lambda z: louvre_wall(np.array([span]), np.array([float(z)]))[0][0]
    glass_end = offset(roof, -3.4)[east[-1]]
    return_top = float(east_z[-1])-.6
    add_mesh('east wall return', STONE, STONE_TINT, [(*glass_end, 36), (*glass_end, return_top), wall_end(return_top), wall_end(36)], [(0, 1, 2, 3)], smooth=None)
    loft('roof hood', [(roof[keep_arc], np.full(len(keep_arc), 52.0)), (roof[keep_arc], np.maximum(edge_z[keep_arc]-1, 52.5))], closed=False)
    inner_core = hub+(roof-hub)*np.minimum(np.hypot(*(offset(roof, -7)-hub).T)/np.hypot(*(roof-hub).T), .78)[:, None]
    loft('inner core', [(inner_core, 0), (inner_core, np.maximum(edge_z-3.5, 3))])
    # The roof: rounded edge, three arms flowing to a kerb round the dome.
    to_kerb = np.hypot(*(kerb-roof).T)
    towards = lambda d: roof+((kerb-roof)/to_kerb[:, None])*np.minimum(d, to_kerb*d/24)[:, None]
    climb = np.abs(np.gradient(edge_z))*n/240
    calm = np.clip(1.5-climb, 0, 1)
    rows = [(roof, edge_z-1), (towards(.4), edge_z-1+1.4*calm), (towards(2), edge_z-1+2.3*calm), (towards(4), edge_z-1+2*calm), (towards(6), edge_z-1+calm)]
    for t, lift in ((.3, 0), (.55, 0), (.8, -.4), (.93, -.2), (1, 1.2)):
        rows.append((roof+(kerb-roof)*t, edge_z+(top_z-edge_z)*ease(t)+lift))
    loft('stone roof', rows if LOD == 0 else [rows[k] for k in (0, 2, 4, 5, 6, 9)], smooth=50)
    skylight('dome', float(hub[0]), float(hub[1]), top_z+1, dome_rx, dome_ry, rise=12, ribs=16, rings=5)
    # Trees on the tiers.
    def tier_floor(x, y):
        i = int(np.argmin(np.abs(((np.degrees(math.atan2(y-hub[1], x-hub[0]))-bearing+180) % 360)-180)))
        out = math.hypot(x-hub[0], y-hub[1])
        if past_east[i] and out < math.hypot(*(decks[1][i]-hub))-2:
            return 38.8
        return 20.8 if closing[i] > .64 and out < math.hypot(*(decks[0][i]-hub))-2 else 1.4
    for x, y, height, spread in ((260, 800, 18, 15), (225, 760, 22, 18), (465, 620, 19, 16), (575, 800, 15, 13)):
        (tx, ty), = tp([(x, y)])
        tree(tx, ty, tier_floor(tx, ty), height, spread, rng)
    # Beds round the foot.
    ground = offset(plinth_edge, -1)
    plant_band('ground plants', ground, 1.4, [i for i in range(n) if off_south[i] > 42], rng, spacing=2.8, size=(5.5, 10), flowers=.14, deep=2.5)
    pocket = [i for i in range(n) if 50 < off_south[i] < 62]
    plant_band('pocket plants', plinth_edge+(roof-plinth_edge)*.55, 1.4, pocket, rng, spacing=2.8, size=(6, 11), flowers=.16, deep=4)
    flush_cards()
    return roof, plinth_edge, decks, edge_z, hub, fan_ids, kerb, top_z


def civic_volumes(roof, base, decks, edge_z, hub, fan_ids, kerb, top_z):
    """Inside the glass of each tier, behind the lobby under the arch, each floor under the roof that slopes over it; a thin top gives the stone roof its hexes."""
    def under_roof(ring, z):
        # How far in from the edge the roof, rising as ease(t) towards the kerb, clears this solid's top.
        need = np.clip((z+2-edge_z)/np.maximum(top_z-edge_z, 1), 0, 1)
        t = .5-np.sin(np.arcsin(1-2*need)/3)
        limit = np.hypot(*(roof+(kerb-roof)*t[:, None]-hub).T)
        out = np.hypot(*(ring-hub).T)
        return hub+(ring-hub)*(np.minimum(out, limit)/out)[:, None]
    lobby = roof+(hub-roof)/np.hypot(*(hub-roof).T)[:, None]*11
    behind = decks[0].copy()
    behind[fan_ids] = lobby[fan_ids]
    volume_prism('building_volume ground', offset(behind, -6), 0, 17)
    volume_prism('building_volume first deck', base, 17, 18)
    second = decks[1].copy()
    second[fan_ids] = lobby[fan_ids]
    volume_prism('building_volume second', under_roof(offset(second, -5), 36), 18, 36)
    third = roof.copy()
    third[fan_ids] = lobby[fan_ids]
    volume_prism('building_volume third', under_roof(offset(third, -5), 52), 36, 53)
    volume_prism('building_volume roof', roof, 53, 54)


def sky_gardens(rng):
    """Sheet 'Sky Gardens', 3 x 3 hexes: a six-level and a four-level planted block joined by a glazed sky bridge over an arch, a garden court with a tree."""
    tp = lambda points: [((x-385)*.394, (725-y)*.394+12) for x, y in points]
    n = {0: 64, 1: 32, 2: 20}[LOD]
    plaza = polar_ring(tp([(113, 545), (122, 522), (145, 510), (320, 510), (345, 550), (355, 600), (385, 615), (430, 610), (480, 570), (510, 515), (635, 510), (657, 522), (665, 548), (665, 900), (657, 928), (630, 948),
                           (150, 948), (125, 935), (113, 908)]), tp([(385, 760)])[0], SAMPLES[LOD])
    plaza = offset(plaza, 5)
    plinth(plaza)
    # The tall block, terraced all round.
    left_c = tp([(235, 715)])[0]
    left_base = polar_ring(tp([(133, 600), (165, 525), (235, 520), (305, 535), (338, 600), (342, 700), (332, 800), (330, 860), (300, 895), (220, 905), (160, 890), (135, 850), (130, 720)]), left_c, n)
    left_top = polar_ring(tp([(165, 620), (190, 545), (250, 535), (300, 550), (320, 620), (318, 720), (300, 800), (262, 832), (200, 822), (170, 770), (160, 700)]), left_c, n)
    left_decks = [left_base+(left_top-left_base)*.72*(k/5)**.9 for k in range(6)]
    every = list(range(n))
    bridge_y = tp([(0, 685)])[0][1], tp([(0, 750)])[0][1]
    # Ground storey of the tall block: stone with a glazed arch to the south and louvres.
    surface = ring_surface(offset(left_base, 1), left_base, 0, 18, math.pi, closed=True)
    # The polar ring starts at the west, so the south is at -90 degrees.
    arch = [(-110, -2), (-110, 8), (-102, 15), (-90, 17), (-78, 15), (-70, 8), (-70, -2)]
    louvres = [pill(-64, -32, 3, 13)]
    wrapped_skin('tall ground', surface, lambda a: np.full(len(a), 17.0), [arch]+louvres if LOD < 2 else [arch], reach=math.pi, depth=5)
    core = offset(left_base, -5)
    glazing('tall lobby', core, 1.3, 16, every, rng, bay=6, warm=.8, lit=True, closed=True)
    if LOD < 2:
        around = np.linspace(-math.pi, math.pi, n, endpoint=False)
        fins('tall louvre', surface, around, louvres, np.arange(4.5, 13, 2.4), **LOUVRE, colour=SLAT)
    if LOD == 0:
        i = int(np.argmin(left_base[:, 1]))
        door_pair(float(left_base[i, 0]), float(core[i, 1])-.1, 1.4)
    for k in range(5):
        terrace(f'tall deck {k}', left_decks[k], left_decks[k+1], 18*(k+1), 18*(k+2), every, every, rng, phase=k*1.3, hang=.35, warm=.35, lit=True, plants=5, bay=6.5)
    # Its roof garden: a low rim, a winding path, a skylight, plants and small trees.
    roof = 108.0
    ring = left_decks[5]
    slab_edge('tall roof edge', ring, roof, every)
    rail('tall roof rail', offset(ring, -.8), roof+2.8, every)
    bed = offset(ring, -.4)
    cap('tall roof garden', bed, roof+2.4, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in bed])
    sky = tp([(253, 635)])[0]
    skylight('tall skylight', sky[0], sky[1], roof+2.5, 13, 16, rise=3.5)
    for name, points in (('tall path', [(190, 720), (215, 690), (222, 640), (240, 560), (285, 575), (300, 650), (290, 720), (250, 770), (215, 790), (185, 760)]),):
        loop = arc_ring(tp(points), {0: 48, 1: 20, 2: 12}[LOD])
        loft(name, [(offset(loop, 3), roof+2.65), (offset(loop, -3), roof+2.65)], PAVE, DECK_TINT, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for r in (offset(loop, 3), offset(loop, -3)) for q in r])
        keep_path(loop, 3.5, roof+2.4)
    plant_band('tall roof plants', offset(ring, -6), roof+2.4, every, rng, spacing=3, size=(6, 10.5), flowers=.1, deep=1.5)
    plant_band('tall roof plants inner', offset(ring, -19), roof+2.4, every, rng, spacing=6, size=(6, 10), flowers=.14, deep=2)
    for x, y in ((195, 590), (305, 600), (200, 780), (280, 790), (240, 700)):
        (tx, ty), = tp([(x, y)])
        tree(tx, ty, roof+2.4, rng.uniform(13, 16), rng.uniform(11, 14), rng)
    # The lower block: terraces to the court and the north, a stone wall with long openings to the east.
    right_c = tp([(572, 720)])[0]
    right_base = polar_ring(tp([(495, 620), (515, 555), (560, 535), (625, 540), (650, 590), (654, 720), (650, 830), (640, 880), (600, 905), (530, 905), (497, 870), (495, 740)]), right_c, n)
    right_top = polar_ring(tp([(520, 640), (532, 575), (570, 555), (615, 560), (635, 605), (638, 720), (636, 800), (625, 860), (590, 880), (540, 870), (515, 820), (510, 720)]), right_c, n)
    right_decks = [right_base+(right_top-right_base)*.72*(k/3)**.9 for k in range(4)]
    wall_ids = indices_between(right_base, right_c, -65, 135)
    rest = indices_between(right_base, right_c, 133, -60)
    rest_arc = indices_between(right_base, right_c, 131, -58)
    span = math.radians(100)
    low, high = right_base[wall_ids], right_decks[3][wall_ids]
    east = ring_surface(low, high, 0, 72, span)
    bands = []
    fin_bands = []
    for k in range(3):
        z = 18*(k+1)
        bands.append(pill(-58, 26, z+1.5, z+14.5))
        fin_bands.append(pill(-93, -66, z+5, z+13))
    bands.append(pill(-58, 26, 2.5, 15.5))
    wrapped_skin('low block wall', east, lambda a: np.full(len(a), 71.4), bands+fin_bands, reach=span)
    around = np.radians(np.linspace(-100, 100, len(wall_ids)))
    behind = around[np.degrees(around) < -60]
    backing = [(ring_on(east, behind, z, inset=DARK_INSET[LOD]+.2), z) for z in (1, 71)]
    loft('low block dark', backing, FLAT, LOUVRE_BACK, closed=False, smooth=None, stone_uv=False, uvs=[(0, 0)]*(2*len(behind)))
    pane = ring_on(east, around, 36, inset=4.2)
    past = 0 if LOD == 0 else 200/(len(around)-1)  # A coarser ring reaches past the opening's ends.
    glazing('low block glass', pane, 1.3, 71, [i for i in range(len(pane)) if -62-past <= math.degrees(around[i]) <= 30+past], rng, bay=6.5, warm=.35, lit=True)
    fins('low block louvre', east, around, fin_bands, np.arange(20.0, 70, 3), **LOUVRE, colour=SLAT)
    for k in range(3):
        sill = ring_on(east, around, 18*(k+1), inset=-1)
        slab_edge(f'east sill {k}', sill, 18*(k+1), [i for i in range(len(sill)-1) if -58 <= math.degrees(around[i]) <= 26], rise=1.4, nose=.5, under=3, drop=.8, floor_to=ring_on(east, around, 18*(k+1), inset=4))
        plant_band('east plants', ring_on(east, around, 18*(k+1), inset=-.7), 18*(k+1)+1.2, [i for i in range(len(sill)) if -48 <= math.degrees(around[i]) <= 16], rng, spacing=8, size=(3.6, 6.5), hang=.7, deep=.2, rim=2)
    glazing('low ground', offset(right_base, -5), 1.3, 16, rest, rng, bay=6, warm=.8, lit=True)
    for i, flip in ((rest[0], False), (rest[-1], True)):
        foot, head = right_base[i], right_decks[3][i]
        inner = right_c+(foot-right_c)*.45
        points = [(*foot, 0), (*inner, 0), (*inner, 71), (*head, 71)]
        add_mesh('low block end', STONE, STONE_TINT, points[::-1] if flip else points, [(0, 1, 2, 3)], smooth=None)
    for k in range(3):
        terrace(f'low deck {k}', right_decks[k], right_decks[k+1], 18*(k+1), 18*(k+2), rest_arc, rest, rng, phase=k*2.2, hang=.35, warm=.35, lit=True, plants=5, bay=6.5, planted=rest[3:-3])
    # Its roof: paving, a pergola, a timber path, beds and trees.
    top_z = 72.0
    ring = right_decks[3]
    slab_edge('low roof edge', ring, top_z, every)
    rail('low roof rail', offset(ring, -.8), top_z+2.8, every)
    bed = offset(ring, -.4)
    cap('low roof', bed, top_z+2.4, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in bed])
    loop = arc_ring(tp([(565, 620), (610, 650), (610, 710), (590, 760), (598, 830), (565, 850), (548, 780), (560, 700), (535, 660)]), {0: 40, 1: 16, 2: 10}[LOD])
    cap('low roof deck', loop[::-1], top_z+2.6, PAVE, DECK_TINT)
    keep_path(loop, 6, top_z+2.4)
    px, py = tp([(582, 660)])[0]
    keep_clear(px, py, 13, 13, top_z+2.4)
    posts = [(px+dx, py+dy) for dx in (-11, 11) for dy in (-11, 11)]
    for x, y in posts:
        tube('pergola post', [(x, y, top_z+2.6), (x, y, top_z+12)], .7, STONE, STONE_TINT, sides=6 if LOD == 0 else 3)
    block('pergola beam', (px, py-11, top_z+12.2), (26, 1.2, 1.2), STONE, STONE_TINT)
    block('pergola beam', (px, py+11, top_z+12.2), (26, 1.2, 1.2), STONE, STONE_TINT)
    if LOD < 2:
        for dy in np.linspace(-10, 10, 9 if LOD == 0 else 4):
            block('pergola slat', (px, py+dy, top_z+13.2), (24, .7, .7), STONE, STONE_TINT)
    plant_band('low roof plants', offset(ring, -6), top_z+2.4, every, rng, spacing=3, size=(6, 10.5), flowers=.1, deep=1.5)
    for x, y in ((535, 590), (620, 600), (530, 830), (625, 840), (555, 720)):
        (tx, ty), = tp([(x, y)])
        tree(tx, ty, top_z+2.4, rng.uniform(13, 16), rng.uniform(11, 14), rng)
    # The sky bridge: a stone arch below, a glazed storey, a planted roof.
    x0, x1 = tp([(322, 0)])[0][0], tp([(510, 0)])[0][0]
    south, north = bridge_y[1], bridge_y[0]
    deep = north-south
    steps = 40
    line = np.c_[np.linspace(x0, x1, steps), np.full(steps, south)]
    flat_reach = math.radians(45)
    court_arch = ring_surface(line, line, 0, 40, flat_reach)
    arch_points = [(-28, -2), (-28, 12), (-21, 26), (-8, 33), (8, 33), (21, 26), (28, 12), (28, -2)]
    wrapped_skin('bridge arch', court_arch, lambda a: np.full(len(a), 36.0), [arch_points], reach=flat_reach, depth=deep)
    back_line = line[::-1]*(1, 0)+(0, north)
    wrapped_skin('bridge arch north', ring_surface(back_line, back_line, 0, 40, flat_reach), lambda a: np.full(len(a), 36.0), [arch_points], reach=flat_reach, depth=1.5)
    glass_s = np.c_[np.linspace(x0, x1, steps), np.full(steps, south+1.6)]
    glass_n = glass_s[::-1]*(1, 0)+(0, north-1.6)
    glazing('bridge south', glass_s, 37.5, 52, range(steps), rng, bay=6.5, warm=.5, lit=True)
    glazing('bridge north', glass_n, 37.5, 52, range(steps), rng, bay=6.5, warm=.3, lit=True)
    block('bridge floor', ((x0+x1)/2, (south+north)/2, 36.4), (x1-x0, deep+1.6, 1.6), STONE, STONE_TINT)
    block('bridge roof', ((x0+x1)/2, (south+north)/2, 53), (x1-x0, deep+2.4, 2.6), STONE, STONE_TINT)
    for y in (south-.6, north+.6):
        block('bridge parapet', ((x0+x1)/2, y, 55.4), (x1-x0, 1.2, 2.4), STONE, STONE_TINT)
    cap('bridge garden', np.array(((x0, south+.5), (x1, south+.5), (x1, north-.5), (x0, north-.5))), 54.4, TURF, TURF_TINT, stone_uv=False,
        uvs=[(x0/LAWN_REPEAT, south/LAWN_REPEAT), (x1/LAWN_REPEAT, south/LAWN_REPEAT), (x1/LAWN_REPEAT, north/LAWN_REPEAT), (x0/LAWN_REPEAT, north/LAWN_REPEAT)])
    strip = np.c_[np.linspace(x0+16, x1-16, 30), np.full(30, (south+north)/2)]
    plant_band('bridge plants', strip, 54.4, range(30), rng, spacing=3.4, size=(6, 10.5), flowers=.16, deep=7)
    for x in (x0+22, x1-20):
        tree(x, (south+north)/2, 54.4, rng.uniform(14, 17), rng.uniform(12, 15), rng)
    # The garden court.
    cx, cy = tp([(385, 815)])[0]
    round_bed('court bed', cx, cy, 1.4, 15, rng, 26, 22)
    round_bench(cx, cy, 1.4, 22, 150, 215)
    round_bench(cx, cy, 1.4, 22, -60, 0)
    keep_clear((x0+x1)/2, (south+north)/2, (x1-x0)/2+6, deep/2+6, 1.4)
    # Beds along the plinth's front, either side of the walk to the court.
    for x0_px, x1_px in ((130, 335), (500, 650)):
        strip = np.array(tp([(x, 928) for x in np.linspace(x0_px, x1_px, 24)]))
        plant_band('front bed', strip, 1.4, range(24), rng, spacing=4.5, size=(5.5, 10), flowers=.12, deep=2.5)
    # Beds at the foot of both blocks.
    for ring, name in ((offset(left_base, 4.5), 'tall foot'), (offset(right_base, 4.5), 'low foot')):
        i0 = int(np.argmin(ring[:, 1]))
        keep = [i for i in every if math.hypot(ring[i, 0]-ring[i0, 0], ring[i, 1]-ring[i0, 1]) > 22]
        plant_band(name, ring, 1.4, keep, rng, spacing=5, size=(5.5, 10), flowers=.1, deep=2)
    flush_cards()
    return left_decks, right_decks, (x0, x1, south, north)


def sky_volumes(left_decks, right_decks, bridge):
    """Every block's floors behind its glass; the bridge's over its arch."""
    x0, x1, south, north = bridge
    for block, decks, count in (('tall', left_decks, 6), ('low', right_decks, 4)):
        volume_prism(f'building_volume {block} ground', offset(decks[0], -7), 0, 17)
        volume_prism(f'building_volume {block} first deck', decks[0], 17, 18)
        for k in range(1, count):
            volume_prism(f'building_volume {block} {k}', offset(decks[k], -6), 18*k, 18*(k+1))
    plan = np.array(((x0, south+3), (x1, south+3), (x1, north-3), (x0, north-3)))
    volume_prism('building_volume bridge', plan, 36, 54)


def smooth_keys(keys, span=14):
    """A function through (x, value) keys, with its corners rounded over span units."""
    xs, vs = np.array(keys, float).T
    grid = np.arange(xs[0]-span, xs[-1]+span+1)
    line = np.interp(grid, xs, vs)
    box = np.ones(span)/span
    for _ in range(2):
        line = np.convolve(np.pad(line, span, 'edge'), box, 'same')[span:-span]
    return lambda x: np.interp(x, grid, line)


def town_tower(rng):
    """Sheet 'Crown Observatory', 7 hexes, 16 levels: three twisting ribs and a glass shaft carry a trefoil crown over a glazed podium and a planted plaza.

    The sheet at this height would span 390 units, so the plan is drawn in: crown 180, podium 168, plaza 256 across.
    """
    n = SAMPLES[LOD]
    axis = (0, 0)
    around = np.linspace(-math.pi, math.pi, n, endpoint=False)
    circle = lambda r: np.c_[r*np.cos(around), r*np.sin(around)]
    arc = lambda r, a0, a1, count: [(r*math.cos(math.radians(a)), r*math.sin(math.radians(a))) for a in np.linspace(a0, a1, count)]
    edge = polar_ring([((x-385)*.6, (700-y)*.6) for x, y in ((385, 852), (440, 828), (447, 770), (470, 742), (505, 725), (535, 680), (530, 630), (490, 605), (440, 603),
                                                             (385, 612), (330, 603), (280, 605), (240, 630), (235, 680), (265, 725), (300, 742), (323, 770), (330, 828))], axis, n)
    radii = np.hypot(*edge.T)
    reach = lambda deg: float(np.interp(math.radians(deg), around, radii, period=math.tau))
    # The plaza and its six planted beds, with curved benches facing the podium.
    plaza = circle(128)
    plinth(plaza)
    for at in (-52, -128, 180, 0, 58, 122):
        bed = arc_ring(arc(120, at-19, at+19, 7)+arc(101, at+19, at-19, 7), {0: 48, 1: 16, 2: 8}[LOD])
        loft('bed kerb', [(bed, 1.4), (bed, 3.4), (offset(bed, -.9), 3.6)] if LOD == 0 else [(bed, 1.4), (bed, 3.4)])
        soil = offset(bed, -.9) if LOD == 0 else bed
        cap('bed soil', soil, 3.6 if LOD == 0 else 3.4, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in soil])
        mid = np.array(arc(110.5, at-17, at+17, 24 if LOD == 0 else 10))
        plant_band('bed plants', mid, 3.4, range(len(mid)), rng, spacing=2.8, size=(6, 10), flowers=.2, deep=4.5)
        for off in (-9, 9):
            x, y = arc(110.5, at+off, at+off, 1)[0]
            tree(x, y, 3.4, rng.uniform(15, 20), rng.uniform(13, 17), rng)
        if LOD == 0:
            for off in (-11, 11):
                tube('bench', [(*q, 2.9) for q in arc(95, at+off-5, at+off+5, 7)], 1.3, STONE, STONE_TINT, sides=6)
    # The podium, two levels of warm glass, drawn back at the door behind the arch.
    degrees = np.degrees(around)
    pod = circle(84)*(1-(22/84)*np.maximum(np.exp(-((degrees+90)/52)**4), np.exp(-((degrees-90)/20)**2)))[:, None]
    glass = offset(pod, -4)
    glazing('podium glass', glass, 1.3, 29, indices_between(pod, axis, 96, 84), rng, bay=5, warm=.5, lit=True)
    slab_edge('podium edge', pod, 31, rise=3, nose=1, under=7, drop=2)
    roof = 33.2
    garden = offset(pod, -.1)
    cap('podium roof', garden, roof, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in garden])
    loft('podium walk', [(pod*.72, roof+.2), (pod*.62, roof+.2)], PAVE, DECK_TINT, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for ring in (pod*.72, pod*.62) for q in ring])
    keep_path(pod*.67, 4, roof)
    keep_clear(0, -56, 36, 10, roof)
    for at in (-125, -55, 90):
        x, y = arc(52, at, at, 1)[0]
        keep_clear(x, y, 15, 15, roof)
    plant_band('podium plants', offset(pod, -6), roof, range(n), rng, spacing=3.2, size=(6, 10), flowers=.14, deep=2, hang=.06, rim=7.2)
    plant_band('podium plants inner', pod*.82, roof, range(n), rng, spacing=4.5, size=(5.5, 9), deep=2.5)
    for at in (-20, 25, 60, 120, 155, -160):
        x, y = arc(68, at, at, 1)[0]
        tree(x, y, roof, rng.uniform(15, 20), rng.uniform(13, 17), rng)
    if LOD == 0:
        door_pair(0, float(glass[:, 1].min())-.2, 1.4)
    # The stem's foot rises smoothly from the podium's garden.
    round_sides = {0: 30, 1: 16, 2: 10}[LOD]
    round_ring = lambda r: np.array(arc(r, -180, 180-360/round_sides, round_sides))
    loft('stem foot', [(round_ring(42), roof), (round_ring(24), roof+15), (round_ring(12.9), roof+38)], smooth=70)
    # The glass shaft.
    shaft = round_ring(13)
    obj = loft('shaft', [(shaft, roof), (shaft, 196)], GLASS, GLASS_TINT, smooth=60, stone_uv=False, uvs=[(float(q[0])/18, z/18) for z in (roof, 196) for q in shaft])
    shared.emissive(obj, NIGHT_GLASS, night=True)
    if LOD == 0:
        for z in np.arange(54, 190, 18):
            tube('shaft floor', [(q[0], q[1], z) for q in round_ring(13.2)], .5, FRAME, FRAME_TINT, sides=3, closed=True)
            at = rng.uniform(-150, -30)
            x, y = arc(13.3, at, at, 1)[0]
            glow = block('shaft light', (x, y, z+7), (3.2, 3.2, 5), FLAT, (.9, .75, .5))
            shared.emissive(glow, (1, .82, .55), night=True)
        for at in range(-165, 180, 30):
            x, y = arc(13.2, at, at, 1)[0]
            block('shaft mullion', (x, y, (roof+196)/2), (.45, .45, 196-roof))
    # The crown's underside: a bell from the stem out to the first floor's edge.
    bell = []
    for f, z in {0: ((.2, 150), (.22, 170), (.3, 185), (.43, 196), (.62, 205), (.8, 211), (.94, 215), (1, 217)),
                 1: ((.2, 150), (.3, 185), (.62, 205), (.94, 215), (1, 217)), 2: ((.2, 150), (.5, 200), (1, 217))}[LOD]:
        bell.append((edge*f, z))
    loft('crown bell', bell, smooth=70)
    if LOD == 0:
        cove = tube('cove light', [(q[0], q[1], 209) for q in (edge*.73)[::2]], .5, FLAT, (.9, .75, .5), sides=3, closed=True)
        shared.emissive(cove, (1, .82, .55), night=True)
    # Three ribs climb and twist from the plaza to the crown's dips, where they pass in front of the glass into the rim.
    lobe = (radii-radii.min())/(radii.max()-radii.min())
    rim_top = 266+4*lobe
    z_rows = {0: np.r_[np.linspace(0, 60, 9), np.linspace(70, 190, 8), np.linspace(198, 240, 7), 258],
              1: np.r_[np.linspace(0, 60, 5), np.linspace(80, 190, 4), np.linspace(202, 240, 4), 258],
              2: np.r_[0, 20, 50, 110, 170, 205, 225, 258]}[LOD]
    section = {0: 14, 1: 8, 2: 5}[LOD]
    twist = lambda z: float(np.clip((z-60)/150, 0, 1))
    for bottom, high in ((-125, -154), (-55, -26), (90, 90)):
        far = reach(high)
        outer = smooth_keys([(0, 92), (9, 84), (30, 62), (48, 48), (80, 30), (112, 19), (170, 26), (200, 42), (216, far+1.2), (290, far+1.2)])
        inner = smooth_keys([(0, 72), (30, 46), (60, 26), (78, 12), (98, 11), (183, 11), (204, 24), (216, far-8), (290, far-8)])
        half = smooth_keys([(0, 17), (30, 14), (60, 10), (120, 7), (190, 13), (216, 20), (250, 14), (290, 14)])
        rows = []
        for z in z_rows:
            t = twist(z)
            t = t*t*(3-2*t)
            bearing = math.radians(bottom+(high-bottom)*t)
            er, et = np.array((math.cos(bearing), math.sin(bearing))), np.array((-math.sin(bearing), math.cos(bearing)))
            r0, r1 = float(inner(z)), float(outer(z))
            ring = []
            for k in range(section):
                a = k*math.tau/section
                ca, sa = math.cos(a), math.sin(a)
                ring.append(er*((r0+r1)/2+(r1-r0)/2*math.copysign(abs(ca)**.55, ca))+et*float(half(z))*math.copysign(abs(sa)**.55, sa))
            rows.append((np.array(ring), z))
        loft('rib', rows, caps=(False, True), smooth=60)
    # The arch over the door springs from the two front ribs.
    reach_arch = math.radians(35)
    arch_band = ring_surface(np.array(arc(78, -125, -55, 24)), np.array(arc(46, -125, -55, 24)), 0, 56, reach_arch)
    opening = [(-27, -2), (-27, 10), (-22, 26), (-12, 38), (0, 42), (12, 38), (22, 26), (27, 10), (27, -2)]
    wrapped_skin('door arch', arch_band, lambda a: np.maximum(54*np.sqrt(np.maximum(1-(np.degrees(a)/35)**2, 0)), 2), [opening], reach=reach_arch, depth=24, lip=.7, keep_back=True)
    # The crown: first floor's edge, glass, the second floor's edge, glass and a thick rim round the roof garden.
    slab_edge('crown first edge', edge, 217, rise=5, nose=1.2, under=7, drop=1, floor_to=offset(edge, -2.6))
    slab_edge('crown second edge', offset(edge, -.6), 234.5, rise=4, nose=.8, under=6, drop=1, floor_to=offset(edge, -2.6))
    everywhere = range(n)
    behind_rib = indices_between(edge, axis, 94, 86)
    glazing('crown glass low', offset(edge, -2.4), 222, 234.2, behind_rib, rng, bay=4.6, warm=.5, lit=True)
    glazing('crown glass high', offset(edge, -2.4), 238.5, 252.5, behind_rib, rng, bay=4.6, warm=.5, lit=True)
    rim_rows = [(offset(edge, -2.4), 252), (offset(edge, 1.2), 254), (offset(edge, 2), 258), (offset(edge, 1.2), rim_top-1.6), (offset(edge, -.6), rim_top), (offset(edge, -5), rim_top+.3),
                (offset(edge, -9), rim_top-1.4), (offset(edge, -9.6), np.full(n, 264.0))]
    loft('crown rim', rim_rows if LOD == 0 else [rim_rows[k] for k in (0, 2, 4, 5, 7)] if LOD == 1 else [rim_rows[k] for k in (0, 2, 5, 7)])
    floor = 264.6
    bed = offset(edge, -9.2)
    cap('crown garden', bed, floor, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in bed])
    loft('crown walk', [(edge*.72, floor+.25), (edge*.6, floor+.25)], PAVE, DECK_TINT, stone_uv=False, uvs=[(float(q[0])/30, float(q[1])/30) for ring in (edge*.72, edge*.6) for q in ring])
    skylight('crown dome', 0, 0, floor+.3, 22, 30, rise=19)
    keep_path(edge*.66, 4, floor)
    for at in (-154, -26, 90):
        r = reach(at)
        keep_clear(r*math.cos(math.radians(at)), r*math.sin(math.radians(at)), 20, 20, floor)
    crown_bed = edge*(1-np.maximum(.16, 12/radii))[:, None]
    clear_of_rim = [i for i in everywhere if np.hypot(*(edge-crown_bed[i]).T).min() > 11]
    plant_band('crown plants', crown_bed, floor, clear_of_rim, rng, spacing=3, size=(6, 10.5), flowers=.16, deep=.8)
    plant_band('crown plants inner', edge*.5, floor, everywhere, rng, spacing=3.6, size=(5, 8.5), flowers=.16, deep=1.2)
    for at in (30, 150, -90, 18, 162, -75):
        r = reach(at)*.85
        tree(r*math.cos(math.radians(at)), r*math.sin(math.radians(at)), floor, rng.uniform(13, 17), rng.uniform(9, 11), rng)
    flush_cards()
    return edge, pod


def tower_volumes(edge, pod):
    around = np.linspace(-math.pi, math.pi, 48, endpoint=False)
    # The game draws a floor at every level inside the volumes: these stay in the glass. The thin disc gives the outer hexes their roof.
    volume_prism('building_volume podium', offset(pod, -6), 0, 35)
    volume_prism('building_volume podium roof', np.c_[84*np.cos(around), 84*np.sin(around)], 35, 36)
    volume_prism('building_volume stem', np.c_[11*np.cos(around), 11*np.sin(around)], 36, 216)
    volume_prism('building_volume crown', offset(edge, -7), 216, 270)


# Px to units on a reference's top panel.
def from_top(points, origin, scale, shift=(0, 0)):
    return [((px-origin[0])*scale+shift[0], (origin[1]-py)*scale+shift[1]) for px, py in points]


def garden_habitat(rng):
    """Sheet 'Garden Habitat', 2 x 2 hexes: a stepped planted front curling round a leaning shell with an oval louvre."""
    origin, scale, shift = (395, 745), 160/420, (28, -46)
    tp = lambda points: from_top(points, origin, scale, shift)
    centre = np.array(tp([(450, 715)])[0])
    n = SAMPLES[LOD]
    plaza = polar_ring(tp([(395, 527), (476, 540), (542, 603), (580, 675), (606, 755), (621, 830), (608, 908), (553, 955), (470, 968),
                           (320, 968), (248, 947), (200, 905), (185, 830), (200, 760), (225, 680), (262, 610), (320, 545)]), centre, n)
    base = polar_ring(tp([(398, 556), (462, 568), (515, 620), (552, 690), (574, 770), (586, 835), (572, 893), (528, 925), (460, 943),
                          (330, 943), (262, 925), (222, 893), (207, 830), (220, 770), (244, 690), (280, 620), (332, 568)]), centre, n)
    top = polar_ring(tp([(427, 580), (477, 600), (520, 660), (547, 720), (560, 787), (552, 820), (505, 807), (477, 792), (430, 797), (363, 797),
                         (323, 760), (317, 720), (330, 680), (363, 627), (390, 593)]), centre, n)
    garden = polar_ring(tp([(433, 613), (470, 630), (490, 680), (493, 720), (477, 753), (437, 783), (370, 783), (333, 753), (327, 720), (343, 687),
                            (380, 653), (403, 623)]), centre, n)
    decks = [36, 54, 72, 90, 108, 126]
    fraction = lambda k: (k/(len(decks)-1))**.92
    ring_at = [base+(top-base)*fraction(k) for k in range(len(decks))]
    plinth(plaza)
    # The rear shell wraps the building from the south-east tip counter-clockwise past north to the north-west.
    sector_start, sector_end = -58, 118
    shell_ids = indices_between(base, centre, sector_start, sector_end)
    ids = indices_between(base, centre, sector_end-2, sector_start+2)
    arc = indices_between(base, centre, sector_end-5, sector_start+5)
    angle = np.degrees(np.arctan2(base[:, 1]-centre[1], base[:, 0]-centre[0])) % 360
    to_east = np.minimum((angle-(sector_start % 360)) % 360, (sector_start-angle) % 360)
    to_west = np.minimum((angle-sector_end) % 360, (sector_end-angle) % 360)
    ease = lambda t: np.clip(t, 0, 1)**2*(3-2*np.clip(t, 0, 1))
    sweep = 11*ease(1-to_east/70)+4*ease(1-to_west/50)
    level = lambda k: decks[k]+sweep*(k < len(decks)-1)
    # Ground storey: elephant feet, widest at the ground, narrowing to a waist and flaring to the first deck, which it follows.
    foot_rows = [(offset(base, -5), 1.4), (offset(base, -14), 14), (offset(base, -11), 25), (offset(base, -3), 31), (base, 34.5), (base, 34.5+sweep)]
    lower = loft('ground storey', foot_rows if LOD < 2 else foot_rows[0:1]+foot_rows[4:], caps=(True, True))
    front_y = float(base[:, 1].min())
    arches = [(shift[0]-44, 24, 23), (shift[0], 39, 28.5), (shift[0]+44, 24, 23)]
    floor = 1.4
    for x, width, height in arches:
        here = float(base[np.abs(base[:, 0]-x) < 8, 1].min())
        back = here+(16 if x == shift[0] else 26)
        if LOD < 2:
            carve(lower, *prism(arch_outline(width, height, (x, here-8), floor), (0, 1, 0), back-here+8.5))
        else:
            back = here-.3
        pane = arch_outline(width-.6, height-.3, (x, back), floor, sides=12 if LOD == 0 else 6)[2:]
        corners = pane+[(x-width/2+.3, back, floor), (x+width/2-.3, back, floor)]
        lobby = add_mesh('lobby glass', GLASS, LOBBY, corners, [tuple(range(len(corners)))], smooth=None, stone_uv=False,
                         uvs=[(c[0]/18, c[2]/18) for c in corners])
        shared.emissive(lobby, NIGHT, night=True)
        if LOD == 0:
            for k in range(1, 6):
                mx = x-width/2+k*width/6
                head = floor+height*.45+height*.55*math.sqrt(max(0, 1-((mx-x)/(width/2))**2))
                block('lobby mullion', (mx, back-.2, (floor+head)/2), (.5, .5, head-floor))
            block('lobby transom', (x, back-.2, floor+height*.45), (width-1, .5, .5))
    if LOD == 0:
        door_pair(shift[0], front_y+15.8, floor)
    if LOD < 2:
        # The arches' raised frames lie on the carved wall, from the ground up.
        bpy.context.view_layer.update()
        wall_bvh = BVHTree.FromObject(lower, bpy.context.evaluated_depsgraph_get())

        frame = []
        for a in np.linspace(0, math.pi, 26 if LOD == 0 else 10):
            fx, fz = shift[0]+23*math.cos(a), floor+32*math.sin(a)
            hit = wall_bvh.ray_cast(Vector((fx, front_y-80, fz)), Vector((0, 1, 0)), 200)[0]
            frame.append((fx, hit.y+.6 if hit is not None else frame[-1][1] if frame else front_y+12, fz))
        tube('great arch', frame, 3.1, STONE, STONE_TINT, sides=8 if LOD == 0 else 4, smooth=70)
    # Decks: rounded edge, a planter of varying width, a walkway behind it and the storey's glass under the deck above. Each sweeps
    # up as it nears the shell, the south-east end most, which is the sheet's strongest line.
    for k in range(1, len(decks)):
        for i in (shell_ids[0], shell_ids[-1]):
            keep_clear(ring_at[k][i, 0], ring_at[k][i, 1], 9, 9, decks[k])
    for k in range(len(decks)-1):
        terrace(f'deck {k}', ring_at[k], ring_at[k+1], level(k), level(k+1), arc, ids, rng, phase=k*1.7, hang=.14 if k < 4 else .05, line=True,
                planted=indices_between(base, centre, sector_end+7, sector_start-7))
    slab_edge(f'deck {len(decks)-1} edge', ring_at[-1], level(len(decks)-1), arc)
    # The rear shell: one surface on the decks' own rings. Over the south-east and east it is a solid lobe whose face leans back;
    # round the north it is a rim. Its top is a hood peaking over the north-east, with a rounded crest.
    span = len(shell_ids)
    bearing = np.degrees(np.arctan2(base[shell_ids, 1]-centre[1], base[shell_ids, 0]-centre[0]))
    radius = lambda ring: np.hypot(*(ring-centre).T)[shell_ids]
    thick = np.maximum(radius(top)-radius(garden), 3)
    ends = ease(np.minimum(bearing-sector_start, sector_end-bearing)/30)
    hood = decks[-1]+3+21*np.exp(-((bearing-40)/70)**2)*ends

    def surface(t):
        """The shell's outer points at a step between base and top, and the direction from them to the centre."""
        ring = (base+(top-base)*t)[shell_ids]
        inward = centre-ring
        inward /= np.hypot(*inward.T)[:, None]
        return ring-inward*1.3, inward
    def band(outer, inner):
        """The shell's plan at one height: out along its face, round a rounded nose, back along its inner side, round the other nose."""
        ahead = outer[-1]-outer[-2]
        behind = outer[0]-outer[1]
        ahead, behind = ahead/np.hypot(*ahead), behind/np.hypot(*behind)
        steps = (.25, .5, .75)
        end = [outer[-1]+(inner[-1]-outer[-1])*t+ahead*12*math.sin(t*math.pi) for t in steps]
        start = [inner[0]+(outer[0]-inner[0])*t+behind*12*math.sin(t*math.pi) for t in steps]
        return np.r_[outer, end, inner[::-1], start]
    level_of = lambda z: np.r_[z, [z[-1]]*3, z[::-1], [z[0]]*3]
    rows = []
    for t, z in [(0, 1.4), (0, 36)]+[(fraction(k), 36+18*k) for k in range(1, 6)]:
        part, inward = surface(t)
        rows.append((band(part, part+inward*thick[:, None]), level_of(np.full(span, float(z)))))
    for inset, drop in ((0, 6), (1.4, 2.4), (3.0, 0)):
        part, inward = surface(1)
        step = inward*(inset*np.minimum(1, thick/7.5))[:, None]
        rows.append((band(part+step, part+inward*thick[:, None]-step), level_of(np.maximum(hood-drop, 126+(hood-126)*(1-drop/6)))))
    if LOD:
        rows = rows[::2]+rows[-1:]
    spine = part+inward*thick[:, None]/2
    rows.append((np.r_[spine, [spine[-1]]*3, spine[::-1], [spine[0]]*3], level_of(hood)))
    shell = loft('rear shell', rows, caps=(True, False), smooth=38)
    # The tall oval louvre on the lobe's leaning face, turned to show from the front and the side.
    near = int(np.argmin(np.abs(bearing+22)))
    t = ((80-36)/18/5)**.92
    at = surface(t)[0][near]
    oval_c = Vector((at[0], at[1], 80))
    oval_n = Vector((.95, -.27, .17)).normalized()
    oval_w, oval_h = 45, 92
    louvre('east louvre', shell, tuple(oval_c), tuple(oval_n), oval_w, oval_h)
    # The roof: a low wall on the open side, a pale sand floor, a winding path, the dome, plants and small trees.
    roof = decks[-1]
    loft('roof rim', [(top[arc], roof+1.6), (offset(top, -.9)[arc], roof+2.7), (offset(garden, 1.1)[arc], roof+2.7), (garden[arc], roof+1.6)], closed=False)
    cap('roof floor', offset(garden, 1.8), roof+1.6, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in offset(garden, 1.8)])
    dome = tp([(447, 687)])[0]
    skylight('roof dome', dome[0], dome[1], roof+1.7, 10.7, 14.3)
    pts = line_through(tp([(360, 712), (378, 700), (398, 716), (416, 744), (436, 760), (420, 780), (396, 776)]), {0: 5, 1: 3, 2: 2}[LOD])
    keep_path(pts, 4.5, roof+1.6)
    if LOD < 2:
        left, right = [], []
        for i in range(len(pts)):
            d = pts[min(i+1, len(pts)-1)]-pts[max(i-1, 0)]
            d = d/np.hypot(*d)
            normal = np.array((-d[1], d[0]))
            left.append(pts[i]+normal*5)
            right.append(pts[i]-normal*5)
        m = len(pts)
        for side in (left, right):
            for i in range(1, m):
                if np.dot(side[i]-side[i-1], pts[min(i+1, m-1)]-pts[max(i-1, 0)]) <= 0:
                    side[i] = side[i-1]
        verts = [(*q, roof+1.8) for q in right]+[(*q, roof+1.8) for q in left]
        add_mesh('roof path', PAVE, DECK_TINT, verts, [(i, i+1, m+i+1, m+i) for i in range(m-1)], smooth=None)
    plant_band('roof plants', offset(garden, -3), roof+1.6, range(len(garden)), rng, spacing=3.6, size=(4.5, 8))
    west = [i for i in range(len(garden)) if garden[i, 0] < float(dome[0])-6]
    plant_band('roof plants inner', offset(garden, -9), roof+1.6, west, rng, spacing=5.5, size=(5, 8))
    for corner in tp([(377, 683), (368, 757), (470, 733), (425, 640)]):
        tree(corner[0], corner[1], roof+1.6, rng.uniform(12, 16), rng.uniform(9, 11), rng)
    # Low beds across the whole front but the entrance, and round the plinth; trees at the shoulders.
    bed = offset(base, -1)
    along_shell = set(indices_between(base, centre, sector_start-18, sector_end+12))
    plant_band('ground plants', bed, floor, [i for i in range(len(base)) if i not in along_shell and (abs(base[i, 0]-shift[0]) > 27 or base[i, 1] > front_y+16)], rng, spacing=3, size=(4, 7.5), deep=1.6)
    plant_band('shell bed', offset(base, 5.5), floor, sorted(along_shell, key=lambda i: (angle[i]-(sector_start-18)) % 360), rng, spacing=2.8, size=(5.5, 9.5), flowers=.1, deep=1.2)
    if LOD == 0:
        rocks([q for q in offset(base, 5)[::9] if abs(q[0]-shift[0]) > 28 or q[1] > front_y+16], floor, rng)
    for at_tree in tp([(600, 800), (603, 862), (572, 925), (212, 915), (198, 800)]):
        tree(at_tree[0], at_tree[1], floor, rng.uniform(11, 15), rng.uniform(8, 11), rng)
    flush_cards()
    return ring_at, decks


def garden_volumes(ring_at, decks):
    volume_prism('building_volume ground', offset(ring_at[0], -32), 0, 35)
    volume_prism('building_volume first deck', offset(ring_at[0], -4), 35, 36)
    for k in range(1, len(decks)):
        volume_prism(f'building_volume terrace {k}', offset(ring_at[k], -4), decks[k-1], decks[k])


def rounded_rect(x0, x1, y0, y1, radius, n=None):
    """A rounded rectangle, counter-clockwise, at even spacing."""
    n = n or SAMPLES[LOD]
    corners = ((x1-radius, y1-radius, 0), (x0+radius, y1-radius, 90), (x0+radius, y0+radius, 180), (x1-radius, y0+radius, 270))
    outline = [(cx+radius*math.cos(math.radians(a+t)), cy+radius*math.sin(math.radians(a+t))) for cx, cy, a in corners for t in np.linspace(0, 90, 24)]
    outline = np.array(outline)
    step = np.hypot(*(np.roll(outline, -1, 0)-outline).T)
    run = np.r_[0, np.cumsum(step)]
    wanted = np.linspace(0, run[-1], n, endpoint=False)
    loop = np.r_[outline, outline[:1]]
    return np.c_[np.interp(wanted, run, loop[:, 0]), np.interp(wanted, run, loop[:, 1])]


def oval_louvre_x(name, wall, x, y, z, length, height, slat=3.0):
    """A long oval of level slats let into a wall that faces +X: the recess is carved, the slats sit in it. Far away, a flat oval in their mean tone."""
    sides = {0: 32, 1: 14, 2: 10}[LOD]
    ring = lambda at: [(at, y+length/2*math.cos(a), z+height/2*math.sin(a)) for a in np.linspace(0, math.tau, sides, endpoint=False)]
    if LOD < 2:
        carve(wall, *prism(ring(x-4), (1, 0, 0), 8))
    add_mesh(name+' back', FLAT, LOUVRE_BACK, ring(x+.15 if LOD == 2 else x-2.6), [tuple(range(sides))], smooth=None, stone_uv=False, uvs=[(0, 0)]*sides)
    lip, rear = (x+.4, x+.4) if LOD == 2 else (x-1.2, x-2.1)  # Uncarved at the farthest level: flat on the wall.
    count = int(height/slat)
    for k in range(1, count):
        h = -height/2+k*height/count
        half = length/2*math.sqrt(max(0, 1-(2*h/height)**2))
        if half < 1.5:
            continue
        verts = [(lip, y-half, z+h-.25), (lip, y+half, z+h-.25), (rear, y+half, z+h+.25), (rear, y-half, z+h+.25)]
        add_mesh(name+' slat', STONE, SLAT, verts, [(0, 1, 2, 3)], smooth=None)
    if LOD < 2:
        tube(name+' frame', [(q[0]+.35, q[1], q[2]) for q in ring(x)], 1.0, STONE, STONE_TINT, sides=5 if LOD == 0 else 3, closed=True, smooth=70)


def arch_section(cx, half, crown, spring, sides):
    """A vault's cross-section, left foot to right foot, from the ground: straight walls under a half ellipse."""
    pts = [(cx-half, 0.0)]
    for k in range(sides+1):
        a = math.pi-k*math.pi/sides
        pts.append((cx+half*math.cos(a), spring+(crown-spring)*math.sin(a)))
    pts.append((cx+half, 0.0))
    return pts


def roof_section(cx, half, crown, left, right, sides):
    """A hall's cross-section, left foot to right foot: walls under a shallow curve that drops by left and right at its edges."""
    pts = [(cx-half, 0.0)]
    for k in range(sides+1):
        a = math.pi-k*math.pi/sides
        pts.append((cx+half*math.cos(a), crown-(left if a > math.pi/2 else right)*(1-math.sin(a))))
    pts.append((cx+half, 0.0))
    return pts


def fabrication_works(rng):
    """Sheet 'Fabrication Works', 3 x 3 hexes: three vaulted halls with loading doors, a wavy east wall, a rounded office wing."""
    origin, scale, shift = (372, 720), 208/445, (0, 12)
    px = lambda x, y: ((x-origin[0])*scale+shift[0], (origin[1]-y)*scale+shift[1])
    x0, y1 = px(150, 478)
    x1, y0 = px(595, 962)
    plaza = rounded_rect(x0, x1, y0, y1, 26)
    plinth(plaza)
    front, rear = px(0, 905)[1]+7.4, px(0, 555)[1]
    nose = front-7.4
    back = px(0, 500)[1]
    centres = [px(235, 0)[0], px(360, 0)[0], px(480, 0)[0]]
    half, spring, valley = 25.5, 34, 5.5
    wy1_px = px(0, 735)[1]
    sides = {0: 16, 1: 8, 2: 6}[LOD]
    rows = {0: 14, 1: 9, 2: 6}[LOD]
    wave = lambda t: t*t*(3-2*t)
    curve = lambda t: 45+13*wave(min(1, max(0, t)/.42))
    shares = [i/rows for i in range(rows+1)] if LOD == 0 else sorted({*np.linspace(0, .42, 7 if LOD == 1 else 4).tolist(), (wy1_px-30-rear)/(front-rear), 1.0})
    profile = [(rear+t*(front-rear), curve(t)+{0: 0, 1: .15, 2: .4}[LOD]) for t in shares]
    for c in centres:
        # The barrel, with a soft shoulder over its front, closed at the back.
        stations = [(y, crown) for y, crown in profile]
        stations = stations+([(nose+3.6, 57.4), (nose+1.4, 56.2), (nose, 54.2)] if LOD == 0 else [(nose+2.4, 57.2), (nose, 54.6)])
        shoulder = lambda y: valley+13.5*min(1, max(0, (y-rear)/(nose-rear))) if c == centres[0] else valley
        loops = [roof_section(c, half, crown, shoulder(y), valley, sides) for y, crown in stations]
        m = len(loops[0])
        verts = [(x, stations[r][0], z) for r, loop in enumerate(loops) for x, z in loop]
        faces = [(r*m+i, (r+1)*m+i, (r+1)*m+i+1, r*m+i+1) for r in range(len(loops)-1) for i in range(m-1)]
        add_mesh('vault', STONE, STONE_TINT, verts, faces, smooth=70)
        add_mesh('vault back', STONE, STONE_TINT, [(x, rear, z) for x, z in loops[0]], [tuple(range(m))], smooth=None)
        y_f = stations[-1][0]
        crown = stations[-1][1]
        # The arch's deep frame: a ring from the barrel's end back to the recessed wall, then the wall.
        outer = loops[-1]
        inner = arch_section(c, half-5.5, crown-6, spring, sides)
        wall_y = y_f+6.0
        verts = [(x, y_f, z) for x, z in outer]+[(x, y_f+1.6, z) for x, z in arch_section(c, half-2.4, crown-2.6, spring, sides)]+[(x, wall_y, z) for x, z in inner]
        faces = [(i*m+k, (i+1)*m+k, (i+1)*m+k+1, i*m+k+1) for i in range(2) for k in range(m-1)]
        add_mesh('vault arch', STONE, STONE_TINT, verts, faces, smooth=50)
        if LOD < 2:
            tube('vault rim', [(x, y_f+.2, z) for x, z in arch_section(c, half-2.6, crown-2.8, spring, sides)][1:-1], 1.6, STONE, STONE_TINT, sides=6 if LOD == 0 else 4, smooth=70)
        add_mesh('vault end wall', STONE, STONE_SHADE, [(x, wall_y, z) for x, z in inner], [tuple(range(m))[::-1]], smooth=None)
        # The loading door and the half-oval louvre over it. Door 30 x 23 units: 10 x 7.7 m.
        door_z = 23.0
        front_y = wall_y-.2
        block('loading door', (c, front_y-.2, 1.4+door_z/2), (30, .5, door_z), FRAME, (.36, .39, .31))
        block('loading door frame', (c, front_y-.1, 1.4+door_z+.5), (31.6, .7, 1.2), FRAME, FRAME_TINT)
        if LOD == 0:
            for side in (-1, 1):
                block('loading door jamb', (c+side*15.5, front_y-.1, 1.4+door_z/2), (.9, .7, door_z), FRAME, FRAME_TINT)
            for k in range(1, 6):
                block('door panel joint', (c, front_y-.5, 1.4+k*door_z/6), (29.6, .1, .22), FRAME, (.24, .26, .20))
            for k in range(4):
                block('door window', (c-8.1+k*5.4, front_y-.5, 1.4+door_z*.72), (3.6, .12, 1.5), GLASS, GLASS_TINT)
        low = 1.4+door_z+1.4
        top_z = crown-7.4
        width = 2*(half-7)
        span = top_z-low
        slats = 8
        for k in range(slats):
            h = (k+.5)/slats
            w = width*math.sqrt(max(0, 1-h*h))
            if LOD == 2:
                add_mesh('louvre slat', STONE, SLAT, [(c-w/2, front_y-.3, low+h*span-.2), (c+w/2, front_y-.3, low+h*span-.2), (c+w/2, front_y-.3, low+h*span+.2), (c-w/2, front_y-.3, low+h*span+.2)], [(0, 1, 2, 3)], smooth=None)
            else:
                block('louvre slat', (c, front_y-.3, low+h*span), (w, .9, .4), STONE, SLAT)
        lens = [(c+width/2*math.cos(a), front_y-.1, low+span*math.sin(a)) for a in np.linspace(0, math.pi, 14 if LOD < 2 else 8)]
        add_mesh('louvre back', FLAT, LOUVRE_BACK, lens, [tuple(range(len(lens)))], smooth=None, stone_uv=False, uvs=[(0, 0)]*len(lens))
    # The glazed strips in the valleys: over the roof and down between the arch frames at the front.
    strip_half = 4.0
    for k in range(2):
        cx = (centres[k]+centres[k+1])/2
        stations = [(y, crown-valley) for y, crown in profile]
        stations.append((nose+.8, 49))
        section = [(-strip_half, -1.2), (-strip_half*.5, .8), (strip_half*.5, .8), (strip_half, -1.2)]
        m = len(section)
        verts = [(cx+sx, y, z+sz) for y, z in stations for sx, sz in section]
        faces = [(r*m+i, (r+1)*m+i, (r+1)*m+i+1, r*m+i+1) for r in range(len(stations)-1) for i in range(m-1)]
        obj = add_mesh('roof glazing', GLASS, GLASS_TINT, verts, faces, smooth=None, stone_uv=False, uvs=[(v[0]/18, v[1]/18) for v in verts])
        shared.emissive(obj, NIGHT_GLASS, night=True)
        pane_y = nose+.8
        top = 49.5
        window = [(cx-strip_half, pane_y, 36), (cx+strip_half, pane_y, 36), (cx+strip_half, pane_y, top-1.4), (cx, pane_y, top), (cx-strip_half, pane_y, top-1.4)]
        obj = add_mesh('valley window', GLASS, GLASS_TINT, window, [(0, 1, 2, 3, 4)], smooth=None, stone_uv=False, uvs=[(v[0]/18, v[2]/18) for v in window])
        shared.emissive(obj, NIGHT_GLASS, night=True)
        add_mesh('valley wall', STONE, STONE_TINT, [(cx-strip_half, nose, 1.4), (cx+strip_half, nose, 1.4), (cx+strip_half, nose, 36), (cx-strip_half, nose, 36)], [(0, 1, 2, 3)], smooth=None)
        if LOD < 2:
            for t in range(1, 8 if LOD == 0 else 3):
                y = rear+t*(front-rear)/(8 if LOD == 0 else 3)
                c = 45+13*wave(min(1, (y-rear)/(front-rear)/.42))-valley
                block('roof glazing bar', (cx, y, c+.95), (strip_half*2, .35, .3), FRAME, FRAME_TINT)
            for t in (40, 44):
                block('valley window bar', (cx, pane_y-.2, t), (strip_half*2, .3, .3), FRAME, FRAME_TINT)
            block('valley window mullion', (cx, pane_y-.2, 42.5), (.3, .3, 13), FRAME, FRAME_TINT)
    # The east wall: a long surface with a wavy top, a band of glass under it and two long oval louvres.
    east1 = px(568, 0)[0]
    east0 = east1-3.5
    stations = np.linspace(back, px(0, 915)[1]+30, {0: 36, 1: 16, 2: 7}[LOD])
    strip = [(x, y, crown-valley) for y, crown in profile if y >= wy1_px-(front-rear)/rows-30 for x in (centres[2]+half, east0)]
    faces = [(2*r, 2*r+2, 2*r+3, 2*r+1) for r in range(len(strip)//2-1)]
    obj = add_mesh('east roof glazing', GLASS, GLASS_TINT, strip, faces, smooth=None, stone_uv=False, uvs=[(v[0]/18, v[1]/18) for v in strip])
    shared.emissive(obj, NIGHT_GLASS, night=True)
    def wall_top(y):
        return 60-10*wave(min(1, max(0, (y-y0-135)/55)))
    verts, faces = [], []
    for y in stations:
        top = wall_top(y)
        verts += [(east1-3.5, y, 0), (east1, y, 0), (east1, y, top-2), (east1-1.2, y, top), (east1-3.5, y, top)]
    n = 5
    for r in range(len(stations)-1):
        for i in range(n):
            j = (i+1) % n
            faces.append((r*n+i, r*n+j, (r+1)*n+j, (r+1)*n+i))
    faces.append(tuple(range(n-1, -1, -1)))
    faces.append(tuple((len(stations)-1)*n+i for i in range(n)))
    wall = add_mesh('east wall', STONE, STONE_TINT, verts, faces, smooth=None)
    oval_louvre_x('east louvre near', wall, east1, y0+99, 28.5, 55, 28)
    oval_louvre_x('east louvre far', wall, east1, y0+179, 24.5, 52, 26)
    band = [(east1+.15, y, wall_top(y)-9.0) for y in stations]
    band_top = [(v[0], v[1], wall_top(v[1])-4.2) for v in band]
    m = len(band)
    obj = add_mesh('clerestory', GLASS, GLASS_TINT, band+band_top, [(m+i, m+i+1, i+1, i) for i in range(m-1)], smooth=None, stone_uv=False,
                   uvs=[(v[1]/18, v[2]/18) for v in band+band_top])
    shared.emissive(obj, NIGHT_GLASS, night=True)
    if LOD == 0:
        tube('clerestory sill', [(v[0]+.1, v[1], v[2]-.1) for v in band], .3, FRAME, FRAME_TINT, sides=3)
        tube('clerestory head', [(v[0]+.1, v[1], v[2]+.1) for v in band_top], .3, FRAME, FRAME_TINT, sides=3)
        for y in stations[::2]:
            top = wall_top(y)
            block('clerestory mullion', (east1+.3, y, top-6.6), (.3, .3, 4.8), FRAME, FRAME_TINT)
    # The west wall and the plant deck behind the vaults.
    west = centres[0]-half
    deck_z = 42.0
    add_mesh('west wall', STONE, STONE_TINT, [(west, back, 0), (west, rear-.6, 0), (west, rear-.6, deck_z+1.2), (west, back, deck_z+1.2)], [(0, 1, 2, 3)], smooth=None)
    deck = [(west, back), (east0, back), (east0, rear-.6), (west, rear-.6)]
    add_mesh('plant deck', STONE, STONE_SHADE, [(x, y, deck_z) for x, y in deck], [(3, 2, 1, 0)], smooth=None)
    add_mesh('rear wall', STONE, STONE_TINT, [(west, back, 0), (east1, back, 0), (east1, back, deck_z+.5), (west, back, deck_z+.5)], [(3, 2, 1, 0)], smooth=None)
    add_mesh('roof end wall', STONE, STONE_TINT, [(west, rear-.6, 0), (east0, rear-.6, 0), (east0, rear-.6, deck_z+1.2), (west, rear-.6, deck_z+1.2)], [(0, 1, 2, 3)], smooth=None)
    add_mesh('roof end wall', STONE, STONE_TINT, [(west, rear-.6, deck_z), (east0, rear-.6, deck_z), (east0, rear-.6, deck_z+1.2), (west, rear-.6, deck_z+1.2)], [(3, 2, 1, 0)], smooth=None)
    block('deck parapet', ((west+east0)/2, back, deck_z+1.2), (east0-west, 1.2, 2.4), STONE, STONE_TINT)
    block('deck parapet', (west, (back+rear)/2, deck_z+1.2), (1.2, back-rear, 2.4), STONE, STONE_TINT)
    for px_x, wide, tall in ((248, 28, 10), (472, 26, 10)):
        cx = px(px_x, 0)[0]
        cy = back+(rear-back)*.52
        block('plant unit', (cx, cy, deck_z+tall/2), (wide, 18, tall), STONE, STONE_SHADE)
        block('plant unit hood', (cx, cy, deck_z+tall+.6), (wide-3, 15, 1.2), STONE, (.80, .79, .77))
        if LOD == 0:
            for k in range(5):
                block('plant unit slat', (cx, cy-9.1, deck_z+1.5+k*1.6), (wide-3, .3, .7), FRAME, FRAME_TINT)
    cx = px(355, 0)[0]
    block('plant box', (cx, back+(rear-back)*.52, deck_z+3.7), (44, 19, 7.4), STONE, STONE_SHADE)
    block('plant grille', (cx, back+(rear-back)*.52, 49.4), (44, 19, 1.0), 'structures/common/grille', (.66, .66, .64))
    cx = px(528, 0)[0]
    block('plant fan', (cx, back+(rear-back)*.52, deck_z+5), (14, 14, 10), STONE, STONE_SHADE)
    # The office wing on the front east corner: a rounded tongue of three storeys, glass round its south end.
    wx0, wx1 = px(488, 0)[0], px(570, 0)[0]
    wy0, wy1 = px(0, 915)[1], px(0, 735)[1]
    tongue = rounded_rect(wx0, wx1, wy0, wy1, 14.5)
    cen = np.array(((wx0+wx1)/2, wy0+14))
    glass_ids = [i for i in range(len(tongue)) if tongue[i, 1] < wy0+46]
    glass_ids.sort(key=lambda i: (math.degrees(math.atan2(tongue[i, 1]-cen[1], tongue[i, 0]-cen[0]))+360-90) % 360)
    glass_ring = offset(tongue, -2.2)
    for k, z in enumerate((1.4, 18, 36)):
        glazing(f'wing storey {k}', glass_ring, z+.4, z+(16.4 if k == 0 else 16), glass_ids, rng, bay=4.2, warm=.3)
    solid = [i for i in range(len(tongue)) if tongue[i, 1] >= wy0+42 and tongue[i, 0] < cen[0]]
    solid.sort(key=lambda i: tongue[i, 1])
    part = tongue[solid]
    loft('wing wall', [(part, 0), (part, 54)], closed=False, smooth=40, flip=True)
    for k, z in enumerate((18, 36)):
        slab_edge(f'wing floor {k}', offset(tongue, 1.8), z, [i for i in glass_ids if tongue[i, 1] < wy0+28 or tongue[i, 0] < cen[0]], rise=2.2, under=4, floor_to=offset(tongue, -2.4))
        ring = offset(tongue, -.6)
        plant_band(f'wing plants {k}', ring, z+2.0, [i for i in glass_ids if tongue[i, 0] > wx0+8 and tongue[i, 1] < wy0+22], rng, spacing=4, size=(3.4, 6), hang=.3, deep=.6, rim=3.5)
    slab_edge('wing roof', offset(tongue, 1.4), 54, None, rise=3.2, under=6)
    cap('wing roof', offset(tongue, -.1), 56.8)
    patch = rounded_rect(wx0+2.5, wx1-2.5, wy0+2.5, wy0+26, 11, {0: 40, 1: 20, 2: 12}[LOD])
    cap('wing roof planter', patch, 56.9, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in patch])
    plant_band('wing roof plants', patch, 56.9, [i for i in range(len(patch)) if patch[i, 0] > wx0+9], rng, spacing=2.6, size=(5, 8.5), flowers=.1, deep=1.6)
    for at in ((wx0+11, wy0+10),):
        tree(at[0], at[1], 56.9, rng.uniform(9, 11), rng.uniform(8, 10), rng)
    # The wing's entrance: a glazed arch in the ground storey, with doors at their true size.
    door_x = (wx0+wx1)/2
    if LOD == 0:
        door_pair(door_x, wy0-.2, 1.4)
    # Beds, bollards and trees on the plinth.
    edge = offset(plaza, -7)
    east_bed = [i for i in range(len(edge)) if edge[i, 0] > east1+2 and edge[i, 1] > wy1-30]
    east_bed.sort(key=lambda i: edge[i, 1])
    plant_band('east bed', edge, 1.4, east_bed, rng, spacing=3.2, size=(4, 8), deep=2)
    west_bed = [i for i in range(len(edge)) if edge[i, 0] < west-1 and edge[i, 1] > nose]
    west_bed.sort(key=lambda i: edge[i, 1])
    plant_band('west bed', edge, 1.4, west_bed, rng, spacing=3.4, size=(4, 8), deep=1.6)
    bay_y = nose-5.5
    for x in (centres[0]-half+2, (centres[0]+centres[1])/2, (centres[1]+centres[2])/2, centres[2]+half+4.5, wx1+2):
        if LOD == 2:
            continue
        box = rounded_rect(x-5.5, x+5.5, bay_y-3, bay_y+3, 1.8, 24 if LOD == 0 else 12)
        soil = offset(box, -.5) if LOD == 0 else box
        loft('door planter', [(box, 1.4), (box, 3.4), (soil, 3.4)] if LOD == 0 else [(box, 1.4), (box, 3.4)])
        cap('door planter soil', soil, 3.4, TURF, TURF_TINT, stone_uv=False, uvs=[(float(q[0])/LAWN_REPEAT, float(q[1])/LAWN_REPEAT) for q in soil])
        for dx in (-3, 0, 3):
            shrub(x+dx, bay_y, 3.1, rng.uniform(3.4, 5.4), rng)
        if x != wx1+2:
            upright(FLOWER, LILAC, x+rng.uniform(-3, 3), bay_y, 4.2, 2.6, 2.6, rng.uniform(0, math.pi))
    if LOD == 0:
        for c in centres:
            for side in (-1, 1):
                tube('bollard', [(c+side*17, nose-2.6, 1.4), (c+side*17, nose-2.6, 7.2)], .45, 'structures/common/safety-yellow', (1, 1, 1), sides=6)
    # The two trees stand in the end planters, on their soil.
    tree(centres[0]-half+2, bay_y, 3.2, 21, 13, rng)
    tree(wx1+2, bay_y, 3.2, 12, 8, rng)
    flush_cards()
    return (west, east1, nose, back, rear, wx0, wx1, wy0, wy1),


def fabrication_volumes(box):
    west, east, front, back, rear, wx0, wx1, wy0, wy1 = box
    # The east wall is 3.5 thick and its oval louvres open through it: the volumes stop inside its inner face.
    inner = east-3.5
    hall = np.array(((inner-.6, front+7), (west+.6, front+7), (west+.6, rear), (inner-.6, rear)))[::-1]
    volume_prism('building_volume halls', hall, 0, 53)
    volume_prism('building_volume roof', np.array(((east, front), (west, front), (west, rear), (east, rear)))[::-1], 53, 54)
    deck = np.array(((inner-.6, rear), (west+.6, rear), (west+.6, back-.6), (inner-.6, back-.6)))[::-1]
    volume_prism('building_volume plant deck', deck, 0, 36)
    volume_prism('building_volume wing', offset(rounded_rect(wx0, wx1, wy0, wy1, 14.5, 48), -3.5), 0, 54)


BUILDINGS = {'garden-habitat': (garden_habitat, garden_volumes, 8),
             'fabrication-works': (fabrication_works, fabrication_volumes, 3),
             'office-tower': (office_tower, office_volumes, 12),
             'tower': (town_tower, tower_volumes, 16),
             'market-pavilion': (market_pavilion, market_volumes, 3),
             'civic-conservatory': (civic_conservatory, civic_volumes, 3),
             'habitat2': (sky_gardens, sky_volumes, 6)}


def build_level(builder, level, seed=7):
    global LOD
    LOD = level
    shared.objects = []
    kept_clear.clear()
    strips_seen.clear()
    rng = random.Random(seed)
    result = builder(rng)
    made = shared.objects
    shared.objects = []
    return made, result


def build(name):
    global LOD
    builder, volumes, levels = BUILDINGS[name]
    full = 'utopia-'+name
    shared.fresh(full)
    shared.role = ''
    models, stats, kept = {}, {}, None
    near_rooms.clear()
    near_plants.clear()
    for level in (0, 1, 2):
        made, result = build_level(builder, level)
        if level:
            # Far levels are chords of the near one's curves. A little larger, they enclose it, and its shadow does not speckle them; no larger than that, or every edge moves at the switch.
            for obj in made:
                obj.data.transform(Matrix.Scale(1.002 if level == 1 else 1.007, 4))
        bpy.context.view_layer.update()
        models[level] = shared.export_model(made, f'{full}-lod{level}', level=level, exact=True)
        stats[level] = {'vertices': sum(len(m['vertices'])//12 for m in models[level]['meshes']),
                        'triangles': sum(len(p['indices'])//3 for m in models[level]['meshes'] for p in m['parts'])}
        assert stats[level]['vertices'] < 65535, stats
        if level:
            for obj in made:
                obj.hide_render = obj.hide_viewport = True
        else:
            kept = result
    shared.volumes = []
    LOD = 0
    volumes(*kept)
    bpy.context.view_layer.update()
    helpers = shared.export_model(shared.volumes, full, helper=True)
    for obj in shared.volumes:
        obj.hide_render = obj.hide_viewport = True
    write_glb(shared.DEST/(full+'.glb'), levels=models, groups={'building_volumes': helpers})
    print('RESULT', full, stats)
    return stats


def sheet(name, folder, width=760, height=500, samples=48, see_through=()):
    """Front, side, top and isometric views in the reference's order, on its pale ground; faces the game culls in
    magenta, but for cutouts and the see_through board materials (glass the culled faces show through)."""
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == 'OPTIX'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.film_transparent = False
    world = scene.world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.74, .70, .68, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    scene.collection.objects.link(sun)
    sun.data.energy = 2.6
    sun.data.angle = math.radians(14)
    sun.rotation_euler = (math.radians(48), 0, math.radians(38))
    shown = [obj for obj in scene.objects if obj.type == 'MESH' and not obj.hide_render]
    # Faces the game culls show magenta. Only cutouts draw both sides.
    for mat in {obj.data.materials[0] for obj in shown if not obj['board_material'].endswith('-cutout')
                and obj['board_material'] not in see_through}:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        surface = nodes['Material Output'].inputs['Surface']
        mix, culled = nodes.new('ShaderNodeMixShader'), nodes.new('ShaderNodeEmission')
        culled.inputs['Color'].default_value = (1, 0, 1, 1)
        links.new(nodes.new('ShaderNodeNewGeometry').outputs['Backfacing'], mix.inputs[0])
        links.new(surface.links[0].from_socket, mix.inputs[1])
        links.new(culled.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], surface)
    corners = np.array([obj.matrix_world @ Vector(c) for obj in shown for c in obj.bound_box])
    camera = bpy.data.objects.new('camera', bpy.data.cameras.new('camera'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = 'ORTHO'
    camera.data.clip_end = 5000
    views = {'front': Vector((0, -1, 0)), 'side': Vector((1, 0, 0)), 'top': Vector((0, 0, 1)), 'iso': Vector((.62, -.62, .46))}
    for view, direction in views.items():
        turn = Matrix.Identity(3) if view == 'top' else direction.to_track_quat('Z', 'Y').to_matrix()
        camera.rotation_euler = turn.to_euler()
        right, up = np.array(turn.col[0]), np.array(turn.col[1])
        across, along = corners@right, corners@up
        mid = Vector(right*(across.min()+across.max())/2+up*(along.min()+along.max())/2)
        camera.location = mid+direction.normalized()*(1500+float(corners@np.array(direction.normalized())@np.ones(len(corners)))/len(corners))
        camera.data.ortho_scale = max(float(across.max()-across.min())*1.08, float(along.max()-along.min())*1.12*width/height)
        scene.render.filepath = str(Path(folder)/f'{view}.png')
        bpy.ops.render.render(write_still=True)
    print('RESULT sheet', folder)


if __name__ == '__main__' and '--' in sys.argv:
    args = sys.argv[sys.argv.index('--')+1:]
    build(args[0])
    if len(args) > 1:
        sheet(args[0], args[1])
