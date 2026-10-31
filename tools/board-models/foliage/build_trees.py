"""python tools/board-models/foliage/build_trees.py [--out BOARD] [names]: the conifers' and broadleaf trees' LOD0-2
and their manifest counts.

Each species is grown from its botany instead of modelled by hand. Every card face has its back; every card carries
its crown's envelope normal (the game lights cards as proxies of the leaves around them, terrain-foliage.frag), and
vertex colours shade the crown dark inside and bright at its surface. Coarser levels keep the silhouette with fewer,
wider cards. Each level is scaled to the plants' common height of 30 units, standing at the origin.

Conifers: a straight, tapered trunk with a root flare and branches in whorls up the trunk, with smaller ones between,
their reach following the crown's cone. A branch is one card of the conifer-cutout spray, bent along its length (it
leaves the trunk at its whorl's angle, sags and turns its tip up) and folded along its stem so its side shoots hang
like the curtains of a spruce, which is what the board's iso and top views see. pine is a Norway spruce, pine-tall a
forest-grown spruce with a bare lower trunk, pine-broad a silver fir, pine-slender a subalpine fir (kept full enough
to read as cover) and pine-layered a fir with open tiers.

Broadleaf trees: a trunk forking into curved limbs (or, in excurrent species, a leader with limbs along it) and twigs,
all bark tubes, ending in clumps of crossed broadleaf-cutout cards inside the crown's ellipsoid. Each clump has its
own dome normal and shade, so the crown reads as clumps lit on top and dark beneath, with branches in the gaps.
tree is a linden, tree-broad an oak, tree-slender a Lombardy poplar, tree-layered a beech, tree-forked a twin-stemmed
maple, the birches silver birches with drooping clumps and the willows weeping willows: a dome of drooping clumps over
arched limbs, so the top view sees a closed crown, with curtains hanging below it.

The canopy's winter form is a material variant (mmVariants.snow): the snow cutout, with a colour scale that turns the
species' leaf tint grey. pine-tall-snow, tree-forked-snow and willow-snow are their species' geometry with that variant
applied, as files of their own. Afterwards refresh the impostors with Blender: tools/prepare_tree_lods.py -- impostors
<names>. --out writes the GLBs into another board folder (its textures must resolve as ../textures from its
vegetation folder) and leaves the manifest alone.
"""
import json
import math
import random
import sys
from pathlib import Path

MM = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MM / 'tools'))
from glb_geometry import display, linear, read_glb, write_glb  # noqa: E402

BOARD = MM / 'data/models/board'
MANIFEST = MM / 'tools/board-models/manifest.json'
HEIGHT = 30.0
# Each family's triangle ceilings per level, about what its full design needs (a plant fills them only so far):
# broadleaf crowns carry twigs and side shoots on the two near levels. Shrubs and orchards set their own.
BUDGETS = {'broadleaf': (1600, 410, 96), 'conifer': (1200, 300, 96), 'palm': (1000, 300, 96),
           'cactus': (1000, 300, 96)}
# Each cutout's stem: U at its base on the bottom edge; V from the base to the tip (V runs down the image).
STEMS = {'conifer': .55, 'broadleaf': .42}
BASE_V, TIP_V = .985, .02
WINTER = ('pine-tall-snow', 'tree-forked-snow', 'willow-snow', 'tree-dead-snow')

# Conifers: crown base and widest radius as shares of the height, the envelope's exponent (1 a cone, less is fuller),
# whorls, branches per whorl and between whorls, branch angles at the top and the bottom of the crown (degrees), sag
# and tip upturn (shares of the reach), the side shoots' droop at the stem and the tip at the top and the bottom of the
# crown (degrees), the card's width over its reach, trunk radius at the foot, bark and leaf tints (display RGB) and
# dead branch stubs below the crown.
CONIFERS = {
    'pine': dict(seed=1, base=.05, radius=.32, exponent=.85, whorls=14, per_whorl=5, between=2, angles=(42, -18),
                 sag=(.05, .32), upturn=(0, .3), droop=((18, 30), (40, 62)), width=.85, trunk=.55,
                 bark=(.44, .37, .33), leaves=(.78, .93, .7), stubs=0),
    'pine-tall': dict(seed=2, base=.28, radius=.28, exponent=.8, whorls=12, per_whorl=5, between=2, angles=(45, -12),
                      sag=(.05, .28), upturn=(0, .28), droop=((18, 28), (36, 58)), width=.82, trunk=.55,
                      bark=(.47, .39, .34), leaves=(.76, .88, .62), stubs=14),
    'pine-broad': dict(seed=3, base=.04, radius=.4, exponent=.92, whorls=12, per_whorl=6, between=2,
                       angles=(38, -6), sag=(.04, .14), upturn=(0, .12), droop=((10, 18), (18, 32)), width=.9,
                       trunk=.62, bark=(.52, .49, .46), leaves=(.72, .88, .8), stubs=0),
    'pine-slender': dict(seed=4, base=.03, radius=.26, exponent=.75, whorls=16, per_whorl=4, between=1,
                         angles=(48, -26), sag=(.06, .3), upturn=(0, .18), droop=((22, 34), (40, 60)), width=.85,
                         trunk=.42, bark=(.5, .45, .41), leaves=(.74, .9, .79), stubs=0),
    'pine-layered': dict(seed=5, base=.2, radius=.37, exponent=.75, whorls=8, per_whorl=7, between=0,
                         angles=(30, -4), sag=(.03, .12), upturn=(.05, .22), droop=((10, 16), (16, 28)), width=.9,
                         trunk=.6, bark=(.48, .4, .35), leaves=(.88, .98, .6), stubs=8),
}
# How each level thins a conifer: whorls kept, branches per whorl and between whorls, card width, bends on the long
# branches, folded cards, trunk sides and rings, core cards, leader cards and stubs. A level with no branches per whorl
# spirals single branches up the trunk instead, so a few cards cover the whole crown without gaps between tiers. Far
# levels keep core cards: their flat branch cards alone turn edge-on to a low view.
CONIFER_LEVELS = (
    dict(whorls=1, per_whorl=1, between=1, width=1, segments=2, fold=True, sides=6, rings=7, core=3, leader=2,
         stubs=True, core_width=1.1),
    dict(whorls=.85, per_whorl=1, between=0, width=1.25, segments=1, fold=False, sides=5, rings=3, core=2, leader=1,
         stubs=False, core_width=1.3),
    dict(whorls=.3, per_whorl=0, between=0, width=2.1, segments=1, fold=False, sides=4, rings=2, core=3, leader=1,
         stubs=False, core_width=1.75))
# Conifer branches reaching further than this share of the crown's widest radius bend twice.
LONG = .55

