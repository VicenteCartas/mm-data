"""Reference-scale HPG headquarters. Run build() through Blender MCP.

Z up, 18 units per level, 83.125 x 72 per hex. Only the closed architectural
envelopes belong to building_volumes; the reflector and machinery are decoration.
The original Blender scene is preserved. Rebuilds replace only this script's scene.
"""
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import authored_examples as shared
from glb_geometry import linear
from lunar_equipment import generator_ring

NAME = 'hpg-headquarters'
SCENE = 'HPG reference facility'
# Shared Material Maker finishes. Pigments are display-space sRGB, matching the
# shared GLB writer, and never above 1.
# Colours follow the battlemat: warm mottled dish, pale concrete decks, darker hall
# roof, slate fins and machinery, blue cells. Large faces avoid the fully metallic
# finishes, whose low reflectance reads near black under the board's light.
DISH = 'structures/buildings/fortress-concrete'
CONCRETE = shared.CONCRETE
MACHINE = 'structures/common/painted-steel'
SATIN = shared.STEEL
STEEL = 'structures/common/steel'
GRILLE = 'structures/common/grille'
FLAT = shared.FLAT
CONCRETE_REPEAT = 54
# On CONCRETE.
CLADDING = (.847, .847, .831)
ARMOUR = (.742, .742, .719)
BAND = (.662, .662, .63)
RECESS = (.404, .404, .388)
ROOF = (.565, .565, .533)
MID_DECK = (.678, .678, .646)
PALE_DECK = (.847, .847, .847)
BANK_FLOOR = (.404, .404, .388)
# On DISH.
PLATE = (1, 1, 1)
PLATE_ALT = (.93, .93, .92)
PLATE_FAR = (.86, .86, .85)
PLATE_LOW = (.72, .72, .70)
BACKING = (.70, .70, .68)
# On MACHINE.
SLATE = (.50, .51, .52)
SLATE_DARK = (.36, .37, .38)
HOUSING = (.23, .24, .25)
# On STEEL, whose atlas already holds its dark alloy colour: these only tint it.
DARK = (.564111, .607735, .621461)
TRIM = (.697036, .763647, .784305)
ALLOY = (1, 1, 1)
STEEL_CYAN = (.218202, .720091, .961738)
# On SATIN.
SATIN_ALLOY = (.626210, .646077, .634253)
# On FLAT.
CYAN = (.128354, .423583, .565728)
# Emission of the generators' core, display-space RGB.
REACTOR_BLUE = (.08,.50,.90)
# The large bank's deck: its volume is two levels, so the game draws a floor at z 18, which a lower deck would lie under.
BANK_TOP = 18.3
BANK_OUTLINE = [(100,-60),(215,-60),(220,-80),(220,-218),(202,-236),(150,-236),(146,-250),(112,-250),(98,-236),(98,-80)]
# Centres along Y, read off the battlemat's crop.
LARGE_GENERATORS = (-113,-147,-181)
SMALL_GENERATORS = (-107,-125,-143,-161)
DISH_CENTER = Vector((-110,-10,342))
DISH_NORMAL = Vector((-.82,-.10,.565)).normalized()
DISH_RIGHT = Vector((DISH_NORMAL.y,-DISH_NORMAL.x,0)).normalized()
# Spins the reflector pattern about its axis, placing the short fins and boom nodes
# near the battlemat's and keeping all four booms apart when seen from above.
DISH_SPIN = math.radians(15)
APEX_Z = 370
BOOM_WIDTH = 19
BOOM_DEPTH = 11
BOOM_BAY = 24
# Every envelope as (name, base outline, roof outline, height, wall pigment, roof pigment), for LOD2's plain masses.
MASSES = []


def mesh(name, verts, faces, key=CONCRETE, colour=CLADDING, detail=False, helper=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return shared.finish(obj, key, colour, detail, helper)


def prism(name, outline, bottom, top, key=CONCRETE, colour=CLADDING, detail=False, helper=False, caps=True):
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(outline,outline[1:]+outline[:1])) < 0:
        outline = list(reversed(outline))
    n = len(outline)
    v = [(x,y,z) for z in (bottom,top) for x,y in outline]
    f = [tuple(reversed(range(n))),tuple(range(n,n*2))] if caps else []
    f += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh(name,v,f,key,colour,detail,helper)


def box(name, pos, size, key=CONCRETE, colour=CLADDING, detail=False):
    x,y,z=pos; w,d,h=size
    o=prism(name,[(x-w/2,y-d/2),(x+w/2,y-d/2),(x+w/2,y+d/2),(x-w/2,y+d/2)],z-h/2,z+h/2,key,colour,detail)
    return o


def beam(name,a,b,width,depth=None,key=STEEL,colour=TRIM,detail=False):
    a,b=Vector(a),Vector(b)
    obj=box(name,(0,0,0),(width,depth or width,(b-a).length),key,colour,detail=detail)
    obj.matrix_world=Matrix.Translation((a+b)/2) @ (b-a).to_track_quat('Z','Y').to_matrix().to_4x4()
    return obj


def cylinder(name,a,b,radius,key=STEEL,colour=ALLOY,sides=16,detail=False,caps=True):
    a,b=Vector(a),Vector(b)
    outline=[(radius*math.cos(i*math.tau/sides),radius*math.sin(i*math.tau/sides)) for i in range(sides)]
    obj=prism(name,outline,-(b-a).length/2,(b-a).length/2,key,colour,detail,caps=caps)
    obj['uv_projection']='cylinder'
    for face in obj.data.polygons:
        face.use_smooth=len(face.vertices)==4
    obj.matrix_world=Matrix.Translation((a+b)/2) @ (b-a).to_track_quat('Z','Y').to_matrix().to_4x4()
    return obj


def outline_box(x0,x1,y0,y1,ch=8):
    return [(x0+ch,y0),(x1-ch,y0),(x1,y0+ch),(x1,y1-ch),(x1-ch,y1),(x0+ch,y1),(x0,y1-ch),(x0,y0+ch)]


def inset_outline(poly,distance,closed=True):
    """Parallel left-hand contour, with mitered joins and square ends for open paths."""
    result=[]
    for i,(before,point,after) in enumerate(zip(poly[-1:]+poly[:-1],poly,poly[1:]+poly[:1])):
        p=Vector(point);a=(p-Vector(before)).normalized();b=(Vector(after)-p).normalized()
        if not closed and i==0:a=b
        if not closed and i==len(poly)-1:b=a
        n1=Vector((-a.y,a.x));n2=Vector((-b.y,b.x));bisector=n1+n2
        result.append(tuple(p+bisector*(distance/max(.001,bisector.dot(n1)))))
    return result


def outline_band(name,path,z,height,width,offset=0,key=CONCRETE,colour=CLADDING,closed=True,profile=None):
    """One closed solid with shared corner vertices, including every miter joint."""
    if closed and sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(path,path[1:]+path[:1]))<0:path=list(reversed(path))
    outer=inset_outline(path,-offset-width/2,closed)
    inner=inset_outline(path,-offset+width/2,closed)
    n=len(path)
    verts=[(x,y,zz+(profile(x,y) if profile else 0))
           for contour,zz in ((outer,z-height/2),(inner,z-height/2),(outer,z+height/2),(inner,z+height/2)) for x,y in contour]
    faces=[]
    for i in range(n if closed else n-1):
        j=(i+1)%n
        faces += [(i,j,2*n+j,2*n+i),(n+j,n+i,3*n+i,3*n+j),
                  (2*n+i,2*n+j,3*n+j,3*n+i),(j,i,n+i,n+j)]
    if not closed:faces += [(0,2*n,3*n,n),(n-1,2*n-1,4*n-1,3*n-1)]
    return mesh(name,verts,faces,key,colour)


def border_courses(path,height,closed=False):
    for z,width,depth in ((3,4,5),(height-3,4,4),(height+1,3,4)):
        outline_band('layered border course',path,z,depth,width,1.2,closed=closed)


def envelope(name,poly,height,colour=CLADDING,parapet=True,volume_height=None,roof=ROOF):
    """Hollow walls and a thin roof, plus one watertight gameplay helper."""
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))<0:poly=list(reversed(poly))
    inner=inset_outline(poly,3)
    for i,(a,b) in enumerate(zip(poly,poly[1:]+poly[:1])):
        prism(name+' wall', [a,b,inner[(i+1)%len(poly)],inner[i]],0,height,CONCRETE,colour)['building_paint']=True
    prism(name+' roof',poly,height-2,height,CONCRETE,roof)
    prism('volume '+name,poly,0,height if volume_height is None else volume_height,FLAT,(.25,.8,.6),helper=True)
    if parapet:
        outline_band(name+' parapet',poly,height+2,4,4,colour=BAND)
    MASSES.append((name,poly,poly,height,colour,roof))


