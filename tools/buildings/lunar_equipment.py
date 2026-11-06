"""Lunar base support pieces for the multi-hex buildings (BoardMultiHexBuilding) and lunar props, modelled in Blender.

    blender -b --factory-startup --python tools/buildings/lunar_equipment.py

Writes data/models/buildings/multihex/lunar-equipment.glb: one node per piece and level of detail (`<piece>-lod0`,
`<piece>-lod1`), each standing on its origin with its front towards +Y (north), in board units. Pieces: `tanks`
(three pressure tanks on saddles with their manifold), `plant` (a life support unit with two fans), `airlock` (a
pressure door module that stands against a facade, its back on y = 0) and `pylon` (a dome podium's corner block).
Painted parts take the domes' white `dome-frame`, metal `steel`, fan guards `grille`, door frames `hazard-stripes`;
vertex colours carry contact shading and settled regolith dust.

Also writes the lunar props as board objects: roof props (ROOF_PROPS) in data/models/board/scenery/roofs/<name>.glb
and colony detail props (COLONY_PROPS) in data/models/board/scenery/colony/<name>.glb.
"""
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import write_glb  # noqa: E402

MODELS = TOOLS.parent / 'data/models'
OUT = MODELS / 'buildings/multihex'
ROOFS = MODELS / 'board/scenery/roofs'
COLONY = MODELS / 'board/scenery/colony'
BOARD = {'paint': 'structures/lunar/dome-frame', 'steel': 'structures/common/steel',
         'shell': 'structures/common/matte-steel', 'plate': 'structures/common/matte-steel',
         'grille': 'structures/common/grille', 'hazard': 'structures/common/hazard-stripes',
         'cells': 'structures/lunar/solar-cells', 'glass': 'structures/lunar/skylight-glass',
         'dark': 'structures/lunar/habitat-pier', 'beacon': 'structures/lunar/skylight-glass'}
# Board units one texture repeat covers.
REPEAT = {'paint': 12.0, 'steel': 8.0, 'grille': 5.2, 'hazard': 6.0, 'cells': 6.5, 'glass': 10.0, 'dark': 12.0,
          'beacon': 10.0, 'shell': 8.0, 'core': 10.0, 'plate': 12.0}
TINT = {'paint': (1, 1, 1), 'steel': (.82, .82, .84), 'grille': (.75, .75, .76), 'hazard': (1, 1, 1),
        'cells': (1, 1, 1), 'glass': (1, 1, 1), 'dark': (1, 1, 1), 'beacon': (1, .25, .2), 'plate': (.92, .92, .89)}
DUST = (.62, .58, .53)
# The kinds a placement can recolour, in slot order. A slot's default colour is its kind's tint.
COLOUR_SLOTS = {'shell': {'name': 'Shell', 'colour': '#3c3f44', 'presets': [['Charcoal', '#3c3f44'], ['Steel', '#c4c8cc'], ['Roof', '#b0a997']]},
                'core': {'name': 'Glow', 'colour': '#366383',
                         'presets': [['Blue', '#366383'], ['Cyan', '#478a98'], ['Amber', '#8a5a18'], ['Red', '#8a241c'], ['Green', '#2c7a44']]}}
TINT.update({kind: tuple(int(slot['colour'][i:i + 2], 16) / 255 for i in (1, 3, 5)) for kind, slot in COLOUR_SLOTS.items()})


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def solid(obj, kind, bevel=0.0, segments=2, smooth=0.0):
    """Tag `obj` with its material kind; bevel its edges and smooth its normals below `smooth` radians."""
    obj['kind'] = kind
    if bevel > 0:
        modifier = obj.modifiers.new('Bevel', 'BEVEL')
        modifier.width = bevel
        modifier.segments = segments
        modifier.limit_method = 'ANGLE'
        modifier.angle_limit = math.radians(40)
        modifier.harden_normals = True
    if smooth > 0:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=smooth)
        obj.select_set(False)
    return obj


def box(kind, centre, size, bevel=0.0, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre, rotation=rotation)
    obj = bpy.context.active_object
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return solid(obj, kind, bevel)


def cylinder(kind, start, end, radius, sides, bevel=0.0, cap=True):
    start, end = Vector(start), Vector(end)
    axis = end - start
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=radius, depth=axis.length, location=(start + end) / 2,
                                        end_fill_type='NGON' if cap else 'NOTHING')
    obj = bpy.context.active_object
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis.normalized())
    return solid(obj, kind, bevel, segments=3, smooth=math.radians(50))


def cone(kind, start, end, radius, sides):
    start, end = Vector(start), Vector(end)
    axis = end - start
    bpy.ops.mesh.primitive_cone_add(vertices=sides, radius1=radius, radius2=0, depth=axis.length, location=(start + end) / 2,
                                    end_fill_type='NGON')
    obj = bpy.context.active_object
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis.normalized())
    return solid(obj, kind, smooth=math.radians(50))