# Broadleaf trees: the fork's height and the crown ellipsoid's centre height, horizontal and vertical radii as shares
# of the height; trunk radius at the foot; limbs, their angle from the vertical (degrees) and how far above their
# origin they end (shares of the vertical radius); whether a leader runs to the top with the limbs along it; twigs per
# limb; leaf clumps at LOD0 and their size (share of the horizontal radius); how far the clumps hang (0 up, 1 down);
# how far the cards lie flat (0 any way, 1 level, beech sprays); whether curtains hang to near the ground; bark role,
# bark and leaf tints (display RGB). Optional: `floor`, the shade of the innermost clumps (.66; an open crown is
# lighter inside), `deep`, the share of clumps set deeper in the crown, `shell`, how far the limbs reach out,
# `lobes`, how far past the shell each limb's lobe reaches (1 to 1.15), `scatter`, how far cards turn from the crown's
# normal (.3), `even`, clumps spread evenly over a mound rather than in lobes about the limbs, and `far`, the middle
# level's card size (1; overlapping fine twig fans need less).
# A willow's dome of clumps reaches down to this height on its crown's unit ellipsoid.
WILLOW_DOME = .4
BROADLEAF = {
    'tree': dict(seed=11, fork=.3, crown=(.6, .32, .32), trunk=.72, limbs=4, spread=(30, 65), rise=(.4, 1.1),
                 leader=False, twigs=3, clumps=100, leaf=.42, hang=0, flat=0, curtain=False, bark_role='bark',
                 bark=(.46, .42, .38), leaves=(.82, .95, .76)),
    'tree-broad': dict(seed=12, fork=.24, crown=(.58, .44, .3), trunk=.95, limbs=5, spread=(45, 78), rise=(.1, .8),
                       leader=False, twigs=3, clumps=92, leaf=.4, hang=0, flat=0, curtain=False, bark_role='bark',
                       bark=(.44, .41, .38), leaves=(.76, .9, .7)),
    'tree-slender': dict(seed=13, fork=.08, crown=(.55, .2, .45), trunk=.6, limbs=9, spread=(8, 22), rise=(.2, .6),
                         leader=True, twigs=1, clumps=110, leaf=.85, hang=0, flat=0, curtain=False, bark_role='bark',
                         bark=(.5, .47, .43), leaves=(.8, .94, .74)),
    'tree-layered': dict(seed=14, fork=.2, crown=(.55, .38, .38), trunk=.78, limbs=6, spread=(50, 82),
                         rise=(-.1, .7), leader=False, twigs=3, clumps=100, leaf=.4, hang=0, flat=.35,
                         curtain=False, bark_role='bark', bark=(.55, .53, .5), leaves=(.82, .96, .72)),
    'tree-forked': dict(seed=15, fork=.14, crown=(.6, .36, .34), trunk=.82, limbs=2, spread=(16, 26), rise=(1.1, 1.4),
                        leader=False, twigs=6, clumps=100, leaf=.4, hang=0, flat=0, curtain=False, bark_role='bark',
                        bark=(.47, .43, .39), leaves=(.8, .94, .74)),
    'birch': dict(seed=16, fork=.3, crown=(.6, .26, .38), trunk=.42, limbs=8, spread=(30, 55), rise=(.2, .7),
                  leader=True, twigs=1, clumps=100, leaf=.56, hang=.4, flat=0, curtain=False, bark_role='bark-birch',
                  bark=(.92, .92, .9), leaves=(.9, 1.0, .7), floor=.8),
    'birch-tall': dict(seed=17, fork=.4, crown=(.66, .24, .33), trunk=.44, limbs=8, spread=(28, 50), rise=(.2, .6),
                       leader=True, twigs=1, clumps=100, leaf=.58, hang=.35, flat=0, curtain=False,
                       bark_role='bark-birch', bark=(.9, .9, .88), leaves=(.88, .98, .7), floor=.8),
    'birch-young': dict(seed=18, fork=.22, crown=(.58, .21, .4), trunk=.3, limbs=7, spread=(25, 45), rise=(.2, .7),
                        leader=True, twigs=1, clumps=90, leaf=.6, hang=.3, flat=0, curtain=False,
                        bark_role='bark-birch', bark=(.9, .88, .84), leaves=(.9, 1.0, .68), floor=.8),
    'birch-spreading': dict(seed=19, fork=.3, crown=(.6, .33, .36), trunk=.46, limbs=9, spread=(40, 65),
                            rise=(.1, .6), leader=True, twigs=1, clumps=100, leaf=.52, hang=.45, flat=0, curtain=False,
                            bark_role='bark-birch', bark=(.92, .91, .88), leaves=(.88, 1.0, .72), floor=.8),
    'willow': dict(seed=20, fork=.26, crown=(.6, .38, .3), trunk=.95, limbs=6, spread=(30, 55), rise=(.7, 1.1),
                   leader=False, twigs=2, clumps=96, leaf=.3, hang=1, flat=0, curtain=True, bark_role='bark',
                   bark=(.44, .41, .37), leaves=(.86, 1.0, .72), cutout='willow', snow_cutout='broadleaf'),
    'willow-broad': dict(seed=21, fork=.24, crown=(.58, .47, .28), trunk=1.05, limbs=7, spread=(40, 65),
                         rise=(.6, 1.0), leader=False, twigs=2, clumps=96, leaf=.28, hang=1, flat=0, curtain=True,
                         bark_role='bark', bark=(.44, .41, .37), leaves=(.84, .98, .72), cutout='willow',
                         snow_cutout='broadleaf'),
}
# How each level thins a broadleaf tree: clumps (share), crossed cards per clump, card size, twigs (share), forks per
# twig, limbs kept, limb and twig sides, limb segments, trunk sides and rings; with few clumps they spread evenly over
# the crown. A far level thinned to fit its budget widens its cards to keep the near level's cover. `reach`: how far
# (in card sizes) a spray's base may lie from the wood before a twig grows out to it.
BROADLEAF_LEVELS = (
    dict(clumps=2, cards=1, size=1, twigs=2, forks=1, limbs=99, limb_sides=4, twig_sides=3, segments=3, sides=6,
         rings=4, even=False, reach=.6),
    dict(clumps=.6, cards=1, size=1.8, twigs=.5, limbs=4, limb_sides=3, twig_sides=3, segments=2, sides=5, rings=2,
         even=False, cover=True, reach=1),
    dict(clumps=.17, cards=1, size=2.9, twigs=0, limbs=3, limb_sides=3, twig_sides=3, segments=1, sides=4, rings=1,
         even=True, cover=True))
# Dry plants grow like broadleaf trees, with no winter variant and their own cutouts and bark: tree-dead an old oak
# snag, bleached, its broken limbs ending in fans of bare twigs; foliage-desert a creosote bush, an open vase of thin
# stems under a wide, uneven crown of olive sprays; foliage-barren a big sagebrush, an uneven silvery mound on twisted
# stems. Shrubs stand `height` tall, within their own `budgets`.
SHRUB = dict(height=18, budgets=(480, 240, 96), fork=.03, leader=False, twigs=0, flat=0, curtain=False,
             bark_role='bark', bark_maps=('albedo', 'normal', 'orm'), floor=.85, winter=False)
DRY = {
    'tree-dead': dict(seed=51, fork=.3, crown=(.58, .36, .33), trunk=.85, limbs=5, spread=(22, 62), rise=(.2, 1.0),
                      shell=(.55, .85), leader=False, twigs=3, clumps=36, leaf=.6, hang=0, flat=0, curtain=False,
                      bark_role='bark', bark_texture='dead-wood', bark_maps=('albedo', 'normal', 'orm'),
                      bark=(.8, .78, .74), leaves=(.84, .8, .76), cutout='twig', far=.95, winter=False),
    'foliage-desert': dict(SHRUB, seed=61, crown=(.62, .48, .3), trunk=.38, limbs=8, spread=(20, 50), rise=(.5, 1.0),
                           lobes=(1, 1.35), deep=.3, clumps=85, leaf=.44, hang=0, bark=(.42, .37, .33),
                           leaves=(.7, .76, .54), cutout='creosote'),
    'foliage-barren': dict(SHRUB, seed=62, crown=(.45, .52, .36), trunk=.45, limbs=6, spread=(30, 72), rise=(.1, .7),
                           lobes=(1, 1.3), deep=.4, clumps=95, leaf=.34, hang=.2, scatter=.65, bark=(.5, .46, .42),
                           leaves=(.9, .96, .86), cutout='sagebrush'),
    # Level-one cover of the other families: a hazel, a mountain pine, a spreading juniper, a shrub willow, a snowed
    # juniper and a cinder shrub.
    'foliage-temperate': dict(SHRUB, seed=63, xy=1.15, crown=(.42, .64, .32), trunk=.35, limbs=6, spread=(30, 60),
                              rise=(.6, 1.0), lobes=(1, 1.25), deep=.25, clumps=70, leaf=.48, hang=.2, floor=.75,
                              bark=(.48, .42, .36), leaves=(.84, .96, .7), cutout='broadleaf'),
    'foliage-highland': dict(SHRUB, seed=64, xy=1.2,
                             crown=(.38, .62, .3), trunk=.4, limbs=6, spread=(20, 55), rise=(.4, .9),
                             lobes=(1, 1.25), deep=.25, clumps=75, leaf=.45, hang=.1, floor=.72, bark=(.42, .36, .32),
                             leaves=(.74, .88, .66), cutout='conifer'),
    'foliage-rocky': dict(SHRUB, seed=65, crown=(.38, .62, .3), trunk=.4, limbs=6, spread=(50, 80), rise=(.1, .5),
                          lobes=(1, 1.3), deep=.2, clumps=80, leaf=.42, hang=0, flat=.4, floor=.72,
                          bark=(.46, .4, .36), leaves=(.72, .86, .78), cutout='conifer'),
    'foliage-wetland': dict(SHRUB, seed=66, xy=1.25,
                            crown=(.45, .62, .33), trunk=.35, limbs=7, spread=(25, 55), rise=(.7, 1.1),
                            lobes=(1, 1.2), deep=.2, clumps=80, leaf=.44, hang=.3, bark=(.5, .44, .38),
                            leaves=(.76, .9, .68), cutout='willow'),
    'foliage-snow': dict(SHRUB, seed=67, xy=1.3,
                         crown=(.42, .58, .34), trunk=.4, limbs=6, spread=(45, 78), rise=(.1, .6),
                         lobes=(1, 1.3), deep=.2, clumps=80, leaf=.42, hang=0, flat=.3, bark=(.46, .4, .36),
                         leaves=(.96, .97, 1.0), cutout='conifer-snow', canopy_role='canopy-snow-cutout'),
    'foliage-volcano': dict(SHRUB, seed=68, xy=1.25,
                            crown=(.45, .66, .32), trunk=.4, limbs=5, spread=(20, 55), rise=(.4, .9),
                            lobes=(1, 1.3), deep=.25, clumps=70, leaf=.5, hang=.1, floor=.72, bark_role='bark-volcano',
                            bark_texture='volcano/cinder-bark', bark=(.6, .55, .52), leaves=(.95, .9, .88),
                            cutout='volcano/cinder'),
}
# Cinder trees of the volcano biome, grown like ohia lehua on lava: a gnarled, buttressed trunk whose unequal forks
# divide at staggered heights, under a crown of rust and copper flush (bronze-olive inside). tree-volcano-crown is a
# mature open-grown ohia, tree-volcano-forked a many-trunked spreading one (after pohutukawa), tree-volcano-spire a
# young upright one. Optional keys used here: `gnarl`, `buttress`, `collar` (the root collar's reach), `stagger` and
# `palette` (inner and outer leaf tints).
CINDER_BASE = dict(curtain=False, hang=0, bark_role='bark-volcano', bark_texture='volcano/cinder-bark',
                   bark_maps=('albedo', 'normal', 'orm'), bark=(1, .96, .9), cutout='volcano/cinder', winter=False,
                   gnarl=.6, buttress=.32, collar=1.1, stagger=.35)