def tapered_envelope(name,base,roof,height):
    """Hollow sloped walls with matching closed gameplay geometry and flat roof."""
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(base,base[1:]+base[:1]))<0:
        base=list(reversed(base));roof=list(reversed(roof))
    MASSES.append((name,base,roof,height,CLADDING,PALE_DECK))
    n=len(base);inner_base=inset_outline(base,3);inner_roof=inset_outline(roof,3)
    vertices=[(*p,z) for contour,z in ((base,0),(roof,height),(inner_base,0),(inner_roof,height)) for p in contour]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,n+j,n+i),(2*n+j,2*n+i,3*n+i,3*n+j),
                  (n+i,n+j,3*n+j,3*n+i),(j,i,2*n+i,2*n+j)]
    mesh(name+' sloped walls',vertices,faces,CONCRETE,CLADDING)['building_paint']=True
    prism(name+' flat roof',roof,height-2,height,CONCRETE,PALE_DECK)
    helper_faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    helper_faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    obj=mesh('volume '+name,[(*p,z) for contour,z in ((base,0),(roof,height)) for p in contour],helper_faces,FLAT,(.25,.8,.6),helper=True)
    obj['reference_tapered']=True
    for z in (3,8,height-4,height+1):
        contour=[tuple(Vector(a).lerp(Vector(b),min(z,height)/height)) for a,b in zip(base,roof)]
        outline_band('operations stepped molding',contour,z,3,3,.5)
    # Real relief follows the slope; panels do not float on vertical proxy walls.
    for i in range(n):
        j=(i+1)%n;a,b=Vector(base[i]),Vector(base[j]);c,d=Vector(roof[i]),Vector(roof[j])
        direction=(b-a).normalized();outward=Vector((direction.y,-direction.x))
        def at(t,z,offset=0):
            p=(a+(b-a)*t).lerp(c+(d-c)*t,z/height)+outward*offset
            return (p.x,p.y,z)
        count=max(1,round((b-a).length/23))
        for k in range(count):
            t0=(k+.16)/count;t1=(k+.84)/count
            mesh('sloped recessed cassette',[at(t0,11,.5),at(t1,11,.5),at(t1,27,.5),at(t0,27,.5)],[(0,1,2,3)],CONCRETE,RECESS)
            mesh('sloped inset panel',[at(t0+.07/count,13,1),at(t1-.07/count,13,1),at(t1-.07/count,25,1),at(t0+.07/count,25,1)],[(0,1,2,3)],CONCRETE,ARMOUR)['building_paint']=True
            beam('sloped wall rib',at(k/count,4,.6),at(k/count,32,.6),3,3,CONCRETE,CLADDING)
    outline_band('operations roof inset seam',roof,height+.2,1,1.5,-6,colour=RECESS)


def ring(name,r0,r1,z,height,key=STEEL,colour=TRIM,sides=96,detail=False,curve=False):
    # Fine enough to keep the sub-unit circular silhouette error, with room in
    # the rigid vertex budget for distinct UVs on the machined edge faces.
    sides = 56 if sides >= 80 else max(12, 4 * round(sides * .625 / 4))
    verts=[]
    for radius,offset in ((r0,0),(r1,0),(r1,height),(r0,height)):
        for i in range(sides):
            a=math.tau*i/sides
            verts.append((radius*math.cos(a),radius*math.sin(a),z+offset+(dish_z(radius) if curve else 0)))
    faces=[]
    for j in range(4):
        for i in range(sides):
            k=(i+1)%sides
            faces.append((j*sides+i,j*sides+k,((j+1)%4)*sides+k,((j+1)%4)*sides+i))
    obj=mesh(name,verts,faces,key,colour,detail)
    obj['uv_projection']='planar'
    for face in obj.data.polygons:face.use_smooth=True
    return obj


def fan(x,y,z,r=9):
    cylinder('fan well',(x,y,z),(x,y,z+1),r,MACHINE,SLATE_DARK,12)
    for k in range(5):
        a=k*math.tau/5
        beam('fan blade',(x+2*math.cos(a),y+2*math.sin(a),z+1.2),(x+(r-1)*math.cos(a+.35),y+(r-1)*math.sin(a+.35),z+1.2),2,1,STEEL,ALLOY,True)
    cylinder('fan hub',(x,y,z+1),(x,y,z+2),2,STEEL,TRIM,8,True)


def vent(x,y,z,w,h,side=1):
    box('recessed louvre',(x,y,z),(w,2,h),GRILLE,(.55,.59,.60))
    for dz in range(0,int(h),4):
        box('louvre blades',(x,y+side*1.3,z-h/2+dz+1),(w-3,1.2,1.4),STEEL,ALLOY,detail=True)


def facade(a,b,height):
    """Layered inset armour and grille piers along an oblique end wall."""
    a,b=Vector((*a,0)),Vector((*b,0));axis=(b-a).normalized()
    normal=Vector((axis.y,-axis.x,0))
    count=max(1,round((b-a).length/30))
    for i in range(count):
        c=a+(b-a)*(i+.5)/count+normal*1.15
        width=(b-a).length/count-6
        for z,w,h,offset,key,col in [(height*.48,width,height*.66,0,CONCRETE,RECESS),(height*.49,width-5,height*.55,1.4,CONCRETE,ARMOUR)]:
            p=c+normal*offset
            o=box('chamfered end armour',(0,0,0),(w,2.5,h),key,col)
            o['building_paint']=col==ARMOUR
            matrix=Matrix(((axis.x,-normal.x,0),(axis.y,-normal.y,0),(0,0,1))).to_4x4()
            o.matrix_world=Matrix.Translation(Vector((p.x,p.y,z))) @ matrix
        if i%2==0:
            for shift in (-6,0,6):
                p=c+axis*shift+normal*3.4
                beam('endwall grille flute',(p.x,p.y,14),(p.x,p.y,height-14),2,2,STEEL,ALLOY,True)


def reference_hex(column, joined_row):
    """Source map1717 is the anchor. Lower maprow01 is joinedrow18."""
    return ((column-17)*62.34375, -(joined_row-17)*72-((column-1)&1)*36)


def edge_details(a,b,height,teeth=True):
    """Layered parapet, recessed skirt and pilasters on one exposed edge."""
    a,b=Vector((*a,0)),Vector((*b,0));length=(b-a).length
    if length<5:return
    axis=(b-a)/length;normal=Vector((axis.y,-axis.x,0))
    rotation=Matrix(((axis.x,-normal.x,0),(axis.y,-normal.y,0),(0,0,1))).to_4x4()
    def panel(name,p,z,size,key,colour,detail=False):
        o=box(name,(0,0,0),size,key,colour,detail)
        o['building_paint']=colour==ARMOUR
        o.matrix_world=Matrix.Translation(p+Vector((0,0,z))) @ rotation
    count=max(1,round(length/21))
    for i in range(count):
        center=a+(b-a)*(i+.5)/count
        panel('border recessed cassette',center+normal*.9,height*.5,(length/count-6,2,max(5,height-10)),CONCRETE,RECESS)
        panel('border inset armour',center+normal*2.1,height*.5,(length/count-10,2,max(3,height-14)),CONCRETE,ARMOUR)
        p=a+(b-a)*i/count
        panel('border buttress',p+normal*3,height*.5,(4.5,7,height+1),CONCRETE,CLADDING)
        if teeth:
            panel('parapet merlon',p+normal*2,height+3.5,(8,7,7),CONCRETE,CLADDING)
        if i%2==0:
            panel('border inset vent grille',center+normal*3.4,height*.5,(8,1,max(3,height-15)),GRILLE,(.55,.59,.60))


def main_wing():
    axis=0
    x7,x9,x16=(reference_hex(c,17)[0] for c in (7,9,16))
    poly=[(x7,-36),(x9,-108),(x16,-108),(0,-72),(0,72),(x16,108),(x9,108),(x7,36)]
    envelope('command hall',poly,54)
    facade(poly[0],poly[1],54);facade(poly[-2],poly[-1],54);facade(poly[-1],poly[0],54)
    # Position source-map landmarks FIRST. Each opposite pair shares a hex column;
    # their two-column spacing and five-row separation are exact, not eyeballed.
    for side,row in ((1,14),(-1,19)):
        edge=axis+side*108;gallery_edge=axis+side*168
        # The 0815 / 0801 / 0802 terraces extend beside the chamfered nose.
        # Their footprint was absent when the gallery was a strip starting at09.
        # The southern gallery meets the service court at exactly X=-57: no
        # coplanar overlap and no open slot between the two level-one roofs.
        front=-577.7632 if side==1 else -575.5962
        shoulder_x=front-15
        shoulder_y=36+(shoulder_x-x7)*72/(x9-x7)
        end=0 if side==1 else -57
        apron=[(shoulder_x,side*shoulder_y),(x9,edge),(end,edge),(end,gallery_edge),
               (front+8,gallery_edge),(front,side*160),(front,side*80)]
        if side==-1:
            apron=[(shoulder_x,-shoulder_y),(x9,-108),(end,-108),(end,-168),
                   (-480.9137,-168),(-480.9137,-180),(-570.262,-180),(front,-173.3333),(front,-96.6667)]
            apron.reverse()
        envelope('north gallery' if side==1 else 'south gallery',apron,18,ARMOUR,False,roof=MID_DECK)
        # Trace the exposed outer border, leaving the wall against the hall open.
        exposed=[(end,gallery_edge),(front+8,gallery_edge),(front,side*160),
                 (front,side*80),(shoulder_x,side*shoulder_y)]
        if side==-1:
            exposed=[(shoulder_x,-shoulder_y),(front,-96.6667),(front,-173.3333),
                     (-570.262,-180),(-480.9137,-180),(-480.9137,-168),(end,-168)]
        border_courses(exposed,18)
        for a,b in zip(exposed,exposed[1:]):edge_details(a,b,18)
        for column in (10,12,14):
            x,cap_y=reference_hex(column,row)
            arm=[(x-30,edge),(x+30,edge)]+[(x+36*math.cos(-math.pi/6+k*math.pi/9),cap_y+side*36*math.sin(-math.pi/6+k*math.pi/9)) for k in range(13)]
            envelope('hex %02d%02d service arm'%(column,row if row<=17 else row-17),arm,36,CLADDING)
            cylinder('arm terminal',(x,cap_y,36),(x,cap_y,39),28,STEEL,TRIM,24)
            fan(x,cap_y,39,18)
            for zz in (6,28):
                outline_band('arm layered fascia',arm,zz,3,3,colour=BAND)
            for k in range(13):
                angle=-math.pi/6+k*math.pi/9
                cx=x+36.5*math.cos(angle);cy=cap_y+side*36.5*math.sin(angle)
                beam('rounded bay vertical rib',(cx,cy,5),(cx,cy,31),2.5,3,CONCRETE,CLADDING,True)
            for r,z in ((29,37.5),(25,38.8)):
                o=ring('terminal concentric rim',r-1.5,r+1,z,1.5,STEEL,ALLOY,32)
                o.location=(x,cap_y,0)
            bridge_y=(edge+cap_y)/2
            box('arm bridge inset',(x,bridge_y,37),(39,47,2),CONCRETE,RECESS)
            for dx in (-12,0,12):
                box('bridge cables',(x+dx,bridge_y,38.4),(2.5,41,1),STEEL,ALLOY,detail=True)
            box('rooftop air handling',(x,edge-side*16,57.5),(43,20,7),MACHINE,SLATE)
            for dx in (-11,11): fan(x+dx,edge-side*16,61,7)
        # Bay centers sit in the intervening source columns11,13,15.
        for column in (11,13,15):
            x=reference_hex(column,17)[0]
            box('gallery bay shadow',(x,edge+side*2,30),(65,2,22),CONCRETE,RECESS)
            for dx in (-31,31): box('bay pilaster',(x+dx,edge+side*5,29),(5,8,25),CONCRETE,CLADDING)
            box('bay lintel',(x,edge+side*6,43),(69,9,5),CONCRETE,ARMOUR)
            for xx in (-20,0,20): box('bay service door',(x+xx,edge+side*4,26),(13,1,16),STEEL,TRIM)
        for column in range(9,17):
            x=reference_hex(column,17)[0]
            for dx in (0,31.171875):
                xx=x+dx
                if xx>x16: continue
                box('fortified vertical pier',(xx,edge+side*2,32),(8,8,41),CONCRETE,CLADDING)
                box('battlement',(xx,edge+side*2,57),(12,8,9),CONCRETE,CLADDING)
        for z in (20,44):
            box('continuous string course',((x9+x16)/2,edge+side*2,z),(x16-x9,6,4),CONCRETE,BAND)
    # The miniature's hex markings locate tabletop pieces; the game model has
    # a continuous roof supplied by the command-hall envelope above.
    for x in (x7+22,x7+38,x7+54):
        box('front air intake',(x,axis,56),(8,30,4),MACHINE,SLATE_DARK)
        for yy in (-9,0,9): box('front louvre',(x,axis+yy,58),(8,2,1),STEEL,ALLOY,detail=True)
    # Broad shoulders and the flat front have the same layered fortified rim.
    nose=[poly[-2],poly[-1],poly[0],poly[1]]
    border_courses(nose,54)
    for z in (8,47):outline_band('endwall cornice',nose,z,3,3,.8,closed=False)
    for a,b in ((poly[0],poly[1]),(poly[-2],poly[-1]),(poly[-1],poly[0])):
        edge_details(a,b,54)


