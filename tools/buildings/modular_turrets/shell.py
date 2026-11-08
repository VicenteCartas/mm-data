"""The turret shell every modular head builds on, the turret materials and the modelling helpers. +Y forward, +Z up.

The fixed collar and the yaw hull are separate. No firing or gameplay logic is embedded.
LOD1 is rebuilt with fewer parts and radial segments, never decimated.
"""
import bpy
import math
from pathlib import Path
from mathutils import Vector

# Textured roles are board materials (tools/materials/structures/turret).
TEXTURES = Path(__file__).resolve().parents[3] / 'data/models/board/textures'
# Board material albedo maps by image name, for the exported GLBs' relative URIs.
ALBEDOS = {}
MATS = {}
PARTS = []
LOD = 0

def role_material(name, material):
    # The game draws a base colour that is a board material's albedo as that material: its .tres gives the
    # tint, finish and normal map, so the Blender material needs the albedo alone.
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    image = mat.node_tree.nodes.new('ShaderNodeTexImage')
    albedo = TEXTURES/f'{material}_albedo.png'
    ALBEDOS[albedo.stem] = albedo
    image.image = bpy.data.images.load(str(albedo), check_existing=True)
    image.interpolation = 'Linear'; image.extension = 'REPEAT'
    mat.node_tree.links.new(image.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    return mat

def flat_material(name, color, metal=0, rough=.5, emission=0):
    mat=bpy.data.materials.new(name); mat.use_nodes=True
    p=mat.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    if emission:
        p.inputs['Emission Color'].default_value=(*color,1)
        p.inputs['Emission Strength'].default_value=emission
    mat.diffuse_color=(*color,1)
    return mat

def materials():
    # Armor plates and covers are the unit paint role on a painted steel plate (structures/turret/turret-paint): the
    # player's camouflage paints them in game, shaded by the plate's light and dark over its finish (GpuUnitCamouflage).
    MATS['armor']=MATS['pale']=role_material('paint','structures/turret/turret-paint')
    MATS['armor']['mmBuildingPaint']=True
    MATS['steel']=role_material('Turret | worn machined steel','structures/common/steel')
    MATS['edge']=role_material('Turret | rubbed alloy edges','structures/turret/turret-edge')
    MATS['dark']=role_material('Turret | dark mechanical steel','structures/turret/turret-dark')
    MATS['black']=flat_material('Turret | recesses',(.012,.016,.014),.5,.64)
    MATS['red']=flat_material('Turret | red optic',(.65,.012,.002),.2,.24,2.4)
    MATS['lens']=flat_material('Turret | optic core',(1,.20,.035),.0,.16,3)

def uv_project(obj, scale=9):
    # Consistent world-space density on each polygon, including small beveled faces.
    mesh=obj.data; layer=mesh.uv_layers.new(name='UVMap')
    seed=sum(ord(c) for c in obj.name)
    off=((seed%17)*.091, (seed%23)*.113)
    for face in mesh.polygons:
        n=face.normal; axis=max(range(3), key=lambda j:abs(n[j]))
        u,v=[j for j in range(3) if j != axis]
        for li in face.loop_indices:
            p=mesh.vertices[mesh.loops[li].vertex_index].co
            layer.data[li].uv=(p[u]/scale+off[0],p[v]/scale+off[1])

def mesh_obj(name, verts, faces, mat='armor', bevel=0, smooth=False, bevel_face=0):
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh); bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(MATS[mat])
    import bmesh
    bm=bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    if bevel and LOD==0:
        # Keep the exposed perimeter bevel; buried back and side edges do not need bevels.
        obj.data.materials.append(MATS['edge'])
        bm.faces.ensure_lookup_table()
        edges=list(bm.faces[bevel_face].edges)
        bmesh.ops.bevel(bm,geom=edges,offset=bevel,segments=1,affect='EDGES',
                       clamp_overlap=True,material=1)
        # Sloping-foot miters must stay inside the authored bounds, especially Z=0/18.
        bounds=[(min(v[i] for v in verts),max(v[i] for v in verts)) for i in range(3)]
        for v in bm.verts:
            for i,(lo,hi) in enumerate(bounds):v.co[i]=max(lo,min(hi,v.co[i]))
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.000001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces)); bm.to_mesh(obj.data); bm.free()
    for p in obj.data.polygons: p.use_smooth=smooth
    uv_project(obj)
    PARTS.append(obj)
    return obj

