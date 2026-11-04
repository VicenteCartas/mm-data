"""MegaMek material preview, assignment, and GLB editing for Blender."""
bl_info = {
    'name': 'MegaMek Materials & GLB',
    'author': 'MegaMek contributors',
    'version': (1, 4, 1),
    'blender': (5, 2, 0),
    'location': '3D View > Sidebar > MegaMek / MM Materials',
    'description': 'Assign Material Maker .tres materials and save GLBs with shared external textures',
    'category': 'Import-Export',
}

import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
from datetime import datetime
from urllib.parse import quote

import bmesh
import bpy
from bpy.props import StringProperty, CollectionProperty, PointerProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import glb
from . import testing
from . import palette
from .tres import read_material
from .preview import build_preview, show_materials

_import_path = None
_export_path = None
_hook_errors = []


def data_root(context):
    value = context.scene.mm_materials.root
    if not value:
        addon = context.preferences.addons.get(__name__)
        value = addon.preferences.root if addon else ''
    if not value:
        for parent in Path(__file__).resolve().parents:
            if (parent / 'data/models/board/textures').is_dir():
                return parent
        raise ValueError('Set the mm-data folder in the MegaMek panel')
    root = Path(bpy.path.abspath(value)).resolve()
    if not (root / 'data/models/board/textures').is_dir():
        raise ValueError('Choose mm-data, containing data/models/board/textures')
    return root


def textures_root(context):
    return data_root(context) / 'data/models/board/textures'


def clear_library(owner, context):
    # A directory change must not leave choices from a different checkout visible.
    palette.clear_icons()
    for scene in bpy.data.scenes:
        state = scene.mm_materials
        if state == owner or (isinstance(owner, MMPreferences) and not state.root):
            state.materials.clear()
            state.material = ''
            if hasattr(scene, 'mm_palette'):
                scene.mm_palette.folder = 'ALL'


def remember_name(source, target):
    if source.name:
        target['_mm_original_name'] = source.name
        target['_mm_import_name'] = target.name


def export_name(target):
    return target.get('_mm_original_name', target.name) if target.name == target.get('_mm_import_name') else target.name


def preview_lod(state, context):
    for obj in context.scene.objects:
        ancestor, level = obj, None
        while ancestor:
            match = re.search(r'(?:^|[-_])lod(\d+)(?:$|[-_])', export_name(ancestor))
            if match:
                level = match[1]
                break
            ancestor = ancestor.parent
        obj.hide_set(state.lod != 'ALL' and level is not None and level != state.lod)


