# Ground scar artwork

These materials are the editable source artwork for the 3D board's combat scars: Godot 4
Standard materials whose `NAME_albedo.png` holds the artwork (alpha is coverage).
The game loads them from `data/models/board/textures/terrain/damage/` when preparing a board.

| Material | Used for |
| --- | --- |
| `laser-gouge`, `laser-blast` | Smooth laser grooves and round fused impacts |
| `ppc-gouge`, `ppc-blast` | Fractured fused grooves and round impacts, selected by `F_PPC` |
| `ballistic-gouge`, `ballistic-blast` | Autocannon and other ballistic furrows and round impacts |
| `blast` | Missiles and artillery; damage controls size |
| `burn` | Flamer scorch patches, without excavated relief |
| `plasma-splash` | Melted splashes, selected by `F_PLASMA` or `F_PLASMA_MFUK` |

## Editing

Keep RGBA PNG transparency. Alpha controls coverage and must fade out along the
ragged perimeter. RGB is grayscale material detail: dark regions become charred
cores, and lighter regions become disturbed debris. The image modulates the
receiving material's colour and grain: middle gray leaves its brightness unchanged,
darker values char it. Grass uses its existing soil texture beneath the scar.
The round stamps have a translucent irregular fringe, with an opaque center.
This lets the same mark blend into grass, dirt and sand without an opaque gray rim.
Transparent pixels contribute nothing, regardless
of their RGB. Avoid a solid background, directional lighting, baked highlights,
text or a checkerboard painted into the image.

Keep the art simple enough to read when displayed 30 to 100 pixels wide: broad
dark forms, a few coarse variations, no bright raised rims or fine rendered rocks.
Gouges run left to right and use a 256-by-64 canvas with 240-by-48 artwork (5:1).
Round marks use a 256-square canvas with 240-square artwork. Leave eight pixels
of transparent padding. This common layout makes damage scaling comparable.
Runtime ignores margins below alpha 16/255 when measuring the visible footprint,
and keeps mip chains capped at 256 pixels on the longest side.

At load time `GpuGroundDamage` converts alpha and grayscale detail into its shared
coverage, premultiplied luminance, glass and shallow-relief channels. Weapon style
sets the material response: PPC and plasma are glassy; plasma is shallow; flamer
burns have no glass or depression and use a fixed 65% opacity. The loaded image supplies the actual
silhouette and detail. There is no second procedural shape generator.

Damage, minimum size, impact placement, direction and grass clearing remain in the
renderer. Damage is clamped to one only for scar sizing. Base visible span is
`3 * sqrt(damage)` metres, measured after removing empty margins, for gouge
length and burn width. Missile/artillery blasts and plasma splashes use the smooth
power curve `2.7 * damage^0.4634086426` metres: LRM is 2.7 metres across (10% smaller)
and Long Tom is 12 metres across (20% smaller), with all other damage values
following the same curve. A 10-damage plasma rifle leaves a 7.8-metre splash.
Perpendicular
laser/PPC/ballistic blast diameter is twice gouge width (40% of its length).
Flamer damage
changes size only, not opacity. Mipmap filtering is applied both when sampling the
source artwork and when displaying it at a distance. Runtime masks use eight-metre
tiles at 30 texels per metre, allocated only around impacts. Each 256-square image
has a 240-square interior and eight border pixels per edge. All tiles and their
directory share one GPU texture array and one sampler; larger boards do not reduce
scar resolution. These masks do not store terrain weathering or board decorations.

Lasers, PPCs and ballistics choose their round image when the incoming shot is
within 45 degrees of the receiving surface triangle's normal (including 45 degrees).
Shallower strikes keep the gouge. An AC/20 therefore leaves a 13.4-by-2.7-metre
gouge or a 5.4-metre blast. Both shapes preserve the weapon's material response.
Missed beams, projectiles, missiles, artillery, plasma and flames use their first
contact with the installed terrain or structure geometry. Curved flights check
32 bounded segments once at emission; straight projectiles check one. Contact
position, direction and arrival time are shared by the flight, impact and scar.
This is cosmetic and does not change the game's hit or damage result.

Cliffs and opaque structure walls use patches cut from the actual receiving mesh,
so scars follow deformed surfaces. Their sparse image tiles share the ground
mask's texture array, mipmaps and material channels. Further hits repaint existing
tiles instead of adding geometry per shot. Only newly damaged areas need patches;
terrain detail replacement rebuilds those patches while retaining the images.
Wall projection is limited to two queued impacts per frame. The shared GPU array
layer limit still bounds total history. Trees, foliage and transparent surfaces
are not wall scar receivers.

After editing, stage the data and reopen the board (or restart the client) to reload
the artwork. An absent or unreadable PNG logs a warning and disables that style;
it is not silently replaced with a different shape.

## Provenance

Generated with Codex's built-in ImageGen, fitted to its visible alpha bounds and
exported at the dimensions above with premultiplied-alpha downsampling; no
procedural shapes or painted replacement alpha masks were added. Each image's
Material Maker project, `tools/materials/terrain/damage/<name>/<name>.ptex`, holds
an identical copy under `sources/` and its export settings. In-game material
conversion and filtering do not modify these source files.