def clipped(w,d,c):
    x,y=w/2,d/2
    if c==0:return [(-x,-y),(x,-y),(x,y),(-x,y)]
    return [(-x+c,-y),(x-c,-y),(x,-y+c),(x,y-c),(x-c,y),(-x+c,y),(-x,y-c),(-x,-y+c)]

def loft(name, sections, mat='armor', bevel=0):
    # sections: list of rings of 3D coordinates, matching vertex count.
    n=len(sections[0]); verts=[p for ring in sections for p in ring]
    faces=[tuple(reversed(range(n))),tuple((len(sections)-1)*n+i for i in range(n))]
    for j in range(len(sections)-1):
        for i in range(n): faces.append((j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i))
    return mesh_obj(name,verts,faces,mat,bevel,bevel_face=1)

def block(name, center, size, mat='armor', cut=.2, bevel=.045, angle=0):
    w,d,h=size; x,y,z=center
    pts=clipped(w,d,min(cut,w*.3,d*.3))
    ca,sa=math.cos(angle),math.sin(angle)
    return loft(name,[[(x+px*ca-py*sa,y+px*sa+py*ca,z+zz) for px,py in pts] for zz in (-h/2,h/2)],mat,bevel)

def ring(name, profile, mat='steel', segments=None, center=(0,0), axis='Z', phase=0, bands=None):
    # profile [(distance along axis,radius)]; closes at ends, optionally forms a hollow mouth.
    n=segments or (32 if LOD==0 else 12)
    rings=[]
    for z,r in profile:
        pts=[]
        for i in range(n):
            a=2*math.pi*i/n+phase; x,y=r*math.cos(a),r*math.sin(a)
            pts.append((x+center[0],y+center[1],z) if axis=='Z' else (x+center[0],z,y+center[1]))
        rings.append(pts)
    o=loft(name,rings,mat)
    if bands:
        assert len(bands)==len(profile)-1
        for key in dict.fromkeys([*bands,'black']):
            if MATS[key].name not in o.data.materials:o.data.materials.append(MATS[key])
        for p in o.data.polygons:
            first,last=min(p.vertices)//n,max(p.vertices)//n
            key=bands[first] if last!=first else ('black' if first==len(profile)-1 else mat)
            p.material_index=o.data.materials.find(MATS[key].name)
    # Cylindrical UV avoids planar seams around barrels. Faces across the axis (caps, steps, shallow cones) take
    # the planar projection, which a cylindrical one would smear into radial streaks.
    uv=o.data.uv_layers.active
    for p in o.data.polygons:
        if abs(p.normal.z if axis=='Z' else p.normal.y)>.7:
            for li in p.loop_indices:
                co=o.data.vertices[o.data.loops[li].vertex_index].co
                uv.data[li].uv=(co.x/9,(co.y if axis=='Z' else co.z)/9)
            if len(p.vertices)==4:p.use_smooth=(axis=='Y')
            continue
        angles=[]
        for li in p.loop_indices:
            co=o.data.vertices[o.data.loops[li].vertex_index].co
            dx=co.x-center[0]; dy=(co.y-center[1]) if axis=='Z' else (co.z-center[1])
            angles.append(math.atan2(dy,dx)/(2*math.pi)+.5)
        if max(angles)-min(angles)>.5: angles=[a+1 if a<.5 else a for a in angles]
        for li,a in zip(p.loop_indices,angles):
            co=o.data.vertices[o.data.loops[li].vertex_index].co
            uv.data[li].uv=(a*max(r for _,r in profile)*.7,(co.z if axis=='Z' else co.y)/7)
        if len(p.vertices)==4:p.use_smooth=(axis=='Y')
    if axis=='Y':
        # Smooth around each barrel, but preserve the machined steps between profile bands.
        normals=[None]*len(o.data.loops)
        for p in o.data.polygons:
            for li in p.loop_indices:
                co=o.data.vertices[o.data.loops[li].vertex_index].co
                radial=Vector((co.x-center[0],0,co.z-center[1])).normalized()
                v=radial*math.hypot(p.normal.x,p.normal.z)+Vector((0,p.normal.y,0)) if p.use_smooth else p.normal
                normals[li]=v.normalized()
        o.data.normals_split_custom_set(normals)
    return o