class glTF2ImportUserExtension:
    def gather_import_node_after_hook(self, vnode, node, obj, gltf):
        if _import_path and node is not None:
            remember_name(node, obj)

    def gather_import_material_after_hook(self, source, vertex_color, material, gltf):
        if not _import_path:
            return
        remember_name(source, material)
        variant_paths = {}
        for name, variant in (source.extras or {}).get('mmVariants', {}).items():
            variant_paths[name] = {role: str(glb.image_path(_import_path, uri))
                                   for role, uri in variant.get('textures', {}).items()}
        material['_mm_variant_paths'] = json.dumps(variant_paths)
        material['_mm_surface'] = json.dumps({k: v for k, v in source.to_dict().items()
                                              if k in ('alphaMode', 'alphaCutoff', 'doubleSided') and v is not None})
        pbr = source.pbr_metallic_roughness
        if pbr and pbr.base_color_factor:
            surface = json.loads(material['_mm_surface'])
            surface['baseColorFactor'] = pbr.base_color_factor
            material['_mm_surface'] = json.dumps(surface)
        if pbr and pbr.base_color_texture:
            texture = gltf.data.textures[pbr.base_color_texture.index]
            if texture.sampler is not None:
                material['_mm_sampler'] = json.dumps(gltf.data.samplers[texture.sampler].to_dict())
            image = gltf.data.images[texture.source]
            if image.uri and not image.uri.startswith('data:'):
                path = glb.image_path(_import_path, image.uri)
                if path.name.endswith('_albedo.png'):
                    resource = path.with_name(path.name[:-11] + '.tres')
                    root = textures_root(bpy.context)
                    if resource.is_relative_to(root) and resource.is_file():
                        material['_mm_tres'] = resource.relative_to(root).as_posix()
        if material.get('_mm_tres') and (source.emissive_texture or any(source.emissive_factor or [])):
            material['_mm_model_emission'] = True
            material['_mm_emission_factor'] = source.emissive_factor or [0, 0, 0]
            if source.emissive_texture:
                texture = gltf.data.textures[source.emissive_texture.index]
                image = gltf.data.images[texture.source]
                material['_mm_emission_image'] = bpy.data.images[image.blender_image_name]

    def gather_import_mesh_after_hook(self, source, mesh, gltf):
        if not _import_path:
            return
        remember_name(source, mesh)
        parts = {}
        for primitive in source.primitives:
            if primitive.extras:
                name = gltf.data.materials[primitive.material].name if primitive.material is not None else ''
                if name in parts and parts[name] != primitive.extras:
                    _hook_errors.append('Distinct part metadata shares one material; split those parts before Blender editing')
                parts[name] = primitive.extras
        mesh['_mm_parts'] = json.dumps(parts)
        # Blender's importer normally quantizes COLOR_0 to BYTE_COLOR. These values
        # also carry game data, so retain the original linear floats on face corners.
        if any('COLOR_0' in p.attributes for p in source.primitives):
            import numpy as np
            from io_scene_gltf2.io.imp.gltf2_io_binary import BinaryData
            colors = []
            for primitive in source.primitives:
                indices = (BinaryData.decode_accessor(gltf, primitive.indices).reshape(-1)
                           if primitive.indices is not None else
                           np.arange(gltf.data.accessors[primitive.attributes['POSITION']].count))
                indices = np.unique(indices)
                values = np.ones((len(indices), 4), dtype=np.float32)
                if 'COLOR_0' in primitive.attributes:
                    source_colors = BinaryData.decode_accessor(gltf, primitive.attributes['COLOR_0'])[indices]
                    values[:, :source_colors.shape[1]] = source_colors
                colors.append(values)
            colors = np.concatenate(colors)
            if len(colors) != len(mesh.vertices):
                _hook_errors.append('Cannot preserve vertex colours: unexpected imported vertex ordering')
            else:
                for layer in list(mesh.color_attributes):
                    mesh.color_attributes.remove(layer)
                layer = mesh.color_attributes.new('Color', 'FLOAT_COLOR', 'CORNER')
                loops = np.empty(len(mesh.loops), dtype=np.int32)
                mesh.loops.foreach_get('vertex_index', loops)
                layer.data.foreach_set('color', colors[loops].reshape(-1))
                mesh.color_attributes.render_color_index = 0


class glTF2ExportUserExtension:
    def gather_image_hook(self, image, export_image, sockets, settings):
        if not _export_path:
            return
        source = export_image.blender_image(settings)
        if source is None or source.packed_file or source.source != 'FILE' or source.is_dirty:
            return
        path = Path(bpy.path.abspath(source.filepath, library=source.library)).resolve()
        if path.is_file() and path.is_relative_to(data_root(bpy.context) / 'data/models'):
            image.buffer_view = None
            image.uri = quote(os.path.relpath(path, _export_path.parent).replace(os.sep, '/'), safe='/')
            image.mime_type = None

    def gather_material_hook(self, material, source, settings):
        if not _export_path:
            return
        material.name = export_name(source)
        for name, paths in json.loads(source.get('_mm_variant_paths', '{}')).items():
            if material.extras and name in material.extras.get('mmVariants', {}):
                material.extras['mmVariants'][name]['textures'] = {
                    role: quote(os.path.relpath(path, _export_path.parent).replace(os.sep, '/'), safe='/')
                    for role, path in paths.items()}
        resource = source.get('_mm_tres')
        if not resource:
            return
        try:
            from io_scene_gltf2.io.com import gltf2_io as io
            spec = read_material(textures_root(bpy.context) / resource, textures_root(bpy.context))
            uri = quote(os.path.relpath(spec['albedo'], _export_path.parent).replace(os.sep, '/'), safe='/')
            image = io.Image(None, None, None, None, spec['albedo'].stem, uri)
            original_sampler = json.loads(source.get('_mm_sampler', '{}'))
            sampler = io.Sampler(None, None, original_sampler.get('magFilter') or 9729,
                                 original_sampler.get('minFilter') or 9987, None,
                                 original_sampler.get('wrapS') or 10497, original_sampler.get('wrapT') or 10497)
            texture = io.Texture(None, None, None, sampler, image)
            original = json.loads(source.get('_mm_surface', '{}'))
            material.pbr_metallic_roughness = io.MaterialPBRMetallicRoughness(
                original.get('baseColorFactor', [1, 1, 1, 1]), io.TextureInfo(None, None, texture, 0),
                None, None, 0, None, 1)
            material.normal_texture = material.occlusion_texture = None
            if not source.get('_mm_model_emission'):
                material.emissive_texture = None
                material.emissive_factor = None
            material.extensions = ({key: value for key, value in (material.extensions or {}).items()
                                    if key == 'KHR_materials_emissive_strength'} or None
                                   if source.get('_mm_model_emission') else None)
            material.alpha_mode = original.get('alphaMode', 'MASK' if spec['transparent'] else 'OPAQUE')
            if source.get('mmPaintMask'):
                material.alpha_mode = 'OPAQUE'
            material.alpha_cutoff = original.get('alphaCutoff', spec['alpha_cutoff']) if material.alpha_mode == 'MASK' else None
            material.double_sided = original.get('doubleSided', spec['double_sided'])
        except Exception as error:
            _hook_errors.append(str(error))

    def gather_node_hook(self, node, source, settings):
        if not _export_path:
            return
        node.name = export_name(source)
        if node.mesh and source.type == 'MESH':
            node.mesh.name = export_name(source.data)
            parts = json.loads(source.data.get('_mm_parts', '{}'))
            for primitive in node.mesh.primitives:
                name = primitive.material.name if primitive.material else ''
                if name in parts:
                    primitive.extras = parts[name]


