"""Civic Habitat 02, Commercial Center, Offices and Industrial Works: brutalist blocks from their sheets in references/civic-*.png.

Run: blender -b --factory-startup --python civic_blocks.py -- <name> [<sheet folder>]
Writes data/models/buildings/authored/civic-<name>.glb, and with a folder a four-view sheet laid out like the reference's.
Every block is a closed box with its facade laid on it, so nothing can be seen through. The sheets' window and gallery rows are
visual detail, as on civic-habitat; gameplay floors stay 18 units apart.
Facades are placed on a wall: (x, y, n) with n its outward axis, a running left to right seen from outside and d outward.
Far levels keep the real pieces, less the fine ones (detail flags, then far_piece): building_lod's merging shreds sheets of glass and fins.
"""
import json
import math
import random
import re
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import authored_examples as shared
import civic_buildings as civic
import civic_habitat as h
from civic_citadel import ALLOY, DARK, GLAZING
from civic_habitat import (CAST, EDGE, FRAME, GRILLE, HANDRAIL, PAINT, PALE_GLASS, PANELS, SLATS, SOIL, STEEL, TONES, LOUVRE,
                           add, cuboid, deck, disc, door, foliage_clump, lamp, rail, round_prism, soffit, wall_quad)
from glb_geometry import write_glb
from utopia_buildings import sheet, tube

LEVEL = 18
STONE = TONES[0]
SOUTH, EAST, NORTH, WEST = (0, -1), (1, 0), (0, 1), (-1, 0)
HAZARD = 'structures/common/hazard-stripes'
GROUND = .4  # The apron's top: doors and shutters stand on it.
COPING = (.92, .91, .86)
SHUTTER = (.72, .74, .74)
AMBER = (.50, .42, .26)
AMBER_LIGHT = (1, .72, .35)
TEAL_GLASS = (.52, .68, .64)
PIPE = (.62, .65, .64)
RED_LIGHT = (1, .035, .012)
# Parts left out of the farthest level, by name.
FINE = ('rail', 'post', 'lamp', 'mullion', 'frame', 'bracket', 'ladder', ' bar', 'joint', 'collar', 'spoke', 'hub', 'stair flight', 'half landing', 'stay',
        'pedestal', 'vent', 'curb', 'door', 'guard', 'seam', 'bench', 'bollard', 'antenna', 'mast', ' light', 'pipe', 'head box', 'transom', 'planting', 'riser', 'sill', 'ceiling', 'floor', 'stall', 'spandrel')


def far_piece(obj):
    """Whether a part stays at the farthest level. A part named fine goes unless one of its faces is a surface: a coping over a whole roof is a roof."""
    name = re.sub(r'\.\d+$', '', obj.name)
    if 'gallery' in name and name.endswith(' window'):
        return bool(obj.get('building_night_emission', False))
    if not any(word in name for word in FINE):
        return True
    verts = obj.data.vertices
    return any(min((verts[a].co-verts[b].co).length for a, b in face.edge_keys) >= FAR_SURFACE for face in obj.data.polygons)
FAR_SURFACE = 3.5
DARK_RECESS = (.42, .42, .40)
ROOF_TONE = (.94, .93, .88)


# -- Facade kit ---------------------------------------------------------------------------------

def at(wall, a, d=0.0):
    x, y, n = wall
    return x-n[1]*a+n[0]*d, y+n[0]*a+n[1]*d


def quad(name, wall, a0, a1, z0, z1, off, key=PANELS, colour=STONE, **flags):
    wall_quad(name, wall[0], wall[1], wall[2], a0, a1, z0, z1, off, key, colour, **flags)


def on_wall(name, wall, a0, a1, d0, d1, z0, z1, key=PANELS, colour=STONE, front=True, whole=False, under=False, **flags):
    """A box standing on a wall, without the faces against it (unless whole) and the ground (unless under)."""
    xs, ys = zip(*(at(wall, a, d) for a in (a0, a1) for d in (d0, d1)))
    back, ahead = {SOUTH: 'kf', NORTH: 'fk', EAST: 'lr', WEST: 'rl'}[wall[2]]
    omit = ('' if under else 'b')+('' if whole else back)+('' if front else ahead)
    cuboid(name, min(xs), max(xs), min(ys), max(ys), z0, z1, key, colour, omit=omit, **flags)


def face(name, wall, a0, a1, z0, z1, du=8.0, dv=13.5, colour=STONE, off=0.0, **kw):
    """A concrete wall with grime at each grid vertex."""
    kw.setdefault('amount', .4)
    h.grid_wall(name, at(wall, a0, off), at(wall, a1, off), z0, z1, du, dv, colour, **kw)


def cast_band(name, wall, a0, a1, d, z0, z1, colour=STONE, du=8.0):
    """A cast upstand standing d off the wall, streaked in front and soot-dark toward its underside, with a coping."""
    face(name, wall, a0, a1, z0, z1, du, z1-z0, colour, off=d, shade=(.92, 1.02))
    on_wall(name, wall, a0, a1, 0, d, z0, z1, PANELS, colour, front=False)
    on_wall(name+' coping', wall, a0-.02, a1+.02, -.12, d+.12, z1, z1+.25, PANELS, COPING)
    xs, ys = zip(*(at(wall, a, q) for a in (a0, a1) for q in (0, d)))
    soffit(name+' soffit', min(xs), max(xs), min(ys), max(ys), z0)


def pane(name, wall, a0, a1, z0, z1, kind='black', lit=False, off=.06):
    key, colour = (PALE_GLASS, TEAL_GLASS) if kind == 'teal' else h.glass_finish(kind)
    quad(name, wall, a0, a1, z0, z1, off, key, colour, light=lit if lit == 'dim' else 'night' if lit else 'off')


def ribbon(name, wall, a0, a1, z0, z1, rng, pitch=5.5, lit=.3, kind='black'):
    """A strip window in a dark frame: one pane per bay, with mullions."""
    quad(name+' frame', wall, a0-.5, a1+.5, z0-.5, z1+.5, .03, PANELS, (.46, .46, .44))
    count = max(1, round((a1-a0)/pitch))
    step = (a1-a0)/count
    for i in range(count):
        pane(name, wall, a0+i*step, a0+(i+1)*step, z0, z1, kind, lit if lit == 'dim' else rng.random() < lit)
        if i:
            quad(name+' mullion', wall, a0+i*step-.14, a0+i*step+.14, z0, z1, .1, STEEL, (.50, .52, .52), detail=True)


def louvre(name, wall, a0, a1, z0, z1):
    quad(name+' frame', wall, a0-.5, a1+.5, z0-.5, z1+.5, .03, PANELS, (.40, .40, .38))
    quad(name, wall, a0, a1, z0, z1, .06, SLATS, LOUVRE)


def shutter(name, wall, a0, a1, z1, rng):
    """A loading door: a dark roller shutter in a recess, hazard-striped guides and an amber work light over it."""
    quad(name, wall, a0, a1, GROUND, z1, .05, SLATS, SHUTTER)
    on_wall(name+' head box', wall, a0, a1, 0, 1.1, z1-.6, z1+1.4, PAINT, (.42, .44, .45))
    for a in (a0, a1-1.2):
        quad(name+' guard', wall, a, a+1.2, GROUND, GROUND+7, .12, HAZARD, (1, 1, 1))
    middle = (a0+a1)/2
    quad(name+' work light', wall, middle-6.5, middle+6.5, z1+2.2, z1+3, .15, PAINT, AMBER, light=AMBER_LIGHT)
    x, y = at(wall, middle, 2)
    h.fixtures.append((x, y, z1+2.6))


def double_door(name, wall, a, z=GROUND, fixture=True):
    x0, y0 = at(wall, a-2.15)
    x1, y1 = at(wall, a+2.15)
    door(name, x0, y0, z, wall[2], lit=False)
    door(name, x1, y1, z, wall[2], lit=False)
    x, y = at(wall, a)
    lamp(x, y, z+8.4, wall[2], fixture=fixture)


def extrude(name, outline, wall, a0, a1, key=PANELS, colour=STONE, **flags):
    """A (d, z) outline run along a wall from a0 to a1, closed at both ends."""
    if sum(p[0]*q[1]-p[1]*q[0] for p, q in zip(outline, outline[1:]+outline[:1])) < 0:
        outline = list(reversed(outline))
    n = len(outline)
    verts = [(*at(wall, a, d), z) for a in (a0, a1) for d, z in outline]
    faces = [tuple(range(n)), tuple(range(2*n-1, n-1, -1))]
    faces += [(i, n+i, n+(i+1) % n, (i+1) % n) for i in range(n)]
    add(name, key, colour, verts, faces, **flags)


def frustum(name, low, high, z0, z1, key=PANELS, colour=STONE, **flags):
    """A battered block between two plan rectangles (x0, x1, y0, y1)."""
    corners = lambda b: [(b[0], b[2]), (b[1], b[2]), (b[1], b[3]), (b[0], b[3])]
    verts = [(x, y, z0) for x, y in corners(low)]+[(x, y, z1) for x, y in corners(high)]
    add(name, key, colour, verts, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)], **flags)


def tapered(name, yf, yr, front, rear, zf, zr, base, key=PANELS, colour=STONE, **flags):
    """A block from yf to yr whose (left, right) x changes from front to rear, its top sloping from zf to zr."""
    verts = [(front[0], yf, base), (front[1], yf, base), (rear[1], yr, base), (rear[0], yr, base),
             (front[0], yf, zf), (front[1], yf, zf), (rear[1], yr, zr), (rear[0], yr, zr)]
    add(name, key, colour, verts, [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)], **flags)


def plant_box(name, x0, x1, y0, y1, z, height, fans, rows=1):
    """A grey roof unit on a curb: louvred sides, fans with spokes in its top."""
    top = z+height
    cuboid(name+' curb', x0-.8, x1+.8, y0-.8, y1+.8, z, z+.9, PANELS, EDGE, omit='b')
    cuboid(name, x0, x1, y0, y1, z+.9, top, PAINT, (.46, .47, .46), omit='bt')
    deck(name+' top', x0, x1, y0, y1, top, PAINT, (.52, .54, .54))
    for wall, a0, a1 in (((0, y0, SOUTH), x0, x1), ((x1, 0, EAST), y0, y1), ((0, y1, NORTH), -x1, -x0), ((x0, 0, WEST), -y1, -y0)):
        cells = max(1, round((a1-a0)/9))
        for i in range(cells):
            quad(name+' louvre', wall, a0+(a1-a0)*i/cells+.5, a0+(a1-a0)*(i+1)/cells-.5, z+1.7, top-.8, .05, SLATS, LOUVRE)
    width, depth = (x1-x0)/fans, (y1-y0)/rows
    radius = min(width, depth)/2-.8
    for i in range(fans):
        for j in range(rows):
            x, y = x0+(i+.5)*width, y0+(j+.5)*depth
            disc(name+' fan well', x, y, top+.04, radius, 'z', PAINT, (.07, .08, .08), 12)
            ring = lambda r, k: (x+r*math.cos(k*math.tau/12), y+r*math.sin(k*math.tau/12), top+.08)
            for k in range(12):
                add(name+' fan collar', PAINT, (.64, .66, .66), [ring(radius, k), ring(radius+.5, k), ring(radius+.5, k+1), ring(radius, k+1)], [(0, 1, 2, 3)], detail=True)
            for k in range(3):
                c, d = math.cos(k*math.pi/3+.4), math.sin(k*math.pi/3+.4)
                w = .16
                add(name+' fan spoke', STEEL, (.60, .62, .62), [(x-radius*c+w*d, y-radius*d-w*c, top+.07), (x+radius*c+w*d, y+radius*d-w*c, top+.07), (x+radius*c-w*d, y+radius*d+w*c, top+.07), (x-radius*c-w*d, y-radius*d+w*c, top+.07)], [(0, 1, 2, 3)], detail=True)
            disc(name+' fan hub', x, y, top+.1, radius*.22, 'z', PAINT, (.40, .42, .42), 6, detail=True)


def solar(name, x0, x1, y0, y1, z, cols, rows):
    cuboid(name+' frame', x0, x1, y0, y1, z, z+1, STEEL, ALLOY, omit='b')
    deck(name, x0+.3, x1-.3, y0+.3, y1-.3, z+1.02, h.DARK_GLASS, GLAZING, light='off')
    for i in range(1, cols):
        x = x0+(x1-x0)*i/cols
        deck(name+' line', x-.08, x+.08, y0+.3, y1-.3, z+1.05, STEEL, ALLOY, detail=True)
    for j in range(1, rows):
        y = y0+(y1-y0)*j/rows
        deck(name+' line', x0+.3, x1-.3, y-.08, y+.08, z+1.05, STEEL, ALLOY, detail=True)


def beacon(x, y, z):
    round_prism('beacon pedestal', x, y, z, z+1.6, .5, STEEL, DARK, 6)
    round_prism('red obstruction beacon', x, y, z+1.6, z+3, .9, PAINT, (.85, .08, .025), 8, light=RED_LIGHT)


def mast(x, y, z, height):
    """A lattice antenna: a plinth, a stem and three pairs of arms."""
    cuboid('mast plinth', x-2.5, x+2.5, y-2.5, y+2.5, z, z+1.4, PANELS, EDGE, omit='b')
    cuboid('mast', x-.3, x+.3, y-.3, y+.3, z+1.4, z+height, STEEL, ALLOY, omit='b')
    for k in (.55, .72, .88):
        arm = z+height*k
        cuboid('mast arm', x-2.6, x+2.6, y-.14, y+.14, arm, arm+.28, STEEL, ALLOY)
        for side in (-2.6, 2.6):
            cuboid('mast antenna', x+side-.2, x+side+.2, y-.2, y+.2, arm-1.8, arm+1.8, PAINT, (.72, .74, .72), detail=True)


def ladder_on(name, wall, a, z0, z1):
    """A ladder on any wall: uprights survive the first far level, rungs do not."""
    for side in (-.9, .9):
        on_wall(name+' upright', wall, a+side-.09, a+side+.09, .5, .68, z0, z1+1.2, STEEL, HANDRAIL)
    z = z0+.7
    while z < z1+.5:
        on_wall(name+' rung', wall, a-.9, a+.9, .52, .66, z-.06, z+.06, STEEL, HANDRAIL, detail=True)
        z += 1.5


def roof_rim(name, x0, x1, y0, y1, z, height=2.4):
    """A parapet and coping round a roof, seen from both sides."""
    for side, wall, a0, a1 in (('s', (0, y0, SOUTH), x0, x1), ('e', (x1, 0, EAST), y0, y1), ('n', (0, y1, NORTH), -x1, -x0), ('w', (x0, 0, WEST), -y1, -y0)):
        on_wall(f'{name} parapet {side}', wall, a0, a1, -1, 0, z, z+height, PANELS, EDGE, whole=True)
        on_wall(f'{name} coping {side}', wall, a0-.1, a1+.1, -1.1, .1, z+height, z+height+.25, PANELS, COPING)


def block(name, x0, x1, y0, y1, z0, z1, sides='sewn', du=8.0, dv=13.5, colour=STONE, rim=2.4, foot=None):
    """A closed box: grimy walls on the named sides, a roof above the game's floor and a parapet. Gives its walls by side."""
    walls = {'s': ((0, y0, SOUTH), x0, x1), 'e': ((x1, 0, EAST), y0, y1), 'n': ((0, y1, NORTH), -x1, -x0), 'w': ((x0, 0, WEST), -y1, -y0)}
    for side in sides:
        wall, a0, a1 = walls[side]
        face(f'{name} {side}', wall, a0, a1, z0, z1, du, dv, colour, foot=0 if z0 == 0 else foot, top=z1)
    deck(name+' roof', x0, x1, y0, y1, z1+.3, CAST, ROOF_TONE)
    if rim:
        roof_rim(name, x0, x1, y0, y1, z1, rim)
    return {side: walls[side][0] for side in walls}


def plan_of(wall, a0, a1, d0, d1):
    """A wall's strip as a plan rectangle (x0, x1, y0, y1)."""
    xs, ys = zip(*(at(wall, a, d) for a in (a0, a1) for d in (d0, d1)))
    return min(xs), max(xs), min(ys), max(ys)


