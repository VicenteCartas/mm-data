"""Run with Blender --background --factory-startup --python tools/blender/test_roundtrip.py."""
import addon_utils
import json
from pathlib import Path
import sys
import tempfile
import traceback
import struct
import os

import bpy
import bmesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
addon_utils.enable('mm_materials', default_set=True)
import mm_materials as addon


def triangle_count(doc):
    return sum(doc['accessors'][p['indices']]['count'] // 3
               for mesh in doc['meshes'] for p in mesh['primitives'])


def vertex_rows(doc, binary):
    def values(index):
        a = doc['accessors'][index]
        view = doc['bufferViews'][a['bufferView']]
        size = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
        code, width = {5126: ('f', 4), 5123: ('H', 2), 5125: ('I', 4), 5121: ('B', 1)}[a['componentType']]
        start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        rows = [struct.unpack_from('<' + code * size, binary, start + i * view.get('byteStride', size * width))
                for i in range(a['count'])]
        if a.get('normalized') and code != 'f':
            rows = [tuple(v / (2 ** (8 * width) - 1) for v in row) for row in rows]
        return rows
    result = []
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            attrs = [values(p['attributes'][k]) for k in sorted(p['attributes'])]
            for index, in values(p['indices']):
                result.append(tuple(round(v, 5) for attr in attrs for v in attr[index]))
    return sorted(result, key=lambda row: row[7:] + row[:4] + row[4:7])


