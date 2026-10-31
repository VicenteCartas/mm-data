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
buildings = json.loads((MANIFESTS / 'building-manifest.json').read_text())
features = json.loads((MANIFESTS / 'manifest.json').read_text())
catalog = dict(features, **buildings)

lods = {}
for asset, entry in features.items():
    if 'lods' in entry:
        # Three mesh levels and the impostor; a winter variant (`"variant": "snow"`) reads its bare species' file.
        # Entries are keyed by the model's path; its level groups by its own name.
        name = asset.rsplit('/', 1)[-1]
        assert [lod['node'] for lod in entry['lods']] == [f'{name}-lod{level}' for level in range(4)], asset
        for level, lod in enumerate(entry['lods']):
            assert 0 < lod['triangles'] <= (1000, 300, 96, 12)[level], lod
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
    if asset in buildings:
        assert min(heights) == 0 and max(heights) == 18, f'One-level building: {path}'
    elif asset.startswith(('foliage-', 'orchard-')):
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
            if part['id'] == 'roof' and asset in buildings:
                for offset in range(0, len(indices), 3):
                    a, b, c = [vertices[index * 12:index * 12 + 3] for index in indices[offset:offset + 3]]
                    normal_z = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                    assert normal_z > 0, f'Roof winding: {path}'
    # Plant levels keep their own budgets (above); every other model stays within 500 triangles.
    assert 0 < triangles <= (1000 if asset in lods else 500), (path, triangles)
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
    if asset in buildings:
        facade = buildings[asset]['wall_texture']
        wall = next(material for material in model['materials'] if material['id'] != 'roof')
        assert (path.parent / wall['textures'][0]['filename']).resolve() == (BOARD / facade).resolve(), path
        assert Image.open(BOARD / facade).size == (128, 128), path
        assert (wall['id'] == 'shell') == buildings[asset]['full_height_facade'], path

print(json.dumps({'buildings': len(buildings), 'features': len(features), 'plant_lods': len(lods),
                  'max_triangles': maximum}))
