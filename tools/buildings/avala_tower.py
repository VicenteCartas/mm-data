"""Avala-inspired fixed authored Tower. Build through the live Blender MCP.

One metre = 3 model units. Concrete 136.65m, mast 68m, viewpoint 122m.
Private helper-module instances keep the concurrent civic authoring state intact.
Only this script's Tower scene is rebuilt; no other scene or asset is saved.
"""
import importlib.util
from collections import defaultdict
from contextlib import contextmanager
import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def private_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shared = private_module('_tower_shared', 'authored_examples.py')
geometry = private_module('_tower_geometry', 'hpg_headquarters.py')
geometry.shared = shared
from glb_geometry import display, write_glb
from mm_building_materials import glb as glb_container

mesh, prism, box = geometry.mesh, geometry.prism, geometry.box
beam, cylinder = geometry.beam, geometry.cylinder
CONCRETE = shared.CONCRETE
STEEL = shared.STEEL
PAINT = 'structures/common/painted-steel'
GLASS = 'structures/buildings/tower-glass'
GRILLE = 'structures/common/grille'
WARM_LIGHT = (1.0, .55, .20)
WINDOW_LIGHT = (.32, .21, .055)
RED_LIGHT = (1.0, .008, .002)
STONE = (1, .99, .93)
DARK = (.31, .35, .35)
ALLOY = (.75, .78, .77)
GLAZING = (.84, .94, .96)
RED = (.57, .20, .14)
TOP = (136.65 + 68) * 3
MAST_BASE = 136.65 * 3
VIEWPOINT = 122 * 3
SCENE = 'Civic tower'
NAME = 'civic-tower'


def triangle(radius, cut=.12):
    corners = [Vector((radius * math.cos(math.pi/2+i*math.tau/3),
                       radius * math.sin(math.pi/2+i*math.tau/3))) for i in range(3)]
    return [tuple(a.lerp(b, fraction)) for a,b in zip(corners,corners[1:]+corners[:1])
            for fraction in (cut, 1-cut)]


def loft(name, rings, material=CONCRETE, colour=STONE, hollow=0, helper=False, tint=False,
         cap_bottom=0, cap_top=0):
    """Closed shell through matching CCW contours; optional open interior."""
    n=len(rings[0][1]);count=len(rings)
    verts=[(x,y,z) for z,outline in rings for x,y in outline]
    faces=[]
    for k in range(count-1):
        for i in range(n):
            j=(i+1)%n
            faces.append((k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i))
    if hollow:
        inner=[(z,geometry.inset_outline(outline,hollow)) for z,outline in rings]
        # Exterior soffits/roof caps close the shell without baking interior floors.
        if cap_bottom:
            (z,a),(zz,b)=inner[:2]
            inner[0]=(z+cap_bottom,[tuple(Vector(p).lerp(Vector(q),cap_bottom/(zz-z)))
                                      for p,q in zip(a,b)])
        if cap_top:
            (z,a),(zz,b)=inner[-2:]
            inner[-1]=(zz-cap_top,[tuple(Vector(p).lerp(Vector(q),1-cap_top/(zz-z)))
                                       for p,q in zip(a,b)])
        offset=len(verts)
        verts += [(x,y,z) for z,outline in inner for x,y in outline]
        for k in range(count-1):
            for i in range(n):
                j=(i+1)%n
                faces.append((offset+k*n+j,offset+k*n+i,offset+(k+1)*n+i,offset+(k+1)*n+j))
        for i in range(n):
            j=(i+1)%n;top=(count-1)*n
            if not cap_bottom:faces.append((j,i,offset+i,offset+j))
            if not cap_top:faces.append((top+i,top+j,offset+top+j,offset+top+i))
        if cap_bottom:
            faces += [tuple(reversed(range(n))),tuple(range(offset,offset+n))]
        if cap_top:
            faces += [tuple(range(top,top+n)),tuple(reversed(range(offset+top,offset+top+n)))]
    else:
        faces += [tuple(reversed(range(n))),tuple(range((count-1)*n,count*n))]
    obj=mesh(name,verts,faces,material,colour,helper=helper)
    if tint:obj['building_paint']=True
    return obj


def tri_loft(name, profile, cut=.12, **kwargs):
    return loft(name,[(z,triangle(radius,cut)) for z,radius in profile],**kwargs)


def poured_loft(name, rings, hollow=0, cap_bottom=0):
    # Real3m formwork courses. Independent UV origins prevent long repeated tiles;
    # adjacent closed shells share their exact boundary, leaving no open gaps.
    levels=sorted({z for z,_ in rings} | set(range(math.ceil(rings[0][0]/9)*9,
                                                 math.floor(rings[-1][0])+1,9)))
    def contour(z):
        for (z0,a),(z1,b) in zip(rings,rings[1:]):
            if z0<=z<=z1:
                return [tuple(Vector(p).lerp(Vector(q),(z-z0)/(z1-z0))) for p,q in zip(a,b)]
        raise ValueError(z)
    for i,(z0,z1) in enumerate(zip(levels,levels[1:])):
        shade=random.Random(name+str(i)).uniform(.975,1.015)
        loft(name+' cast course',[(z0,contour(z0)),(z1,contour(z1))],
             colour=tuple(c*shade for c in STONE),hollow=hollow,tint=True,
             cap_bottom=cap_bottom if i==0 else 0)


