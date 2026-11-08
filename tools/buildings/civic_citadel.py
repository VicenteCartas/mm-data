"""Fourteen-level civic citadel, authored in the connected Blender MCP instance.

The compact three-bay podium and vertical shaft follow references/citadel-concept-v2.png.
One gameplay level is 18 model units (6m); all occupied sections have closed helpers.
The glazed shoulder bays, rooftop machinery and antennae do not add floors.
"""
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

import authored_examples as shared
import civic_buildings as civic
from glb_geometry import display, write_glb
from hpg_headquarters import mesh, box, prism, beam, cylinder, outline_band

NAME = 'civic-citadel'
SCENE = 'Civic citadel'
HERE = Path(__file__).resolve().parent
CONCRETE = shared.CONCRETE
STEEL = shared.STEEL
PAINT = civic.PAINT
GLASS = civic.GLASS
GRILLE = civic.GRILLE
STONE = (1, .99, .93)
EDGE = (.87, .87, .81)
DARK = (.28, .32, .32)
ALLOY = (.64, .68, .66)
GLAZING = (.84, .94, .96)
WINDOW_LIGHT = tuple(display(c) for c in (.32, .21, .055))
HEX_WIDTH = 83.125
FACADE_RIBS = tuple(range(-35,36,10))


def concrete(name, center, size, tint=False, colour=STONE):
    obj = box(name, center, size, CONCRETE, colour)
    if tint:
        obj['building_paint'] = True
    return obj


def shell(name, outline, top, tint=True, bottom=0, thickness=1.4, roof=True):
    wall_top = top-1.5 if roof else top
    obj = outline_band(name+' walls', outline, (bottom+wall_top)/2, wall_top-bottom,
                       thickness, -thickness/2, key=CONCRETE, colour=STONE)
    if tint:
        obj['building_paint'] = True
    if roof:
        prism(name+' roof', outline, top-1.5, top, CONCRETE, EDGE)
    return obj


def helper(name, outline, top):
    return prism('building_volume '+name, outline, 0, top, shared.FLAT,
                 (.3, .8, .65), helper=True)


def lamp(name, center, width=2.1, height=.4, horizontal=(1,0,0), colour=(1,.72,.35)):
    u = Vector(horizontal).normalized()
    normal = u.cross(Vector((0,0,1)))
    civic.vertical_panel(name+' housing', civic.rect(-width/2-.22,width/2+.22,-.22,height+.22),
                         center, u, STEEL, DARK, .45)
    face = civic.vertical_panel(name+' lens', civic.rect(-width/2,width/2,0,height),
                                Vector(center)+normal*.28, u, PAINT, (.85,.78,.60), .10)
    return shared.emissive(face, colour)


def side_prism(name, profile, lo, hi, axis='X', material=CONCRETE, colour=STONE):
    """Extrude a Y/Z or X/Z section, with the caps and winding kept by prism()."""
    obj = prism(name, profile, lo if axis == 'X' else -hi, hi if axis == 'X' else -lo, material, colour)
    if axis == 'X':
        obj.matrix_world = Matrix(((0,0,1,0),(1,0,0,0),(0,1,0,0),(0,0,0,1)))
    else:
        obj.matrix_world = Matrix(((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1)))
    return obj


def sloped_panel(name, start, end, width, horizontal, material=GRILLE, colour=DARK):
    """A closed slab parallel to the shoulder, with a small physical separation."""
    a,b = Vector(start),Vector(end)
    u = Vector(horizontal).normalized()
    v = (b-a).normalized()
    normal = u.cross(v).normalized()
    if normal.z < 0:
        u = -u
        normal = -normal
    obj = box(name, (0,0,0), (width,(b-a).length,.35),material,colour)
    frame = Matrix.Translation((a+b)/2+normal*.3) @ Matrix((
        (u.x,v.x,normal.x,0),(u.y,v.y,normal.y,0),(u.z,v.z,normal.z,0),(0,0,0,1)))
    # Bake the basis into the mesh: an object's rotation/scale cannot retain a sheared slab.
    obj.data.transform(frame)
    return obj, frame


