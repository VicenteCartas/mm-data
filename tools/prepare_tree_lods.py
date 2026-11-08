"""Run with Blender --background --python tools/prepare_tree_lods.py -- impostors [names...].

The command adds LOD3 to existing plant GLBs, standing for LOD2, the level it replaces, while preserving their three
mesh levels: one quad the game turns toward the camera, textured with renders of LOD2 from many directions (frames),
of which it shows the ones nearest the view. Each frame holds LOD2's unlit colour, and its surface's normal and depth,
so the game lights and shadows each texel as it does LOD2's surface (terrain-foliage.frag, impostor-frames.glsl).
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
from mathutils import Matrix, Vector

BOARD = Path(__file__).resolve().parents[1] / 'data/models/board'
# The plant GLBs; their texture paths are relative to this folder.
PLANTS = BOARD / 'vegetation'
# The plants' levels and sources: tool data, never shipped.
MANIFEST = Path(__file__).resolve().parent / 'board-models/manifest.json'
IMPOSTORS = 'textures/vegetation/impostors'
# The frames: AZIMUTHS directions around the plant at each of ELEVATIONS (degrees above the horizon; 35.26 is the board's
# isometric view), each FRAME texels square; the atlas holds a row of azimuths per elevation, the lowest on top. The
# game draws impostors only below TreeLod's smallest threshold (24 pixels), so FRAME texels oversample it twice.
# impostor-frames.glsl must match these.
AZIMUTHS, ELEVATIONS, FRAME = 8, (10, 35.26, 60, 85), 48
# Each frame renders at this many times its texels, then averages them by alpha, as the game's cutout mip levels do
# (GpuColorTexture.cutout): a texel keeps the colour of the leaves it shows and the share of it they cover.
SAMPLES = 4
# The crown mask's texels a side: the plant's coverage from straight above, which BoardTreeCoverage measures.
CROWN = 128
# The position render's world coordinates as emitted colour (show()): small enough that no frame's goes below 0.
POSITION_SCALE = .1
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
    world-space normal as 0..1), 'position' (the world-space position times POSITION_SCALE about .5), 'surface' (the
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
            scaled.inputs[1].default_value = (.5,) * 3 if shown == 'normal' else (POSITION_SCALE,) * 3
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


def frame_axes(azimuth, elevation):
    """A frame's view (from the plant toward the camera), right and up axes, in the plant's frame; impostor-frames.glsl
    builds the same."""
    az, el = math.radians(azimuth), math.radians(elevation)
    view = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    right = Vector((-math.sin(az), math.cos(az), 0))
    up = Vector((-math.sin(el) * math.cos(az), -math.sin(el) * math.sin(az), math.cos(el)))
    return view, right, up


# Each frame: its column and row in the atlas, and its axes.
FRAMES = [(column, row, *frame_axes(360 * column / AZIMUTHS, elevation))
          for row, elevation in enumerate(ELEVATIONS) for column in range(AZIMUTHS)]


def sphere(model):
    """The impostor's centre, on the plant's axis at the height where the sphere about it that holds the mesh is
    smallest, and that sphere's radius, with a little margin that keeps the dilated rim inside its frame."""
    points = numpy.asarray(model['meshes'][0]['vertices']).reshape(-1, 12)[:, :3]
    across = (points[:, :2] ** 2).sum(axis=1)
    reach = lambda z: float(numpy.sqrt((across + (points[:, 2] - z) ** 2).max()))
    low, high = float(points[:, 2].min()), float(points[:, 2].max())
    for _ in range(60):
        a, b = low + (high - low) / 3, high - (high - low) / 3
        low, high = (low, b) if reach(a) < reach(b) else (a, high)
    centre = Vector((0, 0, (low + high) / 2))
    return centre, reach(centre.z) * 1.04


def placement(column, row, view, right, up, centre, radius):
    """The frame's turn (the plant's axes onto the camera's right, depth and up) and the world position of the plant's
    origin that puts its sphere, scaled to a unit diameter, in the frame's cell (cells one unit wide, the camera at -y)."""
    turn = Matrix((right, -view, up))
    cell = Vector((column - AZIMUTHS / 2 + .5, 0, len(ELEVATIONS) / 2 - .5 - row))
    return turn, cell - turn @ centre / (2 * radius)


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


