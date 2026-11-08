"""Small civic buildings; build and review in the connected Blender MCP instance.

Exact board units: hex 83.125 x 72, level 18. Church ~1 x 2 hexes,
arena ~2 x 3. Shared Material Maker finishes only; no private texture copies.
The flat-topped helpers describe usable space, never the decorative roof/spires.
"""
import bisect
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import authored_examples as shared
import building_lod
from hpg_headquarters import mesh, prism, box, beam, inset_outline, outline_band
from glb_geometry import write_glb

CONCRETE = shared.CONCRETE
PAINT = 'structures/common/painted-steel'
STEEL = shared.STEEL
GRILLE = 'structures/common/grille'
GLASS = 'structures/buildings/fortress-glass'
CREAM = (1, .99, .93)
LIGHT = (.86, .88, .88)
DARK = (.27, .32, .35)
TEAL = (.30, .40, .39)
GOLD = (.84, .54, .22)
NAME = ''
ARENA_POWER = 3.2


def painted(obj):
    obj['building_paint'] = True
    return obj


def wall_shell(name, outline, height, material=CONCRETE, colour=CREAM, tint=True):
    # Continuous mitered shell, with no hidden floor spanning the usable space.
    obj = outline_band(name, outline, height/2, height, 1.2, -.6,
                       key=material, colour=colour)
    if tint:
        painted(obj)
    return obj


def helper(name, outline, height):
    return prism('building_volume '+name, outline, 0, height,
                 shared.FLAT, (.3, .8, .65), helper=True)


def rect(x0, x1, y0, y1):
    return [(x0,y0), (x1,y0), (x1,y1), (x0,y1)]


def vertical_panel(name, polygon, origin, horizontal=(1,0,0), material=PAINT,
                   colour=CREAM, thickness=.3, tint=False):
    # Polygon lives in local X/Z. Its front faces local -Y, rotated with the facade.
    p = prism(name, polygon, -thickness/2, thickness/2, material, colour)
    u = Vector(horizontal).normalized()
    z = Vector((0,0,1)); outward = u.cross(z)
    frame = Matrix(((u.x,z.x,outward.x,0), (u.y,z.y,outward.y,0),
                    (u.z,z.z,outward.z,0), (0,0,0,1)))
    p.matrix_world = Matrix.Translation(Vector(origin)) @ frame
    if tint:
        painted(p)
    return p


def stairs(name, x, front_y, rear_y, width, height, count=5):
    for i in range(count):
        #30cm treads lead onto a level landing at the threshold.
        y0=front_y+min(.9,(rear_y-front_y)/count)*i
        box(name+' tread',(x,(y0+rear_y)/2,(i+1)*height/count/2),
            (width,rear_y-y0,(i+1)*height/count),CONCRETE,(.867,.892,.88))


def concrete_box(name, center, size, tint=True, colour=CREAM):
    obj=box(name,center,size,CONCRETE,colour)
    return painted(obj) if tint else obj


def personnel_door(name, center, horizontal=(1,0,0)):
    # Three world units per metre: 1.2m x2.4m door inside the much larger portal.
    c=Vector(center);u=Vector(horizontal);n=u.cross(Vector((0,0,1)))
    vertical_panel(name+' frame',rect(-2.1,2.1,0,7.7),c,u,STEEL,DARK,.45)
    vertical_panel(name+' leaf',rect(-1.8,1.8,0,7.2),c+n*.28+Vector((0,0,.15)),
                   u,PAINT,(.45,.51,.50),.2)
    vertical_panel(name+' vision panel',rect(-.9,.9,0,2),c+n*.41+Vector((0,0,3.7)),
                   u,GLASS,(.86,.89,.86),.12)
    a=c+u*1.15+n*.53+Vector((0,0,3.1))
    beam(name+' pull handle',a,a+Vector((0,0,.65)),.12,.13,STEEL,(.72,.75,.72),True)
    utility_light(c+Vector((0,0,8.1)),2.1,u)


def guardrail(name, start, end, height=3.3, start_post=True, end_post=True):
    # 1.1m top rail and waist rail, with maximum2m post spacing.
    a,b=Vector(start),Vector(end);up=Vector((0,0,height))
    beam(name+' top',a+up,b+up,.18,.18,STEEL,(.52,.57,.55))
    beam(name+' mid',a+up*.5,b+up*.5,.12,.12,STEEL,(.46,.51,.50),True)
    count=max(1,math.ceil((b-a).length/6))
    for i in range(count+1):
        if (i == 0 and not start_post) or (i == count and not end_post):
            continue
        p=a.lerp(b,i/count)
        beam(name+' post',p,p+up,.2,.2,STEEL,(.49,.54,.52),True)


def marking(text, origin, horizontal=(1,0,0), size=1.4):
    # A few legible wayfinding numerals, mesh-only and omitted at the far LOD.
    bpy.ops.object.text_add()
    obj=bpy.context.object;obj.name='access marking '+text
    obj.data.body=text;obj.data.size=size;obj.data.extrude=.008;obj.data.resolution_u=1
    u=Vector(horizontal);z=Vector((0,0,1));n=u.cross(z)
    obj.matrix_world=Matrix.Translation(Vector(origin))@Matrix(((u.x,z.x,n.x,0),
        (u.y,z.y,n.y,0),(u.z,z.z,n.z,0),(0,0,0,1)))
    bpy.ops.object.convert(target='MESH')
    obj=bpy.context.object
    # Font conversion splits cap boundaries. Weld them without altering the glyph.
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free()
    return shared.finish(obj,PAINT,(.76,.75,.65),True,False)


