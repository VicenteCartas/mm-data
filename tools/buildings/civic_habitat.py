"""Civic Habitat: build and review in the connected Blender MCP instance.

references/civic-habitat-isometric-guide.png controls shape, proportion and detail language.
Plan coordinates below: X across the building, Y from the slab's front parapet (back is +Y).
Slab 192 x 63 with 15 window storeys (10.125) under a one-storey fascia, roof at 216 (12 levels); two 20 x 36.5 cores
rise to 240; three stepped wings and a rear annex make the podium (18/36/54 helper tops).
Only shared board materials are used. Grime is per-vertex, so stains never repeat with the tile.
"""
import json
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector

import authored_examples as shared
import civic_buildings as civic
from civic_citadel import DARK, ALLOY, GLAZING, WINDOW_LIGHT, display
from hpg_headquarters import mesh
from glb_geometry import linear, write_glb
from weathering import grime
from mm_building_materials.preview import build_preview

NAME = 'civic-habitat'
SCENE = 'Civic habitat'
HERE = Path(__file__).resolve().parent
REFERENCE = HERE/'references/civic-habitat-isometric-guide.png'
CAST, STEEL, PAINT, GRILLE = shared.CONCRETE, shared.STEEL, civic.PAINT, civic.GRILLE
PANELS = 'structures/common/concrete-panels'
SLATS = 'structures/common/louvre'
LOUVRE = (.50, .52, .52)  # Most of the map is dark gap, so this reads as a dark panel with lit slat tops.
PALE_GLASS, DARK_GLASS = 'structures/buildings/tower-glass', civic.GLASS
BUSH = 'terrain/surfaces/grassland-floor'
BUSH_COLOURS = ((.58, .68, .46), (.44, .54, .38))
SOIL = 'terrain/surfaces/biome-soil'
DIM_LIGHT = tuple(display(c) for c in (.028, .019, .005))  # A whole glazed roof, lit from inside.

LEVEL = 18
ROOF = 216
CORE_TOP = 240
PODIUM = 54
STOREYS = 16
STOREY = (ROOF-PODIUM)/STOREYS
BAND = STOREY*.4
PANEL_REPEAT = 2*STOREY  # Panel seams land on the storey lines.
SLAB_Y = 63
LOGGIA = 7
CORES = ((-60, -40), (40, 60))
CORE_Y = (-16, 20.5)
BAYS = ((-96, -60), (-40, 40), (60, 96))
SUN_ROOM_X = 3, 32
SHIFT_Y = -16.5  # Centres the Y -85..118 plan on the placement origin.

TONES = ((.99, .97, .92), (.96, .94, .89), (.91, .89, .84))
STONE = (.88, .86, .80)
EDGE = (.74, .74, .69)
ROOF_DECK = (.73, .73, .705)
TERRACE = (.94, .94, .90)
FRAME = (.50, .53, .54)
PALE_FRAME = (.74, .76, .75)
PALE = (1, .90, .90)  # Takes the cyan out of tower-glass.
VOID = (.64, .60, .58)
INTERIOR = (.72, .66, .50)
CURTAIN = (.55, .50, .41)
TAN = (.60, .53, .43)
AC_CASE = (.60, .60, .57)
HANDRAIL = (.62, .65, .64)
JOINT = (.50, .49, .46)

bins = {}
fixtures = []


def add(name, key, colour, verts, faces, weights=None, detail=False, light=None):
    b = bins.setdefault((name, key, tuple(colour), detail, light), {'v': [], 'f': [], 'w': []})
    base = len(b['v'])
    b['v'].extend(verts)
    b['f'].extend(tuple(i+base for i in f) for f in faces)
    b['w'].extend(weights if weights else [1]*len(verts))


# -- Grime --------------------------------------------------------------------------------------

# -- Geometry -----------------------------------------------------------------------------------

def cuboid(name, x0, x1, y0, y1, z0, z1, key=PANELS, colour=STONE, omit='', **flags):
    v = [(x, y, z) for z in (z0, z1) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    faces = {'b': (3, 2, 1, 0), 't': (4, 5, 6, 7), 'f': (0, 1, 5, 4), 'r': (1, 2, 6, 5), 'k': (2, 3, 7, 6), 'l': (3, 0, 4, 7)}
    add(name, key, colour, v, [f for k, f in faces.items() if k not in omit], **flags)


def wall_y(name, x0, x1, y, z0, z1, key=PANELS, colour=STONE, facing=-1, **flags):
    if facing > 0:
        x0, x1 = x1, x0
    add(name, key, colour, [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], [(0, 1, 2, 3)], **flags)


def wall_x(name, x, y0, y1, z0, z1, key=PANELS, colour=STONE, facing=1, **flags):
    if facing < 0:
        y0, y1 = y1, y0
    add(name, key, colour, [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)], [(0, 1, 2, 3)], **flags)


def deck(name, x0, x1, y0, y1, z, key=CAST, colour=ROOF_DECK, **flags):
    add(name, key, colour, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(0, 1, 2, 3)], **flags)


def soffit(name, x0, x1, y0, y1, z, key=CAST, colour=(.55, .55, .535), **flags):
    add(name, key, colour, [(x0, y1, z), (x1, y1, z), (x1, y0, z), (x0, y0, z)], [(0, 1, 2, 3)], **flags)


def grid_wall(name, a, b, z0, z1, du, dv, colour=STONE, key=PANELS, top=None, foot=None, shade=None, amount=1, **flags):
    """A vertical wall from a to b, seen with b to the right, with grime at each grid vertex."""
    (ax, ay), (bx, by) = a, b
    length = math.hypot(bx-ax, by-ay)
    nu, nv = max(1, round(length/du)), max(1, round((z1-z0)/dv))
    verts, weights, faces = [], [], []
    for j in range(nv+1):
        z = z0+(z1-z0)*j/nv
        for i in range(nu+1):
            t = i/nu
            x, y = ax+(bx-ax)*t, ay+(by-ay)*t
            verts.append((x, y, z))
            w = grime(x+1.37*y, z, top, foot, max(3.6, 1.2*du), amount)
            if shade:
                w *= shade[0]+(shade[1]-shade[0])*j/nv
            weights.append(w)
    for j in range(nv):
        for i in range(nu):
            k = j*(nu+1)+i
            faces.append((k, k+1, k+nu+2, k+nu+1))
    add(name, key, colour, verts, faces, weights=weights, **flags)


def band(name, x0, x1, y0, y1, z0, z1, colour=STONE, du=5.5, **flags):
    """A cast upstand: streaked front, soot-darkened toward its underside."""
    grid_wall(name, (x0, y0), (x1, y0), z0, z1, du, z1-z0, colour, shade=(.84, 1.04), **flags)
    cuboid(name, x0, x1, y0, y1, z0, z1, PANELS, colour, omit='f', **flags)


def profile_x(name, profile, x0, x1, key=PANELS, colour=STONE, **flags):
    """Extrude a Y/Z outline along X."""
    if sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(profile, profile[1:]+profile[:1])) < 0:
        profile = list(reversed(profile))
    n = len(profile)
    v = [(x, y, z) for x in (x0, x1) for y, z in profile]
    f = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    f += [(i, (i+1) % n, n+(i+1) % n, n+i) for i in range(n)]
    add(name, key, colour, v, f, **flags)


def round_prism(name, x, y, z0, z1, radius, key=PAINT, colour=DARK, sides=8, **flags):
    outline = [(x+radius*math.cos(i*math.tau/sides), y+radius*math.sin(i*math.tau/sides)) for i in range(sides)]
    v = [(a, b, z) for z in (z0, z1) for a, b in outline]
    f = [tuple(range(sides, 2*sides))]+[(i, (i+1) % sides, (i+1) % sides+sides, i+sides) for i in range(sides)]
    add(name, key, colour, v, f, **flags)


def disc(name, x, y, z, radius, normal, key=PAINT, colour=DARK, sides=8, **flags):
    """A flat polygon facing -Y, +Y or +Z."""
    a = [(radius*math.cos(i*math.tau/sides), radius*math.sin(i*math.tau/sides)) for i in range(sides)]
    if normal == 'z':
        v = [(x+p, y+q, z) for p, q in a]
    elif normal == '-y':
        v = [(x+p, y, z+q) for p, q in a]
    else:
        v = [(x-p, y, z+q) for p, q in a]
    add(name, key, colour, v, [tuple(range(sides))], **flags)


def rail(name, a, b, height=3.3, spacing=7):
    """Axis-aligned guard rail: the top rail survives LOD1, posts and mid rail do not."""
    (ax, ay, az), (bx, by, bz) = a, b
    r = .11
    x0, x1, y0, y1 = min(ax, bx)-r, max(ax, bx)+r, min(ay, by)-r, max(ay, by)+r
    cuboid(name+' top', x0, x1, y0, y1, az+height-.22, az+height, STEEL, HANDRAIL, omit='b')
    cuboid(name+' mid', x0, x1, y0, y1, az+height/2-.08, az+height/2+.08, STEEL, HANDRAIL, omit='b', detail=True)
    length = abs(bx-ax)+abs(by-ay)
    count = max(1, math.ceil(length/spacing))
    for i in range(count+1):
        x, y = ax+(bx-ax)*i/count, ay+(by-ay)*i/count
        cuboid(name+' post', x-r, x+r, y-r, y+r, az, az+height, STEEL, HANDRAIL, omit='bt', detail=True)


def glass_finish(kind):
    return {'pale': (PALE_GLASS, PALE), 'blue': (PALE_GLASS, (.70, .80, .95)), 'void': (PALE_GLASS, VOID), 'interior': (PALE_GLASS, INTERIOR), 'black': (DARK_GLASS, GLAZING)}[kind]


def pane_y(name, x0, x1, y, z0, z1, kind, lit, facing=-1):
    key, colour = glass_finish(kind)
    wall_y(name, x0, x1, y, z0, z1, key, colour, facing, light='night' if lit else 'off')


