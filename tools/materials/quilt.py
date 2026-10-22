"""A larger tile from a seamless one, by image quilting on a torus (needs numpy and scipy).

quilt(stack, weights, size): stack is H x W x C floats, a square texture that already tiles (every map or source field
of one material, aligned); the result is size x size and tiles too. It is a grid of overlapping blocks, each a window
of the texture (any offset, wrapping, in any of its eight rotations and mirror images, so the material must have no
direction of its own, such as baked light), chosen among those that best match what is already placed where they
overlap, preferring parts of the texture used least so far; a block replaces what lies beyond a minimum-error cut
through each overlap, so grains stay whole. The last blocks overlap the first, so the result wraps. weights gives
each channel's say in the matching and the cuts; every channel moves together.
"""
import numpy as np
from scipy import fft
from scipy.ndimage import gaussian_filter


def _dihedral(a, v):
    """The v-th (0..7) rotation or mirror image of a square array's first two axes."""
    return np.rot90(a[:, ::-1] if v >= 4 else a, v % 4)


def _source(v, y, x, side):
    """The texel of the texture itself that _dihedral(texture, v) shows at (y, x)."""
    n = side - 1
    p, q = [(y, x), (x, n - y), (n - y, n - x), (n - x, y)][v % 4]
    return np.array([p, n - q if v >= 4 else q])


def _crowding(points, places, side, spread):
    """For each point of the texture, how near the blocks already placed came from it, across the wrap."""
    if not places:
        return np.zeros(len(points))
    d = np.abs(points[:, None, :] - np.asarray(places)[None, :, :])
    d = np.minimum(d, side - d)
    return np.exp(-(d ** 2).sum(-1) / (2 * spread ** 2)).sum(1)


def _cut(cost):
    """A path down cost (rows x columns), one column a row and at most one column of change a row, of minimum total."""
    rows, cols = cost.shape
    total = cost[0].copy()
    back = np.zeros((rows, cols), np.int64)
    for row in range(1, rows):
        choice = np.stack([np.concatenate([[np.inf], total[:-1]]), total, np.concatenate([total[1:], [np.inf]])])
        pick = choice.argmin(0)
        back[row] = np.arange(cols) + pick - 1
        total = choice[pick, np.arange(cols)] + cost[row]
    path = np.empty(rows, np.int64)
    path[-1] = int(total.argmin())
    for row in range(rows - 1, 0, -1):
        path[row - 1] = back[row, path[row]]
    return path


def quilt(stack, weights, size, block=176, overlap=48, tolerance=.08, reuse=.6, seed=1, progress=None):
    side = stack.shape[0]
    step = block - overlap
    if stack.shape[1] != side or size % step:
        raise ValueError(f'a square texture, and a size that is a multiple of {step}')
    weights = np.asarray(weights, float)
    matched = [c for c in range(stack.shape[2]) if weights[c] > 0]
    variants = [np.ascontiguousarray(_dihedral(stack, v)) for v in range(8)]
    # A window's mismatch at every offset at once, as correlations over the torus:
    # sum over the overlap M of (S - T)^2 = corr(S^2, M) - 2 corr(S, M T) + const.
    spectra = [{c: fft.rfft2(v[..., c], workers=-1) for c in matched} for v in variants]
    squares = [fft.rfft2(sum(weights[c] * v[..., c] ** 2 for c in matched), workers=-1) for v in variants]
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size, stack.shape[2]))
    filled = np.zeros((size, size), bool)
    places = []
    blocks = size // step
    for i in range(blocks):
        for j in range(blocks):
            rows = (np.arange(block) + i * step) % size
            cols = (np.arange(block) + j * step) % size
            target = out[np.ix_(rows, cols)]
            known = filled[np.ix_(rows, cols)]
            if known.any():
                kernel = np.zeros((side, side))
                kernel[:block, :block] = known
                k_known = np.conj(fft.rfft2(kernel, workers=-1))
                k_target = {}
                for c in matched:
                    kernel[:block, :block] = known * target[..., c]
                    k_target[c] = np.conj(fft.rfft2(kernel, workers=-1))
                costs = np.maximum(np.stack([fft.irfft2(squares[v] * k_known - 2 * sum(
                      weights[c] * spectra[v][c] * k_target[c] for c in matched), s=(side, side), workers=-1)
                      for v in range(8)]), 0)
                best = costs.min()
                candidates = np.argwhere(costs <= best * (1 + tolerance) + 1e-9)
            else:
                costs, best = None, 0.0
                candidates = np.stack([rng.integers(0, 8, 400), rng.integers(0, side, 400),
                                       rng.integers(0, side, 400)], 1)
            if len(candidates) > 400:
                candidates = candidates[rng.choice(len(candidates), 400, replace=False)]
            centres = np.array([_source(v, (y + block // 2) % side, (x + block // 2) % side, side)
                                for v, y, x in candidates])
            score = reuse * _crowding(centres, places, side, block / 2) + rng.random(len(candidates)) * .02
            if costs is not None:
                score += costs[tuple(candidates.T)] / (best + 1e-9)
            v, y, x = candidates[int(np.argmin(score))]
            window = np.take(np.take(variants[v], (np.arange(block) + y) % side, 0), (np.arange(block) + x) % side, 1)
            # The block replaces what is there beyond a cut through each side whose strip is already placed.
            error = (((window - target) ** 2) * weights).sum(-1)
            take = np.ones((block, block))
            if known[:, :overlap].all():
                for r, c in enumerate(_cut(error[:, :overlap])): take[r, :c] = 0
            if known[:, -overlap:].all():
                for r, c in enumerate(_cut(error[:, -overlap:])): take[r, block - overlap + c + 1:] = 0
            if known[:overlap].all():
                for c, r in enumerate(_cut(error[:overlap].T)): take[:r, c] = 0
            if known[-overlap:].all():
                for c, r in enumerate(_cut(error[-overlap:].T)): take[block - overlap + r + 1:, c] = 0
            take = np.where(known, gaussian_filter(take, 1.0), 1.0)[..., None]
            out[np.ix_(rows, cols)] = take * window + (1 - take) * target
            filled[np.ix_(rows, cols)] = True
            places.append(_source(v, (y + block // 2) % side, (x + block // 2) % side, side))
        if progress:
            progress(i + 1, blocks)
    return out