def band(name, radius, z, depth, material=CONCRETE, colour=STONE, cut=.12):
    return geometry.outline_band(name,triangle(radius,cut),z,depth,1.2,
                                 key=material,colour=colour)


def panel(name, points, center, tangent, material, colour, depth=.2, detail=False):
    obj=prism(name,points,-depth/2,depth/2,material,colour,detail)
    u=Vector(tangent).normalized();z=Vector((0,0,1));normal=u.cross(z)
    basis=Matrix(((u.x,z.x,normal.x,0),(u.y,z.y,normal.y,0),
                  (u.z,z.z,normal.z,0),(0,0,0,1)))
    obj.matrix_world=Matrix.Translation(Vector(center))@basis
    return obj


def rect(x0,x1,z0,z1):
    return [(x0,z0),(x1,z0),(x1,z1),(x0,z1)]


def emissive(obj, factor, night_only=False):
    # The shared exporter expects display-space colours. Use a non-emissive
    # library finish so the game cannot add the dome material's extra glow/map.
    return shared.emissive(obj,tuple(display(c) for c in factor),night=night_only)


def glazing_ring(name, lower_radius, upper_radius, bottom, top, cut=.12, bay=5):
    emissive(tri_loft(name+' glass',[(bottom,lower_radius),(top,upper_radius)],cut,
             material=GLASS,colour=GLAZING,hollow=.22),WINDOW_LIGHT,night_only=True)
    a,b=triangle(lower_radius+.15,cut),triangle(upper_radius+.15,cut)
    for i in range(len(a)):
        j=(i+1)%len(a)
        p,q=Vector(a[i]),Vector(a[j]);r,s=Vector(b[i]),Vector(b[j])
        count=max(1,round((q-p).length/bay))
        for k in range(count):
            t=k/count
            beam(name+' mullion',(*p.lerp(q,t),bottom),(*r.lerp(s,t),top),
                 .34,.34,STEEL,ALLOY)
        beam(name+' window sill',(*p,bottom),(*q,bottom),.48,.48,STEEL,ALLOY)
        beam(name+' window head',(*r,top),(*s,top),.48,.48,STEEL,ALLOY)


def entrance_door(center, tangent=(1,0,0)):
    # 2.4m tall, paired 1.1m leaves: human scale inside a much larger pod.
    c=Vector(center);u=Vector(tangent);n=u.cross(Vector((0,0,1)))
    panel('entry metal frame',rect(-3.6,3.6,0,7.8),c,u,STEEL,ALLOY,.36)
    for side in (-1,1):
        emissive(panel('entry glazed door',rect(-1.45,1.45,.35,7.35),
              c+u*side*1.65+n*.22,u,GLASS,GLAZING,.12),WINDOW_LIGHT,night_only=True)
        a=c+u*side*.42+n*.42+Vector((0,0,2.6))
        beam('door pull',a,a+Vector((0,0,1.4)),.12,.12,STEEL,ALLOY,True)
    panel('entrance light housing',rect(-3.4,3.4,0,.8),c+n*.25+Vector((0,0,8.1)),
          u,STEEL,DARK,.7)
    emissive(panel('entrance warm downlight',rect(-2.8,2.8,0,.28),c+n*.66+Vector((0,0,8.3)),
          u,PAINT,(1,.85,.65),.15),WARM_LIGHT)


def handrail(name, a, b, spacing=3, detail_posts=True):
    a,b=Vector(a),Vector(b)
    beam(name+' top',a+Vector((0,0,3.3)),b+Vector((0,0,3.3)),.18,.18,STEEL,DARK)
    beam(name+' middle',a+Vector((0,0,1.7)),b+Vector((0,0,1.7)),.12,.12,STEEL,ALLOY,True)
    count=max(1,math.ceil((b-a).length/spacing))
    for i in range(count+1):
        p=a.lerp(b,i/count)
        fine_post=detail_posts and i not in (0,count) and i%3!=0
        beam(name+' baluster',p,p+Vector((0,0,3.3)),.12,.12,STEEL,ALLOY,fine_post)