def sloped_window(name, start, end, width, horizontal, columns=2, rows=5):
    glass, frame = sloped_panel(name+' glass', start, end, width, horizontal, GLASS, GLAZING)
    shared.emissive(glass, WINDOW_LIGHT, night=True)
    length = (Vector(end)-Vector(start)).length
    for i in range(columns+1):
        x = -width/2+width*i/columns
        beam(name+' mullion', frame@Vector((x,-length/2,.22)),
             frame@Vector((x,length/2,.22)), .42, .42, STEEL, ALLOY)
    for i in range(rows+1):
        y = -length/2+length*i/rows
        beam(name+' transom', frame@Vector((-width/2,y,.26)),
             frame@Vector((width/2,y,.26)), .36, .36, STEEL, ALLOY)
    return glass


def facade_windows(side):
    # Twenty-two roughly3m rows retain human scale within the84m envelope.
    y = -28.08 if side < 0 else 38.08
    horizontal = (1,0,0) if side < 0 else (-1,0,0)
    for bay,x in enumerate((-30,-20,-10,0,10,20,30)):
        bottom = 216 if side > 0 and abs(x) < 28 else 94 if side < 0 else 58
        civic.vertical_panel('recessed window channel',civic.rect(-3.9,3.9,0,249-bottom),
                             (x,y,bottom),horizontal,STEEL,DARK,.45)
        for row in range(22):
            z = 61+row*8.7
            if z+4.8 < bottom:
                continue
            glass = civic.vertical_panel('office glazing',civic.rect(-2.75,2.75,0,4.8),
                                         (x,y+side*.32,z),horizontal,GLASS,GLAZING,.14)
            # Selected occupied windows glow only after dusk; the daytime glass stays cool.
            if (row*7+bay*3+(side>0))%9 in (0,3):
                shared.emissive(glass,WINDOW_LIGHT,night=True)
            else:
                shared.emission_off(glass)
            box('window sill',(x,y+side*.48,z-.12),(6.7,.45,.35),STEEL,ALLOY,True)
            box('window divider',(x,y+side*.47,z+2.4),(.13,.2,4.8),STEEL,DARK,True)
        for z in (90,126,162,198,234):
            box('deep channel service cover',(x,y+side*.48,z),(6.7,.45,1.7),PAINT,(.42,.45,.42),True)


def tower():
    plan = civic.rect(-36,36,-28,38)
    # Behind its back wall (1.4 thick), which stands against the rear annex's: neither volume reaches the other's wall.
    helper('main shaft',civic.rect(-36,36,-28,38-1.4),252)
    shell('main shaft',plan,252)
    # Primary load-bearing ribs remain pale; only wall infill carries the editor tint.
    for side in (-1,1):
        y = -30 if side < 0 else 40
        for i,x in enumerate(FACADE_RIBS):
            fin=concrete('tower continuous concrete fin',(x,y,164),(3.2,5,184),False)
            if side<0:
                # Meet the sloping rib on its top plane instead of burying a square-ended fin in the glass.
                for v in fin.data.vertices:
                    if v.co.z<100:v.co.z=62+(v.co.y+56)*40/28
                fin.data.update()
            concrete('fin head',(x,y,254.2),(3.6,5.4,4.4),False,EDGE)
            # Sparse casting lift lines carry human construction scale into the long piers.
            for z in range(90,251,18):
                box('fin casting joint',(x,y+side*2.515,z),(3.15,.05,.09),STEEL,(.48,.48,.44),True)
        facade_windows(side)
    for side in (-1,1):
        concrete('shaft side corner pier',(side*36.4,-23,146),(4,7,220))
        concrete('shaft side rear pier',(side*36.4,33,146),(4,7,220))
        concrete('side shear blade',(side*37,20,141),(3.7,18,210),True)
        for z in range(90,251,18):
            box('side wall casting course',(side*37.015,5,z),(.06,52,.10),STEEL,(.51,.51,.47),True)
        # A full-height recessed service channel and ordinary landing rails.
        civic.vertical_panel('side service recess',civic.rect(-4.5,4.5,0,179),
                             (side*36.1,-1,69),(0,side,0),STEEL,DARK,.3)
        for offset in (-2.2,2.2):
            cylinder('exposed service riser',(side*36.7,-1+offset,68),
                     (side*36.7,-1+offset,247),.32,STEEL,ALLOY,8)
        for z in (72,108,144,180,216):
            if side > 0 and z == 72:
                continue  # The projecting glazed bay occupies this landing's space.
            concrete('maintenance landing',(side*40,-1,z),(9.2,12,1.1),False,EDGE)
            corners=[(side*36.5,-6.6,z+.55),(side*44.3,-6.6,z+.55),
                     (side*44.3,4.6,z+.55),(side*36.5,4.6,z+.55)]
            for i,(a,b) in enumerate(zip(corners,corners[1:])):
                civic.guardrail('service landing rail',a,b,3.3,start_post=i==0)
            if side > 0 and z == 216:
                lamp('landing work light',(side*36.4,1.4,z+6.4),1.5,.35,(0,side,0))
            else:
                civic.personnel_door('landing access',(side*36.4,-1,z+.55),(0,side,0))
    # Lower rear core makes the actual stepped side silhouette of the photograph.
    rear = civic.rect(-27,27,37,54)
    helper('rear service core',rear,216)
    shell('rear service core',rear,216)
    for side in (-1,1):
        concrete('rear core buttress',(side*26,53.6,132),(4,4,168))
    for row in range(18):
        z = 60+row*8.4
        if z < 88:
            continue
        glass = civic.vertical_panel('rear core windows',civic.rect(-9,9,0,3.5),(0,54.08,z),
                                     (-1,0,0),GLASS,GLAZING,.16)
        if row%4==0:
            shared.emissive(glass,WINDOW_LIGHT,night=True)
        else:
            shared.emission_off(glass)


