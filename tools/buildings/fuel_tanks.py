"""Fuel tank kits: round tanks joined by pipes, on the board's shared materials.

    python tools/buildings/fuel_tanks.py [weight ...]

Writes data/models/buildings/fuel_tanks/fuel_tank_<weight>.glb, connected kits (see data/models/buildings/README.md)
stacked as built: the base (first course, from the ground), a floor (a further course), the domed roof, the north pipe
(`link-n`) and the blind flange where no pipe leaves (`end-n`), in three levels of detail (the props' rule: above 80
pixels on screen, down to 24, below). The designer's kits set the sizes, the paint and the roof's rings, bolts and
seams. The light and medium tanks are banded: a painted shell on a steel plinth, with grey rings standing out from
it. The heavy and hard tanks are clad: painted cladding standing out from the shell, with painted panels let into it
in bays, and on the hard tank pressed vents between them. Painted parts take `weathered-paint` and vents
`vent-slots`, both tinted by vertex colour; steel parts take `rusted-steel`. Vertex colours also carry contact
shading and grime.
"""
import math
import os
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import write_glb  # noqa: E402

MODELS = TOOLS.parent / 'data/models'
OUT = MODELS / 'buildings/fuel_tanks'
BOARD_MATERIALS = {'paint': 'structures/common/weathered-paint', 'steel': 'structures/common/rusted-steel',
                   'vent': 'structures/common/vent-slots'}
# Board units one texture repeat covers; a vent maps one repeat (two slots across, eight down) onto VENT units square.
REPEAT = {'paint': 24.0, 'steel': 12.0, 'vent': 8.0}
VENT = 8.0
TEXTURES = os.path.relpath(MODELS / 'board/textures', OUT).replace(os.sep, '/') + '/'
MATERIALS = [{'id': kind, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
              'extras': {'mmBuildingPaint': True} if kind == 'paint' else {},
              'textures': [{'type': 'DIFFUSE', 'filename': f'{TEXTURES}{name}_albedo.png'}]}
             for kind, name in BOARD_MATERIALS.items()]
# Display tints over the shared materials' mean albedo, measured from the designer's atlases.
WHITE, RED, YELLOW, GREY = (.89, .90, .91), (.87, .29, .24), (.89, .645, .22), (.58, .60, .63)
STEEL, DARK_STEEL, BOLT, CLAD = (1, 1, 1), (.78, .76, .76), (.55, .55, .55), (.46, .48, .52)
# Rust gathered at a panel's edges, over its paint.
RUST_EDGE = np.array([.72, .58, .46])
# A banded shell's grey ring standing out from it, as its lip.
RING = 'ring'
LEVEL, EDGE = 18.0, 36.0
PIPE_R, PIPE_Z, FLANGE_R = .9, 1.5, 1.3
# Segments round the tank and round the pipe, by level of detail.
SEGMENTS, PIPE_SEGMENTS = (40, 16, 10), (12, 6, 4)
# How far rust bleeds along the line from a joint; how far a nozzle reaches out of the tank.
BLEED, NOZZLE = 1.2, .55
# Per weight: the shell's radius and how far out its rings, plinth or cladding stand. A banded tank has a plinth and
# paint bands (from where each starts, a colour or RING) up its base and a floor; a clad tank has `bays` (count,
# width in degrees), pressed `vents` between them if any, and panel rows (bottom, top, paint bands) in its base and a
# floor. Roof: paint rings out from the
# centre, bolt rings (radius, count, head size), raised dashes along a ring and pads across one (radius, count,
# length, width), and the rounded seam near the rim.
WEIGHTS = {
    'light': {'radius': 16.0, 'outer': 16.96, 'plinth': 4.0,
              'base': [(4.0, RED), (10.0, YELLOW), (11.0, WHITE), (17.0, RING)], 'floor': [(0.0, WHITE), (17.0, RING)],
              'roof': [(0.0, WHITE), (11.1, YELLOW), (12.7, RED)], 'bolts': [(10.2, 16, .32)], 'seam': 15.4},
    'medium': {'radius': 20.0, 'outer': 21.2, 'plinth': 4.0,
               'base': [(4.0, RED), (8.0, RING), (9.0, YELLOW), (17.0, RING)],
               'floor': [(0.0, WHITE), (8.0, RING), (9.0, WHITE), (17.0, RING)],
               'roof': [(0.0, WHITE), (13.8, YELLOW), (16.2, RED)], 'bolts': [(5.7, 16, .22), (13.2, 24, .26)],
               'seam': 19.3},
    'heavy': {'radius': 24.0, 'outer': 25.44, 'bays': (8, 34.0),
              'base': [(9.0, 17.0, [(9.0, RED), (13.0, YELLOW)])],
              'floor': [(0.0, 8.0, [(0.0, WHITE)]), (9.0, 17.0, [(9.0, WHITE)])],
              'roof': [(0.0, WHITE), (13.8, YELLOW), (17.6, RED)], 'bolts': [(4.5, 20, .2)],
              'pads': [(11.9, 16, 1.3, .7)], 'seam': 23.3},
    'hard': {'radius': 26.4, 'outer': 27.98, 'bays': (8, 23.0), 'vents': True,
             'base': [(9.0, 17.0, [(9.0, RED), (13.0, YELLOW)])],
             'floor': [(0.0, 8.0, [(0.0, WHITE)]), (9.0, 17.0, [(9.0, WHITE)])],
             'roof': [(0.0, WHITE), (16.0, YELLOW), (20.0, RED)],
             'dashes': [(15.1, 24, 1.6, .36), (24.8, 32, 1.4, .36)], 'seam': 25.7},
}