def maintenance_ladder(center, horizontal, bottom, top):
    u=Vector(horizontal);c=Vector(center)
    for side in (-1,1):
        a=c+u*(side*1.15)+Vector((0,0,bottom))
        beam('maintenance ladder upright',a,a+Vector((0,0,top-bottom)),.17,.17,STEEL,(.57,.62,.59),True)
    for step in range(math.floor((top-bottom)/.9)+1):
        p=c+Vector((0,0,bottom+step*.9))
        beam('maintenance ladder rung',p-u*1.15,p+u*1.15,.13,.13,STEEL,(.57,.62,.59),True)


def church_scale_details():
    # Explicit construction cadence:3m lifts and~1.5m formwork panels.
    for side in (-1,1):
        height=79 if side<0 else 56
        for z in range(9,height,9):
            box('tower cast lift joint',(side*11.2,-66.035,z),(9.5,.09,.10),STEEL,(.56,.57,.52),True)
        box('tower formwork joint',(side*11.2,-66.035,height/2),(.10,.09,height-.1),STEEL,(.58,.59,.54),True)
        for y in (-34,-9,16,41):
            for z in (9,18,27):
                box('pier cast lift joint',(side*35.035,y,z),(.09,8.6,.10),STEEL,(.56,.57,.52),True)
        for y0,y1 in ((-29.5,-13.5),(-4.5,11.5),(20.5,36.5)):
            guardrail('aisle roof safety rail',(side*29.8,y0,18.15),(side*29.8,y1,18.15))
        guardrail('nave roof safety rail',(side*20.8,-32,37),(side*20.8,39,37))
    maintenance_ladder((35.35,41,0),(0,1,0),1.5,30.5)
    maintenance_ladder((23.35,41,0),(0,1,0),29,38.7)
    # Recessed roof access cover and service curbs, with ordinary human dimensions.
    box('maintenance roof hatch',(12,31,38.85),(5,7,.7),STEEL,(.43,.49,.47))
    for y in (28.5,33.5):
        box('hatch hinge',(9.4,y,38.95),(.7,.8,.6),STEEL,(.63,.67,.63),True)
    for x in (-7.3,7.3):
        guardrail('entry handrail',(x,-72.5,.3),(x,-63,1.5),2.9)
    marking('01',(5.2,-62.25,4),size=1.2)


def arena_scale_details(rx,ry):
    for i in range(12):
        a0=i*math.tau/12+.021;a1=(i+1)*math.tau/12-.021
        for t in (2/6,4/6):
            a=a0+(a1-a0)*t
            p=(rx*.80*oval(a)[0],ry*.80*oval(a)[1],41.84)
            q=(rx*.97*oval(a)[0],ry*.97*oval(a)[1],40.04)
            beam('canopy formwork joint',p,q,.10,.08,STEEL,(.57,.58,.53),True)
        a=(i+.5)*math.tau/12
        for z in (10,19):
            r=1.045-(z-4)*.075/19
            ellipse_section('buttress cast lift joint',rx,ry,
                            [(r,z-.05),(r+.0014,z-.05),(r+.0014,z+.05),(r,z+.05)],
                            a-.084,a+.084,2,STEEL,(.56,.57,.52))['detail']=True
    guardrail('scoreboard service rail',(-23,61.2,37.5),(23,61.2,37.5))
    maintenance_ladder((24.3,66,0),(0,1,0),18,39.2)
    for end in (-1,1):
        for x in (-9,9):
            guardrail('arena entry handrail',(x,end*112.5,.2),(x,end*100,1.2),2.9)
        marking('02' if end>0 else '01',(7 if end<0 else -7,end*101.7,4),
                (1,0,0) if end<0 else (-1,0,0),1.2)