def small_radar():
    """Hex 2116: tiled receiver with a driven azimuth/elevation cradle."""
    x,y=reference_hex(21,16)
    n=Vector((-.55,-.30,.78)).normalized();u=Vector((.30,-.55,0)).normalized();v=n.cross(u)
    center=Vector((x,y,58))
    frame=Matrix.Translation(center) @ Matrix(((u.x,v.x,n.x),(u.y,v.y,n.y),(u.z,v.z,n.z))).to_4x4()
    cylinder('secondary radar turntable',(x,y,18),(x,y,24),39,STEEL,TRIM,32)
    cylinder('secondary azimuth race',(x,y,24),(x,y,27),32,STEEL,DARK,24)
    cylinder('secondary radar pedestal',(x,y,27),(x,y,38),23,MACHINE,SLATE,12)
    for i in range(8):
        angle=i*math.tau/8
        cylinder('azimuth retaining bolt',(x+35*math.cos(angle),y+35*math.sin(angle),24),
                 (x+35*math.cos(angle),y+35*math.sin(angle),25.3),1.7,STEEL,ALLOY,6,True)
    for side in (-1,1):
        foot=Vector((x,y,28))+u*side*26
        pivot=center+u*side*46-n*6
        beam('secondary armoured yoke',foot,pivot,9,12,MACHINE,SLATE)
        cylinder('secondary elevation bearing',pivot-u*6,pivot+u*6,8,STEEL,TRIM,12)
        cylinder('secondary bearing cap',pivot+u*side*6,pivot+u*side*8,5.7,STEEL,ALLOY,12)
    rear=Vector((x,y,31))-Vector((n.x,n.y,0))*23
    actuator=frame @ Vector((0,20,-9))
    cylinder('elevation actuator body',rear,rear.lerp(actuator,.7),4.5,STEEL,DARK,10)
    cylinder('elevation actuator piston',rear.lerp(actuator,.58),actuator,2.6,SATIN,SATIN_ALLOY,10)
    start=len(shared.objects)
    # A shallow curved backing supports twelve separate receiver cartridges.
    verts=[];faces=[]
    for j in range(9):
        xx=-42+j*10.5
        for yy in (-33,33): verts.append((xx,yy,xx*xx/420))
    for j in range(8): faces.append((j*2,(j+1)*2,(j+1)*2+1,j*2+1))
    o=mesh('secondary radar backing',verts,faces,GRILLE,(.45,.49,.51))
    mod=o.modifiers.new('Receiver backing','SOLIDIFY');mod.thickness=5
    # Create the edge faces before UV projection; inherited front-face UVs
    # otherwise collapse the solidified rim to a line in exported normal maps.
    bpy.context.view_layer.update()
    evaluated=o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    closed=evaluated.to_mesh().copy();evaluated.to_mesh_clear()
    old=o.data;o.modifiers.clear();o.data=closed;bpy.data.meshes.remove(old)
    rim=[(-43+j*10.75,-34) for j in range(9)]+[(43-j*10.75,34) for j in range(9)]
    outline_band('secondary receiver continuous frame',rim,2,7,5,key=STEEL,colour=TRIM,profile=lambda x,y:x*x/420)
    for xx in (-43,43):
        for yy in (-30,30):
            cylinder('receiver captive fastener',(xx,yy,9),(xx,yy,10.5),2,STEEL,ALLOY,8,True)
    for xx in (-30,-10,10,30):
        for yy in (-21,0,21):
            cartridge=len(shared.objects)
            carrier=prism('receiver cartridge',outline_box(-9,9,-9,9,1.5),0,1.8,STEEL,TRIM,True)
            for face in carrier.data.polygons:face.use_smooth=False
            mesh('receiver ceramic face',[(-7.4,-7.4,1.81),(7.4,-7.4,1.81),(7.4,7.4,1.81),(-7.4,7.4,1.81)],[(0,1,2,3)],SATIN,SATIN_ALLOY,True)
            for slot in (-3.5,3.5):
                mesh('receiver etched waveguide',[(-6,slot-.55,1.82),(6,slot-.55,1.82),(6,slot+.55,1.82),(-6,slot+.55,1.82)],[(0,1,2,3)],STEEL,DARK,True)
            placement=Matrix.Translation(Vector((xx,yy,xx*xx/420-.45))) @ Matrix.Rotation(-math.atan(xx/210),4,'Y')
            bpy.context.view_layer.update()
            for obj in shared.objects[cartridge:]:obj.matrix_world=placement @ obj.matrix_world
    for yy in (-22,-11,0,11,22):
        beam('receiver rear cooling rib',(-36,yy,-5),(36,yy,-5),2,4,STEEL,TRIM,True)
    box('receiver processing pack',(0,0,-9),(29,24,7),MACHINE,SLATE)
    cylinder('receiver cable socket',(0,-14,-9),(0,-22,-9),4,STEEL,ALLOY,10,True)
    bpy.context.view_layer.update()
    for obj in shared.objects[start:]: obj.matrix_world=frame @ obj.matrix_world


def relay_head(x,y):
    """Hex 2315: armoured optical/subspace relay, with a recessed emitter and cooling stack."""
    for i in range(6):
        angle=(i*2+.5)*math.tau/12
        radial=Vector((math.cos(angle),math.sin(angle),0));tangent=Vector((-radial.y,radial.x,0))
        surface=Vector((x,y,0))+radial*26.4
        mesh('relay base vent recess',[surface+tangent*dx+Vector((0,0,z)) for dx,z in ((-7,10),(7,10),(7,29),(-7,29))],[(0,1,2,3)],STEEL,DARK,True)
        for z in (14,19,24):
            mesh('relay base vent blade',[surface+radial*.3+tangent*dx+Vector((0,0,zz)) for dx,zz in ((-6,z),(6,z),(6,z+1.2),(-6,z+1.2))],[(0,1,2,3)],STEEL,ALLOY,True)
    cylinder('relay bearing plinth',(x,y,36),(x,y,40),28,STEEL,TRIM,24)
    cylinder('relay drive gasket',(x,y,40),(x,y,42),23,STEEL,DARK,16)
    cylinder('relay azimuth motor',(x,y,42),(x,y,47),18,MACHINE,SLATE,12)
    n=Vector((-.66,-.20,.72)).normalized();u=Vector((.20,-.66,0)).normalized();v=n.cross(u)
    center=Vector((x,y,58))
    for side in (-1,1):
        pivot=center+u*side*18
        beam('relay mounting cheek',Vector((x,y,43))+u*side*13,pivot,7,9,MACHINE,SLATE)
        cylinder('relay trunnion',pivot-u*3,pivot+u*3,6,STEEL,ALLOY,12)
    start=len(shared.objects)
    head=box('relay angular shroud',(0,0,-2),(30,28,20),MACHINE,SLATE)
    chamfer=head.modifiers.new('Machined shroud corners','BEVEL');chamfer.width=3;chamfer.segments=1
    for face in head.data.polygons:face.use_smooth=False
    collar=ring('relay emitter armoured collar',10.5,16,7,5,STEEL,TRIM,16)
    lip=ring('relay recessed aperture lip',8.5,11.5,8,2.2,STEEL,ALLOY,16)
    # Machined annular faces must stay flat; smoothing across the thickness makes
    # a square-edged collar look like an inflated tyre.
    for obj in (collar,lip):
        for face in obj.data.polygons:
            if abs(face.normal.z)>.9:face.use_smooth=False
    cylinder('relay dark optical well',(0,0,7.4),(0,0,8.1),9.7,STEEL,DARK,16)
    cylinder('relay blue emitter',(0,0,8.2),(0,0,8.5),6.8,FLAT,CYAN,16)
    focus=ring('relay inner focus ring',3.2,4.1,8.7,.8,STEEL,ALLOY,12,True)
    for face in focus.data.polygons:
        if abs(face.normal.z)>.9:face.use_smooth=False
    for i in range(4):
        angle=(i+.5)*math.pi/2
        cylinder('relay collar bolt',(13*math.cos(angle),13*math.sin(angle),12),
                 (13*math.cos(angle),13*math.sin(angle),13.3),1.5,STEEL,ALLOY,6,True)
    for z in (-15,-12,-9):
        cylinder('relay stacked cooling fin',(0,0,z),(0,0,z+1.2),15,STEEL,TRIM,12,True)
    for side in (-1,1):
        for z in (-3,1,5):box('relay side cooling slot',(side*15.2,0,z),(1.4,15,1.2),STEEL,DARK,detail=True)
    frame=Matrix.Translation(center) @ Matrix(((u.x,v.x,n.x),(u.y,v.y,n.y),(u.z,v.z,n.z))).to_4x4()
    bpy.context.view_layer.update()
    for obj in shared.objects[start:]:obj.matrix_world=frame @ obj.matrix_world


