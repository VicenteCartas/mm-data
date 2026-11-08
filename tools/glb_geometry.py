"""Shared GLB writer for the rigid unit and terrain kits. No Blender dependency.

Authoring uses MegaMek's Z-up coordinates and display-space colors. Files use
glTF's Y-up coordinates and linear colors; the runtime keeps those colors linear.
The explicit linear_colors option preserves original glTF color values in offline processing.
The small reader is for our offline review, processing and validation tools.
"""
import json
import math
import struct
from pathlib import Path


STRIDES = {'POSITION': 3, 'NORMAL': 3, 'COLOR': 4, 'TEXCOORD0': 2}
SEMANTICS = {'POSITION': 'POSITION', 'NORMAL': 'NORMAL', 'COLOR': 'COLOR_0', 'TEXCOORD0': 'TEXCOORD_0'}


def linear(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def display(value):
    return value * 12.92 if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055


def y_up(value):
    return [value[0], value[2], -value[1]]


def z_up(value):
    return [value[0], -value[2], value[1]]


def fit_colours(colours, positions, indices):
    """One part's stored vertex colours (lists, changed in place) within 0 to 1, each channel keeping its average over the
    part's surface.

    Blender's glTF exporter clips vertex colours to 0..1, so a value above 1 would silently change the moment an author
    saved the file. Vertices over the range take 1 and the rest rise just enough to make up what they lost: the same look,
    and the same on every later save.
    """
    used = sorted(set(indices))
    if all(0 <= c <= 1 for i in used for c in colours[i]):
        return
    surface = dict.fromkeys(used, 1e-12)
    for k in range(0, len(indices), 3):
        a, b, c = (positions[i] for i in indices[k:k+3])
        u, v = [b[j]-a[j] for j in range(3)], [c[j]-a[j] for j in range(3)]
        area = math.hypot(u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])/2
        for i in indices[k:k+3]:
            surface[i] += area/3
    total = sum(surface.values())
    for channel in range(3):
        target = min(1, sum(colours[i][channel]*surface[i] for i in used)/total)

        def mean(scale):
            return sum(min(1, max(0, colours[i][channel]*scale))*surface[i] for i in used)/total

        low, high = 1, 1
        while mean(high) < target and high < 1024:
            high *= 2
        for _ in range(40):
            scale = (low+high)/2
            if mean(scale) < target:
                low = scale
            else:
                high = scale
        scale = high
        for i in used:
            colours[i][channel] = min(1, max(0, colours[i][channel]*scale))
    for i in used:
        colours[i][3:] = [min(1, max(0, c)) for c in colours[i][3:]]


