"""Native Blender authoring for modular turret heads and detachable equipment.

Run with `blender --background --factory-startup --python author.py` or through Blender MCP.
"""
import bpy
import importlib.util
import json
import math
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parents[2] / 'data/models/buildings/turrets/modular'
# The shared shell, turret materials and modelling helpers.
spec = importlib.util.spec_from_file_location('turret_shell', ROOT/'shell.py')
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)
REPORT = {}
pillar = {'HERE': ROOT}
exec(compile((ROOT/'pillar.py').read_text(encoding='utf-8'),'pillar','exec'),pillar)
racks = {}
exec(compile((ROOT/'racks.py').read_text(encoding='utf-8'),'racks','exec'),racks)
pods = {'HERE': ROOT}
exec(compile((ROOT/'pod_mounts.py').read_text(encoding='utf-8'),'pod_mounts','exec'),pods)
# Gun families authored on the shared receivers: module name, descriptor family, tier, authoring file.
GUNS = [(f'artillery{suffix}','ballistic',tier,'artillery.py')
        for suffix,tier in (('-light','light'),('','standard'),('-heavy','heavy'))] + [
       (f'gauss{suffix}','ballistic',tier,'gauss.py') for suffix,tier in (('-light','light'),('','standard'),('-heavy','heavy'))] + [
       (f'rotary-{size}','ballistic',size,'rotary.py') for size in ('2','5')] + [
       (f'hag-{size}','ballistic',f'hag-{size}','hag.py') for size in ('20','30','40')] + [
       (f'plasma-{tier}','energy',tier,'plasma.py') for tier in ('rifle','cannon')] + [
       ('flamer','flamer','light','flamer.py'),('flamer-heavy','flamer','heavy','flamer.py')]

def reset():
    name = 'Modular turret authoring'
    if name in bpy.data.scenes:
        old = bpy.data.scenes[name]
        for obj in list(old.objects): bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(old)
    scene = bpy.data.scenes.new(name)
    if bpy.context.window: bpy.context.window.scene = scene
    ref.materials()
    for key, mat in ref.MATS.items():
        # The unit paint role keeps its name: camouflage finds it by that name.
        if mat.name != 'paint': mat.name = 'authored/' + key
        mat.use_backface_culling=True
    ref.MATS['blue'] = ref.flat_material('authored/blue-lens',(.015,.16,.65),.4,.2,.6)
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT/'renders').mkdir(exist_ok=True)
    return scene

def meshes(root): return [o for o in ref.descendants(root) if o.type == 'MESH']

def bounds(root):
    bpy.context.view_layer.update()
    points = [o.matrix_world@v.co for o in meshes(root) for v in o.data.vertices]
    return {'min':[min(v[i] for v in points) for i in range(3)],
            'max':[max(v[i] for v in points) for i in range(3)]}

def export(name, roots, kind, family, joints, points=None, emitters=None, rig=None):
    ref.export(roots, OUT/(name+'.glb'))
    descriptor = {'schema':2,'kind':kind,'family':family,'mesh':name+'.glb',
                  'bounds':bounds(roots[0]),'rig':rig or ('building-turret-v1' if kind=='body' else 'equipment-v1'),
                  'joints':joints,'locations':{},'hardpoints':points or [],'emitters':emitters or []}
    (OUT/(name+'.json')).write_text(json.dumps(descriptor,indent=2)+'\n')
    REPORT[name] = [sum(len(p.vertices)-2 for o in meshes(r) for p in o.data.polygons) for r in roots]
    for root in roots:
        for obj in ref.descendants(root): obj.hide_render=True; obj.hide_set(True)