def ring_parts(lod,slit,deep):
    """The prop's own arch as (kind, mesh) in prop units."""
    scene=bpy.context.scene;before=set(scene.objects)
    generator_ring(lod,slit=slit,deep=deep,printed=False)
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();parts=[]
    for obj in [o for o in scene.objects if o not in before]:
        data=bpy.data.meshes.new_from_object(obj.evaluated_get(deps));data.transform(obj.matrix_world)
        parts.append((obj['kind'],data))
        old=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(old)
    return parts


def generator_units():
    """Seven generator-ring arches in the battlemat's two columns; the small ones are always the LOD1 slit geometry."""
    # Stretched flatter than the prop, so their cuts need more depth in prop units to read as deep.
    large,small=ring_parts(0,False,.95),ring_parts(1,True,.75)
    units=[(large,172,y,BANK_TOP,(40.5/10.5,13/3,9/3.6)) for y in LARGE_GENERATORS]
    units += [(small,258,y,5,(19/10.5,6.5/3,5.8/3.6)) for y in SMALL_GENERATORS]
    placed=[]
    for parts,x,y,z,(sx,sy,sz) in units:
        for kind,data in parts:
            part=data.copy();part.transform(Matrix.Translation((x,y,z)) @ Matrix.Diagonal((sx,sy,sz,1)))
            obj=bpy.data.objects.new('generator ring',part);bpy.context.scene.collection.objects.link(obj)
            if kind=='core':
                shared.finish(obj,FLAT,CYAN);shared.emissive(obj,REACTOR_BLUE)
            else:
                shared.finish(obj,MACHINE,HOUSING)
            placed.append(obj)
    for parts in (large,small):
        for _,data in parts:bpy.data.meshes.remove(data)
    return placed


def low_shaft(x,y0,y1,z,half,height):
    """The visible top of a low half-round shaft along Y; both ends and its underside are buried."""
    arc=[(x-half*math.cos(k*math.pi/6),z+height*math.sin(k*math.pi/6)) for k in range(7)]
    obj=mesh('generator shaft',[(px,y,pz) for y in (y0,y1) for px,pz in arc],
             [(k,k+1,k+8,k+7) for k in range(6)],MACHINE,HOUSING)
    for face in obj.data.polygons:face.use_smooth=True


def wall_stub(x0,x1,y,z,radius):
    """Pointed fitting out of a bank's outer wall."""
    cylinder('generator wall stub',(x0,y,z),(x1,y,z),radius,MACHINE,SLATE,6)
    cylinder('generator wall stub tip',(x1,y,z),(x1+math.copysign(4,x1-x0),y,z),radius*.5,MACHINE,SLATE,6)


def bank_floor():
    """The large bank's dark machine floor inside its lighter frame, with a darker line between them."""
    outline=list(reversed(BANK_OUTLINE))
    prism('bank floor line',inset_outline(outline,8),BANK_TOP,BANK_TOP+.06,MACHINE,(.22,.23,.24))
    prism('bank floor',inset_outline(outline,10),BANK_TOP,BANK_TOP+.12,MACHINE,(.33,.34,.35))


def shaft_terminal():
    """The chamfered block the large shaft ends in against the building, framed around a dark grille."""
    prism('generator shaft terminal',outline_box(138,206,-92,-61,9),BANK_TOP,BANK_TOP+7,MACHINE,SLATE)
    prism('generator shaft terminal grille',outline_box(146,198,-87,-66,6),BANK_TOP+7,BANK_TOP+7.3,GRILLE,(.30,.32,.33))


def power_plant():
    """The battlemat's power plant, read off its crop: three large and four small arches threaded on low shafts,
    with feeds into thin pipes on saddles, end feet, wall stubs, and the two blocks the large bank's lines end in."""
    bank_floor()
    for x,y0,y1 in ((119.5,-192,-162),(119.5,-150,-112),(119.5,-104,-74)):
        box('bank floor panel',(x,(y0+y1)/2,BANK_TOP+.2),(19,y1-y0,.1),MACHINE,(.40,.41,.42))
    generator_units()
    low_shaft(172,-205,-90,BANK_TOP,15,4.2)
    shaft_terminal()
    z=BANK_TOP-12
    box('generator shaft housing',(179.5,-218,17+z),(49,26,10),MACHINE,SLATE_DARK)
    box('generator shaft housing grille',(179.5,-218,22.3+z),(43,20,.6),GRILLE,(.55,.59,.60))
    for y in LARGE_GENERATORS:
        box('generator end foot',(212.5,y,13.2+z),(10,14,2.4),MACHINE,SLATE_DARK)
        # Into the arch short of its outer cut.
        cylinder('generator feed',(141,y,13.8+z),(121,y,13.8+z),1.4,MACHINE,SLATE,6)
        for x in (121,129):
            cylinder('generator feed collar',(x-2.4,y,13.8+z),(x+2.4,y,13.8+z),2.4,STEEL,TRIM,6,True)
    for x in (121,129):
        cylinder('generator pipe',(x,-63,13.8+z),(x,-206,13.8+z),1.2,MACHINE,SLATE,6)
    # The mains end in a flange on the deck's kerb, through which they reach the building.
    box('generator pipe flange',(125,-62.6,13.8+z),(14,1.2,4.4),MACHINE,SLATE_DARK)
    for y in (-92,-130,-164,-198):
        box('generator pipe saddle',(125,y,12.7+z),(14,3,1.4),MACHINE,SLATE_DARK)
    box('generator switchgear',(126.5,-221.5,18+z),(47,33,12),MACHINE,SLATE)
    box('generator switchgear inset',(126.5,-221.5,24.2+z),(22,18,.5),MACHINE,SLATE_DARK)
    for x in (114,139):
        box('generator switchgear window',(x,-235,24.2+z),(10,4,.5),FLAT,CYAN)
    for y in (-130,-163):
        wall_stub(101,92,y,8,2.6)
    low_shaft(258,-173,-88,5,6.5,2.6)
    box('generator shaft end',(258,-174.5,6.9),(16,5,3.8),MACHINE,SLATE_DARK)
    for y in SMALL_GENERATORS:
        for x in (237.5,277):
            box('generator end foot',(x,y,5.7),(5,8,1.4),MACHINE,SLATE)
    for x,y in ((238,-107),(234,-125),(230,-143)):
        # Each thin pipe leaves the wall, stands on one saddle and enters its own arch short of the slit.
        cylinder('generator pipe',(x,-89,6),(x,y,6),.8,MACHINE,SLATE,6)
        cylinder('generator pipe',(x,y,6),(243,y,6),.8,MACHINE,SLATE,6)
        box('generator pipe saddle',(x,(y-92)/2,5.3),(3,2.4,.6),MACHINE,SLATE_DARK)
    for y in (-124,-143,-162):
        wall_stub(278,290,y,3.4,2)