def refresh_materials(context):
    root = textures_root(context)
    materials = {slot.material for obj in context.scene.objects if obj.type == 'MESH'
                 for slot in obj.material_slots if slot.material and slot.material.get('_mm_tres')}
    # Check every resource before changing any preview.
    for material in materials:
        read_material(root / material['_mm_tres'], root)
    for material in materials:
        coloured = any(obj.type == 'MESH' and obj.data.color_attributes.active_color is not None
                       and any(slot.material == material for slot in obj.material_slots) for obj in context.scene.objects)
        build_preview(material, root / material['_mm_tres'], root, vertex_colors=coloured)
    show_materials(context)
    return len(materials)


def open_glb(context, filepath):
    global _import_path
    path = Path(filepath).resolve()
    root = data_root(context)
    doc, binary = glb.read_glb(path)
    glb.validate(doc, path, root / 'data/models')
    prepared, binary, changed = glb.prepare_import(doc, binary)
    # Scene-local edits never mix assets or overwrite the user's existing scene.
    previous = context.window.scene
    scene = bpy.data.scenes.new(path.stem)
    scene.mm_materials.root = str(root)
    context.window.scene = scene
    _hook_errors.clear()
    import_copy = None
    try:
        _import_path = path
        if changed:
            descriptor, filename = tempfile.mkstemp(prefix='.mm-import-', suffix='.glb', dir=path.parent)
            os.close(descriptor)
            import_copy = Path(filename)
            glb.write_glb(import_copy, prepared, binary)
        result = bpy.ops.import_scene.gltf(filepath=str(import_copy or path), import_pack_images=False,
                                           import_scene_as_collection=True, import_scene_extras=True,
                                           import_shading='NORMALS', merge_vertices=False)
        if result != {'FINISHED'} or _hook_errors:
            raise ValueError('; '.join(_hook_errors) or 'Blender could not import this GLB')
        scene.mm_materials.source = str(path)
        scene.mm_materials.source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        scene.mm_materials.root_extras = json.dumps(doc.get('extras', {}))
        refresh_materials(context)
        preview_lod(scene.mm_materials, context)
        context.view_layer.update()
        visible = [obj for obj in scene.objects if obj.type == 'MESH' and obj.visible_get()]
        for obj in scene.objects:
            obj.select_set(False)
        if visible:
            active = max(visible, key=lambda obj: len(obj.data.polygons))
            active.select_set(True)
            context.view_layer.objects.active = active
            from mathutils import Vector
            corners = [obj.matrix_world @ Vector(corner) for obj in visible for corner in obj.bound_box]
            low = Vector(tuple(min(v[i] for v in corners) for i in range(3)))
            high = Vector(tuple(max(v[i] for v in corners) for i in range(3)))
            if context.screen:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        view = area.spaces.active.region_3d
                        view.view_location = (low + high) / 2
                        view.view_distance = max(2, (high - low).length * 1.2)
        return scene
    except Exception:
        context.window.scene = previous
        # This scene and its objects were just created by us.
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        raise
    finally:
        _import_path = None
        if import_copy:
            import_copy.unlink(missing_ok=True)


