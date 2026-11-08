"""Far levels of authored buildings: pure geometry, no Blender.

A far level only draws while a building, or five hexes of a giant, is a few dozen pixels wide (TreeLod.PROPS), so nothing
smaller than a pixel needs to survive. Each connected piece merges with itself alone on a grid: its vertices sharing a cell become the
one with the most surface around it, so a piece stays on its own surface and never moves further than a cell. On upright
pieces plan and height merge apart, so walls stay upright and floors level. A piece too thin to cover a pixel goes and
leaves its colour on the surface around it, so that a far level keeps the overall look: dark seat rows darken the bowl.
"""
import numpy as np

STRIDE = 12  # position 3, normal 3, colour 4, uv 2
# The building's larger side on screen, in pixels, below which each level draws: TreeLod.PROPS.
LEVEL_PIXELS = {1: 80, 2: 24}
# The merge grid, in those pixels.
CELL_PIXELS = 1.5
# Its largest cell, in model units (a hex is 83): a giant's levels switch at five hexes of its side (TreeLod.PROPS_SIDE), and
# its surfaces are made of parts small against a hex, not against its whole side.
MAX_CELL = {1: 12, 2: 32}
# Windows and lamps merge on a finer grid and never go: at night they are all that reads of a far building.
LIT_CELL = .25
# A piece narrower than this many cells across its second largest side goes altogether.
THIN_CELLS = .5


def lathe(stations, segments, at):
    """A round building's plain far shape: one (vertices, faces, finish) for each step between stations.

    stations: (radius, height, finish of the step ending there), walked from the foot in to the centre so that every face
    looks out and up; a last radius of 0 closes it with one flat face. at(angle) gives the outline's point at radius 1.
    """
    outline = [at(i*2*np.pi/segments) for i in range(segments)]
    result = []
    for (r0, z0, _), (r1, z1, finish) in zip(stations, stations[1:]):
        ring = [(r0*x, r0*y, z0) for x, y in outline]
        if r1:
            quads = [(i, (i+1) % segments, (i+1) % segments+segments, i+segments) for i in range(segments)]
            result.append((ring+[(r1*x, r1*y, z1) for x, y in outline], quads, finish))
        else:
            result.append((ring, [tuple(range(segments))], finish))
    return result


def is_lit(material):
    """Whether a material id belongs to a window or a lamp."""
    return '#emission' in material or 'glass' in material or 'dome-window' in material


def connected_pieces(points, triangles):
    """The connected piece of each point; points at one position are one vertex."""
    _, welded = np.unique(np.round(points, 3), axis=0, return_inverse=True)
    welded = welded.ravel()
    parent = list(range(welded.max()+1))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in welded[triangles].tolist():
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    return np.fromiter((find(i) for i in welded.tolist()), np.int64, len(welded))


def _heaviest(keys, values, weights):
    """Each row's value replaced by that of the heaviest row with the same key."""
    _, groups = np.unique(keys, axis=0, return_inverse=True)
    groups = groups.ravel()
    order = np.lexsort((weights, groups))
    sorted_groups = groups[order]
    last = np.r_[sorted_groups[1:] != sorted_groups[:-1], True]
    return values[order[last]][groups]


def _bounds(points, pieces):
    """The lowest and highest corner of each point's piece."""
    ids, inverse = np.unique(pieces, return_inverse=True)
    inverse = inverse.ravel()
    low, high = np.full((len(ids), 3), np.inf), np.full((len(ids), 3), -np.inf)
    np.minimum.at(low, inverse, points)
    np.maximum.at(high, inverse, points)
    return low[inverse], high[inverse]


def _cells(vertices, pieces, weights, size, sheets):
    """Each vertex's cell within its piece, and its merged position.

    With sheets, a piece thinner than a cell across the plan keeps both its faces: merged into one plane it could land behind
    the wall it lay on, which is how a dark channel on a tower's side once vanished.
    """
    points = vertices[:, :3]
    grid = np.column_stack((pieces, np.floor(points/size).astype(np.int64)))
    if sheets:
        low, high = _bounds(points, pieces)
        across = (high-low)[:, :2]
        faces = np.round((points[:, :2]-low[:, :2])/np.where(across > 0, across, 1)).astype(np.int64)
        grid[:, 1:3] = np.where(across < size, faces, grid[:, 1:3])
    _, cells = np.unique(grid, axis=0, return_inverse=True)
    # Heights merge to the top of their band: a thin overlay flattens onto its visible face, not under what it lay on.
    upright = np.column_stack((_heaviest(grid[:, :3], points[:, :2], weights), _heaviest(grid[:, [0, 3]], points[:, 2:], points[:, 2])))
    # A piece with much surface that is neither wall nor deck, like a dish, would leave its surface that way.
    _, inverse = np.unique(pieces, return_inverse=True)
    inverse = inverse.ravel()
    slant = (np.abs(vertices[:, 5]) > .1)&(np.abs(vertices[:, 5]) < .95)
    slanted = np.bincount(inverse, weights*slant)/np.bincount(inverse, weights) > .3
    return cells.ravel(), np.where(slanted[inverse, None], _heaviest(grid, points, weights), upright)


