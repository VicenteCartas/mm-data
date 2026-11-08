"""The civic and Utopia looks as connected building kits: their pieces GLBs and kit JSONs.

Run: blender -b --factory-startup --python theme_kits.py -- <civic|utopia> ...
Writes data/models/buildings/<kit>/<kit>-pieces.glb and <kit>.json, for the game's bays kit (GeneratedKit, BayKit).

A piece's x runs along its wall, left to right seen from outside, from 0 to its length; its facade faces -y (out of the
wall line at y 0), z up from its storey's floor; a storey is 18 high, a roof piece stands on the roof. Each piece is built
once, from the civic and Utopia buildings' own parts and finishes; its far level leaves out the parts flagged as detail.
Utopia's plants and trees are its buildings' own (utopia_buildings), replayed fewer and larger far away as theirs are.

The runtime picks a base, floors and a roof per hex and per storey, so a variant's storeys share their profile (slab
edges, bands, canopy heights) and differ in their bays, laid by the wall's place; the editor's Variant row picks the
storey type. Utopia rounds its convex corners: a short piece lies along each facet of the arc. Roofs carry fittings,
laid out about the hex's middle.
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import authored_examples as shared
import civic_blocks as c
import civic_buildings as cb
import civic_habitat as h
import utopia_buildings as u
from civic_blocks import COPING, HAZARD, SHUTTER, SOUTH, TEAL_GLASS
from civic_citadel import GLAZING
from civic_habitat import (CAST, EDGE, LOUVRE, PAINT, PALE_GLASS, PANELS, SLATS, STEEL, TONES, add, cuboid, deck, disc, rail,
                           round_prism)
from glb_geometry import write_glb
from utopia_buildings import (GLASS as U_GLASS, GLASS_TINT, LAWN_REPEAT, LOBBY, NIGHT, RAIL, RAIL_TINT, REPEAT as STONE_REPEAT,
                              SLAT, STONE as WHITE_STONE, STONE_SHADE, STONE_TINT, TURF as LAWN, TURF_TINT as LAWN_TINT)

h.SHIFT_Y = 0  # flush() centres the habitat's plan; pieces stand in their own frame.
W, LEVEL = 24.0, 18.0
ROUND = 6.0  # A rounded corner's facet piece, stretched to each facet.
DARK_BACK = (.30, .30, .29)
DATA = Path(__file__).resolve().parents[2]/'data'
front = (0, 0, SOUTH)  # The facade's plane in a piece.


def plane(y):
    """A wall plane parallel to the facade, y behind it (negative: in front)."""
    return (0, y, SOUTH)


# -- Parts shared by both looks ---------------------------------------------------------------------

def back_wall(length, z0, z1, depth=3.0, colour=(.62, .62, .58)):
    """The inner face that closes a piece, seen from inside the building."""
    add('back', CAST, colour, [(length, depth, z0), (0, depth, z0), (0, depth, z1), (length, depth, z1)], [(0, 1, 2, 3)])


def glass(name, x0, x1, z0, z1, y, lit, tint=GLAZING, key=h.DARK_GLASS):
    """A pane facing out at y, lit at night or dark."""
    add(name, key, tint, [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], [(0, 1, 2, 3)], light='night' if lit else 'off')


def window(name, x0, x1, z0, z1, y, lit, tint=GLASS_TINT):
    """Utopia's warm glass."""
    glass(name, x0, x1, z0, z1, y, lit, tint, U_GLASS)


def mullions(name, x0, x1, z0, z1, y, count, colour=(.32, .33, .33), key=STEEL):
    for k in range(1, count):
        x = x0+(x1-x0)*k/count
        cuboid(name+' mullion', x-.15, x+.15, y-.15, y+.05, z0, z1, key, colour, omit='bk', detail=True)


def recess(name, x0, x1, z0, z1, depth, colour=TONES[1], key=PANELS):
    """A box cut into the wall depth deep: reveals, soffit, sill and a dark back."""
    add(name+' reveal', key, colour, [(x0, 0, z0), (x0, depth, z0), (x0, depth, z1), (x0, 0, z1)], [(0, 1, 2, 3)])
    add(name+' reveal', key, colour, [(x1, depth, z0), (x1, 0, z0), (x1, 0, z1), (x1, depth, z1)], [(0, 1, 2, 3)])
    add(name+' soffit', key, (.80, .80, .76), [(x0, 0, z1), (x1, 0, z1), (x1, depth, z1), (x0, depth, z1)], [(3, 2, 1, 0)])
    add(name+' sill', key, colour, [(x0, 0, z0), (x1, 0, z0), (x1, depth, z0), (x0, depth, z0)], [(0, 1, 2, 3)])
    add(name+' back', PAINT, DARK_BACK, [(x0, depth, z0), (x1, depth, z0), (x1, depth, z1), (x0, depth, z1)], [(0, 1, 2, 3)])


def facade(name, holes, z0, z1, length=W, colour=TONES[0], du=8, dv=9, key=PANELS, start=0.0):
    """The facade plane from start to length and z0 to z1 less rectangular holes (x0, x1, za, zb), in strips."""
    xs = sorted({start, length, *[min(max(v, start), length) for hole in holes for v in hole[:2]]})
    for xa, xb in zip(xs, xs[1:]):
        inside = [hole for hole in holes if hole[0] <= xa+1e-6 and hole[1] >= xb-1e-6]
        zs = sorted({z0, z1, *[v for hole in inside for v in hole[2:]]})
        for za, zb in zip(zs, zs[1:]):
            if not any(hole[2] <= za+1e-6 and hole[3] >= zb-1e-6 for hole in inside):
                c.face(name, front, xa, xb, za, zb, du, dv, colour, key=key, top=z1)


def plants(x0, x1, y, z, rng, size=(4, 7), spacing=3.4):
    """Utopia's planting along a planter at y from x0 to x1 (utopia_buildings.plant_band): shrubs, spiky plants and lilac
    flowers, whose leaning cards reach about .91 of their size from the root: on a wall, within the 5 an isolated Angled
    hex leaves outside its walls. No trailing ferns: they would hang into the storey below, and a kit's storey keeps to
    its own 18 units."""
    xs = np.arange(x0, x1+1e-6, .5)
    u.plant_band('planter', np.c_[xs, np.full(len(xs), y)], z, range(1, len(xs)-1), rng, spacing=spacing, size=size, deep=.3)


# -- Civic: brutalist concrete ----------------------------------------------------------------------
CANOPY = 12.6, 15.4  # Every ground bay's canopy or band: one line along the street.


def civic_canopy(deep):
    c.cast_band('canopy', front, 0, W, 4.5 if deep else 1.4, *CANOPY, TONES[0])
    facade('canopy wall', [], CANOPY[0], LEVEL)


def civic_shop(rng, kind):
    """A shopfront deep under the canopy between piers: lit windows, a roller shutter or the lobby doors."""
    facade('shop wall', [(2.5, 21.5, 0, 12.5)], 0, CANOPY[0])
    recess('shop', 2.5, 21.5, 0, 12.5, 3)
    civic_canopy(True)
    if kind == 'closed':
        add('shop shutter', SLATS, SHUTTER, [(2.5, 2.9, .3), (21.5, 2.9, .3), (21.5, 2.9, 12.5), (2.5, 2.9, 12.5)], [(0, 1, 2, 3)])
        for x in (2.5, 20.3):
            add('shop guard', HAZARD, (1, 1, 1), [(x, 2.8, .3), (x+1.2, 2.8, .3), (x+1.2, 2.8, 6.5), (x, 2.8, 6.5)], [(0, 1, 2, 3)], detail=True)
    elif kind == 'door':
        glass('lobby', 2.5, 7.5, .6, 12.4, 2.95, True, TEAL_GLASS, PALE_GLASS)
        glass('lobby', 16.5, 21.5, .6, 12.4, 2.95, True, TEAL_GLASS, PALE_GLASS)
        for x in (8.2, 12.1):
            add('lobby door frame', STEEL, (.30, .31, .31), [(x, 2.92, .3), (x+3.7, 2.92, .3), (x+3.7, 2.92, 8.6), (x, 2.92, 8.6)], [(0, 1, 2, 3)])
            glass('lobby door', x+.4, x+3.3, .6, 8.2, 2.85, True, TEAL_GLASS, PALE_GLASS)
        glass('lobby transom', 7.5, 16.5, 9, 12.4, 2.95, True, TEAL_GLASS, PALE_GLASS)
        mullions('lobby', 2.5, 7.5, .6, 12.4, 2.9, 2)
        mullions('lobby', 16.5, 21.5, .6, 12.4, 2.9, 2)
    else:
        panes = 3 if kind == 'wide' else 4
        for k in range(panes):
            x0, x1 = 2.5+19*k/panes, 2.5+19*(k+1)/panes
            glass('shop window', x0+.15, x1-.15, 1.1, 11.6, 2.95, rng.random() < .7, TEAL_GLASS, PALE_GLASS)
        cuboid('shop stall', 2.5, 21.5, 2.3, 3, 0, 1.1, PANELS, TONES[2], omit='bk')
        mullions('shop', 2.5, 21.5, 1.1, 11.6, 2.9, panes)
        add('shop sign', PAINT, (.18, .19, .19), [(5, 2.6, 10.4), (19, 2.6, 10.4), (19, 2.6, 12.2), (5, 2.6, 12.2)], [(0, 1, 2, 3)], detail=True)
    for x0, x1 in ((0, 2.5), (21.5, W)):
        cuboid('shop pier', x0, x1, -1.2, 0, 0, CANOPY[0], PANELS, TONES[1], omit='bk')
    back_wall(W, 0, LEVEL)