def pane_x(name, x, y0, y1, z0, z1, kind, lit, facing=1):
    key, colour = glass_finish(kind)
    wall_x(name, x, y0, y1, z0, z1, key, colour, facing, light='night' if lit else 'off')


def ac_unit(x, y, z):
    """Window-mounted air conditioner: a pale casing with a dark round fan facing out."""
    w, d, h = 3, 1.6, 2.4
    cuboid('air conditioner', x-w/2, x+w/2, y-d, y, z, z+h, PAINT, AC_CASE, omit='b', detail=True)
    disc('air conditioner fan', x-.15, y-d-.03, z+h/2, .95, '-y', PAINT, (.22, .24, .24), detail=True)


def foliage_clump(x, y, z, width, height, rng, depth=None):
    """A lumpy shrub in the board's grass floor. Opaque on purpose: the shared leaf cutouts are alpha
    blended, and one blended material removes a building's hex slice from the hover cutaway.
    Darkened toward its foot so it reads as volume; LOD1 keeps every other clump."""
    detail = rng.random() < .5
    r = width/2
    ry = r if depth is None else min(r, depth)
    spin = rng.uniform(0, math.tau)
    verts, weights = [], []
    for radius, level, weight in ((1, 0, .55), (.86, .55, .85)):
        for i in range(6):
            a = spin+i*math.tau/6
            k = radius*rng.uniform(.82, 1.12)
            verts.append((x+r*k*math.cos(a), y+ry*k*math.sin(a), z+height*level*rng.uniform(.9, 1.1)))
            weights.append(weight)
    verts.append((x+r*rng.uniform(-.15, .15), y+ry*rng.uniform(-.15, .15), z+height))
    weights.append(1)
    faces = [(i, (i+1) % 6, (i+1) % 6+6, i+6) for i in range(6)]+[(i+6, (i+1) % 6+6, 12) for i in range(6)]
    add('planting', BUSH, rng.choice(BUSH_COLOURS), verts, faces, weights=weights, detail=detail)


def planter(x0, x1, y0, y1, z, height, rng, density=.45):
    cuboid('planter trough', x0, x1, y0, y1, z, z+height-.4, PANELS, EDGE, omit='bt')
    deck('planter soil', x0, x1, y0, y1, z+height-.4, SOIL, (.24, .22, .18))
    rows = max(1, round((y1-y0)/3.4))
    for row in range(rows):
        y = y0+(y1-y0)*(row+.5)/rows
        x = x0+1.0
        while x < x1-.8:
            # Patchy bushes with gaps between them; a planter is rarely a clipped hedge.
            if rng.random() < .75:
                foliage_clump(x, y, z+height-.7, rng.uniform(2.2, 6.4), rng.uniform(1.4, 3.2), rng, depth=(y1-y0)/rows/2-.15)
            x += rng.uniform(.7, 1.3)/density


# -- Residential slab ------------------------------------------------------------------------

def loggia_row(lo, hi, z, rng, row):
    width = hi-lo
    tone = TONES[rng.randrange(3)]
    top = z+BAND
    if row == STOREYS-1:
        # The last storey is the roof's thick fascia, as tall as the reference's top band.
        band('top fascia', lo, hi, 0, 1.3, z-.4, ROOF+2.2, tone)
        cuboid('fascia coping', lo-.02, hi+.02, -.14, 1.44, ROOF+2.2, ROOF+2.5, PANELS, EDGE, omit='b')
        return
    # A solid upstand fills 40 % of the storey; the deep shadow comes from the floor behind it.
    band('slab parapet', lo, hi, 0, 1.3, z-.4, top, tone)
    cuboid('parapet coping', lo-.02, hi+.02, -.14, 1.44, top, top+.22, PANELS, EDGE, omit='b')
    cuboid('balcony rail band', lo, hi, .7, 1.15, top+.22, top+.62, STEEL, (.40, .44, .48), omit='b', detail=True)
    deck('loggia floor', lo, hi, 1.44, LOGGIA, z, CAST, (.523, .523, .51))
    soffit('loggia ceiling', lo, hi, 1.3, LOGGIA, z-.4)
    ceiling = z+STOREY-.4
    # Partition the bay into runs of glazing.
    x, runs = lo, []
    while x < hi-1:
        run = min(hi-x, rng.choice((.25, .34, .5, .66))*width)
        if hi-x-run < 7:
            run = hi-x
        runs.append((x, x+run))
        x += run
    for x0, x1 in runs:
        kind = rng.choice(('interior', 'interior', 'void', 'pale', 'pale', 'enclosed'))
        if kind == 'enclosed' and x1-x0 > .34*width:
            kind = 'pale'
        lit = rng.random() < .34
        forward = kind == 'enclosed'
        y = 1.46 if forward else 4.2 if kind == 'pale' else LOGGIA-.06
        bottom = top+.62 if forward else z+.1
        pitch = 3.9 if kind in ('pale', 'enclosed') else 6.6
        count = max(1, round((x1-x0)/pitch))
        pitch = (x1-x0)/count
        finish = 'pale' if forward else kind
        for i in range(count):
            a, b = x0+i*pitch, x0+(i+1)*pitch
            pane_y('facade glass', a, b, y, bottom, ceiling, finish, lit and rng.random() < .75)
            wall_y('window mullion', b-.13, b+.13, y-.05, bottom, ceiling, STEEL, PALE_FRAME if forward else FRAME, detail=True)
            # Lives behind the glass: a drawn curtain or blind in a few of the dim windows.
            if finish != 'pale' and rng.random() < .4:
                c0 = rng.uniform(a+.2, b-2)
                wall_y('curtain', c0, min(b-.2, c0+rng.uniform(1.4, 3)), y-.03, bottom+rng.uniform(.5, 1.5), ceiling-.2, PAINT, CURTAIN, detail=True)
        if kind in ('pale', 'enclosed'):
            wall_y('window head', x0, x1, y-.05, ceiling-.5, ceiling, STEEL, PALE_FRAME if forward else FRAME)
            wall_y('window sill', x0, x1, y-.05, bottom, bottom+.4, STEEL, PALE_FRAME if forward else FRAME, detail=True)
            for e in (x0, x1):
                cuboid('glazing jamb', e-.18, e+.18, 1.4, LOGGIA, z, ceiling, PANELS, EDGE, omit='bt', detail=True)
        if kind in ('black', 'void') and rng.random() < .36 and row < 11:
            foliage_clump(rng.uniform(x0+2, x1-2), 3.4, z+.2, rng.uniform(2.6, 4), BAND+.9, rng)
    # Party walls at the apartment grid.
    steps = 4 if width > 60 else 2
    for i in range(1, steps):
        p = lo+width*i/steps
        cuboid('loggia party wall', p-.3, p+.3, 1.4, LOGGIA, z, ceiling, PANELS, EDGE, omit='bt', detail=True)
    # Air conditioners cluster beside the cores.
    near_core = lo+2.6 if lo > -60 else hi-2.6
    if rng.random() < .55:
        ac_unit(near_core, -.12, top-2.7)
    for _ in range(2 if width > 60 else 1):
        if rng.random() < (.55 if width > 60 else .38):
            ac_unit(rng.uniform(lo+4, hi-4), -.12, top-2.7)


def slab():
    rng = random.Random(16)
    # Behind the loggias a single hollow shell: loggia back wall, side walls, rear wall.
    wall_y('slab loggia back wall', -96, 96, LOGGIA, PODIUM-6, ROOF, PANELS, (.26, .26, .25))
    for i in range(STOREYS):
        z = PODIUM+i*STOREY
        for lo, hi in BAYS:
            loggia_row(lo, hi, z, rng, i)
    for side in (-1, 1):
        side_wall(side)
        wall_x('loggia end wall', side*95.94, 0, LOGGIA, PODIUM, ROOF, PANELS, EDGE, facing=-side)
    rear_wall()
    deck('slab roof', -96, 96, 0, SLAB_Y, ROOF, CAST, ROOF_DECK)
    # Roof parapet: a thin solid band on the three exposed sides, the front is the fascia.
    for side in (-1, 1):
        cuboid('roof parapet', side*96-.7, side*96+.7, 0, SLAB_Y+.7, ROOF, ROOF+2.2, PANELS, EDGE, omit='b')
        cuboid('roof parapet coping', side*96-.85, side*96+.85, -.1, SLAB_Y+.85, ROOF+2.2, ROOF+2.5, PANELS, (.92, .91, .86), omit='b')
    cuboid('roof parapet', -96, 96, SLAB_Y-.7, SLAB_Y+.7, ROOF, ROOF+2.2, PANELS, EDGE, omit='b')
    cuboid('roof parapet coping', -96, 96, SLAB_Y-.85, SLAB_Y+.85, ROOF+2.2, ROOF+2.5, PANELS, (.92, .91, .86), omit='b')
    for x in (-94.5, 94.5):
        round_prism('slab downpipe', x, SLAB_Y+.5, 36, ROOF, .4, PAINT, (.30, .32, .32), 6)
    # The side rails stop at the escape stair heads (y 31 to 46).
    for x in (-94.4, 94.4):
        rail('roof edge rail', (x, 1, ROOF+.1), (x, 30.6, ROOF+.1))
        rail('roof edge rail', (x, 46.4, ROOF+.1), (x, SLAB_Y-1.4, ROOF+.1))
    # Behind the fascia, between the cores and the penthouse.
    for x0, x1 in ((-94.4, -60.4), (-39.6, -20.4), (8.4, 39.6), (60.4, 94.4)):
        rail('roof edge rail', (x0, 1.7, ROOF+.1), (x1, 1.7, ROOF+.1))
    rail('roof edge rail', (-94.4, SLAB_Y-1.4, ROOF+.1), (94.4, SLAB_Y-1.4, ROOF+.1))


