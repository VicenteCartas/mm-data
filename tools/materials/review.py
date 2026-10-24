"""Review a material in the game: export it, then render the material fixture with MegaMek's offline board renderer.

python review.py terrain/surfaces/dirt-ground/dirt-ground.ptex [--view VIEW ...] [--hour 13] [--label after] [--no-export]

The export is export.py's: the maps go to data/models/board/textures, and the MegaMek build stages them like any other
data before rendering. Each view renders twice, from straight above and obliquely:
  board                           the whole fixture
  rock, grassland, dirt           one of the fixture's three panels (rock, grassland and dirt themes)
  rock-back, grassland-back, ...  the same panel seen from the other side
  x,y,zoom,orbit                  any close-up: zero-based hex, camera zoom and orbit in degrees
Captures go to <megamek>/build/material-review/<material>/<label>/<view>/ and are listed at the end. Rendering waits
while a GPU benchmark holds the benchmark lock.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
BOARD = 'fixtures/Rock Slopes and Cliffs.board2'
# Zero-based column in the middle of each fixture panel (columns 1-9, 11-19 and 21-29), on its middle row
PANELS = {'rock': 4, 'grassland': 14, 'dirt': 24}
TEST = 'megamek.client.ui.clientGUI.boardview.gpu.GpuBoardFileSmokeTest.capturesShippedBoards'
# Staging tasks the review does not need; models (the exported maps) and boards still stage
SKIPPED_STAGING = ('stageDataImages', 'stageDataFonts', 'stageDataMekfiles', 'stageDataRat')


def closeup(view):
    if view == 'board':
        return None
    panel, _, side = view.partition('-')
    if panel in PANELS:
        return f'{PANELS[panel]},5,0.6,{180 if side == "back" else 0}'
    if len(view.split(',')) != 4:
        raise SystemExit(f'Unknown view {view!r}: use board, a panel ({", ".join(PANELS)}, optionally -back) or x,y,zoom,orbit')
    return view


def megamek_checkout(path):
    candidates = [Path(path)] if path else [ROOT.parents[2] / name for name in ('megamek_temp', 'megamek')]
    for candidate in candidates:
        if (candidate / 'megamek' / 'build.gradle').is_file():
            return candidate.resolve()
    raise SystemExit('No MegaMek checkout found: pass --megamek')


def capture(megamek, view, hour, output):
    lock = megamek / 'build/shader-audit/gpu-benchmark.lock'
    if lock.exists():
        print('Waiting for the GPU benchmark to release its lock...', flush=True)
        while lock.exists():
            time.sleep(30)
    review = megamek / 'megamek/build/gpu-board-review/boards'
    shutil.rmtree(review, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    command = [str(megamek / ('gradlew.bat' if os.name == 'nt' else 'gradlew')), ':megamek:gpuBoardSmoke',
               '--tests', TEST, '-Dmegamek.gpu.card=DISCRETE', f'-Dmegamek.gpu.boards={BOARD}',
               f'-Dmegamek.gpu.boards.hour={hour}', '--console=plain']
    if closeup(view):
        command.append(f'-Dmegamek.gpu.boards.closeup={closeup(view)}')
    for task in SKIPPED_STAGING:
        command += ['-x', task]
    # Selects the NVIDIA GPU on hybrid-graphics laptops; other drivers ignore it
    environment = dict(os.environ, SHIM_MCCOMPAT=os.environ.get('SHIM_MCCOMPAT', '0x800000001'))
    with open(output / 'gradle.log', 'w', encoding='utf-8') as log:
        subprocess.run(command, cwd=megamek, env=environment, stdout=log, stderr=subprocess.STDOUT)
    # Gradle can report a failure after the captures are written, so the captures decide
    captures = sorted(review.glob('*.png'))
    if not captures:
        raise SystemExit(f'No capture for view {view}: see {output / "gradle.log"}')
    for file in captures:
        shutil.copyfile(file, output / file.name)
    return [output / file.name for file in captures]


def main():
    arguments = argparse.ArgumentParser(description='Export a board material and render it in the game.')
    arguments.add_argument('project', help='the .ptex path relative to tools/materials, as for export.py')
    arguments.add_argument('--view', action='append', help='board (default), rock, grassland, dirt, <panel>-back or x,y,zoom,orbit')
    arguments.add_argument('--hour', default='13', help='time of day, default 13')
    arguments.add_argument('--label', default=time.strftime('%H%M%S'), help='name of this capture set, e.g. before or after')
    arguments.add_argument('--no-export', action='store_true', help='render the maps as they are')
    arguments.add_argument('--megamek', help='MegaMek checkout, default the sibling megamek_temp or megamek')
    options = arguments.parse_args()
    views = options.view or ['board']
    for view in views:
        closeup(view)
    megamek = megamek_checkout(options.megamek)
    if not options.no_export:
        subprocess.run([sys.executable, str(ROOT / 'export.py'), options.project], check=True)
    destination = megamek / 'build/material-review' / Path(options.project).stem / options.label
    for view in views:
        print(f'Rendering {view}...', flush=True)
        for file in capture(megamek, view, options.hour, destination / view):
            print(file)


if __name__ == '__main__':
    main()