def church():
    global NAME
    NAME='civic-church'
    shared.fresh('Civic church')
    # Structural solids are unchanged from the checkpoint.
    nave=rect(-17,17,-49,44)
    helper('nave',nave,36)
    wall_shell('nave lower wall',nave,27)
    for side in (-1,1):
        aisle=rect(side*17,side*31,-49,44)
        helper('aisle',aisle,18)
        wall_shell('aisle wall',aisle,18)
        x0,x1=sorted((side*17,side*31))
        prism('aisle flat roof',rect(x0+.2,x1-.2,-48.8,43.8),16.8,18.15,CONCRETE,CREAM)
        # Four broad, stepped wall piers carry the nave canopy.
        for y in (-34,-9,16,41):
            profile=[(side*16,0),(side*35,0),(side*35,29),
                     (side*23,29),(side*23,35),(side*16,35)]
            p=prism('monolithic aisle pier',profile,-4.4,4.4,CONCRETE,CREAM)
            p.matrix_world=Matrix.Translation((0,y,0))@Matrix.Rotation(math.pi/2,4,'X')
            painted(p)
            concrete_box('pier footing',(side*31,y,1.4),(8.4,9,2.8),False,(.792,.804,.767))
            painted(box('pier recessed armor',(side*35.05,y,8),( .18,4,9),PAINT,TEAL))
        # Openings are several units behind the outer piers, under deep lintels.
        for y in (-21.5,3.5,28.5):
            u=(0,side,0)
            vertical_panel('aisle recessed dark glazing',rect(-7.7,7.7,0,5.4),
                           (side*31.04,y,4.1),u,GLASS,(.56,.60,.59),.16)
            for offset in (-5,0,5):
                # Between the mullions, not across them.
                if offset<5:vertical_panel('aisle amber light',rect(-1.3,1.3,0,1),
                                           (side*31.15,y+offset+2.5,5),u,PAINT,GOLD,.12)
                beam('aisle window mullion',(side*31.3,y+offset,4),
                     (side*31.3,y+offset,9.7),.38,.38,STEEL,DARK)
            painted(box('aisle opaque spandrel',(side*31.3,y,13.4),
                        (1,15.5,7.2),PAINT,TEAL))
            concrete_box('aisle deep lintel',(side*32.4,y,18),
                         (4.7,16,2.4),False)
            vertical_panel('clerestory recessed glass',rect(-7.8,7.8,0,4.4),
                           (side*17,y,27.1),u,GLASS,(.45,.52,.53),.2)
            concrete_box('clerestory lintel',(side*18,y,33.2),(5,16,3.6),False)
        for y in (-46,-34,-9,16,41):
            concrete_box('clerestory structural pier',(side*17,y,30),(3,9,8))
        concrete_box('clerestory blind infill',(side*17,-40,29.5),(1.2,3.6,5),False)
        # Low utility slots stay subordinate to the structural bays.
        vertical_panel('rear service grille',rect(-3.4,3.4,0,4),
                       (side*31.1,37,3),(0,side,0),GRILLE,(.60,.63,.61),.2)
    # Flat, cantilevered concrete roof; stepped plant spine replaces the gable.
    concrete_box('nave deep roof',(0,-1.5,34.5),(44,94,5),False)
    concrete_box('nave upper roof step',(0,-1.5,37.5),(34,91,2),False,(.943,.943,.88))
    for y0,y1 in ((-38,-15),(-12,12),(15,40)):
        concrete_box('raised axial roof spine',(0,(y0+y1)/2,41),(17,y1-y0,7),False)
        for side in (-1,1):
            vertical_panel('axial spine recessed cooling',rect(-(y1-y0-3)/2,(y1-y0-3)/2,0,3.4),
                           (side*8.52,(y0+y1)/2,39),(0,side,0),GRILLE,(.43,.47,.46),.12)
        box('spine expansion joint',(0,(y0+y1)/2,44.55),(.16,y1-y0,.10),STEEL,DARK,True)
    # Rear apse keeps the original two-level envelope, finished with stepped caps.
    apse=[(-17,39),(17,39),(19,48),(14,59),(0,65),(-14,59),(-19,48)]
    # Its volume starts where the nave's ends: the apse wall slants out past the nave's line before y 44.
    helper('apse',[(-17,44),(17,44)]+apse[2:],36)
    wall_shell('apse wall',apse,36)
    prism('apse concrete roof',inset_outline(apse,.2),33.5,36.15,CONCRETE,CREAM)
    prism('apse upper blind cap',inset_outline(apse,2.5),36,39,CONCRETE,(.943,.943,.88))
    for i in (1,2,3,4,5):
        a,b=Vector(apse[i]),Vector(apse[(i+1)%len(apse)])
        t=(b-a).normalized();n=Vector((t.y,-t.x));mid=(a+b)/2
        vertical_panel('apse recessed light slot',rect(-2.6,2.6,0,13),
                       (*tuple(mid+n*.04),9),(*t,0),STEEL,DARK,.15)
        vertical_panel('apse amber glass',rect(-.42,.42,0,10),
                       (*tuple(mid+n*.14),10.5),(*t,0),PAINT,GOLD,.12)
    # No front wall across the portal: the tower has actual deep jambs and reveals.
    tower=rect(-12,12,-64,-39)
    # Inside the side walls (x 10..12): a floor reaching their outer faces flickered on them.
    helper('tower',rect(-10,10,-64,-39),54)
    for side in (-1,1):
        concrete_box('tower side wall',(side*11,-51.5,27),(2,25,54))
        height=79 if side<0 else 56
        concrete_box('tower monumental front pier',(side*11.2,-62,height/2),(9.6,8,height))
        painted(box('tower side blind armor',(side*12.1,-49,32),(.3,14,27),PAINT,TEAL))
        concrete_box('tower outer shoulder',(side*16.5,-54,22),(5,19,44))
        concrete_box('tower shoulder infill',(side*13,-54,22),(2,19,44))
        concrete_box('tower rear pocket infill',(side*14.5,-38,46.25),(5,5,15.5),False)
    concrete_box('tower rear wall',(0,-40,27),(24,2,54))
    concrete_box('tower structural roof',(0,-51.5,53),(24,25,2),False)
    # Recessed light well has a dark back and thick concrete on either side.
    box('light well back',(0,-57.8,38),(13,.6,38),STEEL,DARK)
    for side in (-1,1):
        concrete_box('light well inner return',(side*5.4,-60.3,38),(1.3,5,37),False,(.83,.842,.792))
    vertical_panel('tower vertical amber slot',rect(-.85,.85,0,33),(0,-58.25,21),
                   material=PAINT,colour=GOLD,thickness=.2)
    for z in (27,36,45):
        box('light well transom',(0,-58.5,z),(2.1,.4,.35),STEEL,DARK,True)
    # Crown is blind roof architecture. The only tower gameplay top remains54.
    concrete_box('tower crown lower cantilever',(0,-51.5,56),(34,32,4),False)
    concrete_box('tower crown shadow core',(2,-49.5,62),(18,20,8),False,(.654,.704,.679))
    concrete_box('tower crown upper cantilever',(2,-49.5,67.5),(26,25,3),False)
    concrete_box('tower crown rear anchor',(-11,-40,68.8),(9,8,21.6))
    concrete_box('tower crown bridge',(-2,-53,78.5),(28,25,3),False)
    for side in (-1,1):
        vertical_panel('crown recessed aperture',rect(-7,7,0,1.2),
                       (2+side*9.05,-49.5,62),(0,side,0),PAINT,GOLD,.12)
    # Recessed monumental portal, connected to the tower, within old approach bounds.
    for side in (-1,1):
        concrete_box('portal jamb',(side*10.7,-65.5,8),(4.5,9,16))
        box('portal steel return',(side*8.15,-65,8),( .5,8,15),STEEL,DARK)
    concrete_box('portal massive lintel',(0,-65.5,18),(26,9,4),False)
    box('sanctuary portal shadow back',(0,-61.5,8),(16,.6,16),STEEL,DARK)
    for x in (-2.4,2.4):personnel_door('sanctuary entry',(x,-61.9,1.5))
    stairs('entry stair',0,-73,-62,20,1.5,3)
    utility_light((0,-70.1,18),9)
    # Cast joints are local shallow relief, never hex placement markings.
    for y in (-34,-9,16,41):
        for side in (-1,1):
            for z in (10,20):
                box('concrete pour joint',(side*35.05,y,z),(.10,8.7,.10),STEEL,(.49,.51,.48),True)
    personnel_door('apse service entry',(7.03,62.06,0),(-.919,.394,0))
    church_scale_details()
    for o in shared.objects+shared.volumes:o.location.y+=36
    return finish_scene()


