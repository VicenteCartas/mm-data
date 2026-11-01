"""The light building as connected kits (models/buildings/README.md), laid out from its hand-made art.

    python tools/buildings/building_light.py

Reads art/building_light_00.glb, the artist's free-standing block (module variants base0, base1, floor0, floor1,
roof0), and writes both footprints (kit_geometry.footprint) to data/models/buildings/building_light/:
building_light.glb (Angled) and building_light-square.glb (Square). Every wall is laid from the art's window bays,
pier centre to pier centre (24, the Angled walls' length), whole bays fitted to each wall so that no window is cut; a
sidewalk runs along the ground storey, the art's cornice along the roof. Roofs, floors and sidewalks are the board's
tileable materials on the board's axes, so they run on across corner pieces and hexes.
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kit_geometry import (A, ROOF_INSET, Geometry, clipped, facade, flat, inset, inside_hex, normal, sector,  # noqa: E402
                          slab_height, to_facade, without_flats, write_kits)

SOURCE = HERE / 'art/building_light_00.glb'
FOLDER = HERE.parents[1] / 'data/models/buildings/building_light'
# The art's bays, pier centre to pier centre: (origin, along, out) on its east, west, north and south facades.
BAY = 24.0
BAYS = [((14, -24), (0, 1), (1, 0)), ((14, 0), (0, 1), (1, 0)), ((-14, 24), (0, -1), (-1, 0)),
        ((-14, 0), (0, -1), (-1, 0)), ((12, 26), (-1, 0), (0, 1)), ((-12, -26), (1, 0), (0, -1))]
# How far into the wall and out of it a bay reaches (its awnings and cornices).
INSIDE, OUTSIDE = 5.0, 8.0
# The ground storey's sidewalk out from the walls and its kerb height; the board textures' repeat.
SIDEWALK, KERB = 4.0, .3
REPEAT = 12.0
# The lone hex, from its front (a block a hexside wide, short of its north and south hexsides), and a single link's
# band end.
LONE = [(-A, -34.25), (A, -34.25), (A, 34.25), (-A, 34.25)]
END = 1.75
# Every material is the board's (tools/materials/structures/buildings): the art's atlases on their own UVs, the roof
# and sidewalk on the board's axes.
BOARD = {'building_light_00_cornices': ('structures/buildings/light-cornices', None),
         'building_light_00_walls': ('structures/buildings/light-walls', None),
         'building_light_00_frameswindows': ('structures/buildings/light-frames', None),
         'lod1': ('structures/buildings/light-far', None),
         'roof': ('structures/buildings/light-roof', REPEAT), 'sidewalk': ('structures/buildings/light-sidewalk', REPEAT)}


def bays(geometry):
    """The module's bays in the facade frame, without the art's flat roof slab and sidewalk (laid over the footprint)."""
    return [without_flats(clipped(to_facade(geometry, origin, along, out),
                                  [lambda d, t: d + INSIDE, lambda d, t: OUTSIDE - d, lambda d, t: t,
                                   lambda d, t: BAY - t]))
            for origin, along, out in BAYS]


def run(variants, pick):
    """Lays a wall: whole bays fitted to its length, one more past each end that goes on (trimmed by its mitre)."""
    def lay(length, before, after):
        count = max(1, round(length / BAY))
        scale = length / (count * BAY)
        placed = [(index * BAY * scale, variants[pick(index)], scale) for index in range(count)]
        if before:
            placed.append((-BAY * scale, variants[pick(-1)], scale))
        if after:
            placed.append((length, variants[pick(count)], scale))
        return placed
    return lay


def sidewalk(wall, before, after):
    """The sidewalk strip out from a ground storey's wall, at kerb height (east and west facing a hair higher so two
    never meet in one plane)."""
    n = normal(wall.p, wall.q)
    length = math.dist(wall.p, wall.q)
    u = ((wall.q[0] - wall.p[0]) / length, (wall.q[1] - wall.p[1]) / length)
    a = (wall.p[0] - u[0] * before, wall.p[1] - u[1] * before)
    b = (wall.q[0] + u[0] * after, wall.q[1] + u[1] * after)
    strip = [a, b, (b[0] + n[0] * SIDEWALK, b[1] + n[1] * SIDEWALK), (a[0] + n[0] * SIDEWALK, a[1] + n[1] * SIDEWALK)]
    result = Geometry()
    flat(result, 'sidewalk', strip, KERB + (.02 if abs(n[0]) > .5 else 0), REPEAT)
    return result


def module(role, geometry, polygons, walls, direction, level):
    """One piece of a module: its walls' bays (and sidewalk), its floor or roof slab, cut to its corner."""
    ground, top = role.startswith('base'), role.startswith('roof')
    variants = bays(geometry)
    result = Geometry()
    for wall in walls:
        # A wall's bays are chosen by where it stands, the same in every piece that holds it.
        mid = ((wall.p[0] + wall.q[0]) / 2, (wall.p[1] + wall.q[1]) / 2)
        seed = int(round(mid[0] * 7 + mid[1] * 13)) % 997
        laid, before, after = facade(wall, run(variants, lambda index, seed=seed: (seed + index * 5) % len(variants)),
                                     inset=ROOF_INSET if top else 0.0)
        result.add(laid)
        if ground:
            result.add(clipped(sidewalk(wall, before, after), [inside_hex, *wall.keeps]))
    # The roof's slab where the art has it; a storey's floor (all a piece open on both sides holds), kept off its walls
    # so that it never shows in a recess of the facade.
    height = slab_height(geometry) if top else min(v[2] for t in geometry.parts.values() for f in t for v in f) + .05
    for polygon in polygons:
        flat(result, 'roof' if top else 'sidewalk', polygon if top else inset(polygon, walls, 2.0), height, REPEAT)
    return clipped(result, sector(direction)) if direction is not None else result


if __name__ == '__main__':
    write_kits(SOURCE, FOLDER, 'building_light', module, LONE, END, BOARD)
