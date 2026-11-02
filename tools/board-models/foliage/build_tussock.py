"""python tools/board-models/foliage/build_tussock.py: foliage-tussock.glb and its manifest entry, a tundra grass
tussock for the foliage (tree) pass. Crossed full-width cards of the tundra-tussock cutout stand through the root, each
slightly tilted and bowed so the clump has volume, its blades fountaining out of a dense base as the photograph shows
them; a low skirt around the base, its edge on the ground, carries the clump seen from above, so the top view is full
and from the side it reads as the drooping outer blades, never as a lid. Every face has its back. LOD0-2 here; then
refresh LOD3 (the impostor) with Blender: tools/prepare_tree_lods.py -- impostors foliage-tussock. Roots at Z=0,
LOD0 18 units tall, as the understory plants.
"""
import json
import math
import random
import sys
from pathlib import Path

MM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MM / 'tools'))
from glb_geometry import write_glb  # noqa: E402

NAME = 'foliage-tussock'
HEIGHT = 18.0
# The side view's half-width over its height: the photographed clump is 1.64 times as wide as tall.
RADIUS = HEIGHT * 1.64 / 2
# The atlas (sources/tundra-tussock.png): the side view across the top, its base at SIDE_BASE, and the clump seen
# from above in the square below it, centred at TOP_CENTRE with radius TOP_RADIUS (UV units).
SIDE_BASE = 624 / 1024
TOP_CENTRE, TOP_RADIUS = (192 / 1024, 832 / 1024), 184 / 1024
MATERIAL = {'id': 'canopy-cutout', 'diffuse': [1, 1, 1], 'roughness': 1, 'alphaTest': .5,
            'textures': [{'id': 'tussock', 'type': 'DIFFUSE', 'filename': '../textures/vegetation/tundra-tussock_albedo.png',
                          'wrapS': 33071, 'wrapT': 33071}]}


def level(cards, rows, cols, segments, seed):
    rng = random.Random(seed)
    vertices, indices = [], []

    def vertex(p, n, uv, shade):
        vertices.extend([*p, *n, shade, shade, shade, 1.0, *uv])
        return len(vertices) // 12 - 1

    def surface(grid, normal_of):
        """Both faces of a grid of (point, uv, shade) rows."""
        for face in (1, -1):
            ids = [[vertex(p, [c * face for c in normal_of(p)], uv, shade) for p, uv, shade in line] for line in grid]
            for row in range(len(grid) - 1):
                for col in range(len(grid[0]) - 1):
                    a, b = ids[row][col], ids[row][col + 1]
                    c, d = ids[row + 1][col + 1], ids[row + 1][col]
                    indices.extend([a, b, c, a, c, d] if face == 1 else [a, c, b, a, d, c])

    turn = rng.uniform(0, math.pi)
    for k in range(cards):
        az = turn + math.pi * (k + rng.uniform(-.2, .2)) / cards
        across = (math.cos(az), math.sin(az))
        facing = (-across[1], across[0])
        width, tall = RADIUS * rng.uniform(.88, 1.04), HEIGHT * rng.uniform(.84, 1.0)
        tilt = math.radians(rng.uniform(-9, 9))
        bow = rng.choice((-1, 1)) * RADIUS * .16
        grid = []
        for row in range(rows):
            t = row / (rows - 1)
            line = []
            for col in range(cols):
                s = col / (cols - 1) * 2 - 1
                # Bowed across, so the card's sides curl around the clump, and tilted a little about its base.
                out = bow * (s * s) + tall * t * math.sin(tilt)
                p = (across[0] * s * width + facing[0] * out, across[1] * s * width + facing[1] * out,
                     tall * t * math.cos(tilt))
                line.append((p, (.5 + .5 * s, SIDE_BASE * (1 - t)), .8 + .2 * t))
            grid.append(line)
        surface(grid, lambda p: (facing[0] * .55, facing[1] * .55, .83))
    # The skirt: the clump from above, a low cone from inside the base out to the ground at the blades' reach.
    rings = ((0, .3, 0), (.45, .2, .5), (.95, .03, 1.0))
    centre = (0, 0, HEIGHT * rings[0][1])
    grid = []
    for reach, height, texture in rings[1:]:
        line = []
        for i in range(segments + 1):
            a = 2 * math.pi * i / segments
            p = (RADIUS * reach * math.cos(a), RADIUS * reach * math.sin(a), HEIGHT * height)
            uv = (TOP_CENTRE[0] + TOP_RADIUS * texture * math.cos(a), TOP_CENTRE[1] + TOP_RADIUS * texture * math.sin(a))
            line.append((p, uv, .9 if reach < .5 else .8))
        grid.append(line)
    surface(grid, lambda p: (p[0] / RADIUS * .3, p[1] / RADIUS * .3, .95))
    for face in (1, -1):
        middle = vertex(centre, (0, 0, face), TOP_CENTRE, .9)
        inner = [vertex(p, (0, 0, face), uv, shade) for p, uv, shade in grid[0]]
        for i in range(segments):
            a, b = inner[i], inner[i + 1]
            indices.extend([middle, a, b] if face == 1 else [middle, b, a])
    return {'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': vertices,
                        'parts': [{'id': 'tussock', 'type': 'TRIANGLES', 'indices': indices}]}],
            'nodes': [{'id': NAME, 'parts': [{'meshpartid': 'tussock', 'materialid': 'canopy-cutout'}]}],
            'materials': [MATERIAL]}


levels = {0: level(7, 4, 5, 12, 1), 1: level(5, 3, 3, 8, 1), 2: level(3, 2, 2, 6, 1)}
path = MM / 'data/models/board/vegetation' / f'{NAME}.glb'
write_glb(path, levels=levels)
counts = [{'node': f'{NAME}-lod{i}', 'triangles': len(m['meshes'][0]['parts'][0]['indices']) // 3,
           'vertices': len(m['meshes'][0]['vertices']) // 12} for i, m in sorted(levels.items())]
print(path, counts)
manifest_path = MM / 'tools/board-models/manifest.json'
raw = manifest_path.read_text()
manifest = json.loads(raw)
manifest[f'vegetation/{NAME}'] = {'mesh': f'vegetation/{NAME}.glb', 'triangles': counts[0]['triangles'], 'vertices': counts[0]['vertices'],
                  'texture': 'textures/vegetation/tundra-tussock_albedo.png', 'lods': counts}
assert json.dumps(json.loads(raw), indent=2) + '\n' == raw, 'manifest layout changed'
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
print('manifest entry written')