def utility_light(center, width=2.5, horizontal=(1,0,0)):
    u=Vector(horizontal);n=u.cross(Vector((0,0,1)))
    vertical_panel('utility lamp housing',rect(-width/2-.35,width/2+.35,-.4,.5),center,u,STEEL,DARK,.8)
    vertical_panel('amber lamp lens',rect(-width/2,width/2,-.1,.2),Vector(center)+n*.48,u,PAINT,GOLD,.2)


def superellipse(angle, power):
    c,s=math.cos(angle),math.sin(angle)
    r=(abs(c)**power+abs(s)**power)**(-1/power)
    return c*r,s*r


def arc_table(samples=1440):
    """Running length around the 69 x 99 arena outline, so that its bays stay even along it."""
    points=[superellipse(i*math.tau/samples,ARENA_POWER) for i in range(samples+1)]
    lengths=[0.]
    for a,b in zip(points,points[1:]):
        lengths.append(lengths[-1]+math.hypot(69*(b[0]-a[0]),99*(b[1]-a[1])))
    return lengths


ARC_LENGTHS=arc_table()


def oval(angle, power=ARENA_POWER):
    """A point of the arena's unit outline, a rounded rectangle, at a fraction angle/tau of its length; power 2 is a circle."""
    if power==2:
        return math.cos(angle),math.sin(angle)
    target=(angle%math.tau)/math.tau*ARC_LENGTHS[-1]
    i=min(bisect.bisect_right(ARC_LENGTHS,target),len(ARC_LENGTHS)-1)
    span=ARC_LENGTHS[i]-ARC_LENGTHS[i-1]
    return superellipse((i-1+(target-ARC_LENGTHS[i-1])/span)*math.tau/(len(ARC_LENGTHS)-1),power)


def ellipse_ring(name, rx, ry, profile, material=PAINT, colour=LIGHT,
                 segments=64, helper_only=False, smooth=False, tint=False, detail=False, power=ARENA_POWER):
    # Closed cross section swept around an ellipse; empty interior is preserved.
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(profile,profile[1:]+profile[:1]))<0:
        profile=list(reversed(profile))
    verts=[(rx*r*oval(i*math.tau/segments,power)[0],ry*r*oval(i*math.tau/segments,power)[1],z)
           for r,z in profile for i in range(segments)]
    faces=[]
    for j in range(len(profile)):
        k=(j+1)%len(profile)
        for i in range(segments):
            n=(i+1)%segments
            faces.append((j*segments+i,j*segments+n,k*segments+n,k*segments+i))
    o=mesh(name,verts,faces,material,colour,detail,helper_only)
    o['ring_segments']=segments
    o['ring_profile_points']=len(profile)
    if smooth:
        for p in o.data.polygons:p.use_smooth=True
    if tint:painted(o)
    return o


def ellipse_section(name, rx, ry, profile, start, end, segments=6,
                    material=CONCRETE, colour=CREAM, tint=False):
    """Closed annular sector, including its underside and both radial end caps."""
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(profile,profile[1:]+profile[:1]))<0:
        profile=list(reversed(profile))
    count=segments+1
    verts=[(rx*r*oval(start+(end-start)*i/segments)[0],
            ry*r*oval(start+(end-start)*i/segments)[1],z)
           for r,z in profile for i in range(count)]
    faces=[]
    for j in range(len(profile)):
        k=(j+1)%len(profile)
        for i in range(segments):
            faces.append((j*count+i,j*count+i+1,k*count+i+1,k*count+i))
    faces.append(tuple(j*count for j in range(len(profile))))
    faces.append(tuple(reversed([j*count+segments for j in range(len(profile))])))
    obj=mesh(name,verts,faces,material,colour)
    obj['section_segments']=segments
    obj['section_profile_points']=len(profile)
    if tint:painted(obj)
    return obj


