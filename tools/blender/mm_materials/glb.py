"""Lossless GLB container I/O and checks around Blender's mesh conversion."""
import json
import struct
import copy
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def read_glb(path):
    raw = Path(path).read_bytes()
    if len(raw) < 20 or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('Expected a GLB version 2 file')
    chunks, offset = {}, 12
    while offset < len(raw):
        size, kind = struct.unpack_from('<II', raw, offset)
        if offset + 8 + size > len(raw) or size % 4 or kind in chunks:
            raise ValueError('Invalid GLB chunk')
        chunks[kind] = raw[offset + 8:offset + 8 + size]
        offset += 8 + size
    if set(chunks) - {0x4E4F534A, 0x004E4942}:
        raise ValueError('Unknown GLB chunks cannot be preserved by Blender')
    return json.loads(chunks[0x4E4F534A]), chunks.get(0x004E4942, b'')


def write_glb(path, doc, binary):
    data = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    data += b' ' * (-len(data) % 4)
    chunks = struct.pack('<II', len(data), 0x4E4F534A) + data
    if binary:
        binary += b'\0' * (-len(binary) % 4)
        chunks += struct.pack('<II', len(binary), 0x004E4942) + binary
    Path(path).write_bytes(struct.pack('<4sII', b'glTF', 2, len(chunks) + 12) + chunks)


def prepare_import(document, binary):
    """Blender removes duplicate/reversed faces that share vertices (foliage cards).

    Give affected primitives separate triangle vertices in a temporary import copy.
    Attribute bytes, winding, material assignment, and the source file stay unchanged.
    """
    doc, data, changed = copy.deepcopy(document), bytearray(binary), False

    def rows(index):
        accessor = doc['accessors'][index]
        if 'sparse' in accessor:
            raise ValueError('Sparse accessors are not supported for duplicate-face preservation')
        view = doc['bufferViews'][accessor['bufferView']]
        width = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[accessor['componentType']]
        size = width * {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        return [bytes(data[offset + i * view.get('byteStride', size):offset + i * view.get('byteStride', size) + size])
                for i in range(accessor['count'])]

    def append_accessor(template, values, target):
        data.extend(b'\0' * (-len(data) % 4))
        payload = b''.join(values)
        view = len(doc['bufferViews'])
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(data), byteLength=len(payload), target=target))
        data.extend(payload)
        accessor = {k: v for k, v in template.items() if k not in ('bufferView', 'byteOffset', 'sparse')}
        accessor.update(bufferView=view, count=len(values))
        doc['accessors'].append(accessor)
        return len(doc['accessors']) - 1

    for mesh in doc.get('meshes', []):
        for primitive in mesh['primitives']:
            if 'indices' not in primitive:
                continue
            source = doc['accessors'][primitive['indices']]
            code = {5121: 'B', 5123: 'H', 5125: 'I'}[source['componentType']]
            indices = [struct.unpack('<' + code, row)[0] for row in rows(primitive['indices'])]
            faces = [tuple(sorted(indices[i:i + 3])) for i in range(0, len(indices), 3)]
            if any(len(set(face)) != 3 for face in faces):
                raise ValueError('GLB contains degenerate indexed triangles; repair the source mesh first')
            if len(set(faces)) == len(faces):
                continue
            changed = True
            for key, index in list(primitive['attributes'].items()):
                values = rows(index)
                primitive['attributes'][key] = append_accessor(doc['accessors'][index], [values[i] for i in indices], 34962)
            primitive['indices'] = append_accessor(dict(type='SCALAR', componentType=5125),
                                                   [struct.pack('<I', i) for i in range(len(indices))], 34963)
    if changed:
        data.extend(b'\0' * (-len(data) % 4))
        doc['buffers'][0]['byteLength'] = len(data)
    return doc, bytes(data), changed


def image_path(glb, uri):
    parsed = urlsplit(uri)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or '\\' in uri or parsed.path.startswith('/'):
        raise ValueError(f'Textures must use local relative paths: {uri}')
    return (Path(glb).parent / unquote(parsed.path)).resolve()


def library_resource(image, textures):
    """The library .tres, relative to textures, that this albedo image file belongs to, or None."""
    if image.name.endswith('_albedo.png'):
        resource = image.with_name(image.name[:-11] + '.tres')
        if resource.is_relative_to(textures) and resource.is_file():
            return resource.relative_to(textures).as_posix()
    return None


def kit_pieces(path):
    """A building kit's modelled pieces (GeneratedKit), known by the file's name."""
    return Path(path).name.endswith('-pieces.glb')


def kit_material(doc, material, path, textures):
    """The library material a kit piece draws as, the one its albedo image belongs to (without .tres), or None."""
    texture = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
    uri = doc['images'][doc['textures'][texture['index']]['source']].get('uri') if texture else None
    resource = library_resource(image_path(path, uri), textures) if uri else None
    return resource.removesuffix('.tres') if resource else None


