"""Export all materials, or one relative PTEX path: python export.py [--wrap] [material.ptex]

A project at tools/materials/<folder>/<name>/<name>.ptex exports with Material Maker's stock Godot/Godot 4 Standard
target into data/models/board/textures/<folder>: <name>.tres and its <name>_albedo/_orm/_normal/_heightmap/_emission/
_sss.png maps, the files File > Export material > Godot > Godot 4 Standard writes, plus each Export node's own map.

Material Maker's command line renders every map at 2048 pixels whatever the nodes' Size, so each map is resampled to its
node's Size here, the size the editor's own export writes. The resampled pixels are close to the editor's, not
identical (a normal map's resampled texels are slightly shorter than unit length). Export larger sizes, or exact
pixels, from the editor.

A material with a map StandardMaterial3D has no slot for keeps a <name>.gdshader beside it: its <name>.tres is then a
ShaderMaterial of that shader, which this script writes from Material Maker's StandardMaterial3D. Standard maps and
factors take Godot's parameter names; each other `uniform sampler2D texture_<x>` of the shader is the Export node's
<name>_<x>.png. --wrap does only that, without Material Maker, after an editor export replaced the ShaderMaterial.
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MATERIAL_MAKER = shutil.which('material_maker') or 'C:/material_maker/material_maker.exe'
BAKED = ROOT.parents[1] / 'data/models/board/textures'
TARGET = 'Godot/Godot 4 Standard'
# Every map the target can write; one this export did not write belongs to an older version of the material.
MAPS = ('albedo', 'orm', 'emission', 'normal', 'heightmap', 'sss')
# A StandardMaterial3D map (with its enable flag) as the ShaderMaterial parameter of Godot's own converted shaders.
# The ORM map holds occlusion, roughness and metallic, as Godot's ORMMaterial3D packs them.
TEXTURES = {
    'texture_albedo': (('albedo_texture', None),),
    'texture_orm': (('roughness_texture', None), ('ao_texture', 'ao_enabled'), ('metallic_texture', None)),
    'texture_normal': (('normal_texture', 'normal_enabled'),),
    'texture_heightmap': (('heightmap_texture', 'heightmap_enabled'), ('depth_texture', 'heightmap_enabled')),
    'texture_emission': (('emission_texture', 'emission_enabled'),),
    'texture_subsurface_scattering': (('subsurf_scatter_texture', 'subsurf_scatter_enabled'),),
}
# A StandardMaterial3D factor as its ShaderMaterial parameter, with Godot's default when the resource omits it.
FACTORS = {
    'albedo': (('albedo_color',), 'Color(1, 1, 1, 1)'),
    'roughness': (('roughness',), '1.0'),
    'metallic': (('metallic',), '0.0'),
    'normal_scale': (('normal_scale',), '1.0'),
    'heightmap_scale': (('heightmap_scale',), '5.0'),
    'emission_energy': (('emission_energy_multiplier', 'emission_energy'), '1.0'),
    'subsurface_scattering_strength': (('subsurf_scatter_strength',), '0.0'),
}


def nodes(graph):
    for node in graph['nodes']:
        yield node
        if node['type'] == 'graph':
            yield from nodes(node)


def sizes(project):
    """Each map's intended width: the Material node's Size for its maps, an Export node's own for its map."""
    graph = json.loads(project.read_text(encoding='utf-8'))
    materials = [node for node in graph['nodes'] if node['type'] == 'material']
    if len(materials) != 1:
        raise SystemExit(f'{project.relative_to(ROOT)}: expected one stock Material node')
    size = 2 ** int(materials[0]['parameters']['size'])
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
    from PIL import Image  # Only exports resample; --wrap runs without Pillow.
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