def side_wall(side):
    x = side*96
    a, b = ((x, 0), (x, SLAB_Y)) if side > 0 else ((x, SLAB_Y), (x, 0))
    grid_wall('slab side wall', a, b, 36, ROOF, 5.5, STOREY, STONE, top=ROOF)
    # One column of narrow dark windows with a concrete spandrel between each.
    for i in range(STOREYS):
        z = PODIUM+i*STOREY
        y0, y1 = 36.2, 41.2
        pane_x('side stair window', x+side*.06, y0, y1, z+1.2, z+STOREY-.8, 'black', (i*5+side) % 7 == 0, facing=side)
        cuboid('side window sill', min(x, x+side*.35), max(x, x+side*.35), y0-.3, y1+.3, z+.9, z+1.2, PANELS, EDGE, omit='b', detail=True)
    # Dark slot and riser pier at the rear, with small balconies carried on brackets.
    lo, hi = sorted((x+side*.05, x+side*.3))
    wall_x('side riser slot', x+side*.02, 55, 58, 36, ROOF-3, PAINT, (.16, .17, .17), facing=side)
    cuboid('side riser pier', min(x, x+side*2.6), max(x, x+side*2.6), 58, 62, 36, ROOF+2.2, PANELS, (.72, .71, .67), omit='b')
    # Every third floor, with a door level with the corridor. West's first is the terrace itself.
    for k in range(5):
        if side > 0 or k > 0:
            side_balcony(side, PODIUM+3*k*STOREY-2.2)


def side_balcony(side, z):
    x = side*96
    y0, y1 = 53.5, 63.5
    # Bracketed slab, thick at the wall and thin at the lip.
    profile = [(0, -2.6), (10, 1.2), (10, 2.2), (0, 2.2)]
    verts = [(x+side*p, y, z+q) for y in (y0, y1) for p, q in profile]
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    if side < 0:
        faces = [tuple(reversed(f)) for f in faces]
    add('side balcony', PANELS, EDGE, verts, faces)
    far = x+side*9.6
    rail('side balcony rail', (far, y0+.3, z+2.2), (far, y1-.3, z+2.2), 3.4, 2.4)
    rail('side balcony rail', (x, y0+.3, z+2.2), (far, y0+.3, z+2.2), 3.4, 2.4)
    rail('side balcony rail', (x, y1-.3, z+2.2), (far, y1-.3, z+2.2), 3.4, 2.4)
    door('side balcony', x, 55.8, z+2.2, (side, 0))


def rear_wall():
    grid_wall('slab rear wall', (96, SLAB_Y), (-96, SLAB_Y), 36, ROOF, 8, STOREY, STONE, top=ROOF)
    for i in range(STOREYS):
        z = PODIUM+i*STOREY
        cuboid('rear floor band', -96, 96, SLAB_Y, SLAB_Y+.8, z-.5, z+.5, PANELS, EDGE, omit='b')
        for c in range(13):
            xc = -84+c*14
            pane_y('rear window', xc-5.2, xc+5.2, SLAB_Y+.06, z+2.2, z+7.6, 'pale' if (c+i) % 4 == 0 else 'void', (c*5+i*3) % 9 < 2, facing=1)


# -- Service cores ---------------------------------------------------------------------------

def core(x0, x1):
    y0, y1 = CORE_Y
    # Battered foot from the podium roof down to the street.
    flare = 9
    base = ((x0-2, y0-flare), (x1+2, y0-flare), (x1+2, y1), (x0-2, y1))
    upper = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    v = [(a, b, 0) for a, b in base]+[(a, b, PODIUM) for a, b in upper]
    add('battered core foot', PANELS, (.80, .78, .74), v, [(0, 1, 5, 4), (1, 2, 6, 5), (3, 0, 4, 7)])
    grid_wall('core', (x0, y0), (x1, y0), PODIUM, CORE_TOP, 4, 13.5, STONE, top=CORE_TOP)
    grid_wall('core', (x1, y0), (x1, y1), PODIUM, CORE_TOP, 4.5, 13.5, STONE, top=CORE_TOP)
    grid_wall('core', (x0, y1), (x0, y0), PODIUM, CORE_TOP, 4.5, 13.5, STONE, top=CORE_TOP)
    grid_wall('core', (x1, y1), (x0, y1), ROOF, CORE_TOP, 4, 12, STONE, top=CORE_TOP)
    cuboid('core cap', x0-.25, x1+.25, y0-.25, y1+.25, CORE_TOP, CORE_TOP+.7, PANELS, (.86, .85, .80), omit='b')
    for k in (x0+6.7, x1-6.7):
        wall_y('core board joint', k-.09, k+.09, y0-.03, PODIUM, CORE_TOP-13, STEEL, JOINT, detail=True)
    for k in (y0+12, y0+24):
        for wx, face in ((x0, -1), (x1, 1)):
            wall_x('core board joint', wx+face*.03, k-.09, k+.09, PODIUM, CORE_TOP, STEEL, JOINT, facing=face, detail=True)
    deck('core head', x0+.3, x1-.3, y0+.3, y1-.3, CORE_TOP+.72, CAST, (.863, .863, .81))
    x = (x0+x1)/2
    # A small louvre pair near the head and a beacon on top.
    for xx in (x-3.3, x+3.3):
        wall_y('core louvre', xx-3, xx+3, y0-.05, CORE_TOP-12, CORE_TOP-5.5, SLATS, (.42, .43, .43))
    wall_y('core louvre frame', x-6.5, x+6.5, y0-.04, CORE_TOP-12.4, CORE_TOP-5.1, PANELS, (.40, .40, .38))
    cuboid('core beacon plinth', x-1, x+1, -1, 1, CORE_TOP+.7, CORE_TOP+1.4, STEEL, DARK, omit='b')
    round_prism('core beacon pedestal', x, 0, CORE_TOP+1.4, CORE_TOP+3, .55, STEEL, DARK, 6)
    round_prism('core red obstruction beacon', x, 0, CORE_TOP+3, CORE_TOP+4.2, 1, PAINT, (.85, .08, .025), 8, light=(1, .035, .012))
    round_prism('core red obstruction beacon', x, 0, CORE_TOP+4.2, CORE_TOP+4.8, .6, PAINT, (.85, .08, .025), 8, light=(1, .035, .012))
    cuboid('core head hatch', x+3, x+7, y1-9, y1-4, CORE_TOP+.7, CORE_TOP+1.6, STEEL, ALLOY, omit='b', detail=True)
    round_prism('core head vent', x-5, y1-8, CORE_TOP+.7, CORE_TOP+2, .6, STEEL, ALLOY, 6, detail=True)


# -- Roof machinery --------------------------------------------------------------------------

def plant(name, x0, x1, y0, y1, height, fans):
    z = ROOF
    cuboid(name+' curb', x0-1, x1+1, y0-1, y1+1, z, z+1, PANELS, EDGE, omit='b')
    cuboid(name, x0, x1, y0, y1, z+1, z+height, shared.PAINT, (.36, .37, .37), omit='b')
    cells = max(1, round((x1-x0)/9))
    for i in range(cells):
        a = x0+(x1-x0)*i/cells+.6
        b = x0+(x1-x0)*(i+1)/cells-.6
        wall_y(name+' louvre', a, b, y0-.05, z+2.2, z+height-1, SLATS, LOUVRE)
    cells = max(1, round((y1-y0)/9))
    for i in range(cells):
        a = y0+(y1-y0)*i/cells+.6
        b = y0+(y1-y0)*(i+1)/cells-.6
        wall_x(name+' louvre', x1+.05, a, b, z+2.2, z+height-1, SLATS, LOUVRE)
    deck(name+' top', x0, x1, y0, y1, z+height+.02, PAINT, (.24, .25, .25))
    # Evenly along the unit, so that they neither touch nor overhang it.
    for i in range(fans):
        xx = x0+(i+.5)*(x1-x0)/fans
        yy = (y0+y1)/2
        r = min((y1-y0)/2-.8, 4.2)
        disc(name+' fan well', xx, yy, z+height+.04, r, 'z', PAINT, (.10, .11, .11), 12)
        outer = [(xx+(r+.5)*math.cos(i*math.tau/12), yy+(r+.5)*math.sin(i*math.tau/12)) for i in range(12)]
        inner = [(xx+r*math.cos(i*math.tau/12), yy+r*math.sin(i*math.tau/12)) for i in range(12)]
        ring = [(p, q, z+height) for p, q in outer]+[(p, q, z+height+1) for p, q in outer]+[(p, q, z+height+1) for p, q in inner]
        ring += [(p, q, z+height) for p, q in inner]
        faces = [(k, (k+1) % 12, (k+1) % 12+12, k+12) for k in range(12)]+[(k+12, (k+1) % 12+12, (k+1) % 12+24, k+24) for k in range(12)]
        faces += [(k+24, (k+1) % 12+24, (k+1) % 12+36, k+36) for k in range(12)]
        add(name+' fan collar', PAINT, (.28, .30, .30), ring, faces)


def ladder(x, y, z0, z1):
    """Maintenance ladder on a rear wall (facing +Y): uprights survive LOD1, rungs do not."""
    for a in (x-.9, x+.9):
        cuboid('maintenance ladder upright', a-.09, a+.09, y+.5, y+.68, z0, z1+1.2, STEEL, HANDRAIL, omit='bt')
    z = z0+.7
    while z < z1+.5:
        cuboid('maintenance ladder rung', x-.9, x+.9, y+.52, y+.66, z-.06, z+.06, STEEL, HANDRAIL, omit='lr', detail=True)
        z += 1.5