def civic_plinth(rng, kind):
    """A battered plinth under a shallow band: slot windows, a louvre, a service door or a billboard."""
    facade('plinth wall', [], 3.5, CANOPY[0])
    c.extrude('plinth batter', [(0, 0), (2.4, 0), (0, 3.5)], front, 0, W, PANELS, TONES[1])
    civic_canopy(False)
    if kind == 'slots':
        for x in (6, 12, 18):
            c.slot_windows('plinth slot', front, x, 5, 11.5, width=2.2, height=2.8, gap=1.4)
    elif kind == 'louvre':
        c.louvre('plinth louvre', front, 4, 20, 5, 11)
    elif kind == 'door':
        h.door('plinth service', 12, 0, 3.5, SOUTH, lit=False)
        cuboid('plinth step', 9, 15, -2.4, 0, 0, 3.5, PANELS, TONES[2], omit='bk')
        c.slot_windows('plinth slot', front, 19.5, 5, 11.5, width=2.2, height=2.8, gap=1.4)
    else:
        c.advert('plinth billboard', front, 3, 21, 5.5, 10.8, d=1.2)
    back_wall(W, 0, LEVEL)


def civic_gallery(rng, kind):
    """An access gallery: a deep recess behind an upstand and rail, doors, windows and louvres at its back."""
    depth = 6.0
    facade('gallery wall', [(0, W, 3.4, 15.6)], 0, LEVEL)
    add('gallery floor', CAST, (.62, .62, .58), [(0, 0, 3.4), (W, 0, 3.4), (W, depth, 3.4), (0, depth, 3.4)], [(0, 1, 2, 3)])
    add('gallery ceiling', PANELS, (.78, .78, .74), [(0, 0, 15.6), (W, 0, 15.6), (W, depth, 15.6), (0, depth, 15.6)], [(3, 2, 1, 0)])
    cuboid('gallery upstand', 0, W, -1.2, 0, 0, 6.2, PANELS, TONES[rng.randrange(3)], omit='bk')
    cuboid('gallery upstand coping', -.02, W+.02, -1.3, .1, 6.2, 6.45, CAST, COPING, omit='b')
    rail('gallery rail', (0, -.6, 6.45), (W, -.6, 6.45), 2.4, 8)
    add('gallery back', PANELS, DARK_BACK, [(0, depth, 3.4), (W, depth, 3.4), (W, depth, 15.6), (0, depth, 15.6)], [(0, 1, 2, 3)])
    cells = {'a': 'wwdw', 'b': 'dwwd', 'c': 'wlww', 'd': 'wdlw'}[kind]
    cell = W/len(cells)
    for k, what in enumerate(cells):
        x0, x1 = k*cell+.6, (k+1)*cell-.6
        if what == 'w':
            glass('gallery window', x0, x1, 5.2, 13.6, depth-.06, rng.random() < .35)
            mullions('gallery window', x0, x1, 5.2, 13.6, depth-.1, 2)
        elif what == 'd':
            add('gallery door', PAINT, (.26, .30, .30), [(x0+.6, depth-.06, 3.4), (x1-.6, depth-.06, 3.4), (x1-.6, depth-.06, 12.4), (x0+.6, depth-.06, 12.4)], [(0, 1, 2, 3)])
        else:
            c.louvre('gallery louvre', plane(depth), x0+.3, x1-.3, 6, 13)
    for x0, x1 in ((0, 1.2), (W-1.2, W)):
        cuboid('gallery pier', x0, x1, 0, depth, 3.4, 15.6, PANELS, TONES[1], omit='bkt')
    back_wall(W, 0, LEVEL, depth+.1)


def civic_ribbon(rng, kind):
    """Heavy precast bands with a ribbon window between; a blank panel with slots; a balcony box under the ribbon."""
    c.cast_band('ribbon sill band', front, 0, W, .9, 4.6, 6.5, TONES[0])
    c.cast_band('ribbon head band', front, 0, W, .9, 14, 16.2, TONES[1])
    if kind == 'panel':
        facade('panel wall', [], 0, LEVEL, colour=TONES[2])
        for x in (5, 10, 15, 20):
            c.slot_windows('panel slot', front, x, 7, 13.5, width=2, height=2.6, gap=1.2)
        back_wall(W, 0, LEVEL)
        return
    facade('ribbon wall', [(0, W, 6.5, 14)], 0, LEVEL)
    recess('ribbon', 0, W, 6.5, 14, 1.5, TONES[2])
    panes = 4
    for k in range(panes):
        glass('ribbon window', W*k/panes+.15, W*(k+1)/panes-.15, 6.6, 13.9, 1.44, rng.random() < (.6 if kind == 'lit' else .3))
    mullions('ribbon', 0, W, 6.6, 13.9, 1.4, panes)
    if kind == 'balcony':
        cuboid('balcony box', 4, 20, -4.5, 0, 0, 4.6, PANELS, TONES[1], omit='bk')
        cuboid('balcony coping', 3.9, 20.1, -4.6, 0, 4.6, 4.85, CAST, COPING, omit='bk')
        rail('balcony rail', (4.2, -4.2, 4.85), (19.8, -4.2, 4.85), 2.4, 6)
    back_wall(W, 0, LEVEL)


def civic_fins(rng, kind):
    """Deep concrete fins every 6 over dark glass and pale spandrels; a louvre, a blank panel or a sunshade among them."""
    c.face('fins back', plane(2.2), 0, W, 0, LEVEL, 8, 9, DARK_BACK)
    add('fins head soffit', PANELS, TONES[0], [(0, 0, 15.8), (W, 0, 15.8), (W, 2.2, 15.8), (0, 2.2, 15.8)], [(3, 2, 1, 0)])
    c.face('fins head', front, 0, W, 15.8, LEVEL, 8, 3, TONES[0], top=LEVEL)
    bays, step = 4, W/4
    for k in range(bays):
        x0, x1 = k*step+.9, (k+1)*step-.9
        if kind == 'louvre' and k in (1, 2):
            c.louvre('fins louvre', plane(2.1), x0, x1, 1, 15.2)
        elif kind == 'blank' and k == 3:
            c.face('fins blank', plane(.4), x0, x1, 0, 15.8, 4, 9, TONES[1])
        else:
            glass('fins glass', x0, x1, 5.4, 15.4, 2.14, rng.random() < .3)
            add('fins spandrel', PANELS, (.58, .60, .58), [(x0, 1.3, .4), (x1, 1.3, .4), (x1, 1.3, 5.2), (x0, 1.3, 5.2)], [(0, 1, 2, 3)])
    # A fin at each bay's ends is half a fin, its neighbour's the other half.
    for k in range(bays+1):
        x = k*step
        omit = 'bk'+('l' if k == 0 else 'r' if k == bays else '')
        cuboid('fin', max(0, x-.9), min(W, x+.9), -1.2, 2.2, 0, 15.8, PANELS, TONES[1], omit=omit)
    if kind == 'shade':
        cuboid('fins sunshade', 0, W, -3.2, -1.2, 14.6, 15.2, PANELS, TONES[0], omit='bk')
    back_wall(W, 0, LEVEL, 2.3)


def civic_parapet(rng, kind):
    """A heavy parapet with its coping; low with a rail; raised over its middle."""
    spans = [(0, W, 2.2 if kind == 'rail' else 4.2)] if kind != 'tall' else [(0, 6, 4.2), (6, 18, 7.0), (18, W, 4.2)]
    for x0, x1, height in spans:
        cuboid('parapet', x0, x1, 0, 1.6, 0, height, PANELS, TONES[rng.randrange(3)], omit='bft')
        c.face('parapet face', front, x0, x1, -.4, height, 8, height+.4, TONES[0], top=height)
        cuboid('parapet coping', x0-.02, x1+.02, -.25, 1.85, height, height+.3, CAST, COPING, omit='b')
    if kind == 'rail':
        rail('parapet rail', (0, .8, 2.5), (W, .8, 2.5), 2.6, 8)


# Civic roof fittings: each stands on the roof about its origin.
def civic_fan_unit(rng):
    c.plant_box('fan unit', -9, 9, -6, 6, 0, 6.5, 2, rows=2)


def civic_louvre_cage(rng):
    cuboid('cage', -7, 7, -5, 5, 0, 9, PAINT, (.20, .21, .21), omit='b')
    for wall, a0, a1 in (((0, -5, SOUTH), -7, 7), ((7, 0, (1, 0)), -5, 5), ((0, 5, (0, 1)), -7, 7), ((-7, 0, (-1, 0)), -5, 5)):
        c.quad('cage louvre', wall, a0+.4, a1-.4, .6, 8.4, .05, SLATS, LOUVRE)
    for x in (-7, 0, 7):
        for y in (-5, 5):
            cuboid('cage post', x-.35, x+.35, y-.35, y+.35, 0, 9.3, STEEL, (.16, .17, .17), omit='b', detail=True)


def civic_plant_room(rng):
    walls = c.block('plant room', -8, 8, -6, 6, 0, 10, 'sewn', 6, 6, TONES[1], rim=1.2)
    h.door('plant room', -2, -6, 0, SOUTH, lit=False)
    c.louvre('plant room louvre', walls['s'], 2, 6.5, 2, 8)
    c.mast(5, 3, 10.3, 16)


def civic_vent_stack(rng):
    cuboid('vent plinth', -4, 4, -3, 3, 0, 1.2, PANELS, EDGE, omit='b')
    for x in (-2, 2):
        round_prism('vent stack', x, 0, 1.2, 7.5, 1.1, STEEL, (.52, .54, .54), 10)
        round_prism('vent stack cap', x, 0, 7.5, 8.1, 1.5, STEEL, (.40, .42, .42), 10, detail=True)


def civic_water_tank(rng):
    for x in (-4, 4):
        for y in (-4, 4):
            cuboid('tank leg', x-.4, x+.4, y-.4, y+.4, 0, 4, STEEL, (.36, .38, .38), omit='b')
    round_prism('water tank', 0, 0, 4, 11, 5.6, PAINT, (.56, .58, .56), 16)
    round_prism('water tank lid', 0, 0, 11, 11.6, 4, PAINT, (.46, .48, .46), 12, detail=True)