def radial_panel(name, angle, width, bottom, top, r0, r1, thick, mat='armor'):
    ca,sa=math.cos(angle),math.sin(angle)
    # Tangent width and radial depth; tapered slab on a sloping face.
    def pt(t,r,z): return (r*ca-t*sa,r*sa+t*ca,z)
    sections=[]
    for z,r in [(bottom,r0),(top,r1)]:
        sections.append([pt(-width/2,r-thick/2,z),pt(width/2,r-thick/2,z),pt(width/2,r+thick/2,z),pt(-width/2,r+thick/2,z)])
    verts=[p for section in sections for p in section]
    faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    # Face 4 is the broad outward panel, including on the sloping collar and feet.
    return mesh_obj(name,verts,faces,mat,.055,bevel_face=4)

def slab(name, points, thickness=.28, mat='armor'):
    return loft(name,[[(x,y,z-thickness) for x,y,z in points],points],mat,.035)

def bolt(center, axis='Z', mat='edge', radius=.14):
    x,y,z=center
    # The cap preserves the visible screw; the tiny cylindrical body was buried in armor.
    points=[]
    for i in range(6):
        a=i*math.pi/3
        points.append((x+radius*math.cos(a),y+radius*math.sin(a),z+.06) if axis=='Z'
                      else (x+radius*math.cos(a),y+.06,z-radius*math.sin(a)))
    return mesh_obj('Captive bolt cap',points,[tuple(range(6))],mat)