def podium():
    half = 63
    plan = civic.rect(-half,half,-65,-27)
    upper = civic.rect(-half,half,-56,-27)
    helper('front podium lower storey',plan,18)
    helper('front podium upper block',upper,54)
    # Open porches sit outside the upper helper so generated floors do not bisect the recesses.
    for side in (-1,1):
        concrete('podium side wall',(side*(half-.7),-41.5,26.25),(1.4,29,52.5),True)
        concrete('porch lower side wall',(side*(half-.7),-60.5,7),(1.4,9,14),True)
    concrete('podium rear wall',(0,-27.7,26.25),(2*half,1.4,52.5),True)
    concrete('podium upper recess wall',(0,-55.8,33.25),(2*half,1.4,38.5),True)
    concrete('podium lower front wall',(0,-64.3,7),(2*half,1.4,14),True)
    prism('upper podium roof',upper,52.5,54,CONCRETE,EDGE)
    concrete('portal continuous lintel',(0,-64,54),(131.4,19,8))
    concrete('portal continuous sill',(0,-64,16),(131.4,19,4),False,EDGE)
    for x in (-63,-21,21,63):
        concrete('portal shared jamb',(x,-64,34),(5.4,19,32))
    for bay,x in enumerate((-42,0,42)):
        # Three deep, square portal frames and small lower-storey entrance glazing.
        # Dark slab stays behind the frame. Ordinary doors establish the enormous recess depth.
        box('portal recess back',(x,-56.85,34),(32,.5,32),STEEL,DARK)
        civic.vertical_panel('armored upper service gate',
                             [(-10.8,0),(10.8,0),(10.8,22),(8.2,24),(-8.2,24),(-10.8,22)],
                             (x,-57.3,18),material=PAINT,colour=(.43,.46,.43),thickness=.55)['building_paint']=True
        for z in (20,26,32,38):
            box('gate horizontal panel joint',(x,-57.65,z),(20.4,.10,.13),STEEL,DARK,True)
        box('gate centre seam',(x,-57.67,30),(.16,.12,23),STEEL,DARK,True)
        for sign in (-1,1):
            concrete('gate machinery pilaster',(x+sign*12,-58,31.5),(2,2.2,27),False,EDGE)
            lamp('gate side marker',(x+sign*12,-59.2,29),.8,2.2)
        lamp('portal overhead light',(x,-65.3,49.25),7,.6)
        box('ground entry shadow',(x,-65.2,6),(32,.65,10),STEEL,DARK)
        for xx in (-10,-5,5,10):
            glass = civic.vertical_panel('ground lobby glazing',civic.rect(-1.8,1.8,0,5.2),
                                         (x+xx,-65.6,2),material=GLASS,colour=GLAZING,thickness=.16)
            shared.emissive(glass,WINDOW_LIGHT,night=True)
        civic.personnel_door('podium personnel entrance',(x,-65.7,.5))
        civic.stairs('podium entry stair',x,-73,-65.5,12,.6,1)
        civic.marking(str(bay+1).zfill(2),(x+13,-74,14.2),size=1.6)
    for side in (-1,1):
        outline=civic.rect(-72,-43,-49,64) if side<0 else civic.rect(43,72,-49,64)
        helper('side annex',outline,36)
        shell('side annex',outline,36)
        # The annex roof runs on to the shaft: no slit down to the ground beside the tower.
        x0,x1=(36,43) if side>0 else (-43,-36)
        prism('annex roof to shaft',civic.rect(x0,x1,-27,38),34.5,36,CONCRETE,EDGE)
        civic.personnel_door('annex roof access',(side*36.2,-16,36),(0,side,0))
        outline_band('annex parapet',outline,36.8,1.6,1.2,-.6,key=CONCRETE,colour=EDGE)
        for y in (-34,-7,20,47):
            concrete('annex blind wall buttress',(side*71.9,y,18),(1.6,2,36))
            for z in (9,18,27):
                box('annex formwork course',(side*72.02,y,z),(.06,24,.09),STEEL,(.50,.50,.46),True)
        for y in (-29,40):
            civic.personnel_door('annex maintenance entry',(side*72.08,y,.1),(0,side,0))
        for y in (-18,6.5):
            civic.vertical_panel('annex radiator',civic.rect(-7,7,0,6),
                                 (side*72.08,y,3),(0,side,0),GRILLE,(.60,.63,.60),.2)
        for y in (-25,37):
            box('annex air handler',(side*58,y,38.1),(13,16,4.2),PAINT,(.49,.52,.48))
            box('annex air handler grille',(side*58,y,40.26),(11,14,.15),GRILLE,(.56,.59,.55))
        civic.guardrail('annex roof rail',(side*69.8,-40,36),(side*69.8,57,36),3.3)
    rear=civic.rect(-44,44,38,68)
    helper('rear annex',civic.rect(-44,44,38+1.4,68),36)
    shell('rear annex',rear,36)
    civic.guardrail('rear annex roof rail',(-42,66.8,36),(42,66.8,36),3.3)
    for x in (-31,0,31):
        civic.personnel_door('rear service access',(x,68.1,0),(-1,0,0))
    for x in (-19,19):
        civic.vertical_panel('rear loading grille',civic.rect(-7,7,0,8),
                             (x,68.08,14),(-1,0,0),GRILLE,(.55,.59,.55),.2)