def pad(name, x, y, z, w, h):
    if ref.LOD==0: ref.block(name+' gasket',(x,y-.08,z),(w+.22,.35,h+.22),'black',cut=0,bevel=0)
    ref.block(name+' plate',(x,y+.12,z),(w,.25,h),'steel',cut=0,bevel=0)
    ref.flat_patch(name+' key',(x,y+.255,z),(w*.28,.11),'Y','black')
    if ref.LOD==0:
        for dx in (-w*.38,w*.38):
            for dz in (-h*.37,h*.37): ref.bolt((x+dx,y+.255,z+dz),'Y',radius=.10)

def head(form):
    roots=[]; points=[]
    for lod in (0,1):
        root=ref.turret(lod)
        ref.LOD=lod
        fixed=next(o for o in root.children if o.name.split('.')[0].endswith('-mount'))
        yaw=next(o for o in root.children if o.name.split('.')[0].endswith('-yaw'))
        shell=next(o for o in yaw.children if o.name.split('.')[0].endswith('-head'))
        if form=='pillar':
            # The missile pillar replaces the broad shell on the same fixed collar.
            bpy.data.objects.remove(shell,do_unlink=True)
            ref.PARTS=[]
            pillar['shell'](ref,lod)
            shell=ref.join_parts('armor',ref.PARTS.copy(),yaw)
        root.name=f'head-{form}-lod{lod}'
        fixed.name='mount'; yaw.name='yaw'; shell.name='armor'
        assembly=ref.empty('root',root)
        fixed.parent=assembly; yaw.parent=assembly
        # Identical child names in separate exports; Blender appends suffixes in-memory.
        root['node_names']={assembly.name:'root',fixed.name:'mount',yaw.name:'yaw',shell.name:'armor'}
        ref.PARTS=[]
        if form=='pods': slots=[]
        elif form=='pillar': slots=[('center',0,pillar['FRONT'],12.6,5.0,4.6)]
        elif form=='mixed': slots=[('center',0,9.2,10.25,6,5),('left',-7.4,7.7,10.25,5.9,5),('right',7.4,7.7,10.25,5.9,5)]
        elif form=='center': slots=[('center',0,9.2,10.25,7,5.4)]
        elif form=='twin': slots=[('left',-4.8,7.7,10.25,6.8,5.4),('right',4.8,7.7,10.25,6.8,5.4)]
        else:
            slots=[(f'{side}-{row}',sign*8.0,9.6,z,5.6,3.35)
                   for side,sign in [('left',-1),('right',1)] for row,z in enumerate((7.0,11.0,15.0))]
            slots += [('center',0,9.3,10.0,5.4,5.2)]
            for sign in (-1,1):
                # A full receiver bay extends back into the hull behind every stacked gun.
                shapes={}
                exec(compile((ROOT/'hard_surface.py').read_text(),'hard_surface','exec'),shapes)
                ref.loft('Tapered armored receiver bay',
                         [[(sign*8+x,y,11+z) for x,z in shapes['section'](w,h,.65)]
                          for y,w,h in [(-1,5.5,8),(2,6.5,11.7),(9.7,6.5,12.2)]],'armor')
                ref.block('Receiver bay rear service cover',(sign*8,-1.04,11),(4.3,.18,6.5),'steel',cut=.35,bevel=0)
                if lod==0:
                    for z in (7,11,15):
                        ref.flat_patch('Receiver bay side cooling panel',(sign*11.26,3.5,z),(3.9,1.7),
                                       'X' if sign>0 else '-X','dark')
        if form=='pillar':
            slots += [('aux-left',-1.5,pillar['FRONT'],7.6,1.6,1.5),('aux-right',1.5,pillar['FRONT'],7.6,1.6,1.5)]
            slots += [('external-searchlight',*pillar['LAMP'],2.2,2.0)]
        else:
            slots += [('aux-left',-3.0,8.4,6.4,1.6,1.5),('aux-right',3.0,8.4,6.4,1.6,1.5)]
            lamp_x,lamp_y=0,-7.2
            slots += [('external-searchlight',lamp_x,lamp_y,15.1,2.2,2.0)]
            ref.block('Lamp pedestal',(lamp_x,lamp_y-.7,13.9),(2.5,2.1,2.0),'armor',cut=.2,bevel=.02)
        # The sockets are mating faces, not floating plates. Solid adapter webs bury their
        # rear ends in the core and terminate behind the gasket, at both detail levels.
        if form not in ('twin','pods','pillar'):
            ref.block('Central adapter web',(0,8.05,10.15),(7.7 if form=='center' else 6.3,2.7,5.8),'armor',cut=.45,bevel=.03)
            if form=='shoulder':
                ref.block('Optic supporting pedestal',(0,6.0,12.9),(3.2,4.4,3.0),'armor',cut=.35,bevel=.03)
        for sign in (-1,1) if form!='pillar' else ():
            ref.block('Lower socket web',(sign*3,7.25,6.5),(1.95,2.65,1.8),'armor',cut=.2,bevel=.02)
        for sid,x,y,z,w,h in slots: pad(sid,x,y,z,w,h)
        # Mixed roof/front batteries need a clear sweep above the center bay. Seat
        # their optic low in the forward hull, between the auxiliary sockets.
        if form not in ('twin','pods','pillar'):
            # Identify the original optic geometry by its small bounded region, not by material.
            import bmesh
            bm=bmesh.new(); bm.from_mesh(shell.data)
            remaining=set(bm.verts)
            while remaining:
                seed=next(iter(remaining)); stack=[seed]; island=set()
                while stack:
                    v=stack.pop()
                    if v in island: continue
                    island.add(v); stack.extend(e.other_vert(v) for e in v.link_edges)
                remaining-=island
                coords=[shell.matrix_world@v.co for v in island]
                if min(v.y for v in coords)>4.1 and max(abs(v.x) for v in coords)<2.0 and min(v.z for v in coords)>9.5:
                    for v in island:
                        if form=='shoulder': v.co.z+=4.0
                        else:
                            v.co.y+=1.35
                            v.co.z-=5.6
            bm.to_mesh(shell.data); bm.free()
        carrier=ref.join_parts('carrier',ref.PARTS.copy(),yaw)
        # Explicit export names are normalized in a staging scene below.
        root['node_names'][carrier.name]='carrier'
        if lod==0:
            bpy.context.view_layer.update()
            points=[{'id':sid,'location':'*','side':'front','node':'yaw','position':list(yaw.matrix_world.inverted()@Vector((x,y+.25,z))),
                     'rotation':[0,0,0,1],'size':[w,30,h], 'minScale':.35,'maxScale':1,
                     'roles':['weapon','misc']} for sid,x,y,z,w,h in slots]
            # Roof sockets mark the rear of a roof weapon; its shared mount (posts or pedestal)
            # seats in the hull. These are not front sockets.
            roof=[('pod-center',0,-4.6,pillar['TOP']-2.3)] if form=='pillar' else [
                (sid,x,-4,11) for sid,x in [('pod-center',0),('pod-left',-4.5),('pod-right',4.5),
                                           ('pod-wide-left',-8.6),('pod-wide-right',8.6),
                                           ('pod-outer-left',-12.9),('pod-inner-left',-4.3),
                                           ('pod-inner-right',4.3),('pod-outer-right',12.9)]]
            for sid,x,y,z in roof:
                points.append({'id':sid,'location':'*','side':'front','node':'yaw',
                               'position':list(yaw.matrix_world.inverted()@Vector((x,y,z))),
                               'rotation':[0,0,0,1],'size':[8.2,15,11],
                               'minScale':1,'maxScale':1,'roles':['weapon']})
            # Side launcher arms leave the head flanks: the shared arm bracket (mount-arm) stands on the socket and
            # the launcher hangs outboard of its bearing (BuildingTurretVisual).
            if form=='pillar':
                arms=[(sid,s*pillar['FLANK'],-.3,z) for sid,(s,z) in pillar['ARMS'].items()]
            else:
                flank=10.8 if form=='shoulder' else 11.45
                arms=[('arm-left',-flank,-.7,9.0),('arm-right',flank,-.7,9.0)]
            for sid,x,y,z in arms:
                points.append({'id':sid,'location':'*','side':'front','node':'yaw',
                               'position':list(yaw.matrix_world.inverted()@Vector((x,y,z))),
                               'rotation':[0,0,0,1],'size':[14,30,12],
                               'minScale':1,'maxScale':1,'roles':['weapon']})
        roots.append(root)
    normalize_export('head-'+form,roots,'body','building-turret',{'root':'root','turret':'yaw'},points)
    return roots