def fin_wall(name, wall, a0, a1, z0, z1, rng, pitch=12.8, rows=10, depth=3.6, lit=.28):
    """Deep concrete fins over rows of dark glass and pale spandrels."""
    bays = max(1, round((a1-a0)/pitch))
    step = (a1-a0)/bays
    storey = (z1-z0)/rows
    quad(name+' back', wall, a0, a1, z0, z1, .02, PANELS, (.58, .60, .58))
    for i in range(bays):
        b0, b1 = a0+i*step+1.1, a0+(i+1)*step-1.1
        for j in range(rows):
            z = z0+j*storey
            pane(name+' glass', wall, b0, b1, z+storey*.36, z+storey*.96, 'black', rng.random() < lit)
            quad(name+' spandrel', wall, b0, b1, z+storey*.04, z+storey*.36, .9, PANELS, (.58, .60, .58))
            on_wall(name+' spandrel side', wall, b0, b1, 0, .9, z+storey*.36, z+storey*.38, PANELS, (.46, .48, .46), detail=True)
    for i in range(bays+1):
        a = a0+i*step
        on_wall(name+' fin', wall, a-1.1, a+1.1, 0, depth, z0, z1, PANELS, TONES[1])


def galleries(name, wall, a0, a1, z0, rows, storey, rng, recess=7.0, lit=.3):
    """Access galleries cut into a wall: a low upstand and rail at each storey, long runs of dark glass and doors at the back, piers far apart with an amber lamp."""
    x0, x1, y0, y1 = plan_of(wall, a0, a1, -recess, 0)
    bays = max(1, round((a1-a0)/32))
    step = (a1-a0)/bays
    for j in range(rows):
        z = z0+j*storey
        tone = TONES[rng.randrange(3)]
        on_wall(name+' upstand', wall, a0, a1, -1.2, 0, z-1.3, z+1.9, PANELS, tone, whole=True, under=True)
        on_wall(name+' upstand coping', wall, a0-.02, a1+.02, -1.3, .1, z+1.9, z+2.1, PANELS, COPING)
        px, py = at(wall, a0, -.6), at(wall, a1, -.6)
        rail(name+' rail', (px[0], px[1], z+2.1), (py[0], py[1], z+2.1), 2.2, 8)
        deck(name+' floor', x0, x1, y0, y1, z, CAST, (.55, .55, .53))
        soffit(name+' ceiling', x0, x1, y0, y1, z+storey-1.3)
        quad(name+' back', wall, a0, a1, z, z+storey-1.3, -recess, PANELS, (.32, .32, .31))
        for i in range(bays):
            b0, b1 = a0+i*step, a0+(i+1)*step
            cells = max(1, round((b1-b0-2)/6.5))
            width = (b1-b0-2)/cells
            for c in range(cells):
                p0 = b0+1+c*width
                if c % 4 == 3:
                    quad(name+' door', wall, p0+.3, p0+width-.3, z+.1, z+storey-3.2, -recess+.06, PAINT, (.26, .30, .30))
                else:
                    pane(name+' window', wall, p0+.15, p0+width-.15, z+.2, z+storey-2.2, 'black', rng.random() < lit, off=-recess+.06)
            if i < bays-1:
                on_wall(name+' pier', wall, b1-.6, b1+.6, -recess, -1.2, z, z+storey-1.3, PANELS, TONES[1])
                x, y = at(wall, b1, -1.2)
                wall_quad(name+' lamp', x, y, wall[2], -.3, .3, z+storey-4.6, z+storey-3.6, .06, PAINT, AMBER, light=AMBER_LIGHT)
    for a, b in ((a0-1.55, a0), (a1, a1+1.55)):
        on_wall(name+' end', wall, a, b, -recess, 0, z0-1.3, z0+rows*storey-.8, PANELS, TONES[1], whole=True)


def slot_windows(name, wall, a, z0, z1, width=2.4, height=5.0, gap=2.6):
    """A vertical column of small dark windows in a shallow reveal."""
    quad(name+' reveal', wall, a-width/2-.5, a+width/2+.5, z0-.5, z1+.5, .03, PANELS, (.36, .36, .34))
    z = z0
    while z+height <= z1:
        pane(name, wall, a-width/2, a+width/2, z, z+height, 'black', False)
        z += height+gap


def ac_box(x, y, z, w=9.0, d=7.0, height=5.0):
    """A small louvred roof unit."""
    cuboid('roof unit', x-w/2, x+w/2, y-d/2, y+d/2, z, z+height, PAINT, (.46, .47, .46), omit='b')
    quad('roof unit louvre', (x, y-d/2, SOUTH), -w/2+.5, w/2-.5, z+.7, z+height-.7, .04, SLATS, LOUVRE)
    deck('roof unit top', x-w/2+.8, x+w/2-.8, y-d/2+.8, y+d/2-.8, z+height+.02, PAINT, (.30, .31, .31))


def bollard(x, y):
    round_prism('bollard', x, y, GROUND, GROUND+3, .5, STEEL, (.42, .44, .44), 6, detail=True)


def bend(points, radius):
    """A pipe's path through points, its corners rounded."""
    path = [points[0]]
    for prev, corner, after in zip(points, points[1:], points[2:]):
        a = [c-radius*(c-p)/math.dist(corner, prev) for c, p in zip(corner, prev)]
        b = [c+radius*(q-c)/math.dist(corner, after) for c, q in zip(corner, after)]
        for t in (0, .25, .5, .75, 1):
            path.append(tuple((1-t)**2*p+2*t*(1-t)*c+t*t*q for p, c, q in zip(a, corner, b)))
    path.append(points[-1])
    return path


def pipe(name, points, radius, sides=8):
    return tube(name, bend(points, radius*2.2), radius, STEEL, PIPE, sides=sides, smooth=50)


def volume(name, ring, z0, z1):
    return civic.prism('building_volume '+name, ring, z0, z1, shared.FLAT, (.3, .8, .65), helper=True)


def apron(x0, x1, y0, y1):
    deck('apron', x0, x1, y0, y1, GROUND, CAST, (.94, .94, .90))
    for wall, a0, a1 in (((0, y0, SOUTH), x0, x1), ((x1, 0, EAST), y0, y1), ((0, y1, NORTH), -x1, -x0), ((x0, 0, WEST), -y1, -y0)):
        quad('apron edge', wall, a0, a1, 0, GROUND, 0, CAST, (.56, .56, .53))


# -- Industrial Works ---------------------------------------------------------------------------

def industrial_works():
    """Sheet 'Industrial Works', 3 x 3 hexes: a hall of three sawtooth bays behind a heavy front beam, loading shutters, a rear block with paired stacks."""
    rng = random.Random(29)
    x0, x1, y0, y1 = -104, 104, -78, 112
    wall_top, ridge, block_top = 54, 72, 90
    roof = wall_top+.3
    bx0, bx1, by0, by1 = 60, 112, 50, 120
    south, east, north, west = (0, y0, SOUTH), (x1, 0, EAST), (0, y1, NORTH), (x0, 0, WEST)
    apron(-120, 120, -96, 126)

    # The hall's walls and roof deck. The deck lies above the game's floor at this height.
    face('hall south wall', south, x0, x1, 0, wall_top, 8, 13.5, foot=0, top=wall_top)
    face('hall east wall', east, y0, by0, 0, wall_top, 8, 13.5, foot=0, top=wall_top)
    face('hall north wall', north, -bx0, -x0, 0, wall_top, 8, 13.5, foot=0, top=wall_top)
    face('hall west wall', west, -y1, -y0, 0, wall_top, 8, 13.5, foot=0, top=wall_top)
    deck('hall roof', x0, x1, y0, y1, roof, CAST, ROOF_TONE)
    for name, wall, a0, a1 in (('east', east, y0, by0), ('north', north, -bx0, -x0), ('west', west, -y1, -y0)):
        on_wall(f'{name} parapet', wall, a0, a1, -1.2, 0, wall_top, wall_top+2.6, PANELS, EDGE, whole=True)
        on_wall(f'{name} parapet coping', wall, a0-.1, a1+.1, -1.3, .1, wall_top+2.6, wall_top+2.9, PANELS, COPING)

    # The front: a heavy beam on piers over three shutters and a staff door, between corner buttresses.
    cast_band('front beam', south, -84, 84, 3, 38, wall_top+.6, STONE)
    on_wall('front beam kerb', south, -84, 84, -1.2, 0, wall_top, wall_top+.86, PANELS, EDGE, whole=True)
    bays = ((-58, -22), (-6, 30), (46, 82))
    for name, (a0, a1) in zip('abc', bays):
        shutter('loading shutter '+name, south, a0, a1, 31, rng)
    for a0, a1 in ((-20.5, -7.5), (31.5, 44.5)):
        on_wall('front pier', south, a0, a1, 0, 4.4, 0, 38, PANELS, TONES[1])
        on_wall('front pier head', south, a0, a1, 0, 5.2, 38, wall_top+2.2, PANELS, TONES[0])
        on_wall('front pier head coping', south, a0-.1, a1+.1, -.1, 5.3, wall_top+2.2, wall_top+2.5, PANELS, COPING)
    on_wall('staff bay pier', south, -62, -59, 0, 3, 0, 38, PANELS, TONES[1])
    double_door('staff', south, -72)
    on_wall('staff door hood', south, -79, -65, 0, 2, 11.2, 12, PANELS, EDGE, under=True)
    for x_low, x_top, x_edge in ((-116, -104, -84), (116, 104, 84)):
        lo, hi = sorted((x_low, x_edge))
        tlo, thi = sorted((x_top, x_edge))
        frustum('corner buttress', (lo, hi, y0-14, y0+15), (tlo, thi, y0-5, y0+10), 0, 34, PANELS, TONES[1])
        cuboid('corner buttress band', tlo-.5, thi+.5, y0-5.5, y0+10.5, 34, 36, PANELS, TONES[0], omit='b')
        frustum('corner buttress', (tlo+.8 if x_low < 0 else tlo, thi-.8 if x_low > 0 else thi, y0-4.4, y0+10), (tlo+1.6 if x_low < 0 else tlo, thi-1.6 if x_low > 0 else thi, y0-3.6, y0+10), 36, 58, PANELS, TONES[1])
        frustum('corner buttress head', (tlo+1.6 if x_low < 0 else tlo, thi-1.6 if x_low > 0 else thi, y0-3.6, y0+10), (tlo-.4, thi+.4, y0-5.4, y0+10.4), 52, 58, PANELS, TONES[0])
        cuboid('corner buttress cap', tlo-.4, thi+.4, y0-5.4, y0+10.4, 58, 62, PANELS, TONES[0], omit='b')
        cuboid('corner buttress cap coping', tlo-.5, thi+.5, y0-5.5, y0+10.5, 62, 62.3, PANELS, COPING, omit='b')

    # Three sawtooth bays. Each roof rises eastward to a ridge beam that overhangs the glass, which stands recessed on a curb between
    # two end piers. The gables' glass lies recessed behind a thick sloped frame and the pier. All of the roof glass glows together.
    spans = ((-96, -31, y1-8), (-31, 34, y1-8), (34, 99, by0))
    front = y0+10
    frame = 2.6
    for k, (a, b, rear) in enumerate(spans):
        top = b-10
        rise = lambda x: roof+(ridge-roof)*(x-a)/(top-a)
        glass_top = (top+3.5, ridge-1.6)
        glass_foot = (top+8, roof+2.6)
        body = [(a, roof), (top, ridge), (top, ridge+.8), (top+6, ridge+.8), (top+6, glass_top[1]), glass_top, glass_foot, (b, glass_foot[1]), (b, roof)]
        extrude(f'saw bay {k}', [(x-a, z) for x, z in body], (a, 0, EAST), front+frame, rear-frame, PANELS, STONE)
        # The glass and its bars, facing east and a little up.
        count = 16
        lift = .05
        ya, yb = front+frame, rear-frame
        add(f'saw glazing {k}', PALE_GLASS, TEAL_GLASS,
            [(glass_foot[0]+lift, ya, glass_foot[1]+lift), (glass_foot[0]+lift, yb, glass_foot[1]+lift), (glass_top[0]+lift, yb, glass_top[1]+lift), (glass_top[0]+lift, ya, glass_top[1]+lift)], [(0, 1, 2, 3)], light='dim')
        for i in range(1, count):
            y = ya+(yb-ya)*i/count
            add(f'saw glazing bar {k}', STEEL, (.26, .28, .28),
                [(glass_foot[0]+2*lift, y-.16, glass_foot[1]+2*lift), (glass_foot[0]+2*lift, y+.16, glass_foot[1]+2*lift), (glass_top[0]+2*lift, y+.16, glass_top[1]+2*lift), (glass_top[0]+2*lift, y-.16, glass_top[1]+2*lift)], [(0, 1, 2, 3)])
        # Each end: a thick frame along the slope, a square pier at the high side, and the gable's glass behind them.
        for y_out, y_in, sign in ((front, front+frame, -1), (rear, rear-frame, 1)):
            y_lo, y_hi = sorted((y_out, y_in))
            low, high = a+7, top-1
            rim = [(a, roof), (a, roof+.8), (high, rise(high)+.8), (high, rise(high)-1.6), (low, rise(low)-1.6), (low, roof)]
            extrude(f'gable rim {k}', [(x-a, z) for x, z in rim], (a, 0, EAST), y_lo, y_hi, PANELS, TONES[1])
            cuboid(f'gable pier {k}', top-1, b, y_lo-.3, y_hi, roof, ridge+2.2, PANELS, TONES[0], omit='b')
            cuboid(f'gable pier cap {k}', top-1.2, b+.2, y_lo-.5, y_hi+.2, ridge+2.2, ridge+2.6, PANELS, COPING, omit='b')
            cuboid(f'gable foot {k}', low, high, y_lo, y_hi, roof, roof+.5, PANELS, EDGE, omit='b')
            bottom = roof+.5
            verts = [(low, y_in+sign*.06, bottom), (high, y_in+sign*.06, bottom), (high, y_in+sign*.06, rise(high)-1.6), (low, y_in+sign*.06, rise(low)-1.6)]
            add(f'gable glass {k}', PALE_GLASS, TEAL_GLASS, verts if sign < 0 else verts[::-1], [(0, 1, 2, 3)], light='dim')
            step = (high-low)/6
            for i in range(1, 6):
                x = low+i*step
                bar = [(x-.14, y_in+sign*.1, bottom), (x+.14, y_in+sign*.1, bottom), (x+.14, y_in+sign*.1, rise(x)-1.6), (x-.14, y_in+sign*.1, rise(x)-1.6)]
                add(f'gable bar {k}', STEEL, (.26, .28, .28), bar if sign < 0 else bar[::-1], [(0, 1, 2, 3)])
        # Rooflights and small vents on the slope.
        for c in (front+(rear-front)*.27, front+(rear-front)*.73):
            ya, yb, xa, xb = c-14, c+14, a+22, a+35
            add(f'bay rooflight kerb {k}', PAINT, (.34, .36, .36), [(xa-.6, ya-.6, rise(xa-.6)+.1), (xb+.6, ya-.6, rise(xb+.6)+.1), (xb+.6, yb+.6, rise(xb+.6)+.1), (xa-.6, yb+.6, rise(xa-.6)+.1)], [(0, 1, 2, 3)])
            add(f'bay rooflight {k}', GRILLE, (.34, .36, .36), [(xa, ya, rise(xa)+.2), (xb, ya, rise(xb)+.2), (xb, yb, rise(xb)+.2), (xa, yb, rise(xa)+.2)], [(0, 1, 2, 3)])
        for t in (.08, .5, .92):
            y = front+(rear-front)*t
            cuboid(f'bay hood {k}', a+7, a+11, y-2, y+2, rise(a+7)-.3, rise(a+11)+1.6, PANELS, EDGE, omit='b')
    # East side: a plain wall with louvres, buttresses, and the maintenance walkway: wide enough to pass the buttresses,
    # a door at its far end, a ladder at its outer edge. The big pipes rise beyond its end.
    for a0, a1 in ((-30, -16), (6, 20)):
        frustum('east buttress', (x1, x1+8, a0-2, a1+2), (x1, x1+2.4, a0, a1), 0, 46, PANELS, TONES[1])
        cuboid('east buttress cap', x1, x1+2.4, a0-.3, a1+.3, 46, 47.4, PANELS, COPING, omit='b')
    walk = 34
    walk_from, walk_to, walk_d = -60, 40, 8
    ladder_a = -52
    on_wall('east walkway', east, walk_from, walk_to, 0, walk_d, walk-.5, walk, STEEL, (.66, .68, .67), under=True)
    for a in range(walk_from+2, walk_to, 12):
        extrude('east walkway bracket', [(0, walk-.5), (walk_d-.4, walk-.5), (0, walk-5.5)], east, a-.2, a+.2, STEEL, DARK, detail=True)
    outer = x1+walk_d-.3
    rail('east walkway rail', (outer, walk_from, walk), (outer, ladder_a-1.5, walk))
    rail('east walkway rail', (outer, ladder_a+1.5, walk), (outer, walk_to, walk))
    rail('east walkway end rail', (x1, walk_from, walk), (outer, walk_from, walk), spacing=4)
    rail('east walkway end rail', (x1, walk_to, walk), (outer, walk_to, walk), spacing=4)
    door('walkway', x1, walk_to-4, walk, EAST, fixture=True)
    ladder_on('east walkway ladder', (x1+walk_d-.6, 0, EAST), ladder_a, GROUND, walk+2.4)
    for z in (12, 24):
        for side in (-.9, .9):
            on_wall('ladder stay', east, ladder_a+side-.07, ladder_a+side+.07, 0, walk_d-.1, z, z+.14, STEEL, HANDRAIL, under=True, detail=True)
    for a0, a1 in ((-60, -44), (-12, 2), (24, 40)):
        louvre('east louvre', east, a0, a1, 14, 23)
    double_door('east staff', east, -40, fixture=True)
    on_wall('electrical cabinet', east, -62, -54, 0, 2.4, GROUND, 9, PAINT, (.52, .55, .54))
    quad('cabinet seam', east, -58.08, -57.92, GROUND, 9, 2.44, STEEL, DARK, detail=True)
    for z in (6, 11):
        pipe('east main', [(x1, 26, z), (x1+7.5, 26, z), (x1+7.5, 45+(z-6)/2.5, z), (x1+7.5, 45+(z-6)/2.5, 44+z/2), (x1, 45+(z-6)/2.5, 44+z/2)], 1.7)
    for a in (32, 40):
        on_wall('pipe bracket', east, a-.3, a+.3, 0, 7, 3.6, 13, STEEL, DARK)
    for a in (-71, -5):
        round_prism('downpipe', x1+.5, a, GROUND, wall_top+2, .4, PAINT, (.30, .32, .32), 6)

    # West side: buttresses, louvres, a strip window and a door.
    for a0, a1 in ((-70, -56), (-24, -10), (22, 36)):
        frustum('west buttress', (x0-10, x0, -a1-3, -a0+3), (x0-2, x0, -a1, -a0), 0, 46, PANELS, TONES[1])
        cuboid('west buttress cap', x0-2.4, x0, -a1-.3, -a0+.3, 46, 47.4, PANELS, COPING, omit='b')
    for a0, a1 in ((-98, -76), (-50, -32), (-4, 14), (42, 64)):
        louvre('west louvre', west, a0, a1, 15, 24)
    door('west staff', x0, -14, GROUND, WEST, fixture=True)

    # North side: the bays' gables over a plain wall, grilles, a door and downpipes. Corner buttress at the west end.
    frustum('corner buttress', (-116, -84, y1-11, y1+14), (-104, -84, y1-6, y1+6), 0, 30, PANELS, TONES[1])
    frustum('corner buttress', (-104, -84, y1-6, y1+6), (-104, -84, y1-6, y1+6), 30, 58, PANELS, TONES[1])
    cuboid('corner buttress cap', -104.4, -83.6, y1-6.4, y1+6.4, 58, 62, PANELS, TONES[0], omit='b')
    for a0, a1 in ((-52, -28), (-8, 16), (34, 58)):
        quad('north grille frame', north, a0-.5, a1+.5, 5.5, 18.5, .03, PANELS, (.40, .40, .38))
        quad('north grille', north, a0, a1, 6, 18, .06, GRILLE, (.46, .49, .48))
    door('north staff', 20, y1, GROUND, NORTH, fixture=True)
    for x in (-40, 30):
        round_prism('downpipe', x, y1+.5, GROUND, wall_top+2, .4, PAINT, (.30, .32, .32), 6)

    # The rear block: three storeys of strip windows, stacks and plant on its roof.
    block_e, block_s, block_n, block_w = (bx1, 0, EAST), (0, by0, SOUTH), (0, by1, NORTH), (bx0, 0, WEST)
    face('block east wall', block_e, by0, by1, 0, block_top, 7, 15, foot=0, top=block_top)
    face('block north wall', block_n, -bx1, -bx0, 0, block_top, 7, 15, foot=0, top=block_top)
    face('block south wall', block_s, x1, bx1, 0, roof, 4, 15, foot=0)
    face('block south wall', block_s, bx0, bx1, roof, block_top, 7, 12, top=block_top)
    face('block west wall', block_w, -by1, -y1, 0, block_top, 4, 15, foot=0, top=block_top)
    face('block west wall', block_w, -y1, -by0, roof, block_top, 7, 12, top=block_top)
    deck('block roof', bx0, bx1, by0, by1, block_top, CAST, ROOF_TONE)
    for wall, a0, a1, name in ((block_e, by0, by1, 'east'), (block_n, -bx1, -bx0, 'north'), (block_s, bx0, bx1, 'south'), (block_w, -by1, -by0, 'west')):
        on_wall(f'block {name} parapet', wall, a0, a1, -1, 0, block_top, block_top+2.2, PANELS, EDGE, whole=True)
        on_wall(f'block {name} coping', wall, a0-.1, a1+.1, -1.1, .1, block_top+2.2, block_top+2.5, PANELS, COPING)
    for z in (34, 55, 75):
        ribbon('block east window', block_e, by0+10, by1-8, z, z+7.5, rng, pitch=6.5, kind='teal')
        ribbon('block north window', block_n, -bx1+7, -bx0-7, z, z+7.5, rng, pitch=6.5, kind='teal') if z > 34 else None
    ribbon('block south window', block_s, bx0+6, bx1-6, 76, 83, rng, pitch=6.5, kind='teal')
    ribbon('block west window', block_w, -by1+8, -by0-22, 72, 79.5, rng, pitch=6.5, kind='teal')
    door('block roof deck', bx0, 62, roof, WEST, fixture=True)
    door('block staff', bx1, 80, GROUND, EAST, fixture=True)
    for a0, a1 in ((by0+7, by0+21), (92, 108)):
        louvre('block louvre', block_e, a0, a1, 3, 10)
    ladder_on('block roof ladder', block_n, -bx1+4, GROUND, block_top+1.6)
    for x, y in ((bx0+2.5, by1-2.5), (bx1-2.5, by0+2.5)):
        beacon(x, y, block_top+2.5)
    for a, b in (((bx0+1.5, by0+1.5, block_top+.1), (bx1-1.5, by0+1.5, block_top+.1)), ((bx1-1.5, by0+1.5, block_top+.1), (bx1-1.5, by1-5, block_top+.1)),
                 ((bx0+1.5, by1-1.5, block_top+.1), (bx1-6, by1-1.5, block_top+.1)), ((bx0+1.5, by0+1.5, block_top+.1), (bx0+1.5, by1-1.5, block_top+.1))):
        rail('block roof rail', a, b, spacing=6)

    # Paired square stacks with a dark louvred band below the rim.
    stack_top = 114
    for cx in (76, 94):
        cy = 98
        half = 5.4
        walls = ((cx, cy-half, SOUTH), (cx+half, cy, EAST), (cx, cy+half, NORTH), (cx-half, cy, WEST))
        for wall in walls:
            face('exhaust stack', wall, -half, half, block_top, stack_top, 4.5, 9, top=stack_top)
            quad('stack louvre', wall, -half+.8, half-.8, stack_top-5.5, stack_top-2, .05, SLATS, (.40, .41, .41))
            on_wall('stack band', wall, -half-.3, half+.3, 0, .3, stack_top-7, stack_top-6.2, PANELS, EDGE, detail=True)
        cuboid('stack rim', cx-half-.4, cx+half+.4, cy-half-.4, cy+half+.4, stack_top, stack_top+1, PANELS, TONES[0], omit='b')
        deck('stack flue', cx-half+1.2, cx+half-1.2, cy-half+1.2, cy+half-1.2, stack_top+1.02, PAINT, (.08, .08, .08))
    plant_box('block plant', 68, 100, 62, 76, block_top, 7, 2)

    # The large pipes: from the low roof up into the block's west wall, and from the plant to the stacks.
    pipe('main duct', [(26, 108, roof+2.6), (52, 108, roof+2.6), (52, 108, 84), (bx0, 108, 84)], 2.4)
    for x in (32, 44):
        cuboid('pipe stand', x-.5, x+.5, 105.6, 110.4, roof, roof+2, STEEL, ALLOY, omit='b')
    pipe('stack feed', [(85, 76, block_top+5), (85, 86, block_top+5), (76, 86, block_top+5), (76, 92.6, block_top+5)], 1.6)

    # Structure: the hall, the bays' ridges as a thin top, and the block.
    volume('hall', civic.rect(x0+1.5, x1-1.5, y0+1.5, by0-1), 0, wall_top)
    volume('hall rear', civic.rect(x0+1.5, bx0-1, by0-1, y1-1.5), 0, wall_top)
    volume('saw roofs', civic.rect(-96, 34, front, y1-8), ridge-1, ridge)
    volume('saw roof east', civic.rect(34, 99, front, by0), ridge-1, ridge)
    volume('rear block', civic.rect(bx0+1.5, bx1-1.5, by0+1.5, by1-1.5), 0, block_top)