def tripod():
    for k in range(3):
        angle=math.pi/2+k*math.tau/3
        u=Vector((math.cos(angle),math.sin(angle)));v=Vector((-u.y,u.x))
        rings=[]
        # Keep the feet/outer silhouette; extend the inner haunch into the shaft.
        for z,radius,depth,width in [(0,63,11,10),(36,44,11,10),(54,32,14,9.4),
                                     (66,25,14,9),(75,20.4,12.8,7.5),
                                     (90,15.15,7.3,5),(108,10.9,1.6,2)]:
            points=[tuple(u*(radius+dr)+v*ds) for dr,ds in
                    [(-depth/2,-width/2),(depth/2,-width/2),(depth/2,width/2),(-depth/2,width/2)]]
            rings.append((z,points))
        poured_loft('splayed concrete leg',rings)
        loft('building_volume leg',rings,material=shared.FLAT,colour=(.3,.8,.65),helper=True)
        foot=[tuple(u*(63+dr)+v*ds) for dr,ds in [(-6,-5.7),(6,-5.7),(6,5.7),(-6,5.7)]]
        prism('leg foundation',foot,0,1.1,CONCRETE,(.72,.73,.69))
        # Construction courses follow the actual inclined outer face, not a decal grid.
        for z in range(9,100,9):
            for (z0,p0),(z1,p1) in zip(rings,rings[1:]):
                if z0<=z<=z1:
                    t=(z-z0)/(z1-z0)
                    a=Vector(p0[1]).lerp(Vector(p1[1]),t)+u*.045
                    b=Vector(p0[2]).lerp(Vector(p1[2]),t)+u*.045
                    beam('leg pour joint',(*a,z),(*b,z),.075,.075,CONCRETE,(.66,.67,.63),True)
                    break


def shaft():
    profile=[(54,34),(75,21),(96,14.5),(306,12.8),(322,12.8)]
    poured_loft('triangular concrete shaft',[(z,triangle(r)) for z,r in profile],hollow=1.9,cap_bottom=.6)
    tri_loft('building_volume tapered shaft',profile[:-1]+[(324,12.8)],
             material=shared.FLAT,colour=(.3,.8,.65),helper=True)
    # 3m pours and narrower corner strips anchor the size of the bare shaft.
    for z in range(81,307,9):
        for (z0,r0),(z1,r1) in zip(profile,profile[1:]):
            if z0<=z<=z1:
                radius=r0+(r1-r0)*(z-z0)/(z1-z0)
                outline=triangle(radius+.045)
                for i in (0,2,4):
                    a,b=outline[i],outline[(i+1)%len(outline)]
                    beam('shaft formwork course',(*a,z),(*b,z),.07,.07,
                         CONCRETE,(.72,.73,.68),z%27!=0)
                    p,q=Vector(a),Vector(b);t=(q-p).normalized();n=Vector((t.y,-t.x,0))
                    count=max(2,round((q-p).length/4.5))
                    for j in range(1,count):
                        at=Vector((*p.lerp(q,j/count),z-2.1))
                        cylinder('form tie recess',at-n*.02,at+n*.035,.11,
                                 CONCRETE,(.45,.47,.44),6,True)
                    if z%27==0:
                        a3=Vector((*p.lerp(q,.5),z-8.7));b3=Vector((*p.lerp(q,.5),z-.1))
                        beam('form board vertical joint',a3+n*.035,b3+n*.035,.045,.045,
                             CONCRETE,(.72,.73,.68),True)
                break
    # Small maintenance slits on one face are metre-scale, not storey-sized windows.
    for z in (144,180,216,252,288):
        radius=14.5+(12.8-14.5)*(z-96)/(306-96)
        points=triangle(radius);a,b=Vector(points[2]),Vector(points[3])
        mid=(a+b)/2;t=(b-a).normalized();n=Vector((t.y,-t.x))
        panel('shaft inspection slot',rect(-1,1,0,.7),(*tuple(mid+n*.09),z),
              (*t,0),GRILLE,DARK,.14)