def shoulders():
    # The front haunch slopes continuously from the three square bays into the tall shaft.
    side_prism('front concrete equipment haunch',[(-55,54),(-28,54),(-28,98),(-55,58)],-43,43)
    for left,right in zip(FACADE_RIBS,FACADE_RIBS[1:]):
        x=(left+right)/2
        sloped_window('front sloping window bay',(x,-52.5,62),(x,-30.5,94.3),6.2,(1,0,0))
        lamp('shoulder warning strip',(x,-52.9,61.3),3,.4)
    for x in FACADE_RIBS:
        side_prism('raking concrete shoulder rib',[(-56,56),(-28,96),(-28,102),(-56,62)],x-1.6,x+1.6,colour=EDGE)
    # Low, broad observation bay: shallow glazed shoulders, blunt nose, faceted soffit.
    # The reference projects outward horizontally; it is not a tall triangular buttress.
    profile=[(35,48),(57,42),(68,45),(78,56),(75,68),(35,84)]
    sections=[(-10,.88),(-7,1),(11,1),(14,.88),(17,1),(35,1),(38,.88)]
    vertices=[(35+(x-35)*scale,y,z) for y,scale in sections for x,z in profile]
    n=len(profile)
    faces=[tuple(range(n)),tuple(reversed(range((len(sections)-1)*n,len(sections)*n)))]
    for section in range(len(sections)-1):
        for i in range(n):
            a=section*n+i;b=section*n+(i+1)%n
            faces.append((a,a+n,b+n,b))
    mesh('paired faceted cantilever bay',vertices,faces,CONCRETE,STONE)
    for y in (2,26):
        sloped_window('projecting side roof glazing',(73,y,68.9),(40,y,82),17.4,(0,-1,0),3,3)
        sloped_window('projecting side nose glazing',(77.6,y,57.6),(75.5,y,66),17.4,(0,-1,0),3,1)
    beam('projection central concrete rib',(36,14,84.7),(70.6,14,68.8),2.1,1.1,CONCRETE,EDGE)
    for y in (-7,14,35):
        beam('projection concrete support',(35.5,y,35.5),(66,y,44.8),3.6,3.6,CONCRETE,EDGE)
    side_prism('rear equipment haunch',[(54,36),(68,36),(68,46),(54,88)],-26,26)
    for x in (-16,0,16):
        sloped_window('rear sloping window bay',(x,66.5,50.6),(x,55.5,83.7),11,(-1,0,0),2,4)