def arena():
    global NAME
    NAME='civic-arena'
    shared.fresh('Civic arena')
    rx,ry=69,99
    ellipse_ring('building_volume concourse',rx,ry,[(.48,0),(1,0),(1,18),(.48,18)],
                 shared.FLAT,(.3,.8,.65),48,True)
    # The solid base blocks grass; eight notches let the bowl stairs reach the 18-unit concourse.
    # The continuous outer landing and lower core keep the notches closed underneath.
    ellipse_ring('closed seating concourse',rx,ry,
                 [(.65,-.1),(.967,-.1),(.967,18),(.726,18),(.726,14.35),(.65,14.35)],
                 CONCRETE,(.798,.825,.771))
    for bay in range(8):
        # Overlap the landing: the ring and these sectors use different angular samples in each LOD.
        ellipse_section('concourse between access flights',rx,ry,
                        [(.65,14.3),(.733,14.3),(.733,18),(.65,18)],
                        (bay+.5)*math.tau/8+.026,(bay+1.5)*math.tau/8-.026,6,
                        CONCRETE,(.798,.825,.771))
    ellipse_ring('heavy concrete podium',rx,ry,[(.94,0),(1,0),(1,10),(.94,10)],
                 CONCRETE,CREAM,tint=True)
    ellipse_ring('podium foundation course',rx,ry,[(.94,0),(1.02,0),(1.02,2.6),(.94,2.6)],
                 CONCRETE,(.851,.865,.811))
    # A narrow dark gallery sits far behind the roof edge and opaque outer piers.
    ellipse_ring('recessed gallery backing',rx,ry,[(.89,17.8),(.92,17.8),(.92,29),(.89,29)],
                 STEEL,DARK)
    ellipse_ring('gallery narrow glazing',rx,ry,[(.921,20),(.924,20),(.924,23),(.921,23)],
                 GLASS,(.48,.54,.52))
    ellipse_ring('deep canopy structural soffit',rx,ry,
                 [(.635,28),(.98,28),(1.014,31),(1.014,34),(.635,34)],
                 CONCRETE,(.931,.944,.878))
    # Twelve broad roof blocks, separated by shallow joints over a continuous slab.
    for i in range(12):
        a0=i*math.tau/12+.007;a1=(i+1)*math.tau/12-.007
        profile=[(.64,32),(.64,36),(.77,36),(.80,38),(1.02,36),(1.02,31),(.92,31)]
        ellipse_section('stepped concrete canopy block',rx,ry,profile,a0,a1,6,
                        colour=CREAM if i%3 else (1,1,.958))
        ellipse_section('canopy upper terrace',rx,ry,
                        [(.80,37.6),(.80,41.8),(.97,40),(.97,35.8)],
                        a0+.014,a1-.014,6,colour=(.984,.998,.931))
        # Recessed opaque spandrels replace the blue window ribbon.
        ellipse_section('angled concourse armor',rx,ry,
                        [(.967,8),(.997,8),(.975,17),(.955,17)],
                        a0+.08,a1-.08,6,PAINT,TEAL,True)
        for fraction in (.359,.665,.971):
            a=a0+(a1-a0)*fraction
            p=Vector((rx*.926*oval(a)[0],ry*.926*oval(a)[1],21))
            tangent=Vector((rx*(oval(a+.01)[0]-oval(a-.01)[0]),ry*(oval(a+.01)[1]-oval(a-.01)[1]),0)).normalized()
            vertical_panel('gallery amber aperture',rect(-1.7,1.7,0,1),p,tangent,PAINT,GOLD,.18)
    # Integral broad piers carry the entire canopy; no thin exoskeleton cage.
    for i in range(12):
        a=(i+.5)*math.tau/12
        ellipse_section('broad tapered concrete buttress',rx,ry,
                        [(.88,0),(1.045,0),(1.045,4),(.97,23),(.97,32),(.88,32)],
                        a-.085,a+.085,2,CONCRETE,CREAM,True)
        ellipse_section('buttress foot block',rx,ry,
                        [(.9,0),(1.05,0),(1.05,2),(.9,2)],
                        a-.09,a+.09,2,CONCRETE,(.865,.878,.825))
    # Retain colored seating in both LODs and the open central field.
    for row in range(8):
        r0=.48+row*.022;r1=r0+.022;z=3+row*1.5
        for bay in range(8):
            start=(bay+.5)*math.tau/8+.025
            end=(bay+1.5)*math.tau/8-.025
            ellipse_section('seating tier',rx,ry,
                            [(r0,z-1.5),(r1,z-1.5),(r1,z),(r0,z)],
                            start,end,6,CONCRETE,(.732,.758,.718))
            ellipse_section('seat row',rx,ry,
                            [(r0+.002,z),(r1-.002,z),(r1-.002,z+.7),(r0+.002,z+.7)],
                            start,end,6,PAINT,(.32,.39,.40))
            # Keep the last backrest clear of the closed concourse wall.
            back=min(r1-.002,.647)
            ellipse_section('seat back',rx,ry,
                            [(back-.004,z+.7),(back,z+.7),(back,z+2),(back-.004,z+2)],
                            start,end,6,PAINT,(.32,.39,.40))
        #Half-metre seat divisions are surface markings, not another ring of solids.
        divisions=round(math.tau*math.sqrt((rx*rx+ry*ry)/2)*(r0+r1)/2/1.5)
        vertices=[];faces=[]
        for seat in range(divisions):
            a=seat*math.tau/divisions;w=.024/(rx*(r0+r1)/2)
            if abs(a%(math.tau/8)-math.tau/16)<.027:continue
            base=len(vertices)
            vertices += [(rx*r*oval(t)[0],ry*r*oval(t)[1],z+.74)
                         for r,t in ((r0+.004,a-w),(r1-.004,a-w),
                                     (r1-.004,a+w),(r0+.004,a+w))]
            faces.append(tuple(base+j for j in range(4)))
        obj=mesh('seat division markings',vertices,faces,PAINT,(.44,.49,.47),detail=True)
        obj['surface_detail']=True
    ellipse_ring('field retaining wall',rx,ry,[(.465,0),(.48,0),(.48,3.4),(.465,3.4)],
                 CONCRETE,(.838,.865,.811))
    # Bowl circulation stairs break up the rings at sensible radial intervals.
    for i in range(8):
        a=(i+.5)*math.tau/8
        for row in range(8):
            for step in range(3):
                r0=.48+(row+step/3)*.022;r1=r0+.022/3+.001
                z=3+(row-1)*1.5+(step+1)*.5
                ellipse_section('seating access stair',rx,ry,
                                [(r0,z-.2),(r1,z-.2),(r1,z+.85),(r0,z+.85)],
                                a-.023,a+.023,1,CONCRETE,(.891,.918,.865))
        # Aisle rails are structural scale cues, kept in both LODs.
        guardrail('bowl aisle rail',
                  (rx*.485*oval(a)[0],ry*.485*oval(a)[1],2.85),
                  (rx*.645*oval(a)[0],ry*.645*oval(a)[1],14.35),3)
        # Seven ordinary 17 cm risers continue through the notch to a level landing.
        for step in range(7):
            r0=.656+step*.01;r1=r0+.0105
            top=14.35+(18-14.35)*(step+1)/7+.02
            ellipse_section('upper concourse access stair',rx,ry,
                            [(r0,14.3),(r1,14.3),(r1,top),(r0,top)],
                            a-.023,a+.023,1,CONCRETE,(.891,.918,.865))
        guardrail('concourse access rail',
                  (rx*.645*oval(a)[0],ry*.645*oval(a)[1],14.35),
                  (rx*.738*oval(a)[0],ry*.738*oval(a)[1],18.02),3,start_post=False)
    # Deep front and rear portal. Gameplay pavilion outlines remain identical.
    for end in (-1,1):
        before=len(shared.objects);before_vol=len(shared.volumes)
        footprint=rect(-16,16,-108,-86)
        helper('entry pavilion',footprint,18)
        # Closed back at the recessed door, real open tunnel in front of it.
        concrete_box('entry rear wall',(0,-87,9),(32,2,18))
        for side in (-1,1):
            concrete_box('entry monolithic jamb',(side*13.7,-98,8),(4.6,21,16))
            box('portal inset return',(side*11.2,-101,8),( .5,13,15),STEEL,DARK)
        concrete_box('entry deep concrete lintel',(0,-98,18.5),(32,21,5),False)
        concrete_box('entry upper step',(0,-95,22),(29,14,2),False,(.998,1,.931))
        box('arena portal shadow back',(0,-100.5,8),(22,.6,16),STEEL,DARK)
        for x in (-5,0,5):personnel_door('arena entry',(x,-101,1.2))
        stairs('arena entrance',0,-113,-98,25,1.2,3)
        utility_light((0,-108.6,18),11)
        if end>0:
            rotation=Matrix.Rotation(math.pi,4,'Z')
            for o in shared.objects[before:]+shared.volumes[before_vol:]:o.matrix_world=rotation@o.matrix_world
    # Low, broad scoreboard replaces the fins: a distinct brutalist silhouette.
    # This is blind equipment above the concourse, not another occupied storey.
    for side in (-1,1):
        concrete_box('scoreboard load bearing pier',(side*20,77,28),(8,24,20))
        concrete_box('scoreboard deep side reveal',(side*21.5,78,43.5),(4,21.5,10),False)
    concrete_box('scoreboard rear enclosure',(0,82,44.5),(43,13,15),False)
    concrete_box('scoreboard service deck',(0,64,36),(52,5,3),False)
    concrete_box('scoreboard lower sill',(0,78,37.5),(47,21.5,3),False)
    concrete_box('scoreboard massive lintel',(0,78,50),(47,21.5,4),False)
    concrete_box('scoreboard overhanging roof',(0,78,52),(50,25,3),False)
    vertical_panel('scoreboard recessed display',rect(-19,19,0,9),(0,70.4,38.5),
                   material=STEEL,colour=(.19,.24,.24),thickness=.3)
    marking('00 : 00',(-10.6,70.2,40.6),size=4.2)['detail']=False
    vertical_panel('scoreboard rear radiator',rect(-15,15,0,5),(0,88.6,40),(-1,0,0),
                   GRILLE,(.45,.50,.48),.25)
    for a in (0,math.pi):
        point=Vector((rx*1.024*oval(a)[0],0,0))
        # A plain door block carries the door out past the podium's foundation course.
        concrete_box('podium door block',(rx*.994*oval(a)[0],0,4.5),(4.4,10,9),False)
        tangent=Vector((0,math.cos(a),0))
        vertical_panel('podium service door',rect(-3.6,3.6,0,7.6),point,tangent,STEEL,DARK,.25)
        utility_light(point+Vector((0,0,8.3)),4,tangent)
    arena_scale_details(rx,ry)
    arena_floor()
    from civic_night_lighting import floodlights
    floodlights()
    return finish_scene()


