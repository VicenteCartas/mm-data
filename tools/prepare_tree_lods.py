"""Run with Blender --background --python tools/prepare_tree_lods.py -- impostors [names...].

The command adds LOD3 to existing plant GLBs: three textured cards standing for LOD2, the level they replace, while
preserving their three mesh levels. Each card carries two renders of LOD2 from its side: its unlit colour, and its
surface's normal and depth, so the game lights and shadows each texel as it does LOD2's surface (terrain-foliage.frag).
"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from glb_geometry import read_glb, write_glb

import copy
import json
import math

import bpy
import numpy
from mathutils import Euler, Matrix, Vector

BOARD = Path(__file__).resolve().parents[1] / 'data/models/board'
# The plant GLBs; their texture paths are relative to this folder.
PLANTS = BOARD / 'vegetation'
# The plants' levels and sources: tool data, never shipped.
MANIFEST = Path(__file__).resolve().parent / 'board-models/manifest.json'
IMPOSTORS = 'textures/vegetation/impostors'
# Pixels per card face; the game draws the cards only below TreeLod's smallest threshold.
PANEL = 128
# Each panel renders at this many times its texels, then averages them by alpha, as the game's cutout mip levels do
# (GpuColorTexture.cutout): a texel keeps the colour of the leaves it shows and the share of it they cover.
SAMPLES = 4
# A material's surface response where it has no occlusion map, as terrain-foliage.frag assumes: occlusion, roughness,
# scatter.
SURFACE = (1, .58, .35)


def counts(model):
    mesh = model['meshes'][0]
    return {'triangles': sum(len(part['indices']) // 3 for part in mesh['parts']),
            'vertices': len(mesh['vertices']) // 12}


def solid(role):
    """Roles the game lights as solid rather than as a canopy (GpuTerrain.foliage)."""
    return role.startswith('bark') or role in ('cactus', 'fruit', 'coral')


def leaf(role):
    """Roles the game lights as leaves (GpuTerrain.foliage's part 1): neither solid, snow nor fungal tissue."""
    return not solid(role) and role not in ('fungus', 'mycelium', 'snow', 'canopy-snow-cutout')


def material_roles(model):
    """A split variant can rename a material while retaining the original meshpart ID."""
    roles = {}
    def visit(node):
        for part in node.get('parts', []):
            roles[part['meshpartid']] = part['materialid']
        for child in node.get('children', []):
            visit(child)
    for node in model['nodes']:
        visit(node)
    return roles


def unlit_material(role, filename, images, cutout=False, alpha_test=.5):
    """Unlit pigment; the impostor bake filters sRGB textures in linear light. A cutout (`-cutout` or alpha-tested)
    keeps only its texture's opaque texels."""
    material = bpy.data.materials.new(role)
    # Blender renames a material whose name is taken; the role stays here.
    material['role'] = role
    material.use_nodes = True
    material.use_backface_culling = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    if filename not in images:
        # The bake owns its image copies; never change an open scene's existing image color space.
        images[filename] = bpy.data.images.load(str(PLANTS / filename), check_existing=False)
        images[filename].colorspace_settings.name = 'sRGB'
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = images[filename]
    texture.interpolation = 'Linear'
    color = nodes.new('ShaderNodeVertexColor')
    color.layer_name = 'Color'
    product = nodes.new('ShaderNodeVectorMath')
    product.operation = 'MULTIPLY'
    links.new(texture.outputs['Color'], product.inputs[0])
    links.new(color.outputs['Color'], product.inputs[1])
    albedo = product.outputs[0]
    # Snow uses its authored texture and vertex pigment, just like the runtime foliage shader.
    emission = nodes.new('ShaderNodeEmission')
    links.new(albedo, emission.inputs['Color'])
    output = nodes.new('ShaderNodeOutputMaterial')
    if cutout or role.endswith('-cutout'):
        threshold = nodes.new('ShaderNodeMath')
        threshold.operation = 'GREATER_THAN'
        threshold.inputs[1].default_value = alpha_test
        links.new(texture.outputs['Alpha'], threshold.inputs[0])
        transparent = nodes.new('ShaderNodeBsdfTransparent')
        mix = nodes.new('ShaderNodeMixShader')
        links.new(threshold.outputs[0], mix.inputs[0])
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(emission.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs['Surface'])
        if hasattr(material, 'surface_render_method'):
            material.surface_render_method = 'DITHERED'
        elif hasattr(material, 'blend_method'):
            material.blend_method = 'CLIP'
    else:
        links.new(emission.outputs[0], output.inputs['Surface'])
    return material


def unlit_mesh(model, name, images):
    """A mesh level with one vertex per corner, so every authored colour, normal and texture coordinate survives."""
    mesh = model['meshes'][0]
    source = mesh['vertices']
    textures = {material['id']: material['textures'][0]['filename'] for material in model['materials']}
    cutouts = {material['id']: material['alphaTest'] for material in model['materials'] if 'alphaTest' in material}
    bound_roles = material_roles(model)
    vertices, faces, normals, colors, uvs, roles = [], [], [], [], [], []
    for part in mesh['parts']:
        for offset in range(0, len(part['indices']), 3):
            faces.append((len(vertices), len(vertices) + 1, len(vertices) + 2))
            roles.append(bound_roles[part['id']])
            for index in part['indices'][offset:offset + 3]:
                vertex = source[index * 12:index * 12 + 12]
                vertices.append(vertex[:3])
                normals.append(vertex[3:6])
                # The impostor reads the original linear glTF RGB.
                colors.append(vertex[6:10])
                uvs.append((vertex[10], 1 - vertex[11]))
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    color = data.color_attributes.new('Color', 'FLOAT_COLOR', 'CORNER')
    uv = data.uv_layers.new(name='UV')
    for polygon in data.polygons:
        polygon.use_smooth = True
        for loop in polygon.loop_indices:
            color.data[loop].color = colors[data.loops[loop].vertex_index]
            uv.data[loop].uv = uvs[data.loops[loop].vertex_index]
    # The authored normals (a card's crown envelope normal), which the normal render shows.
    data.normals_split_custom_set([normals[data.loops[loop].vertex_index] for loop in range(len(data.loops))])
    materials = {}
    for polygon, role in zip(data.polygons, roles):
        if role not in materials:
            materials[role] = len(data.materials)
            data.materials.append(unlit_material(role, textures[role], images, role in cutouts, cutouts.get(role, .5)))
        polygon.material_index = materials[role]
    data.update()
    return data


def show(data, model, shown, images):
    """The unlit materials of `data` emit `shown` instead of their pigment, on the same cutout texels: 'normal' (the
    world-space normal as 0..1), 'position' (the world-space position, a quarter of it about .5), 'surface' (the
    material's occlusion map, or SURFACE) or 'solid' (0 for leaves, 1 for the roles the game lights otherwise)."""
    occlusion = {material['id']: next((t['filename'] for t in material['textures'] if t['type'] == 'AMBIENT'), None)
                 for material in model['materials']}
    for material in data.materials:
        role = material['role']
        nodes, links = material.node_tree.nodes, material.node_tree.links
        emission = next(node for node in nodes if node.type == 'EMISSION')
        if shown in ('normal', 'position'):
            geometry = nodes.new('ShaderNodeNewGeometry')
            scaled = nodes.new('ShaderNodeVectorMath')
            scaled.operation = 'MULTIPLY_ADD'
            scaled.inputs[1].default_value = (.5,) * 3 if shown == 'normal' else (.25,) * 3
            scaled.inputs[2].default_value = (.5,) * 3
            links.new(geometry.outputs['Normal' if shown == 'normal' else 'Position'], scaled.inputs[0])
            links.new(scaled.outputs[0], emission.inputs['Color'])
        elif shown == 'surface' and occlusion.get(role):
            key = 'data:' + occlusion[role]
            if key not in images:
                images[key] = bpy.data.images.load(str(PLANTS / occlusion[role]), check_existing=False)
                images[key].colorspace_settings.name = 'Non-Color'
            texture = nodes.new('ShaderNodeTexImage')
            texture.image = images[key]
            texture.interpolation = 'Linear'
            links.new(texture.outputs['Color'], emission.inputs['Color'])
        else:
            for link in list(emission.inputs['Color'].links):
                links.remove(link)
            value = SURFACE if shown == 'surface' else (0, 0, 0) if leaf(role) else (1, 1, 1)
            emission.inputs['Color'].default_value = (*value, 1)


def bounds(model):
    vertices = model['meshes'][0]['vertices']
    return [min(vertices[i::12]) for i in range(3)], [max(vertices[i::12]) for i in range(3)]


def crown(model, low, high):
    """Height of the cap: the canopy's mean height, or the middle of a plant without one."""
    mesh = model['meshes'][0]
    heights = [mesh['vertices'][index * 12 + 2] for part in mesh['parts'] if not solid(part['id'])
               for index in part['indices']]
    return sum(heights) / len(heights) if heights else (low[2] + high[2]) / 2


# The board camera looks down at trees, so the vertical cards show the plant from this elevation: the canopy then
# covers the trunk as it would in three dimensions, while the cap alone shows from straight above.
ELEVATION = math.radians(30)
# The turns that bring each card's face toward a camera at -y: the front and side faces, each turned about the
# plant's axis before it tips toward the camera (tipping first would roll the side view), then the top.
FACES = tuple((Matrix.Rotation(ELEVATION, 3, 'X') @ Matrix.Rotation(turn, 3, 'Z')).to_euler()
              for turn in (0, -math.pi / 2)) + (Euler((math.pi / 2, 0, 0)),)


def framing(turn, low, high):
    """The square panel framing the turned plant: its size and centre, in the camera's right and up axes."""
    rotation = turn.to_matrix()
    corners = [rotation @ Vector((x, y, z)) for x in (low[0], high[0]) for y in (low[1], high[1])
               for z in (low[2], high[2])]
    lowest = Vector((min(c.x for c in corners), 0, min(c.z for c in corners)))
    highest = Vector((max(c.x for c in corners), 0, max(c.z for c in corners)))
    # A little margin keeps the dilated rim inside its own panel.
    return max(highest.x - lowest.x, highest.z - lowest.z) * 1.04, (lowest + highest) / 2


def dilate(values, filled, passes=8):
    """Spread the covered texels' values into the empty ones around them, so filtering and mipmaps never mix in the
    empty texels around a cutout."""
    values, filled = values.copy(), filled.copy()
    for _ in range(passes):
        if filled.all():
            break
        for shift in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            take = ~filled & numpy.roll(filled, shift, (0, 1))
            values[take] = numpy.roll(values, shift, (0, 1))[take]
            filled |= take
    return values


def render(scene, model, name, images, panels, shown):
    """`model` turned toward the camera three times, each face filling its own square panel at SAMPLES times its
    texels, its materials showing `shown` (its unlit colour, or show()'s): linear RGBA premultiplied by coverage, rows
    top-down, averaged down to PANEL texels a panel side."""
    data = unlit_mesh(model, name, images)
    if shown != 'colour':
        show(data, model, shown, images)
    objects = []
    for panel, (turn, (size, centre)) in enumerate(zip(FACES, panels)):
        obj = bpy.data.objects.new(f'{name}-face{panel}', data)
        scene.collection.objects.link(obj)
        obj.rotation_euler = turn
        obj.scale = (1 / size,) * 3
        obj.location = (panel - 1 - centre.x / size, 0, -centre.z / size)
        objects.append(obj)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'render.exr'
        scene.render.filepath = str(path)
        try:
            bpy.ops.render.render(write_still=True)
        finally:
            for obj in objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            for material in list(data.materials):
                bpy.data.materials.remove(material)
            bpy.data.meshes.remove(data)
        image = bpy.data.images.load(str(path), check_existing=False)
        try:
            pixels = numpy.empty(len(image.pixels), dtype=numpy.float32)
            image.pixels.foreach_get(pixels)
        finally:
            bpy.data.images.remove(image)
    side = PANEL * SAMPLES
    pixels = pixels.reshape(side, 3 * side, 4)[::-1]
    return pixels.reshape(PANEL, SAMPLES, 3 * PANEL, SAMPLES, 4).mean(axis=(1, 3))


def unpremultiplied(rgba):
    """A render's linear values where it covers anything, and its coverage."""
    alpha = rgba[..., 3]
    return rgba[..., :3] / numpy.maximum(alpha, 1e-6)[..., None], alpha


def srgb(linear):
    linear = numpy.clip(linear, 0, 1)
    return numpy.where(linear <= .0031308, linear * 12.92, 1.055 * numpy.power(linear, 1 / 2.4) - .055)


def save(values, path):
    """RGBA values in 0..1, rows top-down, as an 8-bit PNG written as they are."""
    atlas = bpy.data.images.new(path.stem, values.shape[1], values.shape[0], alpha=True)
    atlas.colorspace_settings.name = 'Non-Color'
    atlas.pixels.foreach_set(numpy.ascontiguousarray(values[::-1], dtype=numpy.float32).ravel())
    atlas.filepath_raw = str(path)
    atlas.file_format = 'PNG'
    atlas.save()
    bpy.data.images.remove(atlas)


def impostor(scene, model, name, images):
    """LOD3: two crossed vertical cards and a horizontal cap through the crown, textured with orthographic renders of
    `model` (the plant's coarsest mesh level) from the front, the side and above. Fixed in the plant's frame, it draws,
    shadows and picks like any mesh; seen from above, only the cap shows. Each face has a back, as the game culls back
    faces; the back shows the same renders mirrored through its card.

    The colour atlas holds the unlit pigment and its coverage. The normal atlas holds, in its RGB, the normal of the
    surface each texel shows (signed, as n * 127 + 128) in the frame terrain-foliage.frag builds from the card: x along
    the texture's u, y across it about z, the card's vertex normal, which is the direction its render looked from; and,
    in its alpha, how far along that direction the surface stands out of the card (.5 the card itself, 0 and 1 a panel
    side behind and in front), where the game looks up its shadow. The vertical cards stretch the silhouette along v to
    fit it, so that point can lie up to a few units above or below the surface; measured against LOD2, placing it exactly
    (along y as well) matched worse. Each card's colour carries its texels' mean occlusion, the share of them that is
    bark, cactus or snow (lit as solid), and the mean roughness and scatter of the rest, the leaves, as their materials
    give them."""
    low, high = bounds(model)
    cap = crown(model, low, high)
    panels = [framing(turn, low, high) for turn in FACES]
    colour, covered = unpremultiplied(render(scene, model, name, images, panels, 'colour'))
    normals = unpremultiplied(render(scene, model, name, images, panels, 'normal'))[0] * 2 - 1
    positions = (unpremultiplied(render(scene, model, name, images, panels, 'position'))[0] - .5) * 4
    surface = unpremultiplied(render(scene, model, name, images, panels, 'surface'))[0]
    hard = unpremultiplied(render(scene, model, name, images, panels, 'solid'))[0][..., 0]
    filled = covered > 0
    # Texels far from the plant, which dilation leaves, read as the card itself.
    shape = numpy.tile(numpy.array((0, 0, 1, 0)), colour.shape[:2] + (1,)).astype(numpy.float64)
    vertices, indices, card = [], [], []
    corners = (((low[0], 0, low[2]), (high[0], 0, low[2]), (high[0], 0, high[2]), (low[0], 0, high[2])),
               ((0, low[1], low[2]), (0, high[1], low[2]), (0, high[1], high[2]), (0, low[1], high[2])),
               ((low[0], low[1], cap), (high[0], low[1], cap), (high[0], high[1], cap), (low[0], high[1], cap)))
    for panel, (quad, turn, (size, centre)) in enumerate(zip(corners, FACES, panels)):
        rotation = turn.to_matrix()
        positions_z = numpy.asarray(model['meshes'][0]['vertices']).reshape(-1, 12)[:, :3] @ numpy.asarray(rotation)[2]
        bottom, top = float(positions_z.min()), float(positions_z.max())
        toward = rotation.transposed() @ Vector((0, -1, 0))
        uvs = []
        for point in quad:
            # Each corner maps to where the render placed it, in the camera's right and up axes.
            seen = rotation @ Vector(point)
            if panel < 2:
                # Fit the actual tilted silhouette to the card, not the empty corners of its bounding box.
                # This preserves the whole crown and keeps its visible roots at the foot of the card.
                seen.z = bottom + (point[2] - low[2]) / (high[2] - low[2]) * (top - bottom)
            uvs.append(((panel + .5 + (seen.x - centre.x) / size) / 3, .5 - (seen.z - centre.z) / size))
        # The card's points by texture coordinate (affine: the card is a rectangle), and the frame the game builds.
        origin = numpy.asarray(quad[0])
        along_u = (numpy.asarray(quad[1]) - origin) / (uvs[1][0] - uvs[0][0])
        along_v = (numpy.asarray(quad[3]) - origin) / (uvs[3][1] - uvs[0][1])
        normal = numpy.asarray(toward)
        tangent = along_u - normal * (normal @ along_u)
        tangent /= numpy.linalg.norm(tangent)
        bitangent = numpy.cross(normal, tangent)
        if bitangent @ along_v < 0:
            bitangent = -bitangent
        block = slice(panel * PANEL, (panel + 1) * PANEL)
        u = (numpy.arange(panel * PANEL, (panel + 1) * PANEL) + .5) / (3 * PANEL)
        v = (numpy.arange(PANEL) + .5) / PANEL
        on_card = origin + (u[None, :, None] - uvs[0][0]) * along_u + (v[:, None, None] - uvs[0][1]) * along_v
        # The object's transform: location + rotation @ (point / size).
        location = numpy.array((panel - 1 - centre.x / size, 0, -centre.z / size))
        world = positions[:, block] - location
        point = world @ numpy.asarray(rotation) * size
        seen = normals[:, block] @ numpy.asarray(rotation)
        seen /= numpy.maximum(numpy.linalg.norm(seen, axis=2, keepdims=True), 1e-6)
        here = filled[:, block]
        # Signed: the normal in the card's frame, and the surface's depth along z in panel sides.
        shape[:, block, 0][here] = (seen @ tangent)[here]
        shape[:, block, 1][here] = (seen @ bitangent)[here]
        shape[:, block, 2][here] = (seen @ normal)[here]
        shape[:, block, 3][here] = ((point - on_card) @ normal / size)[here]
        weight = covered[:, block]
        total = max(float(weight.sum()), 1e-6)
        bark = float((hard[:, block] * weight).sum()) / total
        leaves = numpy.maximum(weight * (1 - hard[:, block]), 0)
        leaf_total = float(leaves.sum())
        mean = lambda channel, w, t: float((surface[:, block, channel] * w).sum()) / t if t > 1e-6 else SURFACE[channel]
        card.append((mean(0, weight, total), bark, mean(1, leaves, leaf_total), mean(2, leaves, leaf_total)))
        plane = (Vector(quad[1]) - Vector(quad[0])).cross(Vector(quad[2]) - Vector(quad[0])).normalized()
        # The back's renders are the front's mirrored through the card: so is the direction they looked from.
        for side, facing in enumerate((toward, toward - 2 * toward.dot(plane) * plane)):
            base = len(vertices) // 12
            for point, (tu, tv) in zip(quad, uvs):
                vertices.extend(round(value, 6) for value in (*point, *facing, *card[panel], tu, tv))
            indices.extend((base, base + 2, base + 1, base, base + 3, base + 2) if side
                           else (base, base + 1, base + 2, base, base + 2, base + 3))
    pigment = dilate(colour, filled)
    save(numpy.concatenate([srgb(pigment), covered[..., None]], axis=2), BOARD / IMPOSTORS / (name + '.png'))
    shape = dilate(shape, filled)
    save(numpy.concatenate([numpy.clip(shape[..., :3] * 127 + 128, 0, 255) / 255,
                            numpy.clip(shape[..., 3:] * .5 + .5, 0, 1)], axis=2), BOARD / IMPOSTORS / (name + '_normal.png'))
    asset = f'{name}-lod3'
    return {'id': asset,
            'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': vertices,
                        'colorData': True,
                        'parts': [{'id': 'impostor', 'type': 'TRIANGLES', 'indices': indices}]}],
            'nodes': [{'id': asset, 'parts': [{'meshpartid': 'impostor', 'materialid': 'impostor'}]}],
            'materials': [{'id': 'impostor', 'diffuse': [1, 1, 1], 'alphaTest': .5, 'textures': [
                {'id': 'impostor', 'type': 'DIFFUSE', 'filename': f'../{IMPOSTORS}/{name}.png',
                 'wrapS': 33071, 'wrapT': 33071},
                {'id': 'impostor-normal', 'type': 'NORMAL', 'filename': f'../{IMPOSTORS}/{name}_normal.png',
                 'wrapS': 33071, 'wrapT': 33071}]}]}