# -- Commercial Center --------------------------------------------------------------------------

def storefront(name, wall, a0, a1, rng, top=17.0, glass_d=0.0):
    """A shop window to the ground in a dark frame, lit at night, with an amber light over it."""
    quad(name+' frame', wall, a0-.5, a1+.5, GROUND, top+.6, glass_d+.03, PANELS, (.34, .34, .33))
    count = max(1, round((a1-a0)/5.4))
    step = (a1-a0)/count
    for i in range(count):
        pane(name, wall, a0+i*step, a0+(i+1)*step, GROUND+.6, top, 'teal', rng.random() < .75, off=glass_d+.06)
        if i:
            quad(name+' mullion', wall, a0+i*step-.12, a0+i*step+.12, GROUND+.6, top, glass_d+.1, STEEL, DARK, detail=True)
    quad(name+' stall', wall, a0, a1, GROUND, GROUND+.6, glass_d+.08, PANELS, (.46, .46, .44))
    middle = (a0+a1)/2
    half = min(7, (a1-a0)/2-1)
    quad(name+' light', wall, middle-half, middle+half, top+1.2, top+1.9, glass_d+.1, PAINT, AMBER, light=AMBER_LIGHT)


def advert(name, wall, a0, a1, z0, z1, d=1.6):
    """A large blank advertising panel in a concrete surround, standing off the wall."""
    on_wall(name+' surround', wall, a0-1.4, a1+1.4, 0, d, z0-1.4, z1+1.4, PANELS, TONES[1], under=True)
    quad(name, wall, a0, a1, z0, z1, d+.05, PAINT, (.13, .14, .15))
    for i in range(1, 4):
        a = a0+(a1-a0)*i/4
        quad(name+' seam', wall, a-.06, a+.06, z0, z1, d+.08, STEEL, DARK, detail=True)