def flat_patch(name,center,size,axis='Z',mat='black'):
    x,y,z=center;w,h=size
    points=[(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]
    if axis=='X':verts=[(x,y+u,z+v) for u,v in points]
    elif axis=='-X':verts=[(x,y-u,z+v) for u,v in points]
    elif axis=='Y':verts=[(x+u,y,z-v) for u,v in points]
    else:verts=[(x+u,y+v,z) for u,v in points]
    return mesh_obj(name,verts,[tuple(range(4))],mat)

def join_parts(name, parts, parent=None, pivot=(0,0,0)):
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.join()
    o=parts[0]; o.name=name
    # Keep transforms explicit and pivot centered after joining geometry.
    bpy.context.scene.cursor.location=pivot
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    if parent:
        matrix=o.matrix_world.copy(); o.parent=parent; o.matrix_world=matrix
    return o

def empty(name, parent=None, location=(0,0,0)):
    o=bpy.data.objects.new(name,None); bpy.context.scene.collection.objects.link(o)
    o.empty_display_type='PLAIN_AXES'; o.empty_display_size=2
    o.parent=parent; o.location=location
    return o

def turret(lod):
    """The fixed collar (-mount) and the rotating hull (-head under -yaw); weapons are separate modules."""
    global LOD,PARTS
    LOD=lod; PARTS=[]
    root=empty(f'shell-lod{lod}')
    # The fixed mount remains flush with the wall or column cap as the head yaws.
    ring('Mount gasket',[(-.45,11.5),(.25,11.5)],'black',16 if lod==0 else 12)
    ring('Fixed mounting collar',[(0,14.1),(.6,14.1),(2.25,12.25),(2.75,11.7)],'dark',8,phase=math.pi/8)
    ring('Collar upper rim',[(2.5,11.8),(2.78,11.8)],'edge',24 if lod==0 else 12)
    for i in range(8):
        a=math.pi/4*i
        if lod==0:radial_panel('Collar armor sector',a,8.2,.25,2.40,13.15,11.8,.7)
        if lod==0:
            radial_panel('Collar service panel',a,5.5,.65,2.12,13.5,12.24,.10,'armor')
            for s in (-1,1):
                r=12.55; t=s*2
                bolt((r*math.cos(a)-t*math.sin(a),r*math.sin(a)+t*math.cos(a),1.9),radius=.12)
        if i%2==1:
            radial_panel('Raised collar cover',a,5.2,1.8,3.15,12.9,11.6,.65,'pale')
    join_parts(f'shell-lod{lod}-mount',PARTS.copy(),root)
    PARTS=[]
    yaw=empty(f'shell-lod{lod}-yaw',root,(0,0,2.8))
    ring('Bearing shadow',[(2.75,9.75),(3.15,9.75)],'black',16 if lod==0 else 12)
    ring('Rotating bearing',[(3.05,9.6),(3.55,9.6),(5.7,7.9)],'dark',16 if lod==0 else 8)
    for i in range(8):
        a=i*math.pi/4
        if lod==0:radial_panel('Bearing segmented skirt',a,5.6,3.65,5.5,9.18,7.85,.27,'dark')
        if lod==0:radial_panel('Bearing recessed panel',a,3.8,3.85,5.25,9.33,8.1,.04,'armor')
    # Dark continuous core, with armor plates separated by narrow black panel gaps.
    loft('Armored internal core',[
        [(x,y,5.6) for x,y in clipped(17,13,3)],
        [(x,y,8.0) for x,y in clipped(21.0,17.0,3.8)],
        [(x,y,10.1) for x,y in clipped(21.0,17.0,3.8)],
        [(x,y,13.1) for x,y in clipped(10.0,12.0,2.5)]
    ],'dark')
    # Eight broad lower armor panels; not a stack of boxes.
    bottom=clipped(17.5,13.5,2.9); middle=clipped(23.0,18.0,3.8)
    for i in range(8):
        j=(i+1)%8
        b0,b1=Vector(bottom[i]),Vector(bottom[j]); m0,m1=Vector(middle[i]),Vector(middle[j])
        b0,b1=b0.lerp(b1,.025),b0.lerp(b1,.975)
        m0,m1=m0.lerp(m1,.025),m0.lerp(m1,.975)
        vs=[(*b0,5.7),(*b1,5.7),(*m1,8.0),(*m0,8.0),(*b0*.96,5.7),(*b1*.96,5.7),(*m1*.96,8.0),(*m0*.96,8.0)]
        mesh_obj('Lower faceted armor',vs,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],'armor',.045)
    # Large shoulders splay outward around the recessed weapon roots.
    for s in (-1,1):
        slab('Rear sloping shoulder',[(s*x,y,14.7-.27*x) for x,y in [
            (6.25,-6.0),(8.0,-8.2),(10.6,-5.8),(11.2,-1.4),(6.25,-.8)]],1.15)
        slab('Forward sloping shoulder',[(s*x,y,14.7-.27*x) for x,y in [
            (6.4,-.35),(10.6,.3),(11.2,3.6),(9.4,6.5),(6.5,5.7)]],1.15)
        block('Forward cheek armor',(s*8.0,6.4,9.7),(6.4,5.3,2.8),cut=1.25,bevel=.07,angle=-s*.16)
        slab('Upper cheek cover',[(s*x,y,14.82-.27*x) for x,y in [
            (7.1,3.1),(9.2,3.1),(9.8,4.2),(8.8,5.6),(7.1,5.3)]],.12,'pale')
        block('Rear shoulder',(s*7.9,-6.3,9.9),(5.4,4.8,3.3),cut=1.1,bevel=.065,angle=s*.2)
        if lod==0:
            slab('Shoulder inset',[(s*x,y,14.78-.27*x) for x,y in [
                (6.9,-5.5),(8.0,-6.6),(9.9,-5.0),(10.2,-2.0),(6.9,-1.65)]],.08,'dark')
        # Segmented side belt follows the hull silhouette.
        if lod==0:
            for yy in (-3.9,-.7,2.5):
                block('Outer side armor segment',(s*10.9,yy,8.7),(1.15,2.95,2.35),cut=.35,bevel=.045)
        if lod==0:
            for yy in (-4.8,-1.5):bolt((s*7.7,yy,12.74),radius=.12)
            block('Cheek panel gasket',(s*8,7.8,8.25),(3.8,1.3,1.9),'black',cut=.2,bevel=0)
            block('Cheek lower cap',(s*8,8.45,8.25),(3.45,.30,1.55),'armor',cut=.2,bevel=.04)
            for xx in (-1.35,1.35):bolt((s*8+xx,8.64,8.25),'Y',radius=.11)
    # Sloped central top and broad hatch.
    loft('Center roof wedge',[
      [(x,y,10.8) for x,y in clipped(11.5,14,2.0)],
      [(x,y-1.0,13.4) for x,y in clipped(9.5,11.4,1.8)]
    ],'armor',.06)
    block('Central hatch seam',(0,-2.15,13.48),(8.7,8.1,.16),'black',cut=1.1,bevel=0)
    block('Broad central armor hatch',(0,-2.15,13.75),(8.35,7.75,.46),cut=1.05,bevel=.055)
    block('Rear pale service hatch',(0,-6.1,14.18),(5.9,3.7,.45),'pale',cut=.65,bevel=.035)
    block('Service hatch inset',(0,-6.1,14.43),(5.0,2.85,.06),'steel',cut=.5,bevel=0)
    if lod==0:
        for x in (-3.25,3.25):
            for y in (-4.9,.3):bolt((x,y,14.02))
        for x in (-1.9,1.9):block('Hatch hinge',(x,-5.95,13.95),(.9,1.0,.4),'steel',cut=0,bevel=0)
        block('Hatch handle recess',(0,-1.15,14.0),(1.75,1,.025),'black',cut=.15,bevel=0)
        block('Hatch handle',(0,-1.15,14.13),(1.45,.2,.25),'edge',cut=0,bevel=0)
        # Rear vent bank and towing/lifting fixtures.
        block('Rear vent inset',(0,-8.78,9.5),(10.5,.25,2.2),'black',cut=.3,bevel=0)
        for i in range(11):block('Cooling louver',(-4.7+i*.94,-8.99,9.5),(.38,.15,1.65),'dark',cut=0,bevel=0)
        for s in (-1,1):block('Rear lifting lug',(s*8.8,-6.4,12.2),(.55,1.9,1.6),'steel',cut=.2,bevel=.06,angle=s*.2)
    # Forward red optic in its own armored recess, distinct from the weapon apertures.
    block('Optic armored brow',(0,6.15,11.4),(3.8,4.0,2.8),cut=.7,bevel=.05)
    block('Optic bezel',(0,8.24,11.2),(2.4,.36,2.05),'edge',cut=.35,bevel=.025)
    block('Optic black well',(0,8.46,11.2),(1.95,.12,1.65),'black',cut=.2,bevel=0)
    ring('Optic lens metal ring',[(8.53,.70),(8.66,.70),(8.70,.56),(8.53,.56)],'steel',12 if lod==0 else 8,(0,11.2),axis='Y')
    ring('Red lens',[(8.54,.54),(8.64,.54),(8.68,.45)],'red',12 if lod==0 else 8,(0,11.2),axis='Y')
    bolt((0,8.64,11.2),'Y','lens',.14)
    join_parts(f'shell-lod{lod}-head',PARTS.copy(),yaw)
    PARTS=[]
    return root