def casemate(form):
    """A wall casemate: an armored embrasure fixed on the wall face and a gun shield that yaws within it (the
    renderer limits it to 60 degrees each way, the weapon's three-hexside arc). Y=0 is the wall surface, +Y points out
    of the wall and Z=0 is the middle of the floor; one or two guns sit in the shield's front sockets."""
    twin=form=='twin'; width=16.5 if twin else 13.5
    slots=[('left',-3.9,5.25,0,5.6,4.6),('right',3.9,5.25,0,5.6,4.6)] if twin else [('center',0,5.25,0,6.6,5.0)]
    roots=[]; points=[]
    for lod in (0,1):
        ref.LOD=lod; ref.PARTS=[]
        root=ref.empty(f'head-casemate{"-twin" if twin else ""}-lod{lod}')
        assembly=ref.empty('root',root)
        ref.block('Embrasure frame',(0,.25,0),(width+5.5,2.0,14.5),'armor',cut=1.2,bevel=.05)
        ref.block('Embrasure brow',(0,1.7,7.7),(width+6.5,3.4,1.6),'armor',cut=.4,bevel=.04)
        ref.block('Embrasure sill',(0,1.3,-7.5),(width+5.5,2.6,1.2),'armor',cut=.3,bevel=.03)
        ref.block('Embrasure recess',(0,1.3,0),(width+1,.1,10.6),'black',cut=1,bevel=0)
        if lod==0:
            for x in (-(width+5.5)/2+1.3,(width+5.5)/2-1.3):
                for z in (-5.4,0,5.4): ref.bolt((x,1.27,z),'Y',radius=.2)
        frame=ref.join_parts('mount',ref.PARTS.copy(),assembly)
        ref.PARTS=[]
        yaw=ref.empty('yaw',assembly,(0,1.3,0))
        ref.ring('Shield yaw drum',[(-5.0,3.4),(5.0,3.4)],'dark',16 if lod==0 else 8,(0,1.3),axis='Z')
        ref.block('Gun shield',(0,3.3,0),(width,3.7,9.4),'armor',cut=1.4,bevel=.06)
        ref.block('Shield face plate',(0,5.2,0),(width-1.3,.3,8.2),'steel',cut=1.1,bevel=0)
        shield=ref.join_parts('armor',ref.PARTS.copy(),yaw,pivot=(0,1.3,0))
        ref.PARTS=[]
        for sid,x,y,z,w,h in slots: pad(sid,x,y,z,w,h)
        carrier=ref.join_parts('carrier',ref.PARTS.copy(),yaw,pivot=(0,1.3,0))
        root['node_names']={assembly.name:'root',frame.name:'mount',yaw.name:'yaw',shield.name:'armor',
                            carrier.name:'carrier'}
        if lod==0:
            bpy.context.view_layer.update()
            points=[{'id':sid,'location':'*','side':'front','node':'yaw',
                     'position':list(yaw.matrix_world.inverted()@Vector((x,y+.25,z))),'rotation':[0,0,0,1],
                     'size':[w,30,h],'minScale':.35,'maxScale':1,'roles':['weapon','misc']}
                    for sid,x,y,z,w,h in slots]
        roots.append(root)
    normalize_export('head-casemate'+('-twin' if twin else ''),roots,'body','building-turret',
                     {'root':'root','turret':'yaw'},points,rig='building-casemate-v1')
    return roots