def civic_hatch(rng):
    cuboid('hatch kerb', -3, 3, -3, 3, 0, 1.4, PANELS, EDGE, omit='b')
    deck('hatch lid', -2.6, 2.6, -2.6, 2.6, 1.42, PAINT, (.30, .32, .32))


# -- Utopia: white stone, terraces and glass --------------------------------------------------------
NOSE = 4.4  # How far a terrace's rounded slab edge stands out.


def nose(name, x0, x1, z0, z1, out, segments=4):
    """A rounded slab edge from the wall out to out, its front a half round from z0 to z1."""
    r = (z1-z0)/2
    profile = [(0, z0), (out-r, z0)]
    profile += [(out-r+r*math.cos(a), z0+r+r*math.sin(a)) for a in (-math.pi/2+math.pi*k/segments for k in range(1, segments))]
    profile += [(out-r, z1), (0, z1)]
    c.extrude(name, profile, front, x0, x1, WHITE_STONE, STONE_TINT)


def stone(name, x0, x1, z0, z1, y=0.0, colour=STONE_TINT):
    """A white stone face."""
    c.face(name, plane(y), x0, x1, z0, z1, 6, 6, colour, key=WHITE_STONE, top=z1)


def planter(name, x0, x1, z, out, rng, height=2.4, density=.85):
    """A planter on a terrace's edge: a stone lip, soil, shrubs."""
    cuboid(name+' lip', x0, x1, -out, -out+.8, z, z+height, WHITE_STONE, STONE_TINT, omit='b')
    deck(name+' soil', x0, x1, -out+.8, -out+3, z+height-.4, LAWN, LAWN_TINT)
    plants(x0, x1, -1.6, z+height-.4, rng, size=(2.4, 3.0), spacing=2.4/density)


def rooms(name, x0, x1, z0, z1, y, rng, panes=4, warm=.4, fins=False):
    """A storey of glass at y, some panes lit; slender white fins between, or mullions."""
    for k in range(panes):
        window(name, x0+(x1-x0)*k/panes+.1, x0+(x1-x0)*(k+1)/panes-.1, z0, z1, y, rng.random() < warm)
    for k in range(1, panes):
        x = x0+(x1-x0)*k/panes
        if fins:
            cuboid(name+' fin', x-.35, x+.35, y-2.2, y, z0, z1, WHITE_STONE, STONE_TINT, omit='bk')
        else:
            cuboid(name+' mullion', x-.12, x+.12, y-.12, y+.05, z0, z1, RAIL, RAIL_TINT, omit='bk', detail=True)


def oval(rng, length=W, z0=2.6, z1=LEVEL):
    """White stone round an oval window, its glass deep in the reveal."""
    cx, cz, rx, rz, sides = length/2, (z0+z1)/2+.4, min(8.0, length/2-2), 5.6, 16
    angles = [math.tau*k/sides for k in range(sides)]
    ring = [(cx+rx*math.cos(a), cz+rz*math.sin(a)) for a in angles]
    # The facade's edge in each ring point's direction: its corners land at 45, 135, 225 and 315 degrees.
    box = [(cx+max(-cx, min(length-cx, math.cos(a)*99)), cz+max(z0-cz, min(z1-cz, math.sin(a)*99))) for a in angles]
    lit = rng.random() < .5
    for k in range(sides):
        j = (k+1) % sides
        add('oval wall', WHITE_STONE, STONE_TINT, [(box[k][0], 0, box[k][1]), (box[j][0], 0, box[j][1]), (ring[j][0], 0, ring[j][1]), (ring[k][0], 0, ring[k][1])], [(0, 1, 2, 3)])
        add('oval reveal', WHITE_STONE, STONE_SHADE, [(ring[k][0], 0, ring[k][1]), (ring[j][0], 0, ring[j][1]), (ring[j][0], 3, ring[j][1]), (ring[k][0], 3, ring[k][1])], [(0, 1, 2, 3)])
    add('oval glass', U_GLASS, GLASS_TINT, [(x, 2.95, z) for x, z in ring], [tuple(range(sides))], light='night' if lit else 'off')


def utopia_terrace(rng, kind, length=W):
    """A terrace storey: glass set back behind a rounded slab edge with its planter; a stone pier; an oval window."""
    nose('terrace edge', 0, length, 0, 2.6, NOSE)
    if kind == 'pier':
        rooms('terrace glass', 0, 9, 2.6, 16.6, 0, rng, panes=2)
        rooms('terrace glass', 15, length, 2.6, 16.6, 0, rng, panes=2)
        cuboid('terrace pier', 9, 15, -1.6, 0, 2.6, LEVEL, WHITE_STONE, STONE_TINT, omit='bk')
        stone('terrace head', 0, 9, 16.6, LEVEL)
        stone('terrace head', 15, length, 16.6, LEVEL)
        planter('terrace planter', 0, length, 2.6, NOSE, rng, density=.5)
    elif kind == 'oval':
        oval(rng, length)
        rail('terrace rail', (0, -NOSE+.6, 2.6), (length, -NOSE+.6, 2.6), 3, 8)
    else:
        rooms('terrace glass', 0, length, 2.6, 16.6, 0, rng, panes=max(1, round(length/6)))
        stone('terrace head', 0, length, 16.6, LEVEL)
        if kind == 'rail':
            rail('terrace rail', (0, -NOSE+.6, 2.6), (length, -NOSE+.6, 2.6), 3, 8)
        else:
            planter('terrace planter', 0, length, 2.6, NOSE, rng, density=.9 if kind == 'dense' else .45)
    back_wall(length, 0, LEVEL)


def utopia_band(rng, kind, length=W):
    """A white band with its rounded nose under a storey of glass between slender white fins, or curved white slats."""
    nose('band edge', 0, length, 0, 3.2, 2.6)
    if kind == 'slats':
        recess('band', 0, length, 3.2, 16.4, 1.6, STONE_TINT, WHITE_STONE)
        for k in range(8):
            z = 4+k*1.6
            c.extrude('band slat', [(-.4, z), (1.4, z+.25), (1.4, z+.6), (-.4, z+.35)], front, 0, length, WHITE_STONE, SLAT)
    else:
        rooms('band glass', 0, length, 3.2, 16.4, .4, rng, panes=max(1, round(length/(4 if kind == 'fins' else 6))), warm=.45, fins=kind == 'fins')
    stone('band head', 0, length, 16.4, LEVEL)
    back_wall(length, 0, LEVEL)


def utopia_arcade(rng, kind, length=W):
    """The ground storey: a round-headed arch in white stone with lobby glass deep behind; a planted plinth; the door arch."""
    if kind == 'planted':
        stone('plinth', 0, length, 0, 4.4)
        cuboid('plinth bed', 0, length, -4.4, 0, 0, 2.6, WHITE_STONE, STONE_TINT, omit='bk')
        deck('plinth soil', 0, length, -4, -.2, 2.4, LAWN, LAWN_TINT)
        plants(0, length, -1.6, 2.4, rng, size=(2.4, 3.0), spacing=2.2)
        rooms('plinth glass', 0, length, 4.4, 15.6, .6, rng, panes=max(1, round(length/6)), warm=.6)
        stone('plinth head', 0, length, 15.6, LEVEL)
        back_wall(length, 0, LEVEL)
        return
    cx, half, spring, crown, depth, sides = length/2, 7.5, 9.0, 15.0, 4.0, 8
    curve = [(cx-half*math.cos(a), spring+(crown-spring)*math.sin(a)) for a in (math.pi*k/sides for k in range(sides+1))]
    outline = [(cx-half, 0)]+curve+[(cx+half, 0)]
    for (xa, za), (xb, zb) in zip(outline, outline[1:]):
        if xb > xa+1e-6:
            add('arcade wall', WHITE_STONE, STONE_TINT, [(xa, 0, za), (xb, 0, zb), (xb, 0, LEVEL), (xa, 0, LEVEL)], [(0, 1, 2, 3)])
        add('arcade reveal', WHITE_STONE, STONE_SHADE, [(xa, 0, za), (xa, depth, za), (xb, depth, zb), (xb, 0, zb)], [(0, 1, 2, 3)])
    stone('arcade pier', 0, cx-half, 0, LEVEL)
    stone('arcade pier', cx+half, length, 0, LEVEL)
    back = depth-.06
    if kind == 'door':
        add('arcade door', U_GLASS, LOBBY, [(cx-5, back, .3), (cx+5, back, .3), (cx+5, back, spring), (cx-5, back, spring)], [(0, 1, 2, 3)], light='night')
        window('arcade glass', cx-half, cx-5, .3, spring, back, True, LOBBY)
        window('arcade glass', cx+5, cx+half, .3, spring, back, True, LOBBY)
        cuboid('arcade door frame', cx-5.3, cx+5.3, depth-.4, depth, spring-.4, spring, RAIL, RAIL_TINT, omit='bk')
        cuboid('arcade step', cx-6, cx+6, -2, 0, 0, .4, WHITE_STONE, STONE_SHADE, omit='bk')
    else:
        window('arcade glass', cx-half, cx+half, .3, spring, back, rng.random() < .75, LOBBY)
        mullions('arcade', cx-half, cx+half, .3, spring, back-.04, 3, RAIL_TINT, RAIL)
    add('arcade fanlight', U_GLASS, LOBBY, [(x, back, z) for x, z in curve][::-1], [tuple(range(len(curve)))], light='night')
    deck('arcade floor', cx-half, cx+half, 0, depth, .3, WHITE_STONE, STONE_SHADE)
    add('arcade back', PAINT, DARK_BACK, [(cx-half, depth, 0), (cx+half, depth, 0), (cx+half, depth, crown), (cx-half, depth, crown)], [(0, 1, 2, 3)])
    back_wall(length, 0, LEVEL, depth+.1)


