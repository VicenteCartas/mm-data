"""Reproducible ruby crystal meshes; execute with Blender MCP's background executor."""
import hashlib, json, math, random, re, sys
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path('C:/Projects/megamek/mm-data')
WORK=Path('C:/Projects/megamek/megamek_temp/work/crystal-cover')
BOARD=ROOT/'data/models/board'
sys.path.insert(0,str(ROOT/'tools'))
from glb_geometry import write_glb
FORMS=[('cover-low-fan',811,18,8,7.5,5,True),('cover-low-crown',812,18,6,9,5,False),
 ('cover-low-ridge',813,18,9,7.5,5,True),('cover-spire',821,36,5,6.5,5,False),
 ('cover-forked',822,36,6,8.5,5,True),('cover-fan',823,36,8,7.8,5,True),('cover-crown',824,36,5,9,5,False)]
FORMS += [(f'giant-level{n}',840+n,18*n,28,14+.3*n,12,False) for n in range(1,6)]
MATERIALS=[dict(id='crystal',diffuse=[1,1,1],roughness=.23,metallic=0,textures=[
 dict(id='ruby',type='DIFFUSE',filename='../textures/crystal/ruby-crystal_albedo.png')])]

def clip(faces, normal, distance):
    result=[]; cut=[]
    for face in faces:
        kept=[]
        for a,b in zip(face,face[1:]+face[:1]):
            da,db=normal.dot(a)-distance,normal.dot(b)-distance
            if da<=1e-6:kept.append(a)
            if (da<0)!=(db<0):
                point=a.lerp(b,da/(da-db));kept.append(point);cut.append(point)
        if len(kept)>=3:result.append(kept)
    unique=[]
    for p in cut:
        if all((p-q).length>1e-5 for q in unique):unique.append(p)
    if len(unique)>2:
        centre=sum(unique,Vector())/len(unique);axis=(unique[0]-centre).normalized();across=normal.cross(axis).normalized()
        unique.sort(key=lambda p:math.atan2((p-centre).dot(across),(p-centre).dot(axis)))
        result.append(unique)
    return result

def prism(rng,height,radius,origin,lean,lod):
    # Intersect planes rather than triangulating warped rings: every major facet stays optically flat.
    corners=[Vector((x,y,z)) for z in (0,height*2) for y in (-radius*3,radius*3) for x in (-radius*3,radius*3)]
    faces=[[corners[i] for i in f] for f in [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)]]
    turn=rng.uniform(-.4,.4);apothem=radius*math.cos(math.pi/6)
    for i in range(6):
        angle=turn+i*math.tau/6;nx,ny=math.cos(angle),math.sin(angle)
        faces=clip(faces,Vector((nx,ny,0)),apothem)
        # Rhombohedral terminations: broad alternating faces ending in an asymmetric basal table.
        table=rng.uniform(.48,.68) if i%2==0 else rng.uniform(.76,.88)
        slope=apothem*(1-table)/(height*.3)
        faces=clip(faces,Vector((nx,ny,slope)),apothem*table+slope*height)
        basal=apothem*.12/(height*.18)
        faces=clip(faces,Vector((nx,ny,-basal)),apothem*.88)
    tilt=math.tan(rng.uniform(math.radians(15),math.radians(30))) if rng.random()<.45 else rng.uniform(.015,.08)
    azimuth=rng.uniform(-math.pi,math.pi)
    faces=clip(faces,Vector((tilt*math.cos(azimuth),tilt*math.sin(azimuth),1)),height)
    # These sparse rigid meshes keep the same optical boundaries at every LOD.
    for i in range(6):
        angle=turn+(i+.5)*math.tau/6
        faces=clip(faces,Vector((math.cos(angle),math.sin(angle),0)),radius*.975)
    vertices=[];indices=[];top=max(p.z for f in faces for p in f)
    for face in faces:
        indices.append(tuple(range(len(vertices),len(vertices)+len(face))))
        for p in face:
            z=p.z*height/top
            vertices.append(Vector((p.x+origin[0]+lean[0]*z/height,p.y+origin[1]+lean[1]*z/height,z)))
    return vertices,indices