def descendants(root):return [root,*root.children_recursive]

def export(root, path):
    bpy.ops.object.select_all(action='DESELECT')
    for r in root:
        for o in descendants(r):o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,use_active_scene=True,
        export_yup=True,export_materials='EXPORT',export_extras=True,
        export_animations=False,export_cameras=False,export_lights=False,
        export_texcoords=True,export_normals=True,export_tangents=False,
        export_image_format='AUTO',export_apply=True)

def camera(name, pos, target, scale):
    data=bpy.data.cameras.new(name); obj=bpy.data.objects.new(name,data)
    bpy.context.scene.collection.objects.link(obj); obj.location=pos
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    data.type='ORTHO'; data.ortho_scale=scale
    bpy.context.scene.camera=obj
    return obj

def studio():
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.samples=48
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1400; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
    scene.world=bpy.data.worlds.new('Turret studio')
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.19,.22,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.35
    scene.view_settings.view_transform='AgX'
    for name,pos,power,size in [('Key',(-28,16,48),34000,30),('Fill',(30,5,22),18000,26),('Rim',(6,-32,30),40000,20)]:
        data=bpy.data.lights.new(name,'AREA'); data.energy=power; data.shape='DISK'; data.size=size
        o=bpy.data.objects.new(name,data); scene.collection.objects.link(o); o.location=pos
        o.rotation_euler=(Vector((0,0,6))-o.location).to_track_quat('-Z','Y').to_euler()
    ground=flat_material('Studio ground',(.085,.092,.10),0,.8)
    bpy.ops.mesh.primitive_plane_add(size=2000,location=(0,0,-.5)); o=bpy.context.object;o.name='Studio ground';o.data.materials.append(ground)
    camera('Hero camera',(43,55,37),(0,6,7),52)
