"""Read the Material Maker/Godot material subset used by mm-data. No bpy dependency."""
import json
import math
import re
from pathlib import Path


def resolve_map(resource, root, value):
    path = (root / value[6:] if value.startswith('res://') else resource.parent / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Material dependency leaves the textures folder: {value}')
    if not path.is_file():
        raise ValueError(f'Missing material dependency: {path}')
    return path


def read_material(path, root):
    """Return preview parameters; the original .tres remains the runtime authority."""
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Choose a .tres inside the board textures folder')
    text = path.read_text(encoding='utf-8-sig')
    resources, props, kind, section = {}, {}, None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('['):
            section = line[1:].split()[0].rstrip(']')
            attrs = dict(re.findall(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s\]]+)', line))
            attrs = {k: json.loads(v) if v.startswith('"') else v for k, v in attrs.items()}
            if section == 'gd_resource':
                kind = attrs.get('type')
            elif section == 'ext_resource':
                resources[attrs['id']] = resolve_map(path, root, attrs['path'])
        elif section == 'resource' and '=' in line:
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    if kind not in ('StandardMaterial3D', 'ShaderMaterial'):
        raise ValueError(f'Expected StandardMaterial3D or ShaderMaterial: {path}')

    def texture(key):
        value = props.get(key)
        if value is None:
            return None
        match = re.fullmatch(r'ExtResource\(\s*("[^"]+"|\d+)\s*\)', value)
        if not match or match[1].strip('"') not in resources:
            raise ValueError(f'Unsupported texture reference {key} = {value} in {path.name}')
        return resources[match[1].strip('"')]

    paint_mask = props.get('metadata/mmPaintMask') == 'true'
    shader = kind == 'ShaderMaterial'
    if shader:
        shader_path = texture('shader')
        if shader_path is None:
            raise ValueError(f'Missing shader in {path.name}')
        code = re.sub(r'//[^\n]*|/\*.*?\*/', '', shader_path.read_text(encoding='utf-8'), flags=re.S)
        uniforms = dict(re.findall(r'\buniform\s+\w+\s+(\w+)\s*(?::[^=;]*)?(?:=([^;]*))?;', code))
        props = {k[17:]: v for k, v in props.items() if k.startswith('shader_parameter/') and k[17:] in uniforms}
        for key, value in uniforms.items():
            if value.strip():
                props.setdefault(key, value.strip())

    def number(key, default):
        value = float(props.get(key, default))
        if not math.isfinite(value):
            raise ValueError(f'Non-finite {key} in {path.name}')
        return value

    def color(key, default):
        value = props.get(key)
        if value is None:
            return default
        match = re.fullmatch(r'(?:Color|vec4)\(([^)]+)\)', value)
        if not match:
            raise ValueError(f'Unsupported color {key} in {path.name}')
        values = tuple(float(v) for v in match[1].split(','))
        if len(values) == 1:
            values *= 4
        if len(values) != 4 or not all(math.isfinite(v) for v in values):
            raise ValueError(f'Invalid color {key} in {path.name}')
        return values

    def enabled(key):
        return props.get(key, 'false') == 'true'

    albedo = texture('texture_albedo' if shader else 'albedo_texture')
    if albedo != path.with_name(path.stem + '_albedo.png'):
        raise ValueError(f'{path.name} must reference its adjacent {path.stem}_albedo.png for game lookup')
    result = dict(path=path, shader=shader, albedo=albedo,
                  tint=color('albedo' if shader else 'albedo_color', (1, 1, 1, 1)),
                  roughness=number('roughness', 1), metallic=number('metallic', 0),
                  normal_scale=number('normal_scale', 1),
                  transparent=not shader and number('transparency', 0) != 0,
                  alpha_cutoff=number('alpha_scissor_threshold', .5),
                  double_sided=not shader and number('cull_mode', 0) == 2)
    for role, channel in [('roughness', 1), ('metallic', 2), ('ao', 0)]:
        active = shader or role != 'ao' or enabled('ao_enabled')
        result[role + '_map'] = texture('texture_orm' if shader else role + '_texture') if active else None
        result[role + '_channel'] = channel if shader else int(number(role + '_texture_channel', 0))
        if result[role + '_channel'] not in range(5):
            raise ValueError(f'Invalid {role} channel in {path.name}')
    result['normal'] = texture('texture_normal' if shader else 'normal_texture') if shader or enabled('normal_enabled') else None
    result['emission'] = texture('texture_emission' if shader else 'emission_texture') if shader or enabled('emission_enabled') else None
    result['emission_color'] = color('emission', (0, 0, 0, 1)) if not shader and enabled('emission_enabled') else (0, 0, 0, 1)
    result['emission_energy'] = number('emission_energy_multiplier', number('emission_energy', 1))
    result['paint_mask'] = paint_mask
    result['emission_operator'] = int(number('emission_operator', 0))
    result['sss'] = texture('texture_subsurface_scattering' if shader else 'subsurf_scatter_texture') if shader or enabled('subsurf_scatter_enabled') else None
    result['sss_strength'] = number('subsurface_scattering_strength' if shader else 'subsurf_scatter_strength', 0)
    return result