def rooftop():
    plant('rear-west plant', -52, -30, 30, 54, 9, 1)
    plant('central plant', -24, 12, 30, 48, 9.5, 3)
    plant('east plant', 52, 82, 30, 54, 12, 3)
    cuboid('smoke vent', 66, 78, 9, 21, ROOF, ROOF+5, PANELS, EDGE, omit='b')
    deck('smoke vent well', 67, 77, 10, 20, ROOF+5.02, PAINT, (.12, .13, .13))
    wall_y('smoke vent louvre', 67, 77, 9, ROOF+.8, ROOF+4.4, SLATS, LOUVRE)
    wall_x('smoke vent louvre', 78, 10, 20, ROOF+.8, ROOF+4.4, SLATS, LOUVRE)
    # The side-wall stair columns end in stair heads; lifts reach the roof through the cores.
    for x0, x1 in ((-95, -86), (86, 95)):
        cuboid('escape stair head', x0, x1, 31, 46, ROOF, ROOF+10.2, PANELS, TONES[1], omit='b')
        cuboid('escape stair head coping', x0-.15, x1+.15, 30.85, 46.15, ROOF+10.2, ROOF+10.5, PANELS, (.90, .89, .84), omit='b')
        door('escape stair', (x0+x1)/2, 31, ROOF)
    for x in (-50, 50):
        door('core roof', x, CORE_Y[1], ROOF, (0, 1))
        ladder(x+6.5, CORE_Y[1], ROOF+.5, CORE_TOP)
    door('penthouse', -6, 9, ROOF, (0, 1), width=3.6, height=5.6, lit=False)
    # Glazed penthouse strip standing on the front parapet.
    cuboid('penthouse', -20, 8, 1.3, 9, ROOF, ROOF+6, PANELS, EDGE, omit='bf')
    for i in range(7):
        a = -19.6+i*3.9
        pane_y('penthouse glass', a, a+3.7, 1.3, ROOF+1, ROOF+5.4, 'pale', i == 3)
    wall_y('penthouse head', -20, 8, 1.3, ROOF+5.4, ROOF+6, PANELS, EDGE)
    wall_y('penthouse backing', -20, 8, 1.34, ROOF, ROOF+5.4, PANELS, (.30, .30, .29))
    # Weathered bitumen patches break the flat deck.
    for x0, x1, y0, y1, c in ((-94, -62, 2, 34, .60), (-30, 26, 3, 19, .64), (-14, 38, 49, 61, .614), (62, 94, 24, 60, .654), (28, 39, 3, 28, .575)):
        deck('roof patch', x0, x1, y0, y1, ROOF+.03, CAST, (c, c, c*.97))
    # Pipes and small fittings.
    for y in (37, 39):
        cuboid('roof pipe', 12, 52, y-.4, y+.4, ROOF+.6, ROOF+1.4, STEEL, ALLOY, omit='b')
    for x0, x1 in ((-38, -21), (9, 38)):
        cuboid('front parapet conduit', x0, x1, 5, 5.7, ROOF+.4, ROOF+1.1, STEEL, (.40, .42, .42), omit='b')
    for x, w in ((-34, 4), (-27, 3), (12, 5), (20, 3.4), (30, 4.4)):
        cuboid('front parapet junction box', x, x+w, 3, 6.4, ROOF, ROOF+2.4, PAINT, (.36, .38, .38), omit='b')
    for x, y in ((-84, 12), (-70, 24), (90, 12)):
        cuboid('roof fan box', x-2, x+2, y-2, y+2, ROOF, ROOF+3, PAINT, (.40, .42, .42), omit='b')
    for x in (20, 32, 44):
        cuboid('pipe stand', x-.3, x+.3, 36, 40, ROOF, ROOF+.7, STEEL, ALLOY, omit='b', detail=True)
    round_prism('water tank', 86, 57, ROOF, ROOF+8, 2.6, PAINT, (.33, .35, .35), 10)
    round_prism('roof vent', 30, 30, ROOF, ROOF+4, 1.1, PAINT, (.45, .47, .47), 8)
    round_prism('roof vent', -14, 15, ROOF, ROOF+3, .9, PAINT, (.45, .47, .47), 8)
    # Communications mast with crosspieces.
    cuboid('mast plinth', -27, -21, 55, 61, ROOF, ROOF+1.6, PANELS, EDGE, omit='b')
    cuboid('mast', -24.3, -23.7, 57.7, 58.3, ROOF+1.6, ROOF+42, STEEL, ALLOY, omit='b')
    for z in (ROOF+26, ROOF+32, ROOF+38):
        cuboid('mast crosspiece', -27, -21, 57.85, 58.15, z, z+.3, STEEL, ALLOY)
        cuboid('mast antenna', -27, -26.3, 57.8, 58.2, z-2, z+2, PAINT, (.72, .74, .72), detail=True)
        cuboid('mast antenna', -21.7, -21, 57.8, 58.2, z-2, z+2, PAINT, (.72, .74, .72), detail=True)


# -- Podium ----------------------------------------------------------------------------------

def tier_units(name, lo, hi, y, z0, z1, rng, lit_share=.34):
    """One recessed row: dark sliding glass, beige infill panels, narrow concrete piers."""
    x = lo
    while x < hi-.1:
        w = min(hi-x, rng.uniform(5.2, 7.4))
        if hi-x-w < 3:
            w = hi-x
        r = rng.random()
        if r < .30:
            wall_y(name+' infill panel', x+.25, x+w-.25, y, z0, z1, PAINT, TAN)
        else:
            pane_y(name+' glass', x+.25, x+w-.25, y, z0, z1, rng.choice(('black', 'black', 'void')), rng.random() < lit_share)
            wall_y(name+' sash', (2*x+w)/2-.08, (2*x+w)/2+.08, y-.05, z0, z1, STEEL, (.36, .38, .38), detail=True)
        cuboid(name+' pier', x+w-.3, x+w+.3, y-.5, y+.2, z0, z1, PANELS, EDGE, omit='bt')
        x += w


def wing(name, lo, hi, fronts, rear, rng, ground='shutters', top_lo=None, top_hi=None, sun_room=None, cheek_rear=(None, None)):
    """A stepped wing: storefront, three recessed rows behind planted parapets, roof fascia.

    Each step is deeper than it is tall, and the concrete bands overhang the glass below. cheek_rear: where each upper
    cheek stops short of the rear, leaving a core door its way onto the roof deck."""
    top_lo = lo if top_lo is None else top_lo
    top_hi = hi if top_hi is None else top_hi
    floors = (19, 30.5, 42.5)
    y0, y3 = fronts[0], fronts[3]
    # Street storey: a thick band over low shopfronts.
    band(name+' street fascia', lo, hi, y0, y0+2.6, 13, 19, STONE)
    wall_y(name+' street wall', lo, hi, y0+2.6, 0, 13, PANELS, (.42, .42, .40))
    soffit(name+' street soffit', lo, hi, y0, y0+2.6, 13)
    # Paired rows, each band hanging over a covered balcony on the row below.
    for k, floor in enumerate(floors):
        front = fronts[k]
        back = fronts[k+1]+6
        top = floor+4.5
        spans = ((lo, sun_room[0]), (sun_room[1], hi)) if sun_room and k == 2 else ((lo, hi),)
        for a, b in spans:
            band(name+' terrace parapet', a, b, front, front+1.2, floor-.5, top, TONES[k])
            cuboid(name+' parapet coping', a-.02, b+.02, front-.12, front+1.32, top, top+.22, PANELS, (.92, .91, .86), omit='b')
            if b-a > 8:
                planter(a+2.4, b-2.4, front+1.2, front+3.8, floor, 4.6, rng)
        deck(name+' terrace floor', lo, hi, front+1.2, back, floor, CAST, TERRACE)
        ceiling = (floors[k+1] if k < 2 else 50)-.5
        soffit(name+' balcony ceiling', lo, hi, fronts[k+1], back, ceiling)
        wall_y(name+' row wall', lo, hi, back, floor, ceiling, PANELS, (.42, .42, .40))
        tier_units(name+' row', lo+1, hi-1, back-.06, floor+.15, ceiling-.1, rng)
    band(name+' roof fascia', top_lo, top_hi, y3, y3+1.2, 49.5, PODIUM+2.5, STONE)
    cuboid(name+' fascia coping', top_lo-.02, top_hi+.02, y3-.12, y3+1.32, PODIUM+2.5, PODIUM+2.75, PANELS, (.92, .91, .86), omit='b')
    deck(name+' roof deck', top_lo, top_hi, y3+1.2, rear, PODIUM, CAST, TERRACE)
    rail(name+' roof rail', (top_lo+2.5, y3+.6, PODIUM+2.75), (top_hi-2.5, y3+.6, PODIUM+2.75))
    # Stepped cheek walls own the ends of every row; each step has a heavy capped pier.
    for x, inner in ((lo, lo+2.2), (hi-2.2, hi)):
        high_side = top_hi < hi and x > 0 or top_lo > lo and x < 0
        tail = [(y3-3.4, 47.5), (y3-.8, 53), (rear, 53), (rear, 0)] if high_side else [(rear, 47.5), (rear, 0)]
        low = [(y0-.8, 0), (y0-.8, 24.7), (fronts[1]-3.4, 24.7), (fronts[1]-.8, 36.2), (fronts[2]-3.4, 36.2),
               (fronts[2]-.8, 47.5)]+tail
        profile_x(name+' stepped cheek', low, x, inner, PANELS, TONES[1])
    for (x, inner), end in zip(((top_lo, top_lo+2.2), (top_hi-2.2, top_hi)), cheek_rear):
        end = rear if end is None else end
        high = [(y3-3.4, 47.5), (y3-.8, PODIUM+2.75), (end, PODIUM+2.75), (end, 47.5)]
        profile_x(name+' upper cheek', high, x, inner, PANELS, TONES[1])
    if ground == 'shutters':
        street_shutters(name, lo+3, hi-3, y0+2.54)