def resource(path):
    """A Godot text resource's type, ext_resource paths by id and [resource] properties (one line each)."""
    kind, resources, properties, section = None, {}, {}, None
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        header = re.fullmatch(r'\[(\w+)(.*)]', line)
        if header:
            section = header.group(1)
            attributes = {key: value.strip('"') for key, value
                          in re.findall(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)', header.group(2))}
            if section == 'gd_resource':
                kind = attributes.get('type')
            elif section == 'ext_resource':
                resources[attributes['id']] = attributes['path']
        elif section == 'resource' and '=' in line and not line.startswith(';'):
            key, value = line.split('=', 1)
            properties[key.strip()] = value.strip()
    return kind, resources, properties


def uniforms(shader):
    """A shader's material parameters in declaration order: name -> type."""
    code = re.sub(r'//[^\n]*|/\*.*?\*/', '', shader.read_text(encoding='utf-8'), flags=re.S)
    return {match.group(2): match.group(1) for match in re.finditer(
        r'(?<![\w ])\s*uniform\s+(?:(?:lowp|mediump|highp)\s+)?(\w+)\s+(\w+)', code)}


def color(value):
    """Material Maker's Color( 1.0, 1.0, 1.0, 1.0 ) as Godot 4 writes it."""
    parts = [float(part) for part in value[value.index('(') + 1:value.rindex(')')].split(',')]
    return 'Color(' + ', '.join(f'{part:g}' for part in parts) + ')'


def wrap(name, folder, standard):
    """Write folder/<name>.tres as a ShaderMaterial of <name>.gdshader from a StandardMaterial3D (`standard`)."""
    shader = folder / f'{name}.gdshader'
    kind, resources, properties = resource(standard)
    if kind != 'StandardMaterial3D':
        raise SystemExit(f'{standard}: expected Material Maker\'s StandardMaterial3D, not {kind}')
    declared = uniforms(shader)

    def texture(prop, flag):
        value = properties.get(prop)
        if value is None or (flag and properties.get(flag) != 'true'):
            return None
        return resources[re.fullmatch(r'ExtResource\(\s*"?([^")\s]+)"?\s*\)', value).group(1)]

    maps = {}
    for parameter, sources in TEXTURES.items():
        files = {texture(prop, flag) for prop, flag in sources} - {None}
        if len(files) > 1:
            raise SystemExit(f'{standard}: {parameter} must be one map, not {sorted(files)}')
        if files:
            maps[parameter] = files.pop()
    for parameter, kind in declared.items():
        if kind == 'sampler2D' and parameter not in TEXTURES:
            if not parameter.startswith('texture_'):
                raise SystemExit(f'{shader}: a map parameter is named texture_<map>, not {parameter}')
            maps[parameter] = f'{name}_{parameter[len("texture_"):]}.png'
    for parameter, file in maps.items():
        if declared.get(parameter) != 'sampler2D':
            raise SystemExit(f'{shader} must declare uniform sampler2D {parameter} for {file}')
        if not (folder / file).is_file():
            raise SystemExit(f'{folder / file} is missing: {parameter} of {name}.tres')
    for parameter, kind in declared.items():
        if kind == 'sampler2D' and parameter not in maps:
            raise SystemExit(f'{shader} declares {parameter}, but the export has no such map')
    values = {}
    for parameter, (props, fallback) in FACTORS.items():
        if parameter in declared:
            value = next((properties[prop] for prop in props if prop in properties), fallback)
            values[parameter] = color(value) if parameter == 'albedo' else value
    ids = {parameter: f'{index}_{parameter[len("texture_"):]}' for index, parameter in enumerate(maps, 2)}
    lines = [f'[gd_resource type="ShaderMaterial" load_steps={len(maps) + 2} format=3]', '',
             f'[ext_resource type="Shader" path="{shader.name}" id="1_shader"]']
    lines += [f'[ext_resource type="Texture2D" path="{maps[parameter]}" id="{ids[parameter]}"]' for parameter in maps]
    lines += ['', '[resource]', 'render_priority = 0', 'shader = ExtResource("1_shader")']
    for parameter in declared:
        if parameter in maps:
            lines.append(f'shader_parameter/{parameter} = ExtResource("{ids[parameter]}")')
        elif parameter in values:
            lines.append(f'shader_parameter/{parameter} = {values[parameter]}')
    (folder / f'{name}.tres').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def export(project):
    destination = BAKED / project.parent.parent.relative_to(ROOT)
    name = str(destination.relative_to(BAKED) / project.stem).replace('\\', '/')
    expected = sizes(project)
    print(f'Exporting {project.relative_to(ROOT)}', flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary)
        subprocess.run([MATERIAL_MAKER, '--export-material', str(project),
                        '--target', TARGET, '--output-dir', str(output)], check=True)
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
        shader = destination / f'{project.stem}.gdshader'
        for file in written:
            # A material with a shader beside it is a ShaderMaterial, made from Material Maker's StandardMaterial3D.
            if not (shader.is_file() and file.name == f'{project.stem}.tres'):
                shutil.copyfile(file, destination / file.name)
        if shader.is_file():
            wrap(project.stem, destination, output / f'{project.stem}.tres')
    check_catalog(project, name, expected[f'{project.stem}_albedo.png'])


def rewrap(project):
    """After an editor export replaced a ShaderMaterial with Material Maker's StandardMaterial3D, restore it."""
    destination = BAKED / project.parent.parent.relative_to(ROOT)
    tres = destination / f'{project.stem}.tres'
    if not (destination / f'{project.stem}.gdshader').is_file() or not tres.is_file():
        return
    if resource(tres)[0] == 'ShaderMaterial':
        print(f'{project.relative_to(ROOT)}: already a ShaderMaterial')
        return
    wrap(project.stem, destination, tres)
    print(f'{project.relative_to(ROOT)}: wrapped as a ShaderMaterial of {project.stem}.gdshader')


def main():
    arguments = argparse.ArgumentParser(description='Export the board materials with Material Maker.')
    arguments.add_argument('--wrap', action='store_true',
                           help='only restore ShaderMaterials an editor export replaced, without Material Maker')
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
        (rewrap if options.wrap else export)(project)


if __name__ == '__main__':
    main()