def commercial_center():
    """Sheet 'Commercial Center', 4 x 3 hexes, from its ISO: shops under a balcony's solid front, dark glass and advertising panels under a heavy band, a thin pylon with the entrance and the atrium wedge straight behind it, roof fields stepping up to a service deck."""
    rng = random.Random(27)
    cx = 31
    y0, y1 = -96, 126
    glass_y = y0+8
    # Heights: shops, balcony floor and front, band; the front fields behind a parapet, the rear fields a step up behind a beam, the service deck and the raised flank walls.
    shop_z, floor_z, balcony_z, band_z, band_top = 18, 27.5, 29, 47, 57
    low_z, ledge_z, front_z, parapet_z, rear_z, beam_top, head, service_z, raised_z, ridge = 48, 60, 60, 64.5, 67, 70, 72, 72, 75.5, 92
    # Distances from the axis: the band and balcony front, the shop wall, the upper wall, the wall behind the big piers; the upper box, the front and rear fields' edges, the raised wall's face.
    band_a, wall_a, upper_a, rear_a = 136, 129, 128, 133
    top_a, field_a, roof_a, raised_a = 120, 116, 112, 124
    field_y, beam_y, rear_y, wall_end, back_y = glass_y+4, -50, 58, 108, y1-10
    pier_y0, pier_y1 = -26, -10
    apron(cx-144, cx+144, y0-12, y1+8)
    apron(cx-96, cx+96, y0-34, y0-12)
    front, fascia = (cx, glass_y, SOUTH), (cx, y0, SOUTH)
    band_shade = (.92, 1.02)
    face('front wall', front, -wall_a, wall_a, 0, shop_z, 9, 11, foot=0)
    face('front upper wall', front, -upper_a, upper_a, floor_z, band_z, 9, 10)
    # The atrium's wedge, needed here for what stops against it.
    a_front, a_rear = glass_y, 92
    along = lambda y: (y-a_front)/(a_rear-a_front)
    half_at = lambda y: 26+(15-26)*along(y)
    z_at = lambda y: head+.3+13*along(y)
    rise = 1.1
    spread = 11.5
    kerb_at = lambda y: half_at(y)+5.5
    frame_at = lambda y: kerb_at(y)+spread
    slope_at = lambda y, z: kerb_at(y)+spread*(z_at(y)+rise-z)/(z_at(y)+rise-front_z)
    floor_at = lambda y: front_z+.3 if y < beam_y+6 else rear_z+.3 if y < rear_y+4 else service_z+.3
    for sign, n, name in ((1, EAST, 'east'), (-1, WEST, 'west')):
        span = lambda p, q: tuple(sorted((sign*p, sign*q)))
        xs = lambda p, q: tuple(sorted((cx+sign*p, cx+sign*q)))
        flank = lambda a: (cx+sign*a, 0, n)
        plan = lambda points, z: [(cx+sign*a, y, z) for a, y in points]
        up = lambda verts: verts if sign > 0 else verts[::-1]
        outer = 'r' if sign > 0 else 'l'
        slanted = lambda part, a, b, z0, z1, du, dv, **kw: h.grid_wall(part, *((a, b) if sign > 0 else (b, a)), z0, z1, du, dv, amount=.4, **kw)
        # Ground: two shop bays with a small pier between, a battered pier up into the band, a narrow bay and a battered corner pier.
        for p, q in ((49, 75), (84, 104), (120.5, wall_a-.5)):
            storefront('shop', front, *span(p, q), rng, top=15.5)
        on_wall('shop pier', front, *span(75.5, 83.5), 0, 8, 0, shop_z, PANELS, TONES[1])
        low, high = xs(104, 120), xs(109, 119)
        frustum('battered pier', (*low, y0-7, glass_y), (*high, y0-.4, glass_y), 0, band_z+.2, PANELS, TONES[1])
        low, high = xs(wall_a, 140), xs(wall_a+.5, band_a)
        frustum('corner pier', (*low, y0-5, y0+14), (*high, y0, glass_y), 0, shop_z+.2, PANELS, TONES[1])
        # The balcony: a solid front with a rail on it, round the corner and along the flank to the big pier.
        xa, xb = xs(43, band_a)
        cuboid('balcony front', xa, xb, y0, y0+2, shop_z, balcony_z, PANELS, STONE, omit='f')
        face('balcony front', fascia, *span(43, band_a), shop_z, balcony_z, 8, 11, top=balcony_z)
        xa, xb = xs(band_a-2, band_a)
        cuboid('balcony front', xa, xb, y0+2, pier_y0, shop_z, balcony_z, PANELS, STONE, omit='fk'+outer)
        face('balcony front', flank(band_a), *span(y0+2, pier_y0), shop_z, balcony_z, 8, 11, top=balcony_z)
        xa, xb = xs(43, band_a-2)
        soffit('balcony soffit', xa, xb, y0+2, glass_y, shop_z)
        deck('balcony deck', xa, xb, y0+2, glass_y, floor_z, CAST, (.72, .72, .68))
        xa, xb = xs(wall_a, band_a-2)
        soffit('balcony soffit', xa, xb, glass_y, pier_y0, shop_z)
        xa, xb = xs(upper_a+4, band_a-2)
        deck('balcony deck', xa, xb, glass_y, pier_y0, floor_z, CAST, (.72, .72, .68))
        for p, q in ((44, 109), (119.5, band_a-1)):
            lo, hi = xs(p, q)
            rail('balcony rail', (lo, y0+1, balcony_z), (hi, y0+1, balcony_z), spacing=7)
        x = cx+sign*(band_a-1)
        rail('flank balcony rail', (x, y0+1, balcony_z), (x, pier_y0, balcony_z), spacing=7)
        # The upper storey: dark glass by the pylon, a deep panel under a hood in the band, a narrow window at the corner; on the flank a battered wall.
        ribbon('upper shop window', front, *span(48, 72), floor_z+.6, band_z-1, rng, pitch=5.5, lit=.45)
        advert('wing panel', front, *span(76, 107), 30, 45.6, d=4)
        xa, xb = xs(74, 109)
        cuboid('panel hood', xa, xb, y0-2, glass_y, band_z-1, band_top+.8, PANELS, STONE, omit='fk')
        face('panel hood', (cx, y0-2, SOUTH), *span(74, 109), band_z-1, band_top+.8, 8, 11, shade=band_shade)
        ribbon('upper corner window', front, *span(120.5, 126.5), floor_z+1, band_z-1, rng, pitch=7, lit=.3, kind='teal')
        face(name+' shop wall', flank(wall_a), *span(glass_y, pier_y0), 0, shop_z, 9, 11, foot=0)
        for p, q in ((-80, -58), (-48, pier_y0-2)):
            storefront(name+' shop', flank(wall_a), *span(p, q), rng, top=15.5)
        on_wall(name+' shop pier', flank(wall_a), *span(-57.5, -48.5), 0, 5, 0, shop_z, PANELS, TONES[1])
        extrude(name+' battered wall', [(0, floor_z), (4, floor_z), (0, band_z)], flank(upper_a), *span(glass_y, pier_y0), PANELS, STONE)
        # The heavy band with its chamfered corner; a big pier ends it on the flank and rises past it.
        face('heavy band', fascia, *span(43, band_a-3), band_z, band_top, 8, 11, shade=band_shade)
        slanted('heavy band', (cx+sign*(band_a-3), y0), (cx+sign*band_a, y0+3), band_z, band_top, 5, 11, shade=band_shade)
        face('heavy band', flank(band_a), *span(y0+3, pier_y0), band_z, band_top, 8, 11, shade=band_shade)
        ring = [(43, y0), (band_a-3, y0), (band_a, y0+3), (band_a, pier_y0), (127, pier_y0), (127, pier_y1), (top_a, pier_y1), (top_a, glass_y+6), (top_a-6, glass_y), (43, glass_y)]
        add('band top', CAST, ROOF_TONE, up(plan(ring, band_top+.25)), [tuple(range(len(ring)))])
        ring = [(43, y0), (band_a-3, y0), (band_a, y0+3), (band_a, pier_y0), (upper_a, pier_y0), (upper_a, glass_y), (43, glass_y)]
        add('band soffit', CAST, (.55, .55, .535), up(plan(ring, band_z))[::-1], [tuple(range(len(ring)))])
        low, high = xs(127, 142), xs(127, 140)
        frustum('big pier', (*low, pier_y0-2, pier_y1+2), (*high, pier_y0, pier_y1), 0, 63, PANELS, TONES[1])
        xa, xb = xs(126.4, 140.6)
        cuboid('big pier cap', xa, xb, pier_y0-.6, pier_y1+.6, 63, 65, PANELS, COPING)
        # On the band: a low parapet with a rail and a chamfered corner, round the front field.
        ring = [(43, glass_y), (top_a-6, glass_y), (top_a, glass_y+6), (top_a, beam_y), (field_a, beam_y), (field_a, field_y), (43, field_y)]
        add('parapet top', PANELS, COPING, up(plan(ring, parapet_z)), [tuple(range(len(ring)))])
        face('front parapet', front, *span(43, top_a-6), band_top, parapet_z, 8, 8, top=parapet_z)
        slanted('front parapet', (cx+sign*(top_a-6), glass_y), (cx+sign*top_a, glass_y+6), band_top, parapet_z, 5, 8)
        face('side parapet', flank(top_a), *span(glass_y+6, beam_y), band_top, parapet_z, 8, 8, top=parapet_z)
        quad('parapet inner', (cx, field_y, NORTH), *span(-43, -field_a), front_z, parapet_z, 0, PANELS, TONES[1])
        quad('parapet inner', (cx+sign*43, 0, WEST if sign > 0 else EAST), *span(-glass_y, -field_y), front_z, parapet_z, 0, PANELS, TONES[1])
        quad('parapet inner', (cx+sign*field_a, 0, WEST if sign > 0 else EAST), *span(-field_y, -beam_y), front_z, parapet_z, 0, PANELS, TONES[1])
        lo, hi = xs(44, field_a+.5)
        rail('front field rail', (lo, field_y-1, parapet_z), (hi, field_y-1, parapet_z), spacing=7)
        x = cx+sign*(field_a+.5)
        rail('side field rail', (x, field_y-1, parapet_z), (x, beam_y-1, parapet_z), spacing=7)
        on_wall('parapet pipe', front, *span(56.5, 57.5), 0, .8, band_top, parapet_z, PANELS, TONES[1])
        # Past the beam: a low rim with a walkway rail on the band outside it, then the thick raised wall above a ledge, to behind the rear wall.
        xa, xb = xs(roof_a, top_a+2)
        cuboid('beam end', xa, xb, beam_y, beam_y+6, band_top, raised_z+.3, PANELS, STONE, omit='b')
        xa, xb = xs(roof_a, top_a)
        cuboid('field rim', xa, xb, beam_y+6, pier_y1, band_top, raised_z, PANELS, STONE, omit='bfk')
        cuboid('field rim coping', xa-.12, xb+.12, beam_y+6, pier_y1, raised_z, raised_z+.3, PANELS, COPING, omit='bfk')
        x = cx+sign*(top_a+1.6)
        rail('walkway rail', (x, beam_y+6.5, band_top+.25), (x, pier_y0, band_top+.25), spacing=7)
        xa, xb = xs(roof_a, raised_a)
        cuboid('raised wall', xa, xb, pier_y1, wall_end, band_top, raised_z, PANELS, STONE, omit='b'+outer)
        face('raised wall', flank(raised_a), *span(pier_y1, wall_end), ledge_z, raised_z, 9, 9, top=raised_z)
        cuboid('raised wall coping', xa-.12, xb+.12, pier_y1-.12, wall_end+.12, raised_z, raised_z+.3, PANELS, COPING, omit='b')
        xa, xb = xs(raised_a, rear_a)
        deck('ledge', xa, xb, pier_y1, wall_end, ledge_z+.3, CAST, ROOF_TONE)
        quad('ledge end', (cx+sign*(raised_a+rear_a)/2, wall_end, NORTH), -(rear_a-raised_a)/2, (rear_a-raised_a)/2, low_z, ledge_z, 0, PANELS, STONE)
        deck('low ledge', xa, xb, wall_end, back_y, low_z+.3, CAST, ROOF_TONE)
        # Past the wall's end the service deck has only a parapet, above the lower rear part.
        face('upper flank', flank(raised_a), *span(wall_end, back_y), low_z, service_z, 8, 9, top=service_z)
        on_wall('upper flank parapet', flank(raised_a), *span(wall_end, back_y), -1.2, 0, service_z, service_z+2.4, PANELS, EDGE, whole=True)
        on_wall('upper flank coping', flank(raised_a), *span(wall_end, back_y), -1.3, .1, service_z+2.4, service_z+2.65, PANELS, COPING)
        # The beam and the rear wall between the levels, stopping on the wedge, with rails on them.
        xa, xb = xs(slope_at(beam_y, beam_top)-.5, roof_a)
        cuboid('beam', xa, xb, beam_y+3, beam_y+6, front_z, beam_top, PANELS, STONE, omit='b')
        cuboid('beam lintel', xa, xb, beam_y, beam_y+3, 66.5, beam_top, PANELS, STONE, omit='k')
        cuboid('beam coping', xa, xb, beam_y-.1, beam_y+6.1, beam_top, beam_top+.3, PANELS, COPING, omit='b')
        rail('beam rail', (cx+sign*(slope_at(beam_y, beam_top)+1.5), beam_y+4.5, beam_top+.3), (cx+sign*(roof_a-.5), beam_y+4.5, beam_top+.3), spacing=8)
        xa, xb = xs(slope_at(rear_y, service_z+1)-.5, roof_a)
        cuboid('rear field wall', xa, xb, rear_y, rear_y+4, rear_z, service_z+1, PANELS, STONE, omit='b')
        cuboid('rear field wall coping', xa, xb, rear_y-.1, rear_y+4.1, service_z+1, service_z+1.3, PANELS, COPING, omit='b')
        rail('rear field wall rail', (cx+sign*(slope_at(rear_y, service_z+1)+1.5), rear_y+2, service_z+1.3), (cx+sign*(roof_a-.5), rear_y+2, service_z+1.3), spacing=8)

    # The central pylon: a thin slab with the entrance in its foot and the great panel on its face. The atrium starts straight behind it.
    pylon_y = y0-6
    pylon = (cx, pylon_y, SOUTH)
    lintel = 22
    for sign in (-1, 1):
        a0, a1 = sorted((sign*30, sign*43))
        face('pylon pier', pylon, a0, a1, 0, head, 5, 11, TONES[1], foot=0, top=head)
        wall = (cx+sign*43, 0, EAST if sign > 0 else WEST)
        a0, a1 = sorted((sign*pylon_y, sign*glass_y))
        face('pylon flank', wall, a0, a1, 0, head, 7, 11, TONES[1], foot=0, top=head)
    face('pylon head', pylon, -30, 30, lintel, head, 8, 11, TONES[1], top=head)
    face('pylon back', (cx, glass_y, NORTH), -43, 43, band_top, head, 8, 11, TONES[1], top=head)
    cuboid('pylon cap', cx-43.3, cx+43.3, pylon_y-.3, glass_y+.3, head, head+.6, PANELS, COPING, omit='b')
    advert('great panel', pylon, -27, 27, 30, 60, d=1.2)
    # Behind the pylon's opening: a landing, lobby glass and doors, reached by steps and two ramps.
    landing = 4.0
    lobby = (cx, glass_y, SOUTH)
    soffit('entrance soffit', cx-30, cx+30, pylon_y, glass_y, lintel)
    for sign in (-1, 1):
        a0, a1 = sorted((-sign*pylon_y, -sign*glass_y))
        quad('entrance reveal', (cx+sign*30, 0, WEST if sign > 0 else EAST), a0, a1, 0, lintel, 0, PANELS, TONES[2])
    face('entrance back', lobby, -30, 30, 19, lintel, 6, 3, DARK_RECESS)
    deck('entrance landing', cx-30, cx+30, pylon_y-1, glass_y, landing, CAST, (.86, .86, .82))
    quad('landing front', (cx, pylon_y-1, SOUTH), -30, 30, 0, landing, 0, CAST, (.70, .70, .67))
    quad('landing side', (cx-30, 0, WEST), -pylon_y, -pylon_y+1, 0, landing, 0, CAST, (.70, .70, .67))
    quad('landing side', (cx+30, 0, EAST), pylon_y-1, pylon_y, 0, landing, 0, CAST, (.70, .70, .67))
    storefront('lobby glass', lobby, -29, -9, rng, top=19)
    storefront('lobby glass', lobby, 9, 29, rng, top=19)
    quad('lobby door frame', lobby, -9, 9, landing, 19, .03, STEEL, DARK)
    pane('lobby transom', lobby, -8.6, 8.6, landing+8.4, 18.6, 'teal', True, off=.06)
    for a in (-6.3, -2.1, 2.1, 6.3):
        x, y = at(lobby, a)
        door('lobby', x, y, landing, SOUTH, lit=False)
    quad('entrance light', pylon, -24, 24, lintel+.6, lintel+1.6, .08, PAINT, AMBER, light=AMBER_LIGHT)
    h.fixtures.append((cx, pylon_y-1.5, lintel+1))
    treads = 8
    for i in range(treads):
        y = pylon_y-1-(i+1)*2.4
        z = landing*(1-i/treads)
        cuboid('entrance step', cx-27, cx+27, y, y+2.4, 0, z, CAST, (.78, .78, .74), omit='b')
    stair_foot = pylon_y-1-treads*2.4
    for sign in (-1, 1):
        rail_x = cx+sign*27.5
        for i in range(treads):
            ya, yb = stair_foot+i*2.4, stair_foot+(i+1)*2.4
            za, zb = landing*i/treads+3.1, landing*(i+1)/treads+3.1
            add('stair rail', STEEL, HANDRAIL, [(rail_x, ya, za), (rail_x, yb, zb), (rail_x, yb, zb+.2), (rail_x, ya, za+.2)] if sign > 0 else [(rail_x, yb, zb), (rail_x, ya, za), (rail_x, ya, za+.2), (rail_x, yb, zb+.2)], [(0, 1, 2, 3)])
        # A ramp along the front to the landing's side, with its rail.
        far, near = cx+sign*92, cx+sign*30
        back, ahead = pylon_y-1, pylon_y-9
        top_face = [(far, back, GROUND), (near, back, landing), (near, ahead, landing), (far, ahead, GROUND)]
        add('entrance ramp', CAST, (.82, .82, .78), top_face if sign > 0 else top_face[::-1], [(0, 1, 2, 3)])
        cheek = [(far, ahead, GROUND), (near, ahead, GROUND), (near, ahead, landing)]
        add('ramp cheek', CAST, (.70, .70, .67), cheek if sign < 0 else cheek[::-1], [(0, 1, 2)])
        cheek = [(far, back, GROUND), (near, back, GROUND), (near, back, landing)]
        add('ramp cheek', CAST, (.70, .70, .67), cheek if sign > 0 else cheek[::-1], [(0, 1, 2)])
        a0, a1 = sorted((-sign*back, -sign*ahead))
        quad('ramp cheek', (near, 0, WEST if sign > 0 else EAST), a0, a1, 0, landing, 0, CAST, (.70, .70, .67))
        steps = 6
        for i in range(steps):
            ax, bx = far+(near-far)*i/steps, far+(near-far)*(i+1)/steps
            az, bz = GROUND+(landing-GROUND)*i/steps, GROUND+(landing-GROUND)*(i+1)/steps
            y = ahead+.2
            bar = [(ax, y, az+3.1), (bx, y, bz+3.1), (bx, y, bz+3.3), (ax, y, az+3.3)]
            add('ramp rail', STEEL, HANDRAIL, bar, [(0, 1, 2, 3)])
            add('ramp rail', STEEL, HANDRAIL, bar[::-1], [(0, 1, 2, 3)])
            cuboid('ramp rail post', ax-.1, ax+.1, y-.1, y+.1, az, az+3.2, STEEL, HANDRAIL, omit='bt', detail=True)

    # The flanks behind the big piers: a last bay under a short canopy, a battered pier, a plant louvre high up; the delivery door on the east.
    for sign, n, name in ((1, EAST, 'east'), (-1, WEST, 'west')):
        span = lambda p, q: tuple(sorted((sign*p, sign*q)))
        xs = lambda p, q: tuple(sorted((cx+sign*p, cx+sign*q)))
        wall = (cx+sign*rear_a, 0, n)
        face(name+' rear wall', wall, *span(pier_y1, wall_end), 0, ledge_z, 9, 11, foot=0, top=ledge_z)
        face(name+' rear wall', wall, *span(wall_end, y1), 0, low_z, 9, 11, foot=0, top=low_z)
        storefront(name+' shop', wall, *span(pier_y1+6, 16), rng, top=15.5)
        cast_band(name+' canopy', wall, *span(pier_y1, 24), 3.5, shop_z, balcony_z)
        x = cx+sign*(rear_a+3)
        rail(name+' canopy rail', (x, pier_y1+3, balcony_z+.25), (x, 22, balcony_z+.25), spacing=7)
        low, high = xs(rear_a, rear_a+8), xs(rear_a, rear_a+3.5)
        frustum(name+' pier', (*low, 20, 40), (*high, 25, 35), 0, 52, PANELS, TONES[1])
        louvre(name+' plant louvre', wall, *span(60, 94), 34, 54)
    east, west = (cx+rear_a, 0, EAST), (cx-rear_a, 0, WEST)
    shutter('delivery shutter', east, 50, 76, 20, rng)
    deck('delivery bay stripes', cx+rear_a, cx+rear_a+6, 50, 76, GROUND+.03, HAZARD, (1, 1, 1))
    for y in (47.5, 78.5):
        round_prism('delivery bollard', cx+rear_a+2.4, y, GROUND, GROUND+5, .7, PAINT, (.85, .62, .12), 6)
    door('delivery staff', cx+rear_a, 44, GROUND, EAST, fixture=True)
    door('delivery staff', cx+rear_a, 84, GROUND, EAST, fixture=True)
    door('west staff', cx-rear_a, 60, GROUND, WEST, fixture=True)
    for a0, a1 in ((-100, -80), (-74, -54)):
        louvre('west louvre', west, a0, a1, 6, 15)
    # The rear: staff doors, a shutter, windows, piers and downpipes.
    north0 = (cx, y1, NORTH)
    face('rear wall', north0, -rear_a, rear_a, 0, low_z, 9, 11, foot=0, top=low_z)
    door('rear staff', cx-60, y1, GROUND, NORTH, fixture=True)
    door('rear staff', cx+60, y1, GROUND, NORTH, fixture=True)
    shutter('rear shutter', north0, -18, 18, 19, rng)
    for a0, a1 in ((-112, -76), (76, 112)):
        ribbon('rear window', north0, a0, a1, 9, 17, rng, pitch=7, lit=.2)
        ribbon('rear upper window', north0, a0, a1, 33, 43, rng, pitch=7, lit=.2)
    for a in (-46, 46):
        on_wall('rear pier', north0, a-5, a+5, 0, 3, 0, low_z, PANELS, TONES[1])
    for x in (cx-92, cx+92):
        round_prism('downpipe', x, y1+.5, GROUND, low_z, .5, PAINT, (.30, .32, .32), 6)
    deck('rear ledge', cx-rear_a, cx+rear_a, back_y, y1, low_z+.3, CAST, ROOF_TONE)
    face('upper north', (cx, back_y, NORTH), -raised_a, raised_a, low_z, service_z, 9, 11, top=service_z)
    on_wall('north parapet', (cx, back_y, NORTH), -raised_a, raised_a, -1.2, 0, service_z, service_z+2.4, PANELS, EDGE, whole=True)
    on_wall('north coping', (cx, back_y, NORTH), -raised_a-.1, raised_a+.1, -1.3, .1, service_z+2.4, service_z+2.65, PANELS, COPING)

    # The roof's levels and rooflights.
    deck('front field', cx-field_a, cx+field_a, field_y, beam_y+3, front_z+.3, CAST, ROOF_TONE)
    deck('front field', cx-43, cx+43, glass_y, field_y, front_z+.3, CAST, ROOF_TONE)
    deck('rear field', cx-roof_a, cx+roof_a, beam_y+6, rear_y, rear_z+.3, CAST, ROOF_TONE)
    deck('service deck', cx-raised_a, cx+raised_a, rear_y+4, back_y, service_z+.3, CAST, (.86, .85, .80))
    for x, y, z in ((cx-74, 10, rear_z), (cx+72, -14, rear_z), (cx+82, 34, rear_z), (cx-70, -68, front_z), (cx+70, -68, front_z)):
        cuboid('rooflight kerb', x-5, x+5, y-5, y+5, z+.1, z+1.5, PANELS, EDGE, omit='b')
        deck('rooflight', x-4, x+4, y-4, y+4, z+1.52, PALE_GLASS, h.VOID, light='off')

    # The atrium: a wedge. A monopitch trapezoid of glass rising to the rear, a thin kerb along it, and under the kerb a sloped wall falling to the roof, with stepped blocks along its foot. The glass glows as a whole.
    tapered('atrium body', a_front, a_rear, (cx-half_at(a_front), cx+half_at(a_front)), (cx-half_at(a_rear), cx+half_at(a_rear)), z_at(a_front), z_at(a_rear), front_z, PANELS, TONES[2])
    for sign in (-1, 1):
        ends = [sorted((cx+sign*half_at(y), cx+sign*kerb_at(y))) for y in (a_front, a_rear)]
        tapered('atrium kerb', a_front, a_rear, tuple(ends[0]), tuple(ends[1]), z_at(a_front)+rise, z_at(a_rear)+rise, front_z, PANELS, COPING)
        for k in range(7):
            ya_k, yb_k = (a_front+(a_rear-a_front)*j/7 for j in (k, k+1))
            corners = [(cx+sign*kerb_at(ya_k), ya_k, z_at(ya_k)+rise), (cx+sign*frame_at(ya_k), ya_k, front_z), (cx+sign*frame_at(yb_k), yb_k, front_z), (cx+sign*kerb_at(yb_k), yb_k, z_at(yb_k)+rise)]
            add('atrium wedge', PANELS, TONES[0], corners if sign > 0 else corners[::-1], [(0, 1, 2, 3)])
    top_z = z_at(a_rear)+rise
    add('atrium tail', PANELS, TONES[0], [(cx+frame_at(a_rear), a_rear, front_z), (cx-frame_at(a_rear), a_rear, front_z), (cx-kerb_at(a_rear), a_rear, top_z), (cx+kerb_at(a_rear), a_rear, top_z)], [(0, 1, 2, 3)])
    ya, yb = a_front+.2, a_rear-5.5
    tapered('atrium rear kerb', yb, a_rear, (cx-half_at(yb), cx+half_at(yb)), (cx-half_at(a_rear), cx+half_at(a_rear)), z_at(yb)+rise, z_at(a_rear)+rise, front_z, PANELS, COPING)
    lift = .15
    add('atrium glass', PALE_GLASS, TEAL_GLASS, [(cx-half_at(ya), ya, z_at(ya)+lift), (cx+half_at(ya), ya, z_at(ya)+lift), (cx+half_at(yb), yb, z_at(yb)+lift), (cx-half_at(yb), yb, z_at(yb)+lift)], [(0, 1, 2, 3)], light='dim')
    cells_x, cells_y = 4, 7
    for j in range(1, cells_y):
        y = ya+(yb-ya)*j/cells_y
        hw = half_at(y)
        add('atrium grid', STEEL, HANDRAIL, [(cx-hw, y-.45, z_at(y)+.35), (cx+hw, y-.45, z_at(y)+.35), (cx+hw, y+.45, z_at(y)+.35), (cx-hw, y+.45, z_at(y)+.35)], [(0, 1, 2, 3)])
    for i in range(1, cells_x):
        t = 2*i/cells_x-1
        xf, xr = cx+t*half_at(ya), cx+t*half_at(yb)
        w = .45 if 2*i == cells_x else .25
        add('atrium grid', STEEL, HANDRAIL, [(xf-w, ya, z_at(ya)+.35), (xf+w, ya, z_at(ya)+.35), (xr+w, yb, z_at(yb)+.35), (xr-w, yb, z_at(yb)+.35)], [(0, 1, 2, 3)])
    for sign in (-1, 1):
        for start, end, count in ((a_front+6, beam_y-3, 2), (beam_y+10, rear_y-4, 4)):
            step = (end-start)/count
            for i in range(count):
                y = start+(i+.5)*step
                floor = floor_at(y)
                foot = slope_at(y, floor)
                lo, hi = sorted((cx+sign*(foot-1.5), cx+sign*(foot+3.5)))
                cuboid('atrium block', lo, hi, y-2.6, y+2.6, floor, floor+3.2, PANELS, TONES[1], omit='b')
                cuboid('atrium block cap', lo-.15, hi+.15, y-2.75, y+2.75, floor+3.2, floor+3.6, PANELS, COPING, omit='b')
                if i < count-1:
                    lo, hi = sorted((cx+sign*(foot-1.5), cx+sign*(foot+2.4)))
                    cuboid('atrium ledge', lo, hi, y+2.6, y+step-2.6, floor, floor+1.8, PANELS, TONES[1], omit='b')

    # The service deck: two fan units, a big square duct ending in a round elbow at the atrium, a black louvred cage and the plant room with its doors, louvre, vent and mast.
    deck_z = service_z+.3
    plant_box('fan plant', cx-96, cx-74, 84, 112, deck_z, 8, 2, rows=2)
    plant_box('fan plant', cx-72, cx-50, 84, 112, deck_z, 8, 2, rows=2)
    cuboid('roof duct', cx-50, cx+6, 94, 104, deck_z, deck_z+9, PAINT, (.62, .64, .63), omit='b')
    for x in (cx-40, cx-20, cx):
        cuboid('roof duct collar', x-.5, x+.5, 93.7, 104.3, deck_z, deck_z+9.3, PAINT, (.48, .50, .50), omit='b')
    pipe('roof duct elbow', [(cx+5, 99, deck_z+4.5), (cx+14, 99, deck_z+4.5), (cx+14, 92, deck_z+4.5)], 3.6)
    box_x0, box_x1, box_y0, box_y1 = cx+30, cx+56, 70, 96
    box_top = deck_z+15
    cuboid('louvre box', box_x0, box_x1, box_y0, box_y1, deck_z-.2, box_top, PAINT, (.20, .21, .21), omit='b')
    for wall, a0, a1 in (((0, box_y0, SOUTH), box_x0, box_x1), ((box_x1, 0, EAST), box_y0, box_y1), ((box_x0, 0, WEST), -box_y1, -box_y0)):
        quad('louvre box louvre', wall, a0, (a0+a1)/2-.3, deck_z+1, box_top-.8, .05, SLATS, LOUVRE)
        quad('louvre box louvre', wall, (a0+a1)/2+.3, a1, deck_z+1, box_top-.8, .05, SLATS, LOUVRE)
    for x in (box_x0, (box_x0+box_x1)/2, box_x1):
        for y in (box_y0, box_y1):
            cuboid('louvre box post', x-.4, x+.4, y-.4, y+.4, deck_z, box_top+.3, STEEL, (.16, .17, .17), omit='b')
    rx0, rx1, ry0, ry1, notch_x, notch_y = cx+58, cx+106, 68, 100, cx+76, 92
    walls = (((0, ry0, SOUTH), rx0, rx1, 'south'), ((rx1, 0, EAST), ry0, ry1, 'east'), ((0, ry1, NORTH), -rx1, -notch_x, 'north'), ((notch_x, 0, WEST), -ry1, -notch_y, 'notch side'), ((0, notch_y, NORTH), -notch_x, -rx0, 'notch'), ((rx0, 0, WEST), -notch_y, -ry0, 'west'))
    for wall, a0, a1, part in walls:
        face('plant room '+part, wall, a0, a1, deck_z-.2, ridge, 7, 7, TONES[1], top=ridge)
        on_wall('plant room parapet '+part, wall, a0, a1, -1, 0, ridge, ridge+1.6, PANELS, EDGE, whole=True)
    deck('plant room roof', rx0, rx1, ry0, notch_y, ridge+.2, CAST, ROOF_TONE)
    deck('plant room roof', notch_x, rx1, notch_y, ry1, ridge+.2, CAST, ROOF_TONE)
    door('plant room', cx+88, ry0, deck_z, SOUTH, fixture=True)
    door('plant room', rx1, 84, deck_z, EAST, fixture=True)
    louvre('plant room louvre', (0, ry0, SOUTH), rx0+3, rx0+19, deck_z+2, deck_z+15)
    round_prism('plant room vent', cx+96, 88, ridge, ridge+3, 1.5, PAINT, (.46, .47, .46), 8)
    mast(rx0+6, notch_y-6, ridge, 28)
    rail('service deck rail', (cx-122, back_y-2, deck_z), (cx+122, back_y-2, deck_z), spacing=8)
    for x in (cx-122, cx+122):
        rail('service deck rail', (x, wall_end+.5, deck_z), (x, back_y-2, deck_z), spacing=6)

    # Structure: under every roof; the atrium's rear and the plant room make the top level.
    volume('ground storey', civic.rect(cx-120.5, cx+120.5, glass_y+1.5, y1-1.5), 0, LEVEL)
    volume('middle', civic.rect(cx-116.5, cx+116.5, glass_y+4.5, y1-3.5), LEVEL, 2*LEVEL)
    volume('front', civic.rect(cx-field_a+1.5, cx+field_a-1.5, field_y+1.5, beam_y+3), 2*LEVEL, 3*LEVEL)
    volume('rear', civic.rect(cx-roof_a+1.5, cx+roof_a-1.5, beam_y+3, back_y-1.5), 2*LEVEL, rear_z-1)
    volume('atrium rear', civic.rect(cx-15, cx+15, 62, a_rear-1), rear_z-1, 83)
    volume('plant room', civic.rect(rx0+1, rx1-1, ry0+1, notch_y-1), rear_z-1, 90)