def street_shutters(name, lo, hi, y):
    """Dark shopfront glass on a low stall riser, between heavy pilasters."""
    count = max(2, round((hi-lo)/18))
    pitch = (hi-lo)/count
    for i in range(count):
        a = lo+i*pitch+.8
        b = lo+(i+1)*pitch-.8
        pane_y(name+' shopfront', a, b, y, 1.4, 12.2, 'black', i % 2 == 0)
        cuboid(name+' security shutter box', a, b, y-.9, y, 11.2, 12.3, PAINT, (.26, .29, .30), omit='k')
        for e in (a+.12, b-.12):
            cuboid(name+' shutter guide', e-.12, e+.12, y-.35, y, .05, 11.2, STEEL, (.28, .30, .30), omit='bt', detail=True)
        wall_y(name+' stall riser', a, b, y, .05, 1.4, PANELS, (.46, .46, .44))
        n = max(2, round((b-a)/3.6))
        for k in range(1, n):
            xx = a+(b-a)*k/n
            wall_y(name+' shopfront mullion', xx-.1, xx+.1, y-.05, 1.4, 11.2, STEEL, (.30, .32, .32), detail=True)
        if i < count-1:
            cuboid(name+' street pilaster', b+.05, b+1.55, y-1.8, y+.1, 0, 13, PANELS, STONE, omit='bt')


def wall_quad(name, x, y, n, a, b, z0, z1, offset, key, colour, **flags):
    """A rectangle on any wall: n is the outward axis, a and b run left to right seen from outside."""
    ux, uy = -n[1], n[0]
    ox, oy = x+n[0]*offset, y+n[1]*offset
    add(name, key, colour, [(ox+ux*a, oy+uy*a, z0), (ox+ux*b, oy+uy*b, z0), (ox+ux*b, oy+uy*b, z1), (ox+ux*a, oy+uy*a, z1)], [(0, 1, 2, 3)], **flags)


def lamp(x, y, z, n=(0, -1), radius=.62, fixture=False):
    """A small amber wall lamp on a bracket, always on like the citadel's work lights."""
    ux, uy = -n[1], n[0]
    wall_quad('wall lamp bracket', x, y, n, -.3, .3, z-.5, z+1.6, .05, STEEL, DARK, detail=True)
    ring = [(ux*radius*math.cos(i*math.tau/8), uy*radius*math.cos(i*math.tau/8), z+.55+radius*math.sin(i*math.tau/8)) for i in range(8)]
    v = [(x+n[0]*off+a, y+n[1]*off+b, c) for off in (.1, .5) for a, b, c in ring]
    add('wall lamp globe', PAINT, (.50, .42, .26), v, [tuple(range(8, 16))]+[(i, (i+1) % 8, (i+1) % 8+8, i+8) for i in range(8)], light=(1, .72, .35))
    if fixture:
        fixtures.append((x+n[0]*1.2, y+n[1]*1.2, z+.5))


def door(name, x, y, z=0, n=(0, -1), width=4.2, height=7.7, fixture=False, lit=True):
    """A 1.4 x 2.6 m steel door with a vision panel and, unless it is under a low head, a lamp."""
    wall_quad(name+' door frame', x, y, n, -width/2, width/2, z, z+height, .04, STEEL, DARK)
    wall_quad(name+' door leaf', x, y, n, -width/2+.3, width/2-.3, z, z+height-.3, .09, PAINT, (.38, .43, .43))
    wall_quad(name+' door vision panel', x, y, n, -.9, .9, z+3.7, z+5.8, .13, PALE_GLASS, PALE, light='night')
    if lit:
        lamp(x, y, z+height+.6, n, radius=.62 if z == 0 else .45, fixture=fixture)


def lobby(lo, hi, y):
    """Full-height central lobby glass between concrete pilasters."""
    pitch = (hi-lo)/6
    for i in range(6):
        a, b = lo+i*pitch, lo+(i+1)*pitch
        pane_y('lobby glass', a+.5, b-.5, y-.06, .3, 12.6, 'black', True)
        wall_y('lobby transom', a+.5, b-.5, y-.12, 8.6, 8.9, STEEL, DARK, detail=True)
        wall_y('lobby mullion', (a+b)/2-.1, (a+b)/2+.1, y-.12, .3, 12.6, STEEL, DARK, detail=True)
        cuboid('lobby pilaster', b-.8, b+.8, y-2.2, y+.1, 0, 13, PANELS, STONE, omit='bt')
        if i in (1, 3):
            lamp(b, y-2.2, 9, fixture=True)
    for x in (-3, 3):
        wall_y('lobby door', x-2.1, x+2.1, y-.14, 0, 7.9, STEEL, DARK)
        pane_y('lobby door glass', x-1.6, x+1.6, y-.18, .8, 7.4, 'black', False)
    cuboid('lobby step', lo, hi, y-8, y-.1, 0, .5, PANELS, EDGE, omit='b')


def centre_glazing(fronts):
    """The reference's glazed sun room over the central wing's right half, with an awning below."""
    x0, x1, z0, z1, y = *SUN_ROOM_X, 42.2, 51.4, fronts[2]-1
    cuboid('central sun room', x0, x1, y, fronts[3], z0, z1, PANELS, EDGE, omit='bft')
    deck('central sun room roof', x0, x1, y, fronts[3], z1, PAINT, (.34, .36, .38))
    count = 8
    pitch = (x1-x0-.4)/count
    for i in range(count):
        a = x0+.2+i*pitch
        pane_y('central sun room glass', a, a+pitch-.25, y, z0+.5, z1-.5, 'blue', i % 3 == 1)
        wall_y('central sun room mullion', a+pitch-.25, a+pitch, y-.05, z0+.5, z1-.5, STEEL, PALE_FRAME, detail=True)
    wall_y('central sun room frame', x0, x1, y, z0, z0+.5, PANELS, EDGE)
    wall_y('central sun room frame', x0, x1, y, z1-.5, z1, PANELS, EDGE)
    y = fronts[2]
    v = [(5, y-4, 38.4), (31, y-4, 38.4), (31, y, 40.2), (5, y, 40.2)]
    add('central awning', PAINT, (.26, .33, .40), v+[(a, b, c-.2) for a, b, c in v], [(0, 1, 2, 3), (7, 6, 5, 4), (4, 5, 1, 0), (6, 7, 3, 2), (5, 6, 2, 1), (7, 4, 0, 3)])


def alley(lo, hi):
    """A recessed street block with a dark double door and lamp; a paved ramp up to the core foot."""
    y = -70
    x = (lo+hi)/2
    grid_wall('alley street wall', (lo, y), (hi, y), 0, 12.6, 4, 12.6, TONES[1], foot=0)
    # The lintel rises as a solid guard to the first-floor landing behind it.
    band('alley lintel', lo, hi, y-1, y+.4, 12.4, 22.3, STONE)
    cuboid('alley lintel coping', lo-.02, hi+.02, y-1.12, y+.52, 22.3, 22.52, PANELS, (.92, .91, .86), omit='b')
    # Door in a concrete reveal: four dark steel leaves, a glazed transom, a lamp on the lintel.
    half = 6.6
    wall_y('alley door reveal', x-half-.6, x+half+.6, y-.04, 0, 11.2, PANELS, (.36, .36, .34))
    wall_y('alley door', x-half, x+half, y-.08, 0, 8.4, PAINT, (.20, .22, .23))
    pane_y('alley door transom', x-half, x+half, y-.08, 8.6, 10.8, 'black', True)
    for k in range(5):
        xx = x-half+2*half*k/4
        wall_y('alley door stile', xx-.1, xx+.1, y-.12, 0, 10.8, STEEL, (.14, .15, .15))
    lamp(x, y-1, 13.2, fixture=True)
    deck('alley paving', lo, hi, -85, y, .2, CAST, (.81, .823, .784))
    # Above the street door a landing gives onto the wings' first floor; a paved ramp climbs
    # from it to a door in the core foot, so residents reach the galleries from the lifts.
    deck('alley landing', lo, hi, y+.4, -64, 19, CAST, (.627, .627, .601))
    door('first floor gallery', lo, -66.5, 19, (1, 0))
    door('first floor gallery', hi, -66.5, 19, (-1, 0))
    y0, y1, z0, z1 = -64, -27, 19, 24
    core_x = -50 if lo < 0 else 50
    add('alley paved ramp', CAST, (.601, .601, .575), [(lo, y0, z0), (hi, y0, z0), (hi, y1, z1), (lo, y1, z1)], [(0, 1, 2, 3)])
    deck('alley upper landing', lo, hi, y1, -18, z1, CAST, (.601, .601, .575))
    cuboid('core foot portal', core_x-6, core_x+6, y1, -15, z1, z1+12, PANELS, STONE, omit='b')
    cuboid('core foot portal head', core_x-6.4, core_x+6.4, y1-.4, -15, z1+12, z1+12.6, PANELS, (.90, .89, .84), omit='b')
    door('core foot', core_x-2.4, y1, z1)
    door('core foot', core_x+2.4, y1, z1)
    for k in range(1, 7):
        t = k/7
        yy, zz = y0+(y1-y0)*t, z0+(z1-z0)*t
        add('alley ramp joint', STEEL, JOINT, [(lo, yy-.07, zz+.03), (hi, yy-.07, zz+.03), (hi, yy+.07, zz+.04), (lo, yy+.07, zz+.04)], [(0, 1, 2, 3)], detail=True)


def step_block(name, x0, x1, y0, y1, z, foot, kerbs, rails):
    """A low terrace at a helper height: deck, 1.2 kerbs and a rail along each open edge."""
    deck(name+' terrace', x0, x1, y0, y1, z, CAST, TERRACE)
    for a, b, c, d in kerbs:
        cuboid(name+' kerb', a, b, c, d, z, z+1.2, PANELS, TONES[0], omit='b')
    for a, b in rails:
        rail(name+' rail', (*a, z+1.2), (*b, z+1.2))