def entrance_pod():
    tri_loft('hanging lower lift core',[(18,15),(24,16),(30,16)],.20,hollow=1.4,cap_bottom=.6)
    # The suspended pod connects to the upper shaft through a real lift enclosure.
    # Without this continuation, the glazing/crown would float inside the flare.
    core=[(24,15.8),(36,12.5),(108,12.5)]
    tri_loft('continuous suspended lift enclosure',core,.20,hollow=1.3)
    tri_loft('building_volume suspended lift enclosure',core,.20,
             material=shared.FLAT,colour=(.3,.8,.65),helper=True)
    for k in range(3):
        a=math.pi/2+k*math.tau/3
        beam('pod suspension web',(10*math.cos(a),10*math.sin(a),50),
             (27*math.cos(a),27*math.sin(a),54),3,4,CONCRETE,STONE)
    tri_loft('entrance faceted underside',[(24,18),(29,29),(32,32)],.20,hollow=1.5)
    tri_loft('entrance concrete belt',[(32,32),(40,32)],.20,hollow=1.4,tint=True)
    glazing_ring('inclined entrance glazing',32,22,40,54,.20,4.8)
    tri_loft('entrance crown',[(54,22.1),(56,21.2)],.20,hollow=1.0)
    tri_loft('building_volume entrance pod',[(18,15),(24,16),(30,32),(40,32),(54,22)],.20,
             material=shared.FLAT,colour=(.3,.8,.65),helper=True)
    for i,(a,b) in enumerate(zip(triangle(32.1,.20),triangle(32.1,.20)[1:]+triangle(32.1,.20)[:1])):
        p,q=Vector(a),Vector(b);t=(q-p).normalized();n=Vector((t.y,-t.x));mid=(p+q)/2
        if (q-p).length>18:
            panel('entrance ventilation grille',rect(-5,5,0,4.5),(*tuple(mid+n*.1),33.3),
                  (*t,0),GRILLE,(.65,.68,.65),.24)
    # Short bridge to a compact ground-access stair; the tripod undercroft stays open.
    box('access bridge deck',(0,-54,34.6),(11,76,2.8),CONCRETE,STONE)
    prism('building_volume access bridge',[(-5.5,-92),(5.5,-92),(5.5,-16),(-5.5,-16)],
          33.2,36,shared.FLAT,(.3,.8,.65),helper=True)
    for x in (-5.7,5.7):
        beam('bridge steel edge',(x,-92,35.3),(x,-16,35.3),.55,1.4,STEEL,ALLOY)
        handrail('bridge railing',(x,-92,36),(x,-17,36),2.7)
        for y in (-86,-68,-50,-32):
            box('bridge bulkhead housing',(x,y,36.6),(.65,1.4,1.15),STEEL,DARK)
            emissive(box('bridge courtesy light',(x-math.copysign(.37,x),y,36.65),
                (.14,.85,.45),PAINT,(1,.8,.5)),WARM_LIGHT)
    box('bridge terminal landing',(0,-97,34.6),(18,12,2.8),CONCRETE,STONE)
    for x in (-7.2,7.2):
        box('landing support',(x,-97,17),(2.8,8,34),CONCRETE,STONE)
    for a,b in [((-9,-103),(-9,-91)),((9,-103),(9,-91)),
                ((-9,-91),(-5.7,-91)),((5.7,-91),(9,-91)),
                ((-5.7,-91),(-5.7,-92)),((5.7,-91),(5.7,-92)),
                ((-9,-103),(-8,-103)),((-1,-103),(9,-103))]:
        handrail('upper landing guard',(*a,36),(*b,36))
    # The far access is a two-flight stair, avoiding an unsupported bridge end.
    for side,y0,y1,z0,z1 in [(-1,-103,-133,36,18),(1,-133,-103,18,0)]:
        center_x=side*4.5
        profile=[(y0,z0-1.8),(y1,z1-1.8),(y1,z1),(y0,z0)]
        if z1==0:profile=[(y0,z0-1.8),(y1,0),(y0,z0)]
        obj=prism('stair structural stringer',profile,-3.5,3.5,CONCRETE,STONE)
        obj.matrix_world=Matrix(((0,0,1,center_x),(1,0,0,0),(0,1,0,0),(0,0,0,1)))
        for i in range(36):
            t=i/36;u=(i+1)/36
            y=y0+(y1-y0)*(t+u)/2;z=z0+(z1-z0)*max(t,u)
            box('human scale stair tread',(center_x,y,z+.25),(7,abs(y1-y0)/36+.035,.5),CONCRETE,STONE,True)
        for x in (center_x-3.5,center_x+3.5):
            handrail('stair handrail',(x,y0,z0),(x,y1,z1),3.5)
    box('stair half landing',(0,-135,17.2),(17,5,1.6),CONCRETE,STONE)
    for x in (-7,7):box('stair half landing pier',(x,-135,8.2),(2,3,16.4),CONCRETE,STONE)
    for a,b in [((-8.5,-132.5),(-8.5,-137.5)),((-8.5,-137.5),(8.5,-137.5)),
                ((8.5,-137.5),(8.5,-132.5)),((-8.5,-132.5),(-8,-132.5)),
                ((-1,-132.5),(1,-132.5)),((8,-132.5),(8.5,-132.5))]:
        handrail('half landing guard',(*a,18),(*b,18))
    # Backed by a solid surround: the glazing above the belt leans in behind the door's upper half.
    box('entry door surround',(0,-15.2,40.2),(8,2,8.4),STEEL,DARK)
    entrance_door((0,-16.2,36))