# -- Offices ------------------------------------------------------------------------------------

def fire_stair(wall_x, reach, y0, y1, landings, roof_z):
    """A steel stair in a recess behind a wall's end: zigzag flights in the recess, slim landings reaching out past the wall with a door and lamp, a ladder between them and on to the roof."""
    x0, x1 = wall_x-8, wall_x-1
    rise = 8.0
    z, going = landings[0], 1
    while z < landings[-1]-.1:
        step = min(rise, landings[-1]-z)
        a, b = (y0+3.4, y1-3.4) if going > 0 else (y1-3.4, y0+3.4)
        for x in (x0+.2, x0+3.2):
            extrude('stair flight', [(a, z-.7), (b, z+step-.7), (b, z+step), (a, z)], (0, 0, NORTH), -x-.1, -x+.1, STEEL, (.42, .44, .44))
        treads = int(abs(b-a)/1.1)
        for i in range(treads):
            t = (i+.5)/treads
            y, zz = a+(b-a)*t, z+step*t
            cuboid('stair tread', x0+.3, x0+3.1, y-.42, y+.42, zz-.12, zz, STEEL, (.50, .52, .52), detail=True)
        extrude('stair handrail', [(a, z+3.1), (b, z+step+3.1), (b, z+step+3.3), (a, z+3.3)], (0, 0, NORTH), -x0-3.3, -x0-3.1, STEEL, HANDRAIL)
        lo, hi = sorted((b, b+going*3.4))
        cuboid('stair half landing', x0, x0+3.5, lo, hi, z+step-.4, z+step, STEEL, (.60, .62, .61))
        z += step
        going = -going
    door_y = y0-4
    for k, z in enumerate(landings):
        cuboid('stair landing', x0, wall_x+reach, door_y-3.4, y1, z-.5, z, STEEL, (.62, .64, .63))
        outer = wall_x+reach-.2
        rail('stair landing rail', (outer, door_y-3.2, z), (outer, y1-.2, z), spacing=4)
        rail('stair landing rail', (wall_x, door_y-3.2, z), (outer, door_y-3.2, z), spacing=4)
        rail('stair landing rail', (x0, y1-.2, z), (outer, y1-.2, z), spacing=4)
        door('stair landing', wall_x, door_y, z, EAST, fixture=k == 1)
    ladder_on('roof ladder', (wall_x, 0, EAST), y0-.8, landings[-1], roof_z+1.2)