CINDER = {
    'tree-volcano-crown': dict(CINDER_BASE, seed=71, fork=.3, crown=(.6, .4, .3), trunk=.95, limbs=5, spread=(30, 70),
                               rise=(.3, 1.0), leader=False, twigs=3, clumps=100, leaf=.4, flat=.15,
                               leaves=(.95, .78, .66), palette=((.6, .6, .46), (.95, .78, .66))),
    'tree-volcano-forked': dict(CINDER_BASE, seed=72, fork=.1, crown=(.62, .44, .3), trunk=1.0, limbs=3,
                                spread=(25, 48), rise=(.9, 1.3), leader=False, twigs=5, clumps=100, leaf=.4, flat=.1,
                                leaves=(.9, .76, .74), palette=((.56, .52, .42), (.9, .76, .74))),
    'tree-volcano-spire': dict(CINDER_BASE, seed=73, fork=.25, crown=(.6, .2, .4), trunk=.7, limbs=8, spread=(20, 45),
                               rise=(.2, .7), leader=True, twigs=1, clumps=100, leaf=.5, flat=0,
                               leaves=(.94, .86, .8), palette=((.62, .6, .5), (.94, .86, .8))),
}
# Orchard trees: pruned apple trees standing in rows, low-forked under broad rounded crowns of leafy apple canopy, red
# apples standing out on the crown (exaggerated, so an orchard reads as one), the broadleaf snow in winter. `near`
# overrides the near level: a lighter trunk and limbs whose only twigs grow out to the leaves, and cards widened as the
# crown thins, so the tight budget keeps the crown closed around its fruit; `tilt` leans an old tree.
ORCHARD_BASE = dict(budgets=(800, 300, 110), curtain=False, hang=.1, flat=.15, twigs=1, bark_role='bark',
                    bark_maps=('albedo', 'normal', 'orm'), bark=(.5, .44, .38), leaves=(.82, .95, .76),
                    cutout='orchard', snow_cutout='broadleaf', lobes=(1, 1.05), shell=(.6, .85), deep=.15,
                    scatter=.2, floor=.68, leader=False, limbs=4, clumps=100, leaf=.42, apples=(10, 6, 4),
                    apple=(.312, .7, .03, 1.3),
                    near=dict(sides=5, rings=2, limb_sides=3, segments=2, twigs=0, cover=True))
ORCHARD = {
    'orchard-round': dict(ORCHARD_BASE, seed=81, fork=.17, crown=(.55, .36, .3), trunk=.55, spread=(40, 65),
                          rise=(.1, .6)),
    'orchard-spreading': dict(ORCHARD_BASE, seed=82, fork=.15, crown=(.5, .4, .26), trunk=.6, spread=(55, 80),
                              rise=(.05, .5)),
    'orchard-upright': dict(ORCHARD_BASE, seed=83, fork=.17, crown=(.58, .32, .3), trunk=.45, spread=(20, 40),
                            rise=(.2, .7)),
    'orchard-vase': dict(ORCHARD_BASE, seed=84, fork=.17, crown=(.56, .36, .3), trunk=.55, spread=(35, 55),
                         rise=(.6, 1.0), deep=.1),
    'orchard-leaning': dict(ORCHARD_BASE, seed=85, fork=.2, crown=(.55, .34, .3), trunk=.6, spread=(30, 65),
                            rise=(.1, .7), tilt=12, gnarl=.5),
    'orchard-young': dict(ORCHARD_BASE, seed=86, fork=.2, crown=(.6, .28, .28), trunk=.35, limbs=3, spread=(25, 50),
                          rise=(.2, .8), clumps=85),
}
# Palms: crown height, the trunk's bend (its bezier control and top offsets, shares of the height), foot and crown
# radii, fronds and their reach (share of the height), their elevations from the youngest to the oldest (degrees), sag
# (shares of the reach), the leaflets' fold (degrees: up in a V, or hanging below 0) and the card's width over its
# reach, dead fronds hanging under the crown and their tint. palm is a date palm, palm-bent a coconut palm. The far
# levels' fewer fronds are wider, to keep the crown's cover.
PALMS = {
    'palm': dict(seed=31, crown=.84, curve=(.02, .03), trunk=1.15, top=.85, fronds=34, reach=.36, elevations=(78, -6),
                 sag=(.05, .5), fold=24, width=.5, dead=10, dry=(.98, .8, .52), cutout='date-palm-frond',
                 bark_role='bark-palm', bark_texture='palm-bark', bark_maps=('albedo', 'normal', 'orm'),
                 bark=(.86, .76, .64), leaves=(.86, .92, .82), winter=False),
    'palm-bent': dict(seed=32, crown=.86, curve=(.2, .24), trunk=.78, top=.5, fronds=24, reach=.4,
                      elevations=(70, -18), sag=(.1, .8), fold=-28, width=.55, dead=4, dry=(.98, .82, .55),
                      cutout='palm-frond', bark_role='bark-palm', bark_texture='palm-bark',
                      bark_maps=('albedo', 'normal', 'orm'), bark=(.84, .76, .66), leaves=(.84, .95, .74),
                      winter=False),
    # The jungle's understory: a fern clump, fronds arching from a stub of rhizome.
    'foliage-jungle': dict(seed=69, height=18, budgets=(480, 240, 96), crown=.03, curve=(0, 0), trunk=.35, top=.3,
                           fronds=22, reach=.62, elevations=(80, 12), sag=(.15, .85), fold=18, width=.65, dead=2,
                           dry=(.95, .8, .55), cutout='fern', bark_role='bark', bark_maps=('albedo', 'normal', 'orm'),
                           bark=(.4, .35, .3), leaves=(.82, .95, .7), winter=False),
}
PALM_LEVELS = (dict(fronds=1, segments=3, fold=True, dead=1, sides=8, rings=10, width=1),
               dict(fronds=.55, segments=2, fold=False, dead=.5, sides=6, rings=4, width=1.15),
               dict(fronds=.45, segments=1, fold=False, dead=.3, sides=4, rings=2, width=1.2))
# Saguaros: column radius at the foot, arms, their radius (share of the column's) and heights (shares of the height),
# the skin's ribs repeats around and whether they bloom (white flowers on the crown and arm tips). Every level keeps
# every arm, so the outline holds at a distance.
CACTI = {
    'cactus': dict(seed=41, trunk=1.6, arms=3, arm=.7, heights=(.3, .58), around=3, flowers=False,
                   bark=(.95, .98, .94)),
    'cactus-flowers': dict(seed=42, trunk=1.5, arms=2, arm=.72, heights=(.36, .6), around=3, flowers=True,
                           bark=(.96, .98, .95)),
}
for spec in CACTI.values():
    spec.update(bark_role='cactus', bark_texture='cactus-skin', bark_maps=('albedo', 'normal'),
                canopy_role='flower-cutout', cutout='cactus-flower', leaves=(1, 1, 1), winter=False)
CACTUS_LEVELS = (dict(sides=12, rings=10, cap=4, arm_sides=8, arm_rings=8, arm_cap=4, blossoms=4),
                 dict(sides=7, rings=4, cap=2, arm_sides=6, arm_rings=4, arm_cap=2, blossoms=2),
                 dict(sides=5, rings=2, cap=1, arm_sides=4, arm_rings=2, arm_cap=0, blossoms=2))


def variants(plants):
    """Every shrub family grows three shapes, each its own seed: the second lower and wider, the third taller and
    narrower (a fern clump: its fronds longer or shorter)."""
    grown = {}
    for name, spec in plants.items():
        grown[name] = spec
        for k, wide in ((2, 1.15), (3, .88)) if name.startswith('foliage-') else ():
            if isinstance(spec['crown'], tuple):
                centre, rx, rz = spec['crown']
                shape = dict(crown=(centre / wide ** .5, rx * wide, rz / wide))
            else:
                shape = dict(reach=spec['reach'] * wide, fronds=round(spec['fronds'] / wide))
            grown[f'{name}-{k}'] = dict(spec, seed=spec['seed'] * 7 + k, **shape)
    return grown


DRY, PALMS = variants(DRY), variants(PALMS)
SPECIES = {**CONIFERS, **BROADLEAF, **DRY, **CINDER, **ORCHARD, **PALMS, **CACTI}


def species(name):
    """The species a file grows: its own, or a winter form's (pine-tall-snow) bare species."""
    return name if name in SPECIES else name.removesuffix('-snow')


def family(name):
    name = species(name)
    return 'conifer' if name in CONIFERS else 'palm' if name in PALMS else 'cactus' if name in CACTI else 'broadleaf'


def snow_scale(spec):
    """The linear factor that turns the species' leaf tint grey on the snow cutout, its brightest channel kept."""
    tint = [linear(c) for c in spec['leaves']]
    return [round(max(tint) / c, 6) for c in tint]


MAPS = {'albedo': 'DIFFUSE', 'normal': 'NORMAL', 'orm': 'AMBIENT'}


