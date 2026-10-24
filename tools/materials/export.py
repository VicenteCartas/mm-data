"""Export all materials, or one relative PTEX path: python export.py [material.ptex]

A project at tools/materials/<folder>/<name>/<name>.ptex exports into data/models/board/textures/<folder>: <name>.tres
and its <name>_albedo/_orm/_normal/_heightmap/_emission/_sss.png maps, plus each Export node's own map, as the editor's
File > Export material writes them. The target is Material Maker's stock Godot/Godot 4 Standard, or the project's own
Godot/Godot 4 ShaderMaterial when its Material node carries one (lava, crust and ice: their .tres is a ShaderMaterial
of the <name>.gdshader beside it).

Material Maker's command line renders every map at 2048 pixels whatever the nodes' Size, so each map is resampled to its
node's Size here, the size the editor's own export writes. The resampled pixels are close to the editor's, not
identical (a normal map's resampled texels are slightly shorter than unit length). Export larger sizes, or exact
pixels, from the editor.
"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MATERIAL_MAKER = shutil.which('material_maker') or 'C:/material_maker/material_maker.exe'
BAKED = ROOT.parents[1] / 'data/models/board/textures'
TARGET = 'Godot/Godot 4 Standard'
SHADER_TARGET = 'Godot/Godot 4 ShaderMaterial'
# Every map the target can write; one this export did not write belongs to an older version of the material.
MAPS = ('albedo', 'orm', 'emission', 'normal', 'heightmap', 'sss')


def nodes(graph):
    for node in graph['nodes']:
        yield node
        if node['type'] == 'graph':
            yield from nodes(node)


def material(graph):
    materials = [node for node in graph['nodes'] if node['type'] in ('material', 'material_export')]
    if len(materials) != 1:
        raise SystemExit('expected one Material node')
    return materials[0]


def target(project):
    """The project's own ShaderMaterial target when its Material node carries one, else the stock target."""
    node = material(json.loads(project.read_text(encoding='utf-8')))
    return SHADER_TARGET if SHADER_TARGET in node.get('shader_model', {}).get('exports', {}) else TARGET


def sizes(project):
    """Each map's intended width: the Material node's Size for its maps, an Export node's own for its map."""
    graph = json.loads(project.read_text(encoding='utf-8'))
    size = 2 ** int(material(graph)['parameters']['size'])
    result = {f'{project.stem}_{name}.png': size for name in MAPS}
    for node in nodes(graph):
        if node['type'] != 'export':
            continue
        parameters = node['parameters']
        name = parameters.get('suffix', '$project').replace('$project', project.stem)
        if parameters.get('format', 0) != 0 or '$' in name or '/' in name:
            raise SystemExit(f'{project.relative_to(ROOT)}: Export node {node["name"]} must write a PNG named '
                             'beside the material (a plain file name, or $project)')
        result[name if name.endswith('.png') else name + '.png'] = 2 ** int(parameters['size'])
    return result


def resample(file, size):
    from PIL import Image
    with Image.open(file) as image:
        if image.size == (size, size):
            return
        if size > image.width:
            raise SystemExit(f'{file.name}: Size {size} is above the {image.width} pixels Material Maker\'s command '
                             'line renders; export this material from the editor instead')
        # An exact box filter; Pillow averages RGBA premultiplied, so transparent texels do not bleed into colour.
        resized = image.resize((size, size), Image.Resampling.BOX)
    resized.save(file)


def check_catalog(project, name, width):
    """The game repeats a loose material at its catalogued density, so a wider export covers more ground."""
    catalog = json.loads((BAKED / 'materials.json').read_text(encoding='utf-8'))
    loose = catalog['loose'].get(name)
    if loose is None:
        if name not in catalog['constrained']:
            print(f'  Add {name} to materials.json: "loose" (repeats across the board) or "constrained"')
        return
    coverage = width / loose['pixels']
    if 'metres' not in loose:
        print(f'  Loose: covers {coverage:g} times its catalogued ground')
        return
    repeat = loose['metres'] * coverage
    print(f'  Loose: one repeat spans {repeat:g} m')
    graph = json.loads(project.read_text(encoding='utf-8'))
    authored = {node['parameters']['RepeatMetres'] for node in nodes(graph)
                if node['type'] == 'remote' and 'RepeatMetres' in node['parameters']}
    for value in sorted(value for value in authored if abs(value - repeat) > 1e-6):
        print(f'  Repeat (metres) is {value:g}, but the game repeats this texture every {repeat:g} m: set '
              f'Repeat (metres) to {repeat:g}, or change its metres in materials.json to change its density')


def export(project):
    destination = BAKED / project.parent.parent.relative_to(ROOT)
    name = str(destination.relative_to(BAKED) / project.stem).replace('\\', '/')
    expected = sizes(project)
    print(f'Exporting {project.relative_to(ROOT)}', flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        subprocess.run([MATERIAL_MAKER, '--export-material', str(project),
                        '--target', target(project), '--output-dir', str(output)], check=True)
        written = sorted(output.iterdir())
        if not (output / f'{project.stem}.tres').is_file() or not (output / f'{project.stem}_albedo.png').is_file():
            raise SystemExit(f'{project.relative_to(ROOT)}: the export wrote no {project.stem}.tres with an albedo map')
        for file in written:
            if file.suffix == '.png':
                if file.name not in expected:
                    raise SystemExit(f'{project.relative_to(ROOT)}: unexpected exported file {file.name}')
                resample(file, expected[file.name])
        destination.mkdir(parents=True, exist_ok=True)
        for map_name in MAPS:
            if not (output / f'{project.stem}_{map_name}.png').exists():
                (destination / f'{project.stem}_{map_name}.png').unlink(missing_ok=True)
        for file in written:
            shutil.copyfile(file, destination / file.name)
    check_catalog(project, name, expected[f'{project.stem}_albedo.png'])


def main():
    arguments = argparse.ArgumentParser(description='Export the board materials with Material Maker.')
    arguments.add_argument('project', nargs='?', help='one .ptex path relative to tools/materials')
    options = arguments.parse_args()
    projects = sorted(ROOT.rglob('*.ptex'))
    if options.project:
        relative = Path(options.project)
        project = (ROOT / relative).resolve()
        if relative.is_absolute() or project not in projects:
            raise SystemExit('Expected an existing .ptex path relative to tools/materials')
        projects = [project]
    for project in projects:
        export(project)


if __name__ == '__main__':
    main()