def arena_floor():
    """Closed ground-level playing deck; the structural helpers still describe the occupied concourse only."""
    if bpy.context.scene.get('arena_floor'):return
    apron=[(69*.491*oval(i*math.tau/64)[0],99*.491*oval(i*math.tau/64)[1]) for i in range(64)]
    prism('arena sealed floor and apron',apron,-.25,1.2,CONCRETE,(.678,.718,.705))
    playing=[(69*.44*oval(i*math.tau/64)[0],99*.44*oval(i*math.tau/64)[1]) for i in range(64)]
    prism('arena green playing surface',playing,1.18,1.26,CONCRETE,(.399,.585,.505))
    # Hard-wearing painted sports lines, set above the slab rather than coplanar with it.
    ink=(1,1,1)
    def line(name,a,b,width=.3):
        a=Vector((*a,1.29));b=Vector((*b,1.29))
        beam('arena field '+name,a,b,width,.045,CONCRETE,ink)
    for x in (-19,19):line('touchline',(x,-28),(x,28))
    for y in (-28,28):line('end line',(-19,y),(19,y))
    line('halfway',(-19,0),(19,0))
    ellipse_ring('arena centre circle',6.4,6.4,[(.95,1.27),(1,1.27),(1,1.32),(.95,1.32)],
                 CONCRETE,ink,segments=48,power=2)
    for side in (-1,1):
        line('end zone',(-7,side*21),(7,side*21))
        for x in (-7,7):line('end zone side',(x,side*21),(x,side*28))
    # The concrete service apron meets the first row's underside, with flush drainage slots.
    for i in range(12):
        a=math.tau*(i+.5)/12
        c=Vector((69*.451*oval(a)[0],99*.451*oval(a)[1],1.235))
        drain=box('arena apron drain',(0,0,0),(2.1,.65,.06),GRILLE,DARK)
        drain.matrix_world=Matrix.Translation(c)@Matrix.Rotation(a+math.pi/2,4,'Z')
    bpy.context.scene['arena_floor']=True
    for obj in shared.objects:
        if obj.name.startswith('arena '):shared.project_uvs(obj)


