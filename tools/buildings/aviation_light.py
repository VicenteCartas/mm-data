"""The aviation obstruction light a generated building kit stands on its roof's convex corners ("aol" in its JSON).

Run with Python (standard library only): python tools/buildings/aviation_light.py
Writes data/models/buildings/fittings/aviation-light.glb: one node, aol-lod0, at the roof's deck with z up. A thin steel
stick runs from well under the deck (it stays buried where a rounded or bevelled edge drops away) up to a square red
lamp, whose emission blinks (mmEmission "blink"). 20 triangles.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from glb_geometry import write_glb

DATA = TOOLS.parent / 'data'
STEEL = 'structures/common/painted-steel'
LAMP = STEEL + '#emission-1-0.04-0.02#blink'
TEXTURE = '../../board/textures/structures/common/painted-steel_albedo.png'
STICK, BOTTOM, TOP = .3, -5.0, 4.6  # Half width, foot under the deck, top under the lamp.
HEAD = .7  # The lamp's half width, as tall again.


def box(vertices, indices, x, y, z0, z1, colour, faces):
    """An axis-aligned box's faces of `faces` (sides, 'top', 'bottom'), wound outward, z up."""
    sides = {
        'south': ((0, -1, 0), [(-x, -y, z0), (x, -y, z0), (x, -y, z1), (-x, -y, z1)]),
        'east': ((1, 0, 0), [(x, -y, z0), (x, y, z0), (x, y, z1), (x, -y, z1)]),
        'north': ((0, 1, 0), [(x, y, z0), (-x, y, z0), (-x, y, z1), (x, y, z1)]),
        'west': ((-1, 0, 0), [(-x, y, z0), (-x, -y, z0), (-x, -y, z1), (-x, y, z1)]),
        'top': ((0, 0, 1), [(-x, -y, z1), (x, -y, z1), (x, y, z1), (-x, y, z1)]),
        'bottom': ((0, 0, -1), [(-x, y, z0), (x, y, z0), (x, -y, z0), (-x, -y, z0)]),
    }
    for face in faces:
        normal, corners = sides[face]
        first = len(vertices) // 12
        for point, uv in zip(corners, [(0, 0), (1, 0), (1, 1), (0, 1)]):
            vertices.extend([*point, *normal, *colour, 1, *uv])
        indices.extend(first + i for i in (0, 1, 2, 0, 2, 3))


def main():
    vertices, stick, lamp = [], [], []
    walls = ('south', 'east', 'north', 'west')
    box(vertices, stick, STICK, STICK, BOTTOM, TOP, (.42, .43, .44), walls)
    box(vertices, lamp, HEAD, HEAD, TOP, TOP + 2 * HEAD, (.55, .06, .05), walls + ('top', 'bottom'))
    mesh = {'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': vertices,
            'parts': [{'id': 'stick', 'type': 'TRIANGLES', 'indices': stick},
                      {'id': 'lamp', 'type': 'TRIANGLES', 'indices': lamp}]}
    node = {'id': 'aol-lod0', 'translation': [0, 0, 0],
            'parts': [{'meshpartid': 'stick', 'materialid': STEEL}, {'meshpartid': 'lamp', 'materialid': LAMP}]}
    steel = {'id': STEEL, 'diffuse': [1, 1, 1], 'roughness': .6, 'metallic': .3,
             'textures': [{'type': 'DIFFUSE', 'filename': TEXTURE}]}
    lens = {'id': LAMP, 'diffuse': [1, 1, 1], 'roughness': .35, 'metallic': 0, 'emissive': [1, .04, .02],
            'extras': {'mmEmission': 'blink'}, 'textures': [{'type': 'DIFFUSE', 'filename': TEXTURE}]}
    folder = DATA / 'models/buildings/fittings'
    folder.mkdir(parents=True, exist_ok=True)
    write_glb(folder / 'aviation-light.glb', levels={0: {'meshes': [mesh], 'nodes': [node], 'materials': [steel, lens]}})
    print('aviation-light.glb', (len(stick) + len(lamp)) // 3, 'triangles')


if __name__ == '__main__':
    main()