def offices():
    """Sheet 'Offices', 3 x 3 hexes with an entrance court of two: a slab of deep fins, a deep podium before it, a finned wing cantilevered on legs and running back to a narrow service tower, an open steel stair cage at the tower's far corner, a low annex along the east."""
    rng = random.Random(28)
    top, core_top, wing_top, base = 126, 144, 90, 36
    sx0, sx1, sy0, sy1 = -108, 71, 54, 116
    wx0, wx1, wy0, wy1 = 32, 106, -66, 54
    tx0, tx1, ty0, ty1 = 71, 104, 54, 100
    px0, py0 = -116, -4
    roof = top+.3
    apron(-126, 124, -76, 124)
    # The court: paving, two planters, bollards and a grate.
    deck('court paving', px0-6, wx0-.1, -74, py0, GROUND+.05, CAST, (.88, .87, .83))
    for x in range(-110, wx0, 18):
        deck('court joint', x-.06, x+.06, -74, py0, GROUND+.08, STEEL, (.50, .50, .48), detail=True)
    for y in range(-68, py0, 18):
        deck('court joint', px0-6, wx0-.1, y-.06, y+.06, GROUND+.08, STEEL, (.50, .50, .48), detail=True)
    for x0, x1, y0, y1 in ((-96, -82, -36, -10), (-112, -78, -66, -54)):
        h.planter(x0, x1, y0, y1, GROUND, 4.2, rng, density=.55)
    for x in (2, 12, 22):
        bollard(x, -26)
    deck('court grate', -60, -50, -70, -66, GROUND+.09, GRILLE, (.36, .38, .38))

    # The podium: grilles and small windows along the court, a deep terrace with two pier heads before the slab.
    podium = block('podium', px0, wx0, py0, sy0, 0, base, sides='sw', rim=2.2)
    south = podium['s']
    face('podium north', (0, sy0, NORTH), -sx0, -px0, 0, base, 6, 12, foot=0, top=base)
    for a0, a1 in ((-110, -84), (-74, -60), (-50, -30), (-26, -12)):
        quad('podium grille frame', south, a0-.5, a1+.5, 3.5, 14.5, .03, PANELS, (.38, .38, .36))
        quad('podium grille', south, a0, a1, 4, 14, .06, SLATS, LOUVRE)
    ribbon('podium strip window', south, -110, -68, 22, 28, rng, pitch=5, lit=.2)
    ribbon('podium strip window', south, -48, -10, 22, 28, rng, pitch=5, lit=.2)
    cast_band('podium band', south, px0, -6, 1.2, 16, 19.4, STONE)
    for x0, x1 in ((px0, -100), (-64, -48)):
        block('podium pier', x0, x1, py0-2, py0+15, base, base+8, sides='sewn', du=8, dv=8, colour=TONES[0], rim=0)
    door('podium staff', -6.5, py0, GROUND, SOUTH, fixture=True)
    block('west annex', -126, px0, py0, 58, 0, 26, sides='swn', rim=1.6)
    # The entrance: a concrete hood on the podium's end, tall glass behind it, warm inside.
    lobby = (0, py0, SOUTH)
    quad('lobby frame', lobby, 0, wx0, GROUND, 30, .03, STEEL, DARK)
    for i in range(6):
        a = i*wx0/6
        pane('lobby glass', lobby, a+.3, a+wx0/6-.3, GROUND+.2, 29.6, 'interior', True)
    quad('lobby transom', lobby, 0, wx0, 12, 12.5, .1, STEEL, DARK)
    for a in (11, 15.2, 19.4, 23.6):
        x, y = at(lobby, a)
        door('lobby', x, y, GROUND, SOUTH, lit=False)
    block('entrance hood', -3, wx0, py0-11, py0, 30, base+2, sides='sw', du=8, dv=8, colour=TONES[0], rim=0)
    soffit('entrance hood soffit', -3, wx0, py0-11, py0, 30)
    for x in (-1.6, wx0-1.8):
        lamp(x, py0, 24, SOUTH, fixture=True)

    # The slab: fins from the podium to the head, a thick end pier, plain flanks.
    slab_south = (0, sy0, SOUTH)
    face('slab south', slab_south, sx0, -96, base, top, 6, 13, TONES[1], top=top)
    fin_wall('slab fins', slab_south, -96, sx1, base+3, top-6, rng)
    on_wall('slab end pier', slab_south, sx0, -96, 0, 4.6, base, top, PANELS, TONES[1], under=True)
    cast_band('slab sill', slab_south, sx0, sx1, 4, base, base+3, STONE)
    cast_band('slab head', slab_south, sx0, sx1, 4.6, top-6, top, STONE)
    west = (sx0, 0, WEST)
    north = (0, sy1, NORTH)
    face('slab west', west, -sy1, -sy0, 0, top, 8, 13, foot=0, top=top)
    face('slab north', north, -sx1, -sx0, 0, top, 8, 13, foot=0, top=top)
    face('slab east', (sx1, 0, EAST), ty1, sy1, 0, top, 7, 13, foot=0, top=top)
    for j in range(8):
        ribbon('slab north window', north, -60, 96, 18+j*12.5, 24+j*12.5, rng, pitch=8, lit=.2)
    slot_windows('slab west window', west, -82, 42, 118)
    for a0, a1 in ((-84, -60), (20, 44), (60, 84)):
        quad('slab north grille frame', north, a0-.5, a1+.5, 3.5, 13.5, .03, PANELS, (.38, .38, .36))
        quad('slab north grille', north, a0, a1, 4, 13, .06, GRILLE, (.46, .49, .48))
    door('slab north staff', 0, sy1, GROUND, NORTH, fixture=True)
    deck('slab roof', sx0, sx1, sy0, sy1, roof, CAST, ROOF_TONE)
    for side, wall, a0, a1 in (('s', slab_south, sx0, sx1), ('n', north, -sx1, -sx0), ('w', west, -sy1, -sy0), ('e', (sx1, 0, EAST), ty1, sy1)):
        on_wall(f'slab parapet {side}', wall, a0, a1, -1.2, 0, top, top+2.4, PANELS, EDGE, whole=True)
        on_wall(f'slab coping {side}', wall, a0-.1, a1+.1, -1.3, .1, top+2.4, top+2.65, PANELS, COPING)
    rail('slab roof rail', (-90, sy0+2.4, roof+2.1), (sx1-2, sy0+2.4, roof+2.1), spacing=8)
    # Roof: two big fan plants, pipes, small units, a corner pedestal.
    plant_box('roof plant', -28, 3, 72, 100, roof, 12, 2)
    plant_box('roof plant', 8, 39, 72, 100, roof, 12, 2)
    ac_box(-50, 86, roof, 9, 8, 4.4)
    ac_box(56, 92, roof, 8, 7, 4.4)
    for x in (-34, 46):
        pipe('roof pipe', [(x, 70, roof+1), (x, 62, roof+1), (x+(8 if x < 0 else -8), 62, roof+1)], .7, sides=6)
    block('roof pedestal', sx0, sx0+16, sy1-18, sy1, top, top+7, sides='sewn', du=8, dv=8, colour=TONES[1], rim=0)
    cuboid('pedestal vent', sx0+5, sx0+11, sy1-12, sy1-6, top+7.3, top+11, PAINT, (.46, .47, .46), omit='b')

    # The tower: short in plan, right behind the wing. A column of slots on each free face, a door onto the wing's roof.
    tower = block('tower', tx0, tx1, ty0, ty1, 0, core_top, sides='en', du=6, dv=13.5, colour=STONE, rim=2.2)
    tower_s, tower_e = tower['s'], tower['e']
    face('tower south', tower_s, tx0, tx1, wing_top, core_top, 6, 13, top=core_top)
    face('tower west', tower['w'], -ty1, -ty0, top, core_top, 6, 9, top=core_top)
    slot_windows('tower window', tower_s, 94, wing_top+8, core_top-5, width=3, height=3.6, gap=1.1)
    slot_windows('tower window', tower_e, 72, 32, core_top-5, width=3, height=3.6, gap=1.1)
    door('tower deck', 80, ty0, wing_top+.3, SOUTH, fixture=True)
    door('slab roof', tx0, 72, top+.3, WEST, fixture=True)
    cuboid('tower deck pier', 96, tx1, ty0-9, ty0, wing_top, wing_top+9, PANELS, TONES[1], omit='b')
    z_t = core_top+.3
    cuboid('tower plant', tx0+7, tx1-5, ty0+8, ty1-8, z_t, z_t+3.4, PAINT, (.42, .43, .42), omit='b')
    for wall, a0, a1 in (((0, ty0+8, SOUTH), tx0+8, tx1-6), ((tx1-5, 0, EAST), ty0+9, ty1-9)):
        quad('tower plant louvre', wall, a0, a1, z_t+.4, z_t+3, .05, SLATS, LOUVRE)
    for a, b in (((tx0+4, ty0+4, z_t), (tx1-3, ty0+4, z_t)), ((tx1-3, ty0+4, z_t), (tx1-3, ty1-4, z_t)), ((tx0+4, ty1-4, z_t), (tx1-3, ty1-4, z_t)), ((tx0+4, ty0+4, z_t), (tx0+4, ty1-4, z_t))):
        rail('tower roof rail', a, b, height=5, spacing=7)

    # The open stair cage at the tower's far corner, from the annex's roof past three landings.
    annex_top = 28
    fire_stair(tx1, 7, ty1, sy1, [annex_top+.4, 44, 76, 116], core_top)
    # The low annex along the east, proud of the tower, its roof behind a rim; a big louvre at its far end.
    annex_x0, annex_x1, annex_y0, annex_y1 = 95, 120, wy1, sy1
    annex = block('east annex', annex_x0, annex_x1, annex_y0, annex_y1, 0, annex_top, sides='ens', du=7, dv=9, rim=2)
    face('east annex west', annex['w'], -annex_y1, -ty1, 0, annex_top, 5, 9, foot=0)
    door('annex staff', annex_x1, 68, GROUND, EAST, fixture=True)
    for a0, a1 in ((76, 86),):
        quad('annex grille', annex['e'], a0, a1, GROUND, 9, .05, SLATS, SHUTTER)
    quad('annex louvre frame', annex['e'], 90, 108, 2.5, 20.5, .03, PANELS, (.38, .38, .36))
    quad('annex louvre', annex['e'], 90.5, 107.5, 3, 20, .06, SLATS, LOUVRE)
    ladder_on('annex ladder', annex['n'], -112, GROUND, annex_top+2.4)

    # The wing: finned, on legs over a recessed ground floor, its head and sill heavy bands.
    wing_foot = 30
    wing_s, wing_e, wing_w = (0, wy0, SOUTH), (wx1, 0, EAST), (wx0, 0, WEST)
    soffit('wing soffit', wx0, wx1, wy0, wy1, wing_foot)
    fin_wall('wing south fins', wing_s, wx0+4, wx1-4, wing_foot+6, wing_top-6, rng, pitch=15.5, rows=6, depth=3.2)
    fin_wall('wing east fins', wing_e, wy0+4, wy1, wing_foot+6, wing_top-6, rng, pitch=13, rows=6, depth=3.2)
    quad('wing end', (0, wy1, NORTH), -wx1, -tx1, wing_foot, wing_top, 0, PANELS, TONES[1])
    face('wing west', wing_w, -wy1, -wy0, wing_foot, wing_top, 8, 12, TONES[1], top=wing_top)
    for wall, a0, a1 in ((wing_s, wx0, wx1), (wing_e, wy0, wy1)):
        cast_band('wing sill', wall, a0, a1, 4.2, wing_foot, wing_foot+6, STONE)
        cast_band('wing head', wall, a0, a1, 4.2, wing_top-6, wing_top, STONE)
    for wall, a0, a1 in ((wing_s, wx0, wx0+4), (wing_s, wx1-4, wx1), (wing_e, wy0, wy0+4)):
        on_wall('wing corner', wall, a0, a1, 0, 4.2, wing_foot+6, wing_top-6, PANELS, TONES[0], under=True)
    deck('wing roof', wx0, wx1, wy0, wy1, wing_top+.3, CAST, ROOF_TONE)
    for side, wall, a0, a1 in (('s', wing_s, wx0, wx1), ('e', wing_e, wy0, wy1), ('w', wing_w, -wy1, -wy0)):
        on_wall(f'wing parapet {side}', wall, a0, a1, -1, 0, wing_top, wing_top+2, PANELS, EDGE, whole=True)
        on_wall(f'wing coping {side}', wall, a0-.1, a1+.1, -1.1, .1, wing_top+2, wing_top+2.25, PANELS, COPING)
    rail('wing roof rail', (wx0+2, wy0+2, wing_top+2), (wx1-2, wy0+2, wing_top+2), spacing=7)
    rail('wing roof rail', (wx1-2, wy0+2, wing_top+2), (wx1-2, wy1-2, wing_top+2), spacing=7)
    for y0, y1 in ((-46, -32), (-28, -14), (-10, 4)):
        solar('wing solar', 62, 88, y0, y1, wing_top+.3, 4, 2)
    ac_box(46, -52, wing_top+.3, 10, 9, 5)
    ac_box(50, 22, wing_top+.3, 12, 10, 5.4)
    # The ground floor stands back behind the legs: grilles, windows, doors.
    recess_s, recess_e = (0, wy0+12, SOUTH), (wx1-9, 0, EAST)
    face('wing ground south', recess_s, wx0, wx1-9, 0, wing_foot, 6, 10, TONES[2], foot=0)
    face('wing ground east', recess_e, wy0+12, wy1, 0, wing_foot, 6, 10, TONES[2], foot=0)
    face('wing ground west', (wx0, 0, WEST), -py0, -wy0-12, 0, wing_foot, 6, 10, TONES[2], foot=0)
    face('wing ground north', (0, wy1, SOUTH), wx1-9, tx1, 0, wing_foot, 6, 10, TONES[2], foot=0)
    for a0, a1 in ((38, 52), (58, 74), (78, 92)):
        quad('wing ground grille', recess_s, a0, a1, 4, 13, .06, SLATS, LOUVRE)
    for a0, a1, lit in ((-46, -34, False), (-16, 0, True), (24, 42, False)):
        quad('wing ground window frame', recess_e, a0-.5, a1+.5, 5.5, 14.5, .03, PANELS, (.38, .38, .36))
        pane('wing ground window', recess_e, a0, a1, 6, 14, 'black', lit)
    door('wing ground', wx1-9, -24, GROUND, EAST, fixture=True)
    door('wing ground', wx1-9, 12, GROUND, EAST, fixture=True)
    for x0, x1 in ((wx0+2, wx0+18), (wx1-22, wx1-2)):
        frustum('wing leg', (x0+3, x1-3, wy0+2, wy0+12), (x0, x1, wy0+.5, wy0+12), 0, wing_foot+.1, PANELS, TONES[1])
    for y0, y1 in ((wy0+22, wy0+38), (wy0+62, wy0+78), (wy0+100, wy0+116)):
        frustum('wing leg', (wx1-9, wx1-3, y0+3, y1-3), (wx1-9, wx1-.5, y0, y1), 0, wing_foot+.1, PANELS, TONES[1])
    for x in (-40, 40):
        round_prism('downpipe', x, sy1+.5, GROUND, top+2, .4, PAINT, (.30, .32, .32), 6)

    # Structure.
    volume('podium', civic.rect(px0+1.5, wx0, py0+1.5, sy0), 0, base)
    volume('slab', civic.rect(sx0+1.5, sx1, sy0+1.5, sy1-1.5), 0, top)
    volume('tower', civic.rect(tx0, tx1-1.5, ty0+1.5, ty1-1.5), 0, core_top)
    volume('wing ground', civic.rect(wx0+1, wx1-10.5, wy0+13.5, wy1), 0, base)
    volume('wing', civic.rect(wx0+1.5, wx1-1.5, wy0+1.5, wy1-1), base, wing_top)
    volume('east annex', civic.rect(tx1, annex_x1-1.5, annex_y0+1.5, annex_y1-1.5), 0, LEVEL)


# -- Habitat 02 ---------------------------------------------------------------------------------

def ground_row(name, wall, a0, a1, rng, top=16.0, recess=7.0):
    """The courtyard's street storey: doors and dark glass behind heavy piers, a lamp over each door."""
    quad(name+' back', wall, a0, a1, 0, top, -recess, PANELS, DARK_RECESS)
    x0, x1, y0, y1 = plan_of(wall, a0, a1, -recess, 0)
    soffit(name+' soffit', x0, x1, y0, y1, top-.5)
    for a in (a0, a1-1):
        on_wall(name+' end', wall, a, a+1, -recess, 0, 0, top-.5, PANELS, TONES[1], whole=True)
    bays = max(1, round((a1-a0)/16))
    step = (a1-a0)/bays
    for i in range(bays):
        b0, b1 = a0+i*step, a0+(i+1)*step
        if i % 2 == 0:
            x, y = at(wall, (b0+b1)/2, -recess)
            door(name+' door', x, y, GROUND, wall[2], fixture=i % 4 == 0)
        else:
            pane(name+' glass', wall, b0+1.4, b1-1.4, GROUND+.5, top-2.5, 'black', rng.random() < .5, off=-recess+.06)
        if i < bays-1:
            on_wall(name+' pier', wall, b1-1, b1+1, -recess, 0, 0, top-.5, PANELS, TONES[1])


def bench(x0, x1, y0, y1):
    cuboid('court bench', x0, x1, y0, y1, GROUND, GROUND+2.2, PANELS, EDGE, omit='b')


