"""Live Blender floodlight fixtures for the arenas.

No private textures: housings and lenses reuse shared steel and glass finishes.
"""
import json
import math


def light_extras(scene):
    # Root metadata uses glTF's Y-up coordinates, linear RGB and model units.
    return {'mmNightLights':json.loads(scene.get('night_lights','[]'))}


def floodlights():
    import bpy
    from mathutils import Matrix,Vector
    import civic_buildings as civic
    import authored_examples as shared
    from hpg_headquarters import box,beam
    scene=bpy.context.scene
    if 'night_lights' in scene:return light_extras(scene)
    lights=[]
    for i in range(8):
        a=math.tau*(i+.5)/8
        c=Vector((69*.635*civic.oval(a)[0],99*.635*civic.oval(a)[1],27))
        normal=Vector((-math.cos(a),-math.sin(a),-.7)).normalized()
        rotation=normal.to_track_quat('Z','Y')
        # Bracket bolts directly to the underside of the inner canopy.
        beam('bowl floodlight bracket',c+Vector((0,0,6.5)),c,.55,.55,
             civic.STEEL,civic.DARK)
        housing=box('bowl floodlight housing',(0,0,0),(7,2.7,1.0),civic.STEEL,civic.DARK)
        housing.matrix_world=Matrix.Translation(c)@rotation.to_matrix().to_4x4()
        lens=box('bowl floodlight lens',(0,0,0),(6.2,1.9,.16),civic.GLASS,(.84,.94,.96))
        lens.matrix_world=Matrix.Translation(c+normal*.53)@rotation.to_matrix().to_4x4()
        shared.emissive(lens,(.86,.93,1),night=True)
        point=c+normal*.7
        lights.append({'position':[point.x,point.z,-point.y], 'color':[.80,.89,1.0],
                       'power':1.8,'size':40.0})
    scene['night_lights']=json.dumps(lights)
    for o in shared.objects:
        if o.name.startswith('bowl floodlight'):shared.project_uvs(o)
    bpy.context.view_layer.update()
    return light_extras(scene)