def utopia_rim(rng, kind, length=W):
    """The roof's edge: a rounded white rim, a planter of shrubs behind it or a slender rail on it."""
    nose('rim', 0, length, -.6, 2.4, 1.6)
    cuboid('rim upstand', 0, length, -.1, 1.6, 0, 2.4, WHITE_STONE, STONE_TINT, omit='bf')
    if kind == 'garden':
        cuboid('rim planter', 0, length, 1.6, 5.6, .3, 2.2, WHITE_STONE, STONE_TINT, omit='bf')
        deck('rim soil', 0, length, 1.6, 5.4, 2.0, LAWN, LAWN_TINT)
        plants(0, length, 3.6, 2.0, rng, size=(3.5, 6))
    else:
        rail('rim rail', (0, .7, 2.4), (length, .7, 2.4), 2.6, 8)


# Utopia's roof fittings.
def utopia_skylight(rng):
    sides, rx, ry, rise = 16, 7.0, 5.0, 3.4
    ring = lambda s, z: [(rx*s*math.cos(a), ry*s*math.sin(a), z) for a in (math.tau*k/sides for k in range(sides))]
    v = ring(1.18, 0)+ring(1.18, 1.2)+ring(1, 1.2)
    f = [(k, (k+1) % sides, sides+(k+1) % sides, sides+k) for k in range(sides)]
    f += [(sides+k, sides+(k+1) % sides, 2*sides+(k+1) % sides, 2*sides+k) for k in range(sides)]
    add('skylight kerb', WHITE_STONE, STONE_TINT, v, f)
    rows = [ring(math.cos(t*math.pi/2*.9), 1.2+rise*math.sin(t*math.pi/2)) for t in (0, .35, .7, 1)]
    f = [(r*sides+k, r*sides+(k+1) % sides, (r+1)*sides+(k+1) % sides, (r+1)*sides+k) for r in range(len(rows)-1) for k in range(sides)]
    f.append(tuple((len(rows)-1)*sides+k for k in range(sides)))
    add('skylight glass', U_GLASS, GLASS_TINT, [p for row in rows for p in row], f, light='night')


def utopia_tree(rng):
    sides = 10
    v = [(4.2*math.cos(a), 4.2*math.sin(a), z) for z in (0, 2.4) for a in (math.tau*k/sides for k in range(sides))]
    add('tree planter', WHITE_STONE, STONE_TINT, v, [(k, (k+1) % sides, sides+(k+1) % sides, sides+k) for k in range(sides)])
    disc('tree soil', 0, 0, 2.3, 4.2, 'z', LAWN, LAWN_TINT, sides)
    u.tree(0, 0, 2.3, rng.uniform(13, 16), rng.uniform(11, 14), rng)


def utopia_pergola(rng):
    for x in (-7, 7):
        for y in (-4, 4):
            cuboid('pergola post', x-.35, x+.35, y-.35, y+.35, 0, 7, WHITE_STONE, STONE_TINT, omit='b')
    for y in (-4, 4):
        cuboid('pergola beam', -8, 8, y-.3, y+.3, 7, 7.6, WHITE_STONE, STONE_TINT, omit='b')
    for k in range(9):
        x = -7+14*k/8
        cuboid('pergola slat', x-.18, x+.18, -5, 5, 7.6, 8, WHITE_STONE, STONE_TINT, omit='b', detail=k % 2 == 1)
    plants(-7, 7, -4.6, 0, rng, size=(3, 5), spacing=3)


def utopia_solar(rng):
    for x in (-6, 6):
        cuboid('solar post', x-.3, x+.3, -.3, .3, 0, 5, RAIL, RAIL_TINT, omit='b')
    add('solar panel', h.DARK_GLASS, GLAZING, [(-8, -5, 4.6), (8, -5, 4.6), (8, 5, 6.6), (-8, 5, 6.6)], [(0, 1, 2, 3)], light='off')
    add('solar panel back', RAIL, RAIL_TINT, [(-8, -5, 4.55), (-8, 5, 6.55), (8, 5, 6.55), (8, -5, 4.55)], [(0, 1, 2, 3)])


def utopia_bed(rng):
    cuboid('bed', -7, 7, -3, 3, 0, 2, WHITE_STONE, STONE_TINT, omit='b')
    deck('bed soil', -6.6, 6.6, -2.6, 2.6, 2.02, LAWN, LAWN_TINT)
    plants(-6.6, 6.6, 0, 2.02, rng, size=(3, 5), spacing=2.8)


def utopia_pavilion(rng):
    sides, r = 12, 5.5
    ring = [(r*math.cos(a), r*math.sin(a)) for a in (math.tau*k/sides for k in range(sides))]
    for k in range(sides):
        (xa, ya), (xb, yb) = ring[k], ring[(k+1) % sides]
        add('pavilion glass', U_GLASS, GLASS_TINT, [(xa, ya, .2), (xb, yb, .2), (xb, yb, 6.4), (xa, ya, 6.4)], [(0, 1, 2, 3)], light='night')
    v = [(x*1.25, y*1.25, z) for z in (6.4, 7.4) for x, y in ring]+[(0, 0, 8.2)]
    f = [(k, (k+1) % sides, sides+(k+1) % sides, sides+k) for k in range(sides)]+[(sides+k, sides+(k+1) % sides, 2*sides) for k in range(sides)]
    f.append(tuple(range(sides))[::-1])
    add('pavilion roof', WHITE_STONE, STONE_TINT, v, f)


# -- Frontier: prefab colony containers -------------------------------------------------------------
PLATING = 'structures/frontier/plating'  # Blue-grey enamel in its albedo: drawn white.
SOLAR = 'structures/lunar/solar-cells'
DOME_GLASS = 'structures/lunar/dome-glass'  # The biodome's see-through glass (user, 2026-11-07).
DECK = 'structures/common/diamond-plate'
FRAME = (.74, .76, .78)  # Light steel frames, matte (MATTE): satin steel flared white from one side.
MATTE = 'structures/common/matte-steel'
ORANGE = (.86, .36, .08)
DARK = (.17, .18, .19)
DOOR_GREY = (.44, .46, .48)
TEAL = (.06, .55, .57)
TEAL_LIGHT = (.15, .95, .85)
GREENS = (.50, .78, .32)
CHAMFER = 2.4  # Every module edge's bevel, light steel: between storeys, at joints, round the roof (BayKit joints, seams).
BAND, BAND_OUT = .9, .25  # The steel band along a module face just inside its bevels; how far it stands out.
INNER = CHAMFER+BAND  # Where a module face's plating shows clear of its bands.
BORDER = 1.6  # The steel border round a module's roof, inside its bevel.
BEVEL = (.62, .64, .66)  # The bevels' steel, a little darker than the frames: facing up, they catch the sun.
CREASE = .62  # Past this share of the chamfer a bevel is dark: modules part in a dark crease between light frames.
FOOT = 1.0  # A ground module stands this high on its skids, a shadowed recess under its bottom bevel.
ROOF_INSET = .12  # How far inside its wall line the kit lays a roof piece (KitOutline.ROOF_INSET); seams lie on theirs.


def facing(verts, normal):
    """The face through verts, wound to face normal."""
    a, b, d = (np.array(v, float) for v in verts[:3])
    return tuple(range(len(verts))) if np.dot(np.cross(b-a, d-a), normal) > 0 else tuple(reversed(range(len(verts))))


EDGES = {'top': True, 'bottom': True}  # Off where an authored tall module's storeys run on (frontier_buildings).
NUMBERED = True  # Habitat bays carry their module numbers; authored buildings other than habitats do not.


def split(verts, keep):
    """The part of a convex polygon where keep(vertex) >= 0."""
    out = []
    for i, p in enumerate(verts):
        q = verts[(i+1) % len(verts)]
        a, b = keep(p), keep(q)
        if a >= 0:
            out.append(p)
        if (a < 0) != (b < 0):
            t = a/(a-b)
            out.append(tuple(p[n]+(q[n]-p[n])*t for n in range(3)))
    return out


def bevel(verts, normal, depth):
    """A bevel face: light steel, dark where depth(vertex) (0 at its outer edge, CHAMFER at the groove) passes CREASE."""
    t = CREASE*CHAMFER
    for name, colour, keep in (('frame bevel', BEVEL, lambda v: t-depth(v)), ('bevel crease', DARK, lambda v: depth(v)-t)):
        part = split(verts, keep)
        if len(part) >= 3:
            add(name, MATTE, colour, part, [facing(part, normal)])


def bevels(length, foot=0.0):
    """A module's top and bottom edges along a wall, bevelled: where it meets the module above or below, the roof or the
    ground, in a dark-creased groove; a ground module's bottom `foot` up on its skids, a dark recess under it."""
    L, H, C = length, LEVEL, CHAMFER
    if EDGES['top']:
        bevel([(0, 0, H-C), (L, 0, H-C), (L, C, H), (0, C, H)], (0, -1, 1), lambda v: v[1])
    if EDGES['bottom']:
        bevel([(0, C, foot), (L, C, foot), (L, 0, foot+C), (0, 0, foot+C)], (0, -1, -1), lambda v: v[1])
        if foot:
            add('foot recess', PAINT, DARK, [(0, C, 0), (L, C, 0), (L, C, foot), (0, C, foot)], [(0, 1, 2, 3)])


def face_span(foot=0.0):
    """Where a stretch of module face runs, between its bevels."""
    return foot+CHAMFER if EDGES['bottom'] else 0.0, LEVEL-CHAMFER if EDGES['top'] else LEVEL