def cap(kind, centre, radius, depth, sides, rings, rotation=(0, 0, 0)):
    """A shallow spherical cap (a dish), concave towards its local +Z."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=sides, ring_count=rings, radius=radius, location=(0, 0, 0))
    obj = bpy.context.active_object
    keep = radius - depth
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for vertex in obj.data.vertices:
        vertex.select = vertex.co.z > -keep
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='VERT')
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.location = Vector(centre) + Vector((0, 0, keep))
    obj.rotation_euler = rotation
    modifier = obj.modifiers.new('Shell', 'SOLIDIFY')
    modifier.thickness = .25
    return solid(obj, kind, smooth=math.radians(60))


def tanks(lod):
    sides = 24 if lod == 0 else 10
    for y in (-7.0, 0.0, 7.0):
        z = 4.2
        cylinder('paint', (-10, y, z), (10, y, z), 3.0, sides, bevel=1.4 if lod == 0 else 0)
        for x in (-6.0, 6.0):
            box('steel', (x, y, 1.4), (1.2, 5.6, 2.8), bevel=.15 if lod == 0 else 0)
        if lod == 0:
            for x in (-10.4, 10.4):
                cylinder('steel', (x, y, z), (x + math.copysign(.8, x), y, z), .7, 10)
            cylinder('steel', (11.2, y, z), (11.2, y, 1.0), .45, 8)
    cylinder('steel', (11.2, -7.6, 1.0), (11.2, 7.6, 1.0), .5, 10 if lod == 0 else 6)
    if lod == 0:
        for y in (-7.0, 0.0, 7.0):
            cylinder('steel', (0, y, 7.1), (0, y, 7.9), .5, 10)
    return Vector((24, 22))


def radiator(lod):
    # Three panels edge-on to the sky, in a frame of steel beams, fed by the header pipes along their feet and tops.
    for x in (-8.0, 0.0, 8.0):
        box('paint', (x, 0, 6.0), (7.0, .45, 9.0), bevel=.12 if lod == 0 else 0)
        if lod == 0:
            for rib in range(-3, 4):
                box('paint', (x + rib * .9, 0, 6.0), (.14, .75, 8.6))
    for x in (-12.4, 12.4):
        for y in (-2.0, 2.0):
            box('steel', (x, y, 5.4), (.8, .8, 10.8))
        box('steel', (x, 0, 10.6), (.8, 4.8, .8))
    for z in (1.2, 10.8):
        cylinder('steel', (-12.0, 0, z), (12.0, 0, z), .55, 10 if lod == 0 else 6)
    box('steel', (0, 0, .25), (26, 5.6, .5))
    return Vector((26, 6))


def plant(lod):
    box('paint', (0, 0, 2.6), (13.0, 9.0, 5.2), bevel=.5 if lod == 0 else 0)
    for x in (-3.2, 3.2):
        cylinder('steel', (x, 0, 5.1), (x, 0, 6.1), 2.5, 24 if lod == 0 else 10)
        box('grille', (x, 0, 6.12), (4.2, 4.2, .02))
    box('steel', (0, -4.9, 1.6), (9.0, .8, 2.6), bevel=.1 if lod == 0 else 0)
    if lod == 0:
        for x in (-5.0, 5.0):
            cylinder('steel', (x, 4.4, 1.0), (x, 6.2, 1.0), .5, 8)
            cylinder('steel', (x, 6.2, 1.0), (x, 6.2, .0), .5, 8)
    return Vector((14, 12))


def solar(lod):
    for x in (-7.2, 7.2):
        tilt = math.radians(28)
        box('cells', (x, 0, 4.0), (13.0, 7.0, .25), rotation=(tilt, 0, 0))
        box('steel', (x, 0, 3.86), (13.4, 7.4, .2), rotation=(tilt, 0, 0))
        for px in (x - 5.0, x + 5.0):
            # Tilted up towards +Y: the panel's underside is low at its south edge, high at its north.
            for py, top in ((-2.6, 2.65), (2.6, 5.1)):
                cylinder('steel', (px, py, 0), (px, py, top), .25, 8 if lod == 0 else 4)
    return Vector((28, 8))


def radar_dish(lod):
    # A tracking dish on a drum: its yoke turns on the drum, the dish tilted up towards +Y.
    sides = 32 if lod == 0 else 14
    cylinder('paint', (0, 0, 0), (0, 0, 5.0), 7.0, sides, bevel=.4 if lod == 0 else 0)
    cylinder('steel', (0, 0, 5.0), (0, 0, 6.2), 5.6, sides)
    box('paint', (0, 0, 8.4), (5.0, 6.0, 4.4), bevel=.3 if lod == 0 else 0)
    for x in (-3.0, 3.0):
        box('steel', (x, .4, 11.8), (1.0, 2.6, 5.8))
    tilt = (math.radians(-50), 0, 0)
    cap('paint', (0, 1.6, 13.4), 15.0, 3.6, 48 if lod == 0 else 18, 28 if lod == 0 else 10, rotation=tilt)
    # The feed on three struts from the rim, the counterweight behind.
    feed = Vector((0, 10.6, 22.0))
    for angle in (90.0, 210.0, 330.0):
        a = math.radians(angle)
        rim = Vector((10.5 * math.cos(a), 1.6 + 6.8 * math.sin(a) * .64, 13.4 + 10.5 * math.sin(a) * .77))
        cylinder('steel', rim, feed, .3 if lod == 0 else .45, 6 if lod == 0 else 4)
    cylinder('steel', feed, feed + Vector((0, -1.2, -1.0)), .9, 10 if lod == 0 else 6)
    box('steel', (0, -4.0, 9.0), (3.6, 2.4, 3.0))
    if lod == 0:
        cylinder('steel', (2.6, -2.0, 6.2), (2.6, -2.0, 9.8), .25, 6)
    return Vector((30, 30))


def capsule_tanks(lod):
    # Three horizontal capsules on saddles in a steel frame, each banded twice in lit cyan glass, a manifold along x.
    sides = 24 if lod == 0 else 10
    for y in (-7.4, 0.0, 7.4):
        z = 4.6
        cylinder('paint', (-11, y, z), (11, y, z), 3.4, sides, bevel=1.6 if lod == 0 else 0)
        for x in (-5.0, 5.0):
            cylinder('glass', (x - .6, y, z), (x + .6, y, z), 3.55, sides, cap=False)
            box('steel', (x * 1.45, y, 1.5), (1.2, 6.0, 3.0), bevel=.15 if lod == 0 else 0)
    for x in (-12.6, 12.6):
        box('steel', (x, 0, 3.6), (.8, 20.0, .8))
        for y in (-9.6, 9.6):
            box('steel', (x, y, 1.8), (.8, .8, 3.6))
    cylinder('steel', (12.0, -8.4, 1.2), (12.0, 8.4, 1.2), .55, 10 if lod == 0 else 6)
    return Vector((26, 22))


def airlock(lod):
    # A pressure door module against a facade: its back on y = 0, its door facing +Y.
    box('paint', (0, 4.5, 5.4), (11.0, 9.0, 10.8), bevel=.8 if lod == 0 else 0)
    box('hazard', (0, 9.02, 4.3), (6.4, .1, 8.4))
    box('steel', (0, 9.1, 4.0), (5.0, .3, 7.4), bevel=.1 if lod == 0 else 0)
    box('steel', (0, 9.3, 4.6), (1.4, .1, .9))
    box('paint', (0, 4.5, 11.0), (8.0, 6.0, .5), bevel=.1 if lod == 0 else 0)
    if lod == 0:
        for x in (-4.6, 4.6):
            box('paint', (x, 9.2, .5), (1.6, .8, 1.0))
        cylinder('steel', (3.6, 9.1, 9.0), (3.6, 9.9, 9.0), .45, 10)
    return Vector((11, 9))


def pylon(lod):
    # A podium's corner block, a buttress without a door (only airlocks are gates): stands on the dome's foot, half
    # inside the ring building, its front (+Y) outward.
    box('paint', (0, 0, 8.5), (15.0, 18.0, 17.0), bevel=1.0 if lod == 0 else 0)
    box('paint', (0, 0, 17.3), (11.0, 13.0, .6), bevel=.15 if lod == 0 else 0)
    box('grille', (0, 9.02, 12.5), (11.0, .1, 2.4))
    for x in (-7.52, 7.52):
        box('grille', (x, 2.0, 12.5), (.1, 9.0, 2.4))
    box('steel', (0, 9.1, 1.2), (13.0, .3, 2.4), bevel=.1 if lod == 0 else 0)
    if lod == 0:
        box('paint', (3.5, -2.0, 18.4), (3.0, 3.0, 1.6), bevel=.2)
        cylinder('steel', (-4.0, 3.0, 17.6), (-4.0, 3.0, 23.0), .3, 8)
        for x in (-6.8, 6.8):
            box('steel', (x, 9.2, 8.5), (.8, .4, 17.0))
    return Vector((15, 18))


PIECES = {'tanks': tanks, 'plant': plant, 'airlock': airlock, 'pylon': pylon}
def pipe_run(lod):
    # Three pipes in a bundle along a facade (its back on y = 0), on brackets every six units, 24 long.
    sides = 12 if lod == 0 else 6
    for z, radius in ((6.0, .7), (7.8, .55), (9.4, .45)):
        cylinder('steel', (-12, 1.4, z), (12, 1.4, z), radius, sides)
    for x in (-9.0, -3.0, 3.0, 9.0):
        box('dark', (x, .7, 7.6), (.5, 1.4, 4.6))
        if lod == 0:
            box('dark', (x, 1.4, 7.6), (.7, 1.9, .3))
    return Vector((24, 3))


def vent_unit(lod):
    # A ground-level air handler against a facade: a ribbed box, a fan behind a grille, its duct up the wall.
    box('dark', (0, 2.8, 3.0), (8.0, 5.6, 6.0), bevel=.3 if lod == 0 else 0)
    cylinder('steel', (1.6, 5.6, 3.2), (1.6, 5.75, 3.2), 2.0, 24 if lod == 0 else 10)
    box('grille', (1.6, 5.76, 3.2), (3.6, .02, 3.6))
    box('hazard', (-2.6, 5.62, 1.0), (2.2, .04, 1.2))
    box('steel', (-2.4, 1.0, 9.0), (2.0, 2.0, 6.0), bevel=.15 if lod == 0 else 0)
    return Vector((8, 6))


def wall_tanks(lod):
    # Two upright pressure bottles strapped to a facade, a manifold between them.
    sides = 20 if lod == 0 else 8
    for x in (-3.0, 3.0):
        cylinder('paint', (x, 2.6, .5), (x, 2.6, 13.0), 2.4, sides, bevel=.9 if lod == 0 else 0)
        for z in (3.0, 10.5):
            box('dark', (x, 2.6, z), (5.0, 5.1, .5))
    box('steel', (0, 1.0, 2.0), (6.0, 2.0, 2.0))
    cylinder('steel', (0, 2.6, 13.0), (0, 2.6, 15.0), .4, 8)
    box('dark', (0, 2.6, .25), (11.0, 5.4, .5))
    return Vector((11, 6))


def ladder_cage(lod):
    # A caged ladder two storeys up a facade.
    for x in (-1.0, 1.0):
        box('steel', (x, 1.2, 18.0), (.25, .25, 36.0))
    for z in range(1, 36, 2):
        box('steel', (0, 1.2, z), (2.0, .2, .2))
    if lod == 0:
        for z in range(8, 37, 4):
            cylinder('dark', (-1.6, .4, z), (-1.6, 2.6, z), .12, 5)
            cylinder('dark', (1.6, .4, z), (1.6, 2.6, z), .12, 5)
            box('dark', (0, 2.6, z), (3.4, .2, .2))
        for x in (-1.2, 0.0, 1.2):
            box('dark', (x, 2.7, 22.0), (.15, .15, 28.0))
    return Vector((4, 3))


def light_mast(lod):
    # A lattice mast with a lamp head and a red beacon, for a roof or the ground.
    sides = 6 if lod == 0 else 4
    for x, y in ((-.9, -.9), (.9, -.9), (0, .9)):
        cylinder('steel', (x, y, 0), (x * .4, y * .4, 22.0), .18, sides)
    if lod == 0:
        for z in range(3, 21, 3):
            cylinder('steel', (-.9 + .6 * z / 22, -.9 + .6 * z / 22, z), (.9 - .6 * z / 22, -.9 + .6 * z / 22, z), .1, 4)
    box('dark', (0, 0, 22.4), (3.2, 1.0, .8))
    box('glass', (0, .55, 22.4), (2.8, .1, .5))
    cylinder('beacon', (0, 0, 22.8), (0, 0, 23.6), .35, 8)
    return Vector((3, 3))


def vehicle_gate(lod):
    # A vehicle gate against a facade, one vehicle wide: its back on y = 0, a pale blast door of three leaves facing +Y
    # in a dark frame under a striped lintel between striped posts. The board stretches its depth to the road's end.
    box('paint', (0, 5.0, 7.0), (24.0, 10.0, 14.0), bevel=.8 if lod == 0 else 0)
    box('paint', (0, 4.6, 14.25), (20.0, 7.0, .5), bevel=.1 if lod == 0 else 0)
    box('dark', (0, 10.05, 6.1), (18.0, .3, 12.2))
    box('paint', (0, 10.25, 5.5), (16.0, .3, 11.0), bevel=.08 if lod == 0 else 0)
    for z in (3.7, 7.3):
        box('dark', (0, 10.45, z), (15.6, .15, .3))
    box('hazard', (0, 10.3, 12.9), (18.0, .6, 1.2))
    for x in (-9.6, 9.6):
        box('hazard', (x, 10.3, 5.5), (1.0, .6, 11.0))
    if lod == 0:
        for x in (-6.0, 6.0):
            box('glass', (x, 10.55, 13.0), (1.6, .1, .5))
    return Vector((24, 10))


def generator_ring(lod, slit=False, deep=.35, printed=True):
    # The printed lunar map's generator: a long, low, dark arch on its Y axis, closed at both side faces, with a hub
    # where the shaft passes. Ventilation cuts `deep` through it run along the axis, so from above it is an oval banded
    # in cyan; through them shows the lit core inside, the only part that glows. `slit` makes one long cut along the
    # centre instead, as on the map's small units. `printed` draws the Lunar Base map's forms: near-equal rounded slots, and
    # a line that keeps its width over a pale band across the middle. Cheap on purpose: no undersides, each cut on a
    # segment boundary, no bevels. LOD1 drops the cuts' walls unless it is a slit.
    full = lod == 0
    half, height = 10.5, 3.6
    radius = (half * half + height * height) / (2 * height)

    def rise(x):
        return math.sqrt(radius * radius - x * x) - (radius - height)
    if slit:
        cuts, reach = [(-.76, .76)], .55
        rows = {-1, -.76, -.38, 0, .38, .76, 1} | ({-.72, -.57, -.16, .16, .57, .72} if printed else set())
    else:
        cuts, reach = [(c - w, c + w) for c, w in ((-.63, .036), (-.44, .045), (-.235, .052), (0, .06), (.235, .052),
                                                   (.44, .045), (.63, .036))], 1.9
        rows = {edge for cut in cuts for edge in cut} | {-1, -.83, .83, 1}
    rows = sorted(rows)
    across = ([(-3.0, .91, .7), (-2.16, 1, .95), (-reach, 1, 1), (reach, 1, 1), (2.16, 1, .95), (3.0, .91, .7)]
              if full else [(-3.0, .91, .7), (-reach, 1, 1), (reach, 1, 1), (3.0, .91, .7)])
    walls = full or slit
    floor = deep + .03
    meshes = {}

    def face(kind, *corners):
        points, index, faces = meshes.setdefault(kind, ([], {}, []))
        loop = []
        for corner in corners:
            at = tuple(round(c, 4) for c in corner)
            if at not in index:
                index[at] = len(points)
                points.append(at)
            loop.append(index[at])
        faces.append(tuple(loop))

    def skin(f, y, stretch=1, lift=1, drop=0):
        return f * half * stretch, y, rise(f * half) * lift - drop

    def lens(f):
        # The map's line keeps its width to rounded ends; plain, a lens.
        return reach * .92 * (1 if printed and abs(f) < .72 else math.sqrt(max(0, 1 - (f / (cuts[0][1] + .02)) ** 2)))
    # The arch, crowned across its width and narrower at its edges, open at each cut down to the core.
    middle = len(across) // 2 - 1
    for a, b in zip(rows, rows[1:]):
        cut = any(c0 <= a and b <= c1 for c0, c1 in cuts)
        for j, (s0, s1) in enumerate(zip(across, across[1:])):
            if not (cut and j == middle):
                banded = slit and printed and abs(a + b) < .32 and (j in (1, 3) or not full)
                face('plate' if banded else 'shell', skin(a, *s0), skin(b, *s0), skin(b, *s1), skin(a, *s1))
        if cut and walls:
            face('shell', skin(a, -reach), skin(b, -reach), skin(b, -reach, drop=floor), skin(a, -reach, drop=floor))
            face('shell', skin(a, reach, drop=floor), skin(b, reach, drop=floor), skin(b, reach), skin(a, reach))
            # A dark floor round the lit core's lens shape, which is all the cut shows.
            face('shell', skin(a, -reach, drop=floor), skin(b, -reach, drop=floor), skin(b, reach, drop=floor), skin(a, reach, drop=floor))
        if cut and slit:
            face('core', skin(a, -lens(a), drop=deep), skin(b, -lens(b), drop=deep), skin(b, lens(b), drop=deep), skin(a, lens(a), drop=deep))
    for c0, c1 in cuts:
        if not slit and full:
            # An oval of lit core, widest at the arch's crown.
            c, half_cut = (c0 + c1) / 2, (c1 - c0) / 2
            wide = reach * .96 * (1 - (.18 if printed else .45) * (c / cuts[-1][1]) ** 2)
            sides, power = (12, .55) if printed else (10, 1)
            face('core', *(skin(c + half_cut * math.copysign(abs(math.cos(k * math.tau / sides)) ** power, math.cos(k * math.tau / sides)),
                                wide * math.copysign(abs(math.sin(k * math.tau / sides)) ** power, math.sin(k * math.tau / sides)), drop=deep)
                           for k in range(sides)))
        elif not slit:
            face('core', skin(c0, -reach - deep, drop=deep), skin(c1, -reach - deep, drop=deep), skin(c1, reach + deep, drop=deep), skin(c0, reach + deep, drop=deep))
        if walls:
            face('shell', skin(c0, -reach, drop=floor), skin(c0, reach, drop=floor), skin(c0, reach), skin(c0, -reach))
            face('shell', skin(c1, -reach), skin(c1, reach), skin(c1, reach, drop=floor), skin(c1, -reach, drop=floor))
    # Closed side faces, each with a modest half-round hub where the shaft passes.
    face('shell', *(skin(f, *across[-1]) for f in rows))
    face('shell', *(skin(f, *across[0]) for f in reversed(rows)))
    steps = 6 if full else 4
    arc = [(-4.3 * math.cos(k * math.pi / steps), 1.9 * math.sin(k * math.pi / steps)) for k in range(steps + 1)]
    # The map's small units join their neighbours through these hubs.
    hub = 3.75 if slit and printed else 3.5
    for y0, y1, cap in ((3.0, hub, hub), (-hub, -3.0, -hub)):
        for (x0, z0), (x1, z1) in zip(arc, arc[1:]):
            face('shell', (x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0))
        face('shell', *((x, cap, z) for x, z in (arc if cap > 0 else reversed(arc))))
    for kind, (points, _, faces) in meshes.items():
        data = bpy.data.meshes.new(kind)
        data.from_pydata(points, [], faces)
        data.update()
        obj = bpy.data.objects.new(kind, data)
        bpy.context.collection.objects.link(obj)
        solid(obj, kind, smooth=math.radians(35))
    return Vector((21, 7))


def twin_pipes(lod):
    # The printed lunar map's pair of roof pipes along Y beside a generator bank: two collars, risers at their north end.
    sides, z = (12 if lod == 0 else 6), 4.5
    for x in (-3.2, 3.2):
        cylinder('plate', (x, -44, z), (x, 44, z), 1.0, sides)
        cylinder('plate', (x, 44, 0), (x, 44, z + .6), 1.7, sides)
        cylinder('plate', (x, -44, 0), (x, -44, z), 1.0, sides)
    for y in (0, -31.5):
        cylinder('plate', (-7, y, z), (7, y, z), 2.4, sides)
        if lod == 0:
            box('dark', (0, y, z / 2), (8, 2.2, z))
    return Vector((14, 90))


def edge_spike(lod):
    # The printed lunar map's pointed fitting on a roof's edge: its base on the roof, its point out along +Y past the wall.
    sides = 10 if lod == 0 else 6
    box('dark', (0, 0, 1.6), (7, 6, 3.2), bevel=.25 if lod == 0 else 0)
    cylinder('dark', (0, 3, 2.2), (0, 6, 2.2), 2.6, sides)
    cone('dark', (0, 6, 2.2), (0, 14, 2.2), 2.6, sides)
    return Vector((7, 17))


def twin_pipes(lod):
    # The printed lunar map's pair of roof pipes along Y beside a generator bank: two collars, risers at their north end.
    sides, z = (12 if lod == 0 else 6), 4.5
    for x in (-3.2, 3.2):
        cylinder('plate', (x, -44, z), (x, 44, z), 1.0, sides)
        cylinder('plate', (x, 44, 0), (x, 44, z + .6), 1.7, sides)
        cylinder('plate', (x, -44, 0), (x, -44, z), 1.0, sides)
    for y in (0, -31.5):
        cylinder('plate', (-7, y, z), (7, y, z), 2.4, sides)
        if lod == 0:
            box('dark', (0, y, z / 2), (8, 2.2, z))
    return Vector((14, 90))


def edge_spike(lod):
    # The printed lunar map's pointed fitting on a roof's edge: its base on the roof, its point out along +Y past the wall.
    sides = 10 if lod == 0 else 6
    box('dark', (0, 0, 1.6), (7, 6, 3.2), bevel=.25 if lod == 0 else 0)
    cylinder('dark', (0, 3, 2.2), (0, 6, 2.2), 2.6, sides)
    cone('dark', (0, 6, 2.2), (0, 17, 2.2), 2.6, sides)
    return Vector((7, 20))


def radar_station(lod):
    # The printed lunar map's radar: the roof dish, a third larger, on a turntable inside a raised ring. Its base drum
    # stands taller than a habitat roof's vents (at the Lunar Base's .65 too), so the fittings it covers stay under it.
    sides = 48 if lod == 0 else 20
    cylinder('dark', (0, 0, 0), (0, 0, 3.0), 25.0, sides)
    cylinder('paint', (0, 0, 3.0), (0, 0, 3.8), 25.0, sides)
    cylinder('steel', (0, 0, 3.0), (0, 0, 4.8), 18.0, sides)
    before = set(bpy.context.scene.objects)
    radar_dish(lod)
    for obj in set(bpy.context.scene.objects) - before:
        obj.location = obj.location * 1.3 + Vector((0, 0, 4.8))
        obj.scale = obj.scale * 1.3
    return Vector((50, 50))


def light_well(lod):
    # A square well of lit cyan glass in a steel curb, set in a roof.
    box('steel', (0, 0, .5), (14.0, 14.0, 1.0), bevel=.15 if lod == 0 else 0)
    box('glass', (0, 0, 1.02), (11.0, 11.0, .1))
    if lod == 0:
        for k in (-1.8, 1.8):
            box('steel', (k, 0, 1.1), (.4, 11.0, .2))
            box('steel', (0, k, 1.1), (11.0, .4, .2))
    return Vector((14, 14))


def light_strip(lod):
    # A long strip of lit cyan glass in a steel curb along a roof, glazing bars across it.
    box('steel', (0, 0, .5), (34.0, 7.0, 1.0), bevel=.15 if lod == 0 else 0)
    box('glass', (0, 0, 1.02), (31.0, 4.6, .1))
    if lod == 0:
        for x in range(-12, 13, 4):
            box('steel', (x, 0, 1.1), (.4, 4.6, .2))
    return Vector((34, 7))


def dish_antenna(lod):
    # A small tilted dish with its feed arm on a mast braced by three legs.
    for angle in (90.0, 210.0, 330.0):
        a = math.radians(angle)
        cylinder('steel', (2.4 * math.cos(a), 2.4 * math.sin(a), 0), (0, 0, 13.0), .32, 8 if lod == 0 else 5)
    cylinder('steel', (0, 0, 9.0), (0, 0, 15.0), .55, 10 if lod == 0 else 6)
    box('steel', (0, 0, 15.0), (1.6, 1.6, 1.2))
    tilt = (math.radians(-55), 0, 0)
    cap('paint', (0, .6, 15.6), 5.5, 1.4, 32 if lod == 0 else 14, 24 if lod == 0 else 10, rotation=tilt)
    if lod == 0:
        cylinder('steel', (0, .6, 15.6), (0, 3.6, 18.0), .16, 6)
        cylinder('steel', (0, 3.6, 18.0), (0, 3.6, 18.6), .4, 8)
    return Vector((8, 8))


def sawtooth_skylight(lod):
    # Three sawtooth roof lights in a row on a steel curb: each glazed slope rises towards +Y to a short painted upstand.
    box('steel', (0, 0, .4), (22.0, 16.4, .8), bevel=.15 if lod == 0 else 0)
    rise, run = 3.6, 4.6
    slope = math.atan2(rise, run)
    for y in (-5.2, 0.0, 5.2):
        box('glass', (0, y, .8 + rise / 2), (20.0, math.hypot(rise, run), .3), rotation=(slope, 0, 0))
        box('paint', (0, y + run / 2 + .15, .8 + rise / 2), (20.4, .3, rise), bevel=.06 if lod == 0 else 0)
        if lod == 0:
            for x in (-10.1, 10.1):
                box('paint', (x, y + .4, .8 + rise * .35), (.3, run * .8, rise * .7))
    if lod == 0:
        cylinder('steel', (-11.4, -7.6, 1.3), (-11.4, 7.6, 1.3), .45, 8)
    return Vector((22, 16))


# Roof props: board objects of their own (models/board/scenery/roofs/<name>.glb).
ROOF_PROPS = {'radar-dish': radar_dish, 'capsule-tanks': capsule_tanks, 'generator-ring': generator_ring,
              'generator-slit': lambda lod: generator_ring(lod, slit=True, deep=.5),
              'twin-pipes': twin_pipes, 'edge-spike': edge_spike,
              'radar-station': radar_station, 'light-well': light_well, 'light-strip': light_strip,
              'solar-array': solar, 'dish-antenna': dish_antenna, 'sawtooth-skylight': sawtooth_skylight}
# Colony detail props (models/board/scenery/colony/<name>.glb): building details the board places with precision
# placement to break a block's outline; wall-mounted ones stand with their back on y = 0, against a facade.
COLONY_PROPS = {'pipe-run': pipe_run, 'vent-unit': vent_unit, 'wall-tanks': wall_tanks, 'ladder-cage': ladder_cage,
                'light-mast': light_mast, 'airlock': airlock, 'radiator': radiator, 'vehicle-gate': vehicle_gate}


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def collect(name):
    """The scene's objects as one kit node: triangles by material kind, box-projected UVs, contact and dust shading."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    kinds, welds = {}, {}
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        kind = obj['kind']
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        world = evaluated.matrix_world
        rotate = world.to_3x3().inverted().transposed()
        normals = mesh.corner_normals
        vertices, faces = kinds.setdefault(kind, ([], []))
        welded = welds.setdefault(kind, {})
        for triangle in mesh.loop_triangles:
            corners = []
            for loop in triangle.loops:
                p = world @ mesh.vertices[mesh.loops[loop].vertex_index].co
                n = (rotate @ normals[loop].vector).normalized()
                axis = max(range(3), key=lambda k: abs(n[k]))
                u, v = [(p.y, p.z), (p.x, p.z), (p.x, p.y)][axis]
                repeat = REPEAT[kind]
                shade = .7 + .3 * smoothstep(0, 3.5, p.z)
                if kind in COLOUR_SLOTS:
                    shade *= .5 + .5 * smoothstep(.15, .75, n.z)  # Dark sides and hubs, as the map draws them.
                # No dust on a slot: lighter than a dark default, it would stay as a ratio above 1 under a light colour.
                dust = 0 if kind in COLOUR_SLOTS else (1 - smoothstep(.2, 2.0, p.z)) * .45 + max(0.0, n.z) * .12
                colour = [(TINT[kind][c] * (1 - dust) + DUST[c] * dust) * shade for c in range(3)]
                vertex = (p.x, p.y, p.z, n.x, n.y, n.z, *colour, 1.0, u / repeat, -v / repeat)
                key = tuple(round(x, 5) for x in vertex)
                if key not in welded:
                    welded[key] = len(vertices)
                    vertices.append(list(vertex))
                corners.append(welded[key])
            faces.append(corners)
        evaluated.to_mesh_clear()
    vertices, parts, slots = [], [], []
    for kind, (vs, fs) in sorted(kinds.items()):
        base = len(vertices)
        vertices.extend(vs)
        slots.extend([list(COLOUR_SLOTS).index(kind) + 1 if kind in COLOUR_SLOTS else 0] * len(vs))
        parts.append({'id': f'{name}-{kind}', 'type': 'TRIANGLES', 'indices': [i + base for f in fs for i in f]})
    node = {'id': name, 'parts': [{'meshpartid': p['id'], 'materialid': p['id'].rsplit('-', 1)[1]} for p in parts]}
    mesh = {'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
            'vertices': [float(x) for v in vertices for x in v], 'parts': parts, 'slots': slots}
    return mesh, node, set(kinds), sum(len(f) for _, f in kinds.values())