def winter(model):
    """A mesh level in its snow form (mmSnow on a canopy material): the snow maps under its name, the
    canopy's vertex colours times its linear colour scale, as the game builds the winter form (RigidGlb.source)."""
    variants = {material['id']: material['extras']['mmSnow'] for material in model['materials']
                if material['id'] != 'impostor' and 'mmSnow' in material.get('extras', {})}
    if not variants:
        return None
    result = copy.deepcopy(model)
    mesh = result['meshes'][0]
    roles = material_roles(model)
    for part in mesh['parts']:
        scale = variants.get(roles[part['id']], {}).get('colourScale')
        for index in set(part['indices']) if scale else ():
            for channel in range(3):
                mesh['vertices'][index * 12 + 6 + channel] *= scale[channel]
    def rename(node):
        for part in node.get('parts', []):
            part['materialid'] = variants.get(part['materialid'], {}).get('name', part['materialid'])
        for child in node.get('children', []):
            rename(child)
    for node in result['nodes']:
        rename(node)
    for material in result['materials']:
        if material['id'] in variants:
            variant = variants[material['id']]
            material['id'] = variant.get('name', material['id'])
            if 'baseColor' in variant.get('textures', {}):
                material['textures'][0]['filename'] = variant['textures']['baseColor']
    return result