def module_face(length=W, holes=(), gaps=(), foot=0.0):
    """A stretch of a module's face: its bevels, a steel band inside each (the bottom one broken at gaps (x0, x1)), and
    plating between, less holes (x0, x1, z0, z1); a ground module's `foot` up on skids. It runs on into the next bay's: a
    module ends only at its joints (frontier_joint) and corners (frontier_corner)."""
    L, H, C = length, LEVEL, CHAMFER
    bevels(L, foot)
    low, high = face_span(foot)
    edges = sorted({0.0, L, *[min(max(v, 0.0), L) for gap in gaps for v in gap]})
    for x0, x1 in zip(edges, edges[1:]):
        if EDGES['bottom'] and not any(gap[0] <= x0+1e-6 and gap[1] >= x1-1e-6 for gap in gaps):
            cuboid('frame band', x0, x1, -BAND_OUT, 0, low, low+BAND, MATTE, FRAME, omit='bk')
    if EDGES['top']:
        cuboid('frame band', 0, L, -BAND_OUT, 0, H-C-BAND, H-C, MATTE, FRAME, omit='bk')
    facade('plating', holes, low, high, L, (1, 1, 1), du=6, dv=6, key=PLATING)
    back_wall(L, 0, H, colour=DARK)


def port(name, x0, x1, z0, z1, rng, lit=None):
    """A window set in a dark steel frame, an amber-lit room behind it or none."""
    recess(name, x0, x1, z0, z1, .8, DARK, PAINT)
    glass(name+' glass', x0, x1, z0, z1, .74, rng.random() < .45 if lit is None else lit)
    for a0, a1, b0, b1 in ((x0-.45, x1+.45, z0-.45, z0), (x0-.45, x1+.45, z1, z1+.45), (x0-.45, x0, z0, z1), (x1, x1+.45, z0, z1)):
        cuboid(name+' frame', a0, a1, -.12, 0, b0, b1, PAINT, DARK, omit='bk')


def chevrons(x, z, size=1.6, count=3):
    """The orange /// marks."""
    for k in range(count):
        a = x+k*size*.75
        add('chevron', PAINT, ORANGE, [(a, -.05, z), (a+size*.4, -.05, z), (a+size*.9, -.05, z+size*.7), (a+size*.5, -.05, z+size*.7)],
            [(0, 1, 2, 3)], detail=True)


def marker(x, z, y=-.3):
    """A small amber marker light."""
    add('marker light', PAINT, (.50, .42, .26), [(x-.3, y, z-.2), (x+.3, y, z-.2), (x+.3, y, z+.2), (x-.3, y, z+.2)], [(0, 1, 2, 3)],
        light=c.AMBER_LIGHT)


def feet(xs):
    """The skids a module stands on, a marker light on each."""
    for x in xs:
        cuboid('skid foot', x-1.6, x+1.6, -.3, CHAMFER, 0, CHAMFER*.8, PAINT, DARK)
        marker(x, CHAMFER*.4, -.32)


def utility_box(x, z, w=3.2, height=2.6):
    cuboid('utility box', x-w/2, x+w/2, -1.1, 0, z, z+height, PAINT, (.36, .38, .40), omit='bk')
    add('utility box louvre', SLATS, LOUVRE, [(x-w/2+.4, -1.12, z+.4), (x+w/2-.4, -1.12, z+.4), (x+w/2-.4, -1.12, z+height-.5), (x-w/2+.4, -1.12, z+height-.5)],
        [(0, 1, 2, 3)])