def normalize_export(name, roots, kind, family, joints, points=None, emitters=None, rig=None):
    # Blender names are globally unique. Export one LOD at a time into a temporary name map
    # and merge glTF LODs without touching buffers is avoided: names are normalized in GLB JSON.
    export(name,roots,kind,family,joints,points,emitters,rig)
    import os, struct
    path=OUT/(name+'.glb'); raw=path.read_bytes(); n,t=struct.unpack_from('<II',raw,12)
    doc=json.loads(raw[20:20+n]); mapping={}
    for root in roots: mapping.update(dict(root.get('node_names',{})))
    for node in doc['nodes']:
        if node.get('name') in mapping: node['name']=mapping[node['name']]
        node.pop('extras',None)  # node_names: this export's name map, nothing the game reads.
    binary=raw[28+n:28+n+struct.unpack_from('<I',raw,20+n)[0]]
    # Images reference the board materials' albedo maps instead of travelling inside every GLB.
    embedded=set()
    for image in doc.get('images',[]):
        embedded.add(image.pop('bufferView')); image.pop('mimeType')
        albedo=ref.ALBEDOS[image['name']]; assert albedo.is_file(), albedo
        image['uri']=os.path.relpath(albedo,path.parent).replace(os.sep,'/')
    kept,data={},bytearray()
    for index,view in enumerate(doc['bufferViews']):
        if index in embedded: continue
        start=view.get('byteOffset',0); data+=b'\0'*(-len(data)%4)
        view['byteOffset']=len(data); data+=binary[start:start+view['byteLength']]; kept[index]=len(kept)
    doc['bufferViews']=[view for index,view in enumerate(doc['bufferViews']) if index in kept]
    for accessor in doc['accessors']: accessor['bufferView']=kept[accessor['bufferView']]
    data+=b'\0'*(-len(data)%4); doc['buffers'][0]['byteLength']=len(data)
    chunk=json.dumps(doc,separators=(',',':')).encode(); chunk+=b' ' *((-len(chunk))%4)
    tail=struct.pack('<II',len(data),0x004E4942)+data
    result=struct.pack('<4sII',b'glTF',2,20+len(chunk)+len(tail))+struct.pack('<II',len(chunk),t)+chunk+tail
    path.write_bytes(result)

