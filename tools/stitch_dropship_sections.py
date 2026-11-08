"""Stitches each multi-hex unit's seven hex sections in mekset.txt into one image, for the 3D board's whole tokens.

Every set of "<name>_0" to "<name>_6" gets "<name>_whole", a PNG in a "whole" folder beside its sections, with its line after
the set's last section. Sections lie as EntityImage.X_POS and Y_POS place them, at facing 0. Run again after adding a set: what
exists is written again and no line is added twice.

usage: python tools/stitch_dropship_sections.py
"""
import re
from pathlib import Path

from PIL import Image

UNITS = Path(__file__).resolve().parent.parent / 'data' / 'images' / 'units'
TILESET = UNITS / 'mekset.txt'
HEX_WIDTH, HEX_HEIGHT = 84, 72
X_POS = (0, 0, 63, 63, 0, -63, -63)
Y_POS = (0, -72, -36, 36, 72, 36, -36)
SECTION = re.compile(r'^(chassis|exact) "(.+)_([0-6])" "(.+)"\s*$')


def stitched(sections):
    width, height = HEX_WIDTH + 2 * max(X_POS), HEX_HEIGHT + 2 * max(Y_POS)
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    for position, relative in enumerate(sections):
        section = Image.open(UNITS / relative).convert('RGBA')
        # A shorter section keeps its art at the top, as the game reads it (Buccaneer_4).
        assert section.width <= HEX_WIDTH and section.height <= HEX_HEIGHT, relative
        canvas.alpha_composite(section, (max(X_POS) + X_POS[position], max(Y_POS) + Y_POS[position]))
    return canvas


def main():
    raw = TILESET.read_bytes().decode('utf-8')
    newline = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.split(newline)
    sets = {}
    for line in lines:
        match = SECTION.match(line)
        if match:
            kind, name, position, path = match.groups()
            sets.setdefault((kind, name), {})[int(position)] = path
    existing = set(lines)
    written = 0
    for (kind, name), sections in sets.items():
        assert sorted(sections) == list(range(7)), name
        first = Path(sections[0])
        base = first.stem[:-2]
        whole = first.parent / 'whole' / (base + '.png')
        (UNITS / whole).parent.mkdir(parents=True, exist_ok=True)
        stitched([sections[position] for position in range(7)]).save(UNITS / whole, optimize=True)
        written += 1
        entry = f'{kind} "{name}_whole" "{whole.as_posix()}"'
        if entry not in existing:
            last = lines.index(f'{kind} "{name}_6" "{sections[6]}"')
            lines.insert(last + 1, entry)
    TILESET.write_bytes(newline.join(lines).encode('utf-8'))
    print(f'{written} sets stitched')


if __name__ == '__main__':
    main()
