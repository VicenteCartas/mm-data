"""Validate the board GLBs against their manifests after direct edits: LOD nodes, budgets and texture files."""
from glb_geometry import read_glb
from io import BytesIO
from pathlib import Path
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'data/models/board'
# The board models' budgets, levels and sources: tool data, never shipped.
MANIFESTS = ROOT / 'tools/board-models'
features = json.loads((MANIFESTS / 'manifest.json').read_text())
catalog = dict(features)

lods = {}
for asset, entry in features.items():
    if 'lods' in entry:
        # Three mesh levels and the impostor; a winter variant (`"variant": "snow"`) reads its bare species' file.
        # Entries are keyed by the model's path; its level groups by its own name.
        name = asset.rsplit('/', 1)[-1]
        assert [lod['node'] for lod in entry['lods']] == [f'{name}-lod{level}' for level in range(4)], asset
        # The alien plants (Mars corals, fungal colonies) may use twice the near budgets.
        if asset.startswith('vegetation/orchard-'):
            budgets = (34000, 10000, 3200, 12)
        elif asset.startswith('vegetation/cactus'):
            budgets = (3600, 950, 420, 12)
        elif asset.startswith('vegetation/tree-dead'):
            budgets = (12000, 1800, 180, 12)
        elif entry.get('source') == 'tools/board-models/foliage/build_forest.py':
            budgets = (32000, 10000, 2600, 12)
        elif entry.get('source') == 'tools/board-models/foliage/build_shrubs.py':
            budgets = (24000, 8000, 2200, 12)
        else:
            budgets = (3200, 820, 110, 12) if asset.startswith(('mars/', 'fungus/')) else (1600, 410, 110, 12)
        for level, lod in enumerate(entry['lods']):
            assert 0 < lod['triangles'] <= budgets[level], lod
            catalog[lod['node']] = lod
            lods[lod['node']] = (BOARD / entry['mesh'], level)
maximum = 0
# Placement fits a plant's LOD0 height and every level shares that transform: a coarser level stays within it.
tops = {}
assert not list(BOARD.rglob('*.g3dj')), 'All deployed board meshes must use GLB'
for asset in catalog:
    if asset in features and 'lods' in features[asset]:
        # A plant is checked level by level; a source plant's own count is its source's full count.
        continue
    if asset in lods:
        path, level = lods[asset]
        model = read_glb(path, level)
    else:
        path = BOARD / (asset + '.glb')
        model = read_glb(path)
    heights = [z for mesh in model['meshes'] for z in mesh['vertices'][2::12]]
    if asset.startswith(('foliage-', 'orchard-')):
        plant = asset.rsplit('-lod', 1)[0]
        assert abs(min(heights)) < 1e-5, f'Floating plant root: {path}'
        if level == 0:
            low, high = (17, 18.1) if asset.startswith('foliage-') else (29, 31)
            assert low < max(heights) < high, f'Plant height: {path}'
            tops[plant] = max(heights)
        else:
            assert .9 * tops[plant] < max(heights) < 1.01 * tops[plant], f'LOD {level} height: {path}'
    triangles = 0
    for mesh in model['meshes']:
        assert mesh['attributes'] == ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], path
        vertices = mesh['vertices']
        assert len(vertices) % 12 == 0, path
        for part in mesh['parts']:
            indices = part['indices']
            assert len(indices) % 3 == 0, path
            assert all(0 <= index < len(vertices) // 12 for index in indices), path
            triangles += len(indices) // 3
    # Plant levels keep their own budgets (above); every other model stays within 500 triangles.
    assert 0 < triangles and (asset in lods or triangles <= 500), (path, triangles)
    assert triangles == catalog[asset]['triangles'], (asset, path)
    maximum = max(maximum, triangles)
    for material in model['materials']:
        for texture in material.get('textures', []):
            if 'data' in texture:
                assert Image.open(BytesIO(texture['data'])).format in ('PNG', 'JPEG'), path
                continue
            dependency = (path.parent / texture['filename']).resolve()
            assert dependency.is_relative_to(BOARD.resolve()), dependency
            assert dependency.is_file(), dependency

print(json.dumps({'features': len(features), 'plant_lods': len(lods),
                  'max_triangles': maximum}))