def _thin(points, pieces, size):
    """Whether each point's piece is too thin to keep."""
    low, high = _bounds(points, pieces)
    return np.sort(high-low, axis=1)[:, 1] < size


def _going(data, triangles):
    """Triangles that go, as (centre, area, colour, normal)."""
    a, b, c = (data[triangles[:, i]] for i in range(3))
    cross = np.cross(b[:, :3]-a[:, :3], c[:, :3]-a[:, :3])
    double = np.linalg.norm(cross, axis=1)
    return zip((a[:, :3]+b[:, :3]+c[:, :3])/3, (double/2).tolist(), (a[:, 6:9]+b[:, 6:9]+c[:, 6:9])/3,
               cross/np.where(double > 0, double, 1)[:, None])


def _leave_colour(kept, gone, size):
    """Mixes each gone triangle's colour into the nearest vertex within a cell that stays, by surface.

    kept: (vertices whose colours change in place, surface weights, whether each vertex stays). gone: _going's triangles.
    Only a surface facing the same way, with the triangle in front of it, was covered by it: a hidden soffit leaves nothing
    on the roof above. Windows and lamps take none of it.
    """
    grid = {}
    for k, (data, _, stays) in enumerate(kept):
        for i in np.flatnonzero(stays).tolist():
            grid.setdefault(tuple(np.floor(data[i, :3]/size).astype(np.int64).tolist()), []).append((k, i))
    extra = [np.zeros((len(data), 3)) for data, _, _ in kept]
    surface = [np.zeros(len(data)) for data, _, _ in kept]
    around = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)]
    for centre, area, colour, normal in gone:
        x, y, z = np.floor(centre/size).astype(np.int64).tolist()
        best, nearest = None, size*size
        for dx, dy, dz in around:
            for k, i in grid.get((x+dx, y+dy, z+dz), ()):
                vertex = kept[k][0][i]
                offset = centre-vertex[:3]
                if vertex[3:6]@normal > .5 and offset@vertex[3:6] > -.25*size:
                    distance = float(offset@offset)
                    if distance < nearest:
                        best, nearest = (k, i), distance
        if best:
            extra[best[0]][best[1]] += area*colour
            surface[best[0]][best[1]] += area
    for (data, weights, _), added, more in zip(kept, extra, surface):
        # What went sat on this surface and covered it, by the share of its area: half of a closed thin part faces out.
        # A vertex's weight holds the whole doubled area of each triangle around it: a sixth of that is its own surface.
        cover = np.minimum(1, more/2/(weights/6))[:, None]
        left = np.flatnonzero(more)
        data[left, 6:9] = data[left, 6:9]*(1-cover[left])+added[left]/more[left, None]*cover[left]


def _outer_faces(triangles, corners, positions, centre):
    """Which triangles to keep where a window collapsed into a sheet: only the side looking away from the building."""
    a, b, c = (positions[triangles[:, i]] for i in range(3))
    normals = np.cross(b-a, c-a)
    middle = (a+b+c)/3-centre
    scores = normals[:, 0]*middle[:, 0]+normals[:, 1]*middle[:, 1]+normals[:, 2]*abs(middle).max()
    best = {}
    for i, key in enumerate(map(tuple, np.sort(corners, axis=1).tolist())):
        if key not in best or scores[i] > scores[best[key]]:
            best[key] = i
    return sorted(best.values())