def smoothstep(a, b, x):
    t = min(max((x - a) / (b - a), 0.0), 1.0)
    return t * t * (3 - 2 * t)


class Module:
    """One kit node's triangles by material: position, normal, display colour and uv per vertex. `shade(position,
    kind)` darkens the colour; `turn`, a rotation, turns what is added."""

    def __init__(self, shade=lambda p, kind: 1.0):
        self.kinds, self.shade, self.turn = {}, shade, np.eye(3)

    def add(self, kind, colour, positions, normals, uvs, triangles):
        """`colour`: one for all the vertices, or one each."""
        positions = [self.turn @ np.asarray(p, float) for p in positions]
        normals = [self.turn @ np.asarray(n, float) for n in normals]
        colours = np.broadcast_to(np.asarray(colour, float), (len(positions), 3))
        vertices, faces = self.kinds.setdefault(kind, ([], []))
        first = len(vertices)
        for p, n, c, uv in zip(positions, normals, colours, uvs):
            n = n / (np.linalg.norm(n) or 1)
            vertices.append([*p, *n, *np.clip(c * self.shade(p, kind), 0, 1), 1.0, *uv])
        for t in triangles:
            a, b, c = (np.asarray(positions[i]) for i in t)
            area = np.cross(b - a, c - a)
            if np.linalg.norm(area) < 1e-9:
                continue
            # Wound to face its normals.
            facing = area @ (normals[t[0]] + normals[t[1]] + normals[t[2]])
            faces.append([first + t[0], first + t[1], first + t[2]] if facing >= 0
                         else [first + t[0], first + t[2], first + t[1]])

    def mesh(self, name, lift=0.0):
        """The mesh and its node, raised by `lift` (the loader stands every role on the ground, so a kit is authored
        stacked as built)."""
        vertices, parts = [], []
        for kind, (vs, fs) in sorted(self.kinds.items()):
            base = len(vertices)
            vertices.extend(vs)
            parts.append({'id': f'{name}-{kind}', 'type': 'TRIANGLES', 'indices': [i + base for f in fs for i in f]})
        node = {'id': name, 'parts': [{'meshpartid': p['id'], 'materialid': p['id'].rsplit('-', 1)[1]} for p in parts]}
        if lift:
            node['translation'] = [0.0, 0.0, lift]
        return ({'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                 'vertices': [float(x) for v in vertices for x in v], 'parts': parts}, node)


def frame(axis):
    axis = np.asarray(axis, float)
    across = np.array([1.0, 0, 0]) if abs(axis[0]) < .9 else np.array([0, 0, 1.0])
    across -= axis * (across @ axis)
    across /= np.linalg.norm(across)
    return axis, across, np.cross(axis, across)


def lathe(module, kind, colour, points, segments, normals=None, origin=(0, 0, 0), axis=(0, 0, 1), turn=0.0,
          angles=None):
    """Turn a profile of (radius, height along the axis) points about an axis, starting at angle `turn` (or through
    the given `angles`). Each pair of points makes one band, flat across the profile (a hard edge at each point)
    unless per-point (radial, axial) normals are given."""
    axis, e1, e2 = frame(axis)
    origin = np.asarray(origin, float)
    repeat = REPEAT[kind]
    if angles is None:
        angles = [turn + 2 * math.pi * j / segments for j in range(segments + 1)]
    for i in range(len(points) - 1):
        (r0, a0), (r1, a1) = points[i], points[i + 1]
        if normals is None:
            flat = np.array([a1 - a0, -(r1 - r0)])
            n0 = n1 = flat / (np.linalg.norm(flat) or 1)
        else:
            n0, n1 = np.asarray(normals[i], float), np.asarray(normals[i + 1], float)
        # Rings round a band take a whole number of repeats, or true size with a seam where they start when shorter
        # than one; a band facing along the axis maps flat.
        across = 2 * math.pi * max(r0, r1) / repeat
        across = round(across) if across >= 1 else across
        planar = abs(n0[1] + n1[1]) / 2 > .7
        positions, vectors, uvs, triangles = [], [], [], []
        for j, angle in enumerate(angles):
            radial = math.cos(angle) * e1 + math.sin(angle) * e2
            for r, a, n in ((r0, a0, n0), (r1, a1, n1)):
                p = origin + axis * a + radial * r
                positions.append(p)
                vectors.append(radial * n[0] + axis * n[1])
                uvs.append((r * math.cos(angle) / repeat, r * math.sin(angle) / repeat) if planar
                           else (across * (angle - turn) / (2 * math.pi), -a / repeat))
            if j:
                k = 2 * j
                triangles += [(k - 2, k - 1, k + 1), (k - 2, k + 1, k)]
        module.add(kind, colour, positions, vectors, uvs, triangles)


def prism(module, kind, colour, centre, normal, radius, height, sides=6, turn=0.0):
    """A polygonal prism standing on a surface: a bolt head, a nut, a stud."""
    axis, e1, e2 = frame(normal)
    centre = np.asarray(centre, float)
    repeat = REPEAT[kind]
    ring = [math.cos(turn + 2 * math.pi * k / sides) * e1 + math.sin(turn + 2 * math.pi * k / sides) * e2
            for k in range(sides)]
    top = centre + axis * height
    for k in range(sides):
        a, b = ring[k], ring[(k + 1) % sides]
        face = (a + b) / 2
        quad = [centre + a * radius, centre + b * radius, top + b * radius, top + a * radius]
        module.add(kind, colour, quad, [face] * 4, [(0, 0), (radius / repeat, 0), (radius / repeat, height / repeat),
                                                    (0, height / repeat)], [(0, 1, 2), (0, 2, 3)])
    cap = [top] + [top + r * radius for r in ring]
    module.add(kind, colour, cap, [axis] * len(cap), [((p - top) @ e1 / repeat, (p - top) @ e2 / repeat) for p in cap],
               [(0, k + 1, (k + 1) % sides + 1) for k in range(sides)])


def box(module, kind, colour, centre, axes, half):
    """An oriented box: `axes` its three unit axes, `half` its half sizes along them."""
    centre, repeat = np.asarray(centre, float), REPEAT[kind]
    axes = [np.asarray(a, float) for a in axes]
    for k in range(3):
        u, v = axes[(k + 1) % 3] * half[(k + 1) % 3], axes[(k + 2) % 3] * half[(k + 2) % 3]
        for sign in (1, -1):
            c = centre + sign * axes[k] * half[k]
            quad = [c - u - v, c + u - v, c + u + v, c - u + v]
            size_u, size_v = 2 * half[(k + 1) % 3] / repeat, 2 * half[(k + 2) % 3] / repeat
            module.add(kind, colour, quad, [sign * axes[k]] * 4, [(0, 0), (size_u, 0), (size_u, size_v), (0, size_v)],
                       [(0, 1, 2), (0, 2, 3)])


def radial(angle):
    return np.array([math.cos(angle), math.sin(angle), 0.0])


def grime(p, kind=None):
    """Splashed dirt near the ground."""
    return .8 + .2 * smoothstep(0, 5, p[2])


def contacts(bands, ledge):
    """A banded course's contact edges: where it meets a ring from below (ceilings) and stands on one or on its ledge
    (floors)."""
    tops = [b[0] for b in bands[1:]] + [LEVEL]
    rings = [(low, high) for (low, colour), high in zip(bands, tops) if colour == RING]
    return [low for low, _ in rings], [high for _, high in rings] + [ledge]


def banded_shade(bands, ledge, ground):
    """Contact shading on a banded course: under each ring, above each ring or ledge it stands on; ground grime on the
    base."""
    ceilings, floors = contacts(bands, ledge)

    def shade(p, kind):
        z, value = p[2], 1.0
        for c in ceilings:
            if z <= c:
                value *= .85 + .15 * smoothstep(c, c - 1.5, z)
        for f in floors:
            if z >= f:
                value *= .85 + .15 * smoothstep(f, f + 1.5, z)
        return value * (grime(p) if ground else 1)
    return shade


def courses(module, spec, bands, lod, ledge):
    """A banded course from its first band to the top of the level: paint bands on the shell, and grey rings standing
    out from it. At full detail the rings have their undersides and bevelled top edges, and the shell rings of
    vertices where contact shading ends."""
    radius, outer, segments, detail = spec['radius'], spec['outer'], SEGMENTS[lod], lod == 0
    ceilings, floors = contacts(bands, ledge)
    breaks = [c - 1.5 for c in ceilings] + [f + 1.5 for f in floors]
    for (low, colour), high in zip(bands, [b[0] for b in bands[1:]] + [LEVEL]):
        if colour == RING:
            bevel = .1 if detail else 0
            lathe(module, 'paint', GREY, ([(radius, low)] if detail else []) + [(outer, low), (outer, high - bevel)] +
                  ([(outer - bevel, high)] if detail else []) + [(radius, high)], segments)
        else:
            heights = sorted({low, high} | {h for h in breaks if detail and low < h < high})
            lathe(module, 'paint', colour, [(radius, h) for h in heights], segments)


def bays(spec, lod):
    """A clad course's angles round (uniform, with the bays' edges and at full detail the vents' added, so openings
    and vents are cut exactly), the bays' centres and half width, and the vents' centres and half width. Bays are
    centred between the axes, symmetric about them; vents lie midway between bays."""
    count, width = spec['bays']
    centres = [2 * math.pi * (k + .5) / count for k in range(count)]
    half = math.radians(width) / 2
    vents = [c + math.pi / count for c in centres] if lod == 0 and spec.get('vents') else []
    vent_half = VENT / 2 / spec['outer']
    angles = [2 * math.pi * j / SEGMENTS[lod] for j in range(SEGMENTS[lod])]
    angles += [(c + s * h) % (2 * math.pi) for cs, h in ((centres, half), (vents, vent_half)) for c in cs
               for s in (-1, 1)]
    angles = sorted(angles)
    angles = [a for i, a in enumerate(angles) if i == 0 or a - angles[i - 1] > 1e-6] + [2 * math.pi]
    return angles, centres, half, vents, vent_half


def nearest(angle, centres, half):
    """The centre within `half` of an angle, if any."""
    return next((c for c in centres if abs((angle - c + math.pi) % (2 * math.pi) - math.pi) < half - 1e-6), None)


def clad(module, spec, rows, lod):
    """A clad course: painted cladding standing out from the shell over the whole level, with a bay let into it for
    each of the course's panel rows (bottom, top, paint bands) and, on the hard tank at full detail, a vent between
    each pair of bays. The bays' jambs, sills and heads are rusted steel; the panels on the shell are painted, rust
    gathered at their edges at full detail. A row from the level's foot has no sill: the course below's top closes it.
    At the lowest detail the course is a painted cylinder, each row's bands mixing the panels' paint and the
    cladding's as much as the bays fill it round."""
    shell, outer = spec['radius'], spec['outer']
    if lod == 2:
        count, width = spec['bays']
        share = width * count / 360

        def mixed(colour):
            return tuple(share * np.array(colour) + (1 - share) * np.array(CLAD))

        bands, last = [], 0.0
        for bottom, top, paint in rows:
            if bottom > last:
                bands.append((last, CLAD))
            bands += [(low, mixed(colour)) for low, colour in paint]
            last = top
        bands.append((last, CLAD))
        for (low, colour), high in zip(bands, [b[0] for b in bands[1:]] + [LEVEL]):
            if high > low:
                lathe(module, 'paint', colour, [(outer, low), (outer, high)], SEGMENTS[lod])
        lathe(module, 'paint', CLAD, [(outer, LEVEL), (shell, LEVEL)], SEGMENTS[lod])
        return
    angles, centres, half, vents, vent_half = bays(spec, lod)
    rep, across = REPEAT['paint'], round(2 * math.pi * outer / REPEAT['paint'])
    cuts = sorted({0.0, LEVEL} | {z for bottom, top, _ in rows for z in (bottom, top)} |
                  ({2.5, 5.0} if lod == 0 else set()))
    for a0, a1 in zip(angles, angles[1:]):
        middle = (a0 + a1) / 2
        bay, vent = nearest(middle, centres, half), nearest(middle, vents, vent_half)
        for z0, z1 in zip(cuts, cuts[1:]):
            row = next(((bottom, top) for bottom, top, _ in rows if bottom <= z0 and z1 <= top), None)
            if row and bay is not None:
                continue
            quad = [radial(a0) * outer + [0, 0, z0], radial(a1) * outer + [0, 0, z0], radial(a1) * outer + [0, 0, z1],
                    radial(a0) * outer + [0, 0, z1]]
            corners = ((a0, z0), (a1, z0), (a1, z1), (a0, z1))
            if row and vent is not None:
                # One vent repeat over the row, offset half a slot cell (the slots sit on the cells' edges).
                bottom, top = row
                uvs = [((a - vent + vent_half) / (2 * vent_half) + .25, (top - z) / (top - bottom) + 1 / 16)
                       for a, z in corners]
                module.add('vent', CLAD, quad, [radial(a0), radial(a1), radial(a1), radial(a0)], uvs,
                           [(0, 1, 2), (0, 2, 3)])
            else:
                uvs = [(across * a / (2 * math.pi), -z / rep) for a, z in corners]
                module.add('paint', CLAD, quad, [radial(a0), radial(a1), radial(a1), radial(a0)], uvs,
                           [(0, 1, 2), (0, 2, 3)])
    # Its top, which the course above or the roof stands on.
    lathe(module, 'paint', CLAD, [(outer, LEVEL), (shell, LEVEL)], 0, angles=angles)
    steel = REPEAT['steel']
    for centre in centres:
        inside = [centre - half] + [a for a in angles if abs(a - centre) < half - 1e-6] + [centre + half]
        for bottom, top, bands in rows:
            # Jambs, facing into the opening.
            for edge, facing in ((centre - half, 1), (centre + half, -1)):
                tangent = np.array([-math.sin(edge), math.cos(edge), 0]) * facing
                quad = [radial(edge) * shell + [0, 0, bottom], radial(edge) * outer + [0, 0, bottom],
                        radial(edge) * outer + [0, 0, top], radial(edge) * shell + [0, 0, top]]
                module.add('steel', STEEL, quad, [tangent] * 4,
                           [(0, bottom / steel), ((outer - shell) / steel, bottom / steel),
                            ((outer - shell) / steel, top / steel), (0, top / steel)], [(0, 1, 2), (0, 2, 3)])
            # The sill (facing up) and the head (facing down).
            for z, profile in ((bottom, [(outer, bottom), (shell, bottom)]), (top, [(shell, top), (outer, top)])):
                if z > 0:
                    lathe(module, 'steel', STEEL, profile, 0, angles=inside)
            panel(module, shell, inside, bottom, top, bands, lod == 0)


def panel(module, shell, angles, bottom, top, bands, detail):
    """A painted panel on the shell across a bay's `angles`, in paint bands up from `bottom` to `top`; at full detail
    rust gathers at its edges, over a border about a third of a unit wide."""
    inset = .35
    if detail:
        angles = sorted({*angles, angles[0] + inset / shell, angles[-1] - inset / shell})
    tops = [b[0] for b in bands[1:]] + [top]
    rep = REPEAT['paint']
    for (low, colour), high in zip(bands, tops):
        borders = {h for h in (bottom + inset, top - inset) if low < h < high} if detail else set()
        heights = sorted({low, high} | borders)
        positions, normals, colours, uvs, triangles = [], [], [], [], []
        for i, a in enumerate(angles):
            for j, z in enumerate(heights):
                positions.append(radial(a) * shell + [0, 0, z])
                normals.append(radial(a))
                edge = detail and (i in (0, len(angles) - 1) or z in (bottom, top))
                colours.append(np.array(colour) * (RUST_EDGE if edge else 1))
                uvs.append((a * shell / rep, -z / rep))
                if i and j:
                    k, n = i * len(heights) + j, len(heights)
                    triangles += [(k - n - 1, k - 1, k), (k - n - 1, k, k - n)]
        module.add('paint', colours, positions, normals, uvs, triangles)


def chairs(module, spec):
    """Anchor chairs on the plinth step: two gussets, a top plate and its nut, between the six pipe directions."""
    radius, plinth = spec['radius'], spec['plinth']
    colour = spec['base'][0][1]
    up = np.array([0, 0, 1.0])
    for k in range(12):
        angle = math.radians(15 + 30 * k)
        out, side = radial(angle), np.array([-math.sin(angle), math.cos(angle), 0])
        foot = out * (radius + .42)
        for s in (-1, 1):
            box(module, 'paint', colour, foot + side * s * .45 + up * (plinth + .9), (out, side, up), (.4, .06, .9))
        box(module, 'paint', colour, foot + up * (plinth + 1.88), (out, side, up), (.45, .6, .08))
        prism(module, 'steel', BOLT, foot + out * .1 + up * (plinth + 1.96), up, .22, .2, sides=4, turn=angle)


def base(spec, lod):
    radius, outer, segments = spec['radius'], spec['outer'], SEGMENTS[lod]
    if 'bays' in spec:
        module = Module(grime)
        clad(module, spec, spec['base'], lod)
    else:
        plinth = spec['plinth']
        module = Module(banded_shade(spec['base'], plinth, True))
        # The plinth: a steel ring the shell stands in, its top edge bevelled at full detail.
        bevel = .12 if lod == 0 else 0
        lathe(module, 'steel', DARK_STEEL, [(outer, 0), (outer, plinth - bevel)] +
              ([(outer - bevel, plinth)] if lod == 0 else []) + [(radius, plinth)], segments)
        courses(module, spec, spec['base'], lod, plinth)
        if lod == 0:
            chairs(module, spec)
    # A nozzle in each of the six pipe directions (at full detail): a pipe's flange or a blind flange closes it.
    if lod == 0:
        for k in range(6):
            angle = math.radians(60 * k)
            module.turn = np.array([[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0],
                                    [0, 0, 1]])
            nozzle(module, outer, lod)
        module.turn = np.eye(3)
    return module


def floor(spec, lod):
    if 'bays' in spec:
        module = Module()
        clad(module, spec, spec['floor'], lod)
    else:
        module = Module(banded_shade(spec['floor'], 0, False))
        courses(module, spec, spec['floor'], lod, 0)
    return module


def roof(spec, lod):
    """A dome (a spherical cap rising 4 units) in paint rings, rusty at the rim, with the weight's bolt rings, dashes
    or pads, and a raised rounded seam near the rim."""
    radius, rise, segments, detail = spec['radius'], 4.0, SEGMENTS[lod], lod == 0
    module = Module(lambda p, kind: 1 - .3 * smoothstep(radius - .6, radius, math.hypot(p[0], p[1])))
    sphere = (radius ** 2 + rise ** 2) / (2 * rise)

    def height(r):
        return math.sqrt(sphere ** 2 - r ** 2) - (sphere - rise)

    def normal(r):
        return np.array([r, height(r) + sphere - rise]) / sphere

    def surface(r, angle):
        """A point on the dome and its frame: up (the dome's normal), out (down the slope) and round."""
        n = normal(r)
        up = radial(angle) * n[0] + np.array([0, 0, n[1]])
        out = radial(angle) * n[1] - np.array([0, 0, n[0]])
        return radial(angle) * r + [0, 0, height(r)], up, out, np.cross(up, out)

    rings = spec['roof'] + [(radius, None)]
    for (low, colour), (high, _) in zip(rings, rings[1:]):
        # Rings every 2.5 units at full detail; below, only the paint's.
        radii = np.linspace(low, high, max(2, math.ceil((high - low) / 2.5) + 1) if detail else 2)
        lathe(module, 'paint', colour, [(r, height(r)) for r in radii[::-1]], segments,
              normals=[normal(r) for r in radii[::-1]])
    if not detail:
        return module
    # The seam: a raised rounded rim in the rim's paint.
    seam, bead = spec['seam'], .2
    arc = np.linspace(0, math.pi, 3)
    lathe(module, 'paint', rings[-2][1], [(seam + bead * math.cos(t), height(seam + bead * math.cos(t))
                                           + bead * .8 * math.sin(t)) for t in arc], segments,
          normals=[np.array([math.cos(t), math.sin(t)]) for t in arc])
    # Bolt rings: square heads, as the designer's.
    for ring, count, size in spec.get('bolts', []):
        for k in range(count):
            angle = 2 * math.pi * (k + .5) / count
            point, up, _, _ = surface(ring, angle)
            # Sunk a little: the dome's facets lie up to .04 inside the sphere.
            prism(module, 'steel', STEEL, point - up * .05, up, size, .6 * size + .03, sides=4,
                  turn=angle + math.pi / 4)
    # Raised marks round a ring: dashes along it, pads across it.
    for key, along in (('dashes', True), ('pads', False)):
        for ring, count, length, width in spec.get(key, []):
            for k in range(count):
                point, up, out, round_ = surface(ring, 2 * math.pi * (k + .5) / count)
                box(module, 'steel', BOLT, point + up * .03, (round_, out, up) if along else (out, round_, up),
                    (length / 2, width / 2, .06))
    return module


def flange(module, at, bolts, lod, closed=False, kind='steel', colour=STEEL, radius=FLANGE_R, thickness=.25,
           stud=.1):
    """A pipe flange from `at` along north, with square bolt studs (at full detail) on the face `bolts` points to (+1
    the far face, -1 the near one, 0 none). A closed flange is blind."""
    lathe(module, kind, colour, [(PIPE_R, at), (radius, at), (radius, at + thickness),
                                 (0 if closed else PIPE_R, at + thickness)],
          PIPE_SEGMENTS[lod], origin=(0, 0, PIPE_Z), axis=(0, 1, 0))
    if lod == 0 and bolts:
        for k in range(8):
            angle = 2 * math.pi * (k + .5) / 8
            centre = (1.1 * math.cos(angle), at + (thickness if bolts > 0 else 0), PIPE_Z + 1.1 * math.sin(angle))
            prism(module, 'steel', BOLT, centre, (0, bolts, 0), stud, stud, sides=4)


def nozzle(module, start, lod):
    """The tank's nozzle, pointing north, ending at start + NOZZLE: a weld neck and its flange."""
    lathe(module, 'steel', STEEL, [(PIPE_R + .1, start - .1), (PIPE_R + .1, start + .3)], PIPE_SEGMENTS[lod],
          origin=(0, 0, PIPE_Z), axis=(0, 1, 0))
    flange(module, start + .3, 0, lod)


def paint_runs(module, runs, stop, lod, joints):
    """The line between flanges and sleeves in paint: `runs` are (where a colour starts, colour), up to `stop`, with
    rings where the rust bled from its joints fades out; the paint's seam runs underneath."""
    for (low, colour), high in zip(runs, [r[0] for r in runs[1:]] + [stop]):
        cuts = sorted({low, high} | {j + d for j in joints for d in (-BLEED, BLEED) if lod == 0 and low < j + d < high})
        lathe(module, 'paint', colour, [(PIPE_R, a) for a in cuts], PIPE_SEGMENTS[lod], origin=(0, 0, PIPE_Z),
              axis=(0, 1, 0), turn=math.pi / 2)


def line_grime(joints):
    """The line's grime: ground dirt, and on its paint, dirt splashed underneath and rust bled out from its joints
    (positions along it)."""
    def shade(p, kind):
        if kind != 'paint':
            return grime(p)
        under = .55 + .3 * smoothstep(PIPE_Z - PIPE_R, PIPE_Z + .4, p[2])
        bleed = min([1.0] + [.7 + .3 * smoothstep(0, BLEED, abs(p[1] - joint)) for joint in joints])
        # A dirt film over all of it: the line is dirtier than the shell.
        return .85 * grime(p) * under * bleed
    return shade


def pipe(spec, lod):
    """The north link, painted as the designer's: from the nozzle red, a yellow band, red to a sleeve support on a
    ground block, red again, then white to the edge line, where a blind half joint in the line's paint meets the
    neighbour's. A wide tank leaves room for less: the band and the sleeve go first. Below full detail the line alone
    runs from the tank to the edge, the sleeve a grey band on it (none at the lowest)."""
    segments, sleeve = PIPE_SEGMENTS[lod], EDGE - 7.5
    # At full detail the line starts at the base's nozzle, with its own flange bolted to the nozzle's.
    start = spec['outer'] + (NOZZLE + .25 if lod == 0 else 0)
    joints = [start, sleeve, sleeve + 1.4, EDGE - .25]
    module = Module(line_grime(joints))
    if lod == 0:
        flange(module, start - .25, 1, lod)
    runs = [(start, RED)]
    if sleeve - start >= 9:
        runs += [(start + 4.3, YELLOW), (start + 7.8, RED)]
    if sleeve > start + 1:
        if lod == 0:
            paint_runs(module, runs, sleeve, lod, joints)
            runs = [(sleeve + 1.4, RED)]
            lathe(module, 'steel', STEEL, [(PIPE_R, sleeve), (1.08, sleeve), (1.08, sleeve + 1.4),
                                           (PIPE_R, sleeve + 1.4)], segments, origin=(0, 0, PIPE_Z), axis=(0, 1, 0))
            # The block stands on its base plate and meets the sleeve.
            axes, top = ((1, 0, 0), (0, 1, 0), (0, 0, 1)), PIPE_Z - 1.03
            box(module, 'steel', DARK_STEEL, (0, sleeve + .7, (top + .1) / 2), axes, (.75, .55, (top - .1) / 2))
            box(module, 'steel', DARK_STEEL, (0, sleeve + .7, .05), axes, (1.0, .75, .05))
        elif lod == 1:
            runs += [(sleeve, GREY), (sleeve + 1.4, RED)]
    if lod == 0:
        paint_runs(module, runs + [(EDGE - 3.5, WHITE)], EDGE - .25, lod, joints)
        flange(module, EDGE - .25, -1, lod, closed=True, kind='paint', colour=WHITE)
    else:
        paint_runs(module, runs + [(EDGE - 3.5, WHITE)], EDGE, lod, joints)
    return module


def end(spec, lod):
    """Where no pipe leaves: the base's nozzle closed by a blind flange, painted white as the designer's. It is a
    little larger than a line's flange, so the two never share a surface where a viewer shows the kit whole. Below
    full detail, with no nozzle, a white cap on the tank, a little wider than the line."""
    module = Module(grime)
    outer = spec['outer']
    if lod == 0:
        flange(module, outer + NOZZLE + .01, 1, lod, closed=True, kind='paint', colour=WHITE,
               radius=FLANGE_R + .04, thickness=.27, stud=.12)
    else:
        lathe(module, 'paint', WHITE, [(PIPE_R + .1, outer - .1), (PIPE_R + .1, outer + .3), (0, outer + .3)],
              PIPE_SEGMENTS[lod], origin=(0, 0, PIPE_Z), axis=(0, 1, 0))
    return module


def kit(weight):
    spec = WEIGHTS[weight]
    levels = {}
    for level in range(len(SEGMENTS)):
        prefix = f'fuel_tank_{weight}-lod{level}'
        meshes, nodes, kinds = [], [], set()
        for role, module, lift in (('base0', base(spec, level), 0), ('base0-end-n', end(spec, level), 0),
                                   ('base0-link-n', pipe(spec, level), 0), ('floor0', floor(spec, level), LEVEL),
                                   ('roof0', roof(spec, level), 2 * LEVEL)):
            mesh, node = module.mesh(f'{prefix}-{role}', lift)
            meshes.append(mesh)
            nodes.append(node)
            kinds |= set(module.kinds)
        levels[level] = {'materials': [m for m in MATERIALS if m['id'] in kinds], 'meshes': meshes, 'nodes': nodes}
    path = OUT / f'fuel_tank_{weight}.glb'
    write_glb(path, levels=levels)
    print('written', path, path.stat().st_size, 'bytes')


for name in sys.argv[1:] or WEIGHTS:
    kit(name)