def save_glb(context, filepath, *, selected=False, snapshot=False):
    global _export_path
    if context.scene.mm_asset_test.source_scene:
        raise ValueError('Return to Authoring before exporting; test instances are a preview only')
    state = context.scene.mm_materials
    root = data_root(context)
    path = Path(filepath).resolve()
    if path.suffix.lower() != '.glb' or not path.is_relative_to(root / 'data/models'):
        raise ValueError('Save a .glb inside mm-data/data/models so its textures stay portable')
    if not path.parent.is_dir():
        raise ValueError('Choose an existing destination folder')
    if selected and state.source and path == Path(state.source):
        raise ValueError('Use Save GLB to update the opened asset with all its LODs; export a selection to a different file')
    remembered_path = state.export_path if selected else state.source
    remembered_hash = state.export_hash if selected else state.source_hash
    if remembered_path and path == Path(remembered_path) and path.exists() and remembered_hash:
        if hashlib.sha256(path.read_bytes()).hexdigest() != remembered_hash:
            raise ValueError('The GLB changed on disk since Open/Save. Reopen it or use Save As')
    objects = list(context.selected_objects if selected else context.scene.objects)
    if not any(obj.type == 'MESH' for obj in objects):
        raise ValueError('Select at least one mesh to export')
    for obj in objects:
        if obj.type not in ('MESH', 'EMPTY', 'CAMERA', 'LIGHT'):
            raise ValueError(f'Convert {obj.name} to a mesh before saving')
        if obj.type == 'MESH':
            if obj.data.shape_keys or len(obj.data.uv_layers) > 1 or len(obj.data.color_attributes) > 1:
                raise ValueError(f'{obj.name}: use one UV/color layer and no shape keys')
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.get('_mm_tres'):
                    read_material(textures_root(context) / mat['_mm_tres'], textures_root(context))
                    if any(n.type == 'TEX_IMAGE' and n.image and n.image.is_dirty for n in mat.node_tree.nodes):
                        raise ValueError(f'{mat.name}: save painted texture images first, or Reload Materials & Maps')
                    if not obj.data.uv_layers:
                        raise ValueError(f'UV unwrap {obj.name} before exporting textured materials')
        if obj.animation_data and (obj.animation_data.action or obj.animation_data.nla_tracks):
            raise ValueError(f'{obj.name}: this rigid GLB workflow does not save animation tracks')
    prior_mode = context.object.mode if context.object else 'OBJECT'
    if prior_mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    _hook_errors.clear()
    try:
        # Hooks resolve shared images against the final path, independent of the staging directory.
        with tempfile.TemporaryDirectory(prefix='.mm-export-', dir=path.parent) as temp:
            staged = Path(temp) / path.name
            _export_path = path
            result = bpy.ops.export_scene.gltf(
                filepath=str(staged), export_format='GLB', use_active_scene=True,
                use_selection=selected, use_visible=False, use_renderable=False,
                export_extras=True, export_animations=False, export_cameras=False, export_lights=False,
                export_yup=True, export_texcoords=True, export_normals=True, export_tangents=False,
                export_attributes=True, export_vertex_color='ACTIVE', export_all_vertex_colors=False,
                export_active_vertex_color_when_no_material=True, export_apply=True,
                export_materials='EXPORT', export_image_format='AUTO')
            if result != {'FINISHED'} or _hook_errors:
                raise ValueError('; '.join(_hook_errors) or 'Blender could not export this scene')
            doc, binary = glb.read_glb(staged)
            extras = json.loads(state.root_extras or '{}')
            if extras:
                doc['extras'] = extras
            glb.strip_editor_properties(doc)
            glb.merge_identical_materials(doc)
            glb.ensure_lod_groups(doc, path.stem)
            glb.validate(doc, path, root / 'data/models')
            glb.write_glb(staged, doc, binary)
            backup = None
            if path.exists() and not snapshot:
                backup = root / '.tmp/blender-backups' / path.relative_to(root)
                backup = backup.with_name(path.stem + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.glb')
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            os.replace(staged, path)
        if snapshot:
            return None
        if selected:
            state.export_path = str(path)
            state.export_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            state.source = str(path)
            state.source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return backup
    finally:
        _export_path = None
        if prior_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=prior_mode)


class MMPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    root: StringProperty(name='Default mm-data folder', subtype='DIR_PATH', update=clear_library)
    engine: StringProperty(name='MegaMek engine checkout', subtype='DIR_PATH')

    def draw(self, context):
        self.layout.prop(self, 'root')
        self.layout.prop(self, 'engine')
        self.layout.label(text='Materials are read from data/models/board/textures inside this folder.')