def materials(kinds, folder):
    """Board materials for the kinds used, by their albedo image relative to the GLB's folder."""
    textures = os.path.relpath(MODELS / 'board/textures', folder).replace(os.sep, '/') + '/'
    return [{'id': kind, 'diffuse': [1, 1, 1], 'roughness': .5, 'metallic': 0, 'emissive': TINT[kind]} if kind == 'core'
            else {'id': kind, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
                  'extras': {'mmBuildingPaint': True} if kind == 'paint' else {},
                  'textures': [{'type': 'DIFFUSE', 'filename': f'{textures}{BOARD[kind]}_albedo.png'}]}
            for kind in sorted(kinds)]


def main():
    levels = {}
    for level in (0, 1):
        meshes, nodes, kinds = [], [], set()
        for piece, build in PIECES.items():
            reset()
            build(level)
            mesh, node, used, triangles = collect(f'{piece}-lod{level}')
            meshes.append(mesh)
            nodes.append(node)
            kinds |= used
            print(f'{piece} lod{level}: {triangles} triangles')
        levels[level] = {'materials': materials(kinds, OUT), 'meshes': meshes, 'nodes': nodes}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'lunar-equipment.glb'
    write_glb(path, levels=levels)
    print('written', path, path.stat().st_size, 'bytes')
    for folder, props in ((ROOFS, ROOF_PROPS), (COLONY, COLONY_PROPS)):
        folder.mkdir(parents=True, exist_ok=True)
        for name, build in props.items():
            write_prop(folder, name, build)


def write_prop(folder, name, build):
    """A board object: one piece at both levels of detail, its own file in `folder`."""
    prop = {}
    for level in (0, 1):
        reset()
        build(level)
        mesh, node, used, triangles = collect(name)
        prop[level] = {'materials': materials(used, folder), 'meshes': [mesh], 'nodes': [node]}
        print(f'{name} lod{level}: {triangles} triangles')
    path = folder / f'{name}.glb'
    write_glb(path, levels=prop, extras={'mmColourSlots': list(COLOUR_SLOTS.values())} if used & set(COLOUR_SLOTS) else None)
    print('written', path, path.stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
