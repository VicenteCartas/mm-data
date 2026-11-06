"""Per-vertex concrete weathering for authored buildings: pure geometry, no Blender.

Rain streaks, broad patches, soot under ledges and splash at the ground, written into vertex colours, so stains
never repeat with the tile. Surfaces are cut along a regular grid of planes first, to give the stains vertices to live
on. A new vertex depends only on its edge and plane, so triangles meeting along an edge always agree and no crack opens.
"""
import math

STRIDE = 12  # position 3, normal 3, colour 4, uv 2


def _hash(i, j):
    n = (i*374761393+j*668265263) & 0x7fffffff
    n = ((n ^ (n >> 13))*1274126177) & 0x7fffffff
    return (n ^ (n >> 16))/0x7fffffff


def noise(u, v):
    i, j = math.floor(u), math.floor(v)
    fu, fv = u-i, v-j
    fu, fv = fu*fu*(3-2*fu), fv*fv*(3-2*fv)
    a, b = _hash(i, j), _hash(i+1, j)
    c, d = _hash(i, j+1), _hash(i+1, j+1)
    return (a+(b-a)*fu)*(1-fv)+(c+(d-c)*fu)*fv


def grime(u, z, top=None, foot=None, streak=3.6, amount=1):
    """Long vertical rain streaks, broad patches, soot under a ledge and splash at a foot."""
    w = 1-amount*(.42*noise(u/streak, z/120)**1.6+.18*noise(u/15+40, z/36))
    if top is not None:
        w -= amount*.16*math.exp(-max(0, top-z)/15)
    if foot is not None:
        w -= amount*.12*math.exp(-max(0, z-foot)/8)
    return max(.50, w)


def deck_grime(x, y, amount=1):
    """Flat faces collect broad stains rather than streaks."""
    return max(.50, 1-amount*(.24*noise(x/26+7, y/26)+.12*noise(x/7, y/7+13)))


def _cut(vertices, polygons, axis, at, points):
    """Convex polygons after a cut by the plane where the coordinate axis equals at. points keeps the vertices made so far."""
    result = []
    for polygon in polygons:
        sides = [vertices[i*STRIDE+axis]-at for i in polygon]
        if min(sides) > -.01 or max(sides) < .01:
            result.append(polygon)
            continue
        below, above = [], []
        for k, i in enumerate(polygon):
            j = polygon[(k+1) % len(polygon)]
            here, there = sides[k], sides[(k+1) % len(polygon)]
            if here < .01:
                below.append(i)
            if here > -.01:
                above.append(i)
            if (here < -.01 and there > .01) or (here > .01 and there < -.01):
                key = min(i, j), max(i, j), axis, at
                if key not in points:
                    a, b = key[0]*STRIDE, key[1]*STRIDE
                    t = (at-vertices[a+axis])/(vertices[b+axis]-vertices[a+axis])
                    values = [vertices[a+c]+(vertices[b+c]-vertices[a+c])*t for c in range(STRIDE)]
                    length = math.sqrt(sum(c*c for c in values[3:6])) or 1
                    values[3:6] = [c/length for c in values[3:6]]
                    points[key] = len(vertices)//STRIDE
                    vertices.extend(values)
                below.append(points[key])
                above.append(points[key])
        result += [below, above]
    return result


def average_weather(vertices, selected, amount, tint):
    """What weather_vertices darkens on average, for a level too far and too coarse to show stains. Parts here share no vertices."""
    multiplier = tint(1-.28*amount)
    for i in {i for part in selected for i in part}:
        for k in range(i*STRIDE+6, i*STRIDE+9):
            vertices[k] *= multiplier


def weather_vertices(vertices, selected, others, amount, ledges, tint, du=8., dv=64.):
    """Cuts and darkens the selected index lists of one mesh, in place.

    vertices: the mesh's flat vertex list. selected, others: its parts' index lists; a vertex also used by another
    finish is copied first. ledges: heights that shed soot onto the wall below them. tint: linear darkening to a
    multiplier for the stored colours. du, dv: the grid across and up a wall, in model units: narrow and tall, so that
    stains run down the wall. Flat faces take only broad patches, on a grid of 3 du. Exact rows just under each ledge
    and at the foot let soot and splash read as bands. A triangle no larger than the grid stays whole.
    """
    used_elsewhere = {i for part in others for i in part}
    copies = {}

    def own(i):
        if i not in used_elsewhere:
            return i
        if i not in copies:
            copies[i] = len(vertices)//STRIDE
            vertices.extend(vertices[i*STRIDE:(i+1)*STRIDE])
        return copies[i]

    cuts = sorted({10}|{h-16 for h in ledges if h > 16})
    points = {}
    touched = set()
    for part in selected:
        done = []
        for k in range(0, len(part), 3):
            triangle = own(part[k]), own(part[k+1]), own(part[k+2])
            flat = all(abs(vertices[i*STRIDE+5]) > .7 for i in triangle)
            pieces = [list(triangle)]
            for axis in (0, 1):
                step = 3*du if flat else du
                low, high = sorted((min(vertices[i*STRIDE+axis] for i in triangle), max(vertices[i*STRIDE+axis] for i in triangle)))
                if high-low > step:
                    for n in range(math.ceil(low/step), math.floor(high/step)+1):
                        pieces = _cut(vertices, pieces, axis, n*step, points)
            if not flat:
                low, high = min(vertices[i*STRIDE+2] for i in triangle), max(vertices[i*STRIDE+2] for i in triangle)
                heights = {h for h in cuts if high-low > 24 and low < h < high}
                if high-low > dv:
                    heights.update(n*dv for n in range(math.ceil(low/dv), math.floor(high/dv)+1))
                for h in sorted(heights):
                    pieces = _cut(vertices, pieces, 2, h, points)
            done += [i for piece in pieces for n in range(1, len(piece)-1) for i in (piece[0], piece[n], piece[n+1])]
        part[:] = done
        touched.update(done)
    for i in touched:
        at = i*STRIDE
        x, y, z = vertices[at:at+3]
        if abs(vertices[at+5]) > .7:
            w = deck_grime(x, y, amount)
        else:
            top = min((h for h in ledges if h >= z), default=None)
            w = grime(x+1.37*y, z, top, 0, .75*du, amount)
        multiplier = tint(w)
        for k in range(6, 9):
            vertices[at+k] *= multiplier