def main():
    bpy.context.scene.mm_materials.root = str(ROOT)
    source = ROOT / 'data/models/board/scenery/road/road-tunnel.glb'
    original, original_binary = addon.glb.read_glb(source)
    scene = addon.open_glb(bpy.context, source)
    assert len(scene.objects) == len(original['nodes'])
    managed = [m for m in bpy.data.materials if m.get('_mm_tres')]
    assert managed, 'Import did not recognize board materials'
    assert any(m.node_tree.nodes.get('Normal Map') for m in managed)
    with tempfile.TemporaryDirectory(prefix='.mm-test-', dir=ROOT / 'data/models/board') as temp:
        target = Path(temp) / 'tunnel.glb'
        addon.save_glb(bpy.context, target)
        output, binary = addon.glb.read_glb(target)
        assert triangle_count(original) == triangle_count(output)
        old_rows, new_rows = vertex_rows(original, original_binary), vertex_rows(output, binary)
        assert len(old_rows) == len(new_rows)
        for old, new in zip(old_rows, new_rows):
            # Blender rebuilds custom split normals; compare authored positions, UVs and colours.
            assert all(abs(a - b) <= 2e-5 for i, (a, b) in enumerate(zip(old, new))
                       if not 4 <= i < 7), (old, new)
        assert {n['name'] for n in original['nodes']} == {n['name'] for n in output['nodes']}
        assert all('uri' in image and 'bufferView' not in image for image in output['images']), output['images']
        assert all(addon.glb.image_path(target, i['uri']).is_file() for i in output['images'])
        before = {p['extras']['mmPart'] for m in original['meshes'] for p in m['primitives']}
        after = {p['extras']['mmPart'] for m in output['meshes'] for p in m['primitives']}
        assert before == after, (before, after)
        assert all('COLOR_0' in p['attributes'] and 'TEXCOORD_0' in p['attributes']
                   for m in output['meshes'] for p in m['primitives'])
        assert '_mm_' not in json.dumps(output)
        backup = addon.save_glb(bpy.context, target)
        assert backup and backup.is_file()
        backup.unlink()
        # Verify Blender itself resolves the external images on re-import.
        addon.open_glb(bpy.context, target)
        for m in bpy.data.materials:
            if m.get('_mm_tres'):
                for node in m.node_tree.nodes:
                    if node.type == 'TEX_IMAGE':
                        assert Path(bpy.path.abspath(node.image.filepath)).is_file()
                        assert len(node.image.pixels) > 0, node.image.name
        print('ROUNDTRIP_OK', json.dumps({'triangles': triangle_count(output), 'images': len(output['images']),
                                         'materials': len(output['materials']), 'binary_bytes': len(binary)}))

        # Object-slot assignment preserves roles; face assignment only changes selected faces.
        mesh = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        old_name = addon.export_name(mesh.active_material)
        bpy.context.scene.mm_materials.material = 'structures/common/painted-steel.tres'
        assert bpy.ops.mm_materials.assign() == {'FINISHED'}
        assert addon.export_name(mesh.active_material) == old_name
        assert mesh.active_material['_mm_tres'] == 'structures/common/painted-steel.tres'
        other_indices = [p.material_index for p in mesh.data.polygons]
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(mesh.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(False)
        bm.faces[0].select_set(True)
        bpy.context.scene.mm_materials.material = 'structures/common/safety-yellow.tres'
        assert bpy.ops.mm_materials.assign() == {'FINISHED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        assert mesh.data.polygons[0].material_index != other_indices[0]
        assert [p.material_index for p in mesh.data.polygons][1:] == other_indices[1:]
        addon.save_glb(bpy.context, Path(temp) / 'assigned.glb')

        # Never overwrite a file changed by another program since Open or Save.
        assigned = Path(bpy.context.scene.mm_materials.source)
        changed = assigned.read_bytes() + b'changed elsewhere'
        assigned.write_bytes(changed)
        try:
            addon.save_glb(bpy.context, assigned)
            raise AssertionError('Concurrent edit was overwritten')
        except ValueError as error:
            assert 'changed on disk' in str(error)
        assert assigned.read_bytes() == changed

        # Cover real cutout/multiple-LOD and embedded-image models.
        for relative in ('vegetation/birch.glb', 'scenery/military/cargo-crate.glb'):
            model = ROOT / 'data/models/board' / relative
            before_doc, _ = addon.glb.read_glb(model)
            addon.open_glb(bpy.context, model)
            result = Path(temp) / model.name
            addon.save_glb(bpy.context, result)
            after_doc, _ = addon.glb.read_glb(result)
            assert triangle_count(before_doc) == triangle_count(after_doc)
            assert {n['name'] for n in before_doc['nodes']} == {n['name'] for n in after_doc['nodes']}
            assert before_doc.get('extras') == after_doc.get('extras')
            if any('bufferView' in i for i in before_doc.get('images', [])):
                assert any('bufferView' in i for i in after_doc['images']), 'Embedded images were lost'
            print('ASSET_OK', relative)

        # Game metadata and colour-slot vertex attributes must survive a different destination folder.
        sys.path.insert(0, str(ROOT / 'tools'))
        from glb_geometry import read_glb, write_glb
        model = read_glb(source, linear_colors=True)
        for mesh_data in model['meshes']:
            mesh_data['slots'] = [1] * (len(mesh_data['vertices']) // 12)
        for material in model['materials']:
            for texture in material.get('textures', []):
                texture['filename'] = os.path.relpath(source.parent / texture['filename'], temp).replace(os.sep, '/')
            material['extras'] = {'mmSnow': {'textures': {'baseColor': material['textures'][0]['filename']}}}
        fixture = Path(temp) / 'metadata.glb'
        extras = {'mmColourSlots': [{'name': 'Paint', 'colour': '#6699cc', 'presets': [['Blue', '#6699cc']]}],
                  'authorNote': {'test': True}}
        write_glb(fixture, model, extras=extras, linear_colors=True)
        addon.open_glb(bpy.context, fixture)
        nested = Path(temp) / 'nested'
        nested.mkdir()
        metadata_file = nested / 'metadata.glb'
        addon.save_glb(bpy.context, metadata_file)
        metadata, _ = addon.glb.read_glb(metadata_file)
        assert metadata['extras'] == extras
        assert all('_COLOUR_SLOT' in p['attributes'] for m in metadata['meshes'] for p in m['primitives'])
        assert all(addon.glb.image_path(metadata_file, m['extras']['mmSnow']['textures']['baseColor']).is_file()
                   for m in metadata['materials'])
        print('METADATA_OK')

    root = ROOT / 'data/models/board/textures'
    resources = list(root.rglob('*.tres'))
    for path in resources:
        addon.read_material(path, root)
    print('LIBRARY_OK', len(resources))
    print('ASSIGNMENT_AND_SAFE_SAVE_OK')


try:
    main()
except Exception:
    traceback.print_exc()
    sys.exit(1)