def shoot(scene, model, name, images, shown, matrices, rows, columns):
    """`model` placed once per world matrix, its materials showing `shown` (its unlit colour, or show()'s), as the
    scene's camera sees it at SAMPLES times rows by columns texels: linear RGBA premultiplied by coverage, rows top-down,
    averaged down to rows by columns."""
    data = unlit_mesh(model, name, images)
    if shown != 'colour':
        show(data, model, shown, images)
    objects = []
    for index, matrix in enumerate(matrices):
        obj = bpy.data.objects.new(f'{name}-{index}', data)
        scene.collection.objects.link(obj)
        obj.matrix_world = matrix
        objects.append(obj)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'render.exr'
        scene.render.filepath = str(path)
        scene.render.resolution_x, scene.render.resolution_y = columns * SAMPLES, rows * SAMPLES
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
    pixels = pixels.reshape(rows * SAMPLES, columns * SAMPLES, 4)[::-1]
    return pixels.reshape(rows, SAMPLES, columns, SAMPLES, 4).mean(axis=(1, 3))


def render(scene, model, name, images, centre, radius, shown):
    """`model` once per frame, turned so the camera sees it from the frame's direction, its sphere filling the frame's
    cell (FRAME texels a side), as shoot() renders it."""
    scene.camera.data.ortho_scale = AZIMUTHS
    matrices = []
    for column, row, view, right, up in FRAMES:
        turn, origin = placement(column, row, view, right, up, centre, radius)
        matrices.append(Matrix.Translation(origin) @ turn.to_4x4() @ Matrix.Scale(1 / (2 * radius), 4))
    return shoot(scene, model, name, images, shown, matrices, len(ELEVATIONS) * FRAME, AZIMUTHS * FRAME)


def crown(scene, model, name, images):
    """The crown mask: `model`'s coverage from straight above, x to the right and y up, in a square as wide as its
    larger horizontal extent and a little margin, about the middle of its bounds (BoardTreeCoverage frames it alike)."""
    points = numpy.asarray(model['meshes'][0]['vertices']).reshape(-1, 12)[:, :3]
    low, high = points.min(axis=0), points.max(axis=0)
    size = float((high - low)[:2].max()) * 1.04
    middle = (low + high) / 2
    scene.camera.data.ortho_scale = 1
    # Turned a quarter about x, the plant's y points up the image and its top toward the camera at -y.
    matrix = (Matrix.Translation((-middle[0] / size, 0, -middle[1] / size)) @ Matrix.Rotation(math.pi / 2, 4, 'X')
              @ Matrix.Scale(1 / size, 4))
    coverage = shoot(scene, model, name, images, 'colour', [matrix], CROWN, CROWN)[..., 3]
    save(numpy.dstack([numpy.ones(coverage.shape + (3,)), coverage]), BOARD / IMPOSTORS / (name + '_crown.png'))


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