def observation_head():
    # Two clearly separated glazed tiers, with the upper lookout at exactly122m.
    tri_loft('head splayed structural underside',[(306,12.8),(318,33),(324,39)],hollow=2.0)
    tri_loft('lower turret concrete skirt',[(324,39),(332,39),(336,36)],hollow=1.5,tint=True)
    glazing_ring('lower turret windows',36,39,336,345)
    tri_loft('lower turret fascia',[(345,39.1),(348,39.1),(351,32)],hollow=1.4)
    tri_loft('recessed turret waist',[(351,31.8),(359,31.8)],material=STEEL,colour=DARK,hollow=1)
    tri_loft('observation balcony underside',[(357,32),(363,40),(VIEWPOINT,40)],hollow=4.2)
    glazing_ring('viewpoint windows',35.5,38,VIEWPOINT,378)
    # The way out onto the railed balcony, in a surround standing proud of the outward-leaning glass.
    box('balcony door surround',(0,-18.1,VIEWPOINT+4.2),(8,1.7,8.4),STEEL,DARK)
    entrance_door((0,-19,VIEWPOINT))
    tri_loft('viewpoint overhanging roof',[(378,39),(381,40),(385,35)],hollow=1.6,tint=True)
    tri_loft('upper technical room',[(384,34.8),(399,30.5)],hollow=1.4,tint=True)
    tri_loft('concrete mast cap',[(399,30.5),(MAST_BASE,8.8)],hollow=1.8,cap_top=.75)
    # Helpers enclose only concrete/occupied spaces and stop below the antenna.
    tri_loft('building_volume lower head',[(306,12.8),(318,33),(324,39),(348,39),(360,32)],
             material=shared.FLAT,colour=(.3,.8,.65),helper=True)
    tri_loft('building_volume viewpoint',[(354,32),(360,35.5),(378,38),(396,31.5)],
             material=shared.FLAT,colour=(.3,.8,.65),helper=True)
    outline=triangle(39.1)
    for a,b in zip(outline,outline[1:]+outline[:1]):
        handrail('viewpoint safety rail',(*a,VIEWPOINT),(*b,VIEWPOINT),3)
    for i,(a,b) in enumerate(zip(triangle(33),triangle(33)[1:]+triangle(33)[:1])):
        p,q=Vector(a),Vector(b);t=(q-p).normalized();n=Vector((t.y,-t.x));mid=(p+q)/2
        if (q-p).length>25:
            panel('upper equipment louver',rect(-8,8,0,4),(*tuple(mid+n*.3),389),
                  (*t,0),GRILLE,(.63,.66,.64),.3)


def antenna():
    # 50m of tapered lattice, then an18m broadcast whip:68m in total.
    prism('mast anchored base plate',triangle(8.8),MAST_BASE-.1,MAST_BASE+.35,STEEL,DARK)
    for side in range(3):
        a=math.pi/2+side*math.tau/3
        for offset in (-.7,.7):
            x=5.7*math.cos(a)-offset*math.sin(a)
            y=5.7*math.sin(a)+offset*math.cos(a)
            cylinder('mast anchor bolt',(x,y,MAST_BASE+.35),(x,y,MAST_BASE+.7),.2,
                     STEEL,ALLOY,6,True)
    for bay in range(12):
        z0=MAST_BASE+bay*12.5;z1=z0+12.5
        r0=6.3-bay*4.3/12;r1=6.3-(bay+1)*4.3/12
        colour=RED if bay%2==0 else ALLOY
        for side in range(3):
            a=math.pi/2+side*math.tau/3;b=a+math.tau/3
            p=Vector((r0*math.cos(a),r0*math.sin(a),z0))
            q=Vector((r1*math.cos(a),r1*math.sin(a),z1))
            t=Vector((r0*math.cos(b),r0*math.sin(b),z0))
            end=Vector((r1*math.cos(b),r1*math.sin(b),z1))
            cylinder('mast main chord',p,q,.42,PAINT,colour,6)
            beam('mast transverse',p,t,.29,.29,PAINT,colour)
            beam('mast diagonal',p,end,.24,.24,PAINT,colour)
            beam('mast secondary diagonal',t,q,.18,.18,PAINT,colour,True)
            if bay in (2,5,8,10):
                mid=p.lerp(q,.5);normal=Vector((math.cos(a),math.sin(a),0))
                beam('transmitter bracket',mid,mid+normal*2,.25,.25,STEEL,DARK,True)
                obj=box('broadcast panel',mid+normal*2,(1.2,.8,6.3),PAINT,ALLOY)
                obj.rotation_euler.z=a
        if bay in (0,4,8):
            band('mast maintenance platform',r0+1,z0+.4,.65,STEEL,DARK)
    # Axial cable/ladder spine and a tapered, banded top whip.
    cylinder('mast cable trunk',(0,0,MAST_BASE),(0,0,MAST_BASE+150),.6,STEEL,DARK,8)
    for section in range(9):
        z0=MAST_BASE+150+section*6
        cylinder('upper antenna whip',(0,0,z0),(0,0,z0+6),1.25-section*.11,
                 PAINT,ALLOY if section%2 else RED,8)
    for x in (-.65,.65):
        beam('mast service ladder rail',(x,-1.2,MAST_BASE),(x,-1.2,MAST_BASE+149),
             .14,.14,STEEL,ALLOY,True)
    for i in range(166):
        z=MAST_BASE+i*.9
        beam('mast service ladder rung',(-.65,-1.2,z),(.65,-1.2,z),.12,.12,STEEL,ALLOY,True)
    # Aviation lamps remain emissive in both LODs and never use building tint.
    for z in (MAST_BASE+50,MAST_BASE+100):
        radius=6.3-(z-MAST_BASE)*4.3/150+1.1
        for side in range(3):
            a=math.pi/2+side*math.tau/3
            x,y=radius*math.cos(a),radius*math.sin(a)
            beam('beacon bracket',(x*.75,y*.75,z),(x,y,z),.3,.3,STEEL,DARK)
            cylinder('beacon housing',(x,y,z),(x,y,z+.5),.72,STEEL,DARK,8)
            emissive(cylinder('red aviation beacon',(x,y,z+.5),(x,y,z+1.5),.6,PAINT,RED,8),RED_LIGHT)
    emissive(cylinder('tip aviation beacon',(0,0,TOP-1.2),(0,0,TOP-.4),.7,PAINT,RED,8),RED_LIGHT)