def write_glb(path, model=None, *, levels=None, groups=None, extras=None, linear_colors=False, preserve_groups=()):
    """Export existing rigid authoring arrays, preserving node/part/material IDs.

    With `linear_colors=True`, pigment factors and vertex RGB are already linear; alpha is unchanged.
    A mesh with `colorData=True` stores numeric COLOR_0 channels without any transfer function. Other vertex colours are
    stored within 0 to 1 (fit_colours).
    A mesh may carry `slots`, one colour slot per vertex (0 none, n the model's n-th colour slot), written as the
    `_COLOUR_SLOT` attribute; `extras` become the file's extras (for example its `mmColourSlots` definitions).
    `groups` adds root groups beside the levels by name, which the game reads as data (a `cut` and its `stands`):
    their parts may leave out `materialid`, and nodes without parts are empties.
    `preserve_groups` retains named, static empty-node groups from the existing file when rebuilding its meshes.
    """
    retained = []
    if preserve_groups and Path(path).is_file():
        previous = Path(path).read_bytes()
        length = struct.unpack_from('<I', previous, 12)[0]
        old = json.loads(previous[20:20 + length])

        def retain(index):
            node = dict(old['nodes'][index])
            if any(key in node for key in ('mesh', 'camera', 'skin')):
                raise ValueError('Only empty anchor groups can be preserved: ' + node.get('name', ''))
            node['children'] = [retain(child) for child in node.get('children', [])]
            return node

        for index in old['scenes'][old.get('scene', 0)]['nodes']:
            name = old['nodes'][index].get('name')
            if name in preserve_groups and name not in (groups or {}):
                retained.append(retain(index))
    document = {'asset': {'version': '2.0', 'generator': 'MegaMek rigid mesh exporter'},
                'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
                'materials': [], 'accessors': [], 'bufferViews': [], 'buffers': []}
    binary = bytearray()

    def accessor(values, size, component=5126, target=34962):
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        code = {5126: 'f', 5123: 'H', 5125: 'I'}[component]
        binary.extend(struct.pack('<' + code * len(values), *values))
        view = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': offset,
                                       'byteLength': len(binary) - offset, 'target': target})
        item = {'bufferView': view, 'componentType': component, 'count': len(values) // size,
                'type': {1: 'SCALAR', 2: 'VEC2', 3: 'VEC3', 4: 'VEC4'}[size]}
        if component == 5126:
            item['min'] = [min(values[i::size]) for i in range(size)]
            item['max'] = [max(values[i::size]) for i in range(size)]
        document['accessors'].append(item)
        return len(document['accessors']) - 1

    material_ids = {}
    material_sources = {}
    def emit(model):
        for material in model['materials']:
            if material['id'] in material_ids:
                if material != material_sources[material['id']]:
                    raise ValueError('Conflicting material between LODs: '+material['id'])
                continue
            material_sources[material['id']] = material
            material_ids[material['id']] = len(document['materials'])
            color = material.get('diffuse', [1, 1, 1])
            roughness, metallic = material.get('roughness', 1), material.get('metallic', 0)
            if not (math.isfinite(roughness) and 0 <= roughness <= 1
                    and math.isfinite(metallic) and 0 <= metallic <= 1):
                raise ValueError('Metallic and roughness factors must be finite values in [0, 1]')
            document['materials'].append({'name': material['id'], 'pbrMetallicRoughness': {
                'baseColorFactor': [*(c if linear_colors else linear(c) for c in color[:3]),
                                    material.get('opacity', 1)],
                'metallicFactor': metallic, 'roughnessFactor': roughness}})
            if 'alphaTest' in material:
                document['materials'][-1].update(alphaMode='MASK', alphaCutoff=material['alphaTest'])
            elif material.get('alphaMode') == 'BLEND':
                document['materials'][-1]['alphaMode'] = 'BLEND'
            if material.get('doubleSided'):
                document['materials'][-1]['doubleSided'] = True
            if material.get('extras'):
                document['materials'][-1]['extras'] = material['extras']
            if 'emissive' in material:
                emission = material['emissive']
                if len(emission) != 3 or any(not math.isfinite(c) or not 0 <= c <= 1 for c in emission):
                    raise ValueError('Emissive factors must be three finite values in [0, 1]')
                document['materials'][-1]['emissiveFactor'] = [c if linear_colors else linear(c) for c in emission]
            textures = material.get('textures', [])
            if len({t['type'] for t in textures}) != len(textures):
                raise ValueError('Duplicate material texture role')
            for texture in textures:
                if texture['type'] not in ('DIFFUSE', 'NORMAL', 'AMBIENT', 'METALLIC_ROUGHNESS', 'EMISSIVE'):
                    raise ValueError('Expected diffuse, normal, occlusion, metallic-roughness or emissive texture')
                index = len(document.setdefault('images', []))
                filename = texture['filename']
                encoded_image = texture.get('data')
                if encoded_image is None:
                    document['images'].append({'uri': filename})
                else:
                    while len(binary) % 4:
                        binary.append(0)
                    view = len(document['bufferViews'])
                    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(encoded_image)})
                    binary.extend(encoded_image)
                    mime = 'image/png' if encoded_image.startswith(b'\x89PNG') else 'image/jpeg'
                    document['images'].append({'name': filename, 'bufferView': view, 'mimeType': mime})
                sampler = {'wrapS': texture.get('wrapS', 10497), 'wrapT': texture.get('wrapT', 10497),
                           'minFilter': texture.get('minFilter', 9987), 'magFilter': texture.get('magFilter', 9729)}
                samplers = document.setdefault('samplers', [])
                if sampler not in samplers:
                    samplers.append(sampler)
                document.setdefault('textures', []).append({'source': index, 'sampler': samplers.index(sampler)})
                if texture['type'] == 'DIFFUSE':
                    document['materials'][-1]['pbrMetallicRoughness']['baseColorTexture'] = {'index': index}
                elif texture['type'] == 'NORMAL':
                    document['materials'][-1]['normalTexture'] = {'index': index}
                elif texture['type'] == 'METALLIC_ROUGHNESS':
                    document['materials'][-1]['pbrMetallicRoughness']['metallicRoughnessTexture'] = {'index': index}
                elif texture['type'] == 'EMISSIVE':
                    document['materials'][-1]['emissiveTexture'] = {'index': index}
                else:
                    document['materials'][-1]['occlusionTexture'] = {'index': index}

        parts = {}
        for mesh in model['meshes']:
            stride = sum(STRIDES[name] for name in mesh['attributes'])
            count = len(mesh['vertices']) // stride
            if not count:
                continue
            attributes, offset = {}, 0
            for name in mesh['attributes']:
                size = STRIDES[name]
                values = []
                rows = [mesh['vertices'][index * stride + offset:index * stride + offset + size] for index in range(count)]
                if name == 'COLOR' and not mesh.get('colorData', False):
                    if not linear_colors:
                        rows = [[*(linear(c) for c in value[:3]), value[3]] for value in rows]
                    at = sum(STRIDES[other] for other in mesh['attributes'][:mesh['attributes'].index('POSITION')])
                    positions = [mesh['vertices'][index * stride + at:index * stride + at + 3] for index in range(count)]
                    for part in mesh['parts']:
                        fit_colours(rows, positions, part['indices'])
                for value in rows:
                    if name in ('POSITION', 'NORMAL'):
                        value = y_up(value)
                    if not all(math.isfinite(c) for c in value):
                        raise ValueError('Non-finite vertex')
                    values.extend(value)
                attributes[SEMANTICS[name]] = accessor(values, size)
                offset += size
            if any(mesh.get('slots', ())):
                if len(mesh['slots']) != count or not all(0 <= slot <= 4 for slot in mesh['slots']):
                    raise ValueError('Expected one colour slot from 0 to 4 per vertex')
                attributes['_COLOUR_SLOT'] = accessor([float(slot) for slot in mesh['slots']], 1)
            for part in mesh['parts']:
                if part['type'] != 'TRIANGLES' or len(part['indices']) % 3:
                    raise ValueError('Expected triangle parts')
                if not part['indices'] or min(part['indices']) < 0 or max(part['indices']) >= count:
                    raise ValueError('Invalid vertex index')
                indices = accessor(part['indices'], 1, 5123 if count <= 65535 else 5125, 34963)
                parts[part['id']] = {'attributes': attributes, 'indices': indices, 'mode': 4,
                                     'extras': {'mmPart': part['id']}}
                if mesh.get('colorData', False):
                    parts[part['id']]['extras']['mmColorData'] = True

        def node(source):
            index = len(document['nodes'])
            entry = {'name': source['id']}
            document['nodes'].append(entry)
            if 'translation' in source:
                entry['translation'] = y_up(source['translation'])
            if 'rotation' in source:
                entry['rotation'] = [*y_up(source['rotation'][:3]), source['rotation'][3]]
            if 'scale' in source:
                x, y, z = source['scale']
                entry['scale'] = [x, z, y]
            if source.get('parts'):
                primitives = [{**parts[p['meshpartid']], **({'material': material_ids[p['materialid']]}
                                                             if p.get('materialid') else {})}
                              for p in source['parts']]
                entry['mesh'] = len(document['meshes'])
                document['meshes'].append({'name': source['id'], 'primitives': primitives})
            if source.get('children'):
                entry['children'] = [node(child) for child in source['children']]
            return index

        return [node(n) for n in model['nodes']]

    if levels is None:
        document['scenes'][0]['nodes'] = emit(model)
    else:
        if 0 not in levels or not set(levels) <= {0, 1, 2, 3}:
            raise ValueError('LOD0 is required; supported levels are 0, 1, 2, 3')
        for level, geometry in sorted(levels.items()):
            children = emit(geometry)
            index = len(document['nodes'])
            document['nodes'].append({'name': f'{Path(path).stem}-lod{level}', 'children': children})
            document['scenes'][0]['nodes'].append(index)
    for name, geometry in (groups or {}).items():
        children = emit(geometry)
        document['scenes'][0]['nodes'].append(len(document['nodes']))
        document['nodes'].append({'name': name, 'children': children})
    def restore(node):
        children = [restore(child) for child in node['children']]
        item = {key: value for key, value in node.items() if key != 'children'}
        if children:
            item['children'] = children
        index = len(document['nodes'])
        document['nodes'].append(item)
        return index

    for node in retained:
        document['scenes'][0]['nodes'].append(restore(node))
    if binary:
        document['buffers'] = [{'byteLength': len(binary)}]
    if extras:
        document['extras'] = extras
    # Empty formation references have a rig but no geometry or binary chunk.
    document = {key: value for key, value in document.items() if value != []}
    encoded = json.dumps(document, separators=(',', ':'), allow_nan=False).encode('utf-8')
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    data = struct.pack('<III', 0x46546c67, 2, 20 + len(encoded) + (8 + len(binary) if binary else 0))
    data += struct.pack('<II', len(encoded), 0x4e4f534a) + encoded
    if binary:
        data += struct.pack('<II', len(binary), 0x004e4942) + binary
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_glb(path, level=0, *, linear_colors=False):
    """Read rigid exports; opt into original linear pigment values without a transfer roundtrip."""
    raw = Path(path).read_bytes()
    magic, version, length = struct.unpack_from('<III', raw)
    if (magic, version, length) != (0x46546c67, 2, len(raw)):
        raise ValueError('Invalid GLB header')
    json_length, json_type = struct.unpack_from('<II', raw, 12)
    if json_type != 0x4e4f534a:
        raise ValueError('Expected GLB JSON')
    document = json.loads(raw[20:20 + json_length])
    binary = b''
    if 20 + json_length < len(raw):
        binary_length, binary_type = struct.unpack_from('<II', raw, 20 + json_length)
        if binary_type != 0x004e4942:
            raise ValueError('Expected GLB binary buffer')
        binary = raw[28 + json_length:28 + json_length + binary_length]

    def values(index):
        item = document['accessors'][index]
        view = document['bufferViews'][item['bufferView']]
        size = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[item['type']]
        code = {5126: 'f', 5123: 'H', 5125: 'I'}[item['componentType']]
        stride = view.get('byteStride', struct.calcsize('<' + code) * size)
        offset = view.get('byteOffset', 0) + item.get('byteOffset', 0)
        return [list(struct.unpack_from('<' + code * size, binary, offset + i * stride))
                for i in range(item['count'])]

    roots = document['scenes'][document.get('scene', 0)]['nodes']
    groups = {document['nodes'][i]['name']: i for i in roots}
    name = f'{Path(path).stem}-lod{level}'
    if any(key.startswith(Path(path).stem + '-lod') and 'mesh' not in document['nodes'][index]
           for key, index in groups.items()):
        if name not in groups:
            raise ValueError(f'Missing {name}')
        roots = document['nodes'][groups[name]]['children']
    used = set()
    def visit(index):
        node = document['nodes'][index]
        if 'mesh' in node:
            used.add(node['mesh'])
        for child in node.get('children', []):
            visit(child)
    for index in roots:
        visit(index)

    vertices, slots, parts, layouts, mesh_parts = [], [], [], {}, {}
    color_domains = set()

    for mesh_index in sorted(used):
        mesh = document['meshes'][mesh_index]
        references = []
        for part_index, primitive in enumerate(mesh['primitives']):
            data_colors = primitive.get('extras', {}).get('mmColorData', False)
            color_domains.add(data_colors)
            if len(color_domains) > 1:
                raise ValueError('The review mesh cannot mix pigment and numeric COLOR_0')
            attrs = primitive['attributes']
            layout = tuple(sorted(attrs.items()))
            if layout not in layouts:
                layouts[layout] = len(vertices) // 12
                position, normals = values(attrs['POSITION']), values(attrs['NORMAL'])
                colors = values(attrs['COLOR_0']) if 'COLOR_0' in attrs else [[1, 1, 1, 1]] * len(position)
                uvs = values(attrs['TEXCOORD_0']) if 'TEXCOORD_0' in attrs else [[0, 0]] * len(position)
                for p, n, c, uv in zip(position, normals, colors, uvs):
                    vertices.extend([*z_up(p), *z_up(n), *(v if linear_colors or data_colors else display(v) for v in c[:3]),
                                     c[3] if len(c) == 4 else 1.0, *uv])
                slot_values = values(attrs['_COLOUR_SLOT']) if '_COLOUR_SLOT' in attrs else [[0]] * len(position)
                slots.extend(round(v[0]) for v in slot_values)
            part_id = primitive.get('extras', {}).get('mmPart', f'{mesh_index}-{part_index}')
            indices = [i[0] + layouts[layout] for i in values(primitive['indices'])]
            parts.append({'id': part_id, 'type': 'TRIANGLES', 'indices': indices})
            references.append({'meshpartid': part_id, 'materialid': document['materials'][primitive['material']]['name']})
        mesh_parts[mesh_index] = references

    def node(index):
        source = document['nodes'][index]
        result = {'id': source['name'], 'translation': z_up(source.get('translation', [0, 0, 0])),
                  'parts': mesh_parts[source['mesh']] if 'mesh' in source else [],
                  'children': [node(i) for i in source.get('children', [])]}
        if 'rotation' in source:
            result['rotation'] = [*z_up(source['rotation'][:3]), source['rotation'][3]]
        if 'scale' in source:
            x, y, z = source['scale']
            result['scale'] = [x, z, y]
        return result

    def material(source):
        # glTF's defaults: a material may leave out its factors (white, fully metallic and rough).
        pbr = source.get('pbrMetallicRoughness', {})
        factor = pbr.get('baseColorFactor', [1, 1, 1, 1])
        result = {'id': source['name'], 'diffuse': [v if linear_colors else display(v) for v in factor[:3]]}
        result.update(roughness=pbr.get('roughnessFactor', 1), metallic=pbr.get('metallicFactor', 1))
        if 'emissiveFactor' in source:
            result['emissive'] = [v if linear_colors else display(v) for v in source['emissiveFactor']]
        if source.get('alphaMode') == 'MASK':
            result['alphaTest'] = source.get('alphaCutoff', .5)
        elif source.get('alphaMode') == 'BLEND':
            result['alphaMode'] = 'BLEND'
        if source.get('extras'):
            result['extras'] = source['extras']
        for kind, info in (('DIFFUSE', pbr.get('baseColorTexture')), ('NORMAL', source.get('normalTexture')),
                           ('AMBIENT', source.get('occlusionTexture')),
                           ('METALLIC_ROUGHNESS', pbr.get('metallicRoughnessTexture')),
                           ('EMISSIVE', source.get('emissiveTexture'))):
            if info is None:
                continue
            if kind == 'NORMAL' and info.get('scale', 1) != 1:
                raise ValueError('Bake normal strength into the map')
            texture = document['textures'][info['index']]
            image = document['images'][texture['source']]
            entry = {'id': source['name'], 'type': kind, 'filename': image.get('uri', image.get('name'))}
            if 'bufferView' in image:
                view = document['bufferViews'][image['bufferView']]
                offset = view.get('byteOffset', 0)
                entry['data'] = bytes(binary[offset:offset + view['byteLength']])
            if 'sampler' in texture:
                entry.update(document['samplers'][texture['sampler']])
            result.setdefault('textures', []).append(entry)
        return result

    mesh = {'attributes': list(STRIDES), 'vertices': vertices, 'parts': parts}
    if color_domains == {True}:
        mesh['colorData'] = True
    if any(slots):
        mesh['slots'] = slots
    return {'id': Path(path).stem, 'extras': document.get('extras', {}),
            'meshes': [mesh] if vertices else [],
            'nodes': [node(i) for i in roots],
            'materials': [material(m) for m in document.get('materials', [])]}