def rear_wing():
    # Joined-map outline. These lobes, the cross platform and the unequal banks
    # deliberately remain separate envelopes instead of one bounding rectangle.
    # Green base / red upper outline from the user's corrected overlay. Mirroring
    # on Y=0 removes only the drawing's pen-width asymmetry. It does not move the
    # source hex lattice or substitute a generic bounding shape.
    # The corrected crop has89px per72-unit row (it was resized after capture).
    # Its upper/lower ink is mirrored at233.5px;2317 supplies the X origin.
    def traced(points):
        return [(reference_hex(23,17)[0]+(x-133.5)*62.34375/77,(233.5-y)*72/89) for x,y in points]
    right_base=traced([(44,152),(96,152),(117,118),(176,118),(194,152),(251,182),
                       (251,285),(194,315),(176,349),(117,349),(96,315),(44,315)])
    right_roof=traced([(44,164),(100,164),(119,127),(170,127),(188,164),(222,182),
                       (222,285),(188,303),(170,340),(119,340),(100,303),(44,303)])
    base_join_y=right_base[0][1];roof_join_y=right_roof[0][1]
    base=[(130,47),(177,47),(200,27),(270,27),(292,base_join_y)]+right_base+[
        (292,-base_join_y),(270,-90),(213,-90),(187,-70),(162,-70),(151,-83),(130,-83)]
    roof=[(134,43),(175,43),(201,23),(272,23),(294,roof_join_y)]+right_roof+[
        (294,-roof_join_y),(268,-86),(215,-86),(189,-66),(160,-66),(149,-79),(134,-79)]
    tapered_envelope('operations lobes',base,roof,36)
    envelope('central connecting rooms',outline_box(58,140,-57,42,6),54,ARMOUR)
    # Five rear heat-exchanger cassettes follow the sloped flat back. Their fins
    # are separate relief, not changes to the gameplay footprint.
    back_x,upper_x=right_base[5][0],right_roof[5][0]
    for y in (-32,-16,0,16,32):
        box('rear heatsink recess',(back_x-6,y,15),(9,13,24),CONCRETE,RECESS)
        for z in (5,10,15,20,25):
            x=back_x+(upper_x-back_x)*z/36
            box('rear heatsink fin',(x+5.5,y,z),(14,13,2.3),STEEL,TRIM,True)
        for side in (-1,1):
            beam('heatsink cassette rail',(back_x+5,y+side*7,4),(upper_x+11,y+side*7,29),2,2,MACHINE,SLATE)
    for x,y in ((175,-20),(223,-43),(246,-43),(372,29),(372,-52),(422,-15)):
        box('service roof hatch',(x,y,37),(14,20,2),STEEL,TRIM)
    for x in (312,324,336): box('east lobe raised conduit',(x,-20,37.5),(5,55,3),MACHINE,SLATE)
    for y in (-39,-24,-9,6,21): box('connector roof duct',(114,y,56),(34,7,4),STEEL,TRIM)

    platform=[(185,130),(225,130),(225,170),(270,170),(270,130),(312,130),(312,50),(290,25),(207,25),(185,50)]
    envelope('secondary radar control platform',platform,18,ARMOUR,roof=PALE_DECK)
    # The low control apron at1916/2016 joins the narrow connector to the
    # secondary radar. It must not inherit the adjacent operations roof height.
    control_apron=[(110,42),(140,42),(140,47),(187.64,47),(185,50),(185,98),(128,98),(110,80)]
    envelope('1916 control apron',control_apron,18,ARMOUR,False,roof=PALE_DECK)
    border_courses([(185,98),(128,98),(110,80),(110,42)],18)
    for a,b in (((185,98),(128,98)),((128,98),(110,80)),((110,80),(110,42))):
        edge_details(a,b,18)
    box('control apron access hatch',(132,73,19),(21,27,2),MACHINE,SLATE)
    box('control apron skylight',(164,74,19),(14,19,2),STEEL,STEEL_CYAN)
    outline_band('control platform skirt',platform,6,4,3)
    for x,y in ((203,94),(294,94),(247,154)):
        box('control access hatch',(x,y,19.5),(20,23,3),MACHINE,SLATE)
    small_radar()

    envelope('main power bank',BANK_OUTLINE,BANK_TOP,ARMOUR,volume_height=36,roof=ARMOUR)
    small=[(225,-90),(275,-90),(280,-100),(280,-174),(270,-185),(230,-185),(225,-174)]
    envelope('auxiliary power bank',small,5,ARMOUR,volume_height=18,roof=BANK_FLOOR)
    power_plant()
    # The small northeastern station is different from the rectangular secondary radar.
    envelope('north turret neck',outline_box(359,389,right_roof[2][1],135,4),36,ARMOUR,False)
    # Open the connector at each building and bury the side curbs beneath the
    # bearing plinth. A closed curb here would cross the roof and fight its cap.
    for xx in (359,389):
        outline_band('relay connector side curb',[(xx+(4 if xx==359 else -4),right_roof[2][1]),
                     (xx,right_roof[2][1]+4),(xx,135)],37.5,3,3,
                     key=STEEL,colour=TRIM,closed=False)
    x,y=reference_hex(23,15)
    poly=[(x+27*math.cos(k*math.tau/12),y+27*math.sin(k*math.tau/12)) for k in range(12)]
    envelope('north service turret',poly,36,CLADDING,False)
    relay_head(x,y)


def pedestal():
    poly=[(72*math.cos(math.pi/8+i*math.tau/8),72*math.sin(math.pi/8+i*math.tau/8)) for i in range(8)]
    # The support above the actual central roof is part of the radar prop, not twelve floors.
    envelope('transmitter pedestal',poly,216,ARMOUR,False,volume_height=54)
    for z in (8,65,134):
        belt=cylinder('pedestal octagonal belt',(0,0,z),(0,0,z+7),76,CONCRETE,CLADDING,8)
        belt.rotation_euler.z=math.pi/8
        for face in belt.data.polygons:face.use_smooth=False
    for i in range(8):
        a=math.pi/8+i*math.tau/8
        x,y=72*math.cos(a),72*math.sin(a)
        beam('pedestal corner column',(x,y,0),(x,y,215),8,8,CONCRETE,CLADDING)
    # Exposed triangular frame panels on the tall transmitter tower.
    for sign in (-1,1):
        y=sign*67
        box('tower panel recess',(0,y,162),(41,2,64),CONCRETE,RECESS)
        for x in (-17,17): beam('tower frame',(x,y+sign*2,135),(x,y+sign*2,195),3,3,STEEL,ALLOY)
        beam('tower diagonal',(-17,y+sign*2,135),(17,y+sign*2,192),3,3,STEEL,ALLOY)
        beam('tower diagonal',(17,y+sign*2,135),(-17,y+sign*2,192),3,3,STEEL,ALLOY)
    # Front cable throat and low service court, not a hole in the generated envelope.
    envelope('transmitter service court',outline_box(-57,57,-147,-62,10),18,ARMOUR,roof=MID_DECK)
    cylinder('conduit mouth',(0,-66,45),(0,-73,45),27,MACHINE,SLATE_DARK,24)
    for x in range(-18,19,6):
        conduit=outline_band('transmitter conduit',[(-72.5,43),(-90,19.75),(-134,19.75)],0,3.5,3.5,key=STEEL,colour=ALLOY,closed=False)
        conduit.matrix_world=Matrix.Translation(Vector((x,0,0))) @ Matrix(((0,0,1),(1,0,0),(0,1,0))).to_4x4()
    # Heavy dark crown under the mount, as the art's neck and the battlemat's dark block.
    flare=cone('pedestal crown flare',196,212,72,98,MACHINE,SLATE_DARK,8)
    crown=cylinder('pedestal crown',(0,0,212),(0,0,226),98,MACHINE,SLATE_DARK,8)
    for obj in (flare,crown):
        obj.rotation_euler.z=math.pi/8
        for face in obj.data.polygons:face.use_smooth=False
    cylinder('azimuth bearing',(0,0,226),(0,0,235),84,MACHINE,SLATE,32)
    # Fork carries the tilted reflector from behind its center.
    n,u=DISH_NORMAL,DISH_RIGHT
    center=DISH_CENTER-n*45
    base=Vector((center.x*.4,center.y*.4,250))
    beam('dish mount base',base-u*92,base+u*92,120,30,MACHINE,SLATE_DARK)
    for sign in (-1,1):
        beam('dish mount fork',base+u*sign*64,center+u*sign*64,36,64,MACHINE,SLATE)
    cylinder('elevation axle',center-u*86,center+u*86,18,STEEL,DARK,24)
    for sign in (-1,1): cylinder('elevation hub',center+u*sign*82,center+u*sign*92,30,STEEL,ALLOY,24)


def dish_z(r):
    return 54*(r/300)**2