def habitat2():
    """Sheet 'Habitat 02', 3 x 3 hexes with a courtyard of two: a U of galleries round the yard, a tall rear wing, a west wing stepping down to the front, a low east wing with a small tower."""
    rng = random.Random(26)
    x0, x1, y0, y1 = -116, 116, -66, 118
    cl, cr, cy = -44, 44, 54
    z0, storey = 16.0, 13.75
    row = lambda k: z0+k*storey
    rear_top, tower_top = row(8), 144
    apron(-124, 124, -78, 126)
    # The courtyard: paving, two planters and benches.
    deck('court paving', cl, cr, -78, cy, GROUND+.05, CAST, (.80, .80, .76))
    for x in range(cl+15, cr, 15):
        deck('court joint', x-.07, x+.07, -78, cy, GROUND+.08, STEEL, (.64, .64, .61), detail=True)
    for y in range(-66, cy, 15):
        deck('court joint', cl, cr, y-.07, y+.07, GROUND+.08, STEEL, (.64, .64, .61), detail=True)
    for x_a, x_b, y_a, y_b in ((-22, -2, -14, -3), (20, 30, -42, -24)):
        h.planter(x_a, x_b, y_a, y_b, GROUND, 4, rng, density=.7)
    for box in ((-30, -14, -32, -28), (-34, -18, -52, -48), (4, 20, -54, -50), (0, 16, -72, -68)):
        bench(*box)

    # The rear wing stands east of the stair tower: galleries on the yard and, above the side wings, across their roofs.
    xw = -78
    deck_z, front_z = 90, 72
    rear_s, rear_n = (0, cy, SOUTH), (0, y1, NORTH)
    quad('rear core', (0, cy+7.5, SOUTH), xw, x1, 0, rear_top, 0, PANELS, (.22, .22, .21))
    ground_row('rear ground', rear_s, cl, cr, rng)
    galleries('rear gallery', rear_s, cl+1.6, cr-1.6, row(0), 4, storey, rng)
    galleries('rear gallery upper', rear_s, cl+1.6, x1-1.6, row(4), 1, storey, rng)
    galleries('rear gallery top', rear_s, xw+1.6, x1-1.6, row(5), 3, storey, rng)
    face('rear fascia', (0, cy-.02, SOUTH), xw, x1, rear_top-1.4, rear_top, 9, 2, STONE)
    face('rear east', (x1, 0, EAST), cy, y1, 0, rear_top, 7, 13.75, foot=0, top=rear_top)
    face('rear west', (xw, 0, WEST), -84, -cy, deck_z, rear_top, 7, 12, top=rear_top)
    face('rear north', rear_n, -x1, -xw, 0, rear_top, 9, 13.75, foot=0, top=rear_top)
    deck('rear roof', xw, x1, cy-.02, y1, rear_top+.3, CAST, ROOF_TONE)
    roof_rim('rear roof', xw, x1, cy-.02, y1, rear_top, 2.8)
    rail('rear roof rail', (xw+2, cy+1.6, rear_top+.3), (x1-2, cy+1.6, rear_top+.3), spacing=9)
    rail('rear roof rail', (x1-2, cy+1.6, rear_top+.3), (x1-2, y1-2, rear_top+.3), spacing=9)
    rail('rear roof rail', (xw+2, y1-2, rear_top+.3), (x1-2, y1-2, rear_top+.3), spacing=9)
    roof = rear_top+.3
    plant_box('rear long plant', -20, 18, 88, 108, roof, 8, 4)
    plant_box('rear fan plant', 70, 108, 90, 112, roof, 6, 4, rows=2)
    ac_box(-44, 96, roof, 10, 12, 6)
    ac_box(36, 102, roof, 10, 8, 5)
    ac_box(54, 80, roof, 12, 10, 5)
    mast(-64, 104, roof, 40)
    pipe('roof conduit', [(-20, 84, roof+1), (36, 84, roof+1), (36, 96, roof+1)], .6, sides=6)
    for z in (20, 34, 48, 62, 76, 90, 104):
        ribbon('rear north window', rear_n, -96, -24, z, z+6.5, rng, pitch=7, lit=.25)
        ribbon('rear north window', rear_n, 24, 70, z, z+6.5, rng, pitch=7, lit=.25)
    door('rear north staff', 0, y1, GROUND, NORTH, fixture=True)
    for x in (-14, 14, 110):
        round_prism('downpipe', x, y1+.5, GROUND, rear_top+1, .4, PAINT, (.30, .32, .32), 6)
    round_prism('downpipe', x1+.5, 62, GROUND, rear_top+1, .4, PAINT, (.30, .32, .32), 6)
    # The stair tower rises from the west wing's deck beside the rear wing: landings on its west side, a beacon and a louvre at its head.
    tx0, tx1, ty0 = -108, xw, 84
    tower = block('stair tower', tx0, tx1, ty0, y1, deck_z, tower_top, sides='sw', du=6, dv=9, colour=TONES[1], rim=1.6)
    face('stair tower north', (0, y1, NORTH), -tx1, -tx0, 0, tower_top, 6, 13, TONES[1], foot=0, top=tower_top)
    face('stair tower east', (tx1, 0, EAST), ty0, y1, rear_top, tower_top, 6, 9, TONES[1], top=tower_top)
    face('stair tower west foot', (tx0, 0, WEST), -y1, -ty0, 0, deck_z, 6, 13, TONES[1], foot=0)
    quad('tower louvre frame', tower['s'], tx0+6, tx1-6, tower_top-11, tower_top-3, .03, PANELS, (.40, .40, .38))
    quad('tower louvre', tower['s'], tx0+6.5, tx1-6.5, tower_top-10.5, tower_top-3.5, .06, SLATS, LOUVRE)
    door('tower deck', -100, ty0, deck_z+.3, SOUTH, fixture=True)
    for z in (row(6), row(7)):
        cuboid('stair landing', tx0-8, tx0, 94, 112, z-.5, z, STEEL, (.62, .64, .63))
        soffit('stair landing under', tx0-8, tx0, 94, 112, z-.5, STEEL, DARK)
        rail('stair landing rail', (tx0-7.7, 94, z), (tx0-7.7, 112, z), spacing=4)
        rail('stair landing rail', (tx0-7.7, 94.2, z), (tx0, 94.2, z), spacing=4)
        rail('stair landing rail', (tx0-7.7, 111.8, z), (tx0, 111.8, z), spacing=4)
        door('stair landing', tx0, 103, z, WEST, fixture=True)
    beacon(-93, 101, tower_top+.3)

    # The west wing: a body to the front block's roof, a broad deck over its rear two thirds, on that a penthouse with the solar panels;
    # toward the front, steps narrowing as they climb, flush with the yard's side, each with a strip window.
    deck_front = -18
    inner = (cl, 0, EAST)
    quad('west core', (cl-7.5, 0, EAST), y0, cy+7.5, 0, front_z, 0, PANELS, (.22, .22, .21))
    quad('west core upper', (cl-7.5, 0, EAST), deck_front, cy+7.5, front_z, deck_z, 0, PANELS, (.22, .22, .21))
    ground_row('west ground', inner, y0, cy, rng)
    galleries('west gallery', inner, y0+1.6, cy-1.6, row(0), 4, storey, rng)
    galleries('west gallery upper', inner, deck_front+1.6, cy-1.6, row(4), 1, storey, rng)
    face('west fascia', inner, y0, deck_front, row(4)-1.4, front_z, 7, 2.4, STONE, off=-.02)
    face('west fascia upper', inner, deck_front, cy, row(5)-1.4, deck_z, 7, 6, STONE, off=-.02)
    front = (0, y0, SOUTH)
    west_wall = (x0, 0, WEST)
    face('west front', front, x0, cl, 0, front_z, 8, 13, foot=0, top=front_z)
    face('west wall', west_wall, -ty0, -y0, 0, front_z, 8, 13, foot=0, top=front_z)
    face('west wall north', (0, ty0, NORTH), -tx0, -x0, 0, front_z, 6, 13, foot=0)
    deck('west front roof', x0, cl, y0, ty0, front_z+.3, CAST, ROOF_TONE)
    on_wall('west ledge kerb', front, x0, cl, -1, 0, front_z, front_z+2, PANELS, EDGE, whole=True)
    on_wall('west ledge coping', front, x0-.1, cl+.1, -1.1, .1, front_z+2, front_z+2.25, PANELS, COPING)
    on_wall('west ledge kerb', west_wall, -ty0, -y0, -1, 0, front_z, front_z+2, PANELS, EDGE, whole=True)
    on_wall('west ledge coping', west_wall, -ty0-.1, -y0+.1, -1.1, .1, front_z+2, front_z+2.25, PANELS, COPING)
    rail('west ledge rail', (x0+1.6, y0+1.6, front_z+.3), (-112, y0+1.6, front_z+.3), spacing=5)
    rail('west ledge rail', (x0+1.6, y0+1.6, front_z+.3), (x0+1.6, 80, front_z+.3), spacing=7)
    # The broad deck.
    dx0 = -108
    face('west deck south', (0, deck_front, SOUTH), dx0, -92, front_z, deck_z, 6, 9, top=deck_z)
    face('west deck west', (dx0, 0, WEST), -ty0, -deck_front, front_z, deck_z, 8, 9, top=deck_z)
    deck('west deck', dx0, cl, deck_front, ty0, deck_z+.3, CAST, ROOF_TONE)
    on_wall('west deck kerb', (dx0, 0, WEST), -ty0, -deck_front, -1, 0, deck_z, deck_z+2, PANELS, EDGE, whole=True)
    on_wall('west deck coping', (dx0, 0, WEST), -ty0-.1, -deck_front+.1, -1.1, .1, deck_z+2, deck_z+2.25, PANELS, COPING)
    on_wall('west deck kerb', inner, deck_front, cy, -1, 0, deck_z, deck_z+2, PANELS, EDGE, whole=True)
    on_wall('west deck coping', inner, deck_front-.1, cy+.1, -1.1, .1, deck_z+2, deck_z+2.25, PANELS, COPING)
    on_wall('west deck kerb', (0, deck_front, SOUTH), dx0, -92, -1, 0, deck_z, deck_z+2, PANELS, EDGE, whole=True)
    rail('west deck rail', (dx0+1.6, deck_front+1, deck_z+.3), (dx0+1.6, ty0-1, deck_z+.3), spacing=7)
    rail('west deck rail', (dx0+1.6, deck_front+1.6, deck_z+.3), (-93, deck_front+1.6, deck_z+.3), spacing=7)
    ac_box(-96, -6, deck_z+.3, 10, 13, 8)
    ac_box(-103, 34, deck_z+.3, 6, 12, 6)
    cuboid('west deck vent', -106, -102, 4, 16, deck_z+.3, deck_z+2.2, PANELS, EDGE, omit='b')
    # The penthouse on it, running back to the rear wing.
    pa, pb, pf = -92, -67, 17
    pent_top = 108
    pent_s, pent_e, pent_w = (0, pf, SOUTH), (pb, 0, EAST), (pa, 0, WEST)
    face('penthouse south', pent_s, pa, pb, deck_z, pent_top, 5, 9, top=pent_top)
    face('penthouse east', pent_e, pf, cy, deck_z, pent_top, 6, 9, top=pent_top)
    face('penthouse west', pent_w, -ty0, -pf, deck_z, pent_top, 6, 9, top=pent_top)
    deck('penthouse roof', pa, pb, pf, ty0, pent_top+.3, CAST, ROOF_TONE)
    roof_rim('penthouse', pa, pb, pf, ty0, pent_top, 1.8)
    ribbon('penthouse window', pent_s, pa+3, pb-3, deck_z+6, deck_z+13, rng, pitch=5.5, lit=.4)
    for a0, a1 in ((pf+4, pf+11), (pf+15, pf+22), (pf+26, pf+33)):
        ribbon('penthouse side window', pent_e, a0, a1, deck_z+6, deck_z+13, rng, pitch=7, lit=.4)
    solar('penthouse solar', -86, -73, 35, 60, pent_top+.3, 3, 5)
    ac_box(-80, 74, pent_top+.3, 10, 9, 5)
    # The steps toward the front.
    step_e = cl-8
    for k, (sa, sf, sb, low, high) in enumerate(((-104, -58, -42, front_z, 83), (-94, -42, deck_front, 83, deck_z+2))):
        wall = (0, sf, SOUTH)
        face(f'west step south {k}', wall, sa, step_e, low, high, 6, high-low, top=high)
        face(f'west step west {k}', (sa, 0, WEST), -sb, -sf, low, high, 6, high-low, top=high)
        deck(f'west step roof {k}', sa, step_e, sf, sb, high+.3, CAST, ROOF_TONE)
        on_wall(f'west step coping {k}', wall, sa-.1, step_e+.1, -.8, .4, high, high+.9, PANELS, COPING)
        on_wall(f'west step coping {k}', (sa, 0, WEST), -sb, -sf, -.8, .4, high, high+.9, PANELS, COPING)
        ribbon(f'west step window {k}', wall, sa+4, step_e-3, low+2.4, high-2, rng, pitch=5.5, lit=.35, kind='teal')
        face(f'west step east {k}', (step_e, 0, EAST), sf, sb, low, high, 6, high-low, top=high)
    quad('west step rear', (0, deck_front, NORTH), -step_e, 94, deck_z, deck_z+2.3, 0, PANELS, TONES[0])
    quad('west step rear', (0, -42, NORTH), 94, 104, front_z, 83, 0, PANELS, TONES[0])
    block('west corner pier', step_e, cl, y0, deck_front, front_z, deck_z, sides='sewn', du=5, dv=7, colour=TONES[0], rim=0)
    block('west deck box', -83, -58, -16, -2, deck_z, deck_z+5, sides='sewn', du=6, dv=5, colour=TONES[0], rim=1)
    # The front's strip windows, grilles, doors and the bent pipe.
    for z in (20, 34, 48, 60):
        ribbon('west front window', front, -100, -60, z, z+7, rng, pitch=6.5, lit=.3, kind='teal')
    for a0, a1 in ((-104, -92), (-88, -68)):
        louvre('west front louvre', front, a0, a1, 3, 10)
    door('west front', -110, y0, GROUND, SOUTH, fixture=True)
    door('west front', -52, y0, GROUND, SOUTH, fixture=True)
    pipe('west pipe', [(-114, y0-1.2, GROUND), (-114, y0-1.2, 30), (-106, y0-1.2, 30), (-106, y0-1.2, 44)], .9, sides=6)
    for a0, a1 in ((-60, -30), (-10, 14)):
        ribbon('west side window', west_wall, a0, a1, 50, 57, rng, pitch=6.5, lit=.25)
    door('west side', x0, 30, GROUND, WEST, fixture=True)

    # The east wing: a long main block, and at the front a lower inner block, a small tower with a beacon and a service annex.
    main_y = -24
    wall_inner = (cr, 0, WEST)
    quad('east core', (cr+7.5, 0, WEST), -cy-7.5, -main_y, 0, row(4), 0, PANELS, (.22, .22, .21))
    quad('east core low', (cr+7.5, 0, WEST), -main_y, -y0, 0, row(3), 0, PANELS, (.22, .22, .21))
    face('east fascia', wall_inner, -cy, -main_y, row(4)-1.4, row(4)+1, 7, 2.4, STONE, off=-.02)
    face('east fascia low', wall_inner, -main_y, -y0, row(3)-1.4, row(3), 7, 1.4, STONE, off=-.02)
    ground_row('east ground', wall_inner, -cy, -y0, rng)
    galleries('east gallery', wall_inner, -cy+1.6, -main_y, row(0), 4, storey, rng)
    galleries('east gallery low', wall_inner, -main_y, -y0-1.6, row(0), 3, storey, rng)
    face('east main east', (x1, 0, EAST), main_y, cy, 0, row(4)+1, 8, 13.75, foot=0, top=row(4))
    deck('east main roof', cr, x1, main_y, cy, row(4)+.3, CAST, ROOF_TONE)
    for wall, a0, a1, name in (((x1, 0, EAST), main_y, cy, 'e'), ((cr, 0, WEST), -cy, -main_y, 'w')):
        on_wall('east main kerb '+name, wall, a0, a1, -1, 0, row(4)+1, row(4)+2.6, PANELS, EDGE, whole=True)
        on_wall('east main coping '+name, wall, a0-.1, a1+.1, -1.1, .1, row(4)+2.6, row(4)+2.85, PANELS, COPING)
    z_main = row(4)+.3
    solar('east solar', 70, 98, 34, 48, z_main, 5, 2)
    plant_box('east fan plant', 66, 92, 6, 22, z_main, 6, 2)
    ac_box(106, 34, z_main, 7, 8, 4.4)
    cuboid('east long louvre', 104, 110, -14, 16, z_main, z_main+3.4, PAINT, (.34, .35, .35), omit='b')
    rail('east roof rail', (x1-2, main_y+2, z_main+1.2), (x1-2, cy-2, z_main+1.2), spacing=8)
    east = (x1, 0, EAST)
    ribbon('east side window', east, -8, 34, 42, 49, rng, pitch=6.5, lit=.2)
    for a0, a1 in ((-14, 4), (12, 30), (36, 50)):
        louvre('east side louvre', east, a0, a1, 5, 12)
    door('east side', x1, 8, GROUND, EAST, fixture=True)
    round_prism('downpipe', x1+.5, 50, GROUND, row(4)+1, .4, PAINT, (.30, .32, .32), 6)

    low_top = row(3)
    inner_block = block('east inner', cr, 68, y0, main_y, 0, low_top, sides='s', du=7, dv=13.75, rim=1.6)
    for z in (20, 34, 48):
        ribbon('east inner window', inner_block['s'], cr+3, 65, z, z+7, rng, pitch=6.5, lit=.3)
    door('east inner', 56, y0, GROUND, SOUTH, fixture=True)
    ac_box(56, -46, low_top+.3, 10, 9, 5)
    rail('east inner rail', (cr+2, y0+2, low_top+1.9), (66, y0+2, low_top+1.9), spacing=6)
    tower_e = block('east tower', 68, 92, y0, main_y, 0, 90, sides='se', du=6, dv=13.5, colour=TONES[1], rim=1.6)
    face('east tower west', (68, 0, WEST), -main_y, -y0, low_top, 90, 6, 13, TONES[1], top=90)
    face('east tower north', (0, main_y, NORTH), -92, -68, row(4), 90, 6, 10, TONES[1], top=90)
    slot_windows('east tower window', tower_e['s'], 75, 12, 84, width=1.8, height=6, gap=2)
    slot_windows('east tower window', tower_e['s'], 85, 12, 84, width=1.8, height=6, gap=2)
    door('east tower', 80, y0, GROUND, SOUTH, fixture=True)
    beacon(80, -45, 90.3)
    annex = block('east annex', 92, x1, y0, main_y, 0, 36, sides='se', du=6, dv=12, rim=1.6)
    shutter('east shutter', annex['s'], 97, 111, 15, rng)
    door('east annex', x1, -44, GROUND, EAST, fixture=True)
    deck('east shutter stripes', 97, 111, y0-5, y0, GROUND+.03, HAZARD, (1, 1, 1))
    face('east main south', (0, main_y, SOUTH), 92, x1, 36, row(4)+1, 6, 12, top=row(4))
    face('east main south inner', (0, main_y, SOUTH), cr, 68, low_top, row(4)+1, 6, 12, top=row(4))

    # Structure: behind the galleries; the courtyard's two hexes stay empty.
    volume('rear', civic.rect(xw+1.5, x1-1.5, cy+8.5, y1-1.5), 0, rear_top)
    volume('stair tower', civic.rect(tx0+1.5, tx1, ty0+1.5, y1-1.5), 0, tower_top)
    volume('west body', civic.rect(x0+1.5, cl-8.5, y0+1.5, ty0), 0, front_z)
    volume('west deck', civic.rect(dx0+1.5, cl-8.5, deck_front, ty0), front_z, deck_z)
    volume('west step', civic.rect(-92.5, cl-8.5, -40.5, deck_front), front_z, deck_z)
    volume('penthouse', civic.rect(pa+1.5, pb-1.5, pf+1.5, ty0), deck_z, pent_top)
    volume('east main', civic.rect(cr+8.5, x1-1.5, main_y, cy+8.5), 0, 4*LEVEL)
    volume('east inner', civic.rect(cr+8.5, 68, y0+1.5, main_y), 0, 3*LEVEL)
    volume('east tower', civic.rect(68, 92, y0+1.5, main_y), 0, 90)
    volume('east annex', civic.rect(92, x1-1.5, y0+1.5, main_y), 0, 2*LEVEL)