def pipe_run(points, radius=.4):
    """A pipe through points (x, y, z) with orange clamps along its straight runs; its ends go into something."""
    u.tube('pipe', c.bend(points, radius*2.2), radius, PAINT, (.30, .31, .32), sides=6)
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        for k in range(1, int(length//6)+1):
            t = k*6/length
            if t < .95:
                p = [a[i]+(b[i]-a[i])*t for i in range(3)]
                d = [(b[i]-a[i])/length*.25 for i in range(3)]
                u.tube('pipe clamp', [tuple(p[i]-d[i] for i in range(3)), tuple(p[i]+d[i] for i in range(3))], radius*1.35, PAINT, ORANGE, sides=6)


WINDOWS = 7.6, 13.2  # The sheets' windows sit a little above a module's middle, about 30% of its height.
BAY_WINDOWS = {
    'pair': [(4.2, 9.2), (10.4, 15.4)], 'single': [(4.6, 10.4)], 'wide': [(4.2, 15.2)], 'four': [(1, 5), (7, 11), (13, 17), (19, 23)],
    'med-pair': [(4.6, 10.6), (13.4, 19.4)], 'med-triple': [(4.2, 19.8)], 'med-single': [(9, 15)], 'centre': [(6.5, 17.5)],
    'three': [(2.5, 7.5), (9.5, 14.5), (16.5, 21.5)],
    'big': [(5, 19, 6.2, 13.4)],
}
LABELS = {'pair': '01', 'single': '02', 'wide': '03', 'vent': '04'}  # A habitat module's number, by its windows.


def frontier_bay(rng, kind, base=False, length=W):
    """A stretch of a module's face: windows, its number and chevrons, a vent or a utility box; the medical teal stripe;
    industrial louvres, pipes and slit windows; on the ground, a skid under its middle."""
    holes = [window if len(window) == 4 else (*window, *WINDOWS) for window in BAY_WINDOWS.get(kind, ())]
    if kind == 'slit':
        holes = [(4, 20, 12.2, 13.8)]
    module_face(length, holes, foot=FOOT if base else 0.0)
    for x0, x1, a, b in holes:
        port('window', x0, x1, a, b, rng)
        if x1-x0 > 12:
            for k in (1, 2):
                x = x0+(x1-x0)*k/3
                cuboid('window mullion', x-.25, x+.25, -.12, .8, a, b, PAINT, DARK, omit='b')
    if kind in LABELS and NUMBERED:
        cb.marking('H-'+LABELS[kind], (16.2, -.06, 9.2), (1, 0, 0), 2.0)
        chevrons(16.4, 6.4, 1.4)
    if kind == 'single':
        utility_box(13, 4.2)
    elif kind == 'med-single':
        utility_box(18.5, 4.2)
    elif kind == 'vent':
        cuboid('vent frame', 4.6, 12.4, -.2, 0, 6.4, 13, PAINT, DARK, omit='bk')
        add('vent grille', h.GRILLE, (.62, .64, .66), [(5, -.22, 6.8), (12, -.22, 6.8), (12, -.22, 12.6), (5, -.22, 12.6)], [(0, 1, 2, 3)])
    elif kind == 'louvre':
        cuboid('louvre frame', 5, 19, -.2, 0, 4.4, 14, PAINT, DARK, omit='bk')
        add('louvre', SLATS, LOUVRE, [(5.4, -.22, 4.8), (18.6, -.22, 4.8), (18.6, -.22, 13.6), (5.4, -.22, 13.6)], [(0, 1, 2, 3)])
    elif kind == 'pipes':
        # Two risers out of the wall and back into it; one feeds a utility box.
        pipe_run([(6, 0, 4.2), (6, -.6, 4.2), (6, -.6, 13.8), (6, 0, 13.8)])
        pipe_run([(8.4, 0, 13.8), (8.4, -.6, 13.8), (8.4, -.6, 5.6), (16.4, -.6, 5.6)])
        utility_box(18, 4.4)
    elif kind == 'boxes':
        utility_box(6.5, 4.4)
        utility_box(17, 4.4, 4.4, 3.4)
        chevrons(10, 6)
    elif kind == 'med-box':
        utility_box(5.5, 4.4)
        chevrons(17, 8.4, 1.6)
    if kind.startswith('med'):
        add('medical stripe', PAINT, TEAL, [(0, -.04, 6.0), (length, -.04, 6.0), (length, -.04, 6.6), (0, -.04, 6.6)], [(0, 1, 2, 3)])
    if base:
        feet((length/2,))


def frame_ring(name, outer, inner, out, key, colour, depth=.4):
    """A door frame standing out from the wall: its face between two outlines (x, z) open at the bottom, its sides."""
    n = len(outer)
    v = [(x, -out, z) for x, z in outer]+[(x, -out, z) for x, z in inner]
    add(name, key, colour, v, [(i, i+1, n+i+1, n+i)[::-1] for i in range(n-1)])
    for ring, y1, flip in ((outer, 0, False), (inner, depth, True)):
        for i in range(1, n):
            (xa, za), (xb, zb) = ring[i-1], ring[i]
            quad = [(xa, -out, za), (xb, -out, zb), (xb, y1, zb), (xa, y1, za)]
            add(name+' side', key, colour, quad, [(3, 2, 1, 0) if flip else (0, 1, 2, 3)])


def airlock(rng, kind, face=True):
    """The orange airlock: a chamfered frame standing out, a steel door with a window, an amber light, its panel; MED
    over the medical one. Industrial: a wide roll-up door under an orange beam, hazard chevrons on it. Without its face,
    the door alone, for a wall that is not a module's (frontier_buildings)."""
    cx = W/2
    if kind == 'rollup':
        x0, x1, top = 4.6, 19.4, CHAMFER+11.4
        if face:
            module_face(W, [(x0-1, x1+1, CHAMFER, top+1.6)], [(x0-1, x1+1)], FOOT)
        for a, b in ((x0-1, x0), (x1, x1+1)):
            cuboid('door jamb', a, b, -1, 0, CHAMFER, top, PAINT, ORANGE, omit='bk')
        cuboid('door beam', x0-1, x1+1, -1.2, 0, top, top+1.6, PAINT, ORANGE, omit='k')
        add('door shutter', SLATS, SHUTTER, [(x0, .3, CHAMFER), (x1, .3, CHAMFER), (x1, .3, top), (x0, .3, top)], [(0, 1, 2, 3)])
        for x in (x0+2, x1-6.4):
            chevrons(x, CHAMFER+1, 1.8)
        marker(cx-4, top+.8, -1.25)
        marker(cx+4, top+.8, -1.25)
        cuboid('door step', x0-1, x1+1, -1.6, 0, 0, CHAMFER, PAINT, DARK, omit='bk')
        return
    half, height, rim = 2.5, 8.8, 1.2
    top = CHAMFER+height
    inner = [(cx-half, CHAMFER), (cx-half, top-.9), (cx-half+.9, top), (cx+half-.9, top), (cx+half, top-.9), (cx+half, CHAMFER)]
    outer = [(cx-half-rim, CHAMFER), (cx-half-rim, top+rim-1.4), (cx-half-rim+1.4, top+rim), (cx+half+rim-1.4, top+rim),
             (cx+half+rim, top+rim-1.4), (cx+half+rim, CHAMFER)]
    if face:
        module_face(W, [(cx-half-rim, cx+half+rim, CHAMFER, top+rim)], [(cx-half-rim, cx+half+rim)], FOOT)
    # The plating's hole is square; behind the frame's chamfered head a dark plate closes it.
    add('airlock surround', PAINT, DARK, [(cx-half-rim, .5, CHAMFER), (cx+half+rim, .5, CHAMFER), (cx+half+rim, .5, top+rim),
                                           (cx-half-rim, .5, top+rim)], [(0, 1, 2, 3)])
    out = 2.4  # Deep enough to read as the sheets' vestibule.
    frame_ring('airlock frame', outer, inner, out, PAINT, ORANGE)
    add('airlock door', PAINT, DOOR_GREY, [(x, .4, z) for x, z in inner][::-1], [tuple(range(len(inner)))])
    glass('airlock window', cx-.8, cx+.8, CHAMFER+4.6, CHAMFER+6.6, .36, True)
    add('airlock light', PAINT, (.50, .42, .26), [(cx-1.6, -out-.04, top+.2), (cx+1.6, -out-.04, top+.2), (cx+1.6, -out-.04, top+.7),
                                                  (cx-1.6, -out-.04, top+.7)],
        [(0, 1, 2, 3)], light=c.AMBER_LIGHT)
    cuboid('airlock panel', cx+half+rim+.5, cx+half+rim+1.7, -.5, 0, CHAMFER+3.6, CHAMFER+6.2, PAINT, DARK, omit='bk')
    cuboid('airlock step', cx-half-rim, cx+half+rim, -out-.8, 0, 0, CHAMFER, PAINT, DARK, omit='bk')
    if kind == 'med':
        cuboid('med sign', cx-3.2, cx+3.2, -out-.3, -out, top+rim+.4, top+rim+2.6, PAINT, (.12, .13, .14), omit='bk')
        for a0, a1, b0, b1 in ((cx-2.7, cx-1.3, top+rim+1.25, top+rim+1.75), (cx-2.25, cx-1.75, top+rim+.8, top+rim+2.2)):
            add('med cross', PAINT, TEAL, [(a0, -out-.33, b0), (a1, -out-.33, b0), (a1, -out-.33, b1), (a0, -out-.33, b1)], [(0, 1, 2, 3)],
                light=TEAL_LIGHT)
        cb.marking('MED', (cx-.9, -out-.34, top+rim+.85), (1, 0, 0), 1.3)
        add('medical stripe', PAINT, TEAL, [(0, -.04, 6.0), (cx-half-rim, -.04, 6.0), (cx-half-rim, -.04, 6.6), (0, -.04, 6.6)], [(0, 1, 2, 3)])
        add('medical stripe', PAINT, TEAL, [(cx+half+rim, -.04, 6.0), (W, -.04, 6.0), (W, -.04, 6.6), (cx+half+rim, -.04, 6.6)], [(0, 1, 2, 3)])


def frontier_greenhouse(rng, kind, base=False, length=W):
    """A glass stretch of a module's face: plating up to a steel sill, glass between steel ribs above, racks of greens
    under grow lights."""
    sill, depth, top = 5.2, 3.0, LEVEL-INNER
    module_face(length, [(0, length, sill, top)], foot=FOOT if base else 0.0)
    cuboid('glass sill', 0, length, -.3, 0, sill-.6, sill, STEEL, FRAME, omit='bk')
    add('greenhouse glass', DOME_GLASS, (.92, .97, .97), [(0, 0, sill), (length, 0, sill), (length, 0, top), (0, 0, top)], [(0, 1, 2, 3)])
    for x in (length/4, length*3/4):  # Ribs a module's length apart, wherever its stretches meet.
        cuboid('glass rib', x-.3, x+.3, -.3, 0, sill, top, STEEL, FRAME, omit='bkt')
    for shelf in (6.4, 10.6):
        cuboid('grow rack', .6, length-.6, 1.0, 2.9, shelf-.3, shelf, PAINT, DARK, omit='')
        c.extrude('greens', [(-1.2, shelf), (-2.8, shelf), (-2.7, shelf+.7), (-2.0, shelf+1.1), (-1.3, shelf+.7)], front, .8, length-.8, h.BUSH, GREENS)
        add('grow light', PAINT, (.90, .88, .80), [(.8, 2.2, shelf+3.6), (length-.8, 2.2, shelf+3.6), (length-.8, 2.6, shelf+3.6), (.8, 2.6, shelf+3.6)],
            [(3, 2, 1, 0)], light='night')
    back_wall(length, 0, LEVEL, depth, DARK)
    if kind == 'vent':
        cuboid('vent box', 9, 15, -1, 0, CHAMFER+.4, sill-.8, PAINT, (.36, .38, .40), omit='bk')
    if base:
        feet((length/2,))


def frontier_joint(rng, kind):
    """Where a module meets the next (BayKit joints), built for a wall's end and mirrored for its start: its vertical
    edge bevelled as its top and bottom are, the three bevels meeting in a point at each corner, so neighbouring modules
    part in a V groove; an amber marker by its top corner; on the ground, a skid under it."""
    H, C, m = LEVEL, CHAMFER, CHAMFER/2
    f = FOOT if kind == 'base' else 0.0
    bevel([(0, 0, H-C), (m, m, H-m), (0, C, H)], (0, -1, 1), lambda v: v[1])
    bevel([(0, C, f), (m, m, m+f), (0, 0, C+f)], (0, -1, -1), lambda v: v[1])
    bevel([(0, 0, C+f), (m, m, m+f), (C, C, C+f), (C, C, H-C), (m, m, H-m), (0, 0, H-C)], (1, -1, 0), lambda v: v[1])
    if f:
        add('foot recess', PAINT, DARK, [(0, C, 0), (C, C, 0), (C, C, f), (0, C, f)], [(0, 1, 2, 3)])
    marker(-.7, H-C-BAND/2, -BAND_OUT-.02)
    back_wall(C, 0, H, C, DARK)
    if kind == 'base':
        cuboid('skid foot', -2.8, C-.8, -.3, C+.6, 0, C*.8, PAINT, DARK, omit='b')
        marker(-1.2, C*.4, -.32)


def mirrored(builder, length):
    """builder's piece mirrored end for end: a wall's start piece from its end's."""
    def build(rng):
        builder(rng)
        for b in h.bins.values():
            b['v'] = [(length-x, y, z) for x, y, z in b['v']]
            b['f'] = [tuple(reversed(f)) for f in b['f']]
    return build


def frontier_corner(rng, kind, length=ROUND):
    """A module's corner where its outline turns: its vertical edge chamfered, a steel facet between its bevels, an
    amber marker high up; on the ground, a skid."""
    foot = FOOT if kind == 'base' else 0.0
    bevels(length, foot)
    low, high = face_span(foot)
    add('corner facet', MATTE, FRAME, [(0, 0, low), (length, 0, low), (length, 0, high), (0, 0, high)], [(0, 1, 2, 3)])
    if EDGES['top']:
        marker(length/2, LEVEL-CHAMFER-.8)
    back_wall(length, 0, LEVEL, colour=DARK)
    if kind == 'base':
        feet((length/2,))


def roof_border(length):
    """The steel border round a module's roof, inside its top bevel (the roof slab kept off the wall by the bevel)."""
    cuboid('roof border', 0, length, CHAMFER, CHAMFER+BORDER, 0, .55, MATTE, FRAME, omit='b')


def frontier_roof(rng, kind, length=W):
    """A module's roof along its wall: its border; a pipe run, a grille panel or a beacon on some."""
    roof_border(length)
    y = CHAMFER+BORDER
    if kind == 'pipe':
        pipe_run([(5, y+1.6, 0), (5, y+1.6, 1.2), (length-5, y+1.6, 1.2), (length-5, y+1.6, 0)])
    elif kind == 'grille':
        cuboid('roof grille kerb', 6, 18, y+1.4, y+5.8, 0, .6, PAINT, DARK, omit='b')
        deck('roof grille', 6.3, 17.7, y+1.7, y+5.5, .62, h.GRILLE, (.62, .64, .66))
    elif kind == 'light':
        cuboid('roof beacon post', 11.6, 12.4, y+.6, y+1.4, .5, 2.6, PAINT, DARK, omit='b')
        cuboid('roof beacon', 11.4, 12.6, y+.4, y+1.6, 2.6, 3.4, PAINT, (.50, .42, .26), omit='b', light=c.AMBER_LIGHT)


def frontier_seam(rng, length=W):
    """Where a module's roof meets its neighbour's (BayKit seams): its top edge bevelled down to the joint, the
    neighbour's bevel the groove's other side; its border inside, as along its walls."""
    bevel([(0, 0, -CHAMFER), (length, 0, -CHAMFER), (length, CHAMFER, 0), (0, CHAMFER, 0)], (0, -1, 1), lambda v: CHAMFER-v[1])
    # A dark wall on the joint line, facing this module: the groove's far side when the neighbour is as tall, and closed
    # when it stands taller (its cap starts above this roof, nothing under it on that side).
    wall = [(0, 0, -CHAMFER), (length, 0, -CHAMFER), (length, 0, 0), (0, 0, 0)]
    add('seam wall', PAINT, DARK, wall, [facing(wall, (0, 1, 0))])
    cuboid('roof border', 0, length, CHAMFER+ROOF_INSET, CHAMFER+ROOF_INSET+BORDER, 0, .55, MATTE, FRAME, omit='b')


# Frontier roof fittings: each stands on the roof about its origin.
def frontier_solar(rng):
    for y in (-3.4, 3.4):
        cuboid('solar stand', -7, 7, y-2.8, y+2.8, 0, .9, PAINT, DARK, omit='bt')
        # The stand's top rises with the panel: a wedge under it.
        v = [(-7, y-2.8, .9), (7, y-2.8, .9), (7, y+2.8, .9), (-7, y+2.8, .9), (7, y+2.8, 1.58), (-7, y+2.8, 1.58)]
        add('solar stand', PAINT, DARK, v, [(0, 1, 4, 5), (1, 2, 4), (3, 0, 5), (2, 3, 5, 4)])
        add('solar cells', SOLAR, (1, 1, 1), [(-6.6, y-2.4, .92), (6.6, y-2.4, .92), (6.6, y+2.4, 1.6), (-6.6, y+2.4, 1.6)], [(0, 1, 2, 3)])


def frontier_radome(rng):
    cuboid('mast foot', -1.4, 1.4, -1.4, 1.4, 0, .8, PAINT, DARK, omit='b')
    cuboid('mast', -.25, .25, -.25, .25, .8, 12, STEEL, FRAME, omit='b')
    for z in (8, 10.5):
        cuboid('mast antenna', -.12, .12, -1.6, 1.6, z, z+.2, STEEL, FRAME, detail=True)
    sides, r, base = 10, 2.2, 1.2
    rows = [(r*math.cos(t), base+r*math.sin(t)) for t in (0, .5, 1.0, 1.4)]
    v = [(3.6+rr*math.cos(a), rr*math.sin(a), z) for rr, z in rows for a in (math.tau*k/sides for k in range(sides))]
    f = [(i*sides+k, i*sides+(k+1) % sides, (i+1)*sides+(k+1) % sides, (i+1)*sides+k) for i in range(len(rows)-1) for k in range(sides)]
    f.append(tuple((len(rows)-1)*sides+k for k in range(sides)))
    add('radome', PAINT, (.88, .88, .86), v, f)
    round_prism('radome base', 3.6, 0, 0, base, r*1.05, PAINT, DARK, sides)


def frontier_hvac(rng):
    cuboid('hvac', -5, 5, -3.5, 3.5, 0, 4.2, PAINT, (.40, .42, .44), omit='b')
    deck('hvac grille', -4.4, 4.4, -2.9, 2.9, 4.22, h.GRILLE, (.62, .64, .66))
    add('hvac louvre', SLATS, LOUVRE, [(-4.4, -3.52, .6), (4.4, -3.52, .6), (4.4, -3.52, 3.6), (-4.4, -3.52, 3.6)], [(0, 1, 2, 3)])
    chevrons(2, 1, 1)


def frontier_hatch(rng):
    cuboid('hatch kerb', -3, 3, -3, 3, 0, 1.2, PAINT, DARK)
    deck('hatch grille', -2.6, 2.6, -2.6, 2.6, 1.22, h.GRILLE, (.62, .64, .66))


def frontier_beacon(rng):
    cuboid('beacon post', -.4, .4, -.4, .4, 0, 3, PAINT, DARK, omit='b')
    cuboid('beacon', -.7, .7, -.7, .7, 3, 4, PAINT, (.50, .42, .26), omit='b', light=c.AMBER_LIGHT)


# -- Kits ---------------------------------------------------------------------------------------------

def kinds(prefix, builder, names):
    """Pieces named prefix-<kind>, each built by builder(rng, kind)."""
    return {f'{prefix}-{kind}': (lambda rng, kind=kind: builder(rng, kind)) for kind in names}


CIVIC_PIECES = {
    **kinds('shop', civic_shop, ('narrow', 'wide', 'closed', 'door')),
    **kinds('plinth', civic_plinth, ('slots', 'louvre', 'door', 'billboard')),
    **kinds('gallery', civic_gallery, 'abcd'),
    **kinds('ribbon', civic_ribbon, ('plain', 'lit', 'panel', 'balcony')),
    **kinds('fins', civic_fins, ('glass', 'louvre', 'blank', 'shade')),
    **kinds('parapet', civic_parapet, ('plain', 'rail', 'tall')),
    'fan-unit': civic_fan_unit, 'louvre-cage': civic_louvre_cage, 'plant-room': civic_plant_room, 'vent-stack': civic_vent_stack,
    'water-tank': civic_water_tank, 'hatch': civic_hatch,
}

UTOPIA_PIECES = {
    **kinds('arcade', utopia_arcade, ('arch', 'planted', 'door')),
    'arcade-round': lambda rng: utopia_arcade(rng, 'planted', ROUND),
    **kinds('terrace', utopia_terrace, ('dense', 'sparse', 'rail', 'pier', 'oval')),
    'terrace-round': lambda rng: utopia_terrace(rng, 'dense', ROUND),
    **kinds('band', utopia_band, ('fins', 'glass', 'slats')),
    'band-round': lambda rng: utopia_band(rng, 'glass', ROUND),
    **kinds('rim', utopia_rim, ('garden', 'rail')),
    'rim-round': lambda rng: utopia_rim(rng, 'garden', ROUND),
    'skylight': utopia_skylight, 'tree': utopia_tree, 'pergola': utopia_pergola, 'solar': utopia_solar, 'bed': utopia_bed,
    'pavilion': utopia_pavilion,
}

FRONTIER_BAYS = ('pair', 'single', 'wide', 'four', 'vent', 'med-pair', 'med-triple', 'med-single', 'louvre', 'pipes', 'boxes', 'slit')
FRONTIER_PIECES = {
    **{kind: (lambda rng, kind=kind: frontier_bay(rng, kind)) for kind in FRONTIER_BAYS},
    **{'base-'+kind: (lambda rng, kind=kind: frontier_bay(rng, kind, base=True)) for kind in FRONTIER_BAYS},
    **{name: (lambda rng, kind=kind, base=base: frontier_greenhouse(rng, kind, base))
       for name, kind, base in (('glass', 'plain', False), ('glass-vent', 'vent', False), ('base-glass', 'plain', True),
                                ('base-glass-vent', 'vent', True))},
    'airlock': lambda rng: airlock(rng, 'plain'), 'airlock-med': lambda rng: airlock(rng, 'med'), 'rollup': lambda rng: airlock(rng, 'rollup'),
    'corner-base': lambda rng: frontier_corner(rng, 'base'), 'corner': lambda rng: frontier_corner(rng, 'plain'),
    'joint-end': lambda rng: frontier_joint(rng, 'plain'), 'joint-start': mirrored(lambda rng: frontier_joint(rng, 'plain'), CHAMFER),
    'base-joint-end': lambda rng: frontier_joint(rng, 'base'), 'base-joint-start': mirrored(lambda rng: frontier_joint(rng, 'base'), CHAMFER),
    **kinds('roof', frontier_roof, ('plain', 'pipe', 'grille', 'light')),
    'roof-corner': lambda rng: roof_border(ROUND), 'roof-seam': frontier_seam,
    'solar': frontier_solar, 'radome': frontier_radome, 'hvac': frontier_hvac, 'hatch': frontier_hatch, 'beacon': frontier_beacon,
}

# Board materials textured along the wall's line, so their panels run on from bay to bay.
CIVIC_PLANAR = {PANELS: 18.0, CAST: 12.0}
UTOPIA_PLANAR = {WHITE_STONE: float(STONE_REPEAT)}
FRONTIER_PLANAR = {PLATING: 18.0}


def run(bays, planar, door=None, round_piece=None, joints=None, seam=None):
    result = {'bays': bays, 'bay': W, 'planar': planar}
    if door:
        result['door'] = door
    if round_piece:
        result['round'] = {'piece': round_piece, 'length': ROUND}
    if joints:
        result['joints'] = {'start': joints+'-start', 'end': joints+'-end', 'length': CHAMFER}
    if seam:
        result['seam'] = {'piece': seam, 'length': W}
    return [result]


def fittings(hatch, vent, groups):
    """The same layouts for both footprints: each a dict of piece name -> [x, y, turn]."""
    layouts = [{'hatches': [], 'vents': [], 'pieces': group} for group in groups]
    return {footprint: {'hatch': hatch, 'vent': vent, 'layouts': layouts} for footprint in ('square', 'angled')}


CIVIC_FITTINGS = fittings('hatch', 'vent-stack', [
    {'fan-unit': [[0, 0, 0]]},
    {'plant-room': [[-6, 4, 0]], 'vent-stack': [[11, -9, 0]]},
    {'louvre-cage': [[5, -4, 30]], 'hatch': [[-10, 9, 0]]},
    {'water-tank': [[-8, -5, 0]], 'fan-unit': [[9, 8, 90]]},
    {'hatch': [[4, 6, 0]]},
    {'vent-stack': [[0, 10, 90]], 'hatch': [[-7, -9, 0], [9, -8, 0]]},
])
UTOPIA_FITTINGS = fittings('bed', 'skylight', [
    {'skylight': [[0, 0, 0]]},
    {'tree': [[-7, 4, 0]], 'bed': [[8, -7, 30]]},
    {'pergola': [[0, 0, 30]]},
    {'solar': [[5, -4, 0]], 'tree': [[-9, 9, 0]]},
    {'bed': [[0, 0, 90]], 'skylight': [[-2, 11, 60]]},
    {'pavilion': [[-3, 2, 0]]},
])
FRONTIER_FITTINGS = fittings('hatch', 'hvac', [
    {'solar': [[-5, 5, 0]], 'radome': [[8, -9, 0]]},
    {'hvac': [[0, 0, 0]]},
    {'solar': [[0, -6.5, 0], [0, 8, 0]]},
    {'radome': [[-9, 7, 0]], 'hatch': [[8, -6, 0]]},
    {'hatch': [[0, 2, 0]], 'beacon': [[10, -9, 0]]},
    {'hvac': [[-6, -5, 90]], 'solar': [[7, 8, 0]]},
])
GREENHOUSE_FITTINGS = fittings('hatch', 'hvac', [
    {'hvac': [[0, 0, 0]]},
    {'hatch': [[-6, 4, 0], [8, -6, 0]]},
    {},
    {'hvac': [[-7, 6, 90]]},
    {'beacon': [[0, 10, 0]]},
    {'hatch': [[0, 0, 0]]},
])
LONE = [[-20.78125, -34.25], [20.78125, -34.25], [20.78125, 34.25], [-20.78125, 34.25]]  # As the light building's.


def civic_variant(name, floors):
    p = CIVIC_PLANAR
    return {
        'name': name, 'style': 'bays', 'pieces': 'civic-pieces.glb', 'lone': LONE, 'bandEnd': 1.75,
        'roof': {'material': CAST, 'repeat': 12.0, 'inset': 0.0, 'heights': [0.3]},
        'floors': {'material': CAST, 'repeat': 12.0, 'inset': 3.0, 'heights': [0.05]},
        'sidewalk': {'material': CAST, 'repeat': 12.0, 'width': 5.0, 'kerb': 0.4},
        'modules': {
            'base0': run(['shop-narrow', 'shop-wide', 'shop-closed', 'plinth-louvre', 'shop-narrow'], p, door='shop-door'),
            'base1': run(['plinth-slots', 'shop-wide', 'plinth-billboard', 'plinth-louvre', 'shop-closed'], p, door='plinth-door'),
            'floor0': run(floors[0], p),
            'floor1': run(floors[1], p),
            'roof0': run(['parapet-plain', 'parapet-rail', 'parapet-plain', 'parapet-tall'], p),
        },
        'fittings': CIVIC_FITTINGS,
    }


def utopia_variant(name, floors, round_piece):
    p = UTOPIA_PLANAR
    return {
        'name': name, 'style': 'bays', 'pieces': 'utopia-pieces.glb', 'lone': LONE, 'bandEnd': 1.75,
        'cornerRadius': 10.0, 'cornerSegments': 3,
        'roof': {'material': LAWN, 'repeat': float(LAWN_REPEAT), 'inset': 0.0, 'heights': [0.3]},
        'floors': {'material': WHITE_STONE, 'repeat': 12.0, 'inset': 3.0, 'heights': [0.05]},
        'sidewalk': {'material': WHITE_STONE, 'repeat': 12.0, 'width': 5.0, 'kerb': 0.3},
        'modules': {
            'base0': run(['arcade-arch', 'arcade-planted', 'arcade-arch', 'arcade-arch'], p, 'arcade-door', 'arcade-round'),
            'base1': run(['arcade-planted', 'arcade-arch', 'arcade-planted'], p, 'arcade-door', 'arcade-round'),
            'floor0': run(floors[0], p, round_piece=round_piece),
            'floor1': run(floors[1], p, round_piece=round_piece),
            'roof0': run(['rim-garden', 'rim-rail', 'rim-garden'], p, round_piece='rim-round'),
        },
        'fittings': UTOPIA_FITTINGS,
    }


def frontier_variant(name, bases, floors, door, roof=PLATING, layouts=FRONTIER_FITTINGS):
    p = FRONTIER_PLANAR
    return {
        'name': name, 'style': 'bays', 'pieces': 'frontier-pieces.glb', 'lone': LONE, 'bandEnd': 1.75,
        'cornerRadius': 5.0, 'cornerSegments': 1,
        'roof': {'material': roof, 'repeat': 30.0, 'inset': CHAMFER, 'heights': [0.3], 'underlay': roof == DOME_GLASS},
        'floors': {'material': DECK, 'repeat': 12.0, 'inset': 3.0, 'heights': [0.05]},
        'modules': {
            'base0': run(['base-'+bay for bay in bases[0]], p, door, 'corner-base', 'base-joint'),
            'base1': run(['base-'+bay for bay in bases[1]], p, door, 'corner-base', 'base-joint'),
            'floor0': run(floors[0], p, round_piece='corner', joints='joint'),
            'floor1': run(floors[1], p, round_piece='corner', joints='joint'),
            'roof0': run(['roof-plain', 'roof-pipe', 'roof-plain', 'roof-grille'], p, round_piece='roof-corner', seam='roof-seam'),
            'roof1': run(['roof-pipe', 'roof-light', 'roof-plain'], p, round_piece='roof-corner', seam='roof-seam'),
        },
        'fittings': layouts,
    }


KITS = {
    'civic': (CIVIC_PIECES, [
        civic_variant('galleries', (['gallery-a', 'gallery-b', 'gallery-c', 'gallery-d'], ['gallery-b', 'gallery-d', 'gallery-a', 'gallery-c'])),
        civic_variant('ribbons', (['ribbon-plain', 'ribbon-lit', 'ribbon-balcony', 'ribbon-plain', 'ribbon-panel'],
                                  ['ribbon-lit', 'ribbon-panel', 'ribbon-plain', 'ribbon-balcony'])),
        civic_variant('offices', (['fins-glass', 'fins-louvre', 'fins-glass', 'fins-blank'], ['fins-shade', 'fins-glass', 'fins-shade', 'fins-blank'])),
    ]),
    'frontier': (FRONTIER_PIECES, [
        frontier_variant('habitat', (['pair', 'single', 'four', 'pair', 'vent'], ['wide', 'pair', 'single', 'four']),
                         (['pair', 'four', 'single', 'pair', 'vent'], ['wide', 'pair', 'four', 'single', 'vent']), 'airlock'),
        frontier_variant('medical', (['med-pair', 'med-triple', 'med-single'], ['med-triple', 'med-pair', 'med-single']),
                         (['med-triple', 'med-pair', 'med-single', 'med-triple'], ['med-pair', 'med-triple', 'med-pair', 'med-single']),
                         'airlock-med'),
        frontier_variant('industrial', (['louvre', 'pipes', 'boxes'], ['boxes', 'louvre', 'slit']),
                         (['slit', 'louvre', 'pipes', 'slit'], ['louvre', 'slit', 'boxes', 'vent']), 'rollup'),
        frontier_variant('greenhouse', (['glass', 'glass-vent', 'glass'], ['glass-vent', 'glass', 'glass']),
                         (['glass', 'glass-vent', 'glass'], ['glass', 'glass', 'glass-vent']), 'airlock', DOME_GLASS, GREENHOUSE_FITTINGS),
    ]),
    'utopia': (UTOPIA_PIECES, [
        utopia_variant('terraces', (['terrace-dense', 'terrace-sparse', 'terrace-pier', 'terrace-dense', 'terrace-oval'],
                                    ['terrace-sparse', 'terrace-rail', 'terrace-dense', 'terrace-oval', 'terrace-pier']), 'terrace-round'),
        utopia_variant('bands', (['band-fins', 'band-glass', 'band-fins', 'band-slats'], ['band-glass', 'band-fins', 'band-slats', 'band-glass']), 'band-round'),
    ]),
}


# -- Export -------------------------------------------------------------------------------------------

def build(kit):
    pieces, variants = KITS[kit]
    shared.fresh(kit+'-pieces')
    levels = {level: {'meshes': [], 'nodes': [], 'materials': []} for level in (0, 1, 2)}
    counts = {}
    for name, builder in pieces.items():
        h.bins.clear()
        h.fixtures.clear()
        u.LOD, before = 0, len(shared.objects)
        u.near_plants.clear()
        builder(random.Random(sum(map(ord, name))))
        # Utopia's plants and trees come first, as utopia_buildings makes them: its near level's, then its far level's. A
        # kit's level follows each hex's size on screen, a building's the whole building's: the plants a hex shows from
        # its second switch on are the ones a building shows at about the same size from its first.
        u.flush_cards()
        for obj in shared.objects[before:]:
            if obj.name.split('.')[0] in ('planting', 'planting mass', 'tree trunk'):
                obj['near'] = True
        if u.near_plants:
            grown, u.LOD = len(shared.objects), 1
            u.flush_cards()
            u.LOD = 0
            for obj in shared.objects[grown:]:
                obj['far'] = True
        h.flush()
        made = shared.objects[before:]
        for obj in made:
            if obj['board_material'] == LAWN:  # The authored roofs' lawn scale (utopia_buildings), seen from above.
                layer = obj.data.uv_layers.new(name='UVMap')
                for loop in obj.data.loops:
                    co = obj.data.vertices[loop.vertex_index].co
                    layer.data[loop.index].uv = co.x/LAWN_REPEAT, co.y/LAWN_REPEAT
        for obj in made:
            obj['module'] = name
            if kit == 'utopia' and obj.get('building_night_emission'):
                shared.emissive(obj, NIGHT, night=True)  # Utopia's warm rooms, as its buildings light them.
        bpy.context.view_layer.update()
        for level, merged in levels.items():
            shown = [obj for obj in made if (level < 2 or not obj.get('near')) and (level == 2 or not obj.get('far'))]
            model = shared.export_model(shown, f'{kit}-pieces-lod{level}', level=level, exact=True)
            assert len(model['nodes']) == 1, (name, level)
            node, mesh = model['nodes'][0], model['meshes'][0]
            node['id'] = f'{name}-lod{level}'
            merged['meshes'].append(mesh)
            merged['nodes'].append(node)
            known = {mat['id'] for mat in merged['materials']}
            merged['materials'] += [mat for mat in model['materials'] if mat['id'] not in known]
            counts[name, level] = sum(len(part['indices'])//3 for part in mesh['parts'])
    if not any(obj.get('far') for obj in shared.objects):
        del levels[2]  # Without plants the second switch changes nothing: a level the GLB lacks repeats the one before.
    folder = DATA/'models/buildings'/kit
    folder.mkdir(parents=True, exist_ok=True)
    write_glb(folder/f'{kit}-pieces.glb', levels=levels)
    (folder/f'{kit}.json').write_text(json.dumps(variants, indent=2)+'\n', encoding='utf-8')
    for name in pieces:
        print(f'PIECE {kit} {name:16s}', *(f'lod{level} {counts[name, level]:5d}' for level in levels))
    print('RESULT', kit, len(pieces), 'pieces')


if __name__ == '__main__' and '--' in sys.argv:
    for kit in sys.argv[sys.argv.index('--')+1:]:
        build(kit)
