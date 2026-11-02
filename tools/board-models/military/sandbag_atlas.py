"""Makes data/models/board/textures/scenery/fortified-sandbag_{albedo,normal,orm,heightmap}.png and its .tres from two
photographic studies in sources/: the wall's face (sandbag-face.png, straight on, six courses between sky and ground)
and its top course seen from above (sandbag-top.png, two rows of bags).

Run: python tools/board-models/military/sandbag_atlas.py [<out folder>]
The face is tiled four bags long (a minimum-error cut through its overlap) and scaled to the wall's height; the top is
laid bag by bag from the study's own bags, both rows' joints on the face's top-course joints, its colour matched to the
face's top course. It prints the tile's length and each course's height and joints, build_sandbags.py's SPAN and
COURSES, which lay the emplacement's bags on the photographed ones. The photos keep their light and shade in the albedo,
as a scanned asset does; height, normal and occlusion come from their structure (bright bulges, dark joints). The atlas
is made at 2048 px and written at 512.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, grey_closing, map_coordinates
from scipy.signal import find_peaks

MM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MM / 'tools/materials'))
import seamless  # noqa: E402

STUDIES = Path(__file__).resolve().parent / 'sources'
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else MM / 'data/models/board/textures/scenery'
NAME = 'fortified-sandbag'
SIZE, FACE_ROWS, TOP_ROWS = 2048, 1152, 768
OUTPUT = 512  # the maps' width: made at SIZE, whose pixel-sized filters they keep, then averaged down
HEIGHT, DEPTH, TOP = 1.83, 1.25, 1.15  # the wall's height, the top view's width across it, the top's width
BAGS = 4  # the face's bags along a tile
RELIEF, NORMAL = 10.0, 2.0  # strong: most bags are flat faces whose shape is all relief (build_sandbags.py)


def linear(c):
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= .0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - .055)


def lum(rgb):
    return rgb @ np.array([.2126, .7152, .0722])


def resample(image, rows, cols, wrap):
    """image resampled to rows x cols, cubic, wrapping across its columns if {@code wrap}."""
    h, w = image.shape[:2]
    ys, xs = np.mgrid[0:rows, 0:cols].astype(float)
    ys = (ys + .5) * h / rows - .5
    xs = (xs + .5) * w / cols - .5
    channels = image[..., None] if image.ndim == 2 else image
    out = np.stack([map_coordinates(channels[..., c], [ys, xs], order=3,
                                    mode='grid-wrap' if wrap else 'nearest') for c in range(channels.shape[-1])], -1)
    return out[..., 0] if image.ndim == 2 else out


def joints(L, top, bottom, spacing, wrap=False):
    """The columns of the dark joints between bags across rows top..bottom; across the wrap if {@code wrap}."""
    profile = gaussian_filter(L[top:bottom].mean(0), 4, mode='wrap' if wrap else 'reflect')
    if not wrap:
        return find_peaks(-profile, distance=spacing * .7, prominence=.02)[0]
    w = len(profile)
    peaks = find_peaks(-np.tile(profile, 3), distance=spacing * .7, prominence=.02)[0]
    return np.sort(peaks[(peaks >= w) & (peaks < 2 * w)] - w)


def face():
    rgb = linear(np.asarray(Image.open(STUDIES / 'sandbag-face.png').convert('RGB'), float) / 255)
    h, w, _ = rgb.shape
    L = lum(rgb)
    # The band: sky above the top course's crests, smooth ground below the bottom course.
    detail = gaussian_filter(np.abs(L - gaussian_filter(L, 2)).mean(1), 3)
    rows = np.flatnonzero(detail > .5 * np.percentile(detail, 90))
    crest = np.array([np.argmax(np.abs(L[:rows[0] + 80, x] - L[:8, x].mean()) > .06) for x in range(w)])
    # The ground: just below the shadow line under the bottom course.
    top = int(np.percentile(crest, 5))
    ground = int(rows[-1] + np.argmin(L.mean(1)[rows[-1]:rows[-1] + 60])) + 3
    # Broad light across the wall flattened, its courses' own shading kept.
    broad = gaussian_filter(L[top:ground].mean(0), w / 10, mode='reflect')
    rgb = rgb * (broad.mean() / broad)[None, :, None] ** .8
    # The sky over the top course's dips: the bag below mirrored up, a little darker, as its rounded top turns away.
    for x in range(w):
        edge = max(crest[x], top)
        if edge > top:
            rgb[top:edge, x] = rgb[2 * edge - np.arange(top, edge), x] * .8
    L = lum(rgb)
    pitch = float(np.median(np.diff(joints(L, top, top + (ground - top) // 6, w / 6))))
    span = int(round(BAGS * pitch))
    margin = w - span
    # The tile width within a few pixels of four bags at which the strips across its seam match best.
    band = rgb[top:ground]
    # (Below the top course's dips: the sky filled over them is no match for anything.)
    below = band[crest.max() - top:]
    best = min(range(span - 12, min(span + 12, w - 60)),
               key=lambda s: np.mean((below[:, :w - s] - below[:, s:]) ** 2))
    span, margin = best, min(w - best, 120)
    stack = band[:, :span + margin]
    start, overflow = stack[:, :margin], stack[:, span:span + margin]
    cut = seamless._cut(((start - overflow) ** 2).sum(-1))
    mask = gaussian_filter((np.arange(margin)[None, :] >= cut[:, None]).astype(float), (0, 1.0))[..., None]
    tile = stack[:, :span].copy()
    tile[:, :margin] = mask * start + (1 - mask) * overflow
    metres = span / (ground - top) * HEIGHT
    # The courses: between the dark shadow lines across the tile, bottom first, each with its joints.
    L = lum(tile)
    rows = len(L)
    gaps = np.sort(find_peaks(-gaussian_filter(L.mean(1), 3), distance=rows / 6 * .7, prominence=.03)[0])
    edges = [rows] + [int(g) for g in gaps[::-1]] + [0]
    courses = []
    for bottom, top_row in zip(edges, edges[1:]):
        inset = (bottom - top_row) // 5
        found = joints(L, top_row + inset, bottom - inset, pitch, wrap=True) / span
        courses.append((round((rows - bottom) / rows * HEIGHT, 3), round((rows - top_row) / rows * HEIGHT, 3),
                        tuple(round(float(j), 4) for j in found)))
    print(f'face: rows {top}..{ground}, bag {pitch:.0f} px, tile {span} px = {metres:.3f} m')
    for course in courses:
        print('  course', course)
    # The top course's colour, for the top view's.
    shade = tile[:edges[-2]].reshape(-1, 3).mean(0)
    return resample(tile, FACE_ROWS, SIZE, True), metres, courses, shade


def top_view(face_joints, shade):
    rgb = linear(np.asarray(Image.open(STUDIES / 'sandbag-top.png').convert('RGB'), float) / 255)
    h, w, _ = rgb.shape
    L = lum(rgb)
    profile = gaussian_filter(L.mean(1), 3)
    # The rows: bright bands between the dark ground at the edges and the gap between them.
    bright = profile > .5 * (profile.max() + np.percentile(profile, 5))
    edges = np.flatnonzero(np.diff(bright.astype(int)))
    (a0, a1), (b0, b1) = (edges[0] + 1, edges[1] + 1), (edges[2] + 1, edges[3] + 1)
    gap = (a1 + b0) // 2
    out = np.zeros((TOP_ROWS, SIZE, 3))
    # Across: the top's width TOP centred in DEPTH; the inner row above the outer (PNG order, inner first).
    edge = (DEPTH - TOP) / 2 / DEPTH * TOP_ROWS
    half = (TOP_ROWS - 2 * edge) / 2
    ground = rgb[:max(a0 - 4, 1)].mean((0, 1))
    out[:] = ground
    for (r0, r1), (t0, t1) in (((a0 - 6, gap), (edge, edge + half)), ((gap, b1 + 6), (edge + half, edge + 2 * half))):
        r0, r1 = max(r0, 0), min(r1, h)
        source = rgb[r0:r1]
        # A bag is about twice as long as it is wide: closer dark lines are its creases.
        cuts = joints(lum(source), 0, r1 - r0, 2.1 * (r1 - r0))
        bags = [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
        # Lay them along the row: bag i between target joints i and i + 1, with an overlap feathered at the joint.
        targets = np.sort(face_joints % 1) * SIZE
        rows = int(round(t1)) - int(round(t0))
        row = np.zeros((rows, SIZE, 3))
        weight = np.zeros((rows, SIZE, 1))
        for i in range(BAGS):
            j0 = targets[i]
            j1 = targets[(i + 1) % BAGS] + (SIZE if i == BAGS - 1 else 0)
            s0, s1 = bags[i % len(bags)]
            pad = 24
            piece = source[:, max(s0 - pad, 0):min(s1 + pad, w)]
            flip = i >= len(bags)
            if flip:
                piece = piece[:, ::-1]
            length = int(round(j1 - j0)) + 2 * pad
            piece = resample(piece, rows, length, False)
            ramp = np.clip(np.minimum(np.arange(length) + 1, length - np.arange(length)) / pad, 0, 1)[None, :, None]
            cols = (int(round(j0)) - pad + np.arange(length)) % SIZE
            row[:, cols] += piece * ramp
            weight[:, cols] += ramp
        out[int(round(t0)):int(round(t0)) + rows] = row / np.maximum(weight, 1e-6)
    # The same fabric as the face's top course: the top photograph's colour and brightness matched to it.
    bags = out[int(round(edge)):int(round(edge + 2 * half))]
    out *= (shade / bags.reshape(-1, 3).mean(0))[None, None, :]
    print(f'top: rows {a0}..{a1} and {b0}..{b1}')
    return out


def relief(rgb, wrap_rows):
    """Height (0..1), normal (tangent space, green up) and occlusion from a photo's structure: the bags' bright bulges
    up, the dark joints between them down."""
    L = lum(rgb)
    mode = ('wrap' if wrap_rows else 'reflect', 'wrap')
    bulge = gaussian_filter(L, 4, mode=mode) - gaussian_filter(L, 60, mode=mode)
    seams = gaussian_filter(grey_closing(L, size=(15, 15), mode='wrap') - L, 1.5, mode=mode)
    height = bulge - 1.2 * seams
    lo, hi = np.percentile(height, [1, 99])
    height = np.clip((height - lo) / (hi - lo), 0, 1)
    smooth = gaussian_filter(height, 1.2, mode=mode)
    dx = np.gradient(smooth, axis=1)
    dy = np.gradient(smooth, axis=0)
    strength = 18
    n = np.stack([-dx * strength, dy * strength, np.ones_like(dx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    occlusion = np.clip(1 - 2.2 * seams / np.percentile(seams, 99), .35, 1)
    return height, n * .5 + .5, occlusion


def main():
    face_rgb, span, courses, shade = face()
    top_rgb = top_view(np.array(courses[-1][2]), shade)
    blank = np.zeros((SIZE - FACE_ROWS - TOP_ROWS, SIZE))
    maps = {}
    face_h, face_n, face_o = relief(face_rgb, False)
    top_h, top_n, top_o = relief(top_rgb, False)
    albedo = np.concatenate([face_rgb, top_rgb, np.zeros((blank.shape[0], SIZE, 3))], 0)
    height = np.concatenate([face_h, top_h, blank], 0)
    normal = np.concatenate([face_n, top_n, np.tile([.5, .5, 1], (blank.shape[0], SIZE, 1))], 0)
    occlusion = np.concatenate([face_o, top_o, np.ones_like(blank)], 0)
    maps['albedo'] = srgb(albedo)
    maps['normal'] = normal
    # The photos' shading is in the albedo already: the sky's occlusion only deepens the joints a little more.
    maps['orm'] = np.stack([.75 + .25 * occlusion, np.full_like(occlusion, .92), np.zeros_like(occlusion)], -1)
    maps['heightmap'] = np.repeat(height[..., None], 3, -1)
    # Each OUTPUT texel averages its block of SIZE texels; a normal averages its vectors and is unit again.
    block = SIZE // OUTPUT
    maps = {suffix: pixels.reshape(OUTPUT, block, OUTPUT, block, 3).mean((1, 3)) for suffix, pixels in maps.items()}
    vectors = maps['normal'] * 2 - 1
    maps['normal'] = vectors / np.linalg.norm(vectors, axis=-1, keepdims=True) * .5 + .5
    OUT.mkdir(parents=True, exist_ok=True)
    for suffix, pixels in maps.items():
        Image.fromarray((np.clip(pixels, 0, 1) * 255 + .5).astype(np.uint8)).save(OUT / f'{NAME}_{suffix}.png')
        print('WROTE', OUT / f'{NAME}_{suffix}.png')
    print(f'SPAN = {span:.3f}')
    print(f'COURSES = {courses}')
    (OUT / f'{NAME}.tres').write_text(f'''[gd_resource type="StandardMaterial3D" load_steps=5 format=2]
[ext_resource path="{NAME}_albedo.png" type="Texture" id=1]
[ext_resource path="{NAME}_orm.png" type="Texture" id=2]
[ext_resource path="{NAME}_normal.png" type="Texture" id=3]
[ext_resource path="{NAME}_heightmap.png" type="Texture" id=4]
[resource]
albedo_color = Color(1.0, 1.0, 1.0, 1.0)
albedo_texture = ExtResource( 1 )
metallic = 0.0
roughness = 1.0
roughness_texture = ExtResource( 2 )
roughness_texture_channel = 1
normal_enabled = true
normal_scale = {NORMAL}
normal_texture = ExtResource( 3 )
ao_enabled = true
ao_texture = ExtResource( 2 )
ao_texture_channel = 0
heightmap_enabled = true
heightmap_scale = {RELIEF}
heightmap_deep_parallax = true
heightmap_min_layers = 8
heightmap_max_layers = 32
heightmap_texture = ExtResource( 4 )
''', encoding='utf-8')


main()