def composition(name,i,rng,height,reach,radius,count):
    if name.startswith('giant'):
        anchors=[(-9,-4),(17,8),(-19,17),(12,-19),(-10,-24),(27,-3),(-29,-1),(1,27)]
        x,y=anchors[i%len(anchors)];x+=rng.uniform(-2,2);y+=rng.uniform(-2,2)
        if name=='giant-level1' and i in (1,2,3): x*=.72;y*=.72
        heights=[1,.72,.48,.4,.28,.36,.29,.32]
        h=height*(heights[i] if i<8 else rng.uniform(.1,.25))
        r=radius*(1 if i==0 else .73 if i==1 else rng.uniform(.35,.56))
        lean=(2+rng.uniform(-1.5,1.5),-1+rng.uniform(-1,1))
    else:
        x,y=0,0;h=height;r=radius;lean=(height*.04,-height*.02)
        if i:
            angle=i*2.3+rng.uniform(-.4,.4);distance=reach*rng.uniform(.7,1.1)
            x,y=math.cos(angle)*distance,math.sin(angle)*distance
            h=height*rng.uniform(.24,.6);r=radius*rng.uniform(.4,.65)
            lean=(height*.06+rng.uniform(-2,2),-height*.025+rng.uniform(-1,1))
        if 'forked' in name and i==1:x,y,h,r,lean=5,3,height*.83,radius*.8,(-5,2)
        if 'fan' in name:
            x,y=(i-1)*3.7,(i%2)*2;h=height*(1 if i==0 else [.72,.5,.36,.25][i-1]);lean=(-height*.22,height*.055)
        if 'ridge' in name:
            x,y=(i-1)*4,(i-1)*2.2;h=height*(1 if i==0 else [.75,.54,.36,.26][i-1]);lean=(height*.09,0)
        if 'crown' in name:lean=(rng.uniform(-1,1),rng.uniform(-1,1))
    return x,y,h,r,lean

def make_mesh(name,vertices,faces,scene,role):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);mesh.materials.append(bpy.data.materials[role])
    uv=mesh.uv_layers.new(name='UVMap')
    identity=re.sub(r'-lod[0-3]', '', name)
    phase=int.from_bytes(hashlib.sha256(identity.encode()).digest()[:4],'little')/2**32
    for poly in mesh.polygons:
        normal=poly.normal.normalized()
        up=Vector((0,0,1));up-=normal*up.dot(normal)
        if up.length<.1:
            up=Vector((0,1,0));up-=normal*up.dot(normal)
        up.normalize();across=up.cross(normal).normalized()
        for li in poly.loop_indices:
            p=mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv=(p.dot(across)*.045+phase,p.dot(up)*.045+phase*.73)
    return obj
def model(name,objects):
    vertices=[];parts=[];refs=[]
    for obj in objects:
        mesh=obj.data;mesh.calc_loop_triangles();indices=[]
        for tri in mesh.loop_triangles:
            a,b,c=[mesh.vertices[k].co for k in tri.vertices];ab,ac=b-a,c-a
            if ab.cross(ac).length_squared < max(1e-12,max(ab.length_squared,ac.length_squared)**2*1e-10):continue
            for li in tri.loops:
                p=mesh.vertices[mesh.loops[li].vertex_index].co;uv=mesh.uv_layers.active.data[li].uv
                indices.append(len(vertices)//12);vertices.extend([*p,*tri.normal,1,1,1,1,uv.x,1-uv.y])
        parts.append(dict(id=obj.name,type='TRIANGLES',indices=indices))
        refs.append(dict(meshpartid=obj.name,materialid=obj.data.materials[0].name))
    return dict(id=name,materials=MATERIALS,meshes=[dict(attributes=['POSITION','NORMAL','COLOR','TEXCOORD0'],vertices=vertices,parts=parts)],nodes=[dict(id=name,parts=refs)])
for spec in MATERIALS:
    mat=bpy.data.materials.get(spec['id']) or bpy.data.materials.new(spec['id']);mat.use_nodes=True
    p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*spec['diffuse'],1)
    p.inputs['Roughness'].default_value=.14 if spec['id']=='crystal' else .9
    if spec['id']=='crystal':
        p.inputs['Base Color'].default_value=(.98,.98,.98,1)
        p.inputs['IOR'].default_value=1.76;p.inputs['Transmission Weight'].default_value=.85
        image=bpy.data.images.load(str(BOARD/'textures/crystal/ruby-crystal_albedo.png'));image.pack()
        tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image
        absorption=mat.node_tree.nodes.new('ShaderNodeVolumeAbsorption');absorption.inputs['Density'].default_value=.06
        mat.node_tree.links.new(tex.outputs['Color'],absorption.inputs['Color'])
        mat.node_tree.links.new(absorption.outputs['Volume'],mat.node_tree.nodes.get('Material Output').inputs['Volume'])