# -- Medical Center -----------------------------------------------------------------------------

def ward_face(name, wall, a0, a1, top, rng):
    """A ward wing's long side: three lit strip windows between proud concrete bands."""
    face(name, wall, a0, a1, 0, top, 8, 13.5, foot=0, top=top)
    for z, z1 in ((9.8, 15.6), (23.5, 31.5), (40, 48)):
        ribbon(name+' window', wall, a0+5, a1-5, z, z1, rng, pitch=6, lit=.55, kind='teal')
    for z in (16.5, 33):
        on_wall(name+' band', wall, a0, a1, 0, 1.4, z, z+5.5, PANELS, TONES[0], under=True)
    on_wall(name+' band', wall, a0, a1, 0, 1.4, top-5, top, PANELS, TONES[0], under=True)


def medical_center():
    """Sheet 'Medical Center', 3 x 3 hexes, three of them empty: a plant-topped tower where four arms meet, battered arm ends, an entrance under a canopy, an ambulance canopy beside it, a ramp."""
    rng = random.Random(30)
    cy = 28
    half, tower_top, arm_top, front_top = 42, 90, 54, 36
    wy0, wy1 = cy-33, cy+33
    ax0, ax1 = -110, 110
    ny1, sy0, sx = 118, -78, 36
    tower_y0, tower_y1 = cy-half, cy+half
    # Aprons follow the cross; the front has a forecourt.
    apron(-122, 104, -104, wy0-6)
    apron(ax0-14, -half+6, wy0-6, wy1+6)
    apron(half-6, ax1+14, wy0-6, wy1+6)
    apron(-half-4, half+4, tower_y1-6, ny1+12)
    # Arms.
    for sign, name in ((-1, 'west'), (1, 'east')):
        lo, hi = sorted((sign*half, sign*ax1))
        n_end = EAST if sign > 0 else WEST
        ward_face(name+' arm south', (0, wy0, SOUTH), lo, hi, arm_top, rng)
        ward_face(name+' arm north', (0, wy1, NORTH), -hi, -lo, arm_top, rng)
        face(name+' arm end', (sign*ax1, 0, n_end), *sorted((sign*wy0, sign*wy1)), 0, arm_top, 7, 13.5, foot=0, top=arm_top)
        deck(name+' arm roof', lo, hi, wy0, wy1, arm_top+.3, CAST, ROOF_TONE)
        roof_rim(name+' arm', lo, hi, wy0, wy1, arm_top, 2.2)
        # The battered end, a skirt up to the roof band.
        tip = sign*(ax1+10)
        a, b = sorted((sign*ax1, tip))
        ta, tb = sorted((sign*ax1, sign*(ax1+2.4)))
        frustum(name+' battered end', (a, b, wy0-4, wy1+4), (ta, tb, wy0-1, wy1+1), 0, arm_top+1, PANELS, TONES[1])
        cuboid(name+' end cap', ta, tb, wy0-1.3, wy1+1.3, arm_top+1, arm_top+2, PANELS, COPING, omit='b')
        for x_c in (sign*(half+7), sign*(ax1-6)):
            for y_c in (wy0+5, wy1-5):
                cuboid(name+' corner pedestal', x_c-5, x_c+5, y_c-5, y_c+5, arm_top+.3, arm_top+3.4, PANELS, TONES[0], omit='b')
        ac_box(sign*80, cy+10, arm_top+.3, 9, 8, 4.4)
        solar(name+' solar', *sorted((sign*58, sign*76)), cy-22, cy-8, arm_top+.3, 3, 2)
        ac_box(sign*60, cy+14, arm_top+.3, 8, 8, 4)
    # The north arm.
    ward_face('north arm east', (half-2, 0, EAST), tower_y1, ny1, arm_top, rng)
    ward_face('north arm west', (-half+2, 0, WEST), -ny1, -tower_y1, arm_top, rng)
    n = half-2
    face('north arm end', (0, ny1, NORTH), -n, n, 0, arm_top, 7, 13.5, foot=0, top=arm_top)
    deck('north arm roof', -n, n, tower_y1, ny1, arm_top+.3, CAST, ROOF_TONE)
    roof_rim('north arm', -n, n, tower_y1, ny1, arm_top, 2.2)
    frustum('north battered end', (-n-4, n+4, ny1, ny1+9), (-n-1, n+1, ny1, ny1+2.4), 0, arm_top+1, PANELS, TONES[1])
    cuboid('north end cap', -n-1.3, n+1.3, ny1, ny1+2.4, arm_top+1, arm_top+2, PANELS, COPING, omit='b')
    ac_box(-14, 104, arm_top+.3, 12, 8, 4.4)
    ac_box(20, 94, arm_top+.3, 8, 8, 4)
    for x_c in (-n+5, n-5):
        cuboid('north corner pedestal', x_c-5, x_c+5, ny1-10, ny1, arm_top+.3, arm_top+3.4, PANELS, TONES[0], omit='b')

    # The central tower: two great louvres to the south, pipes and a ladder on the east, cooling plant on top.
    tower = block('tower', -half, half, tower_y0, tower_y1, 0, tower_top, sides='sewn', du=8, dv=12, rim=2.2)
    for z in (arm_top+6, arm_top+20):
        louvre('tower louvre', tower['s'], -28, 28, z, z+9)
    louvre('tower east louvre', tower['e'], tower_y0+14, tower_y1-30, arm_top+14, arm_top+24)
    east_t = tower['e']
    for a, r in ((tower_y1-24, 1.0), (tower_y1-19, 1.0), (tower_y1-14, .7)):
        pipe('tower riser', [(half, a, arm_top+2.5), (half+2.5, a, arm_top+2.5), (half+2.5, a, tower_top-3), (half, a, tower_top-3)], r, sides=6)
    ladder_on('tower ladder', east_t, tower_y1-8, arm_top+.3, tower_top+1)
    door('tower roof door', -20, tower_y1, arm_top+.3, NORTH, fixture=True)
    door('tower roof door', half, cy-10, arm_top+.3, EAST, fixture=True)
    door('tower roof door', -half, cy-10, arm_top+.3, WEST, fixture=True)
    door('tower roof door', 14, tower_y0, front_top+.3, SOUTH, fixture=True)
    z_t = tower_top+.3
    plant_box('cooling plant', -24, 24, cy-2, cy+22, z_t, 12, 3)
    plant_box('cooling plant', -24, 24, cy-26, cy-3, z_t, 12, 3)
    for a, b in (((-30, cy-32, z_t), (30, cy-32, z_t)), ((30, cy-32, z_t), (30, cy+30, z_t)), ((-30, cy+30, z_t), (30, cy+30, z_t)), ((-30, cy-32, z_t), (-30, cy+30, z_t))):
        rail('plant rail', a, b, spacing=7)
    for x, y in ((-36, tower_y0+5), (36, tower_y0+5), (-36, tower_y1-5), (36, tower_y1-5)):
        round_prism('amber beacon', x, y, z_t, z_t+2.2, .7, PAINT, AMBER, 8, light=AMBER_LIGHT)
    mast(34, cy+34, z_t, 30)
    ac_box(-35, cy+12, z_t, 6, 9, 4)

    # The front block: lower, its glass over the entrance canopy, the lobby under it.
    front = (0, sy0, SOUTH)
    face('front south', front, -sx, sx, 18, front_top, 8, 9, top=front_top)
    ribbon('front window', front, -30, 30, 24, 31.5, rng, pitch=6, lit=.55, kind='teal')
    face('front lobby back', front, -sx, sx, 0, 18, 6, 9, foot=0)
    for sign, name in ((-1, 'west'), (1, 'east')):
        side = (sign*sx, 0, EAST if sign > 0 else WEST)
        a0, a1 = sorted((sign*sy0, sign*tower_y0))
        face('front block '+name, side, a0, a1, 0, front_top, 7, 12, foot=0, top=front_top)
        ribbon('front side window', side, a0+6, a1-6, 24, 31.5, rng, pitch=6, lit=.45, kind='teal')
        ta, tb = sorted((sign*sx, sign*(sx+2.4)))
        a, b = sorted((sign*sx, sign*(sx+9)))
        frustum('front battered pier', (a, b, sy0-9, sy0+8), (ta, tb, sy0-1, sy0+2), 0, front_top+1, PANELS, TONES[1])
    deck('front roof', -sx, sx, sy0, tower_y0, front_top+.3, CAST, ROOF_TONE)
    roof_rim('front block', -sx, sx, sy0, tower_y0, front_top, 2.2)
    for x, y in ((-18, -62), (18, -62), (-18, -32), (18, -32)):
        cuboid('front roof vent', x-3, x+3, y-3, y+3, front_top+.3, front_top+2.4, PANELS, EDGE, omit='b')
    # Landing and entrance.
    landing = 1.8
    deck('entrance landing', -sx-9, sx+9, sy0-14, sy0, landing, CAST, (.86, .86, .82))
    quad('landing front', (0, sy0-14, SOUTH), -sx-9, sx+9, 0, landing, 0, CAST, (.70, .70, .67))
    quad('landing side', (sx+9, 0, EAST), sy0-14, sy0, 0, landing, 0, CAST, (.70, .70, .67))
    lobby_wall = (0, sy0+.04, SOUTH)
    for i in range(10):
        a = -30+i*6
        pane('lobby glass', lobby_wall, a+.2, a+5.8, landing+.2, 15.5, 'teal', True)
    quad('lobby head', lobby_wall, -30, 30, 15.5, 18, .03, PANELS, (.36, .36, .34))
    quad('lobby transom', lobby_wall, -30, 30, 11, 11.4, .1, STEEL, DARK)
    for a in (-6.3, -2.1, 2.1, 6.3):
        x, y = at(lobby_wall, a)
        door('lobby', x, y, landing, SOUTH, lit=False)
    # The entrance canopy on two teal-lit pylons.
    cast_band('entrance canopy', front, -34, 34, 11, 16, 20.5, STONE)
    for a in (-16, 0, 16):
        cuboid('canopy light', a-5, a+5, sy0-9, sy0-8, 15.8, 16, PAINT, AMBER, light=AMBER_LIGHT, omit='t')
    h.fixtures.append((0, sy0-6, 15))
    for x in (-33, 33):
        cuboid('canopy pylon', x-1.6, x+1.6, sy0-11, sy0-8, landing, 16, PANELS, TONES[0], omit='b')
        quad('canopy pylon light', (x, sy0-11, SOUTH), -.7, .7, 5, 12, .05, PAINT, (.30, .62, .58), light=(.25, .85, .80))
    for x in (-24, -12, 12, 24):
        bollard(x, sy0-20)

    # The ramp from the west along the front, with its rail.
    far, near = -112, -sx-9
    back, ahead = sy0-5, sy0-13
    top_face = [(far, back, GROUND), (near, back, landing), (near, ahead, landing), (far, ahead, GROUND)][::-1]
    add('entrance ramp', CAST, (.82, .82, .78), top_face, [(0, 1, 2, 3)])
    add('ramp cheek', CAST, (.70, .70, .67), [(far, ahead, GROUND), (near, ahead, GROUND), (near, ahead, landing)], [(0, 1, 2)])
    steps = 6
    for y in (ahead+.2, back-.2):
        for i in range(steps):
            ax, bx = far+(near-far)*i/steps, far+(near-far)*(i+1)/steps
            az, bz = GROUND+(landing-GROUND)*i/steps, GROUND+(landing-GROUND)*(i+1)/steps
            bar = [(bx, y, bz+3.1), (ax, y, az+3.1), (ax, y, az+3.3), (bx, y, bz+3.3)]
            add('ramp rail', STEEL, HANDRAIL, bar, [(0, 1, 2, 3)])
            add('ramp rail', STEEL, HANDRAIL, bar[::-1], [(0, 1, 2, 3)])
            cuboid('ramp rail post', ax-.1, ax+.1, y-.1, y+.1, az, az+3.2, STEEL, HANDRAIL, omit='bt', detail=True)

    # The ambulance canopy: a heavy slab on two columns beside the front block, amber lights under it, a bay door behind.
    cx0, cx1, cy0, cy1 = sx+9, 92, -69, wy0
    cuboid('ambulance canopy', cx0, cx1, cy0, cy1, 17, 21, PANELS, STONE, omit='b')
    soffit('ambulance canopy soffit', cx0, cx1, cy0, cy1, 17)
    cuboid('ambulance canopy coping', cx0-.2, cx1+.2, cy0-.2, cy1, 21, 21.3, PANELS, COPING, omit='b')
    for x, y in ((cx0+5, cy0+4), (cx1-5, cy0+4)):
        cuboid('canopy column', x-3, x+3, y-3, y+3, 0, 17, PANELS, TONES[1], omit='b')
        quad('canopy column light', (x, y-3, SOUTH), -.8, .8, 5, 12, .05, PAINT, (.30, .62, .58), light=(.25, .85, .80))
    for x in (cx0+14, cx0+27, cx0+40):
        cuboid('canopy light', x-4, x+4, -40, -39, 16.8, 17, PAINT, AMBER, light=AMBER_LIGHT, omit='t')
    h.fixtures.append(((cx0+cx1)/2, -40, 16))
    quad('ambulance bay door', (0, wy0, SOUTH), cx0+3, cx1-3, GROUND, 15, 1.5, SLATS, SHUTTER)
    for x in (cx1+8,):
        door('east arm staff', x, wy0, GROUND, SOUTH, fixture=True)
    door('west arm staff', -60, wy0, GROUND, SOUTH, fixture=True)
    door('north arm staff', half-2, ny1-16, GROUND, EAST, fixture=True)

    # Structure: the three corner hexes stay empty of volume; the ambulance canopy's slab gives its hex a roof, without a floor.
    volume('west arm', civic.rect(ax0+1, -half, wy0+1.5, wy1-1.5), 0, arm_top)
    volume('east arm', civic.rect(half, ax1-1, wy0+1.5, wy1-1.5), 0, arm_top)
    volume('north arm', civic.rect(-half+3.5, half-3.5, tower_y1, ny1-1.5), 0, arm_top)
    volume('tower', civic.rect(-half+1.5, half-1.5, tower_y0+1.5, tower_y1-1.5), 0, tower_top)
    volume('front block', civic.rect(-sx+1.5, sx-1.5, sy0+1.5, tower_y0+1.5), 0, front_top)
    volume('ambulance canopy', civic.rect(cx0, cx1, cy0, cy1), LEVEL-1, LEVEL)


# -- Assembly and export ------------------------------------------------------------------------

BUILDINGS = {'industrial-works': (industrial_works, 12), 'commercial-center': (commercial_center, 12), 'offices': (offices, 8), 'habitat2': (habitat2, 13.75), 'medical-center': (medical_center, 12)}


def build_scene(name):
    """The building's objects in a fresh scene."""
    full = 'civic-'+name
    old = bpy.data.scenes.get(full)
    if old:
        bpy.data.batch_remove([obj for obj in old.objects if len(obj.users_scene) == 1])
    h.weathered_material.__defaults__[0].clear()
    shared.fresh(full)
    h.bins.clear()
    h.fixtures.clear()
    builder, storey = BUILDINGS[name]
    h.SHIFT_Y = 0
    h.PODIUM = 0
    h.PANEL_REPEAT = 2*storey
    builder()
    h.flush()
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
    levels = {i: shared.export_model([obj for obj in shared.objects if i < 2 or far_piece(obj)], f'{full}-lod{i}', level=i, exact=True) for i in (0, 1, 2)}
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
        sheet(args[0], args[1])