def check_kit_materials(doc, path, textures):
    """A building kit draws its pieces as the library materials their albedo images belong to."""
    for material in doc.get('materials', []):
        if not kit_material(doc, material, path, textures):
            raise ValueError(f"A building kit's pieces use library materials only, not {material.get('name')}")


def prepare_kit_materials(doc, path, textures):
    """The game reads a piece's library material from its material's name, up to a '#' finish (GeneratedMesh#boardName)."""
    for material in doc.get('materials', []):
        board = kit_material(doc, material, path, textures)
        if board and material.get('name', '').split('#')[0] != board:
            material['name'] = board
        # Blender's copy for a piece without UVs (texCoord -1), which the kit lays on the walls' axes, is the material.
        for texture in [*material.values(), *material.get('pbrMetallicRoughness', {}).values()]:
            if isinstance(texture, dict) and texture.get('texCoord') == -1:
                texture['texCoord'] = 0
    # Blender's copies of one material become one; finishes of one library material that still differ are numbered.
    merge_identical_materials(doc)
    names = set()
    for material in doc.get('materials', []):
        name, count = material.get('name'), 1
        while name and material['name'] in names:
            count += 1
            material['name'] = f'{name}#{count}'
        names.add(material.get('name'))


def check_part_names(doc):
    """The game refuses a level of detail that names two parts alike."""
    for root in doc['scenes'][0].get('nodes', []):
        parts, meshes, pending = set(), set(), [root]
        while pending:
            node = doc['nodes'][pending.pop()]
            meshes.update([node['mesh']] if 'mesh' in node else [])
            pending.extend(node.get('children', []))
        for mesh in meshes:
            for primitive in doc['meshes'][mesh]['primitives']:
                part = primitive.get('extras', {}).get('mmPart')
                if part in parts:
                    raise ValueError(f'Part names must be unique in a level of detail: {part}')
                parts.update([part] if part else [])


def validate(doc, path, models_root):
    if doc.get('skins') or doc.get('animations') or doc.get('extensionsRequired'):
        raise ValueError('This editor supports rigid GLBs without required extensions or animation tracks')
    if len(doc.get('scenes', [])) != 1 or doc.get('scene') != 0:
        raise ValueError('Expected one scene containing all model LODs')
    if len(doc.get('buffers', [])) > 1 or any('uri' in b for b in doc.get('buffers', [])):
        raise ValueError('GLB geometry must be embedded')
    for image in doc.get('images', []):
        if image.get('mimeType') not in (None, 'image/png', 'image/jpeg'):
            raise ValueError('The game supports PNG and JPEG textures')
        if 'uri' in image:
            resolved = image_path(path, image['uri'])
            if not resolved.is_relative_to(models_root.resolve()) or not resolved.is_file():
                raise ValueError(f'Missing texture or texture outside data/models: {resolved}')
            if resolved.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                raise ValueError('The game supports PNG and JPEG textures')
    # Ground-cut helper meshes carry only positions; the renderer does not draw them.
    cut_meshes, drawn_meshes = set(), set()
    def visit(index, cut=False):
        node = doc['nodes'][index]
        if 'mesh' in node:
            (cut_meshes if cut else drawn_meshes).add(node['mesh'])
        for child in node.get('children', []):
            visit(child, cut)
    for index in doc['scenes'][0].get('nodes', []):
        visit(index, doc['nodes'][index].get('name') == 'cut')
    for mesh_index, mesh in enumerate(doc.get('meshes', [])):
        for primitive in mesh['primitives']:
            if primitive.get('mode', 4) != 4 or primitive.get('targets'):
                raise ValueError('Expected rigid triangle meshes without shape keys')
            if set(primitive['attributes']) - {'POSITION', 'NORMAL', 'COLOR_0', 'TEXCOORD_0', '_COLOUR_SLOT'}:
                raise ValueError('The game supports one UV set, one vertex colour set and _COLOUR_SLOT')
            needs_normal = mesh_index not in cut_meshes or mesh_index in drawn_meshes
            if 'POSITION' not in primitive['attributes'] or (needs_normal and 'NORMAL' not in primitive['attributes']):
                raise ValueError('Mesh needs positions and normals')
            if needs_normal and primitive.get('material') is None:
                raise ValueError('Assign a named material to every rendered mesh face before exporting')
    check_part_names(doc)
    if kit_pieces(path):
        check_kit_materials(doc, path, models_root.resolve() / 'board/textures')
    names = set()
    for material in doc.get('materials', []):
        name = material.get('name')
        if not name or name in names:
            raise ValueError(f'Material names must be unique: {name}. Rename the conflicting material in Blender')
        names.add(name)
        emission = material.get('extras', {}).get('mmEmission')
        if emission is not None and emission not in ('always', 'night', 'off'):
            raise ValueError(f'{name}: mmEmission must be always, night or off, not {emission}')
        strength = material.get('extensions', {}).get('KHR_materials_emissive_strength', {}).get('emissiveStrength', 1)
        if strength != 1:
            raise ValueError('The engine does not read KHR_materials_emissive_strength; keep GLB emission within 0–1, '
                             'or author higher emission energy in a shared .tres material')
        for key, texture in list(material.items()) + list(material.get('pbrMetallicRoughness', {}).items()):
            if key.endswith('Texture') and isinstance(texture, dict):
                if texture.get('texCoord', 0) != 0 or texture.get('extensions', {}).get('KHR_texture_transform'):
                    raise ValueError('Use the first UV map and edit its UVs directly; texture transforms are unsupported')
                if key == 'normalTexture' and texture.get('scale', 1) != 1:
                    raise ValueError('For non-library materials, bake normal strength into the map')
                if key == 'occlusionTexture' and texture.get('strength', 1) != 1:
                    raise ValueError('For non-library materials, bake occlusion strength into the map')
        for uri in material.get('extras', {}).get('mmSnow', {}).get('textures', {}).values():
            resolved = image_path(path, uri)
            if not resolved.is_file() or not resolved.is_relative_to(models_root.resolve()):
                raise ValueError(f'Missing snow texture: {resolved}')