def apply_lights():
    lamps=0
    for obj in shared.objects:
        if obj.name.startswith('bowl floodlight lens'):continue
        if obj.get('building_emission_off',False):continue
        emission=None
        night=True
        window=(obj['board_material']==GLASS or obj.name.startswith((
            'apse amber glass','tower vertical amber slot','crown recessed aperture',
            'aisle amber light','gallery amber aperture')))
        if window:
            # Match the tower's cool daytime glass; its warm interior light is a night-only finish.
            obj['board_material']=GLASS
            obj['pigment']=(.84,.94,.96)
            emission=tuple(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055 for v in (.32,.21,.055))
        if obj['board_material']==PAINT and all(abs(a-b)<1e-5 for a,b in zip(obj['pigment'],GOLD)):
            emission=(1,.72,.35)
        if obj.name.startswith('access marking 00 : 00'):
            emission=(.75,.88,1)
            night=False
        if emission is None:continue
        shared.emissive(obj,emission,night=night);lamps+=1
    return lamps


def finish_scene():
    scene=bpy.context.scene
    scene.unit_settings.system='NONE'
    scene['hex_width']=83.125;scene['hex_height']=72;scene['level_height']=18
    scene['hex_metres']=30;scene['level_metres']=6
    scene['concept']=str(HERE/'references'/('church-concept.png' if NAME=='civic-church' else 'arena-concept.png'))
    scene['refinement']=str(HERE/'references/civic-brutalist-massing-preview-v2.png')
    scene['asset_id']='buildings/authored/'+NAME
    for o in shared.volumes:o.hide_set(True)
    bpy.context.view_layer.update()
    apply_lights()
    for o in shared.objects:shared.project_uvs(o)
    verts=[o.matrix_world@v.co for o in shared.objects for v in o.data.vertices]
    bounds=[[round(min(v[i] for v in verts),3),round(max(v[i] for v in verts),3)] for i in range(3)]
    scene['bounds']=json.dumps(bounds)
    # Make the active live Blender viewport useful immediately.
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_location=(0,36 if NAME=='civic-church' else 0,22)
            area.spaces.active.region_3d.view_distance=260 if NAME=='civic-arena' else 180
            area.spaces.active.region_3d.view_rotation=Vector((1,-1,.85)).to_track_quat('Z','Y')
            area.spaces.active.shading.type='MATERIAL'
    return {'asset':NAME,'objects':len(shared.objects),'helpers':len(shared.volumes),'bounds':bounds}


