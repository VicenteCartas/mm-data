"""Material parameters survive generation and offline GLB editing without gamma conversion."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from glb_geometry import read_glb, write_glb


class GlbMaterialsTest(unittest.TestCase):
    def test_emission_survives_offline_round_trip_without_lighting_adjacent_materials(self):
        lamp = {'id': 'lamp', 'emissive': [1, .5, .2],
                'textures': [{'type': 'EMISSIVE', 'filename': 'existing-lamp.png'}]}
        model = {'nodes': [{'id': 'root'}], 'meshes': [], 'materials': [lamp, {'id': 'wall'}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lamps.glb'
            write_glb(path, model)
            loaded = read_glb(path)
            self.assertEqual('EMISSIVE', loaded['materials'][0]['textures'][0]['type'])
            for actual, expected in zip(loaded['materials'][0]['emissive'], lamp['emissive']):
                self.assertAlmostEqual(expected, actual)
            write_glb(path, loaded)
            raw = path.read_bytes()
            doc = json.loads(raw[20:20 + struct.unpack_from('<I', raw, 12)[0]])
            emission = doc['materials'][0]['emissiveFactor']
            self.assertAlmostEqual(.214041140482, emission[1])
            texture = doc['materials'][0]['emissiveTexture']['index']
            self.assertEqual('existing-lamp.png', doc['images'][doc['textures'][texture]['source']]['uri'])
            self.assertNotIn('emissiveFactor', doc['materials'][1])
            self.assertNotIn('emissiveTexture', doc['materials'][1])
            write_glb(path, read_glb(path, linear_colors=True), linear_colors=True)
            self.assertEqual(emission, read_glb(path, linear_colors=True)['materials'][0]['emissive'])

    def test_display_rgb_is_decoded_once_and_alpha_and_linear_inputs_are_preserved(self):
        rgba = [.02, .5, .8, .37]
        decoded = [.001547987616, .214041140482, .603827338855]
        mesh = {'id': 'triangle', 'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                'vertices': [value for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0))
                             for value in (*p, 0, 0, 1, *rgba, 0, 0)],
                'parts': [{'id': 'face', 'type': 'TRIANGLES', 'indices': [0, 1, 2]}]}
        model = {'nodes': [{'id': 'root', 'parts': [{'meshpartid': 'face', 'materialid': 'paint'}]}],
                 'meshes': [mesh], 'materials': [{'id': 'paint', 'diffuse': rgba[:3], 'opacity': .41}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'colour.glb'
            for linear_input, data_colour in ((False, False), (True, False), (False, True)):
                with self.subTest(linear_input=linear_input, data_colour=data_colour):
                    mesh['colorData'] = data_colour
                    write_glb(path, model, linear_colors=linear_input)
                    raw = path.read_bytes()
                    doc = json.loads(raw[20:20 + struct.unpack_from('<I', raw, 12)[0]])
                    factor = doc['materials'][0]['pbrMetallicRoughness']['baseColorFactor']
                    for actual, expected in zip(factor[:3], rgba[:3] if linear_input else decoded):
                        self.assertAlmostEqual(expected, actual, places=7)
                    self.assertEqual(.41, factor[3])
                    loaded = read_glb(path, linear_colors=True)['meshes'][0]['vertices']
                    expected_rgb = rgba[:3] if linear_input or data_colour else decoded
                    for offset in range(0, len(loaded), 12):
                        for actual, expected in zip(loaded[offset + 6:offset + 9], expected_rgb):
                            self.assertAlmostEqual(expected, actual, places=7)
                        self.assertAlmostEqual(.37, loaded[offset + 9], places=7)

    def test_authored_factors_and_packed_map_survive_round_trip(self):
        material = {'id': 'steel', 'diffuse': [.4, .5, .6], 'roughness': .37, 'metallic': .8,
                    'textures': [{'id': 'steel', 'type': 'METALLIC_ROUGHNESS', 'filename': 'surface.png'}]}
        model = {'nodes': [{'id': 'root'}], 'meshes': [], 'materials': [material]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'surface.glb'
            write_glb(path, model)
            loaded = read_glb(path)
            surface = loaded['materials'][0]
            self.assertEqual(.37, surface['roughness'])
            self.assertEqual(.8, surface['metallic'])
            self.assertEqual('METALLIC_ROUGHNESS', surface['textures'][0]['type'])
            write_glb(path, loaded)
            raw = path.read_bytes()
            length = struct.unpack_from('<I', raw, 12)[0]
            document = json.loads(raw[20:20 + length])
            pbr = document['materials'][0]['pbrMetallicRoughness']
            self.assertEqual(.37, pbr['roughnessFactor'])
            self.assertEqual(.8, pbr['metallicFactor'])
            self.assertEqual('surface.png', document['images'][document['textures'][
                pbr['metallicRoughnessTexture']['index']]['source']]['uri'])

    def test_existing_generators_stay_matte_and_invalid_factors_are_rejected(self):
        material = {'id': 'wall'}
        model = {'nodes': [{'id': 'root'}], 'meshes': [], 'materials': [material]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wall.glb'
            write_glb(path, model)
            surface = read_glb(path)['materials'][0]
            self.assertEqual(1, surface['roughness'])
            self.assertEqual(0, surface['metallic'])
            for key in ('roughness', 'metallic'):
                for value in (-.1, 1.1, float('nan')):
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        write_glb(path, {**model, 'materials': [{**material, key: value}]})


if __name__ == '__main__':
    unittest.main()