def ensure_lod_groups(doc, name):
    """Give new meshes the identity LOD root required by RigidGlb.loadLods."""
    nodes = doc.setdefault('nodes', [])
    scene = doc['scenes'][doc.get('scene', 0)]
    # Beside its levels a model's roots may hold data: RigidGlb.CUT, STANDS, SPORES and BuildingVolumes.helper.
    roots = [i for i in scene.get('nodes', []) if nodes[i].get('name') not in ('cut', 'stands', 'spores')
             and not nodes[i].get('name', '').startswith('building_volume')]
    if not roots or not doc.get('meshes'):
        raise ValueError('Select at least one mesh to export')
    levels = [re.fullmatch(r'.+-lod([0-3])', nodes[i].get('name', '')) for i in roots]
    if not any(levels):
        scene['nodes'] = [i for i in scene.get('nodes', []) if i not in roots] + [len(nodes)]
        nodes.append(dict(name=name + '-lod0', children=roots))
        return
    if not all(levels):
        raise ValueError('Place loose meshes inside an existing LOD group, or export those meshes separately')
    if len({m[1] for m in levels}) != len(levels) or '0' not in {m[1] for m in levels}:
        raise ValueError('Use one group per LOD, including LOD0')
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    for i in roots:
        node = nodes[i]
        if ('mesh' in node or not node.get('children') or node.get('matrix', identity) != identity
                or node.get('translation', [0, 0, 0]) != [0, 0, 0]
                or node.get('rotation', [0, 0, 0, 1]) != [0, 0, 0, 1]
                or node.get('scale', [1, 1, 1]) != [1, 1, 1]):
            raise ValueError('LOD roots must be empty groups with identity transforms; transform their children')


def merge_identical_materials(doc):
    """Blender may create separate copies for vertex-colour use or selected objects."""
    def deduplicate(key):
        unique, indices, mapping = [], {}, {}
        for index, item in enumerate(doc.get(key, [])):
            signature = json.dumps(item, sort_keys=True)
            if signature not in indices:
                indices[signature] = len(unique)
                unique.append(item)
            mapping[index] = indices[signature]
        if key in doc:
            doc[key] = unique
        return mapping

    image_map, sampler_map = deduplicate('images'), deduplicate('samplers')
    for texture in doc.get('textures', []):
        if 'source' in texture:
            texture['source'] = image_map[texture['source']]
        if 'sampler' in texture:
            texture['sampler'] = sampler_map[texture['sampler']]
    texture_map = deduplicate('textures')

    def texture_indices(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith('Texture') and isinstance(child, dict) and 'index' in child:
                    child['index'] = texture_map[child['index']]
                elif key != 'extras':
                    texture_indices(child)
    for material in doc.get('materials', []):
        texture_indices(material)
    materials, indices, remap = [], {}, {}
    for index, material in enumerate(doc.get('materials', [])):
        key = json.dumps(material, sort_keys=True)
        if key not in indices:
            indices[key] = len(materials)
            materials.append(material)
        remap[index] = indices[key]
    doc['materials'] = materials
    for mesh in doc.get('meshes', []):
        for primitive in mesh['primitives']:
            if 'material' in primitive:
                primitive['material'] = remap[primitive['material']]


def strip_editor_properties(value):
    if isinstance(value, dict):
        extras = value.get('extras')
        if isinstance(extras, dict):
            for key in list(extras):
                if key.startswith('_mm_') or key in ('mm_materials', 'mm_asset_test', 'mm_palette'):
                    del extras[key]
            if not extras:
                del value['extras']
        for child in value.values():
            strip_editor_properties(child)
    elif isinstance(value, list):
        for child in value:
            strip_editor_properties(child)