def half_width(objects):
    bpy.context.view_layer.update()
    return max(abs((o.matrix_world@v.co).x) for o in objects if o.type=='MESH' for v in o.data.vertices)

def equipment(name, family, variant=None, rack=False, source=None):
    """One weapon module for every installation, centred on its trunnion, with a boss on each side for a mount's pins.
    A launcher (rack) is its rack. A gun is its barrel or emitter, the receiver that carries it on the roof and the
    mantlet that seals it in a front bay; a planned mount omits the part its installation does not show
    (BuildingTurretVisual). Its 'face' point is where the barrel leaves the receiver, the front bay's datum; its
    'trunnion' point is where its bosses end, against the mounts' pins.
    source: the gun family's authoring file (layout, barrel, mantlet, body); AC and PPC by family, the MG and lasers
    in exposed_weapons.py."""
    roots=[]; emitters=[]; points=[]
    pod_shapes={'HERE':ROOT}
    exec(compile((ROOT/'pod_mounts.py').read_text(encoding='utf-8'),'pod_mounts','exec'),pod_shapes)
    gun_shapes={'HERE':ROOT}
    if not rack:
        shapes_source=source or {'ballistic':'ballistic.py','ppc':'ppc.py'}.get(family,'exposed_weapons.py')
        exec(compile((ROOT/shapes_source).read_text(encoding='utf-8'),shapes_source,'exec'),gun_shapes)
        width,shift,cy,cz=gun_shapes['layout'](family,variant)
    for lod in (0,1):
        ref.LOD=lod; ref.PARTS=[]
        root=ref.empty(name+f'-lod{lod}'); joint=ref.empty('module',root)
        aim=ref.empty('aim',joint)
        recoil=ref.empty('recoil',aim) if family in ('ballistic','machine-gun') else None
        fixed=[]; spinning=[]; receiver=[]; mantlet=[]
        tips=[]
        if source or family in ('ballistic','ppc'):
            gun={'HERE':ROOT}
            gun_source=source or ('ballistic.py' if family=='ballistic' else 'ppc.py')
            exec(compile((ROOT/gun_source).read_text(encoding='utf-8'),gun_source,'exec'),gun)
            barrel_start=len(ref.PARTS)
            tips=gun['barrel'](ref,family,variant,lod)
            # A rotary barrel cluster turns about its axis while firing: it gets its own joint inside the recoil joint.
            if gun.get('SPIN'): spinning=ref.PARTS[barrel_start:]
            mantlet=gun['mantlet'](ref,family,variant,lod)
        elif family=='machine-gun':
            length,radius=7,.42
            profile=[(0,radius*1.25),(.9,radius*1.25),(1.3,radius),(length-2,radius*.65),
                     (length-2,radius*.82),(length,radius*.82),(length,radius*.51),(length-1,radius*.51)]
            bands=['dark','steel','steel','dark','dark','edge','black']
            if lod:
                indices=(0,2,5,6,7)
                profile=[profile[i] for i in indices]; bands=[bands[i] for i in indices[:-1]]
            ref.ring('Machined cannon',profile,'steel',8 if lod==0 else 6,(0,0),axis='Y',bands=bands)
            tips=[(0,length,0)]
        elif family in ('laser','missile'):
            shapes={'HERE':ROOT}
            exec(compile((ROOT/'weapon_shapes.py').read_text(),'weapon_shapes','exec'),shapes)
            tips=shapes['draw'](ref,family,variant,lod)
        if rack:
            centre=pod_shapes['dimensions'](*variant)[1]/2
            boss_start=len(ref.PARTS)
            reach=pod_shapes['rack_trunnion'](ref,*variant,lod)
        else:
            # The barrel begins at the front of the receiver.
            for obj in ref.PARTS: obj.location.y+=shift
            tips=[(x,y+shift,z) for x,y,z in tips]
            receiver=gun_shapes['body'](ref,family,variant,lod)
            centre=cy
            boss_start=len(ref.PARTS)
            reach=pod_shapes['gun_trunnion'](ref,half_width(receiver or ref.PARTS),cy,lod)
        # Bosses turn with elevation; they never slide with the recoiling barrel.
        fixed.extend(ref.PARTS[boss_start:])
        # The weapon pitches about its trunnion, the module's origin.
        for obj in ref.PARTS: obj.location.y-=centre
        tips=[(x,y-centre,z) for x,y,z in tips]
        root['node_names']={joint.name:'module',aim.name:'aim'}
        moving=[o for o in ref.PARTS if o not in fixed and o not in spinning and o not in receiver and o not in mantlet]
        if moving:
            mesh=ref.join_parts('geometry',moving,recoil or aim)
            root['node_names'][mesh.name]='geometry'
        if spinning:
            # The barrel axis runs through the trunnion.
            spin=ref.join_parts('spin',spinning,recoil or aim)
            root['node_names'][spin.name]='spin'
        if recoil: root['node_names'][recoil.name]='recoil'
        for parts,node in ((fixed,'collar'),(receiver,'receiver'),(mantlet,'mantlet')):
            if parts:
                joined=ref.join_parts(node,parts,aim)
                root['node_names'][joined.name]=node
        if lod==0:
            role='launcher' if family=='missile' else 'beam' if family in ('laser','ppc','energy') else 'muzzle'
            effect={'missile':'missile','laser':'laser','ppc':'ppc','energy':'energy','flamer':'flame'}.get(family,'bullet')
            node='spin' if spinning else 'recoil' if recoil else 'aim'
            emitters=[{'id':f'{role}-{i}','node':node,'position':list(p),'direction':[0,1,0],'role':role,'effect':effect} for i,p in enumerate(tips)]
            held=[('trunnion',(reach,0,0))]
            if not rack: held.append(('face',(0,shift-centre,0)))
            points=[{'id':pid,'location':'*','side':'front','node':'module','position':list(position),
                     'rotation':[0,0,0,1],'size':[1,1,1],'minScale':1,'maxScale':1,'roles':['weapon']} for pid,position in held]
        roots.append(root)
    joints={'root':'module','aim':'aim','elevation':'aim'}
    if family in ('ballistic','machine-gun'): joints['recoil']='recoil'
    if spinning: joints['spin']='spin'
    normalize_export(name,roots,'equipment',family,joints,points=points,emitters=emitters)
    return roots

