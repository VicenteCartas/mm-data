"""Export authored level-one shrubs with Blender: --background --python build_shrubs.py -- [--out BOARD] [names].

Editable basal stems, branch curves and attached sprays live in sources/shrubs.blend and desert-shrubs.blend.
The forest exporter retains the same woody scaffold and nested foliage samples at every mesh level.
Rebake impostors with prepare_tree_lods.py after changing the source. No addon is needed to export it.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_forest import BOARD, build as export


def build(board=BOARD, names=None):
    result = {}
    for source in ('shrubs.blend', 'desert-shrubs.blend'):
        result.update(export(board, names, HERE / 'sources' / source))
    return result


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    board = BOARD
    if arguments[:1] == ['--out']:
        board, arguments = Path(arguments[1]), arguments[2:]
    build(board, set(arguments))