def materials(kind, spec, snow):
    """The bark (or cactus skin) and the canopy's cutout. A tree with a winter variant carries it on the canopy (its
    winter file is that variant); a plant without one keeps its own cutout in winter, its snowy cards still taking the
    snow's response."""
    winter = spec.get('winter', True)
    cutout = spec.get('cutout', kind)
    if snow and winter:
        cutout = spec.get('snow_cutout', kind) + '-snow'
    canopy = {'id': spec.get('canopy_role', 'canopy-snow-cutout' if snow else 'canopy-cutout'),
              'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0, 'alphaTest': .5, 'textures': [
                  {'id': 'canopy', 'type': role, 'wrapS': 33071, 'wrapT': 33071,
                   'filename': f'../textures/vegetation/{cutout}-cutout_{suffix}.png'}
                  for suffix, role in MAPS.items()]}
    if winter and not snow:
        snowy = spec.get('snow_cutout', kind)
        canopy['extras'] = {'mmVariants': {'snow': {
            'name': 'canopy-snow-cutout',
            'textures': {role: f'../textures/vegetation/{snowy}-snow-cutout_{suffix}.png'
                         for role, suffix in (('baseColor', 'albedo'), ('normal', 'normal'), ('occlusion', 'orm'))},
            'colourScale': snow_scale(spec)}}}
    role = spec.get('bark_role', 'bark')
    texture = spec.get('bark_texture', 'birch-bark' if role == 'bark-birch' else 'bark')
    bark = {'id': role, 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
            'textures': [{'id': role, 'type': MAPS[suffix],
                          'filename': f'../textures/vegetation/{texture}_{suffix}.png'}
                         for suffix in spec.get('bark_maps', ('albedo',))]}
    if 'apple' not in spec:
        return [bark, canopy]
    # Apples are solid balls sampling an apple of the canopy's own (summer) cutout.
    fruit = {'id': 'fruit', 'diffuse': [1, 1, 1], 'roughness': 1, 'metallic': 0,
             'textures': [{'id': 'fruit', 'type': role,
                           'filename': f'../textures/vegetation/{spec["cutout"]}-cutout_{suffix}.png'}
                          for suffix, role in MAPS.items()]}
    return [bark, canopy, fruit]