class MMEntry(bpy.types.PropertyGroup):
    pass


class MMState(bpy.types.PropertyGroup):
    root: StringProperty(name='mm-data folder', subtype='DIR_PATH', update=clear_library)
    source: StringProperty(name='GLB', subtype='FILE_PATH')
    source_hash: StringProperty()
    export_path: StringProperty(subtype='FILE_PATH')
    export_hash: StringProperty()
    root_extras: StringProperty(default='{}')
    materials: CollectionProperty(type=MMEntry)
    material: StringProperty(name='Material')
    lod: EnumProperty(name='Preview LOD', default='0', update=preview_lod,
                      items=[('ALL', 'All', 'Show all levels together'),
                             *[(str(i), f'LOD {i}', f'Preview level {i}; Save still includes every level') for i in range(4)]])


class MM_OT_catalog(bpy.types.Operator):
    bl_idname = 'mm_materials.catalog'
    bl_label = 'Refresh Library'
    bl_description = 'List .tres files from mm-data/data/models/board/textures'

    def execute(self, context):
        try:
            root = data_root(context)
            state = context.scene.mm_materials
            chosen = state.material
            if state.root != str(root):
                state.root = str(root)
            entries = state.materials
            entries.clear()
            for path in sorted((root / 'data/models/board/textures').rglob('*.tres')):
                entries.add().name = path.relative_to(root / 'data/models/board/textures').as_posix()
            palette.refresh(context)
            state.material = chosen if chosen in entries else ''
            context.scene.mm_palette.page = 0
            self.report({'INFO'}, f'{len(entries)} materials available')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_default_folder(bpy.types.Operator):
    bl_idname = 'mm_materials.default_folder'
    bl_label = 'Save as Default Folder'
    bl_description = 'Use this mm-data folder for new scenes and save it in Blender preferences'

    def execute(self, context):
        try:
            context.preferences.addons[__name__].preferences.root = str(data_root(context))
            bpy.ops.wm.save_userpref()
            self.report({'INFO'}, 'Default mm-data folder saved')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_assign(bpy.types.Operator):
    bl_idname = 'mm_materials.assign'
    bl_label = 'Assign Material'
    bl_description = 'Replace the active material slot on selected meshes, or assign selected faces in Edit Mode'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            state = context.scene.mm_materials
            root = textures_root(context)
            path = root / state.material
            if not state.material:
                raise ValueError('Choose a material from the library first')
            spec = read_material(path, root)
            objects = list(context.objects_in_mode) if context.mode == 'EDIT_MESH' else context.selected_objects
            objects = [obj for obj in objects if obj.type == 'MESH']
            if not objects:
                raise ValueError('Select a mesh first')
            if context.mode == 'EDIT_MESH' and any(obj.data.users > 1 for obj in objects):
                raise ValueError('Make linked meshes single-user before assigning individual faces')
            for obj in objects:
                if context.mode == 'EDIT_MESH':
                    mesh = bmesh.from_edit_mesh(obj.data)
                    faces = [face for face in mesh.faces if face.select]
                    if not faces:
                        continue
                    mat = bpy.data.materials.new(path.stem)
                    build_preview(mat, path, root, vertex_colors=obj.data.color_attributes.active_color is not None)
                    obj.data.materials.append(mat)
                    for face in faces:
                        face.material_index = len(obj.data.materials) - 1
                    bmesh.update_edit_mesh(obj.data)
                else:
                    # A new material retains this slot's gameplay role but does not change unselected users.
                    if obj.data.users > 1:
                        obj.data = obj.data.copy()
                    old = obj.active_material
                    mat = old.copy() if old else bpy.data.materials.new(path.stem)
                    if old:
                        mat['_mm_original_name'] = export_name(old)
                        mat['_mm_import_name'] = mat.name
                    surface = json.loads(mat.get('_mm_surface', '{}'))
                    surface.update(alphaMode='MASK' if spec['transparent'] else 'OPAQUE',
                                   alphaCutoff=spec['alpha_cutoff'], doubleSided=spec['double_sided'])
                    mat['_mm_surface'] = json.dumps(surface)
                    build_preview(mat, path, root, vertex_colors=obj.data.color_attributes.active_color is not None)
                    if obj.material_slots:
                        obj.material_slots[obj.active_material_index].material = mat
                    else:
                        obj.data.materials.append(mat)
            show_materials(context)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_reload(bpy.types.Operator):
    bl_idname = 'mm_materials.reload'
    bl_label = 'Reload Materials & Maps'
    bl_description = 'Rebuild this scene’s previews from the current .tres files and reload their images'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            count = refresh_materials(context)
            self.report({'INFO'}, f'Reloaded {count} materials')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_open(bpy.types.Operator, ImportHelper):
    bl_idname = 'mm_materials.open'
    bl_label = 'Open MegaMek GLB'
    filename_ext = '.glb'
    filter_glob: StringProperty(default='*.glb', options={'HIDDEN'})

    def invoke(self, context, event):
        try:
            self.filepath = str(data_root(context) / 'data/models') + os.sep
            return ImportHelper.invoke(self, context, event)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

    def execute(self, context):
        try:
            open_glb(context, self.filepath)
            bpy.ops.mm_materials.catalog()
            self.report({'INFO'}, 'Opened in a new scene; material previews loaded')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_save_as(bpy.types.Operator, ExportHelper):
    bl_idname = 'mm_materials.save_as'
    bl_label = 'Save MegaMek GLB As'
    filename_ext = '.glb'
    filter_glob: StringProperty(default='*.glb', options={'HIDDEN'})

    def invoke(self, context, event):
        self.filepath = context.scene.mm_materials.source or str(data_root(context) / 'data/models/board/model.glb')
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            save_glb(context, self.filepath)
            self.report({'INFO'}, f'Saved {Path(self.filepath).name}; shared textures remain external')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_export_selected(bpy.types.Operator, ExportHelper):
    bl_idname = 'mm_materials.export_selected'
    bl_label = 'Export Selected GLB'
    bl_description = 'Export selected objects with external materials and a LOD0 group; select every mesh part to include'
    filename_ext = '.glb'
    filter_glob: StringProperty(default='*.glb', options={'HIDDEN'})

    def invoke(self, context, event):
        try:
            name = bpy.path.clean_name(context.object.name) if context.object else 'model'
            self.filepath = context.scene.mm_materials.export_path or str(data_root(context) / 'data/models/board' / (name + '.glb'))
            return ExportHelper.invoke(self, context, event)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

    def execute(self, context):
        try:
            save_glb(context, self.filepath, selected=True)
            self.report({'INFO'}, f'Exported selected objects to {Path(self.filepath).name}')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_save(bpy.types.Operator):
    bl_idname = 'mm_materials.save'
    bl_label = 'Save GLB'
    bl_description = 'Save every LOD in this scene to its source GLB; back up the previous file'

    def execute(self, context):
        if not context.scene.mm_materials.source:
            return bpy.ops.mm_materials.save_as('INVOKE_DEFAULT')
        try:
            backup = save_glb(context, context.scene.mm_materials.source)
            self.report({'INFO'}, 'GLB saved' + ('; previous version in .tmp/blender-backups' if backup else ''))
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_PT_panel(bpy.types.Panel):
    bl_label = 'Model / GLB'
    bl_idname = 'MM_PT_materials'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MegaMek'
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        if context.scene.mm_asset_test.source_scene:
            layout.label(text='Asset test preview — edit the authoring scene.')
            layout.operator('mm_materials.test_return', icon='LOOP_BACK')
            return
        state = context.scene.mm_materials
        layout.operator('mm_materials.open', icon='FILE_FOLDER')
        if state.source:
            layout.label(text=Path(state.source).name, icon='MESH_DATA')
            layout.prop(state, 'lod')
            row = layout.row(align=True)
            row.operator('mm_materials.save', icon='FILE_TICK')
            row.operator('mm_materials.save_as', text='Save As…')
        else:
            layout.label(text='New mesh: select parts, then export.')
        layout.operator('mm_materials.export_selected', icon='EXPORT')
        layout.separator()
        layout.operator('mm_materials.browse_materials', icon='MATERIAL')
        layout.label(text='Save .blend separately to keep editor state.')


_classes = (MMPreferences, MMEntry, MMState, MM_OT_catalog, MM_OT_default_folder, MM_OT_assign, MM_OT_reload,
            MM_OT_open, MM_OT_save_as, MM_OT_export_selected, MM_OT_save, MM_PT_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mm_materials = PointerProperty(type=MMState)
    testing.register()
    palette.register()


def unregister():
    palette.unregister()
    testing.unregister()
    del bpy.types.Scene.mm_materials
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