def impostor(scene, model, name, images, tint=(1, 1, 1)):
    """LOD3: one quad the game turns toward the camera (impostor-frames.glsl), textured with orthographic renders of
    `model` (the plant's coarsest mesh level) from each frame's direction. Stored as a horizontal square through the
    impostor's centre, of the radius of the sphere about it that holds the mesh: the game reads the centre and radius
    from it, so the quad covers the plant from any side.

    The colour atlas holds the unlit pigment times `tint` (the impostor material's extras `mmImpostorTint` for this
    atlas, calibrate_impostors.py) and its coverage. The normal atlas holds, in its RGB, the normal of the
    surface each texel shows, in the plant's own axes, and in its alpha that surface's depth along the frame's view, in
    units of the sphere's diameter about .5: the game lights each texel with that normal and takes its shadow at that
    depth. The quad's colour carries its texels' mean occlusion, the share of them that is bark, cactus or snow (lit as
    solid), and the mean roughness and scatter of the rest, the leaves, as their materials give them."""
    centre, radius = sphere(model)
    colour, covered = unpremultiplied(render(scene, model, name, images, centre, radius, 'colour'))
    normals = unpremultiplied(render(scene, model, name, images, centre, radius, 'normal'))[0] * 2 - 1
    positions = (unpremultiplied(render(scene, model, name, images, centre, radius, 'position'))[0] - .5) / POSITION_SCALE
    surface = unpremultiplied(render(scene, model, name, images, centre, radius, 'surface'))[0]
    hard = unpremultiplied(render(scene, model, name, images, centre, radius, 'solid'))[0][..., 0]
    filled = covered > 0
    # Texels away from the plant, which dilation leaves, read as a surface facing up at the centre.
    shape = numpy.tile(numpy.array((0, 0, 1, 0)), colour.shape[:2] + (1,)).astype(numpy.float64)
    for column, row, view, right, up in FRAMES:
        turn, origin = placement(column, row, view, right, up, centre, radius)
        block = (slice(row * FRAME, (row + 1) * FRAME), slice(column * FRAME, (column + 1) * FRAME))
        rotation = numpy.asarray(turn)
        # The render's world vectors back in the plant's axes: world = turn @ local, so local = world @ turn.
        seen = normals[block] @ rotation
        seen /= numpy.maximum(numpy.linalg.norm(seen, axis=2, keepdims=True), 1e-6)
        point = (positions[block] - numpy.asarray(origin)) @ rotation * (2 * radius)
        here = filled[block]
        frame = shape[block]
        frame[..., :3][here] = seen[here]
        frame[..., 3][here] = ((point - numpy.asarray(centre)) @ numpy.asarray(view) / (2 * radius))[here]
        shape[block] = frame
    weight = covered
    total = max(float(weight.sum()), 1e-6)
    leaves = numpy.maximum(weight * (1 - hard), 0)
    leaf_total = float(leaves.sum())
    mean = lambda channel, w, t: float((surface[..., channel] * w).sum()) / t if t > 1e-6 else SURFACE[channel]
    card = (mean(0, weight, total), float((hard * weight).sum()) / total, mean(1, leaves, leaf_total),
            mean(2, leaves, leaf_total))
    vertices = []
    # The stored square samples the topmost frame, as a draw that does not turn it toward the camera shows it.
    top = len(ELEVATIONS) - 1
    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        vertices.extend(round(value, 6) for value in (x * radius, y * radius, centre.z, 0, 0, 1, *card,
                                                       (x * .5 + .5) / AZIMUTHS, (top + .5 - y * .5) / len(ELEVATIONS)))
    # The colour fit to the far mesh as the game shows it at the switch (calibrate_impostors.py), linear RGB.
    pigment = dilate(colour * numpy.asarray(tint), filled)
    save(numpy.concatenate([srgb(pigment), covered[..., None]], axis=2), BOARD / IMPOSTORS / (name + '.png'))
    shape = dilate(shape, filled)
    save(numpy.concatenate([numpy.clip(shape[..., :3] * 127 + 128, 0, 255) / 255,
                            numpy.clip(shape[..., 3:] + .5, 0, 1)], axis=2), BOARD / IMPOSTORS / (name + '_normal.png'))
    asset = f'{name}-lod3'
    return {'id': asset,
            'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'], 'vertices': vertices,
                        'colorData': True,
                        'parts': [{'id': 'impostor', 'type': 'TRIANGLES', 'indices': [0, 1, 2, 0, 2, 3]}]}],
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
        camera.data.clip_end = 1000
        camera.location = (0, -100, 0)
        camera.rotation_euler = (math.pi / 2, 0, 0)
        scene.camera = camera
        scene.render.engine = 'BLENDER_EEVEE'
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
            # The impostor stands for the coarsest mesh level, which it replaces.
            source = levels[max(levels)]
            old = next((material for material in levels[0]['materials'] if material['id'] == 'impostor'), None)
            if old is None and len(entry['lods']) > 3:
                # Its far level is a mesh of its own (the crystals), not an impostor.
                continue
            # The impostor material's extras hold the winter impostor (mmSnow) and the atlases' tints; they and its alpha
            # cutoff, which calibrate_impostors.py fits, stay across rebakes.
            extras = dict((old or {}).get('extras') or {})
            alpha_test = (old or {}).get('alphaTest', .5)
            for model in levels.values():
                model['materials'] = [material for material in model['materials'] if material['id'] != 'impostor']
            tints = extras.get('mmImpostorTint', {})
            levels[3] = impostor(scene, source, name, images, tints.get(name, (1, 1, 1)))
            crown(scene, source, name, images)
            levels[3]['materials'][0]['alphaTest'] = alpha_test
            # A winter form kept as mmSnow gets its own impostor renders and quad colours.
            cold = winter(source)
            if cold:
                frozen = impostor(scene, cold, name + '-snow', images, tints.get(name + '-snow', (1, 1, 1)))
                frozen = frozen['meshes'][0]['vertices']
                crown(scene, cold, name + '-snow', images)
                extras['mmSnow'] = {
                    'textures': {'baseColor': f'../{IMPOSTORS}/{name}-snow.png',
                                 'normal': f'../{IMPOSTORS}/{name}-snow_normal.png'},
                    'colours': [frozen[i + 6:i + 10] for i in range(0, len(frozen), 12)]}
            if extras:
                levels[3]['materials'][0]['extras'] = extras
            entry['lods'] = entry['lods'][:3] + [{'node': f'{name}-lod3', **counts(levels[3])}]
            for other_key, other in manifest.items():
                if other is not entry and other.get('mesh') == entry['mesh'] and 'lods' in other:
                    # A winter form kept in this file shows the same quad.
                    other['lods'][3:] = [{'node': other_key.rsplit('/', 1)[-1] + '-lod3', **counts(levels[3])}]
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