def impostors(only=None):
    """Add or refresh LOD3 of every plant with detail levels, keeping its other levels as they are."""
    manifest = json.loads(MANIFEST.read_text())
    old_scene = bpy.context.window.scene
    scene = bpy.data.scenes.new('MegaMek plant impostors')
    bpy.context.window.scene = scene
    images = {}
    try:
        camera = bpy.data.objects.new('Impostor camera', bpy.data.cameras.new('Impostor camera'))
        scene.collection.objects.link(camera)
        camera.data.type = 'ORTHO'
        camera.data.sensor_fit = 'HORIZONTAL'
        camera.data.ortho_scale = 3
        camera.data.clip_end = 1000
        camera.location = (0, -100, 0)
        camera.rotation_euler = (math.pi / 2, 0, 0)
        scene.camera = camera
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x, scene.render.resolution_y = 3 * PANEL * SAMPLES, PANEL * SAMPLES
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.filter_size = 1.0
        # Linear float renders: impostor() averages and encodes them itself.
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.color_depth = '32'
        # No tone map, exposure or artistic grade.
        scene.display_settings.display_device = 'sRGB'
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
        scene.view_settings.use_curve_mapping = False
        if hasattr(scene, 'eevee'):
            scene.eevee.taa_render_samples = 16
        for key, entry in manifest.items():
            # Entries are keyed by the model's path; the plant's own name names its levels and impostor.
            name = key.rsplit('/', 1)[-1]
            if 'lods' not in entry or only is not None and name not in only and key not in only:
                continue
            if entry['mesh'] != key + '.glb':
                # A winter form kept as a material variant has no GLB of its own; its impostor stays in that file.
                print(name, 'is kept in', entry['mesh'], flush=True)
                continue
            path = BOARD / entry['mesh']
            levels = {level: read_glb(path, level, linear_colors=True) for level in range(min(3, len(entry['lods'])))}
            # The cards stand for the coarsest mesh level, which they replace.
            source = levels[max(levels)]
            # The impostor material's extras hold the winter impostor (mmSnow).
            extras = next((material.get('extras') for material in levels[0]['materials']
                           if material['id'] == 'impostor'), None)
            alpha_test = next((material.get('alphaTest', .5) for material in levels[0]['materials']
                               if material['id'] == 'impostor'), .5)
            for model in levels.values():
                model['materials'] = [material for material in model['materials'] if material['id'] != 'impostor']
            levels[3] = impostor(scene, source, name, images)
            levels[3]['materials'][0]['alphaTest'] = alpha_test
            # A winter form kept as mmSnow gets its own impostor renders and card colours.
            cold = winter(source)
            if cold:
                frozen = impostor(scene, cold, name + '-snow', images)['meshes'][0]['vertices']
                extras = {'mmSnow': {
                    'textures': {'baseColor': f'../{IMPOSTORS}/{name}-snow.png',
                                 'normal': f'../{IMPOSTORS}/{name}-snow_normal.png'},
                    'colours': [frozen[i + 6:i + 10] for i in range(0, len(frozen), 12)]}}
            if extras:
                levels[3]['materials'][0]['extras'] = extras
            entry['lods'] = entry['lods'][:3] + [{'node': f'{name}-lod3', **counts(levels[3])}]
            write_glb(path, levels=levels, linear_colors=True, extras=levels[0].get('extras'), preserve_groups=('spores',))
            print(name, [lod['triangles'] for lod in entry['lods']], flush=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    finally:
        bpy.context.window.scene = old_scene
        bpy.data.scenes.remove(scene)
        for image in images.values():
            bpy.data.images.remove(image)


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    stage = arguments[0] if arguments else 'impostors'
    only = set(arguments[1:]) or globals().get('ONLY')
    if stage != 'impostors':
        raise SystemExit('Only the impostors stage is supported.')
    impostors(only)