def add(a, b, s=1.0):
    return [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def length(v):
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def normalized(v):
    size = length(v) or 1
    return [v[0] / size, v[1] / size, v[2] / size]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def bezier(a, b, c, t):
    return [(1 - t) ** 2 * a[i] + 2 * (1 - t) * t * b[i] + t * t * c[i] for i in range(3)]


def along_line(points, share):
    """The point a share of the way along a polyline."""
    rest = share * sum(length(sub(b, a)) for a, b in zip(points, points[1:]))
    for a, b in zip(points, points[1:]):
        step = length(sub(b, a))
        if rest <= step or b is points[-1]:
            return add(a, sub(b, a), min(1.0, rest / step) if step else 0.0)
        rest -= step


class Tree:
    """One level's geometry: interleaved vertices and the bark, canopy and fruit index lists."""

    def __init__(self, kind, spec, rng):
        self.kind, self.spec, self.rng = kind, spec, rng
        self.vertices, self.parts = [], {'bark': [], 'canopy': [], 'fruit': []}
        # A slight lean, or a strong one (`tilt`, an old orchard tree).
        self.lean = [rng.uniform(-.25, .25) * spec.get('tilt', 1) for _ in range(2)]
        self.stem = STEMS.get(spec.get('cutout', kind), .5)
        # A gnarled trunk wanders about its lean (`gnarl`, units), each tree its own way.
        self.gnarl = [rng.uniform(0, math.tau) for _ in range(2)] if spec.get('gnarl') else None
        if kind == 'conifer':
            self.crown_base = spec['base'] * HEIGHT
        elif kind == 'broadleaf':
            centre, rx, rz = spec['crown']
            self.centre = [0, 0, centre * HEIGHT]
            self.radii = (rx * HEIGHT, rz * HEIGHT)
            self.fork = spec['fork'] * HEIGHT

    def vertex(self, p, n, color, uv):
        self.vertices.extend([*p, *n, *color, 1.0, *uv])
        return len(self.vertices) // 12 - 1

    def axis(self, z):
        """The trunk's centre at height z: straight, with a slight lean that grows toward the top."""
        t = (z / HEIGHT) ** 2
        x, y = self.lean[0] * t, self.lean[1] * t
        if self.gnarl:
            # Broad bends rather than kinks, none at the foot.
            bend = self.spec['gnarl'] * min(1, z / 3)
            x += bend * math.sin(z * .32 + self.gnarl[0])
            y += bend * math.sin(z * .27 + self.gnarl[1])
        return [x, y, z]

    def trunk_radius(self, z):
        foot = self.spec['trunk']
        if self.kind == 'conifer':
            return foot * max(0.0, 1 - z / (HEIGHT * .97)) ** 1.25 * (1 + .55 * math.exp(-z / .7)) + .03
        return foot * (1 - .4 * min(1, z / max(self.fork, 1))) * (1 + .55 * math.exp(-z / .7))

    def surface(self, grid, normals, colors, uvs):
        """Both faces of a canopy grid of rows of points, each cell two triangles a face."""
        for face in (1, -1):
            ids = [[self.vertex(p, normals[i][j], colors[i][j], uvs[i][j]) for j, p in enumerate(row)]
                   for i, row in enumerate(grid)]
            for i in range(len(grid) - 1):
                for j in range(len(grid[0]) - 1):
                    a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                    self.parts['canopy'].extend((a, b, c, a, c, d) if face == 1 else (a, c, b, a, d, c))

    def trunk(self, sides, rings, top, shade_from):
        """The trunk up to `top`, rings crowding at the flare; above `shade_from` it stands in the crown's shade."""
        spec = self.spec
        heights = [top * (k / rings) ** 1.6 for k in range(rings + 1)]
        lobes = self.rng.uniform(0, math.tau)
        circumference = math.tau * spec['trunk']
        ids = []
        for z in heights:
            centre, radius = self.axis(z), self.trunk_radius(z)
            flare = math.exp(-z / spec.get('collar', .7))
            # The root collar is darker with soil and moss.
            shade = (.8 + .2 * min(1, z / 2.5)) * (1 - .4 * min(1, max(0, z - shade_from) / 3))
            row = []
            for k in range(sides + 1):
                angle = math.tau * k / sides
                # The flare spreads into root buttresses.
                r = radius * (1 + spec.get('buttress', .22) * flare * math.cos(3 * angle + lobes))
                if 'buttress' in spec:
                    # Uneven lobes: a fifth harmonic breaks the three into a gnarled foot.
                    r *= 1 + .4 * spec['buttress'] * flare * math.cos(5 * angle + 2 * lobes)
                direction = [math.cos(angle), math.sin(angle), 0]
                row.append(self.vertex([centre[0] + direction[0] * r, centre[1] + direction[1] * r, z],
                                       normalized([direction[0], direction[1], .15 + .6 * flare]),
                                       [c * shade for c in spec['bark']], [k / sides * 2, -z / (circumference * 1.6)]))
            ids.append(row)
        # The trunk is closed: its outside faces alone.
        for i in range(rings):
            for j in range(sides):
                a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                self.parts['bark'].extend((a, b, c, a, c, d))

    def tube(self, points, radii, sides, shade, around=1, cap=0):
        """A bark tube along points, its rings turned by a parallel frame so it never twists, its texture repeating
        `around` times about it. Its last `cap` rings close it as a dome, their normals turning up the tube's end."""
        circumference = math.tau * self.spec['trunk']
        tangent = normalized(sub(points[1], points[0]))
        side = normalized(cross(tangent, [0, 0, 1] if abs(tangent[2]) < .9 else [1, 0, 0]))
        travelled, ids = 0.0, []
        for i, (point, radius) in enumerate(zip(points, radii)):
            if i:
                travelled += length(sub(point, points[i - 1]))
                tangent = normalized(sub(points[min(i + 1, len(points) - 1)], points[i - 1]))
                side = normalized(cross(cross(tangent, side), tangent))
            other = cross(tangent, side)
            tilt = math.pi / 2 * max(0, i - (len(points) - 1 - cap)) / cap if cap else 0
            row = []
            for k in range(sides + 1):
                angle = math.tau * k / sides
                direction = add([c * math.cos(angle) for c in side], other, math.sin(angle))
                normal = normalized(add([c * math.cos(tilt) for c in direction], tangent, math.sin(tilt)))
                row.append(self.vertex(add(point, direction, radius), normal,
                                       [c * shade for c in self.spec['bark']],
                                       [k / sides * around, -travelled * around / (circumference * 1.6)]))
            ids.append(row)
        for i in range(len(points) - 1):
            for j in range(sides):
                a, b, c, d = ids[i][j], ids[i][j + 1], ids[i + 1][j + 1], ids[i + 1][j]
                self.parts['bark'].extend((a, b, c, a, c, d))

    def stubs(self, count):
        """Dead branch stubs on the trunk below the crown: thin three-sided spikes angled down."""
        rng = self.rng
        for _ in range(count):
            z = rng.uniform(2.5, self.crown_base * 1.05)
            azimuth = rng.uniform(0, math.tau)
            direction = [math.cos(azimuth), math.sin(azimuth), 0]
            centre, radius = self.axis(z), self.trunk_radius(z)
            reach = rng.uniform(.8, 2.0) * (1 - .4 * z / max(self.crown_base, 1))
            tip = add(add(centre, direction, radius + reach), [0, 0, -reach * rng.uniform(.2, .6)])
            side = [-direction[1], direction[0], 0]
            thick = .07 + .03 * rng.random()
            ring = [add(add(add(centre, direction, radius * .7), side, thick * math.cos(a)),
                        [0, 0, thick * math.sin(a)]) for a in (0, math.tau / 3, 2 * math.tau / 3)]
            color = [c * .82 for c in self.spec['bark']]
            for k in range(3):
                a, b = ring[k], ring[(k + 1) % 3]
                n = normalized(cross(sub(b, a), sub(tip, a)))
                self.parts['bark'].extend(self.vertex(p, n, color, uv)
                                          for p, uv in ((a, (0, 0)), (b, (.25, 0)), (tip, (.12, -.4))))

    # Conifers

    def reach(self, z):
        """The conifer crown's radius at height z."""
        t = (HEIGHT - z) / (HEIGHT - self.crown_base)
        if t <= 0:
            return 0
        t = min(t, 1)
        # Open-grown crowns round off a little at their lowest whorls.
        return self.spec['radius'] * HEIGHT * t ** self.spec['exponent'] * (1 - .18 * max(0, t - .88) / .12)

    def cone_normal(self, p):
        """The conifer crown's outward normal at p: the cone's normal near its surface, turning up toward the trunk."""
        centre = self.axis(p[2])
        dx, dy = p[0] - centre[0], p[1] - centre[1]
        r = math.hypot(dx, dy)
        slope = self.spec['radius'] * HEIGHT / (HEIGHT - self.crown_base)
        w = min(1, r / max(self.reach(p[2]), 1e-3))
        cone = normalized([dx / (r or 1), dy / (r or 1), slope + .25])
        return normalized([cone[0] * w, cone[1] * w, cone[2] * w + (1 - w)])

    def branch(self, z, azimuth, reach, t, segments, width, fold):
        """One branch card from the trunk at height z, its relative crown depth t (0 at the top, 1 at the base)."""
        spec, rng = self.spec, self.rng
        lerp = lambda pair: pair[0] + (pair[1] - pair[0]) * t  # noqa: E731
        elevation = math.radians(lerp(spec['angles']) + rng.uniform(-6, 6))
        sag, upturn = lerp(spec['sag']) * rng.uniform(.8, 1.2), lerp(spec['upturn']) * rng.uniform(.7, 1.3)
        droop = [math.radians(lerp((a, b)) + rng.uniform(-5, 5)) for a, b in zip(*spec['droop'])]
        if not fold:
            # A flat card keeps a little of the droop as a lowered stem line.
            droop = [angle * .35 for angle in droop]
        roll = math.radians(rng.uniform(-10, 10))
        mirror = rng.random() < .5
        direction = [math.cos(azimuth), math.sin(azimuth), 0]
        # The spray's narrow base passes behind the trunk, so its full width starts at the trunk.
        start = add(self.axis(z), direction, -.1 * reach)
        reach *= 1.1
        half = reach * width * spec['width'] * .5
        tint = self.tint()
        # The inner crown is dark: shade by the distance from the trunk and the depth in the crown.
        inner = .66 + .1 * (1 - t)
        stem = STEMS['conifer'] if not mirror else 1 - STEMS['conifer']
        edges = (0.0, 1.0) if not mirror else (1.0, 0.0)
        rows, normals, colors, uvs = [], [], [], []
        for i in range(segments + 1):
            s = i / segments
            rise = reach * (math.tan(elevation) * s - sag * s * s + upturn * s ** 3)
            point = add(add(start, direction, reach * s), [0, 0, rise])
            slope = math.tan(elevation) - 2 * sag * s + 3 * upturn * s * s
            tangent = normalized(add(direction, [0, 0, slope]))
            side = normalized(cross([0, 0, 1], tangent))
            up = normalized(cross(tangent, side))
            side = add([c * math.cos(roll) for c in side], up, math.sin(roll))
            up = normalized(cross(tangent, side))
            angle = droop[0] + (droop[1] - droop[0]) * s
            left = add(add(point, side, half * math.cos(angle)), up, -half * math.sin(angle))
            right = add(add(point, side, -half * math.cos(angle)), up, -half * math.sin(angle))
            # The lowest branches rest on the ground rather than passing through it.
            row = [[p[0], p[1], max(p[2], .05)] for p in ([left, point, right] if fold else [left, right])]
            rows.append(row)
            # Out along the branch its top faces the sky, so whorl tops catch the sun from above.
            normals.append([normalized(add([c * (1 - .6 * s) for c in self.cone_normal(p)], up, .6 * s))
                            for p in row])
            shade = inner + (1 - inner) * s
            # New growth lightens the tips.
            shade *= 1 + .15 * s ** 2
            # The hanging side shoots are the tier's shaded underside.
            colors.append([[c * shade * (.88 if fold and j != 1 else 1) for c in tint] for j in range(len(row))])
            v = BASE_V + (TIP_V - BASE_V) * s
            uvs.append([[edges[0], v], [stem, v], [edges[1], v]] if fold else [[edges[0], v], [edges[1], v]])
        self.surface(rows, normals, colors, uvs)

    def upright(self, z0, z1, width, azimuth, shade):
        """A vertical card standing on the axis (the leader and the dark core), the spray pointing up."""
        side = [math.cos(azimuth), math.sin(azimuth), 0]
        stem = STEMS['conifer']
        rows, normals, colors, uvs = [], [], [], []
        for z, v in ((z0, BASE_V), (z1, TIP_V)):
            centre = self.axis(z)
            row = [add(centre, side, width * stem), add(centre, side, -width * (1 - stem))]
            rows.append(row)
            normals.append([normalized(add([0, 0, 1], self.cone_normal(p), .5)) for p in row])
            colors.append([[c * shade for c in self.spec['leaves']]] * 2)
            uvs.append([[0, v], [1, v]])
        self.surface(rows, normals, colors, uvs)

    def conifer(self, level, thinning):
        spec, rng = self.spec, self.rng
        self.trunk(level['sides'], level['rings'], HEIGHT * .96, self.crown_base)
        if level['stubs']:
            self.stubs(spec['stubs'])
        if level['per_whorl']:
            whorls = max(3, round(spec['whorls'] * level['whorls'] * thinning ** .6))
            per_whorl = max(3, round(spec['per_whorl'] * level['per_whorl'] * thinning ** .4))
        else:
            whorls, per_whorl = max(6, round(spec['whorls'] * spec['per_whorl'] * level['whorls'] * thinning)), 1
        between = round(spec['between'] * level['between'])
        leader = HEIGHT * .07
        top = HEIGHT - leader * .7
        widest = spec['radius'] * HEIGHT
        # Internodes shorten toward the top, where the newest whorls sit.
        span = top - self.crown_base
        heights = [self.crown_base + span * (1 - (1 - k / whorls) ** 1.25) for k in range(whorls)]
        phase = rng.uniform(0, math.tau)

        def grow(z, azimuth, scale):
            t = (top - z) / span
            reach = (self.reach(z) * rng.uniform(.82, 1.06) + .4) * scale
            segments = level['segments'] if reach > LONG * widest else 1
            self.branch(z, azimuth, reach, t, segments, level['width'], level['fold'])

        for k, z in enumerate(heights):
            z += rng.uniform(-.15, .15) * span / whorls
            phase += 2.39996
            count = per_whorl if (top - z) / span > .12 or per_whorl == 1 else max(3, per_whorl - 1)
            for b in range(count):
                grow(z, phase + math.tau * (b + rng.uniform(-.18, .18)) / count, 1)
            # Smaller branches grow between the whorls.
            gap = (heights[k + 1] if k + 1 < whorls else top) - z
            for b in range(between):
                grow(z + gap * rng.uniform(.35, .65), phase + rng.uniform(0, math.tau), rng.uniform(.6, .78))
        # A dark core of upright cards fills the crown between the branches.
        cores = level['core']
        for k in range(cores):
            z0 = self.crown_base + span * k / max(cores, 1) * .8
            z1 = z0 + span * .38
            for turn in (0, math.pi / 2):
                self.upright(z0, z1, self.reach(z0) * level['core_width'], phase + k * 1.1 + turn, .64)
        # The leader: the top shoot, crossed upright sprays reaching exactly the full height.
        for k in range(level['leader']):
            self.upright(HEIGHT - leader, HEIGHT, leader * .55, phase + k * math.pi / 2, 1.0)

    def tint(self):
        """The species' leaf tint, varied in value alone: the snow variant's colour scale must turn every card grey."""
        value = self.rng.uniform(.94, 1.06)
        return [c * value for c in self.spec['leaves']]

    # Broadleaf trees

    def depth(self, p):
        """How far p lies from the crown's centre toward its ellipsoid: 0 at the centre, 1 on it."""
        rx, rz = self.radii
        q = sub(p, self.centre)
        return math.sqrt((q[0] / rx) ** 2 + (q[1] / rx) ** 2 + (q[2] / rz) ** 2)

    def ellipsoid_normal(self, p):
        rx, rz = self.radii
        q = sub(p, self.centre)
        return normalized([q[0] / rx ** 2, q[1] / rx ** 2, q[2] / rz ** 2])

    def inside(self, p, limit):
        """p pulled toward the crown's centre until it lies within `limit` of the ellipsoid."""
        d = self.depth(p)
        return p if d <= limit else add(self.centre, sub(p, self.centre), limit / d)

    def shell(self, azimuth, z, share):
        """The point at `share` of the ellipsoid's horizontal radius at height z, toward azimuth."""
        rx, rz = self.radii
        h = max(0.0, 1 - ((z - self.centre[2]) / rz) ** 2)
        r = rx * math.sqrt(h) * share
        return [self.centre[0] + math.cos(azimuth) * r, self.centre[1] + math.sin(azimuth) * r, z]

    def skeleton(self, level, thinning=1.0):
        """Limbs from the fork (or along a leader) and their twigs, fewer as the level thins: lists of points with radii
        and ends for clumps."""
        spec, rng = self.spec, self.rng
        rx, rz = self.radii
        top = self.centre[2] + rz * .92
        fork = self.axis(self.fork)
        branches, tips = [], []
        phase = rng.uniform(0, math.tau)
        count = spec['limbs']
        limbs = []
        if spec['leader']:
            points = [self.axis(self.fork + (top - self.fork) * k / 3) for k in range(4)]
            radius = self.trunk_radius(self.fork)
            branches.append((points, [radius * (1 - .85 * k / 3) for k in range(4)], 'limb'))
        for i in range(count):
            phase += 2.39996
            azimuth = phase + rng.uniform(-.3, .3)
            if spec['leader']:
                origin = self.axis(self.fork + (top - self.fork) * (i + rng.uniform(.1, .7)) / count * .85)
            elif spec.get('stagger'):
                # Forks divide at different heights up the trunk, not all from one point.
                origin = self.axis(self.fork + rz * spec['stagger'] * rng.random())
            else:
                origin = fork
            lift = rz * rng.uniform(*spec['rise'])
            z = min(origin[2] + lift, self.centre[2] + rz * .8)
            end = self.shell(azimuth, z, rng.uniform(*spec.get('shell', (.72, .92))))
            span = length(sub(end, origin))
            angle = math.radians(rng.uniform(*spec['spread']))
            start = [math.sin(angle) * math.cos(azimuth), math.sin(angle) * math.sin(azimuth), math.cos(angle)]
            control = add(origin, start, span * .5)
            if spec['curtain']:
                # Willow limbs arch up and over before their curtains fall.
                control = add(control, [0, 0, span * .3])
            radius = self.trunk_radius(self.fork) * (.62 if count > 2 else .78) * (.5 if spec['leader'] else 1)
            if spec.get('stagger'):
                radius *= rng.uniform(.75, 1.1)
            limbs.append((origin, control, end, radius, span))
        limbs.sort(key=lambda limb: -limb[3] * limb[4])
        for origin, control, end, radius, span in limbs[:level['limbs']]:
            segments = level['segments']
            points = [bezier(origin, control, end, k / segments) for k in range(segments + 1)]
            radii = [max(.06, radius * (1 - .8 * k / segments)) for k in range(segments + 1)]
            branches.append((points, radii, 'limb'))
            tips.append((end, 1.0))
            twigs = round(spec['twigs'] * level['twigs'] * thinning)
            for _ in range(twigs):
                s = rng.uniform(.35, .85)
                base = bezier(origin, control, end, s)
                azimuth = math.atan2(end[1] - self.centre[1], end[0] - self.centre[0]) + rng.uniform(-1.2, 1.2)
                z = base[2] + rz * rng.uniform(-.25, .45)
                z = max(self.centre[2] - rz * .7, min(z, self.centre[2] + rz * .85))
                tip = self.inside(self.shell(azimuth, z, rng.uniform(.82, .98)), .95)
                middle = add(bezier(base, base, tip, .5), [0, 0, length(sub(tip, base)) * .12])
                twig = max(.04, radius * (1 - .8 * s) * .5)
                branches.append(([base, middle, tip], [twig, twig * .6, .03], 'twig'))
                tips.append((tip, .8))
                for _ in range(level.get('forks', 0)):
                    # A side shoot leaves the twig's outer half for its own part of the shell, so the gaps between
                    # the leaf clumps show wood branching all the way out.
                    shoot = bezier(base, middle, tip, rng.uniform(.4, .7))
                    turn = azimuth + rng.choice((-1, 1)) * rng.uniform(.35, .8)
                    z = shoot[2] + rz * rng.uniform(-.15, .35)
                    z = max(self.centre[2] - rz * .7, min(z, self.centre[2] + rz * .85))
                    end = self.inside(self.shell(turn, z, rng.uniform(.8, .97)), .95)
                    bend = add(bezier(shoot, shoot, end, .5), [0, 0, length(sub(end, shoot)) * .1])
                    branches.append(([shoot, bend, end], [twig * .6, twig * .4, .03], 'twig'))
                    tips.append((end, .6))
        return branches, tips

    def clump(self, centre, size, cards, hang, curtain, value=1.0):
        """A clump of leaf cards around centre, facing out of the crown so the iso and top views see their faces, the
        twig in each running up (or, as clumps hang, down) the crown's surface; shaded as a dome, times value. A
        curtain hangs straight down from centre instead. Returns where its sprays start."""
        spec, rng = self.spec, self.rng
        out = self.ellipsoid_normal(centre)
        if spec['flat']:
            # Beech sprays lie level.
            out = normalized(add(out, [0, 0, 1], spec['flat'] * 2))
        # Cards tip up a little so the rim's clumps still show their faces from above.
        facing = normalized(add(add(out, [0, 0, .35]), [rng.gauss(0, spec.get('scatter', .3)) for _ in range(3)]))
        if spec['twigs'] and out[2] > .6:
            # A tree's top clumps lie open to the sky, none standing proud of the crown.
            facing = normalized(add(facing, [0, 0, 1], 3 * (out[2] - .6)))
        if curtain:
            facing = normalized([out[0], out[1], 0]) if math.hypot(out[0], out[1]) > .1 else [1, 0, 0]
        # The twig runs along the card: up the surface, or down it as the clumps hang.
        along = add([0, 0, 1 - 2 * hang], [rng.gauss(0, .5) for _ in range(3)])
        along = sub(along, [c * sum(a * b for a, b in zip(along, facing)) for c in facing])
        if length(along) < 1e-3:
            along = cross(facing, [1, 0, 0])
        along = normalized(along)
        if curtain:
            along = [0, 0, -1]
        # A clump low in a shrub stands on its card's height, never lying flat on the ground.
        centre = [centre[0], centre[1], max(centre[2], size * .55)]
        tint = self.tint()
        depth = self.depth(centre)
        if 'palette' in spec:
            # A crown of mixed flush: bronze-olive inside, copper toward its outer tips, each clump its own share.
            inner, outer = spec['palette']
            mix = min(1, max(0, (depth - .45) / .55 + rng.uniform(-.25, .25)))
            value = tint[1] / spec['leaves'][1]
            tint = [(a + (b - a) * mix) * value for a, b in zip(inner, outer)]
        rz = self.radii[1]
        # Inner and lower clumps are darker (less so in an open crown); each clump varies a little, so they read apart.
        floor = spec.get('floor', .66)
        shade = (floor + .4 * min(1, max(0, (depth - .35) / .65)) ** 1.2) * rng.uniform(.9, 1.08) * value
        shade *= 1 - .15 * min(1, max(0, (self.centre[2] - centre[2]) / rz))
        dome = sub(centre, [c * size * .45 for c in out])
        tall = size
        if curtain:
            # A curtain falls from the shell toward the ground, never touching it.
            tall = min(size * 2.6 * rng.uniform(.8, 1.5), centre[2] - HEIGHT * .08)
        stem = self.stem
        for k in range(cards):
            # Further cards of a clump turn about the twig, giving it depth.
            turn = k * math.radians(rng.uniform(50, 70))
            across = normalized(add([c * math.cos(turn) for c in cross(facing, along)], facing, math.sin(turn)))
            base = add(centre, along, 0 if curtain else -tall * .5)
            rows, normals, colors, uvs = [], [], [], []
            mirror = rng.random() < .5
            for s, v in ((0, BASE_V), (1, TIP_V)):
                middle = add(base, along, tall * s)
                # Low cards rest on the ground rather than passing through it.
                row = [[p[0], p[1], max(p[2], .05)]
                       for p in (add(middle, across, size * stem), add(middle, across, -size * (1 - stem)))]
                rows.append(row)
                normals.append([normalized(add(self.ellipsoid_normal(p), normalized(sub(p, dome)))) for p in row])
                lit = shade * (1 - .12 * (1 - s) if not curtain else .85 + .15 * (1 - s))
                colors.append([[tint[0] * lit, tint[1] * lit, tint[2] * lit]] * 2)
                uvs.append([[1, v], [0, v]] if mirror else [[0, v], [1, v]])
            self.surface(rows, normals, colors, uvs)
        return base

    def broadleaf(self, level, thinning):
        spec, rng = self.spec, self.rng
        branches, tips = self.skeleton(level, thinning)
        trunk_top = self.fork + (1.5 if not spec['leader'] else 0)
        self.trunk(level['sides'], level['rings'], trunk_top, self.fork)
        for points, radii, role in branches:
            sides = level['limb_sides'] if role == 'limb' else level['twig_sides']
            self.tube(points, radii, sides, .72)
        count = max(8, round(spec['clumps'] * level['clumps'] * thinning))
        size = spec['leaf'] * self.radii[0] * level['size']
        if level.get('cover'):
            # Level sprays (the beech's) already cover more from above than upright cards do.
            size *= (1 if level['even'] else spec.get('far', 1)) * (1 - .3 * spec['flat']) / math.sqrt(thinning)
        rx, rz = self.radii
        # Clumps cover the crown's shell in lobes around the branches' directions, and its top. Each lobe reaches out
        # its own way past the shell (never inside it, which would open the crown), so crowns are unevenly lobed.
        lobes = [(normalized([(tip[0] - self.centre[0]) / rx, (tip[1] - self.centre[1]) / rx,
                              (tip[2] - self.centre[2]) / rz]), weight, rng.uniform(*spec.get('lobes', (1, 1.15))))
                 for tip, weight in tips]
        lobes.append(([0, 0, 1], 3, 1.0))
        weights = [w for _, w, _ in lobes]
        # A crown grown with twigs leaves no clump floating at the near levels (see below).
        grown = spec['twigs'] and not level['even'] and not spec['curtain']
        wood = [along_line(points, k / 6) for points, _, _ in branches for k in range(1, 7)] if grown else []
        leaves = []
        phase = rng.uniform(0, math.tau)
        for k in range(count):
            # A willow's top is a dome of larger drooping clumps over its arched limbs, spread evenly so the top view
            # sees a closed crown; every other clump hangs from the shell below as a curtain.
            curtain = spec['curtain'] and k % 2 == 1
            dome = spec['curtain'] and not curtain
            extent = 1.0
            if dome:
                # A Fibonacci spiral over the dome.
                j = k // 2
                z = 1 - (1 - WILLOW_DOME) * (j + .5) / ((count + 1) // 2)
                ring = math.sqrt(1 - z * z)
                direction = [ring * math.cos(phase + j * 2.39996), ring * math.sin(phase + j * 2.39996), z]
            elif level['even'] or spec.get('even'):
                # A Fibonacci spiral over the crown, from its top down to its flattened base (a mound's every level).
                z = 1 - 1.6 * (k + .5) / count
                ring = math.sqrt(1 - z * z)
                direction = [ring * math.cos(phase + k * 2.39996), ring * math.sin(phase + k * 2.39996), z]
            else:
                lobe, _, extent = rng.choices(lobes, weights)[0]
                direction = normalized(add(lobe, [rng.gauss(0, .45) for _ in range(3)]))
            # Open-grown crowns are flatter beneath; excurrent crowns reach down their leader.
            direction[2] = max(direction[2], -.95 if spec['leader'] else -.7)
            # Some clumps sit deeper, more of them under the top, so the top view finds no hollow rings; a dense
            # shrub fills its mound with them.
            outer = 1 - spec.get('deep', .25 if direction[2] > .3 else .15)
            depth = rng.uniform(.72, 1.0) if rng.random() < outer else rng.uniform(.4, .72)
            centre = add(self.centre, [direction[0] * rx, direction[1] * rx, direction[2] * rz], depth * extent)
            if curtain:
                centre[2] = max(centre[2], self.centre[2] - rz * .2)
            # Far curtains are fewer, so wider (their length is bounded by the ground).
            scale = (1.35 if dome else 1.3 if curtain and level.get('cover') else 1) * rng.uniform(.85, 1.15)
            # The dome's strands fall every way over it, a little darker than the curtains catching the light.
            base = self.clump(centre, size * scale, level['cards'], .5 if dome else spec['hang'], curtain,
                              .9 if dome else 1)
            if wood:
                leaves.append(base)
        # The wood grows out to every spray it does not reach yet, so no leaves float in the air: a thin twig from the
        # nearest wood to the spray's base, which also carries the sprays beside it.
        for base in leaves:
            near = min(wood, key=lambda p: length(sub(p, base)))
            if length(sub(base, near)) > size * level['reach']:
                self.tube([near, base], [.06, .03], level['twig_sides'], .72)
                wood += [along_line([near, base], k / 3) for k in range(1, 4)]

    def apples(self, count, sides, rings):
        """Apples on the outside of the crown's top and sides, where the iso and top views find them: small solid balls
        (`apple`: an apple's UV centre and radius in the cutout, and the ball's diameter) whose texels are that apple,
        `sides` round and `rings` of latitude between their poles. A far level's fewer apples are larger, keeping the
        crown's share of fruit."""
        if not count:
            return
        u, v, reach, diameter = self.spec['apple']
        rng = self.rng
        rx, rz = self.radii
        phase = rng.uniform(0, math.tau)
        for k in range(count):
            # A Fibonacci spiral over the crown, never its underside.
            z = .9 - 1.25 * (k + .5) / count
            ring = math.sqrt(1 - z * z)
            angle = phase + k * 2.39996 + rng.uniform(-.3, .3)
            share = rng.uniform(.86, .96)
            centre = add(self.centre, [ring * math.cos(angle) * rx, ring * math.sin(angle) * rx, z * rz], share)
            r = diameter * .5 * math.sqrt(self.spec['apples'][0] / count) * rng.uniform(.85, 1.15)
            spin = rng.uniform(0, math.tau)
            # A little flattened: poles on the apple's centre texel, the widest ring on the apple's edge.
            points = [([0, 0, r * .9], (u, v)), ([0, 0, -r * .9], (u, v))]
            for k in range(rings):
                latitude = math.pi / 2 - math.pi * (k + 1) / (rings + 1)
                across, up = math.cos(latitude), math.sin(latitude)
                for j in range(sides):
                    turn = j * math.tau / sides
                    point = [r * across * math.cos(spin + turn), r * across * math.sin(spin + turn), r * .9 * up]
                    points.append((point, (u + reach * across * math.cos(turn), v + reach * across * math.sin(turn))))
            ids = [self.vertex(add(centre, p), normalized(p), [1, 1, 1], uv) for p, uv in points]
            ring = lambda k, j: ids[2 + k * sides + j % sides]
            for j in range(sides):
                self.parts['fruit'].extend((ids[0], ring(0, j), ring(0, j + 1),
                                            ids[1], ring(rings - 1, j + 1), ring(rings - 1, j)))
                for k in range(rings - 1):
                    a, b, c, d = ring(k, j), ring(k, j + 1), ring(k + 1, j + 1), ring(k + 1, j)
                    self.parts['fruit'].extend((a, d, c, a, c, b))

    # Palms

    def frond(self, base, azimuth, elevation, reach, sag, fold, segments, folded, color, centre, wide=1.0):
        """One frond card from base: it leaves at `elevation` degrees and arches down by sag (a share of its reach);
        folded, its leaflets rise from the rachis in a V (fold > 0) or hang from it (fold < 0) by fold degrees."""
        heading = [math.cos(azimuth), math.sin(azimuth), 0]
        side = [-heading[1], heading[0], 0]
        rise, run = math.sin(math.radians(elevation)), math.cos(math.radians(elevation))
        half = reach * self.spec['width'] * wide * .5
        fold = math.radians(fold if folded else 0)
        mirror = self.rng.random() < .5
        stem = 1 - self.stem if mirror else self.stem
        edges = (1.0, 0.0) if mirror else (0.0, 1.0)
        rows, normals, colors, uvs = [], [], [], []
        for i in range(segments + 1):
            s = i / segments
            point = add(add(base, heading, reach * run * s), [0, 0, reach * (rise * s - sag * s * s)])
            tangent = normalized(add([c * run for c in heading], [0, 0, rise - 2 * sag * s]))
            up = normalized(cross(tangent, side))
            left = add(add(point, side, half * math.cos(fold)), up, half * math.sin(fold))
            right = add(add(point, side, -half * math.cos(fold)), up, half * math.sin(fold))
            row = [[p[0], p[1], max(p[2], .05)] for p in ([left, point, right] if folded else [left, right])]
            rows.append(row)
            # The crown shades as a dome: lit on top, dark beneath and toward the trunk.
            normals.append([normalized(add(normalized(sub(p, centre)), [0, 0, .5])) for p in row])
            colors.append([[c * (.8 + .2 * s) for c in color]] * len(row))
            v = BASE_V + (TIP_V - BASE_V) * s
            uvs.append([[edges[0], v], [stem, v], [edges[1], v]] if folded else [[edges[0], v], [edges[1], v]])
        self.surface(rows, normals, colors, uvs)

    def palm(self, level, thinning):
        spec, rng = self.spec, self.rng
        top = spec['crown'] * HEIGHT
        azimuth = rng.uniform(0, math.tau)
        heading = [math.cos(azimuth), math.sin(azimuth), 0]
        # The trunk leans by its bezier's control and comes back toward the vertical at the crown.
        control = add([0, 0, top * .5], heading, spec['curve'][0] * HEIGHT)
        end = add([0, 0, top], heading, spec['curve'][1] * HEIGHT)
        rings = level['rings']
        points = [bezier([0, 0, 0], control, end, k / rings) for k in range(rings + 1)]
        foot, crown = spec['trunk'], spec['top']
        radii = [crown + (foot - crown) * (1 - k / rings) ** 2 + .35 * foot * math.exp(-points[k][2] / 1.2)
                 for k in range(rings + 1)]
        self.tube(points, radii, level['sides'], .9)
        reach = spec['reach'] * HEIGHT
        centre = add(end, [0, 0, -reach * .35])
        tint = spec['leaves']
        count = max(5, round(spec['fronds'] * level['fronds'] * thinning))
        phase = rng.uniform(0, math.tau)
        for k in range(count):
            # A spiral from the youngest frond, nearly upright in the crown's centre, to the oldest, drooping outside.
            age = (k + .5) / count
            elevation = spec['elevations'][0] + (spec['elevations'][1] - spec['elevations'][0]) * age ** .8
            sag = spec['sag'][0] + (spec['sag'][1] - spec['sag'][0]) * age
            length = reach * (.7 + .3 * min(1, age * 3)) * rng.uniform(.9, 1.08)
            direction = phase + k * 2.39996
            base = add(end, [math.cos(direction), math.sin(direction), 0], crown * .6)
            shade = (1.05 - .15 * age) * rng.uniform(.94, 1.04)
            self.frond(base, direction, elevation + rng.uniform(-6, 6), length, sag, spec['fold'],
                       level['segments'], level['fold'], [c * shade for c in tint], centre, level['width'])
        # Dead fronds hang down the trunk under the crown, dry and tan.
        for k in range(round(spec['dead'] * level['dead'])):
            direction = phase + rng.uniform(0, math.tau)
            base = add(end, [math.cos(direction), math.sin(direction), -.4], crown * .7)
            dry = [t * d * rng.uniform(.8, 1) for t, d in zip(tint, spec['dry'])]
            self.frond(base, direction, rng.uniform(-86, -74), reach * rng.uniform(.55, .7), 0, 0, 1,
                       level['fold'], dry, centre)

    # Cacti

    def column(self, points, radius, sides, cap):
        """A ribbed cactus stem along points, closed by a dome of `cap` rings around its end (open without one)."""
        tip, axis = points[-1], normalized(sub(points[-1], points[-2]))
        path = points[:-1] + [add(tip, axis, -radius)] if cap else list(points)
        radii = [radius] * len(path)
        for k in range(1, cap + 1):
            angle = math.pi / 2 * k / cap
            path.append(add(path[len(points) - 1], axis, radius * math.sin(angle)))
            radii.append(max(radius * math.cos(angle), .02))
        self.tube(path, radii, sides, 1.0, self.spec['around'], cap)

    def flower(self, tip, radius, count):
        """White blossoms in a ring around a stem's crown: small cards leaning out from its dome, so the iso view sees
        them as flowers on the stem rather than a disc on its top."""
        phase = self.rng.uniform(0, math.tau)
        size = radius * .9
        for k in range(count):
            azimuth = phase + k * math.tau / count
            out, across = [math.cos(azimuth), math.sin(azimuth), 0], [-math.sin(azimuth), math.cos(azimuth), 0]
            up = normalized(add([0, 0, 1], out, .7))
            base = add(add(tip, out, radius * .8), [0, 0, -radius * .45])
            rows = [[add(add(base, up, size * s), across, -size / 2), add(add(base, up, size * s), across, size / 2)]
                    for s in (0, 1)]
            normal = normalized(add([0, 0, 1], out))
            self.surface(rows, [[normal] * 2] * 2, [[[1, 1, 1]] * 2] * 2,
                         [[[0, BASE_V], [1, BASE_V]], [[0, TIP_V], [1, TIP_V]]])

    def cactus(self, level, thinning):
        spec, rng = self.spec, self.rng
        radius = spec['trunk']
        rings = level['rings']
        self.column([self.axis(HEIGHT * k / rings) for k in range(rings + 1)], radius, level['sides'], level['cap'])
        tips = [self.axis(HEIGHT)]
        phase = rng.uniform(0, math.tau)
        for k in range(spec['arms']):
            # An arm leaves the column level, turns up at its elbow and rises beside it.
            direction = phase + math.tau * (k + rng.uniform(-.15, .15)) / spec['arms']
            out = [math.cos(direction), math.sin(direction), 0]
            arm = radius * spec['arm'] * rng.uniform(.92, 1.05)
            low = HEIGHT * rng.uniform(*spec['heights'])
            high = min(HEIGHT * .9, low + HEIGHT * rng.uniform(.24, .4))
            reach = radius + arm * rng.uniform(2.2, 3.0)
            origin = self.axis(low)
            corner = add(self.axis(low + arm * .3), out, reach)
            end = add(self.axis(high), out, reach * rng.uniform(.95, 1.08))
            count = level['arm_rings']
            self.column([bezier(origin, corner, end, j / count) for j in range(count + 1)], arm, level['arm_sides'],
                        level['arm_cap'])
            tips.append(end)
        if spec['flowers']:
            for tip in tips:
                self.flower(tip, radius, level['blossoms'])

    # Levels

    def fit(self):
        """Scale the level to the common height, its foot at the origin; nothing reaches below the ground (a leaning
        trunk's first ring tilts with it)."""
        scale = self.spec.get('height', HEIGHT) / max(self.vertices[i] for i in range(2, len(self.vertices), 12))
        # A shrub's footprint can spread wider than its height alone gives (`xy`), to cover as level-one woods.
        spread = self.spec.get('xy', 1)
        for i in range(0, len(self.vertices), 12):
            for c in range(3):
                self.vertices[i + c] *= scale * (spread if c < 2 else 1)
            self.vertices[i + 2] = max(0.0, self.vertices[i + 2])


def grow(kind, spec, index, thinning):
    # A saguaro's levels share one seed: the same arms at every distance.
    tree = Tree(kind, spec, random.Random(spec['seed'] * 101 + (0 if kind == 'cactus' else index)))
    if kind == 'conifer':
        tree.conifer(CONIFER_LEVELS[index], thinning)
    elif kind == 'palm':
        tree.palm(PALM_LEVELS[index], thinning)
    elif kind == 'cactus':
        tree.cactus(CACTUS_LEVELS[index], thinning)
    else:
        level = BROADLEAF_LEVELS[index]
        tree.broadleaf({**level, **spec['near']} if index == 0 and 'near' in spec else level, thinning)
        # The far level's apples are three-sided.
        tree.apples(spec.get('apples', (0, 0, 0))[index], *((6, 1), (6, 1), (3, 1))[index])
    tree.fit()
    return tree


def model(name, index):
    kind, snow = family(name), species(name) != name
    spec = SPECIES[species(name)]
    # A crown over its level's budget loses branches or clumps until it fits.
    thinning = 1.0
    tree = grow(kind, spec, index, thinning)
    budget = spec.get('budgets', BUDGETS[kind])[index]
    while sum(map(len, tree.parts.values())) // 3 > budget:
        thinning *= .95
        if thinning < .1:
            raise ValueError(f'{name}-lod{index} cannot fit {budget} triangles')
        tree = grow(kind, spec, index, thinning)
    vertices = list(tree.vertices)
    tint = spec['leaves']
    if spec.get('winter', True):
        # Canopy shades scale the species' tint in linear light, so its winter colour scale greys every card exactly.
        for i in set(tree.parts['canopy']):
            value = min(linear(vertices[i * 12 + 7] / tint[1]), 1 / linear(max(tint)))
            for c in range(3):
                vertices[i * 12 + 6 + c] = display(linear(tint[c]) * value)
        if snow:
            # The winter file applies its variant's colour scale (linear) to the canopy's vertex colours.
            scale = snow_scale(spec)
            for i in set(tree.parts['canopy']):
                for c in range(3):
                    vertices[i * 12 + 6 + c] = display(min(1.0, linear(vertices[i * 12 + 6 + c]) * scale[c]))
    elif snow:
        # Without a snow variant, snow lies where the plant faces the sky: on the tops of its limbs and twigs.
        for i in {index for part in tree.parts.values() for index in part}:
            cover = .9 * min(1, max(0, (vertices[i * 12 + 5] - .25) / .45))
            for c in range(3):
                vertices[i * 12 + 6 + c] += (.98 - vertices[i * 12 + 6 + c]) * cover
    asset = f'{name}-lod{index}'
    roles = [(role, material) for role, material in zip(('bark', 'canopy', 'fruit'), materials(kind, spec, snow))
             if tree.parts[role]]
    parts = [{'id': f'{asset}-{role}', 'type': 'TRIANGLES', 'indices': tree.parts[role]} for role, _ in roles]
    return {'id': asset, 'meshes': [{'attributes': ['POSITION', 'NORMAL', 'COLOR', 'TEXCOORD0'],
                                     'vertices': vertices, 'parts': parts}],
            'nodes': [{'id': asset, 'parts': [{'meshpartid': part['id'], 'materialid': material['id']}
                                              for part, (_, material) in zip(parts, roles)]}],
            'materials': [material for _, material in roles]}


def build(name, board):
    levels = {index: model(name, index) for index in range(3)}
    # The impostor (LOD3) stays until the impostor bake refreshes it.
    shipped = BOARD / f'vegetation/{name}.glb'
    if shipped.exists():
        old = read_glb(shipped, 3)
        old['materials'] = [material for material in old['materials'] if material['id'] == 'impostor']
        levels[3] = old
    write_glb(Path(board) / f'vegetation/{name}.glb', levels=levels)
    counts = [{'node': f'{name}-lod{index}',
               'triangles': sum(len(p['indices']) // 3 for p in levels[index]['meshes'][0]['parts']),
               'vertices': len(levels[index]['meshes'][0]['vertices']) // 12} for index in range(3)]
    if Path(board).resolve() == BOARD.resolve():
        manifest = json.loads(MANIFEST.read_text())
        # A new plant (a shrub's variant) gets its entry; the impostor bake adds its fourth level.
        manifest.setdefault(f'vegetation/{name}', {'mesh': f'vegetation/{name}.glb', 'lods': []})
        # The bare file's entry and its winter variant's (which reads the same file) share its levels.
        for key in (f'vegetation/{name}', f'vegetation/{name}-snow'):
            entry = manifest.get(key)
            if entry and entry['mesh'] == f'vegetation/{name}.glb':
                stem = key.rsplit('/', 1)[-1]
                entry['lods'][:3] = [{**lod, 'node': f'{stem}-lod{index}'} for index, lod in enumerate(counts)]
                entry.update(source='tools/board-models/foliage/build_trees.py', triangles=counts[0]['triangles'],
                             vertices=counts[0]['vertices'])
                # Its textures are named in the GLB.
                entry.pop('texture', None)
        MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n')
    print(name, [lod['triangles'] for lod in counts])


if __name__ == '__main__':
    arguments = sys.argv[1:]
    board = BOARD
    if arguments[:1] == ['--out']:
        board, arguments = Path(arguments[1]), arguments[2:]
    for name in arguments or [*SPECIES, *WINTER]:
        build(name, board)