manifest={};scenes=[]
for name,seed,height,reach,radius,count,fan in FORMS:
    scene=bpy.data.scenes.new(name);scenes.append(scene);levels={}
    for lod in range(4):
        rng=random.Random(seed);objects=[]
        for i in range(count):
            x,y,h,r,lean=composition(name,i,rng,height,reach,radius,count)
            v,f=prism(random.Random(seed*100+i),h,r,(x,y),lean,lod)
            if name.startswith('giant'):
                near,_=prism(random.Random(seed*100+i),h,r,(x,y),lean,1)
                norm=max(max(abs(p.y)/36,abs(p.x)/42+abs(p.y)/72) for p in near)
                factor=min(1,.93/norm)
                for p in v:p.x*=factor;p.y*=factor
            objects.append(make_mesh(f'{name}-lod{lod}-shard{i}',v,f,scene,'crystal'))
        for chip in range(8 if name.startswith('giant') else 3):
            crumbs=random.Random(seed*71+chip);angle=crumbs.random()*math.tau;distance=reach*crumbs.uniform(.45,1)
            size=crumbs.uniform(1.2,2.7) if name.startswith('giant') else crumbs.uniform(.45,1.1)
            v,f=prism(crumbs,size*crumbs.uniform(.7,1.5),size,(math.cos(angle)*distance,math.sin(angle)*distance),(size*.8,-size*.4),lod)
            for p in v:p.z-=size*.25
            # An oblique break through the small crystal leaves an angular fragment, not a miniature complete prism.
            faces=[[v[k] for k in face] for face in f]
            faces=clip(faces,Vector((0,0,-1)),0)
            cut=Vector((.45,-.25,1));centre=Vector((math.cos(angle)*distance,math.sin(angle)*distance,0))
            faces=clip(faces,cut,cut.dot(centre)+size*.65)
            v=[];f=[]
            for face in faces:f.append(tuple(range(len(v),len(v)+len(face))));v.extend(p.copy() for p in face)
            objects.append(make_mesh(f'{name}-lod{lod}-fragment{chip}',v,f,scene,'crystal'))
        levels[lod]=model(f'{name}-lod{lod}',objects)
        for obj in objects: obj.hide_render=lod>0
    path=BOARD/'crystal'/f'{name}.glb';path.parent.mkdir(parents=True,exist_ok=True);write_glb(path,levels=levels)
    lods=[dict(node=f'{name}-lod{i}',triangles=sum(len(p['indices'])//3 for p in m['meshes'][0]['parts']),vertices=len(m['meshes'][0]['vertices'])//12) for i,m in levels.items()]
    manifest['crystal/'+name]=dict(mesh='crystal/'+name+'.glb',lods=lods,triangles=lods[0]['triangles'],vertices=lods[0]['vertices'],source='tools/board-models/crystal/build_crystals.py')
source=ROOT/'tools/board-models/crystal/sources/crystals.blend';source.parent.mkdir(parents=True,exist_ok=True)
bpy.context.window.scene=scenes[0]
for scene in list(bpy.data.scenes):
    if scene not in scenes: bpy.data.scenes.remove(scene)
bpy.ops.wm.save_as_mainfile(filepath=str(source),compress=True)
(WORK/'new-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
result=dict(source=str(source),assets=list(manifest))