def build():
    shared.fresh(SCENE)
    tripod();shaft();entrance_pod();observation_head();antenna()
    scene=bpy.context.scene
    scene.unit_settings.system='NONE'
    scene['asset_id']='buildings/authored/tower'
    scene['height_metres']=204.65;scene['metres_to_model_units']=3
    scene['concrete_metres']=136.65;scene['antenna_metres']=68;scene['viewpoint_metres']=122
    scene['hex_width']=83.125;scene['hex_height']=72;scene['level_height']=18
    scene['reference']='User supplied Avala Tower photographs; height breakdown136.65+68m'
    for obj in shared.volumes:obj.hide_set(True)
    bpy.context.view_layer.update()
    for obj in shared.objects:
        shared.project_uvs(obj)
        if obj['board_material']==CONCRETE:
            rng=random.Random(obj.name)
            offset=Vector((rng.uniform(0,40),rng.uniform(0,40)))
            # The family's concrete at its scale, with per-pour phase shifts.
            for uv in obj.data.uv_layers.active.data:uv.uv=uv.uv+offset
    return audit()


def audit():
    import bmesh
    errors=[]
    for obj in shared.objects+shared.volumes:
        bm=bmesh.new();bm.from_mesh(obj.data)
        if any(not e.is_manifold for e in bm.edges):errors.append([obj.name,'nonmanifold'])
        if bm.calc_volume(signed=True)<=0:errors.append([obj.name,'nonpositive volume'])
        bm.free()
    points=[o.matrix_world@v.co for o in shared.objects for v in o.data.vertices]
    bounds=[[round(min(v[i] for v in points),4),round(max(v[i] for v in points),4)] for i in range(3)]
    return {'objects':len(shared.objects),'helpers':len(shared.volumes),'bounds':bounds,'mesh_errors':errors}


def _convex_planes(points, triangles, epsilon):
    """Only accept an actual convex solid, never the convex hull of a hollow wall."""
    vertices=points[np.asarray(triangles)]
    normals=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
    lengths=np.linalg.norm(normals,axis=1);valid=lengths>epsilon*epsilon
    normals=normals[valid]/lengths[valid,None]
    offsets=np.sum(normals*vertices[valid,0],axis=1)
    planes=np.unique(np.round(np.column_stack((normals,offsets)),8),axis=0)
    if len(planes)>=4 and np.max(points@planes[:,:3].T-planes[:,3])<epsilon:
        return planes
    return None


def _wall_cells(obj, points):
    """Recognize this tower's six-corner hollow lofts and split their walls into solid cells.

    Validate the original outer and inner face topology before using the vertex layout.
    The hollow centre is never an occluder, including under the suspended entrance pod.
    """
    n=6;count=len(points)//(2*n);offset=count*n
    if count<2 or len(points)!=count*12:return []
    faces={tuple(face.vertices) for face in obj.data.polygons}
    for k in range(count-1):
        for i in range(n):
            j=(i+1)%n
            if ((k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i) not in faces or
                (offset+k*n+j,offset+k*n+i,offset+(k+1)*n+i,offset+(k+1)*n+j) not in faces):
                return []
    cells=[]
    for k in range(count-1):
        for i in range(n):
            j=(i+1)%n;indices=[k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i]
            cells.append(points[indices+[v+offset for v in indices]])
    return cells