def west_flank(rng):
    # Two terraces climbing toward the rear, each a full level; a steel stair links them.
    grid_wall('west step wall', (-146, -85), (-127, -85), 0, 18, 5.5, 18, STONE, foot=0)
    grid_wall('west step wall', (-146, -63), (-146, -85), 0, 18, 5.5, 18, STONE, foot=0)
    grid_wall('west step wall', (-146, -14), (-146, -63), 0, 36, 5.5, 18, STONE, foot=0)
    grid_wall('west step wall', (-146, -63), (-127, -63), 18, 36, 5.5, 18, STONE)
    grid_wall('west step wall', (-127, -14), (-146, -14), 0, 37.2, 6, 19, STONE, foot=0)
    step_block('west low', -146, -127, -85, -63, 18, 0, ((-146, -145, -85, -63), (-145, -127, -85, -84)),
               (((-145.4, -84.4), (-145.4, -63.6)), ((-145.4, -84.4), (-128, -84.4))))
    step_block('west high', -146, -127, -63, -14, 36, 0, ((-146, -145, -62, -14), (-141.8, -127, -63, -62), (-145, -127, -15, -14)),
               (((-145.4, -62), (-145.4, -14.6)), ((-145.4, -14.6), (-128, -14.6)), ((-141.6, -62.4), (-128, -62.4))))
    # An industrial steel stair: a level's six metres in thirty 20 cm risers, steep and short, with room on the deck to step onto it.
    foot, head = -77.3, -63.3
    for i in range(30):
        y, z = foot+i*(head-foot)/30, 18+.6*(i+1)
        cuboid('west step stair tread', -144.8, -142, y, y+.6, z-.3, z, STEEL, DARK, omit='b', detail=True)
    for x in (-145, -141.8):
        profile_x('west step stair stringer', [(foot, 18), (foot, 19.2), (head, 37.2), (head, 35.6)], x, x+.2, STEEL, DARK)
        profile_x('west step stair rail top', [(foot, 22.3), (foot, 22.5), (head, 39.5), (head, 39.3)], x, x+.2, STEEL, HANDRAIL)
        for i in range(1, 5):
            y, z = foot+i*(head-foot)/5, 19.2+i*18/5
            cuboid('west step stair rail post', x, x+.2, y-.1, y+.1, z, z+3.3, STEEL, HANDRAIL, omit='bt', detail=True)
    # Kept clear of the stair, which climbs across the wall's other half.
    pane_y('west step window', -132.7, -127.3, -63.06, 23, 32, 'black', True)
    wall_y('west step window frame', -133, -127, -63.03, 22.7, 32.3, PANELS, (.46, .46, .44))
    planter(-139, -130, -60, -36, 36, 3.4, rng, density=1.3)
    wall_y('west goods door frame', -144.6, -133.4, -85.04, 0, 12.6, STEEL, DARK)
    wall_y('west goods door', -144, -134, -85.08, 0, 12, PAINT, (.20, .22, .23))
    for x in (-140.7, -137.3):
        wall_y('west goods door stile', x-.1, x+.1, -85.12, 0, 12, STEEL, (.14, .15, .15))
    for x in (-142, -136):
        lamp(x, -85, 13.4, fixture=x < -140)
    door('west step', -130, -85)
    for y, z0 in ((-52, 8), (-28, 8)):
        wall_x('west step grille', -146.05, y-6, y+6, z0, z0+7, GRILLE, (.42, .45, .45), facing=-1)
    # The long west wall has the same working street face as the east flank.
    for a, b in ((-6, 18), (30, 56)):
        pane_x('flank ribbon window', -127.06, a, b, 8, 16.5, 'black', False, facing=-1)
        for y in range(a+6, b, 6):
            wall_x('flank ribbon mullion', -127.1, y-.12, y+.12, 8, 16.5, STEEL, DARK, facing=-1, detail=True)
    door('west flank staff', -127, 24, n=(-1, 0), fixture=True)
    for y in (70, 96):
        door('west annex staff', -127, y, n=(-1, 0))
    wall_x('west annex shutter', -127.06, 74, 92, .4, 15, GRILLE, (.42, .45, .45), facing=-1)
    round_prism('west downpipe', -127.5, 60, 0, PODIUM+2, .4, PAINT, (.30, .32, .32), 6)


def east_flank(rng):
    # The flank wall drops a level for the front of the wing, then a terrace on the block.
    grid_wall('east step wall', (124, -85), (134, -85), 0, 18, 5, 18, STONE, foot=0, amount=.5)
    grid_wall('east step wall', (134, -85), (134, -35), 0, 18, 5.5, 18, STONE, foot=0, amount=.5)
    grid_wall('east step wall', (134, -35), (124, -35), 0, 18, 5, 18, STONE, foot=0, amount=.5)
    step_block('east low', 124, 134, -85, -35, 18, 0, ((133, 134, -85, -35), (124, 133, -85, -84), (124, 133, -36, -35)),
               (((133.4, -84.4), (133.4, -35.6)), ((125, -84.4), (133.4, -84.4)), ((125, -35.6), (133.4, -35.6))))
    door('east step street', 134, -60, n=(1, 0), fixture=True)
    door('east step street', 129, -85, fixture=True)
    for a, b, lit in ((-78, -68, False), (-52, -40, True)):
        wall_x('east step window frame', 134.04, a-.4, b+.4, 3.6, 12.4, PANELS, (.46, .46, .44))
        pane_x('east step window', 134.08, a, b, 4, 12, 'black', lit)
        wall_x('east step window mullion', 134.12, (a+b)/2-.1, (a+b)/2+.1, 4, 12, STEEL, DARK, detail=True)


def service_block():
    """Low plant room on the west terrace: its front carries the wing's air conditioners."""
    x0, x1, y0, y1, z = -122, -96, -8, 10, PODIUM+10.2
    grid_wall('service block', (x0, y0), (x1, y0), PODIUM, z, 5, 10, TONES[1], foot=PODIUM)
    grid_wall('service block', (x0, y1), (x0, y0), PODIUM, z, 5, 10, TONES[1], foot=PODIUM)
    grid_wall('service block', (x1, y1), (x0, y1), PODIUM, z, 5, 10, TONES[1], foot=PODIUM)
    grid_wall('service block', (x1, y0), (x1, 0), PODIUM, z, 5, 10, TONES[1], foot=PODIUM)
    cuboid('service block roof', x0-.2, x1, y0-.2, y1+.2, z, z+.4, CAST, ROOF_DECK, omit='b')
    for x in (-115, -108.5, -102):
        ac_unit(x, y0-.02, PODIUM+3)
    wall_x('service block vent', x0-.05, -5.4, -.6, PODIUM+1.8, PODIUM+6, SLATS, LOUVRE, facing=-1)
    door('service block', -109, y1, PODIUM, (0, 1))


def east_block():
    """Low skylight box on the east wing's roof, glazed toward the street."""
    x0, x1, y0, y1, z = 98, 115, -24, 6, PODIUM+5.4
    cuboid('east skylight box', x0, x1, y0, y1, PODIUM, z, PANELS, TONES[1], omit='bfr')
    wall_x('east skylight kerb', x1, y0, y1, PODIUM, PODIUM+1, PANELS, EDGE)
    wall_y('east skylight kerb', x0, x1, y0, PODIUM, PODIUM+1, PANELS, EDGE)
    for i in range(5):
        a = x0+i*(x1-x0)/5
        pane_y('east skylight glass', a+.1, a+(x1-x0)/5-.1, y0, PODIUM+1, z-.3, 'pale', i == 2)
    for i in range(7):
        a = y0+i*(y1-y0)/7
        pane_x('east skylight glass', x1, a+.1, a+(y1-y0)/7-.1, PODIUM+1, z-.3, 'pale', i == 4)
    wall_y('east skylight head', x0, x1, y0, z-.3, z, PANELS, EDGE)
    wall_x('east skylight head', x1, y0, y1, z-.3, z, PANELS, EDGE)
    deck('east skylight roof', x0+.4, x1-.4, y0+.4, y1-.4, z+.02, PAINT, (.32, .34, .36))


