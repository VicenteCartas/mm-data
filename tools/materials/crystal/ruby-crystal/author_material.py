"""Author the ruby crystal graph through the native Material Maker MCP."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get('MM_DATA_ROOT', 'C:/Projects/megamek/mm-data'))
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK.parents[1] / 'handoff/photoreal-plants'))
from mm_http import Client

def gradient(points):
    return {'type': 'Gradient', 'interpolation': 1, 'points': [
        dict(pos=position, r=rgb[0], g=rgb[1], b=rgb[2], a=1) for position, rgb in points]}

client = Client('ruby-crystal-authoring')
graph = json.loads((ROOT / 'tools/materials/scenery/gem-crystal/gem-crystal.ptex').read_text())
graph['name'], graph['label'] = 'ruby-crystal', 'Ruby crystal'
opened = client.call('load_graph', graph=graph)
print('Opened', opened, flush=True)
tab = opened['tab']
changes = []
def set_node(node, **parameters):
    changes.append(client.call('set_parameters', tab=tab, node=node, parameters=parameters))

set_node('Material', size=10, flags_transparent=False, sss=.18, normal=.12, depth_scale=0, emission_energy=0)
set_node('base_color', param0=.5, param2=.08, param1=gradient([
    (0, (.58, .007, .018)), (.35, (.7, .01, .024)),
    (.72, (.79, .014, .03)), (1, (.86, .022, .04))]))
set_node('surface_detail', param0=gradient([(0, (.09,) * 3), (1, (.2,) * 3)]), param1=.012)
growth = client._post('tools/call', {'name': 'add_node', 'arguments': dict(
    tab=tab, node='perlin', name='CrystalGrowth', x=50, y=-650,
    parameters={'scale_x':3, 'scale_y':80, 'iterations':3, 'persistence':.35})})
assert 'error' not in growth and not growth.get('result', {}).get('isError'), growth
changes.append(growth)
changes.append(client.call('connect_nodes', tab=tab, **{'from':'CrystalGrowth','from_port':0,'to':'surface_detail','to_port':0}))
added = client._post('tools/call', {'name': 'add_node', 'arguments': dict(
    tab=tab, node='colorize', name='BodyOpacity', x=550, y=600,
    parameters={'gradient': gradient([(0, (1,) * 3), (1, (1,) * 3)])})})
assert 'error' not in added and not added.get('result', {}).get('isError'), added
changes.append(added)
changes.append(client.call('connect_nodes', tab=tab, **{'from':'AmbientNoise', 'from_port':0, 'to':'BodyOpacity', 'to_port':0}))
changes.append(client.call('connect_nodes', tab=tab, **{'from':'BodyOpacity', 'from_port':0, 'to':'Material', 'to_port':7}))
changes.append(client.call('set_parameters', tab=tab, node='About', title='Ruby crystal — cover and giant outcrops',
    text='Crimson ruby corundum with internal growth inclusions, polished dielectric facets, low relief and '
         'partial light transmission. The geometry supplies the large flat facets and bevels; this graph supplies '
         'body colour, fine inclusions, roughness, normal and subsurface scattering. No emission or alpha blending. '
         'The same material is used by all cover heights and all five giant props. Export Godot 4 Standard.'))
path = ROOT / 'tools/materials/crystal/ruby-crystal/ruby-crystal.ptex'
path.parent.mkdir(parents=True, exist_ok=True)
client.call('save_graph', tab=tab, path=str(path))
validation = client.call('validate_graph', path=str(path))
assert validation['valid'] and not validation['problems'], validation
prefix = ROOT / 'data/models/board/textures/crystal/ruby-crystal'
prefix.parent.mkdir(parents=True, exist_ok=True)
# Material Maker preserves an existing .tres: remove this owned generated descriptor so updated factors are exported.
prefix.with_suffix('.tres').unlink(missing_ok=True)
exported = client.call('export_material', tab=tab, path=str(prefix), size=1024)
tres = prefix.with_suffix('.tres')
tres.write_text(tres.read_text().replace('heightmap_enabled = true', 'heightmap_enabled = false'))
prefix.with_name(prefix.name + '_emission.png').unlink(missing_ok=True)
preview = client.call('render_preview', tab=tab, path=str(WORK / 'material-preview.png'), size=768, view='sphere')
result = dict(tab=tab, graph=str(path), validation=validation, export=exported, changes=changes)
(WORK / 'material-maker.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2), flush=True)