def _hidden_faces(items):
    """Cull only coincident internal caps and complete faces buried in another opaque solid.

    Nothing is moved, decimated or dropped for being small. Work separately per LOD so
    LOD0 detail cannot incorrectly conceal geometry that must remain visible in LOD1.
    The tolerance covers float32 transforms at the mast tip (less than 0.04mm at scale).
    """
    epsilon=1e-4;records=[];solids=[];matches=defaultdict(list)
    opaque={key:not shared.read_material(shared.TEXTURES/(key+'.tres'),shared.TEXTURES)['transparent']
            for key in {obj['board_material'] for obj in items}}
    cell_triangles=[(0,1,2),(0,2,3),(7,6,5),(7,5,4),(3,2,6),(3,6,7),
                    (4,5,1),(4,1,0),(0,3,7),(0,7,4),(1,5,6),(1,6,2)]
    for obj in items:
        data=obj.data;data.calc_loop_triangles()
        matrix=np.asarray(obj.matrix_world,dtype=float)
        points=np.asarray([v.co[:] for v in data.vertices])@matrix[:3,:3].T+matrix[:3,3]
        index=len(records);faces=[]
        normal_matrix=np.linalg.inv(matrix[:3,:3]).T
        for face in data.polygons:
            p=points[list(face.vertices)];normal=normal_matrix@np.asarray(face.normal)
            normal/=np.linalg.norm(normal);faces.append((p,normal))
            key=tuple(sorted(tuple(round(float(c),3) for c in point) for point in p))
            if opaque[obj['board_material']]:matches[key].append((index,face.index,normal))
        records.append((obj,faces))
        # All current tower finishes are opaque. Refuse to use any future glass/cutout
        # finish as an occluder, instead of assuming its texture's alpha is solid.
        if not opaque[obj['board_material']]:continue
        planes=_convex_planes(points,[t.vertices[:] for t in data.loop_triangles],epsilon)
        cells=[points] if planes is not None else _wall_cells(obj,points)
        for cell in cells:
            cell_planes=planes if planes is not None else _convex_planes(cell,cell_triangles,epsilon)
            if cell_planes is not None:
                solids.append((index,cell.min(axis=0),cell.max(axis=0),cell_planes))
    removed=defaultdict(set)
    for group in matches.values():
        for i,fi,ni in group:
            for j,fj,nj in group:
                if i==j or np.dot(ni,nj)>-.99999:continue
                p,q=records[i][1][fi][0],records[j][1][fj][0]
                if np.max(np.min(np.linalg.norm(p[:,None,:]-q[None,:,:],axis=2),axis=1))<epsilon:
                    removed[i].add(fi)
    if not solids:return {records[i][0]:faces for i,faces in removed.items() if faces}
    lows=np.asarray([s[1] for s in solids]);highs=np.asarray([s[2] for s in solids])
    for i,(_,faces) in enumerate(records):
        for fi,(p,normal) in enumerate(faces):
            if fi in removed[i]:continue
            # The outward side must also be strictly inside the occluder. This keeps
            # coincident outward-facing surfaces from being deleted on both objects.
            shifted=p+normal*epsilon*4;lo=shifted.min(axis=0);hi=shifted.max(axis=0)
            candidates=np.flatnonzero(np.all(lows<=lo+epsilon,axis=1)&np.all(highs>=hi-epsilon,axis=1))
            for candidate in candidates:
                j,_,_,planes=solids[candidate]
                if i==j:continue
                if (np.max(p@planes[:,:3].T-planes[:,3])<=epsilon and
                    np.max(shifted@planes[:,:3].T-planes[:,3]) < -epsilon):
                    removed[i].add(fi);break
    return {records[i][0]:faces for i,faces in removed.items() if faces}


@contextmanager
def optimized_geometry(low=False):
    """Temporary export/render meshes; keep the editable closed solids and helpers intact."""
    items=[o for o in shared.objects if not low or not o.get('detail')]
    hidden=_hidden_faces(items);swaps=[];visibility=[(o,o.hide_render) for o in shared.objects]
    visible=[]
    try:
        for obj in shared.objects:obj.hide_render=low and bool(obj.get('detail'))
        for obj in items:
            removed=hidden.get(obj,set());source=obj.data
            if len(removed)==len(source.polygons):
                obj.hide_render=True;continue
            visible.append(obj)
            if not removed:continue
            faces=[f for f in source.polygons if f.index not in removed]
            data=bpy.data.meshes.new(source.name+' optimized')
            swaps.append((obj,source,data))
            data.from_pydata([v.co[:] for v in source.vertices],[],[tuple(f.vertices) for f in faces])
            for material in source.materials:data.materials.append(material)
            loops=[li for face in faces for li in face.loop_indices]
            for old,new in zip(faces,data.polygons):
                new.use_smooth=old.use_smooth;new.material_index=old.material_index
            for layer in source.uv_layers:
                target=data.uv_layers.new(name=layer.name)
                for new,old in zip(target.data,loops):new.uv=layer.data[old].uv
            # Preserve the original shading when a concealed neighbour of a smooth
            # cylinder face is removed. No recomputation across newly exposed edges.
            data.normals_split_custom_set([source.corner_normals[li].vector[:] for li in loops])
            data.update();obj.data=data
        bpy.context.view_layer.update()
        yield visible
    finally:
        for obj,source,data in swaps:
            obj.data=source;bpy.data.meshes.remove(data)
        for obj,hidden_state in visibility:obj.hide_render=hidden_state
        bpy.context.view_layer.update()


def plain_mast():
    """The lattice mast on the far levels, where each member is thinner than a pixel: solid, in the same bays, about as wide as it looks."""
    def ring(radius):
        return [(radius*math.cos(math.pi/2+i*math.tau/3),radius*math.sin(math.pi/2+i*math.tau/3)) for i in range(3)]
    for bay in range(12):
        z=MAST_BASE+bay*12.5
        loft('plain mast',[(z,ring(.5*(6.3-bay*4.3/12))),(z+12.5,ring(.5*(6.3-(bay+1)*4.3/12)))],PAINT,RED if bay%2==0 else ALLOY)
    loft('plain whip',[(MAST_BASE+150,ring(1.25)),(TOP,ring(.35))],PAINT,ALLOY)