def rooftop():
    top=civic.rect(-36,36,-28,38)
    outline_band('tower roof parapet',top,253,2,1.2,-.6,key=CONCRETE,colour=EDGE)
    concrete('roof stair enclosure',(-10,15,257),(22,25,10),False,EDGE)
    civic.personnel_door('roof access',(-10,2.4,252.1))
    for x in (-21,4):
        box('rooftop heat exchanger',(x,-13,254),(19,16,4),PAINT,(.46,.49,.46))
        for xx in (-5,5):
            cylinder('cooling fan housing',(x+xx,-13,256),(x+xx,-13,257),4.1,STEEL,DARK,16)
            cylinder('cooling fan hub',(x+xx,-13,257),(x+xx,-13,257.5),.7,STEEL,ALLOY,10)
            for spoke in range(5):
                a=spoke*math.tau/5
                beam('cooling fan blade',(x+xx+.7*math.cos(a),-13+.7*math.sin(a),257.1),
                     (x+xx+3.4*math.cos(a+.25),-13+3.4*math.sin(a+.25),257.1),.65,.15,
                     STEEL,ALLOY,True)
    for x,y in ((-29,-20),(29,-20),(-29,30),(29,30)):
        concrete('comms mast footing',(x,y,253.5),(5,5,3),False,EDGE)
        cylinder('roof communications mast',(x,y,255),(x,y,266),.45,STEEL,ALLOY,10)
        for side in (-1,1):
            box('mast phased array',(x+side*1.4,y,262),(1.1,1.5,5.3),PAINT,(.54,.56,.51))
        cap=cylinder('red obstruction beacon',(x,y,266),(x,y,266.7),.75,PAINT,(.8,.12,.05),10)
        shared.emissive(cap,(1,.055,.025))
    for side in (-1,1):
        for y0,y1 in ((-21,-4),(2,30)):
            civic.guardrail('roof maintenance rail',(side*35,y0,252),(side*35,y1,252),3.3)
    # Right-hand vertical cable race connects visibly to the rooftop equipment.
    for y in (-3.2,1.2):
        beam('roof service cable',(36.7,y,247),(29,y,255),.45,.45,STEEL,ALLOY)
    box('roof cable terminal',(29,-1,254),(3,8,4),STEEL,DARK)
    civic.maintenance_ladder((37.4,-1,0),(0,1,0),216.55,255.3)
    for y in (-2.15,.15):
        for z in (225,243):
            beam('ladder stand-off',(35.9,y,z),(37.4,y,z),.25,.25,STEEL,ALLOY,True)
    box('ladder roof landing',(36.7,-1,252.2),(3,3.2,.5),STEEL,ALLOY)


