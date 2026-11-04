"""Author-placed Empty anchors survive mesh and impostor regeneration."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from glb_geometry import write_glb


def anchors(path):
    raw = path.read_bytes()
    length = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20 + length])
    group = next(node for node in document['nodes'] if node.get('name') == 'spores')
    return [document['nodes'][index] for index in group['children']]


class GlbAnchorsTest(unittest.TestCase):
    def test_rebuilding_levels_preserves_authored_outlet_frames(self):
        mesh = {'nodes': [{'id': 'body'}], 'meshes': [], 'materials': []}
        outlets = {'nodes': [{'id': 'high-bowl', 'translation': [-4, 2, 28], 'scale': [2, 2, 2]},
                             {'id': 'low-bowl', 'translation': [6, -1, 20], 'scale': [1.5, 1.5, 1.5]}],
                   'meshes': [], 'materials': []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fungus.glb'
            write_glb(path, levels={0: mesh}, groups={'spores': outlets})
            original = anchors(path)
            write_glb(path, levels={0: mesh, 1: mesh, 2: mesh, 3: mesh}, preserve_groups=('spores',))
            self.assertEqual(original, anchors(path))
            self.assertTrue(all('mesh' not in node for node in anchors(path)))

    def test_explicit_new_anchors_replace_the_retained_group(self):
        mesh = {'nodes': [{'id': 'body'}], 'meshes': [], 'materials': []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fungus.glb'
            write_glb(path, levels={0: mesh}, groups={'spores': mesh})
            replacement = {**mesh, 'nodes': [{'id': 'moved-bowl', 'translation': [1, 2, 3]}]}
            write_glb(path, levels={0: mesh}, groups={'spores': replacement}, preserve_groups=('spores',))
            self.assertEqual(['moved-bowl'], [node['name'] for node in anchors(path)])


if __name__ == '__main__':
    unittest.main()