def lattice(obj):
    family=obj.name.split('.')[0]
    return family=='upper antenna whip' or (family.startswith('mast ') and family!='mast maintenance platform')


def export():
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    bpy.context.view_layer.update()
    levels={}
    plain=shared.temporary(plain_mast)
    for lod in (0,1,2):
        with optimized_geometry(low=bool(lod)) as items:
            if lod:
                levels[lod]=shared.together(shared.export_model([o for o in items if not lattice(o)],NAME+'-lod'+str(lod),level=lod),
                                            shared.export_model(plain,NAME+'-lod'+str(lod)+'-mast'))
            else:
                levels[lod]=shared.export_model(items,NAME+'-lod0')
    shared.discard(plain)
    helpers=shared.export_model(shared.volumes,NAME,helper=True)
    stats={lod:{'vertices':sum(len(m['vertices'])//12 for m in model['meshes']),
                'triangles':sum(len(p['indices'])//3 for m in model['meshes'] for p in m['parts'])}
           for lod,model in levels.items()}
    assert all(s['vertices']<65535 for s in stats.values()),stats
    write_glb(shared.DEST/(NAME+'.glb'),levels=levels,groups={'building_volumes':helpers})
    doc,_=glb_container.read_glb(shared.DEST/(NAME+'.glb'))
    glb_container.validate(doc,shared.DEST/(NAME+'.glb'),shared.DATA/'models')
    bpy.data.libraries.write(str(shared.SOURCE/(NAME+'.blend')),{bpy.context.scene},fake_user=True)
    return stats


def studio(view='full'):
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    scene=bpy.context.scene
    collection=next((c for c in scene.collection.children if c.get('tower_review_studio')),None)
    if not collection:
        collection=bpy.data.collections.new('Tower review studio');scene.collection.children.link(collection)
        collection['tower_review_studio']=True
        camera=bpy.data.objects.new('Tower review camera',bpy.data.cameras.new('Tower review camera'))
        collection.objects.link(camera);scene.camera=camera
        for loc,power,size in [((250,-350,650),1800000,250),((-350,-80,300),950000,260),((100,350,550),1400000,200)]:
            light=bpy.data.objects.new('Tower softbox',bpy.data.lights.new('Tower softbox','AREA'))
            collection.objects.link(light);light.location=loc;light.data.energy=power;light.data.shape='DISK';light.data.size=size
            light.rotation_euler=(Vector((0,0,260))-light.location).to_track_quat('-Z','Y').to_euler()
        data=bpy.data.meshes.new('Tower review ground');data.from_pydata([(-900,-900,-.1),(900,-900,-.1),(900,900,-.1),(-900,900,-.1)],[],[(0,1,2,3)])
        ground=bpy.data.objects.new('Tower review ground',data);collection.objects.link(ground)
        ground.data.materials.append(shared.material(shared.FLAT,(.20,.23,.25)))
    views={'full':((380,-680,360),(0,-15,300),690,(800,1400)),
           'night':((380,-680,360),(0,-15,300),690,(800,1400)),
           'ground':((200,-340,5.4),(0,0,225),690,(900,1500)),
           'base':((150,-240,115),(0,-30,63),195,(1200,1000)),
           'head':((140,-230,405),(0,0,361),125,(1100,1100)),
           'front':((0,-800,310),(0,0,300),660,(800,1400)),
           'top':((0,0,800),(0,0,0),240,(1000,1000))}
    night=view=='night' or view.endswith('-night')
    location,target,scale,res=views[view[:-6] if view.endswith('-night') else view]
    camera=scene.camera;camera.location=location
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=scale
    if view=='ground':
        camera.data.type='PERSP';camera.data.lens=24
        camera.data.sensor_fit='VERTICAL';camera.data.sensor_height=36
    camera.data.clip_end=3000
    scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
    scene.render.resolution_x,scene.render.resolution_y=res;scene.render.resolution_percentage=100
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.36,.41,.47,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.65
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.65
    for obj in collection.objects:
        if obj.type=='LIGHT':
            if '_tower_day_energy' not in obj:obj['_tower_day_energy']=obj.data.energy
            obj.data.energy=obj['_tower_day_energy']*(.025 if night else 1)
    for obj in shared.objects:
        if obj.get('building_night_emission'):
            shader=next(n for n in obj.data.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
            shader.inputs['Emission Strength'].default_value=1 if night else 0
    if night:
        scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.055,.08,.14,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value=.04
        scene.view_settings.exposure=1.2
    scene.render.image_settings.file_format='PNG';scene.render.filepath=str(shared.SOURCE/(NAME+'-'+view+'.png'))
    return scene.render.filepath
