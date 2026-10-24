"""Make aligned fields tile without a seam, all of them by the same operation (needs numpy and scipy).

seamless(stack, weights): stack is H x W x C floats (every map or source field of one material, aligned); weights
gives each channel's say in where the cut runs. Each axis in turn, the texture and a copy rolled by half a tile: their
broad component (a wrapped Gaussian) cross-fades from the copy at the tile's edges to the texture in its middle, and
their fine grain switches from one to the other along a minimum-error cut, so stones and grit stay whole instead of
ghosting. Neither the texture's edges nor the copy's (which lie in the tile's middle) survive, so whatever seam or
edge ramp the texture had goes with them.
"""
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _cut(cost, starts=32):
    """A path down cost (rows x columns), one column a row and at most one column of change a row, of minimum total
    cost, closing on itself across the wrap (its last row within one column of its first)."""
    rows, cols = cost.shape
    best, best_path = np.inf, None
    for start in np.unique(np.linspace(0, cols - 1, starts).round().astype(int)):
        total = np.full(cols, np.inf)
        total[start] = cost[0, start]
        back = np.zeros((rows, cols), np.int64)
        for row in range(1, rows):
            choice = np.stack([np.concatenate([[np.inf], total[:-1]]), total, np.concatenate([total[1:], [np.inf]])])
            pick = choice.argmin(0)
            back[row] = np.arange(cols) + pick - 1
            total = choice[pick, np.arange(cols)] + cost[row]
        closing = np.full(cols, np.inf)
        lo, hi = max(start - 1, 0), min(start + 1, cols - 1)
        closing[lo:hi + 1] = total[lo:hi + 1]
        end = int(closing.argmin())
        if closing[end] < best:
            best = closing[end]
            best_path = np.empty(rows, np.int64)
            best_path[-1] = end
            for row in range(rows - 1, 0, -1):
                best_path[row - 1] = back[row, best_path[row]]
    return best_path


def _across(stack, weights, broad=24.0, band=96, feather=1.5):
    height, width, channels = stack.shape
    rolled = np.roll(stack, width // 2, axis=1)
    low = np.stack([gaussian_filter(stack[..., c], broad, mode='wrap') for c in range(channels)], -1)
    low_rolled = np.roll(low, width // 2, axis=1)
    fine, fine_rolled = stack - low, rolled - low_rolled
    x = np.arange(width)
    share = _smoothstep(.1, .85, np.minimum(x, width - 1 - x) / (width / 2))[None, :, None]
    difference = ((fine - fine_rolled) ** 2 * weights).sum(-1) + .25 * ((low - low_rolled) ** 2 * weights).sum(-1)
    cuts = []
    for middle in (width // 4, 3 * width // 4):
        cuts.append(_cut(difference[:, middle - band:middle + band]) + middle - band)
    mask = np.zeros((height, width))
    for row in range(height):
        mask[row, cuts[0][row]:cuts[1][row]] = 1
    mask = gaussian_filter1d(mask, feather, axis=1, mode='wrap')[..., None]
    return share * low + (1 - share) * low_rolled + mask * fine + (1 - mask) * fine_rolled


def seamless(stack, weights):
    out = _across(stack, weights)
    return np.transpose(_across(np.transpose(out, (1, 0, 2)), weights), (1, 0, 2))


def wrap_report(image):
    """How much crossing the tile's edges changes it, against an ordinary step between neighbouring texels."""
    a = np.asarray(image, float)
    if a.ndim == 2:
        a = a[..., None]
    inner = (np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean()) / 2
    edge = (np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0] - a[-1]).mean()) / 2
    return edge, inner
