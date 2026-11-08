"""Move or rename a board model, keeping its stable id; or give new models their ids.

Run: python tools/move_model.py <path> <new path>   (paths under data/models/board, without .glb)
     python tools/move_model.py --stamp             (an id for every board model that has none)

A board model is named by its path; saved boards (.board2) also store its stable id from data/models/board/uids.json,
so a board saved before a move still finds the model. Moving a file by hand breaks that link: the BoardModelIdsTest
check fails until its line in uids.json names the new path. Never give a moved model a new id: update its line.
Moving rewrites the GLB's relative texture paths for its new folder and renames its entries in
tools/board-models/manifest.json (a tree's winter form <path>-snow too). Code and data that name the old path are listed for you to update.
"""
import json
import os
import re
import secrets
import string
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'data/models/board'
UIDS = BOARD / 'uids.json'
MANIFEST = ROOT / 'tools/board-models/manifest.json'


def read_uids():
    return json.loads(UIDS.read_text(encoding='utf-8'))


def write_uids(uids):
    ordered = dict(sorted(uids.items(), key=lambda entry: entry[1]))
    UIDS.write_bytes((json.dumps(ordered, indent=2) + '\n').encode('utf-8'))


def new_uid(taken):
    alphabet = string.ascii_lowercase + string.digits
    while True:
        uid = ''.join(secrets.choice(alphabet) for _ in range(8))
        if uid not in taken:
            return uid


def relocate(source, target):
    """Write the GLB at target with its relative texture paths (images, material variants) rewritten, then remove it."""
    data = source.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    rest = data[20 + length:]

    def moved(uri):
        return Path(os.path.relpath((source.parent / uri).resolve(), target.parent.resolve())).as_posix()

    for image in gltf.get('images', []):
        if 'uri' in image:
            image['uri'] = moved(image['uri'])
    for material in gltf.get('materials', []):
        textures = material.get('extras', {}).get('mmSnow', {}).get('textures', {})
        for role in textures:
            textures[role] = moved(textures[role])
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(text) + len(rest))
                       + struct.pack('<I4s', len(text), b'JSON') + text + rest)
    source.unlink()


def move(old, new):
    source, target = BOARD / (old + '.glb'), BOARD / (new + '.glb')
    if not source.is_file() or target.exists():
        raise SystemExit(f'Needs an existing {source} and no {target}')
    uids = read_uids()
    uid = next((key for key, path in uids.items() if path == old), None)
    if uid is None:
        raise SystemExit(f'{old} has no id in {UIDS}; run --stamp first')
    relocate(source, target)
    uids[uid] = new
    write_uids(uids)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    renamed = {}
    for key, entry in manifest.items():
        if entry.get('mesh') == old + '.glb':
            entry['mesh'] = new + '.glb'
        renamed[new + key[len(old):] if key in (old, old + '-snow') else key] = entry
    MANIFEST.write_text(json.dumps(renamed, indent=2) + '\n', encoding='utf-8')
    print(f'{old} -> {new} (id {uid})')
    # This data repository and the code repositories beside it.
    pattern = '"' + re.escape(old) + '(-snow)?"'
    for repo in [ROOT, *(folder for folder in ROOT.parent.iterdir() if (folder / 'megamek/src').is_dir())]:
        users = subprocess.run(['git', '-C', str(repo), 'grep', '-l', '-E', pattern], capture_output=True, text=True)
        if users.stdout:
            print(f'In {repo}, these name "{old}"; update them to "{new}":\n{users.stdout}')


def stamp():
    uids = read_uids()
    known = set(uids.values())
    added = 0
    for path in sorted(BOARD.rglob('*.glb')):
        name = path.relative_to(BOARD).as_posix()[:-len('.glb')]
        if name not in known:
            uids[new_uid(uids)] = name
            added += 1
    write_uids(uids)
    print(added, 'models given ids')


if __name__ == '__main__':
    if sys.argv[1:] == ['--stamp']:
        stamp()
    elif len(sys.argv) == 3:
        move(sys.argv[1], sys.argv[2])
    else:
        raise SystemExit(__doc__)
