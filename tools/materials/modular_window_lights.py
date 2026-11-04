"""Update the existing light-frame material through Material Maker's native MCP.

Neutral dark glazing is isolated from the warm stone/metal in the source atlas.
The resulting emission is baked onto the distant atlas by Blender MCP, so both
LODs use the same window regions. All new outputs are at most 512 square.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0,'C:/material_maker')
import material_maker_mcp as mm

ROOT=Path(__file__).resolve().parents[2]


def call(name,**args):
    result=mm.call(8790,'tools/call',{'name':name,'arguments':args})
    if result.get('isError'):raise RuntimeError(result)
    texts=[c['text'] for c in result.get('content',[]) if c['type']=='text']
    try:return json.loads(texts[0])
    except (ValueError,IndexError):return texts


def edit_project(path,edits):
    result=call('edit_files',files=[str(path)],edits=edits,save=True)
    if any('not_saved' in item for item in result.get('files',[])):
        opened=call('load_graph',path=str(path))
        tab=opened['tab']
        call('apply_edits',tab=tab,edits=edits)
        call('save_graph',tab=tab,path=str(path))
    return result


def frames():
    path=ROOT/'tools/materials/structures/buildings/light-frames/light-frames.ptex'
    graph=json.loads(path.read_text())
    if any(n['name']=='WindowEmission' for n in graph['nodes']):
        return call('export_material',graph_path=str(path),path=str(ROOT/'data/models/board/textures/structures/buildings/light-frames'),
                    size=512,target='Godot/Godot 4 Standard',exact_8bit=False)
    edits=[]
    def add(node,name,parameters,x,y):edits.append({'op':'add','node':node,'name':name,'parameters':parameters,'x':x,'y':y})
    def connect(source,port,target,input=0):edits.append({'op':'connect','from':source,'from_port':port,'to':target,'to_port':input})
    add('decompose','GlassRGB',{},-1200,1000);connect('AlbedoSource',0,'GlassRGB')
    add('math','GlassChroma',{'op':1},-950,1000);connect('GlassRGB',0,'GlassChroma');connect('GlassRGB',2,'GlassChroma',1)
    add('math','GlassChromaAbs',{'op':7},-750,1000);connect('GlassChroma',0,'GlassChromaAbs')
    add('math','NeutralGlass',{'op':15,'default_in2':.012},-550,1000);connect('GlassChromaAbs',0,'NeutralGlass')
    add('math','DarkGlass',{'op':15,'default_in2':.45},-750,1230);connect('GlassRGB',0,'DarkGlass')
    add('math','NotBackground',{'op':15,'default_in1':.045},-750,1450);connect('GlassRGB',0,'NotBackground',1)
    add('math','WindowMask',{'op':2},-300,1000);connect('NeutralGlass',0,'WindowMask');connect('DarkGlass',0,'WindowMask',1)
    add('math','WindowInterior',{'op':2},-80,1000);connect('WindowMask',0,'WindowInterior');connect('NotBackground',0,'WindowInterior',1)
    add('math_v3','WindowEmission',{'op':2,'d_in2_x':.60,'d_in2_y':.49,'d_in2_z':.26},180,1000)
    connect('WindowInterior',0,'WindowEmission');connect('WindowEmission',0,'Material',3)
    result=edit_project(path,edits)
    call('export_material',graph_path=str(path),path=str(ROOT/'data/models/board/textures/structures/buildings/light-frames'),
         size=512,target='Godot/Godot 4 Standard',exact_8bit=False)
    return result


def far_and_glass():
    result=[]
    for name in ('light-far','fortress-glass'):
        path=ROOT/f'tools/materials/structures/buildings/{name}/{name}.ptex'
        graph=json.loads(path.read_text())
        if not any(n['name']=='NightWindowSource' for n in graph['nodes']):
            node='image' if name=='light-far' else 'uniform'
            # New nodes have no project directory until attached. Set the portable
            # source path in a second edit, once the node belongs to this graph.
            parameters={'image':(path.parent/'sources/window-emission.png').as_posix(),'filter':True,'clamp':False} if name=='light-far' else {
                'color':{'type':'Color','r':.60,'g':.49,'b':.26,'a':1}}
            result.append(edit_project(path,[
                {'op':'add','node':node,'name':'NightWindowSource','parameters':parameters,'x':800,'y':900},
                {'op':'connect','from':'NightWindowSource','from_port':0,'to':'Material','to_port':3}]))
        if name=='light-far':
            result.append(edit_project(path,[{'op':'set','node':'NightWindowSource',
                'parameters':{'image':'%PROJECT_PATH%/sources/window-emission.png'}}]))
        result.append(call('export_material',graph_path=str(path),
            path=str(ROOT/f'data/models/board/textures/structures/buildings/{name}'),size=512,
            target='Godot/Godot 4 Standard',exact_8bit=False))
    return result


def night_metadata():
    paths=['structures/buildings/'+n for n in ('light-frames','light-far','fortress-glass')]
    paths+=['structures/lunar/habitat-wall','structures/lunar/dome-window']
    for name in paths:
        path=ROOT/('data/models/board/textures/'+name+'.tres');text=path.read_text()
        if 'emission_texture' not in text:
            image=path.stem+'_emission.png'
            text=text.replace('[resource]',f'[ext_resource path="{image}" type="Texture" id=5]\n[resource]')
            text+='\nemission_enabled = true\nemission = Color(0, 0, 0, 1)\nemission_energy = 1.0\nemission_operator = 0\nemission_texture = ExtResource( 5 )\n'
        if 'metadata/mmNightEmission' not in text:text+='metadata/mmNightEmission = true\n'
        # Header load_steps counts resources plus the material, even though the runtime does not need it.
        import re
        text=re.sub(r'load_steps=\d+',f'load_steps={text.count("[ext_resource")+1}',text)
        path.write_text(text)
    return paths


if __name__=='__main__':
    report={'frames':frames()}
    if '--finish' in sys.argv:report.update(far=far_and_glass(),metadata=night_metadata())
    print(json.dumps(report,indent=2))