def plain_arena():
    """The arena's LOD2: its oval as bare surfaces from the foot to the field, portals and scoreboard as plain blocks.

    The roof stands at the top of the blocks it replaces: the shadow map picks its casters' level by its own texel, and a
    finer block above this surface would shade it.
    """
    roof,inner=(.984,.998,.931),(.798,.825,.771)
    stations=[(1.03,0,None),(1,12,(CONCRETE,CREAM,True)),(.97,18,(CONCRETE,CREAM,True)),(.97,30,(PAINT,(.66,.69,.67),False)),
              (1.03,36,(CONCRETE,CREAM,False)),(.97,42,(CONCRETE,CREAM,False)),(.8,42,(CONCRETE,roof,False)),(.64,36.2,(CONCRETE,roof,False)),(.64,18,(CONCRETE,inner,False)),
              (.48,3,(PAINT,(.20,.24,.25),False)),(.44,1.3,(CONCRETE,(.838,.865,.811),False)),(0,1.3,(CONCRETE,(.399,.585,.505),False))]
    around=lambda a:(69*oval(a)[0],99*oval(a)[1])
    for verts,faces,(key,colour,tint) in building_lod.lathe(stations,20,around):
        obj=mesh('plain arena',verts,faces,key,colour)
        obj['building_paint']=tint
        for face in obj.data.polygons:face.use_smooth=len(faces)>1
    glazing=next(o for o in shared.objects if o.name.startswith('gallery narrow glazing'))
    for verts,faces,_ in building_lod.lathe([(.975,20,None),(.975,23,True)],20,around):
        shared.emissive(mesh('plain gallery',verts,faces,GLASS,tuple(glazing['pigment'])),tuple(glazing['building_emission']),night=bool(glazing['building_night_emission']))
    for end in (-1,1):
        concrete_box('plain portal',(0,end*97,11.5),(32,22,23))
    concrete_box('plain scoreboard',(0,78,35.75),(50,25,35.5),False)
    box('plain scoreboard display',(0,65.3,43),(38,.4,9),STEEL,(.19,.24,.24))


def export():
    bpy.context.view_layer.update()
    levels={i:shared.export_model(shared.objects,NAME+'-lod'+str(i),level=i) for i in (0,1)}
    if NAME=='civic-arena':
        plain=shared.temporary(plain_arena)
        levels[2]=shared.export_model(plain,NAME+'-lod2',level=2,exact=True)
        shared.discard(plain)
    else:
        levels[2]=shared.export_model(shared.objects,NAME+'-lod2',level=2)
    helpers=shared.export_model(shared.volumes,NAME,helper=True)
    stats={i:{'vertices':sum(len(m['vertices'])//12 for m in level['meshes']),
              'triangles':sum(len(p['indices'])//3 for m in level['meshes'] for p in m['parts'])}
           for i,level in levels.items()}
    assert max(s['vertices'] for s in stats.values())<65535,stats
    from civic_night_lighting import light_extras
    write_glb(shared.DEST/(NAME+'.glb'),levels=levels,groups={'building_volumes':helpers},
              extras=light_extras(bpy.context.scene))
    bpy.data.libraries.write(str(shared.SOURCE/(NAME+'.blend')),{bpy.context.scene},fake_user=True)
    return stats


def studio(view='isometric', size=1000):
    scene=bpy.context.scene
    collection=scene.collection.children.get('Civic review studio '+NAME)
    if not collection:
        orphan=bpy.data.collections.get('Civic review studio '+NAME)
        if orphan and orphan.users==0:bpy.data.collections.remove(orphan)
        collection=bpy.data.collections.new('Civic review studio '+NAME)
        scene.collection.children.link(collection)
        camera=bpy.data.objects.new('Review camera',bpy.data.cameras.new('Review camera'))
        collection.objects.link(camera);scene.camera=camera
        for loc,power,scale in [((100,-170,230),320000,180),((-160,-40,110),170000,140),((40,180,150),240000,130)]:
            light=bpy.data.objects.new('Studio softbox',bpy.data.lights.new('Studio softbox','AREA'))
            collection.objects.link(light);light.location=loc;light.data.energy=power;light.data.shape='DISK';light.data.size=scale
            light.rotation_euler=(Vector((0,0,25))-light.location).to_track_quat('-Z','Y').to_euler()
        ground=bpy.data.meshes.new('Studio ground');ground.from_pydata([(-500,-500,-.3),(500,-500,-.3),(500,500,-.3),(-500,500,-.3)],[],[(0,1,2,3)])
        obj=bpy.data.objects.new('Studio ground',ground);collection.objects.link(obj)
        obj.data.materials.append(shared.material(shared.FLAT,(.18,.21,.23)))
    camera=scene.camera
    target=Vector((0,36 if NAME=='civic-church' else 0,26 if NAME=='civic-church' else 24))
    positions={'isometric':(190,-240,180),'front':(0,-300,26),'back':(0,300,26),
               'left':(-300,0,26),'right':(300,0,26),'top':(0,0,350)}
    camera.location=Vector(positions[view])+Vector((0,target.y,0))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=245 if NAME=='civic-arena' else 169
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.resolution_x=size;scene.render.resolution_y=size;scene.render.resolution_percentage=100
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.22,.25,.29,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.7
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=.8
    scene.render.image_settings.file_format='PNG'
    path=shared.SOURCE/(NAME+'-'+view+'.png');scene.render.filepath=str(path)
    return str(path)