def simplify(modules, level, lit):
    """One model's modules [(name, flat vertices, {key: flat indices})] at a far level, and its grid cell.

    lit(key) tells windows and lamps. A module left empty is dropped.
    """
    arrays = [np.asarray(vertices, dtype=np.float64).reshape(-1, STRIDE) for _, vertices, _ in modules]
    every = np.concatenate([a[:, :3] for a in arrays])
    extent = every.max(axis=0)-every.min(axis=0)
    cell = min(max(extent[0], extent[1])/LEVEL_PIXELS[level]*CELL_PIXELS, MAX_CELL[level])
    centre = (every.max(axis=0)+every.min(axis=0))/2
    offsets = np.cumsum([0]+[len(a) for a in arrays])
    connected = connected_pieces(every, np.concatenate([np.asarray(indices, dtype=np.int64).reshape(-1, 3)+offsets[m]
                                               for m, (_, _, parts) in enumerate(modules) for indices in parts.values()]))
    thin = _thin(every, connected, cell*THIN_CELLS)

    # Each part's own copy of its vertices, weighted by the surface around them, on the grid of its kind.
    pieces, gone = [], []
    for m, (_, _, parts) in enumerate(modules):
        for key, indices in parts.items():
            used, inverse = np.unique(np.asarray(indices, dtype=np.int64), return_inverse=True)
            triangles = inverse.reshape(-1, 3)
            kind = bool(lit(key))
            data = arrays[m][used].copy()
            if not kind:
                dropped = thin[used+offsets[m]][triangles[:, 0]]
                gone.extend(_going(data, triangles[dropped]))
                triangles = triangles[~dropped]
            if not len(triangles):
                continue
            a, b, c = (data[triangles[:, i], :3] for i in range(3))
            original = np.cross(b-a, c-a)
            area = np.linalg.norm(original, axis=1)
            weights = np.full(len(used), 1e-6)
            for i in range(3):
                np.add.at(weights, triangles[:, i], area)
            pieces.append((m, key, data, triangles, original, weights, kind, connected[used+offsets[m]]))
    grids = {}
    for kind, size in ((False, cell), (True, cell*LIT_CELL)):
        chosen = [p for p in pieces if p[6] == kind]
        if chosen:
            # A window's sheet keeps its outer side alone (_outer_faces).
            grids[kind] = [*_cells(np.concatenate([p[2] for p in chosen]), np.concatenate([p[7] for p in chosen]),
                                   np.concatenate([p[5] for p in chosen]), size, not kind), 0]

    # What survives the merge is known before any colour mixes, so that what goes can leave its colour on what stays.
    merging, kept = [], []
    for m, key, data, triangles, original, weights, kind, _ in pieces:
        grid = grids[kind]
        cells, positions = grid[0][grid[2]:grid[2]+len(data)], grid[1][grid[2]:grid[2]+len(data)]
        grid[2] += len(data)
        corners = cells[triangles]
        a, b, c = (positions[triangles[:, i]] for i in range(3))
        # A triangle that turned over on the way would show its inside.
        whole = ((corners[:, 0] != corners[:, 1])&(corners[:, 1] != corners[:, 2])&(corners[:, 2] != corners[:, 0])
                 &(np.sum(np.cross(b-a, c-a)*original, axis=1) > 0))
        if not kind:
            gone.extend(_going(data, triangles[~whole]))
            stays = np.zeros(len(data), dtype=bool)
            stays[triangles[whole].ravel()] = True
            kept.append((data, weights, stays))
        if whole.any():
            merging.append((m, key, data, triangles[whole], corners[whole], cells, positions, weights, kind))
    _leave_colour(kept, gone, cell)

    result = [(name, [], {}) for name, _, _ in modules]
    for m, key, data, triangles, corners, cells, positions, weights, kind in merging:
        # Vertices of a cell stay apart only across a hard edge.
        _, groups = np.unique(np.column_stack((cells, np.round(data[:, 3:6]*2).astype(np.int64))), axis=0, return_inverse=True)
        groups = groups.ravel()
        merged = np.zeros((groups.max()+1, STRIDE))
        total = np.zeros(len(merged))
        np.add.at(merged, groups, data*weights[:, None])
        np.add.at(total, groups, weights)
        merged /= total[:, None]
        merged[groups, :3] = positions
        length = np.linalg.norm(merged[:, 3:6], axis=1, keepdims=True)
        merged[:, 3:6] /= np.where(length > 0, length, 1)

        new = groups[triangles]
        # The same triangle twice, through merging: once is enough. Rotated so that the smallest index comes first.
        turn = np.argmin(new, axis=1)
        rows = np.arange(len(new))
        new = np.column_stack((new[rows, turn], new[rows, (turn+1) % 3], new[rows, (turn+2) % 3]))
        new, first = np.unique(new, axis=0, return_index=True)
        if kind:
            new = new[_outer_faces(new, corners[first], merged[:, :3], centre)]
        used, inverse = np.unique(new, return_inverse=True)
        _, vertices, parts = result[m]
        offset = len(vertices)//STRIDE
        vertices.extend(merged[used].ravel().tolist())
        parts[key] = (inverse.ravel()+offset).tolist()
    return [module for module in result if module[2]], cell