def podium():
    rng = random.Random(54)
    # Wings: west, centre, east. The east wing's top is inset, leaving a planted ledge.
    fronts = (-85, -79, -69, -40)
    wing('west wing', -127, -65, fronts, -14, rng, top_hi=-70)
    wing('east wing', 61, 124, fronts, 18, rng, top_lo=60, top_hi=118, cheek_rear=(CORE_Y[0], None))
    centre_fronts = (-79, -73, -63, -46)
    wing('central wing', -34, 34, centre_fronts, 0, rng, ground='lobby', sun_room=SUN_ROOM_X, cheek_rear=(CORE_Y[0], CORE_Y[0]))
    lobby(-32, 32, -76.4)
    centre_glazing(centre_fronts)
    alley(-65, -34)
    alley(34, 61)
    # Solid shoulders between the wings and the cores: no view into the hollow podium.
    cuboid('west alley shoulder', -65, -60, -40, -14, 0, 50, PANELS, TONES[1], omit='b')
    cuboid('west shoulder cap', -70, -60, -40, -14, 49.5, 52, PANELS, TONES[1])
    wall_y('west shoulder back', -70, -60, -14, 52, PODIUM+2.75, PANELS, TONES[1])
    cuboid('east alley shoulder', 60, 63, -34, CORE_Y[0], 0, PODIUM+2.75, PANELS, TONES[1], omit='b')
    cuboid('east alley shoulder', 60, 63, CORE_Y[0], 0, 0, PODIUM-.2, PANELS, TONES[1], omit='b')
    # The central deck reaches the cores behind them, so their doors open onto it.
    for lo, hi in ((-40, -34), (34, 40)):
        deck('central deck return', lo, hi, -16, 0, PODIUM, CAST, TERRACE)
        wall_y('central deck return', lo, hi, -16, 20, PODIUM, PANELS, TONES[1])
        cuboid('central deck return kerb', lo, hi, -16, -15.4, PODIUM, PODIUM+2.75, PANELS, TONES[1], omit='b')
    # West: the 54 terrace runs from the wing back alongside the slab's flank.
    deck('upper terrace', -127, -60, -14, 0, PODIUM, CAST, TERRACE)
    deck('upper terrace', -127, -96, 0, SLAB_Y, PODIUM, CAST, TERRACE)
    grid_wall('west terrace wall', (-127, SLAB_Y), (-127, -14), 0, PODIUM+2.7, 6, 19, STONE, foot=0, amount=.5)
    grid_wall('west terrace wall', (-96, SLAB_Y), (-127, SLAB_Y), 36, PODIUM+2.7, 7, 20.7, STONE)
    cuboid('west terrace parapet', -127, -125.8, -14, SLAB_Y, PODIUM, PODIUM+2.7, PANELS, EDGE, omit='bl')
    cuboid('west terrace coping', -127.1, -125.8, -14, SLAB_Y, PODIUM+2.7, PODIUM+2.95, PANELS, (.92, .91, .86), omit='b')
    rail('west terrace rail', (-126.4, -14, PODIUM+2.9), (-126.4, SLAB_Y-1, PODIUM+2.9))
    cuboid('west terrace rear parapet', -127, -96, SLAB_Y-1.2, SLAB_Y, PODIUM, PODIUM+2.7, PANELS, EDGE, omit='bk')
    planter(-124.5, -98, -13, -10, PODIUM, 3.2, rng)
    service_block()
    east_block()
    wall_y('east terrace back', 96, 118, 18, 36, PODIUM+2.75, PANELS, STONE, facing=1)
    cuboid('east deck parapet', 96, 118, 17, 18, PODIUM, PODIUM+2.75, PANELS, EDGE, omit='bk')
    # Planted ledge beside the inset top of the east wing.
    deck('east ledge', 118, 121.8, -40, 18, 49.7, CAST, ROOF_DECK)
    planter(118.3, 121.6, -38, 16, 49.7, 3.2, rng, density=1)
    cuboid('east ledge front', 118, 121.8, -40.6, -40, 47.5, 53, PANELS, TONES[1], omit='b')
    wall_y('east ledge back', 118, 124, 18, 36, 53, PANELS, STONE, facing=1)
    wall_y('east ledge back', 118, 121.8, 17.9, 49.7, 53, PANELS, EDGE)
    for x, side in ((-65, 1), (61, -1)):
        pane_x('cheek window', x+side*.06, -60, -52, 30, 39, 'black', False, facing=side)
        wall_x('cheek window frame', x+side*.04, -60.4, -51.6, 29.6, 39.4, PANELS, (.46, .46, .44), facing=side)
    # The cores serve each podium deck; the slab's corridors reach the rear terraces.
    door('west deck', -60, -8, PODIUM, (-1, 0))
    door('central deck', -40, -8, PODIUM, (1, 0))
    door('central deck', 40, -8, PODIUM, (-1, 0))
    door('east deck', 60, -8, PODIUM, (1, 0))
    door('west terrace', -96, 26, PODIUM, (-1, 0))
    door('east terrace', 96, 30, 36, (1, 0))
    door('step terrace', -127, -74, 18, (-1, 0))
    door('step terrace', 124, -50, 18, (1, 0))
    grid_wall('east flank face', (124.03, -66), (124.03, 18), 0, 42, 5.5, 14, STONE, foot=0, top=42, amount=.5)
    west_flank(rng)
    east_flank(rng)
    annex(rng)


def annex(rng):
    x0, x1, y0, y1 = -127, 124, SLAB_Y, 118
    top = 36
    grid_wall('annex rear wall', (98, y1), (x0, y1), 0, top+2.2, 8, 19, STONE, foot=0, amount=.5)
    grid_wall('annex rear wall', (x1, y1), (98, y1), 0, 28, 6, 14, TONES[2], foot=0, amount=.5)
    cuboid('garden kerb', 98, x1, y1-1.2, y1, 25, 28, PANELS, EDGE, omit='bk')
    cuboid('garden kerb', x1-1.2, x1, 88, y1, 25, 28, PANELS, EDGE, omit='br')
    cuboid('garden coping', 98, x1+.1, y1-1.3, y1+.1, 28, 28.3, PANELS, (.92, .91, .86), omit='b')
    cuboid('garden coping', x1-1.3, x1+.1, 88, y1, 28, 28.3, PANELS, (.92, .91, .86), omit='b')
    deck('garden bed', 98, x1-1.2, 88, y1-1.2, 26.4, SOIL, (.24, .22, .18))
    for _ in range(26):
        foliage_clump(rng.uniform(101, x1-3), rng.uniform(91, y1-3), 26, rng.uniform(3.4, 5.6), rng.uniform(2, 3.6), rng)
    # The corner block is lower: its deck is a level down, a raised garden behind a tall kerb.
    grid_wall('annex side wall', (x1, 18), (x1, 88), 0, top+2.2, 5.5, 19, STONE, foot=0, top=top+2.2, amount=.5)
    grid_wall('annex side wall', (x1, 88), (x1, y1), 0, 28, 5.5, 14, TONES[2], foot=0, amount=.5)
    cuboid('garden wall', 98, x1, 87, 88, 18, top+2.2, PANELS, TONES[2], omit='b')
    cuboid('garden wall', 97, 98, 87, y1, 18, top+2.2, PANELS, TONES[2], omit='b')
    deck('garden wall inner', 98, x1-1.2, 88, y1-1.2, 18, CAST, (.261, .261, .261))
    round_prism('east downpipe', x1+.5, 88, 0, top+2, .4, PAINT, (.30, .32, .32), 6)
    grid_wall('annex side wall', (x0, y1), (x0, SLAB_Y), 0, top+2.2, 7, 19, STONE, foot=0, amount=.5)
    deck('annex roof', x0, 98, y0, y1, top, CAST, ROOF_DECK)
    deck('east terrace', 96, x1, 18, 88, top, CAST, ROOF_DECK)
    cuboid('annex parapet', x0, 98, y1-1.2, y1, top, top+2.2, PANELS, EDGE, omit='bk')
    cuboid('annex parapet coping', x0-.1, 98, y1-1.3, y1+.1, top+2.2, top+2.5, PANELS, (.92, .91, .86), omit='b')
    cuboid('annex parapet', x0, x0+1.2, y0, y1-1.2, top, top+2.2, PANELS, EDGE, omit='bl')
    cuboid('annex parapet coping', x0-.1, x0+1.3, y0, y1-1.2, top+2.2, top+2.5, PANELS, (.92, .91, .86), omit='b')
    cuboid('east parapet', x1-1.2, x1, 18, 88, top, top+2.2, PANELS, EDGE, omit='br')
    cuboid('east parapet coping', x1-1.3, x1+.1, 18, 88, top+2.2, top+2.5, PANELS, (.92, .91, .86), omit='b')
    # Plant and rooflights over the service floors, reached from the slab's rear corridor.
    door('annex roof', 0, SLAB_Y, top, (0, 1))
    for x in (-84, -30, 24, 78):
        cuboid('annex rooflight kerb', x-9, x+9, 86, 98, top, top+1.6, PANELS, EDGE, omit='b')
        deck('annex rooflight glass', x-8.4, x+8.4, 86.6, 97.4, top+1.62, PALE_GLASS, VOID, light='off')
    cuboid('annex plant', -112, -94, 76, 96, top, top+6, PAINT, (.33, .35, .35), omit='b')
    wall_y('annex plant louvre', -111, -95, 76, top+1, top+5, SLATS, LOUVRE, facing=-1)
    # Inner terrace wall, with rails on the rear and east, and a raised corner planter.
    rail('annex rear rail', (98, 88, top+2.2), (x1-.6, 88, top+2.2))
    rail('annex rear rail', (98, 88, top+2.2), (98, y1, top+2.2))
    rail('annex east rail', (x1-.6, 20, top+2.5), (x1-.6, 88, top+2.5))
    planter(x1-8, x1-1.4, 62, 86, top, 3, rng)
    # East flank: a dark ribbon, staff doors and the loading shutter.
    for a, b in ((-36, -14), (26, 50), (58, 76)):
        pane_x('flank ribbon window', x1+.06, a, b, 8, 16.5, 'black', False)
        for y in range(a+6, b, 6):
            wall_x('flank ribbon mullion', x1+.1, y-.12, y+.12, 8, 16.5, STEEL, DARK, detail=True)
    for y, lit in ((10, True), (54, True), (80, False)):
        door('flank staff', x1, y, n=(1, 0), fixture=lit)
    wall_x('flank loading shutter', x1+.06, 90, 112, .4, 16, GRILLE, (.42, .45, .45))
    wall_x('flank loading bar', x1+.1, 90, 112, .4, 1.2, 'structures/common/hazard-stripes', (1, 1, 1))
    # Rear: quiet windows on a storey grid, plant intake and loading doors.
    for i, x in enumerate(range(-112, 90, 28)):  # The garden's lower wall carries no windows.
        pane_y('annex rear window', x-8, x+8, y1+.06, 21, 30, 'black', i % 3 == 0, facing=1)
        if i % 2 and abs(x) > 40:
            wall_y('annex rear grille', x-8, x+8, y1+.06, 3, 12, GRILLE, (.46, .49, .48), facing=1)
    wall_y('annex rear shutter', -20, 20, y1+.06, .4, 15, GRILLE, (.44, .47, .47), facing=1)
    door('annex rear', 30, y1, n=(0, 1), fixture=True)
    # In the gaps between the rear windows.
    for x in (-124, -42, 42):
        round_prism('annex downpipe', x, y1+.5, 0, top+2, .4, PAINT, (.30, .32, .32), 6)


# -- Helpers, assembly and export -----------------------------------------------------------

