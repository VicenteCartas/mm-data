"""Visual library browser. Thumbnail rendering runs in a separate Blender process."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import bpy
import bpy.utils.previews
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from .tres import read_material

_libraries = {}
_job = None
# A library of any size occupies at most four thumbnail rows.
PAGE_LAYOUTS = {'SMALL': (3, 12, 2.6), 'MEDIUM': (2, 6, 3.8), 'LARGE': (2, 4, 5.2)}


def thumbnail_path(path, root):
    spec = read_material(path, root)
    files = {value for value in spec.values() if isinstance(value, Path)}
    signature = [(str(file), file.stat().st_mtime_ns, file.stat().st_size) for file in sorted(files)]
    # Include parsed shader parameters as well as all map timestamps. Bump the
    # version when the renderer or preview shader changes.
    key = hashlib.sha256(json.dumps(['sphere-v2', spec, signature], sort_keys=True, default=str).encode()).hexdigest()
    return root.parents[3] / '.tmp/blender-material-previews' / (key + '.png'), spec['albedo']


def refresh(context):
    from . import textures_root
    root = textures_root(context)
    key = str(root)
    if key in _libraries:
        bpy.utils.previews.remove(_libraries[key]['icons'])
    icons = bpy.utils.previews.new()
    items = []
    for entry in context.scene.mm_materials.materials:
        name = entry.name
        item = dict(name=name, label=Path(name).stem.replace('-', ' '), folder=str(Path(name).parent).replace('\\', '/'),
                    icon=0, rendered=False, error='')
        try:
            target, albedo = thumbnail_path(root / name, root)
            item.update(target=target, rendered=target.is_file())
            item['icon'] = icons.load(name, str(target if item['rendered'] else albedo), 'IMAGE').icon_id
        except Exception as error:
            item['error'] = str(error)
        items.append(item)
    categories = [('ALL', 'All folders', 'Show the entire material library')]
    categories += [(folder, folder, folder) for folder in sorted({item['folder'] for item in items})]
    library = dict(icons=icons, items=items, categories=categories)
    _libraries[key] = library
    errors = [item['name'] + ': ' + item['error'] for item in items if item['error']]
    if errors:
        report = bpy.data.texts.get('MegaMek Palette Report') or bpy.data.texts.new('MegaMek Palette Report')
        report.clear()
        report.write('\n'.join(errors))
    return library


def library(context):
    from . import textures_root
    key = str(textures_root(context))
    names = [entry.name for entry in context.scene.mm_materials.materials]
    cached = _libraries.get(key)
    return cached if cached and [item['name'] for item in cached['items']] == names else refresh(context)


_empty_categories = [('ALL', 'All folders', 'Show the entire material library')]


def categories(settings, context):
    if context is None:
        return _empty_categories
    try:
        # Keep returned strings alive; Blender's dynamic enum stores their pointers.
        return library(context)['categories']
    except Exception:
        return _empty_categories


def filtered_items(context):
    settings = context.scene.mm_palette
    words = settings.search.casefold().split()
    return [item for item in library(context)['items']
            if (settings.folder == 'ALL' or item['folder'] == settings.folder)
            and all(word in (item['name'] + ' ' + item['label']).casefold() for word in words)]


def reset_page(settings, context):
    settings.page = 0


def page_items(context):
    settings = context.scene.mm_palette
    items = filtered_items(context)
    count = PAGE_LAYOUTS[settings.size][1]
    pages = max(1, (len(items) + count - 1) // count)
    page = min(settings.page, pages - 1)
    return items[page * count:(page + 1) * count], page, pages, len(items)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def poll_render():
    global _job
    if not _job:
        return None
    job = _job
    # Only refresh icons when a new image was atomically published by the worker.
    cached = _libraries.get(str(job['root']))
    if cached:
        for item in cached['items']:
            target = item.get('target')
            if not item['rendered'] and target and target.is_file():
                if item['name'] in cached['icons']:
                    del cached['icons'][item['name']]
                item['icon'] = cached['icons'].load(item['name'], str(target), 'IMAGE').icon_id
                item['rendered'] = True
    redraw()
    if job['process'].poll() is None:
        return .5
    _job = None
    job['log'].close()
    try:
        errors = json.loads((job['folder'] / 'result.json').read_text())
        message = '\n'.join(errors) if errors else 'All material thumbnails rendered.'
    except (OSError, ValueError):
        message = 'Thumbnail rendering failed.\n' + job['log_path'].read_text(errors='replace')[-4000:]
    report = bpy.data.texts.get('MegaMek Palette Report') or bpy.data.texts.new('MegaMek Palette Report')
    report.clear()
    report.write(message)
    job['temporary'].cleanup()
    return None


@bpy.app.handlers.persistent
def stop_render(*args):
    global _job
    if _job:
        job, _job = _job, None
        job['process'].terminate()
        try:
            job['process'].wait(timeout=2)
        except subprocess.TimeoutExpired:
            job['process'].kill()
            job['process'].wait(timeout=2)
        job['log'].close()
        job['temporary'].cleanup()
    if bpy.app.timers.is_registered(poll_render):
        bpy.app.timers.unregister(poll_render)


def clear_icons(*args):
    for cached in _libraries.values():
        bpy.utils.previews.remove(cached['icons'])
    _libraries.clear()


class MMPaletteState(bpy.types.PropertyGroup):
    search: StringProperty(name='Search', options={'TEXTEDIT_UPDATE'}, update=reset_page)
    folder: EnumProperty(name='Folder', items=categories, update=reset_page)
    size: EnumProperty(name='Thumbnails', items=[('SMALL', 'Small · 12 per page', ''), ('MEDIUM', 'Medium · 6 per page', ''),
                                               ('LARGE', 'Large · 4 per page', '')], default='MEDIUM', update=reset_page)
    page: IntProperty(min=0, options={'SKIP_SAVE'})
    assign_on_click: BoolProperty(name='Assign on click', default=True,
                                  description='Click a material name to assign to selected objects or faces; without a mesh, only select it')


class MM_OT_palette_pick(bpy.types.Operator):
    bl_idname = 'mm_materials.palette_pick'
    bl_label = 'Choose Material'
    bl_options = {'REGISTER', 'UNDO'}
    material: StringProperty(options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return properties.material + '\nChoose this material; Assign on click uses selected mesh objects or faces'

    def execute(self, context):
        if context.scene.mm_asset_test.source_scene:
            self.report({'ERROR'}, 'Return to Authoring before assigning materials')
            return {'CANCELLED'}
        if self.material not in context.scene.mm_materials.materials:
            self.report({'ERROR'}, 'Refresh the library before choosing this material')
            return {'CANCELLED'}
        context.scene.mm_materials.material = self.material
        objects = context.objects_in_mode if context.mode == 'EDIT_MESH' else context.selected_objects
        if context.scene.mm_palette.assign_on_click and any(obj.type == 'MESH' for obj in objects):
            return bpy.ops.mm_materials.assign()
        return {'FINISHED'}


class MM_OT_palette_render(bpy.types.Operator):
    bl_idname = 'mm_materials.palette_render'
    bl_label = 'Render Material Thumbnails'
    bl_description = 'Render missing or changed material spheres in background Blender; the current scene is untouched'

    def execute(self, context):
        global _job
        temporary, log = None, None
        try:
            from . import textures_root
            if _job:
                raise ValueError('Material thumbnails are already rendering')
            cached = refresh(context)
            pending = [dict(name=item['name'], target=str(item['target'])) for item in cached['items']
                       if not item['rendered'] and not item['error']]
            if not pending:
                self.report({'INFO'}, 'Thumbnails are up to date; check MegaMek Palette Report if any material has an error')
                return {'FINISHED'}
            root = textures_root(context)
            cache = Path(pending[0]['target']).parent
            cache.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix='render-', dir=cache)
            folder = Path(temporary.name)
            (folder / 'request.json').write_text(json.dumps(dict(root=str(root), materials=pending)))
            log_path = cache / 'render.log'
            log = log_path.open('w', encoding='utf-8')
            process = subprocess.Popen([bpy.app.binary_path, '--background', '--factory-startup', '--disable-autoexec',
                                        '--threads', '4', '--python-exit-code', '1', '--python',
                                        str(Path(__file__).with_name('thumbnail_worker.py')), '--', str(folder)],
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            _job = dict(root=root, process=process, log=log, log_path=log_path, temporary=temporary, folder=folder)
            bpy.app.timers.register(poll_render, first_interval=.5)
            return {'FINISHED'}
        except Exception as error:
            if log:
                log.close()
            if temporary:
                temporary.cleanup()
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_OT_palette_cancel(bpy.types.Operator):
    bl_idname = 'mm_materials.palette_cancel'
    bl_label = 'Stop Rendering'

    def execute(self, context):
        stop_render()
        redraw()
        return {'FINISHED'}


class MM_OT_palette_page(bpy.types.Operator):
    bl_idname = 'mm_materials.palette_page'
    bl_label = 'Change Material Page'
    direction: IntProperty(default=1, options={'SKIP_SAVE'})

    def execute(self, context):
        _, page, pages, _ = page_items(context)
        context.scene.mm_palette.page = max(0, min(pages - 1, page + self.direction))
        return {'FINISHED'}


class MM_OT_browse_materials(bpy.types.Operator):
    bl_idname = 'mm_materials.browse_materials'
    bl_label = 'Browse Materials'
    bl_description = 'Open the separate MM Materials tab and load the library if needed'

    def execute(self, context):
        try:
            if not context.scene.mm_materials.materials:
                if bpy.ops.mm_materials.catalog() != {'FINISHED'}:
                    return {'CANCELLED'}
            area = context.area if context.area and context.area.type == 'VIEW_3D' else next(
                (area for area in context.screen.areas if area.type == 'VIEW_3D'), None)
            if not area:
                raise ValueError('Open a 3D View to browse materials')
            area.spaces.active.show_region_ui = True
            region = next(region for region in area.regions if region.type == 'UI')
            region.active_panel_category = 'MM Materials'
            area.tag_redraw()
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class MM_PT_palette(bpy.types.Panel):
    bl_label = 'Material Browser'
    bl_idname = 'MM_PT_palette'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MM Materials'
    bl_order = 0

    @classmethod
    def poll(cls, context):
        return not context.scene.mm_asset_test.source_scene

    def draw(self, context):
        layout = self.layout
        state = context.scene.mm_materials
        settings = context.scene.mm_palette
        if not state.materials:
            layout.label(text='Load the materials from your mm-data folder.')
            layout.operator('mm_materials.catalog', text='Load Materials', icon='FILE_REFRESH')
            return
        try:
            cached = library(context)
            items, page, pages, total = page_items(context)
        except Exception as error:
            layout.label(text=str(error), icon='ERROR')
            return
        row = layout.row(align=True)
        row.prop(settings, 'search', icon='VIEWZOOM', text='')
        row.operator('mm_materials.catalog', text='', icon='FILE_REFRESH')
        layout.prop(settings, 'folder')
        layout.prop(settings, 'size', text='')
        row = layout.row(align=True)
        previous = row.row(align=True)
        previous.enabled = page > 0
        previous.operator('mm_materials.palette_page', text='', icon='TRIA_LEFT').direction = -1
        row.label(text=f'{page + 1} / {pages} · {total} materials')
        following = row.row(align=True)
        following.enabled = page + 1 < pages
        following.operator('mm_materials.palette_page', text='', icon='TRIA_RIGHT').direction = 1
        layout.prop(settings, 'assign_on_click')
        if not items:
            layout.label(text='No matching materials.')
        columns, capacity, size = PAGE_LAYOUTS[settings.size]
        width = context.region.width / context.preferences.system.ui_scale
        size = max(1.8, min(size, (width - 35) / columns / 20 - 1.1))
        grid = layout.grid_flow(row_major=True, columns=columns, even_columns=True, even_rows=True, align=False)
        for item in items:
            cell = grid.box().column(align=True)
            if item['icon']:
                cell.template_icon(icon_value=item['icon'], scale=size)
            else:
                cell.label(text='Missing preview', icon='ERROR')
            button = cell.operator('mm_materials.palette_pick', text=item['label'], depress=state.material == item['name'])
            button.material = item['name']
            if item['error']:
                cell.label(text='Check .tres / maps', icon='ERROR')
        layout.separator()
        if state.material:
            layout.label(text=Path(state.material).stem.replace('-', ' '), icon='MATERIAL')
        row = layout.row()
        row.enabled = bool(state.material)
        row.operator('mm_materials.assign', text='Assign Chosen Material', icon='CHECKMARK')
        layout.label(text='Selected faces' if context.mode == 'EDIT_MESH' else 'Selected objects · active slot')
        obj = context.object
        if obj and obj.type == 'MESH' and obj.material_slots:
            header, body = layout.panel('mm_material_slots', default_closed=True)
            header.label(text='Material Slots')
            if body:
                body.template_list('MATERIAL_UL_matslots', '', obj, 'material_slots', obj, 'active_material_index', rows=3)
        if _job:
            layout.operator('mm_materials.palette_cancel', text='Thumbnails rendering… Stop', icon='CANCEL')


class MM_PT_library_setup(bpy.types.Panel):
    bl_label = 'Library Setup'
    bl_idname = 'MM_PT_library_setup'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MM Materials'
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return not context.scene.mm_asset_test.source_scene

    def draw(self, context):
        layout = self.layout
        state = context.scene.mm_materials
        prefs = context.preferences.addons[__package__].preferences
        layout.prop(state if state.root else prefs, 'root', text='mm-data')
        layout.operator('mm_materials.default_folder', icon='FILE_TICK')
        layout.label(text=f'{len(state.materials)} materials in library')
        layout.separator()
        layout.operator('mm_materials.reload', text='Reload Assigned Materials', icon='FILE_REFRESH')
        if not _job:
            layout.operator('mm_materials.palette_render', text='Build / Update Thumbnails', icon='RENDER_STILL')
        layout.label(text='Diagnostics: MegaMek Palette Report')


_classes = (MMPaletteState, MM_OT_palette_pick, MM_OT_palette_render, MM_OT_palette_cancel,
            MM_OT_palette_page, MM_OT_browse_materials, MM_PT_palette, MM_PT_library_setup)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mm_palette = PointerProperty(type=MMPaletteState)
    bpy.app.handlers.load_pre.append(stop_render)


def unregister():
    stop_render()
    clear_icons()
    bpy.app.handlers.load_pre.remove(stop_render)
    del bpy.types.Scene.mm_palette
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