def mount(name, shape, *holds):
    """A shared weapon mount (pod_mounts): a fixed body whose hardpoints are where it holds a weapon: the tip of its
    trunnion pin, against the weapon's side, or a pedestal's hinge axis and the seat a weapon rests on. BuildingTurretVisual places it beside or under
    a weapon; the left arm bracket and post are the right ones turned half a turn."""
    roots=[]
    for lod in (0,1):
        ref.LOD=lod; ref.PARTS=[]
        root=ref.empty(f'{name}-lod{lod}'); assembly=ref.empty('root',root)
        shape(ref,lod)
        body=ref.join_parts('mount',ref.PARTS.copy(),assembly)
        root['node_names']={assembly.name:'root',body.name:'mount'}
        roots.append(root)
    points=[{'id':pid,'location':'*','side':'front','node':'root','position':list(position),'rotation':[0,0,0,1],
             'size':[1,1,1],'minScale':1,'maxScale':1,'roles':['weapon']} for pid,position in holds]
    normalize_export(name,roots,'body','building-turret',{'root':'root'},points,rig='building-mount-v1')

def build():
    reset()
    bodies={form:head(form) for form in ('center','twin','shoulder','pods','mixed','pillar')}
    for form in ('single','twin'): casemate(form)
    for calibre in ('2','5','10','20','compact'): equipment('autocannon-'+calibre,'ballistic',calibre)
    equipment('machine-gun','machine-gun')
    for size in ('small','medium','large'): equipment('laser-'+size,'laser',size)
    for tier in ('light','standard','heavy'): equipment('ppc' if tier=='standard' else 'ppc-'+tier,'ppc',tier)
    for name,family,variant,source in GUNS: equipment(name,family,variant,source=source)
    for kind,rack in racks['RACKS'].items():
        for count in rack['cols']:
            name=racks['name'](kind,count)
            equipment(name,'missile',(kind,count),rack=True)
    # The shared mounts external weapons ride, each with the point that holds the weapon.
    mount('mount-arm',lambda ref,lod: pods['bracket'](ref,1,lod),('pin',(pods['ARM_PIN'],0,0)))
    mount('mount-post',pods['post'],('pin',(pods['POST_PIN'],0,pods['POST_HEIGHT'])))
    mount('mount-pedestal',pods['pedestal'],('hinge',(0,0,pods['PEDESTAL_HINGE'])),
          ('seat',(0,0,pods['PEDESTAL_HINGE']+pods['PIN_RADIUS'])))
    (ROOT/'geometry.json').write_text(json.dumps(REPORT,indent=2)+'\n')
    for obj in ref.descendants(bodies['twin'][0]): obj.hide_render=False; obj.hide_set(False)
    ref.studio()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'modular-turrets.blend'))
    return REPORT


if __name__ == '__main__':
    build()
