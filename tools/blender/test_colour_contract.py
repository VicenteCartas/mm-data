"""Run run() through Blender MCP; preserves the user's scenes and authoring state.

Checks real Blender node inputs against raw GLB output and Godot resource colours.
"""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types

import bpy

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / 'buildings'))
from glb_geometry import read_glb, write_glb
import authored_examples as author


def close(actual, expected):
    assert len(actual) == len(expected)
    assert max(abs(a - b) for a, b in zip(actual, expected)) < 2e-7, (actual, expected)


def run(preview=None):
    previous = bpy.context.window.scene
    state = {name: getattr(author, name) for name in ('objects', 'volumes', 'materials', 'role')}
    before = {name: set(getattr(bpy.data, name)) for name in ('objects', 'meshes', 'materials', 'images')}
    scene = bpy.data.scenes.new('Colour contract test')
    bpy.context.window.scene = scene
    # Load repository preview code without registering/replacing the user's addon.
    package = types.ModuleType('_mm_colour_test')
    package.__path__ = [str(HERE / 'mm_materials')]
    sys.modules[package.__name__] = package
    try:
        if preview is None:
            preview = importlib.import_module(package.__name__ + '.preview')
        importlib.reload(author)
        pigment = (.02, .45, .8)
        expected = (.001547987616, .170644935816, .603827338855)
        obj = author.box('Colour probe', (0, 0, 0), (1, 1, 1), author.FLAT, pigment)
        shader = obj.active_material.node_tree.nodes.get('Principled BSDF')
        close(shader.inputs['Base Color'].default_value, (*expected, 1))
        close(obj.active_material.diffuse_color, (*expected, 1))
        with tempfile.TemporaryDirectory(prefix='mm-colour-contract-') as folder:
            folder = Path(folder)
            model = author.export_model([obj], 'probe')
            write_glb(folder / 'probe.glb', model)
            for mesh in read_glb(folder / 'probe.glb', linear_colors=True)['meshes']:
                for offset in range(0, len(mesh['vertices']), 12):
                    close(mesh['vertices'][offset + 6:offset + 10], shader.inputs['Base Color'].default_value)

            image = bpy.data.images.new('Colour fixture', width=1, height=1)
            image.pixels[:] = (1, 1, 1, 1)
            image.filepath_raw = str(folder / 'colour_albedo.png'); image.file_format = 'PNG'; image.save()
            resource = folder / 'colour.tres'
            resource.write_text('[gd_resource type="StandardMaterial3D" format=3]\n'
                                '[ext_resource type="Texture2D" path="colour_albedo.png" id="1"]\n'
                                '[resource]\nalbedo_texture = ExtResource("1")\n'
                                'albedo_color = Color(0.02, 0.45, 0.8, 0.37)\n'
                                'emission_enabled = true\nemission = Color(0.5, 0.25, 0.1, 1)\n'
                                'emission_energy_multiplier = 2\n')
            material = bpy.data.materials.new('Resource colour probe')
            imported_factor = [.25, .5, .75, .4]
            material['_mm_surface'] = json.dumps({'baseColorFactor': imported_factor})
            preview.build_preview(material, resource, folder)
            close(material.diffuse_color, (*expected, .37))
            mixes = [node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeMix']
            close(next(node for node in mixes if tuple(node.location) == (-400, 600)).inputs[7].default_value,
                  (*expected, .37))
            close(next(node for node in mixes if tuple(node.location) == (-200, 750)).inputs[7].default_value,
                  imported_factor)
            shader = next(node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeBsdfPrincipled')
            close(shader.inputs['Emission Color'].default_value, (.214041140482, .050876088172, .010022825575, 1))
            assert shader.inputs['Emission Strength'].default_value == 2
            material['_mm_model_emission'] = True
            material['_mm_emission_factor'] = [.25, .5, .75]
            preview.build_preview(material, resource, folder)
            shader = next(node for node in material.node_tree.nodes if node.bl_idname == 'ShaderNodeBsdfPrincipled')
            close(shader.inputs['Emission Color'].default_value, (.25, .5, .75, 1))
            assert shader.inputs['Emission Strength'].default_value == 1
        return {'authored_preview_matches_glb': True, 'tres_rgb_decoded': True,
                'alpha_and_imported_linear_factors_preserved': True}
    finally:
        bpy.context.window.scene = previous
        bpy.data.scenes.remove(scene)
        for name in ('objects', 'meshes', 'materials', 'images'):
            collection = getattr(bpy.data, name)
            for block in set(collection) - before[name]:
                collection.remove(block, do_unlink=True)
        for name, value in state.items(): setattr(author, name, value)
        for name in list(sys.modules):
            if name == package.__name__ or name.startswith(package.__name__ + '.'):
                del sys.modules[name]


if __name__ == '__main__':
    print(run())