def polar_panel(name,shape,offset=1,thickness=2,key=DISH,colour=PLATE,detail=False):
    """A curved, closed plate; polygon coordinates are (radius, angle)."""
    verts=[]
    for dz in (offset,offset+thickness):
        verts += [(r*math.cos(t),r*math.sin(t),dish_z(r)+dz) for r,t in shape]
    n=len(shape)
    # Inputs follow CCW order in the plane.
    faces=[tuple(reversed(range(n))),tuple(range(n,n*2))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh(name,verts,faces,key,colour,detail)


def sector(r0,r1,a,b,segments=8):
    return [(r0,a)] + [(r1,a+(b-a)*i/segments) for i in range(segments+1)] + [(r0,b)] + [(r0,a+(b-a)*i/segments) for i in range(segments-1,0,-1)]


def polar(r,a,z=0,side=0):
    """Reflector-frame point at radius r and angle a, moved side units along the tangent."""
    return Vector((r*math.cos(a)-side*math.sin(a),r*math.sin(a)+side*math.cos(a),z))


def cone(name,z0,z1,r0,r1,key=STEEL,colour=DARK,sides=12):
    """Tapered section on the reflector axis."""
    verts=[(r*math.cos(i*math.tau/sides),r*math.sin(i*math.tau/sides),z) for z,r in ((z0,r0),(z1,r1)) for i in range(sides)]
    faces=[tuple(reversed(range(sides))),tuple(range(sides,sides*2))]
    faces += [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    obj=mesh(name,verts,faces,key,colour)
    obj['uv_projection']='cylinder'
    for face in obj.data.polygons:face.use_smooth=len(face.vertices)==4
    return obj


def web(name,points,half,a,key=MACHINE,colour=SLATE_DARK):
    """Triangular plate in the radial plane at angle a; points are (radius,z)."""
    (r0,z0),(r1,z1),(r2,z2)=points
    if (r1-r0)*(z2-z0)-(z1-z0)*(r2-r0)<0:points=list(reversed(points))
    verts=[(r,side*half,z) for side in (-1,1) for r,z in points]
    obj=mesh(name,verts,[(0,1,2),(5,4,3),(0,3,4,1),(1,4,5,2),(2,5,3,0)],key,colour)
    obj.rotation_euler.z=a
    return obj


def ribbed_barrel(name,z0,z1,radius,ribs,key=STEEL,colour=DARK):
    cylinder(name,(0,0,z0),(0,0,z1),radius,key,colour,10)
    step=(z1-z0)/ribs
    for i in range(ribs):
        cylinder(name+' collar',(0,0,z0+step*(i+.2)),(0,0,z0+step*(i+.7)),radius+2.4,key,colour,8)


def radial_arm(a):
    """Slate arm from the hub to one fin, tapered and ridged so its two top faces catch the light apart."""
    points=[(28,22,16),(132,dish_z(132)+13,28),(206,dish_z(206)+13,26),(297,dish_z(297)+10,18)]
    for (r0,z0,w0),(r1,z1,w1) in zip(points,points[1:]):
        verts=[(r,y,z+dz) for r,z,w in ((r0,z0,w0),(r1,z1,w1)) for y,dz in ((w/2,-5),(w/2,5-w*.12),(0,5),(-w/2,5-w*.12),(-w/2,-5))]
        faces=[(4,3,2,1,0),(5,6,7,8,9)]+[(i,(i+1)%5,(i+1)%5+5,i+5) for i in range(5)]
        mesh('radial arm',verts,faces,MACHINE,SLATE).rotation_euler.z=a
    for r,z,width in points[1:3]:
        beam('radial arm clamp',polar(r-5,a,z),polar(r+5,a,z),width+8,15,MACHINE,SLATE_DARK)


def boom(a,side):
    """Open lattice boom from a rim node to the apex collar, with its foot and service conduits."""
    foot,top=polar(286,a,80),polar(38,a,APEX_Z)
    along=top-foot;axis=along.normalized();tangent=polar(0,a,0,1)
    normal=axis.cross(tangent)
    corners=[tangent*s*BOOM_WIDTH/2+normal*t*BOOM_DEPTH/2 for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
    bays=round(along.length/BOOM_BAY)
    def station(corner,i):
        return foot+along*i/bays+corners[corner]
    for corner in range(4):
        beam('boom chord',station(corner,0),station(corner,bays),4,4,MACHINE,SLATE_DARK)
    # Each face zigzags in the opposite phase to the face behind it, so looking
    # through the open boom reads as the X bracing the references draw.
    for i in range(bays):
        for c0,c1 in ((0,1),(2,3),(1,2),(3,0)):
            p,q=(c0,c1) if i%2==0 else (c1,c0)
            # Open three-sided members, whose ends are buried in the chords.
            cylinder('boom lacing',station(p,i),station(q,i+1),1.7,MACHINE,SLATE_DARK,3,True,caps=False)
    beam('boom foot block',foot-axis*8,foot+axis*22,BOOM_WIDTH+8,BOOM_DEPTH+8,MACHINE,SLATE_DARK)
    beam('boom head block',top-axis*22,top+axis*6,BOOM_WIDTH+4,BOOM_DEPTH+6,MACHINE,SLATE_DARK)
    web('boom foot gusset',[(190,dish_z(190)+3),(294,dish_z(294)+3),(294,88)],BOOM_WIDTH/2+6,a)
    o=box('boom foot saddle',(297,0,64),(24,42,26),MACHINE,SLATE);o.rotation_euler.z=a
    # Two thin conduits leave the foot, stand off from the boom and rejoin it.
    join=foot+along*.3+tangent*side*BOOM_WIDTH/2
    for offset in (0,6):
        points=[polar(258-offset,a,dish_z(258)+20,side*(12+offset)),polar(208-offset,a,88,side*(32+offset)),join+axis*offset]
        for p,q in zip(points,points[1:]):
            cylinder('boom conduit',p,q,1.5,STEEL,DARK,3,True)


def feed():
    """Hub spike and apex head: stepped, ribbed barrels on the reflector axis."""
    cylinder('central feed socket',(0,0,0),(0,0,18),46,MACHINE,SLATE_DARK,24)
    cone('feed collar',18,32,36,15,sides=16)
    ribbed_barrel('hub spike barrel',32,112,8.5,6)
    cylinder('hub spike band',(0,0,112),(0,0,118),12,STEEL,ALLOY,12)
    cone('hub spike nose',118,146,10,4.5)
    cylinder('hub spike tip',(0,0,146),(0,0,151),2.4,STEEL,ALLOY,8)
    for i in range(8):
        web('hub feed vane',[(58,7),(15,30),(10,60)],1.6,(i+.5)*math.tau/8,STEEL,DARK)
    ring('apex collar',27,33,APEX_Z-4,8,MACHINE,SLATE,32)
    for i in range(4):
        a=(i+.5)*math.tau/4
        beam('apex collar spoke',polar(14,a,APEX_Z),polar(30,a,APEX_Z),6,5,MACHINE,SLATE_DARK)
    cylinder('apex drum',(0,0,APEX_Z-36),(0,0,APEX_Z+36),19,STEEL,DARK,16)
    cone('apex shoulder',APEX_Z+36,APEX_Z+48,19,8,sides=16)
    ribbed_barrel('apex spike barrel',APEX_Z+48,APEX_Z+84,6.5,4)
    cone('apex spike',APEX_Z+84,APEX_Z+142,5.5,3.8,sides=10)
    cone('apex spike tip',APEX_Z+142,APEX_Z+154,5,1.6,STEEL,ALLOY,8)
    ribbed_barrel('apex tail barrel',APEX_Z-72,APEX_Z-36,11,3)
    cone('apex tail nose',APEX_Z-84,APEX_Z-72,5,11)
    for i in range(3):
        web('apex tail vane',[(4,APEX_Z-66),(13,APEX_Z-82),(3,APEX_Z-125)],1.6,i*math.tau/3+.4,STEEL,DARK)


def on_dish(parts):
    """Moves parts modelled in the reflector's own frame onto it."""
    n,u=DISH_NORMAL,DISH_RIGHT
    v=n.cross(u)
    rot=Matrix(((u.x,v.x,n.x),(u.y,v.y,n.y),(u.z,v.z,n.z))).to_4x4()
    frame=Matrix.Translation(DISH_CENTER) @ rot @ Matrix.Rotation(DISH_SPIN,4,'Z')
    bpy.context.view_layer.update()
    for obj in parts:
        obj.matrix_world=frame @ obj.matrix_world
        obj['hpg_part']='reflector'
        if obj.get('uv_projection') != 'cylinder':
            obj['uv_projection']='planar'


def reflector():
    start=len(shared.objects)
    # Keep the circular silhouette fine, with eight radial steps across the
    # shallow bowl (maximum chord error 0.22 units). This leaves the vertex
    # budget for hard architectural edges rather than invisible subdivisions.
    verts=[];faces=[];sides=96;rings=8
    for offset in (0,-5):
        verts.append((0,0,offset))
        for ring_index in range(1,rings+1):
            r=ring_index*300/rings
            verts.extend((r*math.cos(i*math.tau/sides),r*math.sin(i*math.tau/sides),dish_z(r)+offset) for i in range(sides))
    layer=1+rings*sides
    front=[(0,1+i,1+(i+1)%sides) for i in range(sides)]
    for ring_index in range(rings-1):
        a=1+ring_index*sides;b=a+sides
        front.extend((a+i,b+i,b+(i+1)%sides,a+(i+1)%sides) for i in range(sides))
    faces.extend(front);faces.extend(tuple(layer+i for i in reversed(f)) for f in front)
    rim=1+(rings-1)*sides
    faces.extend((rim+i,layer+rim+i,layer+rim+(i+1)%sides,rim+(i+1)%sides) for i in range(sides))
    obj=mesh('backed parabolic reflector',verts,faces,DISH,BACKING)
    for face in obj.data.polygons:face.use_smooth=True
    for i in range(16):
        a,b=i*math.tau/16+.012,(i+1)*math.tau/16-.012
        # Repeated shield plates have notched inner shoulders and broken outer edges.
        shape=[(209,a),(282,a),(291,a+.018),(291,b-.018),(282,b),(209,b),(209,b-.055),(224,b-.055),(224,a+.055),(209,a+.055)]
        polar_panel('outer reflector shield',shape,1,2,colour=PLATE if i%2 else PLATE_ALT)
        polar_panel('inner reflector tile',sector(86,172,a+.012,b-.012,3),1,2)
        # T-shaped etched detail makes the face read as the supplied industrial pattern.
        mid=(a+b)/2
        polar_panel('outer stepped track',[(236,a+.025),(247,a+.025),(247,mid-.035),(277,mid-.035),(277,mid+.035),(247,mid+.035),(247,b-.025),(236,b-.025)],2.8,4.6,DISH,PLATE_LOW)
        o=polar_panel('raised stepped armour',[(241,a+.035),(244,a+.035),(244,mid-.047),(281,mid-.047),(281,mid+.047),(244,mid+.047),(244,b-.035),(241,b-.035)],7.5,2,DISH,PLATE_ALT,True)
        for face in o.data.polygons:face.use_smooth=False
    for r,w,h,z,sides in ((56,7,7,4,48),(80,3,4,4,48),(112,3,3,2.5,64),(140,3,3,2.5,64),(180,4,7,4,96),(199,4,7,4,96)):
        ring('concentric reflector rail',r-w/2,r+w/2,z,h,DISH,PLATE_LOW if r in (112,140,180,199) else PLATE_ALT,sides,curve=True)
    ring('reflector rim',295,303,-10,19,DISH,PLATE_ALT,96,curve=True)
    for i in range(8):
        a=i*math.tau/8
        radial_arm(a)
        for r0,r1 in ((57,177),(202,296)):
            polar_panel('radial rear stiffener',sector(r0,r1,a-.023,a+.023,1),-16,8,MACHINE,SLATE_DARK)
        # Eight alternating arrowhead fins, widest near the rim, with a dark ribbed inset.
        # The four short ones sit on the boom nodes.
        length,wide,tip=(100,27,15) if i%2==0 else (46,21,13)
        end=295+length
        outline=[(295,-12),(318,-wide),(end-8,-tip),(end,-tip+6),(end,tip-6),(end-8,tip),(318,wide),(295,12)]
        o=prism('reflector perimeter fin',outline,51,57,MACHINE,SLATE);o.rotation_euler.z=a
        inset=[(310,-8),(320,-wide+5),(end-11,-tip+4.5),(end-5,-tip+8),(end-5,tip-8),(end-11,tip-4.5),(320,wide-5),(310,8)]
        o=prism('fin inset',inset,57,58,MACHINE,SLATE_DARK);o.rotation_euler.z=a
        for y in (-8,-4,0,4,8) if i%2==0 else (-5,0,5):
            o=mesh('fin longitudinal rib',[(324,y-.6,58.2),(end-12,y-.6,58.2),(end-12,y+.6,58.2),(324,y+.6,58.2)],[(0,1,2,3)],MACHINE,SLATE,True)
            o.rotation_euler.z=a
        o=box('fin mounting saddle',(299,0,55),(17,31,10),MACHINE,SLATE);o.rotation_euler.z=a
        if i%2:boom(a,1 if i in (3,5) else -1)
    feed()
    cone('rear hub housing',-62,-1,72,110,MACHINE,SLATE_DARK,24)
    on_dish(shared.objects[start:])


def preview_materials():
    """Use the shared Material Maker preview and export the same authored UVs."""
    bpy.context.view_layer.update()
    for obj in shared.objects:
        shared.project_uvs(obj)
        # The default 18-unit repeat reads as a lattice across these long spans.
        if obj['board_material'] in (CONCRETE, DISH):
            for corner in obj.data.uv_layers.active.data:
                corner.uv *= 18/CONCRETE_REPEAT


def studio():
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-.5
    world=bpy.data.worlds.new('HPG studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.18,.21,.25,1);world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
    for name,pos,power,size in [('key',(-500,-850,1300),22000000,850),('fill',(700,-100,800),13000000,700),('rim',(0,700,1000),25000000,600)]:
        data=bpy.data.lights.new('HPG '+name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        o=bpy.data.objects.new('HPG '+name,data);scene.collection.objects.link(o);o.location=pos;o.rotation_euler=(Vector((0,0,140))-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('HPG review camera');data.type='ORTHO';data.clip_end=10000
    camera=bpy.data.objects.new('HPG review camera',data);scene.collection.objects.link(camera);scene.camera=camera
    camera.location=(-1500,-1300,1150);data.ortho_scale=1600
    camera.rotation_euler=(Vector((-35,0,220))-camera.location).to_track_quat('-Z','Y').to_euler()
    # A presentation surface, never included in exported geometry or helper volumes.
    ground=mesh('Review ground',[(-3000,-3000,-1),(3000,-3000,-1),(3000,3000,-1),(-3000,3000,-1)],[(0,1,2,3)],FLAT,(.12,.15,.18))
    shared.objects.remove(ground)
    ground['review_only']=True
    # Real model-unit hex grid for judging scale, not a decorative mesh in the asset.
    edges=set()
    for col in range(-12,13):
        for row in range(-7,8):
            cx=col*62.34375;cy=row*72+(col%2)*36
            pts=[(cx+41.5625*math.cos(k*math.tau/6),cy+36*math.sin(k*math.tau/6)/math.sin(math.pi/3),-.6) for k in range(6)]
            for a,b in zip(pts,pts[1:]+pts[:1]):
                pair=tuple(sorted((tuple(round(v,3) for v in a),tuple(round(v,3) for v in b))))
                if pair not in edges:
                    edges.add(pair)
    verts=[];faces=[]
    for a,b in edges:
        av,bv=Vector(a),Vector(b);normal=Vector((-(bv-av).y,(bv-av).x,0)).normalized()*.24
        start=len(verts);verts += [av+normal,av-normal,bv-normal,bv+normal];faces.append(tuple(start+i for i in range(4)))
    grid=mesh('Review hex grid',verts,faces,FLAT,(.29,.35,.38));shared.objects.remove(grid);grid['review_only']=True


def reference_setup():
    """Register the supplied raster to the real hex lattice, correcting its joined seam."""
    path=HERE/'references/hpg-joined-map.png'
    img=bpy.data.images.load(str(path),check_existing=True)
    img.pack()
    correction=bpy.data.images.load(str(HERE/'references/hpg-right-outline.png'),check_existing=True)
    correction.pack()
    guide=bpy.data.objects.new('Right end green-base red-roof reference',None)
    bpy.context.scene.collection.objects.link(guide);guide.empty_display_type='IMAGE';guide.data=correction
    guide.empty_display_size=294*62.34375/77
    guide.scale.y=(72/89)/(62.34375/77)
    guide.location=(reference_hex(23,17)[0]+(147-133.5)*62.34375/77,(233.5-202.5)*72/89,-3)
    guide.hide_render=True;guide.hide_set(True)
    sx,sy=62.34375/93.5,72/108
    material=bpy.data.materials.new('Calibrated HPG reference');material.use_nodes=True
    nodes=material.node_tree.nodes;nodes.clear()
    tex=nodes.new('ShaderNodeTexImage');tex.image=img
    shader=nodes.new('ShaderNodeEmission');shader.inputs['Strength'].default_value=1
    output=nodes.new('ShaderNodeOutputMaterial')
    material.node_tree.links.new(tex.outputs['Color'],shader.inputs['Color'])
    material.node_tree.links.new(shader.outputs[0],output.inputs['Surface'])
    for name,top,bottom,origin_x in [('upper',0,474,972.5),('lower',474,1020,969.25)]:
        x0,x1=-origin_x*sx,(1737-origin_x)*sx
        y0,y1=(420-bottom)*sy,(420-top)*sy
        o=mesh('Reference '+name,[(x0,y0,-2),(x1,y0,-2),(x1,y1,-2),(x0,y1,-2)],[(0,1,2,3)],FLAT,(1,1,1))
        shared.objects.remove(o);o.data.materials.clear();o.data.materials.append(material)
        uv=o.data.uv_layers.new(name='Reference pixels')
        coords=[(0,1-bottom/1020),(1,1-bottom/1020),(1,1-top/1020),(0,1-top/1020)]
        for loop in o.data.loops: uv.data[loop.index].uv=coords[loop.vertex_index]
        o['reference_layer']=True;o['reference_units_per_pixel']=(sx,sy);o.hide_render=True

    def ink(name,colour):
        mat=bpy.data.materials.new(name);mat.diffuse_color=(*colour,1);mat.use_nodes=True
        n=mat.node_tree.nodes;n.clear();em=n.new('ShaderNodeEmission');em.inputs[0].default_value=(*colour,1)
        out=n.new('ShaderNodeOutputMaterial');mat.node_tree.links.new(em.outputs[0],out.inputs['Surface'])
        return mat
    mark_mat=ink('Reference landmark red',(1,.08,.025))
    height_mats={18:ink('One-level footprint',(.05,.8,1)),36:ink('Two-level footprint',(1,.72,.04)),54:ink('Three-level footprint',(.9,.06,.8))}
    taper_base_mat=ink('Traced green base',(.32,1,.04))
    taper_roof_mat=ink('Traced red upper outline',(1,.035,.015))

    def outline(name,points,mat,width=.7,kind='reference_marker'):
        verts=[];faces=[]
        for a,b in zip(points,points[1:]+points[:1]):
            p,q=Vector((*a,300)),Vector((*b,300));d=q-p
            if d.length<.001:continue
            normal=Vector((-d.y,d.x,0)).normalized()*width/2
            offset=len(verts);verts.extend((p+normal,p-normal,q-normal,q+normal));faces.append(tuple(offset+i for i in range(4)))
        obj=mesh(name,verts,faces,FLAT,(1,1,1));shared.objects.remove(obj)
        obj.data.materials.clear();obj.data.materials.append(mat);obj[kind]=True;obj.hide_render=True

    landmarks=[(c,r) for c in (10,12,14) for r in (14,19)]+[(7,17),(17,17),(21,16),(23,15)]
    for c,r in landmarks:
        x,y=reference_hex(c,r);label='%02d%02d'%(c,r if r<=17 else r-17)
        outline('Hex '+label+' alignment ring',[(x+36*math.cos(i*math.tau/64),y+36*math.sin(i*math.tau/64)) for i in range(64)],mark_mat)
        outline('Hex '+label+' center',[(x-5,y),(x+5,y)],mark_mat,1)
        outline('Hex '+label+' center',[(x,y-5),(x,y+5)],mark_mat,1)
        data=bpy.data.curves.new('Source hex '+label,'FONT');data.body=label;data.size=11
        obj=bpy.data.objects.new('Source hex '+label,data);bpy.context.scene.collection.objects.link(obj)
        obj.location=(x+7,y+8,301);obj.data.materials.append(mark_mat);obj['reference_marker']=True;obj.hide_render=True
    for obj in shared.volumes:
        top=max(v.co.z for v in obj.data.vertices)
        for face in obj.data.polygons:
            if all(abs(obj.data.vertices[i].co.z-top)<.001 for i in face.vertices):
                points=[obj.matrix_world @ obj.data.vertices[i].co for i in face.vertices]
                mat=taper_roof_mat if obj.get('reference_tapered') else height_mats[round(top)]
                outline('Volume outline '+obj.name,[(p.x,p.y) for p in points],mat,1,'reference_outline')
            elif obj.get('reference_tapered') and all(abs(obj.data.vertices[i].co.z)<.001 for i in face.vertices):
                points=[obj.matrix_world @ obj.data.vertices[i].co for i in face.vertices]
                outline('Base outline '+obj.name,[(p.x,p.y) for p in points],taper_base_mat,1,'reference_outline')


def view(name='hero',iteration='01'):
    scene=bpy.context.scene
    positions={'hero':(-1500,-1300,1150),'nose':(-1700,-350,950),'side':(0,-2000,620),'rear':(900,1600,1000),'plan':(0,0,2200),'registration':(0,0,2200),'overlay':(0,0,2200),'operations':(1000,-800,850),'sensors':(700,-650,650),'base':(-1500,-900,900)}
    camera=scene.camera;camera.location=positions[name]
    target=Vector((-35,0,220 if name!='plan' else 0))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=1600
    if name=='operations':
        camera.rotation_euler=(Vector((280,-35,40))-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.ortho_scale=630
    if name=='sensors':
        camera.rotation_euler=(Vector((310,110,38))-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.ortho_scale=370
    if name=='base':
        camera.rotation_euler=(Vector((-330,0,45))-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.ortho_scale=930
    if name=='plan':
        camera.location=(-35,0,2200);camera.rotation_euler=(0,0,0);camera.data.ortho_scale=1450
    if name in ('registration','overlay'):
        camera.location=(-60,-60,2200);camera.rotation_euler=(0,0,0);camera.data.ortho_scale=1250
    scene.render.filepath=str(shared.SOURCE/f'hpg-{iteration}-{name}.png')
    hidden=[];states={obj:obj.hide_render for obj in scene.objects}
    if name in ('plan','base'):
        hidden=[o for o in shared.objects if o.get('hpg_part')=='reflector']
        for obj in hidden: obj.hide_render=True
    if name in ('registration','overlay'):
        for obj in scene.objects:
            if obj.type not in ('MESH','FONT'):continue
            obj.hide_render=not (obj.get('reference_layer') or obj.get('reference_marker') or obj.name=='Review hex grid'
                                or name=='overlay' and obj.get('reference_outline'))
    try: bpy.ops.render.render(write_still=True)
    finally:
        for obj,value in states.items(): obj.hide_render=value
    return scene.render.filepath


def plain_dish(sides,bands):
    """The reflector as one smooth bowl in bands of (outer radius, pigment), with a plain back and rim."""
    def annulus(r0,r1,dz):
        ring=lambda r:[(r*math.cos(i*math.tau/sides),r*math.sin(i*math.tau/sides),dish_z(r)+dz) for i in range(sides)]
        if not r0:
            return [(0,0,dz)]+ring(r1),[(0,1+i,1+(i+1)%sides) for i in range(sides)]
        return ring(r0)+ring(r1),[(i,sides+i,sides+(i+1)%sides,(i+1)%sides) for i in range(sides)]
    inner=0
    for outer,colour in bands:
        verts,faces=annulus(inner,outer,3)
        face=mesh('plain dish face',verts,faces,DISH,colour)
        for polygon in face.data.polygons:polygon.use_smooth=True
        inner=outer
    verts,faces=[],[]
    inner=0
    for outer,_ in bands:
        ring,quads=annulus(inner,outer,-6)
        faces+=[tuple(len(verts)+i for i in reversed(f)) for f in quads]
        verts+=ring
        inner=outer
    # The back's last ring meets the face's last ring around the rim.
    back=len(verts)-sides
    verts+=[(inner*math.cos(i*math.tau/sides),inner*math.sin(i*math.tau/sides),dish_z(inner)+3) for i in range(sides)]
    faces+=[(back+i,back+(i+1)%sides,back+sides+(i+1)%sides,back+sides+i) for i in range(sides)]
    back=mesh('plain dish back',verts,faces,DISH,BACKING)
    for polygon in back.data.polygons:polygon.use_smooth=True


def plain_antenna(strut=1,arms=True,foot=(286,80),head=38):
    """The front of the antenna on the far levels: booms as solid beams, spike and head as single shapes on the axis.

    strut scales the booms' section, so that they keep reading where a pixel is wider than they are. foot and head are
    where each boom ends: (radius, height) and radius; without the foot and head blocks it must reach the rim and the collar.
    """
    for i in (1,3,5,7):
        a=i*math.tau/8
        beam('plain boom',polar(foot[0],a,foot[1]),polar(head,a,APEX_Z),BOOM_WIDTH*strut,BOOM_DEPTH*strut,MACHINE,SLATE_DARK)
    for i in range(8 if arms else 0):
        a=i*math.tau/8
        beam('plain radial arm',polar(28,a,22),polar(297,a,dish_z(297)+10),22,10,MACHINE,SLATE)
    cone('plain hub',0,32,46,15,MACHINE,SLATE_DARK,8)
    cone('plain hub spike',32,151,10,2.4,STEEL,DARK,6)
    cone('plain apex tail',APEX_Z-84,APEX_Z-36,5,19,STEEL,DARK,6)
    cone('plain apex collar',APEX_Z-4,APEX_Z+4,33,33,MACHINE,SLATE,8)
    cone('plain apex drum',APEX_Z-36,APEX_Z+36,19,19,STEEL,DARK,8)
    cone('plain apex spike',APEX_Z+36,APEX_Z+154,8,2,STEEL,DARK,6)


def lod1_parts():
    """LOD1's authored shapes: on a grid the arches would close over their cores, and the dish's plates and lattice would shred."""
    plain_generators()
    start=len(shared.objects)
    # A little darker than the plates they replace: each ring's average takes in LOD0's joints and shadow lines.
    plain_dish(32,((86,(.64,.65,.64)),(172,(.91,.91,.91)),(209,(.69,.69,.68)),(303,PLATE_FAR)))
    plain_antenna()
    on_dish(shared.objects[start:])


def plain_masses():
    """Each building's mass as bare walls and a roof on its own outline."""
    for name,base,roof,height,walls,top in MASSES:
        n=len(base)
        verts=[(*p,0) for p in base]+[(*p,height) for p in roof]
        mesh(name+' plain walls',verts,[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],CONCRETE,walls)['building_paint']=True
        mesh(name+' plain roof',[(*p,height) for p in roof],[tuple(range(n))],CONCRETE,top)


def plain_generators():
    """Each generator as a low dark block with its blue core along the top."""
    for x,ys,z,w,d,h,bars,along,across in ((172,LARGE_GENERATORS,BANK_TOP,81,26,8,(-20,0,20),3.5,6.5),(258,SMALL_GENERATORS,5,38,13,5,(0,),14,1.5)):
        for y in ys:
            box('plain generator',(x,y,z+h/2),(w,d,h),MACHINE,HOUSING)
            for dx in bars:
                core=[(x+dx-along,y-across,z+h+.3),(x+dx+along,y-across,z+h+.3),(x+dx+along,y+across,z+h+.3),(x+dx-along,y+across,z+h+.3)]
                shared.emissive(mesh('plain generator core',core,[(0,1,2,3)],FLAT,CYAN),REACTOR_BLUE)


def lod2_parts():
    """All of LOD2 but the parts it borrows: plain masses, dish and struts, no parts too small to see."""
    plain_masses()
    bank_floor()
    shaft_terminal()
    plain_generators()
    cylinder('plain azimuth bearing',(0,0,226),(0,0,235),84,MACHINE,SLATE,8)
    start=len(shared.objects)
    plain_dish(16,((150,PLATE_LOW),(303,PLATE_FAR)))
    plain_antenna(1.5,False,(292,dish_z(292)),25)
    cone('plain rear hub',-62,-1,72,110,MACHINE,SLATE_DARK,8)
    on_dish(shared.objects[start:])


def named(*names):
    return [o for o in shared.objects if o.name.split('.')[0] in names]


def export():
    bpy.context.view_layer.update()
    plain_lod1,plain_lod2=shared.temporary(lod1_parts),shared.temporary(lod2_parts)
    levels={0:shared.export_model(shared.objects,NAME+'-lod0'),
            1:shared.together(shared.export_model([o for o in shared.objects if o.get('hpg_part')!='reflector' and o.name.split('.')[0]!='generator ring'],NAME+'-lod1',level=1),
                       shared.export_model(plain_lod1+named('reflector perimeter fin','fin mounting saddle','boom foot block','boom head block',
                                                            'boom foot gusset','boom foot saddle','rear hub housing','radial rear stiffener'),NAME+'-lod1-dish')),
            2:shared.export_model(plain_lod2+named('pedestal crown flare','pedestal crown','dish mount base','dish mount fork','generator shaft',
                                                   'generator shaft housing','secondary radar backing','secondary radar pedestal',
                                                   'relay bearing plinth','relay angular shroud'),NAME+'-lod2')}
    shared.discard(plain_lod1+plain_lod2)
    helpers=shared.export_model(shared.volumes,NAME,helper=True)
    vertices=[sum(len(m['vertices'])//12 for m in lod['meshes']) for lod in levels.values()]
    assert max(vertices)<=65535, f'Rigid renderer vertex budget exceeded: {vertices}'
    shared.write_glb(shared.DEST/(NAME+'.glb'),levels=levels,groups={'building_volumes':helpers})
    path=shared.SOURCE/(NAME+'.blend')
    # Save the live workspace too, so the visible Blender document is the HPG
    # being edited. Other user scenes remain in that workspace, untouched.
    bpy.ops.wm.save_as_mainfile(filepath=str(path),compress=True,check_existing=False)
    return {'triangles':[sum(len(p['indices'])//3 for m in lod['meshes'] for p in m['parts']) for lod in levels.values()],'vertices':vertices,'volumes':len(shared.volumes),'bytes':(shared.DEST/(NAME+'.glb')).stat().st_size}


def build():
    if bpy.context.object and bpy.context.object.mode!='OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    old=bpy.data.scenes.get(SCENE)
    scene=bpy.data.scenes.new(SCENE+'.new' if old else SCENE)
    bpy.context.window.scene=scene
    if old:
        # Only this generated scene is replaced; user scenes and their objects remain untouched.
        for obj in list(old.objects):
            if len(obj.users_scene)==1: bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.scenes.remove(old);scene.name=SCENE
    shared.objects=[];shared.volumes=[];shared.materials={};shared.role='';MASSES.clear()
    main_wing();rear_wing();pedestal();reflector()
    preview_materials();studio();bpy.context.view_layer.update();reference_setup()
    return {'objects':len(shared.objects),'volumes':len(shared.volumes)}


if __name__=='__main__':
    build();export();view()
