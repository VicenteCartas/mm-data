# Road tunnel portal

Two GLBs share the same portal geometry:

- `data/models/board/road-tunnel.glb`: wing walls, 289 triangles.
- `data/models/board/road-tunnel-bridge.glb`: no wing walls, 273 triangles.

Both use one LOD0. The bridge portal has no `tunnel-wings` part; the arch, deep
shell and lining are identical.

The portal and lining use the dedicated repeating
`data/models/board/textures/scenery/tunnel-concrete_albedo.png` albedo, exported by the
Material Maker project `tools/materials/scenery/tunnel-concrete/`; the floor uses
the shared asphalt texture. At runtime the floor receives its approach's
road material (asphalt, gravel or dirt), including its normal and surface
maps and world-space texture alignment. Concrete repeats every six model units with fine aggregate
and pores, rather than the terrain material's large blotches.
The outer side walls and roof extend the full 18-unit tunnel depth, allowing
the portal to be embedded in a sloping face. The lining and piers do not have
overlapping inner faces. Four lining bays interpolate vertex colour continuously
into a dark end cap.

The 15-unit carriageway continues through the entrance to Y=18. Its four floor
quads retain full material brightness through Y=6 and then fade into darkness;
concrete verges fill the remaining opening width. The floor begins at Y=2.75,
slightly before the shared hex edge at Y=3, with a 0.02-unit recessed lip. This
small underlap seals the lattice's oblique edges without coplanar fighting.

Coordinates: Z up, +Y into the cliff, opening at Y=0, base at Z=0. Opening is
19 units wide, with vertical piers to Z=6 and a 16-segment semicircle of radius
9.5. Outer roof reaches Z=19.2. The width accommodates the existing road without
changing its wheel spacing. `BoardTunnel` uses these dimensions when clipping
the existing terrain for the opening. Update that contract if these change.

Generated reference: `road-tunnel-reference.png`, made with the built-in imagegen
tool. Prompt requested a realistic low-poly concrete portal in a natural cliff,
a thick arched rim, flared wing walls, a deep dark lining, and an unchanged
two-lane road width, viewed from the front and three-quarter angle.

This is a visual entrance only; it does not add a traversable tunnel or change
board elevations, exits or movement rules.

`BoardTunnel` places bridge portals at the actual deck elevation, independent
of the terrain family beneath or beside the bridge. The opening must fit in
the facing dry cliff. Ground roads keep the existing grading decisions.
The Lava Tubes 1 fixture has 13 cliff-facing bridge exits and four exits that
connect the bridge decks to one another; only the former receive portals.

Whole decorative rocks are excluded from the shell, wing walls and immediate
road approach. Formations above the portal and beside its cleared footprint
remain. `BoardTunnel.obstructs` defines this small visual clearance.

The concrete albedo was generated with the built-in imagegen tool. Its complete
prompt is saved in `road-tunnel-texture-prompt.json` for maintenance.