def build():
    shared.fresh(SCENE)
    podium()
    tower()
    shoulders()
    rooftop()
    # Lamps made by the shared door helpers use the same fixed amber pigment.
    civic.apply_lights()
    for obj in shared.objects:
        if obj['board_material'] == GLASS and 'vision panel' in obj.name:
            obj['pigment'] = GLAZING
            shared.emissive(obj,WINDOW_LIGHT,night=True)
        shared.project_uvs(obj)
    for obj in shared.volumes:
        obj.hide_set(True)
    scene=bpy.context.scene
    scene['asset_id']='buildings/authored/'+NAME
    scene['hex_width']=HEX_WIDTH;scene['hex_height']=72;scene['level_height']=18
    scene['gate_centres']=[-42,0,42]
    scene['structural_levels']=14;scene['height_metres']=84
    scene['concept']=str(HERE/'references/citadel-concept-v2.png')
    scene['helper_note']='Occupied roofs:18,36,54,216,252; glazed shoulder bays, plant and antennae add no floors.'
    bpy.context.view_layer.update()
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            space=area.spaces.active
            space.region_3d.view_location=(0,0,126)
            space.region_3d.view_distance=390
            space.region_3d.view_rotation=Vector((1,-1,.7)).to_track_quat('Z','Y')
            space.shading.type='MATERIAL'
    return {'objects':len(shared.objects),'helpers':len(shared.volumes)}


def export():
    levels={i:shared.export_model(shared.objects,NAME+'-lod'+str(i),level=i) for i in (0,1,2)}
    helpers=shared.export_model(shared.volumes,NAME,helper=True)
    stats={i:{'vertices':sum(len(m['vertices'])//12 for m in level['meshes']),
              'triangles':sum(len(p['indices'])//3 for m in level['meshes'] for p in m['parts'])}
           for i,level in levels.items()}
    assert all(s['vertices']<65535 for s in stats.values()),stats
    write_glb(shared.DEST/(NAME+'.glb'),levels=levels,groups={'building_volumes':helpers})
    bpy.data.libraries.write(str(shared.SOURCE/(NAME+'.blend')),{bpy.context.scene},fake_user=True)
    return stats


def studio(view='isometric',size=1200):
    scene=bpy.context.scene
    collection=scene.collection.children.get('Citadel review studio')
    if not collection:
        collection=bpy.data.collections.new('Citadel review studio')
        scene.collection.children.link(collection)
        camera=bpy.data.objects.new('Citadel review camera',bpy.data.cameras.new('Citadel review camera'))
        collection.objects.link(camera);scene.camera=camera
        for loc,power,scale in [((150,-250,430),520000,220),((-220,-70,230),270000,190),((80,240,310),420000,190)]:
            light=bpy.data.objects.new('Citadel softbox',bpy.data.lights.new('Citadel softbox','AREA'))
            collection.objects.link(light);light.location=loc;light.data.energy=power;light.data.shape='DISK';light.data.size=scale
            light.rotation_euler=(Vector((0,0,120))-light.location).to_track_quat('-Z','Y').to_euler()
        mesh=bpy.data.meshes.new('Citadel review ground')
        mesh.from_pydata([(-600,-600,-.25),(600,-600,-.25),(600,600,-.25),(-600,600,-.25)],[],[(0,1,2,3)])
        ground=bpy.data.objects.new('Citadel review ground',mesh);collection.objects.link(ground)
        ground.data.materials.append(shared.material(shared.FLAT,(.20,.23,.24)))
    camera=scene.camera
    targets={'isometric':(340,-440,310),'front':(0,-500,130),'right':(500,0,130),
             'back':(0,500,130),'left':(-500,0,130),'top':(0,0,500)}
    camera.location=targets[view]
    target=Vector((0,0,130 if view!='top' else 0))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=320 if view!='top' else 185
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    scene.render.resolution_x=size;scene.render.resolution_y=size;scene.render.resolution_percentage=100
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.22,.25,.29,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.7
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.8
    scene.render.image_settings.file_format='PNG'
    path=shared.SOURCE/(NAME+'-'+view+'.png');scene.render.filepath=str(path)
    return str(path)