def helpers():
    def box(name, x0, x1, y0, y1, top):
        civic.helper(name, [(x0, y0+SHIFT_Y), (x1, y0+SHIFT_Y), (x1, y1+SHIFT_Y), (x0, y1+SHIFT_Y)], top)
    box('slab', -96, 96, 0, SLAB_Y, ROOF)
    for x0, x1 in CORES:
        box('core', x0, x1, CORE_Y[0], CORE_Y[1], CORE_TOP-6)  # Top six units are a solid head.
    for lo, hi, y, rows, top in ((-127, -65, -85, -63, -40), (-34, 34, -79, -57, -46), (61, 124, -85, -63, -40)):
        box('wing street storey', lo, hi, y, 0, LEVEL)
        box('wing occupied rows', lo, hi, rows, 0, 2*LEVEL)
        box('wing upper', lo, min(hi, 118), top, 0, 3*LEVEL)
    box('west upper', -127, -96, 0, SLAB_Y, 3*LEVEL)
    box('east upper', 60, 118, -14, 18, 3*LEVEL)
    box('alley block', -65, -34, -70, -14, LEVEL)
    box('alley block', 34, 61, -70, -14, LEVEL)
    box('east low step', 124, 134, -85, -35, LEVEL)
    box('west low step', -146, -127, -85, -63, LEVEL)
    box('west high step', -146, -127, -63, -14, 2*LEVEL)
    box('rear annex', -127, 124, SLAB_Y, 118, 2*LEVEL)
    box('east terrace', 96, 124, 18, SLAB_Y, 2*LEVEL)


def weathered_material(key, colour, cache={}):
    """The object's shared finish, previewed with its per-vertex grime."""
    if (key, colour) not in cache or cache[key, colour].name not in bpy.data.materials:
        mat = shared.material(key, colour).copy()
        mat.name += ' weathered'
        build_preview(mat, shared.TEXTURES/(key+'.tres'), shared.TEXTURES, vertex_colors=True)
        cache[key, colour] = mat
    return cache[key, colour]


def surface_uvs(obj):
    """Panels are placed by the storey grid; louvre slats and shrub leaves have their own scale."""
    key = obj['board_material']
    if key not in (PANELS, BUSH, SLATS):
        return
    repeat = 4 if key == SLATS else PANEL_REPEAT  # Two slats a repeat: one every 2 units.
    uv = obj.data.uv_layers.new(name='UVMap')
    verts = obj.data.vertices
    for face in obj.data.polygons:
        n = face.normal
        for li in face.loop_indices:
            co = verts[obj.data.loops[li].vertex_index].co
            if key == BUSH:
                uv.data[li].uv = (co.x+co.z*.6)/7, (co.y+co.z*.6)/7
                continue
            if abs(n.z) > max(abs(n.x), abs(n.y)):
                uv.data[li].uv = co.x/repeat, co.y/repeat
            elif abs(n.x) > abs(n.y):
                uv.data[li].uv = co.y/repeat, (co.z-PODIUM)/repeat
            else:
                uv.data[li].uv = co.x/repeat, (co.z-PODIUM)/repeat


def flush():
    for (name, key, colour, detail, light), b in bins.items():
        obj = mesh(name, [(x, y+SHIFT_Y, z) for x, y, z in b['v']], b['f'], key, colour, detail)
        # Every exposed cast wall takes the tint; the cores stay raw, like the citadel's ribs.
        if key == PANELS and (colour in TONES or colour in (STONE, EDGE)) and 'core' not in name:
            obj['building_paint'] = True
        if min(b['w']) < .999:
            attribute = obj.data.color_attributes.new('weather', 'FLOAT_COLOR', 'POINT')
            for item, w in zip(attribute.data, b['w']):
                g = linear(w)
                item.color = (g, g, g, 1)
            obj.data.materials[0] = weathered_material(key, colour)
        if light == 'night':
            shared.emissive(obj, WINDOW_LIGHT, night=True)
        elif light == 'dim':
            shared.emissive(obj, DIM_LIGHT, night=True)
        elif light == 'off':
            shared.emission_off(obj)
        elif light:
            shared.emissive(obj, light)
        if key == BUSH:
            obj.data.polygons.foreach_set('use_smooth', [True]*len(obj.data.polygons))
        surface_uvs(obj)
    bins.clear()


def build():
    old = bpy.data.scenes.get(SCENE)
    if old:
        bpy.data.batch_remove([obj for obj in old.objects if len(obj.users_scene) == 1])
    weathered_material.__defaults__[0].clear()
    shared.fresh(SCENE)
    bins.clear()
    fixtures.clear()
    slab()
    for x0, x1 in CORES:
        core(x0, x1)
    rooftop()
    podium()
    flush()
    for text, x, y, z, size in (('A', -44, -71.14, 15, 2.2), ('B', 52, -71.14, 15, 2.2), ('L', -.8, -79.14, 15, 2.2)):
        civic.marking(text, (x, y+SHIFT_Y, z), size=size)
    helpers()
    for obj in shared.volumes:
        obj.hide_set(True)
    bpy.context.view_layer.update()
    for obj in shared.objects:
        shared.project_uvs(obj)
    scene = bpy.context.scene
    scene['asset_id'] = 'buildings/authored/'+NAME
    scene['hex_width'] = 83.125
    scene['hex_height'] = 72
    scene['level_height'] = LEVEL
    scene['structural_levels'] = ROOF//LEVEL
    scene['height_metres'] = ROOF/3
    scene['concept'] = str(REFERENCE)
    # Entrance lamps light the street after dusk. glTF is Y-up.
    scene['night_lights'] = json.dumps([{'position': [x, z, -(y+SHIFT_Y)], 'color': [1, .64, .29], 'power': .65, 'size': 13}
                                        for x, y, z in fixtures])
    return {'objects': len(shared.objects), 'helpers': len(shared.volumes),
            'polygons': sum(len(o.data.polygons) for o in shared.objects), 'fixtures': len(fixtures)}


def export():
    bpy.context.view_layer.update()
    levels = {i: shared.export_model(shared.objects, NAME+'-lod'+str(i), level=i) for i in (0, 1, 2)}
    volumes = shared.export_model(shared.volumes, NAME, helper=True)
    stats = {i: {'vertices': sum(len(m['vertices'])//12 for m in level['meshes']),
                 'triangles': sum(len(p['indices'])//3 for m in level['meshes'] for p in m['parts'])}
             for i, level in levels.items()}
    assert all(s['vertices'] < 65535 for s in stats.values()), stats
    write_glb(shared.DEST/(NAME+'.glb'), levels=levels, groups={'building_volumes': volumes},
              extras={'mmNightLights': json.loads(bpy.context.scene['night_lights'])})
    bpy.data.libraries.write(str(shared.SOURCE/(NAME+'.blend')), {bpy.context.scene}, fake_user=True)
    return stats


YAW, PITCH = math.radians(28), math.radians(16)


def studio(view='reference', size=1080, night=False):
    """One review studio for every checkpoint. 'reference' matches the guide image's framing."""
    scene = bpy.context.scene
    collection = next((c for c in scene.collection.children if c.name.startswith('Habitat review studio')), None)
    if not collection:
        collection = bpy.data.collections.new('Habitat review studio')
        scene.collection.children.link(collection)
        camera = bpy.data.objects.new('Habitat review camera', bpy.data.cameras.new('Habitat review camera'))
        collection.objects.link(camera)
        sun = bpy.data.objects.new('Habitat sun', bpy.data.lights.new('Habitat sun', 'SUN'))
        collection.objects.link(sun)
        sun.data.angle = math.radians(30)
        sun.rotation_euler = (Vector((0, 0, 0))-Vector((-.55, -.75, 1))).to_track_quat('-Z', 'Y').to_euler()
        data = bpy.data.meshes.new('Habitat review ground')
        data.from_pydata([(-2000, -2000, -.3), (2000, -2000, -.3), (2000, 2000, -.3), (-2000, 2000, -.3)], [], [(0, 1, 2, 3)])
        ground = bpy.data.objects.new('Habitat review ground', data)
        collection.objects.link(ground)
        ground.data.materials.append(shared.material(shared.FLAT, (.82, .82, .84)))
    camera = next(obj for obj in collection.objects if obj.type == 'CAMERA')
    sun = next(obj for obj in collection.objects if obj.type == 'LIGHT')
    scene.camera = camera
    y = SHIFT_Y
    views = {  # target, yaw, pitch, ortho width
        'reference': ((-15, y, 114.3), YAW, PITCH, 402.4),
        'front': ((0, y, 120), 0, 0, 340),
        'back': ((0, y, 120), math.pi, 0, 340),
        'right': ((0, y+16, 120), math.pi/2, 0, 340),
        'left': ((0, y+16, 120), -math.pi/2, 0, 340),
        'top': ((0, y+16, 0), 0, math.pi/2-1e-3, 340),
        'game': ((0, y+16, 100), math.radians(45), math.radians(35.26), 400),
        'podium': ((0, y-30, 40), YAW, PITCH, 300),
        'east_block': ((130, y-55, 22), math.radians(50), math.radians(22), 90),
        'west_steps': ((-135, y-55, 28), math.radians(-40), math.radians(24), 90),
        'entrance': ((0, y-76, 11), math.radians(8), math.radians(4), 90),
        'alley': ((-50, y-50, 28), math.radians(14), math.radians(20), 70),
    }
    target, yaw, pitch, width = views[view]
    target = Vector(target)
    camera.location = target+1500*Vector((math.sin(yaw)*math.cos(pitch), -math.cos(yaw)*math.cos(pitch), math.sin(pitch)))
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = width
    camera.data.clip_end = 5000
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = size
    scene.render.resolution_y = round(size*369/540) if view in ('reference', 'podium') else size
    scene.render.resolution_percentage = 100
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes['Background']
    background.inputs[0].default_value = (.80, .81, .84, 1)
    background.inputs[1].default_value = .12 if night else 1.15
    sun.data.energy = .15 if night else 3.2
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = .25
    scene.render.image_settings.file_format = 'PNG'
    for obj in shared.objects:
        if obj.get('building_night_emission'):
            obj.data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value = 0 if obj.get('building_emission_off') else int(night)
    return view
