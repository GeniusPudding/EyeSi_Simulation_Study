"""Adhesion-peel demo: a circular membrane (shallow ellipsoid cap) glued onto an
oblate lens.

Shift + left-drag pulls the membrane. Below the adhesion threshold it stays stuck;
past it, that spot peels off and can be lifted/folded. The peeled part slowly adopts
its shape as its rest shape (viscoplastic creep), so it barely springs back. The lens
is a solid obstacle (analytic ellipsoid penalty), so the membrane folds over it.

Physics: mass-spring membrane (edge + bending springs) under implicit Euler, plus a
Python controller doing peel / plasticity / per-step safety nets / diagnostics.
Geometry: generate_cap.py emits cap.obj + lens.obj from the same analytic ellipsoid,
so the membrane lies exactly flush.

Run:  ./scenes/run_cap.sh   (macOS)      .\\scenes\\run_cap.ps1   (Windows)
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
if hasattr(os, "add_dll_directory"):  # Windows only; mac/linux resolve via rpath
    for _p in (os.path.join(SOFA_ROOT, "bin"),):
        if os.path.isdir(_p):
            os.add_dll_directory(_p)
    for _plugin in ("SofaPython3", "SofaImGui"):
        _d = os.path.join(SOFA_ROOT, "plugins", _plugin, "bin")
        if os.path.isdir(_d):
            os.add_dll_directory(_d)

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import generate_cap as G   # geometry: A, C, R, Z0, CAP_HEIGHT, rim_indices()

CAP_OBJ = os.path.join(_HERE, "cap.obj")    # the membrane
LENS_OBJ = os.path.join(_HERE, "lens.obj")  # the flattened (oblate) base it sticks to

# --- membrane in-plane model -------------------------------------------------
# True  = pure mass-spring membrane. A spring force k*(L - L0) has no area in any
#         denominator, so a squashed/inverted triangle cannot self-amplify: hard
#         pulls are blow-up-proof. Edge springs alone give full in-plane stiffness
#         (a triangle with three fixed edge lengths is rigid).
# False = co-rotational triangle FEM on top; richer physics, but an inverted
#         triangle gets pushed the wrong way and inflates without bound.
# The numpy stress observer (principal_stress) is purely geometric -> works in both.
# Switchable without editing this file: CAP_MODE=fem (run_cap.ps1 -Fem / run_cap.sh
# --fem) picks the FEM; anything else keeps the tuned mass-spring default. Measured
# 2026-07-23 on identical scripted pulls, the two are indistinguishable at the normal
# pull rate (rawMax 1.79e3 vs 1.77e3, degen 0 both), so FEM costs no stability while
# giving back the real continuum stress tensor and citable E/nu.
USE_MASS_SPRING = os.environ.get("CAP_MODE", "spring").lower() != "fem"

# --- PAPER MODE: reproduce the INRIA capsulorhexis setup, and nothing else ----------------
# Dequidt 2013 / Marchal 2009 model the capsule as a transversely isotropic co-rotational
# triangular FEM with CONCENTRIC fibre orientations, integrated implicitly, and tear it with
# the argmax-c criterion. Searching the whole of Dequidt 2013 for adhes/glue/peel/debond finds
# nothing: there is NO bond to the lens and no peeling anywhere in that work -- the tear is
# driven purely by, in the paper's words, "the application of shear and stretch forces".
# Everything this demo has around that (breakable adhesion, peel fronts, PEEL_* parameters) is
# our own addition, and it competes with the tear for the same pull (docs 4.11). Paper mode
# removes it so the published method can be judged on its own.
PAPER_MODE = os.environ.get("CAP_PAPER", "0") == "1"
# Fibre-direction (E_F) and transverse (E_T) Young's moduli. The ratio is the anisotropy;
# the capsule's collagen runs concentrically, so E_F is the circumferential stiffness.
PAPER_E_FIBER = float(os.environ.get("CAP_PAPER_EF", "1200"))
PAPER_E_TRANSVERSE = float(os.environ.get("CAP_PAPER_ET", "400"))
PAPER_POISSON = float(os.environ.get("CAP_PAPER_NU", "0.3"))
if PAPER_MODE:
    USE_MASS_SPRING = False          # the paper uses FEM, not a mass-spring approximation

# --- real tearing (CAP_TEAR=1 / run_cap.ps1 -Tear) -----------------------------------
# Built on THIS scene's stress observer, not on any plugin: the crack advances along the
# INRIA argmax-c direction (Dequidt Eq.1-4) evaluated on the crack-tip neighbourhood, and
# the mesh is opened by duplicating the vertices behind the tip and rewiring the triangles
# on one side onto the duplicates. Nothing about the pull mechanics changes -- the membrane
# is still the tuned mass-spring, the rim is NOT anchored, and the mouse spring is untouched.
CAP_TEAR = os.environ.get("CAP_TEAR", "0") == "1"
# sigma_bar_T, the capsule's toughness. Calibrated by sweeping on an identical hand-like
# pull: 220 gives a controlled 179-vertex tear, 20 gives a long smooth 563-vertex tear with
# the mesh still healthy (0.1% degenerate) and the capsule still on the lens, and 1 is WORSE
# than 20 (only 204 vertices) because it shreds the mesh into 24.8% degenerate elements,
# which poisons the stress and stalls the tear -- see the guard below. 20 is the sweet spot;
# raise for a tougher capsule (600 barely tears at all), lower for a fragile one.
TEAR_THRESH = float(os.environ.get("CAP_TEAR_THRESH", "20"))
TEAR_FIB_RATIO = float(os.environ.get("CAP_TEAR_FIBRATIO", "2.5"))   # sigma_bar_L / sigma_bar_T
TEAR_FIB_ALPHA = float(os.environ.get("CAP_TEAR_ALPHA", "2.0"))      # Eq.4 steepness
# Largest turn the crack may make in one edge (Eq.2's H term). Must be bigger than the
# MESH's own angular resolution, not just "a plausible angle for a crack": vertices here
# have ~6 edges at ~60deg spacing, so once the forward edges have been cut the nearest
# legal option sits at 85-95deg. At the old 70 that was illegal, and the crack simply
# stopped -- measured, 55% of all the steps where the criterion said TEAR were refused
# by this limit rather than by any physics, every one of them asking for ~90deg.
# Raising it to 100 doubled the tear (45 -> 90 vertices) and removed the blocking
# entirely; 130 was no better, so the limit is no longer what binds.
TEAR_TURN_MAX = float(os.environ.get("CAP_TEAR_TURN", "100"))
TEAR_EVERY = int(os.environ.get("CAP_TEAR_EVERY", "3"))          # steps between advances
TEAR_TIP_RADIUS = float(os.environ.get("CAP_TEAR_RADIUS", "0.6"))    # tip neighbourhood
# Edges the crack may run in ONE opportunity. A real tear is unstable: once the criterion is
# passed the crack RUNS, it does not creep one element at a time. Advancing a single edge per
# opportunity made it crawl (~13 edges/s) instead of ripping, so the rate now scales with how
# far c exceeds 1 -- c=1 gives one edge, a hard pull gives a fast run -- capped here.
TEAR_MAX_ADVANCE = int(os.environ.get("CAP_TEAR_MAXADV", "4"))
# Crack-tip stress concentration. A real crack tip carries an r^(-1/2) singularity; linear
# FEM on a mesh with 0.3-unit elements cannot represent it, so the tip-neighbourhood average
# UNDER-estimates the driving stress badly -- measured live, the pull zone read sigma1 ~760
# while the tip 2 units away averaged ~4. Without a correction the criterion never fires
# unless you grab exactly on the tip. This is the standard coarse-mesh fix (the same reason
# the earlier demo needed TIP_STRESS_GAIN, see docs/implementation/4 section 5.3).
TEAR_TIP_GAIN = float(os.environ.get("CAP_TEAR_TIPGAIN", "1.5"))
# How far from the tip the pull still drives the crack. The membrane is glued down almost
# everywhere, so stress does not travel; sampling only a 0.6-unit disc means a hand pulling
# 2 units away is invisible to the tip. This widens the sampling for the DRIVING term only.
# Decay LENGTH of the tip-load kernel (NOT a cutoff radius any more -- see
# _tip_stress). A load this far from the tip counts half.
TEAR_REACH = float(os.environ.get("CAP_TEAR_REACH", "3.0"))
# How many of the strongest weighted elements the drive averages. 1 = raw max,
# which lets a single near-degenerate triangle (~100x the bulk) drive the tear.
TEAR_DRIVE_TOPK = int(os.environ.get("CAP_TEAR_TOPK", "8"))
# How many of the most recent crack vertices are off-limits to the advancing tip.
# Only the tail: the tear must be able to reach its own START to close the circle.
TEAR_NOBACK = int(os.environ.get("CAP_TEAR_NOBACK", "8"))
# How strongly the next edge is chosen to STAY ON ITS RING rather than drift in radius.
# OFF (0), because it could not be shown to help and measurably hurt everything that could be
# measured: on a scripted pull, 0/0.3/0.6 gave cut 72/65/52 and crack span 13.0/11.9/1.6. The
# failure it was written for -- the crack boxing itself in, 73.7% of steps blocked by the turn
# limit in a real 71 s session -- could NOT be reproduced by any probe here, scripted or with
# the grab moved around every 120 steps (turn-blocking stayed at 0.0% throughout). Kept as a
# knob because the idea is sound and the failure is real; not enabled on evidence that does
# not exist.
TEAR_RING_KEEP = float(os.environ.get("CAP_TEAR_RINGKEEP", "0.0"))
# Minimum crack length before reaching the seed counts as the rhexis closing,
# so the tear cannot "complete" a few edges after it starts.
TEAR_CLOSE_MIN = int(os.environ.get("CAP_TEAR_CLOSEMIN", "40"))
# Splits between full rebuilds of the edge springs. 1 = every split (most correct,
# ~27 ms each); higher trades accuracy of the cut for framerate.
TEAR_SPRING_REBUILD = int(os.environ.get("CAP_TEAR_SPRINGREBUILD", "1"))
# Use the Capsulorhexis plugin's TopologySplitEngine (official topology API) instead of
# writing topo.triangles directly. OFF BY DEFAULT: the component is correct in isolation
# (tests/test_topology_split.py -- the split lands, positions are interpolated from the
# ancestor, and topo.edges comes out with zero stale and zero missing entries), but merely
# CREATING it inside this scene aborts SOFA with SIGABRT during scene load. The stack points
# at SceneLoaderPY3::doLoad, so it fails while the graph is being built, before any split is
# ever requested; moving it after the geometry algorithms -- the order that works in the unit
# test -- does not help. Not yet diagnosed. With CAP_TOPO_API=0 the scene behaves exactly as
# before, so this costs nothing to leave in place until it is understood.
TOPO_API = os.environ.get("CAP_TOPO_API", "0") == "1"
# Arrest-on-unloading. A crack is driven by work being DONE on it, so letting go should let
# the stored energy run it a little further and then stop it. The criterion alone cannot do
# that: c stays far above 1 on residual stress. Advance only while the tip drive is within
# TEAR_ARREST of its recent peak, where that peak itself decays by TEAR_ARREST_DECAY each
# opportunity so a slow steady pull still counts as loading.
# CALIBRATED AGAINST A REAL SESSION, not a probe. At 0.9 this gate refused 35.8% of all
# opportunities and TEAR_LOCAL_MIN=1.5 refused another 55.8%, leaving 8.3% actually tearing --
# read straight out of the recorded frames' "why" field. It passed the probe only because the
# probe pulled in a perfectly smooth ramp; a real hand jitters, so the drive keeps dipping
# below its own recent peak. With a jittery probe pull, 0.6/0.4 tears 54 vertices against 35,
# still never self-starts, and still stops dead on release.
TEAR_ARREST = float(os.environ.get("CAP_TEAR_ARREST", "0.6"))
# ...but a SPLIT also unloads the tip -- that is what tearing IS -- and taking max() above
# meant the ref remembered the PRE-split peak, so every successful bite immediately arrested
# the next one. Read out of a real 2165-step session: 36.3% of all steps were "arrested" and
# only 11.8% were tearing, while c sat at a median of 392 against a threshold of 20. The gate
# was refusing a criterion that was satisfied twentyfold. After our own split, re-baseline the
# ref to the post-split drive instead, so the gate still catches the hand LETTING GO but no
# longer catches the crack doing its job.
TEAR_ARREST_REBASE = os.environ.get("CAP_TEAR_REBASE", "1") == "1"
# Escape hatch for the turn limit. Restricting the crack to existing edges is the papers' own
# simple strategy, and Dequidt 2013 section 4.3 says outright that it makes propagation "highly
# dependent on the original mesh"; their alternative is to cut in an arbitrary direction and
# remesh. On our mesh the cheap version DEADLOCKS: the same session sat 551 consecutive steps
# (11 s) at exactly c=392.36 with the crack frozen at 22 vertices because every remaining edge
# needed a 131 deg turn and the limit is 100. That is not a difficulty, it is a dead end. So
# after this many consecutive blocked opportunities with the criterion still met, take the
# sharp turn anyway -- a real membrane at 20x its tearing stress does not simply stop.
TEAR_BLOCK_ESCAPE = int(os.environ.get("CAP_TEAR_ESCAPE", "8"))
TEAR_ARREST_DECAY = float(os.environ.get("CAP_TEAR_ARREST_DECAY", "0.97"))
# Minimum sigma1 in the tip's OWN elements before its direction is trusted. Measured, the
# local reading is 0.3 with no load and 5-20 under a real pull, and it is the only source
# that points at the hand -- but only once there is something to point with.
TEAR_LOCAL_MIN = float(os.environ.get("CAP_TEAR_LOCALMIN", "0.4"))
# Crack-length amplification, the K = sigma*sqrt(pi*a) of linear elastic fracture mechanics.
# THIS is why a tear "runs" in reality and never did here. The stress delivered to a crack tip
# grows with the SQUARE ROOT OF CRACK LENGTH, so a long tear extends far more easily than a
# fresh nick -- that is the whole sensation of tearing skin or paper. The criterion had no
# crack-length term at all, so a 100-vertex tear was exactly as hard to extend as the opening
# puncture, which is precisely why it advanced in isolated bursts and never took off.
# Amplify by sqrt(a / a0), a = the crack's physical extent, capped so it cannot run away.
TEAR_LEFM = os.environ.get("CAP_TEAR_LEFM", "1") == "1"
TEAR_LEFM_CAP = float(os.environ.get("CAP_TEAR_LEFMCAP", "6.0"))
# Heading inertia: how much of the crack's PREVIOUS direction is kept when the criterion picks
# a new one. A real tear does not swing wildly from edge to edge -- it carries momentum, and
# the surgeon's pull direction changes slowly. TEAR_TURN_MAX had to be opened up to 100 deg to
# stop the crack dead-ending on the mesh's own 60 deg edge spacing, but that also let the
# heading itself swing that far every single step, which is what produced the jagged
# back-and-forth path. Separating the two: the tip may still CHOOSE among widely-spread
# neighbours, while the heading it steers by turns smoothly. 0 = no inertia (old behaviour).
TEAR_DIR_INERTIA = float(os.environ.get("CAP_TEAR_INERTIA", "0.6"))
# Nucleation anywhere, straight from the paper. Dequidt 2013 section 4.3: "This criterion is
# typically evaluated at the tip of a pre-existing fracture OR AT THE CENTER OF EACH
# POTENTIALLY FRACTURING ELEMENT." We only ever evaluated it at one tip, which is why the tear
# answered the hand only when the hand was near that tip -- a tear could never simply start
# where the membrane was most overloaded. Scanning every healthy element is affordable because
# c <= sigma1/sigma_bar_T, so only elements already above the threshold can possibly reach 1.
TEAR_NUCLEATE = os.environ.get("CAP_TEAR_NUCLEATE", "1") == "1"
# CONSECUTIVE idle opportunities before looking elsewhere. Must be generous: at 10 a
# momentary lull mid-tear discarded a front that was still growing and restarted from
# a single vertex, which measured as the tear collapsing (5 vertices -> 1).
TEAR_NUCLEATE_EVERY = int(os.environ.get("CAP_TEAR_NUCEVERY", "40"))
# Separate, MUCH larger patience for abandoning a BLOCKED front, as opposed to an idle one.
# Being blocked is common -- 73.7% of steps in a recorded session -- so reusing the idle
# threshold made the tear give up and restart somewhere else over and over, leaving scattered
# short cuts instead of one growing tear ("this version tears more messily"). Idle is rare and
# genuinely means nothing is happening; blocked means the tear is alive but cornered, and it
# deserves far more time before it is written off.
TEAR_NUC_BLOCKED_EVERY = int(os.environ.get("CAP_TEAR_NUCBLOCKED", "300"))
TEAR_NUC_MAX = int(os.environ.get("CAP_TEAR_NUCMAX", "40"))   # elements searched per scan
# The initial nick: capsulorhexis starts with a cystotome puncture near the centre, and
# without one there is no crack tip to push -- the membrane would just stretch. This seeds a
# short radial slit of this many edges starting at radius TEAR_START_R.
TEAR_START_R = float(os.environ.get("CAP_TEAR_START_R", "1.0"))
TEAR_START_LEN = int(os.environ.get("CAP_TEAR_START_LEN", "3"))
# Mesh-quality brake. Tearing and the stress field are coupled through mesh quality, and the
# loop can eat itself: tear too fast -> elements go degenerate -> their stress is garbage
# (sigma1 in the thousands from a collapsed triangle) -> that garbage drives the criterion
# even harder -> more tearing. Measured at sigma_T=1: 24.8% of elements degenerate, only 39
# of 2156 spots still glued, and the tear ended up SHORTER (204 vertices) than at a sane
# threshold (563), because the tip neighbourhood became all-degenerate and the criterion
# could no longer be evaluated. Above this fraction the tear pauses so the membrane can
# relax; it resumes by itself once the mesh recovers.
# Raised 0.04 -> 0.10 once the arrest gate stopped self-arresting: with the rebase in place
# the brake became the SECOND-biggest blocker (25% of probe steps at 0.04) and it was braking
# on 4-7% degenerate, nowhere near the 24.8% that actually shreds. Measured on the same pull,
# 0.10 gives crack 154 -> 170 and tearing 50.0% -> 55.3%, and the mesh SATURATES there -- 0.20
# is identical (5.0% degenerate, stretch 8.31 concentrated in 28 torn-lip edges of ~12500,
# p99 1.70), so above 0.10 the brake is no longer what limits the tear anyway.
TEAR_DEGEN_MAX = float(os.environ.get("CAP_TEAR_DEGEN_MAX", "0.10"))

# --- material ----------------------------------------------------------------
CLOTH_YOUNG = float(os.environ.get('CAP_CLOTH_YOUNG', '120.0'))       # FEM-only: soft opening phase
PAPER_YOUNG = float(os.environ.get('CAP_PAPER_YOUNG', '1200.0'))      # FEM-only: stiffened at SWITCH_T; 4000+ risks blow-up
SWITCH_T = 1.0            # [s] cloth -> paper transition
EDGE_STIFFNESS = float(os.environ.get('CAP_EDGE_STIFFNESS', '2500.0'))   # per-edge in-plane stiffness = THE membrane stiffness in
                          # mass-spring mode (raise if the sheet feels too soft)
DAMPING = float(os.environ.get("CAP_DAMPING", "2.0"))   # global viscosity; lower = snappier
                          # (mesh responds to the pull faster), higher = calmer but more
                          # sluggish. Implicit, so any value is stable. Try CAP_DAMPING=1.0.
# Damping must be implicit: an explicit -c*v force is only stable for c*dt/m < 2,
# already violated at c=2 on the lightest nodes (and 18-100x violated when the
# full-peel ramp sets c=60). Implicit damping is unconditionally stable.
DAMPING_IMPLICIT = True

# Per-step displacement clamp, applied in onAnimateEnd BEFORE the frame is drawn:
# no node may move more than this per step; clamped nodes get their velocity
# rescaled (not zeroed). Implicit solves are stable but not bounded -- one mouse
# flick can legally move a node several units in a step; this turns that into
# "saturates and follows" instead of a one-frame explosion.
# 0.5 = 25 units/s: above legitimate flap-folding speeds (10-15), far below
# explosion speeds. 0.25 was too tight (bit normal folding -> stutter). 0 = off.
DISP_CLAMP = float(os.environ.get("CAP_DISP_CLAMP", "0.5"))

# Diagnostics: one CSV row per step (peaks + safety-net counters), overwritten each
# run; pair with run_last.log (console tee in run_cap.sh) to analyse a session.
LOG_DIAG = True
DIAG_PATH = os.path.join(_HERE, "diag_last.csv")

# Bending stiffness = "does the lifted flap flop over, or stand up stiff?"
# smaller -> floppy drape; bigger -> stiff wide curve. In-plane softness is a
# different knob (EDGE_STIFFNESS / PAPER_YOUNG).
# Out-of-plane bending resistance. This is the direct control on whether a torn piece can
# FOLD OVER rather than only lift, so it has to be adjustable to be tested at all.
BEND_STIFFNESS = float(os.environ.get('CAP_BEND', '15.0'))

# Gravity stays 0: gravity weak enough to spare the adhesion cannot bend a
# plasticity-set flap, and gravity strong enough to bend it rips the whole membrane
# off. Fold flaps by dragging across instead; plasticity keeps them folded.
GRAVITY_Z = 0.0

# Lens obstacle: analytic ellipsoid PENALTY force, F = stiffness * penetration
# (positive = repulse outward). STABILITY CEILING: 8000 explodes a fast yank (one
# deep node -> enormous force); 2000 is stable and sinks ~0.15 in normal use.
# Do NOT raise it to chase the last 0.1 of sink-in.
LENS_REPULSION = 2000.0

# --- adhesion of the membrane to the lens ------------------------------------
ADHESION_STIFF = 120.0    # spring pulling each glued node to its rest spot
# Pull force at which a spot peels off. MUST stay low enough that break_lift
# (= BREAK_FORCE/ADHESION_STIFF) is a lift the mesh can actually REACH: the strain clamp
# stops a lone glued node at sqrt((MAX_STRETCH*e)^2 - e^2), which on this mesh (e=0.300,
# MAX_STRETCH=1.6) is 0.375. At the old 60 the required lift was 0.500 -- unreachable, so
# no spot in the interior could EVER debond however hard it was pulled, and the capsule
# behaved as if welded to the lens (measured: a 10.6-long mouse arrow at 6384 of force
# released 65 of 2153 spots). 30 gives break_lift 0.250, comfortably inside the limit and
# 282 spots released on the same pull. Do not raise it past ~45 without also raising
# MAX_STRETCH; _check_peel_reachable() below warns if this is ever violated again.
# Adhesion acts only IN THE PLANE OF THE LENS SURFACE, not as a downward suction.
# The anterior capsule lies ON the lens; what holds it is in-plane continuity and the zonular
# insertion, not something pulling it onto the dome. Modelled as a plain rest-shape spring it
# was pulling every node back toward its rest spot in FULL 3D, so lifting a flap fought a
# spring dragging it down again -- which is why the membrane barely moved however hard it was
# pulled, and why a torn piece could never be folded over. The spring stays (it is implicit,
# so it stays stable), but its anchor now follows the node along the surface NORMAL, leaving
# only the tangential component. Lifting is then resisted by membrane stretch and by the
# neighbours' in-plane anchors -- which is the real mechanism -- and not by glue.
#
# OFF BY DEFAULT, because measuring it did not show the benefit it was built for. On an
# identical pull it moved the grab lift only 2.34 -> 2.36 and the lifted-node count 287 -> 303,
# while HALVING the tear (crack 100 -> 47) and leaving more of the capsule stuck (1044 -> 1388
# glued) -- the membrane gives more easily, so less stress builds and less tears. So the
# downward pull was never what stopped a flap lifting; the limiter is membrane stretch plus
# the neighbours' in-plane anchors. Kept and switchable (CAP_ADH_TANGENTIAL=1) because it is
# still the more faithful model, and it is the right foundation once flap lifting is solved.
ADH_TANGENTIAL = os.environ.get("CAP_ADH_TANGENTIAL", "0") == "1"
# break_lift = BREAK_FORCE/ADHESION_STIFF must sit ABOVE the elastic noise floor (p99 0.234,
# max 0.261 measured) and BELOW what the strain clamp lets a lone node reach (0.375, see
# _check_peel_reachable). 30 gave 0.250, inside the noise; 40 gives 0.333, which clears the
# p99 with margin and still leaves room to be reached.
BREAK_FORCE = 40.0
# NOTE: tear mode deliberately keeps the DEFAULT adhesion. Weakening it to help the flap lift
# was a mistake -- the flap does not need it (splitting a vertex already ungluesthat spot and
# its ring, see _split_vertex), while a low break force let the pull peel the ENTIRE cap off
# the lens: measured 2156 -> 222 glued spots in under 3 s, after which the free sheet crumpled
# into a wad. Override with CAP_ADHESION / CAP_BREAK if a more fragile capsule is wanted.
ADHESION_STIFF = float(os.environ.get("CAP_ADHESION", ADHESION_STIFF))
BREAK_FORCE = float(os.environ.get("CAP_BREAK", BREAK_FORCE))
# Peel fade: a just-broken node's adhesion decays by PEEL_FADE per step (dropped
# below PEEL_FADE_MIN) instead of vanishing at once -- releasing the stored ~60
# units of force in one step is a visible local twitch (~40 units/s impulse).
PEEL_FADE = 0.55
PEEL_FADE_MIN = 6.0
# Peel as a propagating FRONT, not a global threshold. The debond test is a per-node
# lift distance (break_lift = BREAK_FORCE/ADHESION_STIFF = 0.5), but the membrane is
# nearly inextensible, so pulling one edge lifts the whole sheet past 0.5 at once:
# measured without this guard, 2127 glued spots -> 0 in ten steps and the cap crumpled
# off the lens. A bonded spot surrounded by intact adhesive cannot debond; real peeling
# advances from a free boundary. So a spot may only let go on the mesh boundary (rim or
# slit = the crack initiation sites) or once a neighbour has already let go.
PEEL_FRONT_ONLY = os.environ.get("CAP_PEEL_FRONT", "1") == "1"
# Lift (in units of break_lift) at which a spot may debond even with no debonded neighbour.
# Without this the middle of the capsule can never start peeling at all -- see the peel
# trigger. Higher = the sheet only opens from an existing front; lower = easier to start
# lifting anywhere, at the risk of the sheet letting go in several places at once.
PEEL_NUCLEATE = float(os.environ.get("CAP_PEEL_NUCLEATE", "1.2"))
# Lift needed AT THE PEEL FRONT, as a fraction of break_lift. Peeling is not the same
# mechanics as pulling straight off: the work concentrates on the front LINE, which is why a
# sticker peels with almost no force but will not come off if you lift the whole face at once.
# Every glued node needing the SAME break_lift modelled the second case, so the capsule could
# only ever come off in the small patch the hand lifted directly -- "no matter how I pull it
# is always a small crack, never a sheet coming away". A front node is already half free, so
# it lets go far more easily than fresh bonded material.
# MEASURED FLOOR, do not go below it. A node that is nowhere near the hand still moves,
# purely from the membrane's elastic response: median 0.081, p90 0.218, max 0.261 on this
# mesh. Any debond threshold under that detaches the capsule for no physical reason -- at the
# 0.15 this was set to (threshold 0.0375) 58.8% of FAR nodes already qualified, so half the
# sheet came away while visibly sitting still on the lens, which is exactly what it looked
# like. At 1.0 only 0.1% do. The front-concentration idea is sound, but it has to stay above
# the elastic noise floor, and on this mesh there is no room below break_lift for it.
PEEL_FRONT_EASE = float(os.environ.get("CAP_PEEL_EASE", "1.0"))
# How far ahead of the CRACK the debond front may run, in world units. In a real
# capsulorhexis the flap comes away BECAUSE the tear advances -- they are one event. Modelled
# as two independent mechanisms they compete for the same pull, and peeling wins: measured, a
# session went glued 2153 -> 1885 while the crack sat at 4 vertices, the crack then froze at
# 16, and peeling carried on for another 3.9 s releasing 424 more spots after the tear was
# already dead. Unglued membrane goes slack, so the tip stops feeling any load at all and the
# tear can never restart -- the tip's local sigma1 sat at 0.46 through pulls of |F| = 6449.
# Tying the debond front to the crack makes the flap follow the tear instead of outrunning it.
# 0 = off (peel anywhere, the old behaviour, still what the no-tear demo wants).
PEEL_NEAR_CRACK = float(os.environ.get("CAP_PEEL_NEAR", "3.0"))
# ...and keep it with the INSTRUMENT too. Tying the front to the crack alone stops working
# the moment the crack gets long: measured on the irregular mesh, the tear swept 573 deg of
# azimuth, so a 3.0 corridor around it covers essentially the whole disc and every bonded
# spot qualifies. The recorded consequence is an avalanche -- 1685 glued spots down to 884 in
# two seconds, running at the PEEL_RATE ceiling the whole way, until the cap is off the lens.
# PEEL_RATE caps the SPEED of that sweep but nothing stops it, because each freed spot makes
# its neighbours eligible.
# Physically the flap comes away where the hand is lifting it, not everywhere the tear has
# ever been. So require BOTH: within PEEL_NEAR_CRACK of the tear AND within this of the
# instrument. With no instrument engaged, nothing new debonds -- letting go stops the peel,
# which is the behaviour the crack's own arrest gate already has. 0 = off.
PEEL_NEAR_TOOL = float(os.environ.get("CAP_PEEL_TOOL", "3.5"))
# How far above the bulk a node's force must be to count as "the instrument is here".
# Compared against the 99th percentile of all nodal force magnitudes, so it is scale-free.
TOOL_FORCE_RATIO = float(os.environ.get("CAP_TOOL_RATIO", "3.0"))
# ...and cap how fast that front advances. The front rule alone is not enough: each
# freed spot makes its neighbours eligible, so a violent pull still swept the whole cap
# (2263 -> 0). A real crack has a finite propagation speed. Only this many spots debond
# per step, most-lifted (= the crack tip) first. 0 = unlimited.
PEEL_RATE = int(os.environ.get("CAP_PEEL_RATE", "9"))

# --- scripted pull (demo without a mouse; off by default) ---------------------
# Env-driven so a headless run can reproduce the SAME pull twice: CAP_SCRIPTED_PULL=1 with
# `runSofa -g batch -n N` gives deterministic A/B numbers (see diag_last.csv) without a hand
# on the mouse -- the only honest way to compare stability/peel tuning. (These knobs were
# lost as collateral in revert a432f1f, which reverted a peel change that happened to share
# its commit; they are test harness only and change no physics.)
SCRIPTED_PULL = os.environ.get("CAP_SCRIPTED_PULL", "0") == "1"
# Tunable so the harness can sweep from a gentle pull to a violent yank: a mouse drag is far
# harsher than the 6 s default -- the cursor can jump the target several units in ONE step,
# which is what actually triggers the snap.
PULL_END_T = float(os.environ.get("CAP_PULL_END_T", "6.0"))
PULL_MOVE = [float(v) for v in
             os.environ.get("CAP_PULL_MOVE", "1.5,0.0,3.0").split(",")]   # +x rim up/out

ENABLE_MOUSE = True
# Self-collision would let a folded flap rest ON the membrane instead of passing
# through it, but its raw penalty contact pumps energy into tight folds (a proven
# blow-up source), so it stays OFF until a constraint-based contact replaces it.
SELF_COLLISION = False
CONTACT_STIFFNESS = 200.0   # penalty contact strength (also used by the mouse pick)
# Contact proximities MUST stay well below the mesh edge length, or neighbouring
# triangles sit inside each other's alarm radius and the sheet pushes against
# itself. Derived from the mesh so a resolution change cannot break this silently.
ALARM_DISTANCE = 0.40 * G.EDGE_LEN
CONTACT_DISTANCE = 0.20 * G.EDGE_LEN

# Mouse-pull spring (F = stiffness * drag distance past the node). Must beat BREAK_FORCE
# to peel anything. Higher = the mesh follows the cursor sooner and the drag arrow stays
# SHORT (less "drag miles before it moves"); the per-step impulse is bounded by DISP_CLAMP
# / MAX_SPEED / MAX_STRETCH regardless, so raising it mainly costs a little more recoil,
# not stability. Tune live in the GUI (AttachBodyButtonSetting > stiffness, then Enter)
# or up front with CAP_MOUSE_STIFF. 400 was the old cautious default; 600 grabs noticeably
# better -- push to 800-1200 if it still feels heavy, drop it if recoil bothers you.
MOUSE_STIFFNESS = float(os.environ.get("CAP_MOUSE_STIFF", "600"))

# --- camera -------------------------------------------------------------------
# SofaGLFW hard-codes left-drag = orbit (not remappable from the scene), so pulling
# and orbiting share the same button.
LOCK_CAMERA = False              # True = disable orbiting entirely
# Freeze-orbit-while-grabbing. Left-drag both orbits and pulls (SofaGLFW hard-codes the
# binding), so without this the view swings around while you are trying to tear. The two
# object-COUNT detectors this used to rely on could not work -- SofaImGui keeps adding graph
# objects, so any baseline goes stale and the camera locks forever -- so it was left off.
# _is_grabbing() is now name-based and reliable, so it is on by default.
FREEZE_CAMERA_WHILE_PULLING = os.environ.get("CAP_FREEZE_CAM", "1") == "1"
CAM_PROBE = False                # diagnostic: print graph-object changes per step
# Keyboard (needs viewport focus): W/A/S/D or arrows pan, R re-centres, V locks orbit.
CAM_PAN_STEP = 1.5               # world units per pan key press

# --- stress field (foundation for the future tear criterion) -------------------
# Per-triangle principal stress computed in numpy from geometry (rest vs current):
# the FEM's own stress structs are unbindable from Python, and a geometric strain
# needs no FEM anyway. Output is minimal on purpose: a tear only cares WHERE sigma1
# peaks and WHICH WAY it points (crack runs perpendicular to it).
STRESS_MARKER = False    # 3D peak marker (off: terminal report only)
STRESS_TOP_N = 0         # extra markers beyond the peak
STRESS_TABLE_N = 5       # rows in the terminal sigma1 table
DEGEN_LO, DEGEN_HI = 0.25, 4.0   # area_ratio outside this = degenerate, sigma1 invalid


class _Adjacency:
    """CSR-style vertex->neighbours / vertex->triangles map that slices ON DEMAND.

    Storing these as a Python list-of-arrays meant materialising one slice per VERTEX every
    time the topology changed, and the topology changes on every vertex split while a tear
    runs. On this mesh that was ~2250 slices per rebuild and profiled at 31 ms per call even
    after the numpy rewrite -- the numpy work itself is about 1 ms, the rest was pure Python
    object churn. Almost every consumer wants exactly ONE vertex's neighbours (the crack tip),
    so keep the flat arrays and slice when asked."""

    __slots__ = ("flat", "cut")

    def __init__(self, flat, cut):
        self.flat, self.cut = flat, cut

    def __len__(self):
        return len(self.cut) - 1

    def __getitem__(self, v):
        return self.flat[self.cut[v]:self.cut[v + 1]]


def area_ratios(P, R, tris):
    """Per-triangle deformed/rest area -- the |det F| that principal_stress() also returns,
    but on its own. Purely geometric (two cross products), so callers that only need to know
    which elements have collapsed can skip the strain, the material law and the eigenvalues."""
    import numpy as np
    P, R, tris = np.asarray(P, float), np.asarray(R, float), np.asarray(tris, int)
    cur = np.linalg.norm(np.cross(P[tris[:, 1]] - P[tris[:, 0]],
                                  P[tris[:, 2]] - P[tris[:, 0]]), axis=1)
    rest = np.linalg.norm(np.cross(R[tris[:, 1]] - R[tris[:, 0]],
                                   R[tris[:, 2]] - R[tris[:, 0]]), axis=1)
    return cur / np.maximum(rest, 1e-12)
STRESS_LOG_EVERY = 1.0   # [s] between terminal reports
STRESS_HOT_FRAC = 0.5    # 'loaded' = above this fraction of the peak
SHOW_STRESS = True       # compute sigma1 every STRESS_EVERY steps
# SOFA's OWN heatmap: DataDisplay + OglColorMap colour the DEFORMING 3D mesh by sigma1
# (fed from the controller). It SIGABRTs this build's imgui GUI at visual init (batch
# passes, GUI dies) -- which is why the decoupled browser UI exists. But that crash is
# imgui-specific: the Qt / GLFW backends may render it fine. Enable with CAP_STRESS_COLOR=1
# and launch a non-imgui GUI (run_cap.ps1 -SofaHeatmap -Gui qt) to try it and compare.
# Note: this colours the ACTUAL deforming membrane in 3D, whereas the browser UI shows the
# flat undeformed reference disc -- two different, complementary views.
STRESS_COLOR = os.environ.get("CAP_STRESS_COLOR", "0") == "1"
# Steps between stress updates. This is the WHOLE cost of the stress observer + UI feed
# (the O(triangles) numpy + serialisation), so it is the main FPS knob when the heatmap is
# on. 6 = ~8 Hz of field at dt=0.02, smooth enough for the heatmap while keeping the loop
# fast so the mouse-pull stays stable. Lower (3) = smoother field, more FPS cost; raise if
# dragging still feels heavy. Tunable with CAP_STRESS_EVERY.
STRESS_EVERY = int(os.environ.get("CAP_STRESS_EVERY", "6"))
# Observer constitutive constants for sigma = C(E,nu):eps. Used ONLY in mass-spring
# mode (no continuum E exists there, so these set a geometric-strain scale). In FEM
# mode the observer instead reads the FEM's live youngModulus/poissonRatio, so the
# reported sigma1 equals the stress the FEM is actually using to make force (they share
# the same F and constitutive law) -- see _stress_material().
STRESS_E = 1200.0        # E for sigma = C:eps
STRESS_NU = 0.3

# Live force-field UI (decoupled): with CAP_HEATMAP=1 the scene keeps its normal
# deformation view UNCHANGED and additionally serves the sigma1 field over a tiny local
# HTTP server (stdlib, background thread). A self-contained browser page (stress_viewer
# .html, served at "/") polls it and draws a live heatmap of the UNDEFORMED reference
# disc with hover tooltips (sigma1 / crack direction / crack class), a freeze toggle and
# a colour scale. This lives OUTSIDE SofaImGui on purpose: SofaImGui cannot host custom
# widgets, and doing the map in our own page is what makes hover/values possible. The
# scene's physics and rendering are untouched -- this only reads and publishes.
STRESS_UI = os.environ.get("CAP_HEATMAP", "0") == "1"
STRESS_UI_PORT = int(os.environ.get("CAP_UI_PORT", "8790"))
STRESS_UI_OPEN = os.environ.get("CAP_UI_OPEN", "1") == "1"   # auto-open the browser
VIEWER_HTML = os.path.join(_HERE, "stress_viewer.html")
# Default ceiling of the viewer's colour ramp (sigma1 -> red). The page auto-scales to
# the live peak, but this is the starting/fallback scale. Pull-front sigma1 runs a few
# hundred at normal drag, ~2000 on a violent yank. Tune with CAP_HEAT_MAX.
STRESS_HEAT_MAX = float(os.environ.get("CAP_HEAT_MAX", "300"))
# Recording: every published frame is appended to a JSONL log (one frame per line: t,
# step, per-triangle sigma1 + crack angle + area ratio) for offline analysis, AND kept
# in a capped in-memory ring the viewer's timeline can scrub -- so you can drag freely
# without watching, then review any past moment. Log is overwritten each run.
STRESS_LOG = os.environ.get("CAP_STRESS_LOG", "1") == "1"
STRESS_LOG_PATH = os.path.join(_HERE, "stress_log.jsonl")
# Stamped once per process, so every launch's takes get their own filenames.
_RUN_STAMP = __import__("time").strftime("%m%d_%H%M%S")
STRESS_HISTORY = int(os.environ.get("CAP_STRESS_HISTORY", "1500"))   # frames kept for scrub
# How many FINISHED takes (one per scene reset) stay replayable in the browser. Each holds
# up to STRESS_HISTORY frames in memory, so keep this small; the JSONL on disk is per-take
# and unbounded (stress_log_<id>.jsonl), so nothing is lost either way.
STRESS_SESSIONS_MAX = int(os.environ.get("CAP_STRESS_SESSIONS", "6"))

# --- safety nets (all applied in onAnimateEnd, before the frame is drawn) ------
# Layered by failure mode; each net is a hard geometric/kinematic bound that no
# stiffness value can bypass. The textbook cure for the penalty-spring impulses is a
# constraint-based attach (FreeMotionAnimationLoop + LCP) -- a much bigger rework.
MAX_SPEED = 25.0         # units/s speed cap; normal dragging is ~1-3. 0 = off
MAX_COORD = 50.0         # |coord| beyond this = runaway -> rewind to last healthy
# Gross-overstretch panic, as a MULTIPLE of MAX_STRETCH. MAX_COORD alone cannot see a
# crumple: a session that ran to 20.8x edge stretch peaked at |coord| 13.5, nowhere near 50,
# so nothing fired and the mesh just got progressively worse until it looked wadded up. Edge
# stretch is the direct measure of that, and 1.6 -> 20.8 is unambiguous. 0 = off.
STRAIN_PANIC = float(os.environ.get("CAP_STRAIN_PANIC", "4.0"))
                         # frame (the cap lives within ~15 even fully lifted). 0 = off
# Strain clamp: no edge may stretch past MAX_STRETCH x its rest length -- the
# membrane is inextensible-ish, and without this an adhesion avalanche lets
# triangles inflate 8-33x and invert. Projected back per step, Gauss-Seidel style.
MAX_STRETCH = float(os.environ.get('CAP_MAX_STRETCH', '1.6'))        # 0 = off
# Relaxation passes per step. Three is enough while the sheet is anchored, but a FREE
# rim plus a running tear leaves long, nearly-detached strips that a few Gauss-Seidel
# passes cannot pull back (measured: edges reaching 24x rest against a 1.6 limit).
STRAIN_ITERS = int(os.environ.get('CAP_STRAIN_ITERS', '3'))
# Iterations used by the emergency containment path, which runs only when a runaway
# cannot be rewound. Far more than the per-step count: this is a one-off recovery.
STRAIN_PANIC_ITERS = int(os.environ.get('CAP_STRAIN_PANIC_ITERS', '60'))
# Anti-collapse (FEM-only): a triangle can go collinear with all edges at normal
# length -> zero area -> the FEM divides by it. Repair below MIN_AREA_FRAC of rest
# area by lifting the flattest vertex; if more than SEVERE_COLLAPSE collapse in one
# step it is an acute blow-up -> rewind the whole sheet instead. Mass-spring mode
# skips both (springs never divide by area).
MIN_AREA_FRAC = 0.05     # 0 = off
SEVERE_COLLAPSE = 5
# On full peel the sheet is free and still carries the pull momentum; remove the
# momentum (zero velocity + ramp damping to this value + drop the lens obstacle)
# rather than patch geometry. Safe at 60 because the damper is implicit.
PEEL_SETTLE_DAMPING = 60.0

# --- rung-1 tearing (pre-slit circle; off -- kept as reference) -----------------
# generate_cap doubles the vertices of the ring nearest TEAR_RADIUS; stitch springs
# hold the two coincident copies together so the mesh looks continuous. "Tearing"
# = disabling stitches progressively around the circle. Artificial (the tear should
# follow the instrument); runtime path-splitting is the future replacement.
SCRIPTED_TEAR = False
STITCH_K = 2500.0        # holds the slit closed; match EDGE_STIFFNESS
TEAR_T = 3.0             # [s] tear start
TEAR_DURATION = 3.0      # [s] to go all the way around
LIFT_HEIGHT = 4.5        # scripted lift of the freed disc
FIX_OUTER_RIM = os.environ.get("CAP_FIX_RIM", "0") == "1"
# Anatomically the anterior capsule is held at its periphery by the ZONULES. Without that
# anchor a pull does not build tearing stress, it just peels the whole cap off the lens and
# the free sheet crumples into a wad -- which is exactly what happened in tear mode. So tear
# mode anchors a NARROW outer ring by default (CAP_FIX_RIM=0 to switch it off). Narrow on
# purpose: clamping a wide band is what made an earlier attempt feel dead to pull.
RIM_ANCHOR_FRAC = float(os.environ.get("CAP_RIM_FRAC", "0.96"))
if CAP_TEAR:
    FIX_OUTER_RIM = os.environ.get("CAP_FIX_RIM", "1") == "1"
if PAPER_MODE:
    # With no adhesion the rim anchor is the only thing holding the capsule, and it is also
    # the anatomically right boundary (the zonules insert at the periphery). Still overridable,
    # because it is the single biggest lever on whether the membrane can be folded at all.
    FIX_OUTER_RIM = os.environ.get("CAP_FIX_RIM", "1") == "1"
# THE RIM ANCHOR IS WHY -Tear FEELS RIGID. Measured on one identical rim-grab-and-fold:
#
#   no -Tear, rim free   : grab lifts 8.93, 1284 nodes above 1.0, max edge stretch 1.12
#   -Tear, rim anchored  : grab lifts 0.98, ZERO nodes above 1.0   <- cannot be folded at all
#   -Tear, rim free      : grab lifts 5.69,  728 nodes above 1.0, and it still tears (cut 61)
#
# So "I could fold it before -Tear but not after" is exactly this line: tear mode anchors the
# rim, and an anchored rim cannot be lifted. The anchor was added because a free rim let a pull
# peel the whole cap off and crumple it -- but that trade is now measurable rather than
# assumed, and CAP_FIX_RIM=0 (run_cap.ps1 -FreeRim) gets the folding back. The catch is real:
# with a free rim AND a running tear, edges reach 24x their rest length (limit 1.6). More
# relaxation passes do NOT fix it -- measured 3/12/40 iterations giving 24x/150x/38x -- so the
# over-stretch is not the clamp being under-iterated, and it is the thing to solve next.

# --- automatic plasticity (viscoplastic creep) ---------------------------------
# Peeled nodes slowly adopt their current shape as rest shape, so releasing the
# mouse barely springs back. Glued nodes keep their rest on the lens.
PLASTIC_RATE = 0.35      # 0 = fully elastic, 1 = putty; fraction forgotten per update
PLASTIC_EVERY = 5        # steps between updates (creep feel is coupled to dt)

FREEZE_T = None          # [s] auto-freeze timer; None = creep handles it (F = manual)
RELEASE_AFTER_FREEZE = True
# ------------------------------------------------------------------------------

PLUGINS = [
    "Sofa.Component.IO.Mesh",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.SolidMechanics.Spring",
    "Sofa.Component.MechanicalLoad",
    "Sofa.Component.Mass",
    "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Engine.Select",
    "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Collision.Detection.Algorithm",
    "Sofa.Component.Collision.Detection.Intersection",
    "Sofa.Component.Collision.Geometry",
    "Sofa.Component.Collision.Response.Contact",
    "Sofa.Component.Visual",
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.Setting",
    "Sofa.GUI.Component",            # AttachBodyButtonSetting (mouse-pull strength)
    "Sofa.GL.Component.Rendering3D",   # OglModel, DataDisplay
    "Sofa.GL.Component.Rendering2D",   # OglColorMap (stress legend)
]


def principal_stress(pos, rest, tris, E=None, nu=None):
    """Per-triangle max principal stress sigma1 + its world direction, from geometry
    alone: local 2D frame -> in-plane deformation gradient F -> Green strain
    eps = (F'F - I)/2 -> plane-stress sigma -> principal value/direction.

    Returns (sigma1, dir3d, area_ratio); area_ratio = |det F|, far from 1 means the
    triangle is degenerate and its sigma1 is not physical. A crack would run
    PERPENDICULAR to dir3d (Rankine); fiber weighting can be layered on later.
    """
    import numpy as np
    E = STRESS_E if E is None else E
    nu = STRESS_NU if nu is None else nu

    def frame(P):
        e1 = P[:, 1] - P[:, 0]
        e2 = P[:, 2] - P[:, 0]
        n = np.cross(e1, e2)
        x = e1 / np.maximum(np.linalg.norm(e1, axis=1), 1e-12)[:, None]
        z = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
        return x, np.cross(z, x)

    def uv(P, x, y):
        e1 = P[:, 1] - P[:, 0]
        e2 = P[:, 2] - P[:, 0]
        return np.stack([np.stack([(e1 * x).sum(1), (e2 * x).sum(1)], 1),
                         np.stack([(e1 * y).sum(1), (e2 * y).sum(1)], 1)], 1)

    xr, yr = frame(rest[tris])
    xc, yc = frame(pos[tris])
    Dm = uv(rest[tris], xr, yr)
    Ds = uv(pos[tris], xc, yc)
    # Guarded per-triangle 2x2 inverse: a degenerate REST triangle would make a
    # batched np.linalg.inv raise for the whole array; here it just gets Dm_inv=0
    # -> F=0 -> area_ratio=0 -> flagged degenerate, everyone else still measured.
    a11 = Dm[:, 0, 0]; a12 = Dm[:, 0, 1]; a21 = Dm[:, 1, 0]; a22 = Dm[:, 1, 1]
    det = a11 * a22 - a12 * a21
    safe = np.abs(det) > 1e-9
    inv_det = np.where(safe, 1.0 / np.where(safe, det, 1.0), 0.0)
    Dm_inv = np.empty_like(Dm)
    Dm_inv[:, 0, 0] = a22 * inv_det; Dm_inv[:, 0, 1] = -a12 * inv_det
    Dm_inv[:, 1, 0] = -a21 * inv_det; Dm_inv[:, 1, 1] = a11 * inv_det
    F = Ds @ Dm_inv
    eps = 0.5 * (np.einsum('tki,tkj->tij', F, F) - np.eye(2))
    c = E / (1.0 - nu * nu)
    sxx = c * (eps[:, 0, 0] + nu * eps[:, 1, 1])
    syy = c * (eps[:, 1, 1] + nu * eps[:, 0, 0])
    sxy = c * (1.0 - nu) * eps[:, 0, 1]
    mid = 0.5 * (sxx + syy)
    dev = np.sqrt(np.maximum(((sxx - syy) * 0.5) ** 2 + sxy ** 2, 0.0))
    s1 = mid + dev
    # SECOND principal stress: with (s1, s2, principal angle) the FULL tensor can be
    # rebuilt, so the normal stress along ANY direction u is sigma_u = s1 cos^2(psi) +
    # s2 sin^2(psi), psi = angle(u, sigma1-dir). That is exactly what the INRIA
    # anisotropic tear criterion (Dequidt 2013 Eq.3) needs -- s1 alone is not enough.
    s2 = mid - dev
    area_ratio = np.abs(np.linalg.det(F))     # 1.0 = undeformed area
    # principal direction (2D angle) mapped back into 3D via the current frame
    # NO np.maximum guard on the denominator. arctan2(y, x) takes the QUADRANT from the
    # sign of x, so clamping x to >= 1e-12 destroys exactly the information it needs:
    # every state with syy > sxx landed on the wrong branch. Checked against the analytic
    # solution, uniaxial tension along y came out 0 deg instead of 90 deg, and mixed
    # states were off by 22.5 deg. The crack runs PERPENDICULAR to sigma1 (Rankine), so a
    # 90 deg error swaps "circumferential (good)" and "radial (runs to the periphery)" --
    # it inverts the one classification this field exists to produce. The guard was also
    # pointless: arctan2 does no division and handles x = 0 (and x = y = 0) itself.
    ang = 0.5 * np.arctan2(2.0 * sxy, sxx - syy)
    d3 = np.cos(ang)[:, None] * xc + np.sin(ang)[:, None] * yc
    return s1, s2, d3, area_ratio


# --- decoupled stress UI: a tiny local HTTP server the browser viewer polls -----------
# Everything the SOFA thread publishes is a pre-serialized JSON string, swapped/appended
# atomically (GIL), so the server thread reads without a lock:
#   _STRESS_GEOMETRY = the STATIC reference disc (rest-shape xy + triangles), sent once.
#   _STRESS_LATEST   = the newest per-step frame (sigma1, crack angle, area ratio, time).
#   _STRESS_HISTORY  = a capped deque of recent frames, for the viewer's timeline scrubber
#                      (review a moment AFTER dragging -- no need to watch it live).
#   _STRESS_LOG_FH   = append-only JSONL of EVERY frame for offline analysis (full record).
import json as _json
import collections as _collections

_STRESS_GEOMETRY = "{}"
_STRESS_LATEST = "{}"
_STRESS_HISTORY = _collections.deque()
_STRESS_TOTAL = 0                 # frames ever published (also the next frame's global index)
_STRESS_LOG_FH = None
# SESSIONS: each scene reset ends the current recording and starts a new one, instead of
# throwing the old frames away. _STRESS_SESSIONS holds the finished ones (id, frames, time
# span) so the browser can pick WHICH pull to replay; _STRESS_SESSION_ID is the live one.
_STRESS_SESSIONS = []
_STRESS_SESSION_ID = 0


def _stress_build_frame(i, step, t, s1, s2, sdir, aratio):
    """Serialise one frame to a JSON string. All per-triangle numpy work is VECTORISED
    (np.round + one tolist) rather than a per-element Python loop -- the loop over 4166x3
    values roughly halved the framerate, and a slower loop lets the real-time mouse target
    jump further per step, so DISP_CLAMP saturates and the sheet snaps. So this cost was
    itself a source of the 'distort and spring open' instability. A background thread does
    NOT help: the GIL serialises it against the physics thread anyway (measured). The real
    levers are this vectorisation and STRESS_EVERY (how often we do it)."""
    import numpy as np
    bad = (aratio < DEGEN_LO) | (aratio > DEGEN_HI)
    good = s1[~bad]
    smax = float(good.max()) if good.size else 0.0
    # Robust colour-scale ceiling: a few near-degenerate triangles at the pull point reach
    # sigma1 ~100x the bulk; scaling the ramp to the raw max washes the map blue. The 98th
    # percentile of the loaded cells tracks the real working range (viewer auto-scales to it).
    pos = good[good > 0.0]
    sp98 = float(np.percentile(pos, 98)) if pos.size else 0.0
    ang = np.degrees(np.arctan2(sdir[:, 1], sdir[:, 0]))
    return _json.dumps({
        "i": i, "step": int(step), "t": round(float(t), 3),
        "gver": _STRESS_GEOM_VER,        # topology version these arrays belong to
        "tear": dict(_TEAR_STATE),       # live tearing status for the viewer
        "crack": list(_TEAR_PATH["path"]),   # active front (ordered vertex chain)
        "paths": [list(x) for x in _TEAR_PATH["paths"]],   # every front, incl. finished ones
        "lips": list(_TEAR_PATH["lips"]),    # [duplicate, original] split pairs
        "pull": dict(_PULL_STATE),           # where the instrument is pulling, and how hard
        "adh": _ADH_STATE["glued"],          # per-vertex "1"=still on the lens, "0"=peeled off
        "paper": PAPER_MODE,                 # INRIA setup only: no adhesion exists to report
        "s1": np.round(s1, 1).tolist(),
        "s2": np.round(s2, 1).tolist(),
        "ang": np.round(ang, 1).tolist(),
        "aratio": np.round(aratio, 2).tolist(),
        "smax": round(smax, 1), "sp98": round(sp98, 1), "heatmax": STRESS_HEAT_MAX,
    })


_STRESS_GEOM_VER = 0
# Live tearing telemetry, mirrored into every frame so the browser can SHOW whether tearing
# is even enabled and how close the tip is to the criterion. Without this the only way to
# tell "-Tear was not passed" from "the threshold is too high" was reading the console.
_TEAR_STATE = {"on": False, "len": 0, "c": 0.0, "thr": 0.0, "tipr": 0.0, "why": "off",
               "tipx": 0.0, "tipy": 0.0, "s1": 0.0, "s2": 0.0, "th1": 0.0,
               "fib": 0.0, "dang": 0.0, "su": 0.0, "sbu": 0.0, "loc": 0.0,
               "lefm": 1.0}
# The crack itself, for the browser to DRAW rather than just count. A tear is a CHAIN OF
# MESH EDGES: "path" is the ordered vertex list, so consecutive entries are the edges the
# tear has cut, and the last entry is the live tip. "lips" pairs each duplicated vertex with
# the original it was split from -- the two sides of the cut, whose separation is the crack
# opening. Both index the CURRENT reference disc, so they are only meaningful together with
# the frame's "gver".
_TEAR_PATH = {"path": [], "lips": [], "paths": []}
# WHERE THE INSTRUMENT IS PULLING, and how hard. WHETHER a pull is happening comes from
# _is_grabbing() -- the mouse interactor's own objects in the scene graph -- not from the
# force magnitude. Magnitude cannot tell the two apart: measured, max|F| is 0.0 with nobody
# touching the capsule and ~137 during a drag, but the recoil AFTER letting go peaks at 1754,
# far above the drag itself. A threshold that ignores the recoil would also ignore gentle
# pulls. Given that a grab IS happening, argmax|f| then identifies WHICH node is held, exactly
# (checked against a known pulled node: argmax matched, 5 of 2171 nodes above 10% of peak).
_PULL_STATE = {"on": False, "x": 0.0, "y": 0.0, "fx": 0.0, "fy": 0.0, "mag": 0.0,
               "seg": -1}
# Which vertices are STILL GLUED to the lens, as a compact "1"/"0" string (one character per
# vertex, ~2 KB against the ~100 KB of stress arrays already in a frame). The map started out
# uniformly attached and there was no way to see what had come away -- so "the capsule is
# being stripped wherever I drag" could be felt but not checked.
_ADH_STATE = {"glued": "", "n": 0}
# Retained only as a floor on what counts as a meaningful grab force.
PULL_MIN_FORCE = float(os.environ.get("CAP_PULL_MINF", "0.0"))
# A TAKE is one scene run: reloading the scene in SOFA archives the previous recording and
# starts a new file. Inside one take you normally pull, let go, pull somewhere else, pause,
# carry on -- so a take is not a single gesture. Each grab-to-release is numbered as a PULL
# so the timeline can show where they are and jump between them; frames between pulls carry
# seg = -1. PULL_GAP is how long the force may stay below PULL_MIN_FORCE before the pull is
# considered over, so a momentary dip mid-drag does not split one gesture into two.
PULL_GAP = float(os.environ.get("CAP_PULL_GAP", "0.35"))
_PULL_SEG = {"n": 0, "cur": -1, "last_t": -1e9}


_GEOM_PENDING = None      # (rest, tris) waiting to be serialised on demand


def _publish_geometry(rest, tris):
    """(Re)publish the reference disc the browser draws on. Tearing changes the topology at
    runtime, so the version is bumped on every split -- the viewer watches it and refetches,
    otherwise it would keep drawing the OLD triangle list while the stress arrays already
    describe the NEW one (silently mismatched, worse than blank).

    LAZY on purpose: serialising ~2200 vertices + 4166 triangles to JSON on every split ran
    on the physics thread and was pure waste, since the browser only fetches /geometry when
    the version actually changes. Store the arrays, bump the version, and encode later."""
    global _GEOM_PENDING, _STRESS_GEOM_VER
    _STRESS_GEOM_VER += 1
    _GEOM_PENDING = (rest, tris)      # kept as-is; encoded later on the HTTP thread


def _geometry_json():
    """Serialise the pending reference disc (called from the HTTP thread, not physics)."""
    global _STRESS_GEOMETRY, _GEOM_PENDING
    if _GEOM_PENDING is not None:
        rest, tris = _GEOM_PENDING
        _GEOM_PENDING = None
        _STRESS_GEOMETRY = _json.dumps({
            "ver": _STRESS_GEOM_VER,
            "verts": [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in rest],
            "tris": [[int(a), int(b), int(c)] for a, b, c in tris],
        })
    return _STRESS_GEOMETRY


# Past pulls survive the app. Every take is already written to stress_log_<id>.jsonl line by
# line, so the recording of a session is complete the moment SOFA exits (or is paused, or
# crashes) -- but the browser could only ever see takes still held in memory, which vanish
# with the process. These helpers expose the FILES as takes too, so any earlier pull can be
# reopened and scrubbed. Indexed lazily by byte offset, cached on (size, mtime), so a 30 MB
# log costs one pass the first time it is opened and nothing afterwards.
_DISK_INDEX = {}
_DISK_COUNT = {}


def _disk_take_files():
    import glob
    base = os.path.dirname(STRESS_LOG_PATH) or "."
    stem = os.path.basename(STRESS_LOG_PATH).replace(".jsonl", "")
    return sorted(glob.glob(os.path.join(base, stem + "*.jsonl")))


def _disk_stat(path):
    try:
        st = os.stat(path)
        return (st.st_size, int(st.st_mtime))
    except OSError:
        return None


def _disk_count(path):
    """Frame count and first/last timestamp, WITHOUT building a full index.

    Listing the takes must stay cheap: one of these logs is 159 MB, and walking it line by
    line to offer it in a dropdown blocked the request past the browser's fetch timeout, so
    no disk take was ever listed at all. Counting newlines in big chunks is ~100x faster, and
    the last timestamp comes from a short read at the end of the file rather than a scan."""
    key = _disk_stat(path)
    if key is None:
        return None
    hit = _DISK_COUNT.get(path)
    if hit and hit[0] == key:
        return hit[1]
    n = 0
    tail = b""
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 22)
                if not chunk:
                    break
                n += chunk.count(bytes([10]))
            if key[0]:
                # A frame is ~100 KB of JSON, so the window must be comfortably
                # larger than one line or the tail never contains a complete one
                # (that is why every take listed t1 = 0.0).
                f.seek(max(0, key[0] - (1 << 22)))
                tail = f.read()
            f.seek(0)
            head = f.readline()
    except OSError:
        return None

    def _t(line):
        try:
            return float(_json.loads(line).get("t", 0.0))
        except Exception:  # noqa: BLE001
            return 0.0
    lines = [x for x in tail.split(bytes([10])) if x.strip()]
    res = (n, _t(head), _t(lines[-1]) if lines else 0.0)
    _DISK_COUNT[path] = (key, res)
    return res


def _disk_index(path):
    """[byte offset of each frame] -- built only when a take is actually opened."""
    key = _disk_stat(path)
    if key is None:
        return None
    hit = _DISK_INDEX.get(path)
    if hit and hit[0] == key:
        return hit[1]
    offs, pos = [], 0
    try:
        with open(path, "rb") as f:
            for line in f:
                if line.strip():
                    offs.append(pos)
                pos += len(line)
    except OSError:
        return None
    _DISK_INDEX[path] = (key, offs)
    return offs


def _disk_frame(path, i):
    """One frame out of a log file, by index. Builds the offset index on first use."""
    offs = _disk_index(path)
    if not offs or not (0 <= i < len(offs)):
        return b"{}"
    try:
        with open(path, "rb") as f:
            f.seek(offs[i])
            return f.readline().strip() or b"{}"
    except OSError:
        return b"{}"


_SEG_CACHE = {}


def _segments_of(lines_iter, n):
    """Turn a per-frame [(t, seg)] stream into contiguous pull ranges."""
    out, cur = [], None
    for i, (t, seg) in enumerate(lines_iter):
        if seg is not None and seg > 0:
            if cur is None or cur["seg"] != seg:
                if cur is not None:
                    out.append(cur)
                cur = {"seg": seg, "i0": i, "i1": i, "t0": t, "t1": t}
            else:
                cur["i1"], cur["t1"] = i, t
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


def _scan_segments(path):
    """Pull ranges of a take on disk, WITHOUT parsing whole frames.

    A frame is ~100 KB, almost all of it the per-triangle arrays, and json-decoding 1600 of
    them to read two small fields would take seconds. The dict is written with "t" and "pull"
    near the FRONT, so a bounded prefix of each line is enough."""
    import re
    key = _disk_stat(path)
    if key is None:
        return []
    hit = _SEG_CACHE.get(path)
    if hit and hit[0] == key:
        return hit[1]
    offs = _disk_index(path)
    if not offs:
        return []
    rt = re.compile(rb'"t":\s*([-0-9.eE]+)')
    rs = re.compile(rb'"seg":\s*(-?\d+)')
    rows = []
    try:
        with open(path, "rb") as f:
            for o in offs:
                f.seek(o)
                head = f.read(4096)
                mt, ms = rt.search(head), rs.search(head)
                rows.append((float(mt.group(1)) if mt else 0.0,
                             int(ms.group(1)) if ms else None))
    except OSError:
        return []
    res = _segments_of(rows, len(rows))
    _SEG_CACHE[path] = (key, res)
    return res


def _disk_takes():
    out = []
    live = None
    if _STRESS_LOG_FH is not None:
        live = getattr(_STRESS_LOG_FH, "name", None)
    for path in _disk_take_files():
        info = _disk_count(path)
        if not info or not info[0]:
            continue
        n, t0, t1 = info
        out.append({"id": "f:" + os.path.basename(path), "n": n,
                    "t0": t0, "t1": t1, "live": False, "disk": True,
                    "writing": (live is not None and os.path.abspath(live) == os.path.abspath(path))})
    return out


def _stress_record(js):
    """Store one serialized frame: newest pointer + capped history + disk log."""
    global _STRESS_LATEST, _STRESS_TOTAL, _STRESS_LOG_FH
    _STRESS_LATEST = js
    _STRESS_HISTORY.append(js)
    while len(_STRESS_HISTORY) > STRESS_HISTORY:
        _STRESS_HISTORY.popleft()
    if STRESS_LOG:
        try:
            if _STRESS_LOG_FH is None:
                # ONE FILE PER TAKE, named by WHEN it ran, not by its number within the run.
                # Session ids restart at 1 in every new process, so numbering alone meant each
                # launch reopened stress_log_1.jsonl with mode "w" and destroyed the previous
                # launch's first take -- exactly the recording you would want to go back to.
                # A timestamp makes takes accumulate across runs, which is the whole point of
                # being able to reopen an earlier pull in the browser.
                stamp = _RUN_STAMP
                path = STRESS_LOG_PATH.replace(
                    ".jsonl", f"_{stamp}_{max(_STRESS_SESSION_ID, 1)}.jsonl")
                _STRESS_LOG_FH = open(path, "w", buffering=1)
            _STRESS_LOG_FH.write(js + "\n")
        except Exception:  # noqa: BLE001
            pass           # a disk hiccup must never take down the sim
    _STRESS_TOTAL += 1


def _start_stress_server(port, open_browser):
    """Serve the viewer page + the stress field on 127.0.0.1:port (daemon thread).

    Routes: GET /          -> stress_viewer.html (the self-contained browser UI)
            GET /geometry  -> the static reference disc (fetched once by the page)
            GET /stress    -> the newest per-triangle sigma1 frame (polled live)
            GET /meta      -> {count, first, last, n}: how many frames are buffered
            GET /frame?i=N -> the buffered frame with global index N (timeline scrubber)
    Returns True if the server started. Failure (e.g. port in use) is non-fatal: the
    scene keeps running, just without the UI feed.
    """
    import threading, http.server
    from urllib.parse import urlparse, parse_qs

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):        # silence per-request console spam
            pass

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                if self.path.startswith("/stress"):
                    self._send(_STRESS_LATEST.encode(), "application/json")
                elif self.path.startswith("/sessions"):
                    # the finished takes (one per scene reset) + the live one, so the page
                    # can offer "which pull do you want to replay?"
                    out = [{"id": s["id"], "n": len(s["frames"]),
                            "t0": s["t0"], "t1": s["t1"], "live": False}
                           for s in _STRESS_SESSIONS]
                    out.append({"id": _STRESS_SESSION_ID, "n": len(_STRESS_HISTORY),
                                "t0": 0.0, "t1": 0.0, "live": True})
                    try:
                        out.extend(_disk_takes())      # earlier pulls, straight off disk
                    except Exception:  # noqa: BLE001
                        pass
                    self._send(_json.dumps({"sessions": out}).encode(), "application/json")
                elif self.path.startswith("/segments"):
                    # where the PULLS are inside a take: one take is one scene run, but a run
                    # normally contains several grab-release gestures, and the timeline should
                    # show them rather than presenting a single undifferentiated span.
                    q = parse_qs(urlparse(self.path).query)
                    sid = q.get("s", [""])[0]
                    if sid.startswith("f:"):
                        base = os.path.dirname(STRESS_LOG_PATH) or "."
                        segs = _scan_segments(os.path.join(base, os.path.basename(sid[2:])))
                    else:
                        rows = []
                        src = _STRESS_HISTORY
                        if sid != "" and int(sid) != _STRESS_SESSION_ID:
                            arc = next((x for x in _STRESS_SESSIONS
                                        if x["id"] == int(sid)), None)
                            src = arc["frames"] if arc else []
                        # Read "t" and "pull.seg" out of the FRONT of each frame instead of
                        # decoding it. A frame is ~100 KB and the buffer holds up to 1500 of
                        # them, so json-parsing the lot -- on every poll, which the page does
                        # several times a second -- saturated the server and starved /stress:
                        # the page froze while the simulation was still happily publishing.
                        import re as _re
                        _rt = _re.compile(r'"t":\s*([-0-9.eE]+)')
                        _rs = _re.compile(r'"seg":\s*(-?\d+)')
                        for fr in list(src):
                            head = fr[:4096]
                            mt, ms = _rt.search(head), _rs.search(head)
                            rows.append((float(mt.group(1)) if mt else 0.0,
                                         int(ms.group(1)) if ms else None))
                        segs = _segments_of(rows, len(rows))
                        if sid == "" or int(sid) == _STRESS_SESSION_ID:
                            # The live take is scrubbed by GLOBAL frame index, while the
                            # history buffer these were computed over is 0-based, so the
                            # bands landed in the wrong place and "next pull" could never
                            # find one ahead of the live frame.
                            off = _STRESS_TOTAL - len(_STRESS_HISTORY)
                            for g in segs:
                                g["i0"] += off
                                g["i1"] += off
                    self._send(_json.dumps({"segments": segs}).encode(),
                               "application/json")
                elif self.path.startswith("/meta"):
                    n = len(_STRESS_HISTORY)
                    meta = {"count": _STRESS_TOTAL, "n": n,
                            "first": _STRESS_TOTAL - n, "last": _STRESS_TOTAL - 1,
                            "session": _STRESS_SESSION_ID,
                            "nsessions": len(_STRESS_SESSIONS)}
                    self._send(_json.dumps(meta).encode(), "application/json")
                elif self.path.startswith("/frame"):
                    q = parse_qs(urlparse(self.path).query)
                    i = int(q.get("i", ["-1"])[0])
                    sid = q.get("s", [""])[0]
                    if sid.startswith("f:"):           # a take read from a log FILE
                        base = os.path.dirname(STRESS_LOG_PATH) or "."
                        name = os.path.basename(sid[2:])       # never leave the folder
                        self._send(_disk_frame(os.path.join(base, name), i),
                                   "application/json")
                        return
                    if sid != "" and int(sid) != _STRESS_SESSION_ID:
                        # frame from an ARCHIVED take: index is 0-based within that take
                        arc = next((s for s in _STRESS_SESSIONS if s["id"] == int(sid)), None)
                        if arc and 0 <= i < len(arc["frames"]):
                            self._send(arc["frames"][i].encode(), "application/json")
                        else:
                            self._send(b"{}", "application/json")
                        return
                    pos = i - (_STRESS_TOTAL - len(_STRESS_HISTORY))
                    if 0 <= pos < len(_STRESS_HISTORY):
                        self._send(_STRESS_HISTORY[pos].encode(), "application/json")
                    else:
                        self._send(b"{}", "application/json")
                elif self.path.startswith("/geometry"):
                    self._send(_geometry_json().encode(), "application/json")
                else:
                    with open(VIEWER_HTML, "rb") as f:
                        self._send(f.read(), "text/html; charset=utf-8")
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, OSError):
                pass          # browser hung up mid-response (fetch timeout / reload /
                              # tab close) -- normal for a polled feed, ignore. NOTE:
                              # ConnectionAbortedError is the Windows case (WinError 10053)
                              # and MUST be caught here, else it falls through below.
            except Exception:  # noqa: BLE001
                # send_error puts the message in the HTTP status line, which is latin-1
                # only -- a localised (e.g. Chinese) OS error string would itself raise
                # UnicodeEncodeError. Use the default ASCII reason phrase, and never let
                # the error handler crash the request thread.
                try:
                    self.send_error(500)
                except Exception:  # noqa: BLE001
                    pass

    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    except OSError as e:
        print(f"[StressUI] could not bind 127.0.0.1:{port} ({e}); UI disabled")
        return False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"[StressUI] live force field at {url}  (open it in a browser)")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    return True


def _make_controller(fem, springs, bending, mo, adhesion, pull, mouse, damper,
                     topo, display, camera, root, probe, stitch, central, lift,
                     anchor_mo=None, splitter=None):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.fem, self.springs, self.bending = fem, springs, bending
            self.mo, self.adhesion, self.pull = mo, adhesion, pull
            self.mouse, self.damper = mouse, damper
            self.topo, self.display = topo, display
            self.camera, self.root = camera, root
            self.anchor_mo = anchor_mo   # adhesion anchors (tangential-only mode)
            self.splitter = splitter     # official-API topology splitter, or None
            self.probe = probe
            self.last_stress_log = -1e9
            self.stitch = stitch
            self.central = central
            self.lift = lift
            self.n_stitch = len(stitch.indices1.value) if stitch else 0
            self.enabled = [True] * self.n_stitch     # per-stitch alive flag
            self.tear_detached = False
            self.hot_tri = -1
            self.hot_pos = None
            self.hot_dir = None
            self.edges = None
            self.edge_rest = None
            self.base_objs = None      # graph snapshot taken on the first step
            self.grabbing = False
            self.last_good = None      # last all-finite positions, for the NaN-rollback net
            self.tris = None
            self.sigma1_max = 0.0
            self.paper_done = False
            self.adhered = None
            self.peel_fade = {}        # node -> decaying adhesion stiffness (peel fade-out)
            self.nbr = None            # per-node neighbours, for front-only peeling
            self.boundary = None       # mesh-boundary nodes = crack initiation sites
            self.dup_of = {}           # duplicate vertex -> the lip it was split from
            self._visual = None        # rendered skin; must be re-pushed after every split
            self._rest_cache = None    # (step, rest array) so a step re-reads it once
            self._field_cache = None   # (key, s1, area_ratio, centroids) per step
            self._spring_debt = 0      # splits since the edge springs were rebuilt
            self._spring_dirty = False # a split changed the topology; rebuild after the step
            self._split_req = 0        # request counter for TopologySplitEngine
            self.rest0 = None          # PRISTINE rest shape for the reference disc. NOT
                                       # rest_position: plasticity creeps that toward the
                                       # deformed shape, which was warping the "undeformed"
                                       # map in the browser. Grows with duplicates only.
            self.crack = None          # vertex path of the tear; last entry is the live tip
            self.closed = False        # True once the tear has met its own path
            self.block = None          # why the last advance attempt failed
            self.crack_hist = []       # finished fronts, kept so the drawing shows every cut
            self.nuc_tick = 0          # opportunities since the last nucleation scan
            self._drive_ref = None     # decaying peak tip drive, for arrest-on-unloading
            self._just_split = False   # last opportunity ended in a split (see ARREST_REBASE)
            self._blocked_runs = 0     # consecutive turn-blocked opportunities
            self.crack_dir = None      # current heading (unit xy), for the Eq.2 turn limit
            self.vtris = None          # vertex -> [triangle ids], rebuilt on topology change
            self.tear_log_t = -1.0
            # instance copies so the hotkeys can tune them live
            self.plastic_rate = PLASTIC_RATE
            self.break_force = BREAK_FORCE
            self.break_lift = BREAK_FORCE / ADHESION_STIFF
            self.last_log_t = -1.0
            self.fully_peeled = False
            self.frozen = False
            self.step = 0
            self.last_ks = None
            self.clamped = 0
            self.prev_pos = None       # positions as rendered last step, for the disp clamp
            self.disp_clamped = 0      # nodes caught by the per-step displacement clamp
            self.last_jump = 0.0       # pre-guard peak single-frame jump (diagnostics)
            self.diag = None           # diagnostics CSV handle (opened lazily)
            self.tri_idx = None        # triangle index array for the anti-collapse clamp
            self.tri_rest_area = None  # each triangle's ORIGINAL rest area (stable ref)
            self.collapsed = 0         # count of near-flat triangles repaired
            self.last_good_rest = None # rest shape paired with last_good, for full rewind
            self.rewinds = 0           # count of severe-blow-up rewinds
            self.contained = 0         # blow-ups contained in place (no snapshot to use)
            self.rest_objs = None      # self-calibrating idle object count (grab detection)
            self._probe_prev = None    # previous object-name list, for the CAM_PROBE diag
            self.cam_home = None       # (position, lookAt) captured at t0, for R = re-centre
            self.cam_lock = False      # manual orbit lock toggled by V
            self.cam_active = not LOCK_CAMERA  # last-written camera.activated (write on change)

        def _push_adhesion(self):
            # Points = still-glued nodes at full stiffness, then just-broken nodes with
            # their fading stiffness (per-point stiffness list, order-matched). An EMPTY
            # points list makes RestShapeSpringsForceField apply to ALL nodes (snapping
            # the whole membrane back), so when nothing is left, zero the stiffness
            # instead of emptying the points.
            if self.adhesion is None:
                return                      # paper mode: there is no bond to maintain
            fading = sorted(self.peel_fade)
            pts = sorted(self.adhered) + fading
            if pts:
                self.adhesion.points.value = pts
                self.adhesion.stiffness.value = (
                    [ADHESION_STIFF] * len(self.adhered)
                    + [self.peel_fade[p] for p in fading])
            else:
                self.adhesion.stiffness.value = [0.0]

        def _freeze(self, why):
            self.mo.rest_position.value = self.mo.position.value
            self.springs.reinit()
            self.bending.reinit()
            if self.adhered is not None:
                self.adhered.clear()
            self.peel_fade.clear()
            if self.adhesion is not None:
                self.adhesion.points.value = []
                self.adhesion.stiffness.value = [0.0]
            if RELEASE_AFTER_FREEZE and self.pull is not None:
                self.pull.indices.value = []
            self.frozen = True
            print(f"[Freeze] {why}: shape frozen; it will now stay deformed")

        def _set_bend(self, new_ks):
            # TriangularBendingSprings BAKES ks into per-edge data (ei.ks = getKs()), so
            # changing the Data alone does nothing until reinit() re-reads it.
            self.bending.stiffness.value = float(new_ks)
            self.bending.reinit()
            self.last_ks = float(new_ks)
            print(f"[Tune] BEND_STIFFNESS = {float(new_ks):.1f}   "
                  f"(K = stiffer / J = softer; too low -> crumples, too high -> stands rigid)")

        def _check_peel_reachable(self, P):
            """Warn if the peel criterion is geometrically impossible to satisfy.

            The adhesion releases a spot once it has lifted BREAK_FORCE/ADHESION_STIFF, but the
            strain clamp independently forbids any edge from passing MAX_STRETCH x its rest
            length -- so a lone glued node cannot rise past sqrt((MAX_STRETCH*e)^2 - e^2). When
            the required lift exceeds that, NOTHING in the interior can ever debond, at any
            pull force, and the capsule silently behaves as if welded to the lens. That is
            exactly what shipped (0.500 required against 0.375 reachable) and it is invisible
            from the outside: the pull just does nothing. Two independently sensible constants
            in different parts of the file, jointly impossible -- so check it out loud."""
            # Read the topology directly rather than self.tris: this runs the first time the
            # adhesion is set up, which is BEFORE _build_vtris has populated that cache, so
            # trusting it made the check silently do nothing -- the exact failure mode it
            # exists to catch.
            if MAX_STRETCH <= 0.0:
                return
            T = np.array(self.topo.triangles.value)
            if not len(T):
                return
            E = np.unique(np.sort(np.concatenate(
                [T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1), axis=0)
            e = float(np.median(np.linalg.norm(P[E[:, 1]] - P[E[:, 0]], axis=1)))
            reach = float(np.sqrt(max((MAX_STRETCH * e) ** 2 - e * e, 0.0)))
            need = BREAK_FORCE / max(ADHESION_STIFF, 1e-9)
            if need >= reach:
                print(f"[Adhesion] WARNING: break_lift={need:.3f} but the strain clamp stops a "
                      f"lone node at {reach:.3f} (edge {e:.3f} x MAX_STRETCH {MAX_STRETCH}). "
                      f"The interior can NEVER peel. Lower CAP_BREAK below "
                      f"{reach * ADHESION_STIFF:.0f} or raise MAX_STRETCH.")
            else:
                print(f"[Adhesion] break_lift={need:.3f} vs reachable {reach:.3f} -- OK "
                      f"(peel can nucleate in the interior)")

        def _tool_xy(self):
            """Deformed xy of the node the instrument is currently pulling, or None if the
            user is not grabbing. Read straight off the mechanical object's force field --
            the grab spring is by far the largest external force on any node -- rather than
            from _PULL_STATE, which is only refreshed later in the same handler (and in REST
            coordinates, which do not match the deformed positions the peel test uses)."""
            try:
                F = np.asarray(self.mo.force.value, dtype=float)
                if F.ndim != 2 or len(F) < 8:
                    return None
                mag = np.linalg.norm(F, axis=1)
                k = int(np.argmax(mag))
                # Do NOT gate this on _is_grabbing(): that detects SOFA's mouse interactor by
                # name, so a scripted pull or a headless probe -- which drive the same physics
                # through their own spring -- would report "no instrument" and silently freeze
                # peeling altogether. Detect the instrument by what it DOES instead: one node
                # carrying a force far above the bulk. TOOL_FORCE_RATIO against the 99th
                # percentile, so ordinary elastic forces never look like a grab.
                bulk = float(np.percentile(mag, 99))
                if mag[k] < max(TOOL_FORCE_RATIO * bulk, 1e-6):
                    return None
                P = np.asarray(self.mo.position.value, dtype=float)
                if k >= len(P):
                    return None
                return np.array([float(P[k][0]), float(P[k][1])])
            except Exception:  # noqa: BLE001
                return None

        def _build_peel_adjacency(self):
            """Node neighbours + mesh-boundary nodes, for front-only peeling.

            A boundary edge belongs to exactly ONE triangle; its endpoints are the free
            edges of the sheet (this cap's outer rim and its radial slit) and are the
            only places a peel may START. Everything else must be reached by the front.
            """
            tris = np.array(self.topo.triangles.value)
            n = len(self.mo.position.value)
            nbr = [set() for _ in range(n)]
            from collections import Counter
            ecount = Counter()
            for a, b, c in tris.tolist():
                nbr[a].update((b, c)); nbr[b].update((a, c)); nbr[c].update((a, b))
                for u, v in ((a, b), (b, c), (c, a)):
                    ecount[(u, v) if u < v else (v, u)] += 1
            self.nbr = [np.fromiter(x, dtype=int) for x in nbr]
            bset = set()
            for (u, v), k in ecount.items():
                if k == 1:
                    bset.add(u); bset.add(v)
            self.boundary = bset

        def _build_edges(self):
            tris = np.array(self.topo.triangles.value)
            E = set()
            for a, b, c in tris:
                for u, v in ((a, b), (b, c), (c, a)):
                    E.add((min(u, v), max(u, v)))
            self.edges = np.array(sorted(E), dtype=int) if E else np.zeros((0, 2), int)
            R = np.array(self.mo.rest_position.value)
            if len(self.edges):
                self.edge_rest = np.linalg.norm(R[self.edges[:, 1]] - R[self.edges[:, 0]], axis=1)
            else:
                self.edge_rest = np.zeros(0)

        def _build_tri_areas(self):
            # Triangle list + each triangle's ORIGINAL rest area, cached once. The rest area
            # is the stable reference the anti-collapse clamp measures against; it is taken
            # from rest_position at first call (before plasticity has had time to drift it),
            # i.e. the undeformed cap.
            tris = np.array(self.topo.triangles.value)
            self.tri_idx = tris if len(tris) else np.zeros((0, 3), int)
            R = np.array(self.mo.rest_position.value)
            if len(self.tri_idx):
                e1 = R[self.tri_idx[:, 1]] - R[self.tri_idx[:, 0]]
                e2 = R[self.tri_idx[:, 2]] - R[self.tri_idx[:, 0]]
                self.tri_rest_area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
            else:
                self.tri_rest_area = np.zeros(0)

        def _has_degenerate(self, P):
            # True if any triangle is below the min-area threshold in configuration P.
            if self.tri_idx is None or not len(self.tri_idx):
                return False
            t = self.tri_idx
            a = 0.5 * np.linalg.norm(
                np.cross(P[t[:, 1]] - P[t[:, 0]], P[t[:, 2]] - P[t[:, 0]]), axis=1)
            return bool((a < MIN_AREA_FRAC * self.tri_rest_area).any())

        def _is_healthy(self, P):
            # Strict "safe to snapshot as rewind target": finite, coords bounded AND
            # every triangle area within [MIN_AREA_FRAC, DEGEN_HI] x rest. Must reject
            # both failure directions -- caching an inflating-but-finite frame would
            # make every rewind land back inside the explosion.
            if not np.isfinite(P).all():
                return False
            if MAX_COORD > 0.0 and P.size and np.abs(P).max() > MAX_COORD:
                return False
            if self.tri_idx is not None and len(self.tri_idx):
                t = self.tri_idx
                a = 0.5 * np.linalg.norm(
                    np.cross(P[t[:, 1]] - P[t[:, 0]], P[t[:, 2]] - P[t[:, 0]]), axis=1)
                ratio = a / np.maximum(self.tri_rest_area, 1e-12)
                if (ratio < MIN_AREA_FRAC).any() or (ratio > DEGEN_HI).any():
                    return False
            return True

        def _repair_flat_triangle(self, P, tri, rest_area):
            # Push the apex (the vertex opposite the LONGEST edge) perpendicular to that edge
            # until the triangle area reaches MIN_AREA_FRAC x rest_area. Moves ONE node, so it
            # barely perturbs the sheet while lifting the triangle off collinearity.
            pts = [int(tri[0]), int(tri[1]), int(tri[2])]
            v = P[pts]
            pairs = [(1, 2), (2, 0), (0, 1)]      # edge opposite vertex 0, 1, 2
            Ls = [np.linalg.norm(v[i] - v[j]) for i, j in pairs]
            apex = int(np.argmax(Ls))             # the vertex NOT on the longest edge
            b0, b1 = pairs[apex]                   # the two base-edge vertices
            A, B, C = v[apex], v[b0], v[b1]
            u = C - B
            ulen = np.linalg.norm(u)
            if ulen < 1e-12:
                return                            # base edge collapsed too: unrepairable here
            u = u / ulen
            w = (A - B) - np.dot(A - B, u) * u     # apex offset perpendicular to the base
            wlen = np.linalg.norm(w)
            if wlen < 1e-9:
                # fully collinear -> no in-plane perpendicular survives; pick any direction
                # orthogonal to the base so the apex lifts off the line.
                ref = np.array([0.0, 0.0, 1.0])
                if abs(np.dot(ref, u)) > 0.9:
                    ref = np.array([1.0, 0.0, 0.0])
                w = ref - np.dot(ref, u) * u
                w = w / np.linalg.norm(w)
                cur_alt = 0.0
            else:
                cur_alt = wlen
                w = w / wlen
            target_alt = 2.0 * MIN_AREA_FRAC * rest_area / ulen
            if cur_alt < target_alt:
                P[pts[apex]] = A + (target_alt - cur_alt) * w

        def _strain_panic_check(self):
            """Rewind or contain ONLY if an edge is still wildly over-stretched AFTER the
            clamps have had their turn. Anything the clamp can fix is not a blow-up."""
            if STRAIN_PANIC <= 0.0 or MAX_STRETCH <= 0.0:
                return
            P = np.array(self.mo.position.value)
            if not np.isfinite(P).all():
                return                      # the NaN path at stage (0) owns this
            if self.edges is None:
                self._build_edges()
            if not len(self.edges):
                return
            L = np.linalg.norm(P[self.edges[:, 1]] - P[self.edges[:, 0]], axis=1)
            worst = float((L / np.maximum(self.edge_rest, 1e-9)).max())
            if worst <= MAX_STRETCH * STRAIN_PANIC:
                return
            if self.step % 15 == 0:
                print(f"[Runaway] edge still {worst:.1f}x rest after clamping "
                      f"(limit {MAX_STRETCH:g}, panic at {MAX_STRETCH * STRAIN_PANIC:.1f}x)")
            if self.last_good is not None and len(self.last_good) == len(P):
                self._rewind()
            else:
                self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(P)
                self.contained += 1

        def _rewind(self):
            # Restore the last healthy frame: positions, rest shape, zero velocity.
            # Restoring the REST too un-bakes a plasticity-frozen blow-up.
            if self.last_good is None:
                return
            self.mo.position.value = self.last_good
            if self.last_good_rest is not None:
                self.mo.rest_position.value = self.last_good_rest
                self.bending.reinit()
            self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.last_good)
            self.prev_pos = np.array(self.last_good)   # disp clamp baseline follows the rewind
            self.rewinds += 1

        def _count_objs(self):
            """Total objects in the graph. The mouse attach adds one while you grab."""
            n = 0
            stack = [self.root]
            while stack:
                nd = stack.pop()
                try:
                    n += len(nd.objects)
                    stack.extend(list(nd.children))
                except Exception:  # noqa: BLE001
                    pass
            return n

        def _obj_paths(self):
            # Flat list of "ClassName:name" for every object in the graph -- for the CAM_PROBE
            # diagnostic, so we can see exactly which object a Shift+drag adds.
            out = []
            stack = [self.root]
            while stack:
                nd = stack.pop()
                try:
                    for o in nd.objects:
                        try:
                            out.append(f"{o.getClassName()}:{o.getName()}")
                        except Exception:  # noqa: BLE001
                            out.append(str(o))
                    stack.extend(list(nd.children))
                except Exception:  # noqa: BLE001
                    pass
            return out

        def _is_grabbing(self):
            """True while SOFA's mouse interactor is actually holding the membrane.

            Detected BY NAME. The previous version compared the graph's object COUNT against a
            self-calibrating resting minimum, which cannot work: SofaImGui keeps adding objects
            of its own, so the baseline goes stale and the camera ends up locked for good --
            which is why FREEZE_CAMERA_WHILE_PULLING had to be left off, and why left-drag
            orbits the view at the same time as it pulls. When you grab, SOFA's attach
            performer adds a spring between a mouse particle and the picked node, and those
            objects carry "mouse" in their class or name. Verified that nothing in this scene
            does so at rest (0 of 55 objects match), and AttachBodyButtonSetting -- which is
            only the SETTING for how stiff that spring is -- is excluded explicitly."""
            for tag in self._obj_paths():
                low = tag.lower()
                if "mouse" in low and "buttonsetting" not in low:
                    return True
            return False

        def _pan_camera(self, dr, du):
            # Translate BOTH position and lookAt by dr*right + du*up (screen-plane pan), so
            # the view slides without rotating. Right/up derived from the current view dir.
            if self.camera is None:
                return
            try:
                pos = np.array(self.camera.position.value, dtype=float)
                look = np.array(self.camera.lookAt.value, dtype=float)
            except Exception:  # noqa: BLE001
                return
            fwd = look - pos
            fn = np.linalg.norm(fwd)
            if fn < 1e-9:
                return
            fwd = fwd / fn
            world_up = np.array([0.0, 0.0, 1.0])
            right = np.cross(fwd, world_up)
            if np.linalg.norm(right) < 1e-6:            # looking straight up/down: fall back
                right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
            right = right / max(np.linalg.norm(right), 1e-9)
            up = np.cross(right, fwd)
            delta = dr * right + du * up
            self.camera.position.value = (pos + delta).tolist()
            self.camera.lookAt.value = (look + delta).tolist()

        def _reset_camera(self):
            if self.camera is None or self.cam_home is None:
                return
            self.camera.position.value = list(self.cam_home[0])
            self.camera.lookAt.value = list(self.cam_home[1])
            print("[Camera] re-centred to the start view")

        def _report(self):
            print(f"[Knobs] bend={float(self.bending.stiffness.value):7.1f} | "
                  f"plastic={self.plastic_rate:4.2f} | breakForce={self.break_force:5.1f} | "
                  f"mousePull={float(self.mouse.stiffness.value):6.0f} | "
                  f"damping={float(self.damper.dampingCoefficient.value):4.1f} | "
                  f"sigma1max={self.sigma1_max:8.1f}")

        def onKeypressedEvent(self, event):
            k = event["key"]
            if k in ("F", "f"):
                if not self.frozen:
                    self._freeze("key F pressed")
            # --- live knobs (the SofaImGui Data panel segfaults, so tune from here) ---
            elif k in ("K", "k"):      # fold stiffness
                self._set_bend(float(self.bending.stiffness.value) * 1.5)
            elif k in ("J", "j"):
                self._set_bend(float(self.bending.stiffness.value) / 1.5)
            elif k in ("O", "o"):      # plasticity: higher = keeps its shape, less recoil
                self.plastic_rate = min(0.9, self.plastic_rate * 1.4); self._report()
            elif k in ("I", "i"):
                self.plastic_rate = max(0.0, self.plastic_rate / 1.4); self._report()
            elif k in ("N", "n"):      # adhesion threshold: higher = stickier
                self.break_force *= 1.4
                self.break_lift = self.break_force / ADHESION_STIFF; self._report()
            elif k in ("B", "b"):
                self.break_force /= 1.4
                self.break_lift = self.break_force / ADHESION_STIFF; self._report()
            elif k in ("M", "m"):      # mouse pull strength (too high -> explosions)
                self.mouse.stiffness.value = float(self.mouse.stiffness.value) * 1.4
                self._report()
            elif k in ("H", "h"):
                self.mouse.stiffness.value = float(self.mouse.stiffness.value) / 1.4
                self._report()
            elif k in ("P", "p"):      # print current values
                self._report()
            # --- camera controls (best effort; may need the 3D viewport to have focus) ---
            # Arrow keys OR W/A/S/D pan the view; R re-centres; V toggles the orbit lock.
            # SofaGLFW delivers arrow keys as the control chars 18/20/19/21 (up/down/left/
            # right); accept both those and W/A/S/D so at least one route works.
            elif k in ("W", "w", "\x12"):              # up  (\x12 = 18)
                self._pan_camera(0.0, CAM_PAN_STEP)
            elif k in ("S", "s", "\x14"):              # down (\x14 = 20)
                self._pan_camera(0.0, -CAM_PAN_STEP)
            elif k in ("A", "a", "\x13"):              # left (\x13 = 19)
                self._pan_camera(-CAM_PAN_STEP, 0.0)
            elif k in ("D", "d", "\x15"):              # right (\x15 = 21)
                self._pan_camera(CAM_PAN_STEP, 0.0)
            elif k in ("R", "r"):                       # re-centre the view
                self._reset_camera()
            elif k in ("V", "v"):                       # toggle orbit lock manually
                self.cam_lock = not self.cam_lock
                print(f"[Camera] orbit {'LOCKED' if self.cam_lock else 'free'}")

        def _stress_material(self):
            # Constitutive constants (E, nu) the stress observer should use so its
            # sigma1 matches the force actually acting on the sheet:
            #  - FEM mode: read the FEM's live youngModulus/poissonRatio. The observer
            #    and the FEM build sigma from the SAME deformation gradient F and the
            #    SAME plane-stress law sigma = C(E,nu):eps, so with matched (E, nu) the
            #    reported value IS the FEM's stress (exactly at small strain; the
            #    observer's Green strain and the FEM's co-rotational linear strain
            #    diverge slightly at large strain). This also tracks the cloth->paper
            #    ramp, since youngModulus changes at SWITCH_T.
            #  - mass-spring mode: no continuum E exists, so keep STRESS_E/STRESS_NU as a
            #    fixed geometric-strain scale (magnitudes are a proxy; the spatial
            #    pattern of where sigma1 concentrates is identical either way).
            if self.fem is not None:
                try:
                    E = float(np.ravel(self.fem.youngModulus.value)[0])
                    nu = float(np.ravel(self.fem.poissonRatio.value)[0])
                    return E, nu
                except Exception:  # noqa: BLE001
                    pass
            return STRESS_E, STRESS_NU

        def _publish_stress(self, s1, s2, sdir, aratio, t):
            _stress_record(_stress_build_frame(_STRESS_TOTAL, self.step, t, s1, s2, sdir, aratio))

        # ---------------- real tearing (CAP_TEAR) ---------------------------------------
        def _build_vtris(self):
            """vertex -> triangles map, plus the neighbour and boundary maps, for the current
            topology.

            VECTORISED, because this runs after EVERY vertex split and a split is frequent
            while a tear is running. The original triple Python loop over all ~4166 triangles
            (list appends, set updates and a Counter of sorted edge tuples) profiled at 8.5
            ms/step during tearing -- 17% of the whole step and the single largest tearing
            cost, more than the stress solve and the split itself put together. Same outputs,
            built with bincount/unique instead, and handed out through _Adjacency so no
            per-vertex Python object is created at all: verified elementwise against the old
            loop, on a fresh mesh and again after real splits."""
            T = np.array(self.topo.triangles.value)
            n = len(self.mo.position.value)
            self.tris = T
            if not len(T):
                z = np.zeros(n + 1, dtype=int)
                self.vtris = _Adjacency(np.empty(0, dtype=int), z)
                self.nbr = _Adjacency(np.empty(0, dtype=int), z)
                self.boundary = set()
                return
            # vertex -> triangle list: sort the (vertex, triangle) incidence pairs once and
            # slice, rather than appending per triangle.
            vv = T.reshape(-1)
            vt = np.repeat(np.arange(len(T)), 3)
            order = np.argsort(vv, kind="stable")
            vv_s, vt_s = vv[order], vt[order]
            cut = np.concatenate(([0], np.cumsum(np.bincount(vv_s, minlength=n))))
            self.vtris = _Adjacency(vt_s, cut)
            # undirected edges, with multiplicity: an edge used by ONE triangle is a boundary
            E = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
            # Encode each undirected edge as ONE integer rather than calling np.unique with
            # axis=0. That path lexsorts a structured view of the pairs and measured 6.10 ms
            # of this function's 7.48 ms; the 1-D equivalent gives the same answer in 0.72 ms.
            key = E[:, 0].astype(np.int64) * n + E[:, 1]
            ukey, cnt = np.unique(key, return_counts=True)
            eu, ev = ukey // n, ukey % n
            # boundary must be rebuilt together with nbr: the peel logic guards only on
            # self.nbr, so leaving boundary stale/None here made it fail with a TypeError
            # on every step after the first split.
            lone = cnt == 1
            self.boundary = set(np.concatenate([eu[lone], ev[lone]]).tolist())
            # neighbours: every unique edge, both ways
            src = np.concatenate([eu, ev])
            dst = np.concatenate([ev, eu])
            o = np.argsort(src, kind="stable")
            src, dst = src[o], dst[o]
            cut2 = np.concatenate(([0], np.cumsum(np.bincount(src, minlength=n))))
            self.nbr = _Adjacency(dst, cut2)

        def _rest_now(self):
            """rest_position as an array, cached per step: it is read several times per
            advance and the SOFA Data -> numpy conversion is not free."""
            if (self._rest_cache is None or self._rest_cache[0] != self.step
                    or len(self._rest_cache[1]) != len(self.mo.position.value)):
                self._rest_cache = (self.step, np.array(self.mo.rest_position.value))
            return self._rest_cache[1]

        def _field_now(self, P):
            """Whole-mesh stress field for this step, solved once and reused. _tip_stress
            needs the FULL field (its kernel has no cutoff), and the heatmap wants the same
            arrays, so without this the same solve would repeat over identical positions. The
            key includes both array lengths, so a vertex split invalidates it automatically."""
            key = (self.step, len(P), len(self.tris))
            if self._field_cache is None or self._field_cache[0] != key:
                E_obs, nu_obs = self._stress_material()
                s1, s2, sdir, ar = principal_stress(P, self._rest_now(), self.tris,
                                                    E=E_obs, nu=nu_obs)
                cen = P[self.tris][:, :, :2].mean(axis=1)
                self._field_cache = (key, s1, s2, sdir, ar, cen)
            return self._field_cache[1:]

        def _tip_stress(self, P, x, y, radius=None):
            """State driving the crack: DIRECTION from the tip's own elements, MAGNITUDE from a
            wider distance-weighted kernel. Returns (S1, S2, angle_deg, local_s1).

            The split is measured, not stylistic. During a real pull, comparing the angle each
            candidate source makes with the direction from the tip to the hand:

                tip's own local sigma1 :  0.7 - 14.5 deg   <- tracks the hand closely
                wide top-K average     : 24.1 - 84.6 deg   <- essentially uncorrelated

            The wide average is dominated by the elements under the hand, so its angle is the
            stress direction THERE, which carries no geometric meaning at the tip. Using it
            steered the crack independently of where the user pulled: grabbing at azimuth 0
            and at 180 -- opposite sides of the capsule -- both left the tip near -100 deg,
            and identical pulls put it at r=6.42 one run and r=1.45 the next.

            The local MAGNITUDE, though, is useless alone: it reads 0.3-20 against a threshold
            of 20, because a coarse linear mesh has no stress singularity at the tip (docs 5.3)
            and most of the load is still out under the hand. So take the tensor's orientation
            AND its biaxiality from the tip, then scale it to the drive the wider kernel
            reports. Averaging tensor COMPONENTS throughout, never principal values: two states
            90 deg apart average to isotropic rather than to the larger.

            local_s1 is returned so the caller can refuse to tear when the tip is genuinely
            unloaded. With no load the local direction IS numerical noise, and amplifying noise
            by the remote drive is exactly what let the crack random-walk out to the rim before
            the user had pulled at all (recorded: tip r 2.01 -> 6.58 within 0.6 s, c up to
            193)."""
            if self.tris is None or not len(self.tris):
                return None
            s1, s2, sdir, ar, cen = self._field_now(P)
            keep = (ar >= DEGEN_LO) & (ar <= DEGEN_HI)
            if not keep.any():
                return None
            s1, s2, sdir = s1[keep], s2[keep], sdir[keep]
            d2 = (cen[keep, 0] - x) ** 2 + (cen[keep, 1] - y) ** 2
            th = np.arctan2(sdir[:, 1], sdir[:, 0])
            cs, sn = np.cos(th), np.sin(th)

            def tensor_avg(w):
                ws = float(w.sum())
                if ws <= 0.0:
                    return None
                sxx = float((w * (s1 * cs * cs + s2 * sn * sn)).sum() / ws)
                syy = float((w * (s1 * sn * sn + s2 * cs * cs)).sum() / ws)
                sxy = float((w * ((s1 - s2) * sn * cs)).sum() / ws)
                mid = 0.5 * (sxx + syy)
                dev = float(np.hypot((sxx - syy) * 0.5, sxy))
                return mid + dev, mid - dev, np.degrees(0.5 * np.arctan2(2 * sxy, sxx - syy))

            rad = TEAR_TIP_RADIUS if radius is None else radius
            near = tensor_avg((d2 <= rad * rad).astype(float))
            if near is None:
                return None
            l1, l2, th1 = near

            # magnitude only: the most heavily loaded material within reach, distance-weighted.
            # No cutoff -- a hard one at TEAR_REACH=2.5 on a disc of radius 6.89 meant a pull
            # further than a third of the way across counted for nothing, which is what made
            # the capsule feel untearable (drive fell 2407 -> 25 with distance while the field
            # itself moved only 325 -> 149). Top-K rather than the raw max so a single
            # near-degenerate triangle, which can read ~100x the bulk, cannot drive the tear.
            w = 1.0 / (1.0 + d2 / max(TEAR_REACH * TEAR_REACH, 1e-9))
            v = s1 * w
            k = int(min(max(TEAR_DRIVE_TOPK, 1), v.size))
            drive = float(np.mean(np.partition(v, -k)[-k:]))

            # LEFM crack-length amplification (see TEAR_LEFM). A coarse linear mesh has no
            # stress singularity at the tip -- measured on a real session, the tip's own sigma1
            # is about 3% of the field's p98 (ratios 0.006-0.106 over most of the pull), so the
            # tip under-reads by roughly 30x and the criterion could only ever fire when the
            # hand was almost on top of it (median instrument-to-tip distance was 4.30 on a
            # disc of radius 6.89). A flat gain cannot fix that, because what is missing is not
            # a constant: K = sigma*sqrt(pi*a) grows with crack length, which is what makes a
            # tear accelerate once it has started instead of needing the same effort forever.
            if TEAR_LEFM:
                drive *= min(self._crack_extent_factor(), TEAR_LEFM_CAP)
            scale = drive / l1 if l1 > 1e-9 else 0.0
            return l1 * scale, l2 * scale, th1, l1

        def _crack_extent_factor(self):
            """sqrt(a / a0): how much easier this crack is to extend than the opening nick.

            'a' is the crack's SPATIAL EXTENT -- the diagonal of the box containing its path.
            Not the vertex count, which rewards a jagged path that doubles back and cuts little
            new ground; and not tip-to-seed distance, which was the first attempt and collapses
            to nothing for exactly the crack shape a capsulorhexis wants: a curve that comes
            back around, whose endpoints are close together while the crack itself is large.
            Measured, that version returned 1.00 for a 41-vertex tear, i.e. no amplification at
            all. a0 is the seeded nick, so the factor starts at 1."""
            if not self.crack or len(self.crack) < 2:
                return 1.0
            P = np.asarray(self.mo.position.value)
            idx = [v for v in self.crack if v < len(P)]
            if len(idx) < 2:
                return 1.0
            xy = P[idx][:, :2]
            span = xy.max(axis=0) - xy.min(axis=0)
            ext = float(np.hypot(span[0], span[1]))
            a0 = max(2.0 * TEAR_START_R, 1e-6)
            return float(np.sqrt(max(ext, a0) / a0))

        def _try_nucleate(self, P, blocked=False):
            """Give up on this tip and start a tear where the membrane is most overloaded.

            Called both when the tip is idle AND when it is loaded but cannot move. The second
            case used to be missing, and it is the common one: with the crack boxed in, the tip
            reports a huge c (274 was observed on screen) yet every neighbour needs a ~150 deg
            turn, so the advance is refused every single opportunity. Because the scan lived
            inside the 'tip not loaded' branch it was never even reached, and no new tear could
            ever start anywhere -- exactly the "after the first crack I cannot tear anywhere
            else" report. Blocked is at least as good a reason to look elsewhere as idle is."""
            self.nuc_tick += 1
            need = TEAR_NUC_BLOCKED_EVERY if blocked else TEAR_NUCLEATE_EVERY
            if not TEAR_NUCLEATE or self.nuc_tick < need:
                return False
            self.nuc_tick = 0
            hit = self._scan_nucleation(P)
            if hit is None:
                return False
            k, cval, d = hit
            tri = self.tris[k]
            v = int(tri[int(np.argmax(np.hypot(P[tri][:, 0], P[tri][:, 1])))])
            if self.crack and len(self.crack) > 1:
                self.crack_hist.append(list(self.crack))
            self.crack = [v]
            self.crack_dir = np.asarray(d, dtype=float)
            self.closed = False
            self._drive_ref = None
            self._tear_reinit()
            print(f"[Tear] NEW tear nucleated at element {k} (c={cval:.2f}), "
                  f"where the membrane is most overloaded")
            return True

        def _scan_nucleation(self, P):
            """Best fracture site over the WHOLE membrane, per Dequidt 2013 section 4.3: the
            criterion is evaluated at the tip of an existing fracture *or at the centre of each
            potentially fracturing element*. Returns (element, c, direction) or None.

            Cheap because of the paper's own bound: sigma_u <= sigma1 and sigma_bar_u >=
            sigma_bar_T, so c <= sigma1/sigma_bar_T and only elements already past the
            threshold can possibly reach 1. Everything else is rejected without a search."""
            if self.tris is None or not len(self.tris):
                return None
            s1, s2, sdir, ar, cen = self._field_now(P)
            ok = ((ar >= DEGEN_LO) & (ar <= DEGEN_HI) & (s1 >= TEAR_THRESH))
            cand = np.flatnonzero(ok)
            if not cand.size:
                return None
            # strongest first, and only a bounded number of them per scan
            cand = cand[np.argsort(-s1[cand])[:TEAR_NUC_MAX]]
            R0 = self._rest_now()
            best = None
            for k in cand:
                th1 = float(np.degrees(np.arctan2(sdir[k][1], sdir[k][0])))
                tri = self.tris[k]
                if tri.max() >= len(R0):
                    continue
                rc = R0[tri][:, :2].mean(axis=0)          # fibre from the REST shape
                fib = float(np.degrees(np.arctan2(rc[1], rc[0])) + 90.0)
                # heading=None: nothing to continue from, so Eq.2's H term does not apply
                c, d, dang, su, sbu = self._argmax_c(float(s1[k]), float(s2[k]), th1, fib, None)
                if c >= 1.0 and (best is None or c > best[1]):
                    best = (int(k), float(c), d)
            return best

        def _argmax_c(self, S1, S2, th1_deg, fib_deg, heading):
            """INRIA criterion (Eq.1-4). Returns (c, unit direction) for the crack direction
            that maximises c, restricted to turns within TEAR_TURN_MAX of the heading
            (Eq.2's H term -- this is what stops the tear doubling back on itself).

            Also returns the Eq.3/Eq.4 terms AT the winning direction (angle, sigma_u,
            sigma_bar_u) so the viewer can display the criterion itself and not just its
            verdict: c = sigma_u / sigma_bar_u, and seeing which of the two moved explains
            why the tear did or did not go."""
            sT, sL = TEAR_THRESH, TEAR_THRESH * TEAR_FIB_RATIO

            def c_of(a):
                thu = a + 90.0
                cp = np.cos(np.radians(thu - th1_deg))
                su = S1 * cp * cp + S2 * (1.0 - cp * cp)
                if su <= 0.0:
                    return -1.0
                df = abs(thu - fib_deg) % 180.0
                if df > 90.0:
                    df = 180.0 - df
                return su / (sT + (sL - sT) * (1.0 - df / 90.0) ** TEAR_FIB_ALPHA)

            def vec(a):
                v = np.array([np.cos(np.radians(a)), np.sin(np.radians(a))])
                return -v if (heading is not None and v @ heading < 0) else v

            def allowed(a):
                if heading is None:
                    return True
                return np.degrees(np.arccos(np.clip(vec(a) @ heading, -1, 1))) <= TEAR_TURN_MAX

            def terms(a):
                thu = a + 90.0
                cp = np.cos(np.radians(thu - th1_deg))
                su = S1 * cp * cp + S2 * (1.0 - cp * cp)
                df = abs(thu - fib_deg) % 180.0
                if df > 90.0:
                    df = 180.0 - df
                return su, sT + (sL - sT) * (1.0 - df / 90.0) ** TEAR_FIB_ALPHA

            best, ba = -1.0, 0.0
            for a in np.arange(0.0, 180.0, 3.0):
                if allowed(a):
                    cc = c_of(a)
                    if cc > best:
                        best, ba = cc, a
            half = 3.0                       # bisection refine (c(d) has a kink at the fiber)
            for _ in range(6):
                half *= 0.5
                for a in (ba - half, ba + half):
                    if allowed(a):
                        cc = c_of(a)
                        if cc > best:
                            best, ba = cc, a
            su_b, sbu_b = terms(ba)
            return best, vec(ba), float(ba), float(su_b), float(sbu_b)

        def _split_vertex(self, v, P, R):
            """Open the mesh at vertex v: duplicate it and move the triangles on ONE side of
            the crack line onto the duplicate. The two copies start coincident, so the tear
            is invisible until the springs pull the lips apart -- which is exactly how a real
            cut behaves. Returns the new vertex id (or None if the fan cannot be split)."""
            if self.crack_dir is None:
                return None
            tl = self.vtris[v]
            if len(tl) < 2:
                return None
            d = self.crack_dir
            pv = P[v][:2]
            side = []
            for ti in tl:
                cen = P[self.tris[ti]][:, :2].mean(axis=0)
                side.append(d[0] * (cen[1] - pv[1]) - d[1] * (cen[0] - pv[0]))
            neg = [ti for ti, s in zip(tl, side) if s < 0]
            if not neg or len(neg) == len(tl):
                return None                  # crack line misses the fan: nothing to open
            nv = len(P)
            # remember the pairing: plasticity drifts the rest positions, so after a while
            # a duplicate can no longer be matched back to its lip by geometry alone
            self.dup_of[nv] = int(v)
            # the reference disc keeps the PRISTINE shape: the duplicate inherits its lip's
            # original position, so the map stays a clean disc no matter how far the
            # simulation deforms or how much plasticity has crept
            if self.rest0 is not None and v < len(self.rest0):
                self.rest0 = np.vstack([self.rest0, self.rest0[v]])
            used_api = False
            if self.splitter is not None:
                # OFFICIAL TOPOLOGY API (Capsulorhexis plugin, TopologySplitEngine). It calls
                # addPoints with the original as ancestor -- SOFA then interpolates the new
                # DOF, so position, rest position and velocity are all created correctly and
                # none of the manual array surgery below is needed -- then removes and re-adds
                # the moved triangles, which is what keeps the container's EDGE list right.
                # Writing topo.triangles directly (the fallback) cannot do that, and the stale
                # edges become springs stapling the cut shut (docs 4.24).
                try:
                    self.splitter.splitPoint.value = int(v)
                    self.splitter.movedTriangles.value = [int(t) for t in neg]
                    self._split_req += 1
                    self.splitter.request.value = self._split_req
                    # READING newPoint is what runs the split: the component registers an
                    # update callback on 'request', so the work happens when its output is
                    # asked for. That makes it synchronous, which this caller needs -- it
                    # appends the new vertex to the crack and rebuilds its caches right here.
                    got = int(self.splitter.newPoint.value)
                    if got < 0:
                        used_api = False          # component refused; fall back
                    else:
                        nv = got
                        used_api = True
                except Exception:  # noqa: BLE001
                    used_api = False
            if not used_api:
                self.mo.position.value = np.vstack([P, P[v]]).tolist()
                self.mo.rest_position.value = np.vstack([R, R[v]]).tolist()
            # Grow the rewind snapshot with the mesh. The runaway guard refuses to rewind
            # when the snapshot has a different vertex count than the mesh, so without this
            # every split disarmed it until a healthy frame happened to be re-cached -- and
            # once the mesh is degraded no frame IS healthy, so the net stayed disarmed for
            # the rest of the session. That is how a run reached 20.8x edge stretch and
            # |coord| 13.5 on a capsule of radius 6.9 with rewinds still reading 0.
            if self.last_good is not None and len(self.last_good) == nv:
                self.last_good = self.last_good + [list(self.last_good[v])]
            if self.last_good_rest is not None and len(self.last_good_rest) == nv:
                self.last_good_rest = list(self.last_good_rest) + [list(self.last_good_rest[v])]
                # The displacement clamp's baseline has to grow too, or it is disarmed for the
                # step after every split (see _tear_reinit).
                if self.prev_pos is not None and len(self.prev_pos) == nv:
                    self.prev_pos = np.vstack([self.prev_pos, self.prev_pos[v]])
            if not used_api:
                V = np.array(self.mo.velocity.value)
                if len(V) == nv:
                    self.mo.velocity.value = np.vstack([V, V[v]]).tolist()
                T = self.tris.copy()
                for ti in neg:
                    T[ti][T[ti] == v] = nv
                self.topo.triangles.value = T.tolist()
            # Release the adhesion along the cut. Without this the tear is invisible: both
            # lips stay glued flat to the lens by RestShapeSprings (they share a rest
            # position), so the mesh is topologically open but nothing can separate. A real
            # capsulorhexis lifts the flap off the lens as it tears, so unglue the split
            # vertex, its duplicate and their immediate ring -- that is what lets the flap
            # open and be pulled, which in turn keeps stressing the tip.
            # Unglue the two LIPS only. Ungluing their whole ring as well turned the tear
            # itself into the dominant peeling mechanism -- ~6 extra nodes per split, so a
            # 169-vertex crack stripped about a thousand spots and the cap came off the lens
            # and crumpled. The flap still lifts: the normal peel handles the area, this just
            # makes sure the cut edge itself is not stapled down.
            if self.adhered is not None:
                free = {int(v), int(nv)}
                if self.adhered & free:
                    self.adhered.difference_update(free)
                    self._push_adhesion()
            return nv

        def _push_visual(self):
            """Push the new topology to the rendered skin.

            THIS is why a tear was invisible in the SOFA window: OglModel keeps its OWN copy
            of the triangle list from load time and does not follow runtime topology changes.
            Measured after a tear -- topo triangles referenced vertices up to 2230 while the
            visual still indexed only up to 2155 with 2156 positions, i.e. the window was
            faithfully rendering the ORIGINAL intact mesh over an already-torn simulation.
            The positions must be resized first, or the new triangle indices would be out of
            range for the visual's own position array."""
            if self._visual is None:
                return
            try:
                P = np.array(self.mo.position.value)
                self._visual.position.value = P.tolist()
                self._visual.triangles.value = np.array(self.topo.triangles.value).tolist()
            except Exception as e:  # noqa: BLE001
                print(f"[Tear] visual update failed: {type(e).__name__}: {e}")

        def _tear_reinit(self):
            """Rebuild everything that caches the topology after a split.

            FIRST rebuild the topology's own EDGE list. A split rewires triangles by writing
            topo.triangles directly, which never updates topo.edges -- and MeshSpringForceField
            builds its springs from topo.edges, exactly (verified: the spring set and the edge
            set were identical). The consequences were both of the tear's worst symptoms:

              topo.edges 6321 vs 6389 real triangle edges
                129 stale edges  -> springs STAPLING the cut shut. Measured, every one of them
                                    sat within one edge length of the crack, holding it at
                                    1.04x rest, which is why the cut would not open however
                                    hard it was pulled (lip gap stuck at 0.2-0.7).
                197 missing edges -> real edges with NO spring at all, i.e. unsupported
                                    material, which is where the runaway stretch came from.
            """
            try:
                T = np.asarray(self.topo.triangles.value)
                if len(T):
                    E = np.unique(np.sort(np.concatenate(
                        [T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1), axis=0)
                    self.topo.edges.value = E.tolist()
            except Exception:  # noqa: BLE001
                pass
            # Mark the springs for rebuild; the rebuild itself happens AFTER the step, in
            # _rebuild_springs_if_dirty(). Tearing runs in onAnimateBeginEvent, i.e. directly
            # before the solve, and swapping a ForceField in and out at that moment leaves the
            # implicit solver assembling from a component constructed mid-event -- measured as
            # edge stretch 11.7x and 5 blow-ups, against 1.6x and none when the rebuild is
            # deferred by one step.
            self._spring_dirty = True
            try:
                self.bending.reinit()
            except Exception:  # noqa: BLE001
                pass
            self._push_visual()
            self._build_vtris()
            self.edges = self.edge_rest = None      # strain clamp rebuilds
            self.tri_idx = self.tri_rest_area = None
            # Keep the safety nets ARMED across a split. These used to be thrown away here on
            # every split, which quietly undid the snapshot growth done in _split_vertex and
            # left both guards dead for the step after every advance -- and splits are frequent
            # while a tear runs. Consequences, both measured: the rewind never had a usable
            # snapshot (a session reached 4948x edge stretch with only 6 rewinds), and the
            # per-step displacement clamp was disarmed so often that nodes jumped 1.05 against
            # a DISP_CLAMP of 0.5, which is the whole sheet twitching. Only drop them if they
            # genuinely no longer fit the mesh.
            n_now = len(self.mo.position.value)
            if self.last_good is not None and len(self.last_good) != n_now:
                self.last_good = self.last_good_rest = None
            if self.prev_pos is not None and len(self.prev_pos) != n_now:
                self.prev_pos = None
            # Hand the browser the crack itself, not just its length, so the tear can be seen
            # and replayed edge by edge on the timeline.
            _TEAR_PATH["path"] = [int(v) for v in self.crack] if self.crack else []
            # Every front ever opened, so a nucleated second tear does not erase the
            # drawing of the first one.
            _TEAR_PATH["paths"] = ([[int(v) for v in c] for c in self.crack_hist]
                                   + ([_TEAR_PATH["path"]] if self.crack else []))
            _TEAR_PATH["lips"] = [[int(d), int(p)] for d, p in self.dup_of.items()]
            if self.rest0 is not None:
                _publish_geometry(self.rest0, np.array(self.topo.triangles.value))

        def _tear_seed(self, P):
            """Cystotome puncture: a short radial slit near the centre. Without an initial
            crack there is no tip to drive and the membrane would only stretch."""
            self._build_vtris()
            r = np.hypot(P[:, 0], P[:, 1])
            start = int(np.argmin(np.abs(r - TEAR_START_R)))
            self.crack = [start]
            ang = np.arctan2(P[start][1], P[start][0])
            self.crack_dir = np.array([np.cos(ang), np.sin(ang)])   # outward, radial
            for _ in range(max(1, TEAR_START_LEN)):
                if not self._advance_to_best_neighbour(P, forced=True):
                    break
                P = np.array(self.mo.position.value)
            print(f"[Tear] initial nick: {len(self.crack)} vertices from r={TEAR_START_R:g}")

        def _advance_to_best_neighbour(self, P, forced=False):
            """Move the tip one edge along self.crack_dir, splitting the vertex left behind.

            Sets self.block to why it could not move, if it could not. The telemetry used to
            report "tearing" whenever the criterion passed, whether or not the crack actually
            advanced -- so a tear that met the criterion and then failed to move looked, in the
            recording, exactly like one that was tearing. Measured, that is the common case:
            c sat at 1.92 with the crack frozen at 41 vertices, and the black box called it
            "tearing" the whole time."""
            tip = self.crack[-1]
            # Exclude only the RECENT tail, not the whole history. Excluding every vertex the
            # crack ever visited is what dead-ended it: a capsulorhexis is a CLOSED circle, so
            # the tear is supposed to come back and meet its own start, and that rule made the
            # one move it must eventually make illegal. Measured stall: tip at r=6.19 with all
            # 4 neighbours already in the crack, frozen for the rest of the run even though
            # c was over 100. The tail guard is still needed to stop it immediately doubling
            # back onto the edge it just split.
            visited = set(self.crack)
            recent = set(self.crack[-TEAR_NOBACK:])
            # The SEED end of the tear is the one piece of its own path the crack is allowed to
            # reach: arriving there is the rhexis closing. Everything else it has already cut
            # stays off-limits (re-splitting a vertex that is already a lip shreds the opening),
            # but -- unlike before -- being blocked there no longer ends the tear, it just makes
            # the crack route around. Excluding the ENTIRE history was the dead-end: measured, a
            # tip sat at r=6.19 with all 4 neighbours visited and never moved again while c was
            # over 100. Detecting closure on ANY visited vertex is the opposite mistake: the
            # jagged path touches itself early, which ended the tear at 58-115 vertices instead
            # of 85-197.
            seed = set(self.crack[:max(3, TEAR_START_LEN)])
            can_close = len(self.crack) > TEAR_CLOSE_MIN
            cand = [int(j) for j in self.nbr[tip]
                    if int(j) not in recent
                    and (int(j) not in visited or (can_close and int(j) in seed))]
            # Never tear into the zonular anchor ring. Those nodes are held by a
            # FixedProjectiveConstraint whose index list is fixed at build time, so a
            # duplicate created there is NOT anchored -- the tear was cutting its own anchor
            # loose (measured: rim nodes drifting 3.0 instead of staying put), after which the
            # capsule was free again and crumpled. Anatomically the rhexis also stays well
            # inside the zonular insertion.
            if FIX_OUTER_RIM:
                lim = RIM_ANCHOR_FRAC * G.R
                cand = [j for j in cand
                        if np.hypot(P[j][0], P[j][1]) < lim]
            if not cand:
                self.block = "blocked: the crack ran into its own path (no free edge left)"
                return False
            pv = P[tip][:2]
            # Penalise RADIAL DRIFT when choosing the next edge. The criterion already asks
            # for a circumferential tear and the tip mostly gets one -- measured, 65.7% of the
            # edges it takes are within 15 deg of the fibre, against only 34.0% of the edges
            # available, and the direction it asks for sits a median 12.6 deg from the fibre.
            # The trouble is the other ~22%: with 51.9% of this mesh's edges running diagonally
            # (it is a ring mesh whose quads are split, so the diagonals outnumber both the ring
            # and the radial edges), the tip is regularly forced onto one, and each diagonal
            # step moves it to a different ring. That accumulated drift is what eventually walks
            # the crack into its own path, where every remaining neighbour lies backwards and
            # the turn limit stops it for good -- 73.7% of all steps in a recorded session.
            # Rings here are continuous, so a tear that stays on one can close; this is a
            # discretisation correction, not a change to the criterion.
            R0 = self._rest_now()
            r_tip = float(np.hypot(R0[tip][0], R0[tip][1])) if tip < len(R0) else 0.0
            best, bj = -1e9, -1
            for j in cand:
                e = P[j][:2] - pv
                n = np.linalg.norm(e)
                if n < 1e-9:
                    continue
                score = float(e @ self.crack_dir / n)
                if TEAR_RING_KEEP > 0.0 and j < len(R0) and r_tip > 0.5:
                    drift = abs(float(np.hypot(R0[j][0], R0[j][1])) - r_tip)
                    score -= TEAR_RING_KEEP * drift / max(n, 1e-9)
                if score > best:
                    best, bj = score, j
            if bj < 0:
                self.block = "blocked: no usable edge at the tip"
                return False
            e_sel = P[bj][:2] - pv
            n_sel = max(float(np.linalg.norm(e_sel)), 1e-9)
            cos_sel = float(e_sel @ self.crack_dir / n_sel)
            turn = float(np.degrees(np.arccos(np.clip(cos_sel, -1, 1))))
            if not forced and turn > TEAR_TURN_MAX:
                self.block = (f"blocked: needs a {turn:.0f}deg turn, limit is "
                              f"{TEAR_TURN_MAX:.0f}deg")
                return False
            if bj in visited:
                # The tear has come back onto its own path: the rhexis is closed. Split the
                # tip so the last edge actually opens, then stop -- continuing would re-split
                # vertices that are already lips and shred the rim of the opening.
                self._split_vertex(tip, P, np.array(self.mo.rest_position.value))
                self.crack.append(bj)
                self.closed = True
                self._tear_reinit()
                print(f"[Tear] CLOSED: the tear met its own path after {len(self.crack)} "
                      f"vertices -- capsulorhexis complete")
                return False
            R = np.array(self.mo.rest_position.value)
            self._split_vertex(tip, P, R)          # the old tip is now behind the front
            e = P[bj][:2] - pv
            self.crack_dir = e / max(np.linalg.norm(e), 1e-9)
            self.crack.append(bj)
            self._tear_reinit()
            return True

        def _tear_update(self, t):
            """One tearing opportunity: evaluate the criterion at the tip and advance."""
            P = np.array(self.mo.position.value)
            if self._visual is None:
                try:
                    self._visual = self.mo.getContext().getChild("Visual").getObject("visual")
                except Exception:  # noqa: BLE001
                    self._visual = None
            if self.rest0 is None:
                # snapshot BEFORE plasticity has had a chance to creep the rest shape
                self.rest0 = np.array(self.mo.rest_position.value)
            if self.crack is None:
                self._tear_seed(P)
                self._tear_reinit()
                return
            if self.closed:
                _TEAR_STATE.update(on=True, len=len(self.crack), c=0.0, thr=TEAR_THRESH,
                                   why="closed: the rhexis is complete")
                return
            if self.vtris is None or len(self.vtris) != len(P):
                self._build_vtris()
            # Mesh-quality brake (see TEAR_DEGEN_MAX): stop driving the tear while the mesh is
            # in bad shape, otherwise garbage stress from collapsed elements feeds the
            # criterion and the tear destroys the thing it is tearing.
            if TEAR_DEGEN_MAX > 0.0 and self.tris is not None and len(self.tris):
                ar_all = area_ratios(P, self._rest_now(), self.tris)
                frac = float(((ar_all < DEGEN_LO) | (ar_all > DEGEN_HI)).mean())
                if frac > TEAR_DEGEN_MAX:
                    _TEAR_STATE.update(on=True, len=len(self.crack), c=0.0,
                                       thr=TEAR_THRESH, why=f"paused: mesh {frac:.0%} degenerate")
                    if t - self.tear_log_t >= 1.0:
                        self.tear_log_t = t
                        print(f"[Tear] paused at t={t:.2f}s: {frac:.1%} of elements degenerate "
                              f"(limit {TEAR_DEGEN_MAX:.0%}) -- letting the mesh recover")
                    return
            budget, done = max(1, TEAR_MAX_ADVANCE), 0
            while done < budget:
                done += 1
                P = np.array(self.mo.position.value)
                tip = self.crack[-1]
                S = self._tip_stress(P, P[tip][0], P[tip][1])
                if S is None:
                    return
                S1, S2, th1, s1_local = S
                # The tip must actually be loaded before its direction means anything.
                if s1_local < TEAR_LOCAL_MIN:
                    # The tip is idle. Per Dequidt 2013 section 4.3 the criterion is evaluated
                    # at an existing tip OR at the centre of each element, so look for a place
                    # that IS overloaded rather than insisting the user pull near this tip.
                    if self._try_nucleate(P):
                        return
                    # Report the values THIS evaluation measured. Leaving the previous ones in
                    # place made the panel contradict itself -- it showed a local sigma1 above
                    # the gate next to the message saying the gate had refused, because that
                    # number was several frames old.
                    R0 = self._rest_now()
                    rt = R0[tip] if tip < len(R0) else P[tip]
                    _TEAR_STATE.update(on=True, len=len(self.crack), c=0.0, thr=TEAR_THRESH,
                                       tipr=round(float(np.hypot(rt[0], rt[1])), 2),
                                       tipx=round(float(rt[0]), 3),
                                       tipy=round(float(rt[1]), 3),
                                       s1=round(float(S1), 1), s2=round(float(S2), 1),
                                       th1=round(float(th1), 1),
                                       su=0.0, sbu=0.0, loc=round(float(s1_local), 2),
                                       why="tip not loaded -- pull toward the crack tip")
                    return
                # Coarse-mesh stress-concentration correction: a real crack tip is singular,
                # a linear triangle averages that away, so the tip state is scaled up rather
                # than the threshold scaled down (which would also weaken the bulk).
                S1 *= TEAR_TIP_GAIN
                S2 *= TEAR_TIP_GAIN
                # Concentric fibres, from the REST shape. They are a property of the
                # MATERIAL, so the azimuth must be the one the tip has on the undeformed
                # capsule; taking it from the deformed position let the fibre field rotate
                # with the pull, which is not something real collagen does.
                R0 = self._rest_now()
                rt = R0[tip] if tip < len(R0) else P[tip]
                fib = np.degrees(np.arctan2(rt[1], rt[0])) + 90.0
                c, d, dang, su, sbu = self._argmax_c(S1, S2, th1, fib, self.crack_dir)
                # Smooth the heading (see TEAR_DIR_INERTIA) rather than snapping to the new
                # argmax every step. The criterion still decides WHERE it wants to go; this
                # only stops the path zigzagging as the stress direction jitters.
                if TEAR_DIR_INERTIA > 0.0 and self.crack_dir is not None:
                    prev = np.asarray(self.crack_dir, dtype=float)[:2]
                    if float(prev @ d) < 0.0:
                        prev = -prev          # crack direction is a LINE, not an arrow
                    mix = TEAR_DIR_INERTIA * prev + (1.0 - TEAR_DIR_INERTIA) * d
                    n = float(np.linalg.norm(mix))
                    if n > 1e-9:
                        d = mix / n
                # Everything the criterion used, mirrored to the viewer: with all of Eq.3/Eq.4
                # on screen per frame, "why did it not tear" is readable instead of guessed.
                _TEAR_STATE.update(on=True, len=len(self.crack), c=round(float(c), 2),
                                   thr=TEAR_THRESH,
                                   tipr=round(float(np.hypot(rt[0], rt[1])), 2),
                                   # REST space, like the pull marker and the disc the
                                   # viewer draws. Publishing the deformed position mixed two
                                   # frames of reference, so tip-to-instrument distances came
                                   # out larger than the capsule itself (9.68 on r=6.89).
                                   tipx=round(float(rt[0]), 3),
                                   tipy=round(float(rt[1]), 3),
                                   s1=round(float(S1), 1), s2=round(float(S2), 1),
                                   th1=round(float(th1), 1), fib=round(float(fib), 1),
                                   dang=round(float(dang), 1), su=round(float(su), 1),
                                   sbu=round(float(sbu), 1), loc=round(float(s1_local), 2),
                                   lefm=round(float(min(self._crack_extent_factor(),
                                                        TEAR_LEFM_CAP)), 2),
                                   why="tearing" if c >= 1.0 else "c<1: pull harder near the tip")
                if c < 1.0:
                    self._drive_ref = (S1 if self._drive_ref is None
                                       else max(S1, self._drive_ref * TEAR_ARREST_DECAY))
                    return                                   # not tearing right now
                # Arrest on unloading: keep tearing only while the tip is still being loaded.
                # Measured without this, releasing the mouse entirely still carried the crack
                # 98 -> 133 vertices and the tip out to r=6.58 of 6.89, because residual
                # elastic stress holds c far above 1 long after the hand has gone.
                ref = self._drive_ref
                if TEAR_ARREST_REBASE and self._just_split:
                    # The drop we are about to measure is OUR doing, not the hand's: the
                    # previous opportunity split a vertex and that released the tip. Re-baseline
                    # rather than compare against the pre-split peak, or the tear can never take
                    # two bites in a row.
                    ref = None
                self._just_split = False
                self._drive_ref = S1 if ref is None else max(S1, ref * TEAR_ARREST_DECAY)
                if ref is not None and S1 < ref * TEAR_ARREST:
                    _TEAR_STATE.update(on=True, len=len(self.crack), c=round(float(c), 2),
                                       thr=TEAR_THRESH,
                                       why="arrested: tip unloading (pull again to continue)")
                    return
                # Unstable propagation: the further past the criterion, the further the crack
                # runs. Scaled gently (c/4) rather than linearly -- the tip gain and reach can
                # push c into the tens, which at full budget every step shredded the mesh
                # (430 crack vertices in 200 steps) instead of tearing it.
                # Advance ONE edge per opportunity, then let the solver run. Splitting several
                # edges here used them all against a SINGLE stress evaluation: no time step
                # happens inside this loop, so the field cannot relax as the crack consumes it
                # and the tear keeps going on stress it has already released. Measured with 4
                # per opportunity, the crack ran 2.01 -> 6.58 in radius in 0.6s and never
                # stopped while c climbed to 193. One per opportunity means every advance is
                # re-justified against freshly solved physics, so the tear follows the pull and
                # STOPS when the pull stops.
                budget = 1
                self.crack_dir = d
                self.nuc_tick = 0      # this front is alive; do not go looking elsewhere
                self.block = None
                # Take the sharp turn once the tip has been boxed in long enough. Only the turn
                # limit is escaped; "no usable edge" and "ran into its own path" are real
                # topological dead ends and forcing them would re-split existing lips.
                escape = (TEAR_BLOCK_ESCAPE > 0
                          and self._blocked_runs >= TEAR_BLOCK_ESCAPE)
                if not self._advance_to_best_neighbour(P, forced=escape):
                    # The criterion passed but the mesh had nowhere legal to go. Report THAT,
                    # not "tearing" -- it is a completely different problem to fix.
                    if self.block:
                        _TEAR_STATE["why"] = self.block
                        if "deg turn" in self.block:
                            self._blocked_runs += 1
                        else:
                            self._blocked_runs = 0   # a real dead end; escaping cannot help
                    # A boxed-in tip is a dead tip. Look for somewhere else to start, exactly
                    # as we do when it is idle -- otherwise the whole tear is over for good.
                    self._try_nucleate(P, blocked=True)
                    return
                self._just_split = True
                if escape:
                    print(f"[Tear] escaped a {self._blocked_runs}-step turn block")
                self._blocked_runs = 0
                if t - self.tear_log_t >= 0.5:
                    self.tear_log_t = t
                    tp = self.crack[-1]
                    print(f"[Tear] t={t:.2f}s len={len(self.crack)} c={c:.2f} "
                          f"tip r={np.hypot(P[tp][0], P[tp][1]):.2f} "
                          f"verts={len(self.mo.position.value)}")

        def onAnimateEndEvent(self, event):
            # Safety-net chain, in order, all BEFORE this frame is rendered:
            #   (0) NaN / runaway rewind  (0b) per-step displacement clamp
            #   (1) speed clamp           (2) edge-strain clamp (+velocity consistency)
            #   (2b) FEM anti-collapse    (2c) final render guard
            #   (3) healthy-frame snapshot (the rewind target)
            #
            # (0) NaN is sticky (NaN > limit == False beats every clamp below), and a
            # finite-but-runaway frame poisons everything downstream: both rewind.
            P0 = np.array(self.mo.position.value)
            coord_runaway = (MAX_COORD > 0.0 and P0.size > 0
                             and np.isfinite(P0).all() and np.abs(P0).max() > MAX_COORD)
            runaway = coord_runaway
            # NOTE: the strain panic is NOT evaluated here. It used to be, at stage (0),
            # which is before the strain clamp at stage (2) that exists precisely to pull an
            # over-stretched edge back. A transient over-stretch -- normal right after a split,
            # before the clamp has run -- therefore triggered a full rewind instead of being
            # fixed, and once the snapshot was available again that meant rolling back on 47%
            # of all steps. It is checked after the clamp instead; see _strain_panic_check().
            broken = (not np.isfinite(P0).all()) or runaway
            can_rewind = (self.last_good is not None
                          and len(self.last_good) == len(P0))
            if broken and can_rewind:
                if (runaway and coord_runaway and self.step % 15 == 0):
                    print(f"[Runaway] a node passed |coord|>{MAX_COORD:g} "
                          f"(max {float(np.abs(P0).max()):.1f}) -> rewound before it "
                          f"flew off-screen")
                self._rewind()
                return
            if broken:
                # A runaway we CANNOT rewind out of. This used to be a silent no-op -- worse
                # than that, with last_good still None the old code called the rewind anyway,
                # which did nothing, and then returned, skipping every clamp below. And once
                # the mesh has degraded no frame is healthy enough to be cached, so after the
                # next split the snapshot length stops matching and the guard is disabled for
                # good. Measured consequence in a real session: edges reaching 4948x rest and
                # speeds of 7195 against a limit of 25, with only 6 rewinds in the whole run.
                # So contain it in place instead: kill the kinetic energy and pull the
                # over-stretched edges back hard, then fall through to the normal clamps.
                self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(P0)
                if MAX_STRETCH > 0.0:
                    if self.edges is None:
                        self._build_edges()
                    if len(self.edges):
                        P = np.array(self.mo.position.value)
                        e0, e1 = self.edges[:, 0], self.edges[:, 1]
                        limit = self.edge_rest * MAX_STRETCH
                        for _ in range(STRAIN_PANIC_ITERS):
                            d = P[e1] - P[e0]
                            L = np.linalg.norm(d, axis=1)
                            over = L > limit
                            if not over.any():
                                break
                            n = d[over] / np.maximum(L[over], 1e-9)[:, None]
                            excess = (L[over] - limit[over])[:, None]
                            corr = np.zeros_like(P); cnt = np.zeros(len(P))
                            np.add.at(corr, e0[over], 0.5 * excess * n)
                            np.add.at(corr, e1[over], -0.5 * excess * n)
                            np.add.at(cnt, e0[over], 1.0)
                            np.add.at(cnt, e1[over], 1.0)
                            t = cnt > 0
                            P[t] += corr[t] / cnt[t][:, None]
                        self.mo.position.value = P.tolist()
                        self.prev_pos = None      # this frame is not a clamp baseline
                self.contained += 1
                if self.step % 15 == 0:
                    print(f"[Contain] runaway with no usable snapshot "
                          f"(mesh has {len(P0)} verts, snapshot "
                          f"{0 if self.last_good is None else len(self.last_good)}) "
                          f"-> velocities zeroed and edges pulled back in place")

            # (0b) Displacement clamp: cap a solver-produced jump in the very step it
            # is born (see DISP_CLAMP).
            if (DISP_CLAMP > 0.0 and self.prev_pos is not None
                    and len(self.prev_pos) == len(P0)):
                d = P0 - self.prev_pos
                dist = np.linalg.norm(d, axis=1)
                hot = dist > DISP_CLAMP
                if hot.any():
                    P0[hot] = self.prev_pos[hot] + d[hot] * (DISP_CLAMP / dist[hot])[:, None]
                    self.mo.position.value = P0.tolist()
                    # Rescale (never zero) velocity: zeroing freezes a legitimately
                    # swinging flap for a frame -> stop-go stutter.
                    vcap = DISP_CLAMP / max(float(self.mo.getContext().getDt()), 1e-9)
                    v2 = np.array(self.mo.velocity.value, copy=True)
                    sp = np.linalg.norm(v2[hot], axis=1)
                    fast = sp > vcap
                    if fast.any():
                        idx = np.where(hot)[0][fast]
                        v2[idx] *= (vcap / sp[fast])[:, None]
                        self.mo.velocity.value = v2
                    self.disp_clamped += int(hot.sum())

            # (1) Speed clamp: clip runaway node speeds before they travel next step.
            if MAX_SPEED > 0.0:
                v = self.mo.velocity.value
                if len(v):
                    speed = np.linalg.norm(v, axis=1)
                    hot = speed > MAX_SPEED
                    if hot.any():
                        v2 = np.array(v, copy=True)
                        v2[hot] *= (MAX_SPEED / speed[hot])[:, None]
                        self.mo.velocity.value = v2
                        self.clamped += int(hot.sum())

            # (2) Strain clamp: project over-stretched edges back to MAX_STRETCH x rest
            # (a few relaxation passes; rest lengths cached once).
            # The strain clamp stays ON in tear mode. It was skipped on the assumption that it
            # would pull a fresh cut shut -- that was wrong: after a split the two lips are
            # DIFFERENT vertices with no edge between them, so the clamp cannot close a crack;
            # it only limits real mesh edges. Skipping it let torn-off strips stretch without
            # bound into the long spikes seen in the GUI. (edge_rest is invalidated on every
            # split, so it always re-derives against the current topology.)
            if MAX_STRETCH > 0.0:
                if self.edges is None:
                    self._build_edges()
                if len(self.edges):
                    P = np.array(self.mo.position.value)
                    e0, e1 = self.edges[:, 0], self.edges[:, 1]
                    limit = self.edge_rest * MAX_STRETCH
                    moved = False
                    for _ in range(STRAIN_ITERS):
                        d = P[e1] - P[e0]
                        L = np.linalg.norm(d, axis=1)
                        over = L > limit
                        if not over.any():
                            break
                        moved = True
                        n = d[over] / L[over][:, None]
                        excess = (L[over] - limit[over])[:, None]
                        # Average (not sum) corrections per node: summed np.add.at over
                        # k over-limit edges x STRAIN_ITERS passes can move a shared
                        # node further than the solve itself -- the spike this net
                        # exists to prevent.
                        corr = np.zeros_like(P)
                        cnt = np.zeros(len(P))
                        np.add.at(corr, e0[over], 0.5 * excess * n)
                        np.add.at(corr, e1[over], -0.5 * excess * n)
                        np.add.at(cnt, e0[over], 1.0)
                        np.add.at(cnt, e1[over], 1.0)
                        touched = cnt > 0
                        P[touched] += corr[touched] / cnt[touched][:, None]
                    if moved:
                        self.mo.position.value = P.tolist()
                        # Velocity consistency: position projection alone leaves the
                        # separating velocity in place, so the springs recoil next step
                        # (single-step speed pops). Remove the separating component on
                        # at-limit edges (averaged per node) so the projection sticks.
                        V = np.array(self.mo.velocity.value, copy=True)
                        d = P[e1] - P[e0]
                        L = np.linalg.norm(d, axis=1)
                        near = L > 0.98 * limit
                        if near.any():
                            u = d[near] / np.maximum(L[near], 1e-12)[:, None]
                            vrel = ((V[e1[near]] - V[e0[near]]) * u).sum(1)
                            sep = vrel > 0.0
                            if sep.any():
                                iN = np.where(near)[0][sep]
                                corr = 0.5 * vrel[sep][:, None] * u[sep]
                                dV = np.zeros_like(V)
                                cnt = np.zeros(len(V))
                                np.add.at(dV, e1[iN], -corr)
                                np.add.at(dV, e0[iN], corr)
                                np.add.at(cnt, e1[iN], 1.0)
                                np.add.at(cnt, e0[iN], 1.0)
                                touched = cnt > 0
                                V[touched] += dV[touched] / cnt[touched][:, None]
                                self.mo.velocity.value = V

            # (2b) Anti-collapse (FEM-only; springs never divide by area): repair
            # near-collinear triangles, or rewind the sheet if a whole cluster
            # collapsed at once / repair failed.
            degenerate_after = None       # None = not yet known
            if MIN_AREA_FRAC > 0.0 and not USE_MASS_SPRING and not CAP_TEAR:
                if self.tri_idx is None:
                    self._build_tri_areas()
                tris = self.tri_idx
                if len(tris):
                    P = np.array(self.mo.position.value)
                    area = 0.5 * np.linalg.norm(
                        np.cross(P[tris[:, 1]] - P[tris[:, 0]],
                                 P[tris[:, 2]] - P[tris[:, 0]]), axis=1)
                    bad = np.where(area < MIN_AREA_FRAC * self.tri_rest_area)[0]
                    if len(bad) > SEVERE_COLLAPSE and self.last_good is not None:
                        # a whole cluster collapsed this step = acute blow-up -> rewind
                        self._rewind()
                        if self.step % 15 == 0:
                            print(f"[Rewind] {len(bad)} triangles collapsed at once -> "
                                  f"rewound to last healthy frame (total {self.rewinds})")
                        return
                    if len(bad):
                        for t in bad:
                            self._repair_flat_triangle(P, tris[t],
                                                       float(self.tri_rest_area[t]))
                        self.collapsed += int(len(bad))
                        self.mo.position.value = P.tolist()
                        if self.step % 15 == 0:
                            print(f"[AntiCollapse] repaired {len(bad)} near-flat "
                                  f"triangle(s) (total {self.collapsed}); mesh kept solvable")
                        degenerate_after = self._has_degenerate(P)
                        if degenerate_after and self.last_good is not None:
                            self._rewind()
                            return
                    else:
                        degenerate_after = False

            # (2b2) Only now, with the clamps done, decide whether this is a real blow-up.
            self._strain_panic_check()

            # (2c) Final render guard: the nets above edit positions after (0b), so
            # re-apply the displacement cap as the LAST write of the step -- whatever
            # was written, the rendered frame can never jump a node more than
            # DISP_CLAMP. last_jump = pre-guard peak ('maxjump' diagnostics column).
            self.last_jump = 0.0
            if DISP_CLAMP > 0.0 and self.prev_pos is not None:
                P = np.array(self.mo.position.value)
                if len(P) == len(self.prev_pos):
                    d = P - self.prev_pos
                    dist = np.linalg.norm(d, axis=1)
                    if len(dist):
                        self.last_jump = float(dist.max())
                    hot = dist > DISP_CLAMP
                    if hot.any():
                        P[hot] = self.prev_pos[hot] + d[hot] * (DISP_CLAMP / dist[hot])[:, None]
                        self.mo.position.value = P.tolist()
                        # same soft response as (0b): rescale velocity, don't freeze it
                        vcap = DISP_CLAMP / max(float(self.mo.getContext().getDt()), 1e-9)
                        v2 = np.array(self.mo.velocity.value, copy=True)
                        sp = np.linalg.norm(v2[hot], axis=1)
                        fast = sp > vcap
                        if fast.any():
                            idx = np.where(hot)[0][fast]
                            v2[idx] *= (vcap / sp[fast])[:, None]
                            self.mo.velocity.value = v2
                        self.disp_clamped += int(hot.sum())

            # Rebuild the edge springs now that the step is over (see _tear_reinit).
            # MeshSpringForceField reads the topology only at init, so a split needs the whole
            # component replaced -- reinit() leaves the old spring set in place.
            if self._spring_dirty:
                self._spring_debt += 1
                if self._spring_debt >= TEAR_SPRING_REBUILD:
                    self._spring_debt = 0
                    self._spring_dirty = False
                    try:
                        node = self.springs.getContext()
                        node.removeObject(self.springs)
                        self.springs = node.addObject(
                            "MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
                        self.springs.init()
                    except Exception:  # noqa: BLE001
                        pass

            # (3) Snapshot as rewind target only when genuinely healthy (see
            # _is_healthy) -- caching a degenerate or inflating frame would make every
            # rewind land back inside the failure. Rest is snapshotted too so a rewind
            # restores a matching (position, rest) pair.
            Pn = np.array(self.mo.position.value)
            if self._is_healthy(Pn):
                self.last_good = Pn.tolist()
                self.last_good_rest = list(self.mo.rest_position.value)
            # what this step actually renders = the disp clamp's next baseline
            self.prev_pos = Pn

        def onAnimateBeginEvent(self, event):
            t = self.mo.getContext().getTime()

            # Poll Bending.stiffness and re-bake on change: the component bakes ks
            # into per-edge data, so a GUI edit does nothing until reinit().
            ks_now = float(self.bending.stiffness.value)
            if self.last_ks is None:
                self.last_ks = ks_now
            elif abs(ks_now - self.last_ks) > 1e-9:
                self.bending.reinit()
                self.last_ks = ks_now
                print(f"[Tune] BEND_STIFFNESS -> {ks_now:.1f} (applied)")

            if not self.paper_done and t >= SWITCH_T:
                # Cloth -> paper stiffening (FEM path; a no-op stiffness rewrite in
                # mass-spring mode). Optim takes youngModulus as scalar, plain as list.
                if self.fem is not None:
                    try:
                        self.fem.youngModulus.value = PAPER_YOUNG
                    except Exception:  # noqa: BLE001
                        self.fem.youngModulus.value = [PAPER_YOUNG]
                    self.fem.reinit()
                self.springs.linesStiffness.value = EDGE_STIFFNESS
                self.paper_done = True
                print(f"[ClothToPaper] t={t:.2f}s -> paper "
                      f"({'mass-spring' if self.fem is None else f'young={PAPER_YOUNG}'})")

            # --- RUNG 1 TEAR: break the pre-slit circle progressively, detach the disc ---
            if SCRIPTED_TEAR and self.stitch is not None and self.n_stitch:
                frac = (t - TEAR_T) / max(TEAR_DURATION, 1e-6)
                if frac > 0.0:
                    n_break = int(min(1.0, frac) * self.n_stitch)   # how many are torn
                    already = self.enabled.count(False)
                    if n_break > already:               # tear the next arc of the circle
                        for k in range(n_break):
                            self.enabled[k] = False
                        self.stitch.enabled.value = list(self.enabled)
                    if (not self.tear_detached and self.adhered is not None
                            and self.adhesion is not None):
                        # unglue the central disc so it can lift; the rim stays glued
                        self.adhered.difference_update(self.central)
                        if self.adhered:
                            self.adhesion.points.value = sorted(self.adhered)
                        else:
                            self.adhesion.stiffness.value = [0.0]
                        self.tear_detached = True
                        print(f"[Tear] t={t:.2f}s circle tearing; central disc "
                              f"({len(self.central)} nodes) detached from the lens")
                    if n_break >= self.n_stitch and already < self.n_stitch:
                        print(f"[Tear] t={t:.2f}s circle fully torn -> central disc is free")

            pos = self.mo.position.value
            rest = self.mo.rest_position.value
            if self.adhesion is not None and self.adhered is None:
                self.adhered = set(range(len(pos)))
                self._check_peel_reachable(np.asarray(pos))
                self.adhesion.points.value = sorted(self.adhered)

            # --- diagnostics CSV: one numeric row per step, analysed offline after a
            # session (peaks + safety-net counters; see LOG_DIAG at the top).
            if LOG_DIAG:
                if self.diag is None:
                    # line-buffered, so closing the app mid-session loses no rows
                    # Keep the previous session's black box. Overwriting it meant the
                    # evidence for "that run went wrong" was gone the moment anything ran
                    # again -- including a diagnostic probe, which is exactly when you most
                    # want it. Same rotation the run log already uses.
                    try:
                        if os.path.exists(DIAG_PATH):
                            prev = DIAG_PATH.replace(".csv", ".prev.csv")
                            if os.path.exists(prev):
                                os.remove(prev)
                            os.replace(DIAG_PATH, prev)
                    except OSError:
                        pass
                    self.diag = open(DIAG_PATH, "w", buffering=1)
                    # Black box: one row per STEP for the whole session. The TEAR
                    # columns matter as much as the mechanics ones -- "why" is what
                    # revealed that two safety gates were refusing 91.6% of all
                    # tearing opportunities, which the viewport could never show.
                    self.diag.write("step,t,maxcoord,maxspeed,maxstretch,maxjump,glued,"
                                    "rewinds,vclamped,dclamped,crack,c,tipr,why\n")
                P = np.asarray(pos)
                V = np.asarray(self.mo.velocity.value)
                if self.edges is None:
                    self._build_edges()
                if len(self.edges):
                    L = np.linalg.norm(P[self.edges[:, 1]] - P[self.edges[:, 0]], axis=1)
                    maxstretch = float((L / np.maximum(self.edge_rest, 1e-12)).max())
                else:
                    maxstretch = 1.0
                maxspeed = float(np.linalg.norm(V, axis=1).max()) if len(V) else 0.0
                _ts = _TEAR_STATE
                self.diag.write(f"{self.step},{t:.3f},{float(np.abs(P).max()):.3f},"
                                f"{maxspeed:.3f},{maxstretch:.3f},{self.last_jump:.3f},"
                                f"{len(self.adhered) if self.adhered else 0},{self.rewinds},"
                                f"{self.clamped},{self.disp_clamped},"
                                f"{_ts.get('len', 0)},{_ts.get('c', 0)},"
                                f"{_ts.get('tipr', 0)},'{_ts.get('why', '')}'\n")
            if self.adhesion is not None and self.adhered and not self.frozen:
                idx = np.fromiter(self.adhered, dtype=int)
                lift = np.linalg.norm(pos[idx] - rest[idx], axis=1)
                front_lift = self.break_lift * PEEL_FRONT_EASE
                sel = np.flatnonzero(lift > min(front_lift, self.break_lift))
                cand, cand_lift = idx[sel], lift[sel]
                if PEEL_FRONT_ONLY and cand.size:
                    if self.nbr is None:
                        self._build_peel_adjacency()
                    adh = self.adhered
                    # PROPAGATION: a spot at the edge of the still-bonded region (on the mesh
                    # boundary, or with a neighbour already debonded) lets go at break_lift.
                    # This front rule exists to stop the whole sheet debonding at once.
                    #
                    # NUCLEATION: but the front rule ALONE makes the middle of the capsule
                    # impossible to lift, and that -- not the tear criterion -- is what makes
                    # the membrane feel welded to the lens. The bonded region starts as the
                    # ENTIRE disc, so its only front is the mesh boundary, which the zonules
                    # anchor in tear mode; a node in the middle is never on the boundary and
                    # never has a debonded neighbour, so it can never qualify however hard it
                    # is pulled. Measured: pulling a mid-disc node with 6384 of force and a
                    # 10.6-long mouse arrow lifted it just 1.36 and released 65 of 2153 spots.
                    # So let a spot nucleate anywhere, at PEEL_NUCLEATE times the break lift.
                    # Debonding fresh material being harder than extending an existing debond
                    # is also the right physics, and the high bar keeps the avalanche away.
                    nuc = cand_lift > self.break_lift * PEEL_NUCLEATE
                    keep = [k for k, i in enumerate(cand.tolist())
                            if nuc[k]
                            or ((i in self.boundary
                                 or any(int(j) not in adh for j in self.nbr[int(i)]))
                                and cand_lift[k] > front_lift)]
                    cand, cand_lift = cand[keep], cand_lift[keep]
                # Keep the debond front with the tear (see PEEL_NEAR_CRACK).
                if (PEEL_NEAR_CRACK > 0.0 and CAP_TEAR and cand.size
                        and getattr(self, "crack", None)):
                    ck = [v for v in self.crack if v < len(pos)]
                    if ck:
                        C = np.asarray(pos)[ck][:, :2]
                        Q = np.asarray(pos)[cand][:, :2]
                        d2 = ((Q[:, None, :] - C[None, :, :]) ** 2).sum(axis=2).min(axis=1)
                        near = d2 <= PEEL_NEAR_CRACK ** 2
                        cand, cand_lift = cand[near], cand_lift[near]
                # ...and with the INSTRUMENT (see PEEL_NEAR_TOOL). This is the half that
                # makes peeling follow the hand instead of the tear's whole history.
                if PEEL_NEAR_TOOL > 0.0 and cand.size:
                    tool = self._tool_xy()
                    if tool is None:
                        cand, cand_lift = cand[:0], cand_lift[:0]
                    else:
                        Q = np.asarray(pos)[cand][:, :2]
                        d2 = ((Q - np.asarray(tool)[None, :]) ** 2).sum(axis=1)
                        near = d2 <= PEEL_NEAR_TOOL ** 2
                        cand, cand_lift = cand[near], cand_lift[near]
                if PEEL_RATE > 0 and cand.size > PEEL_RATE:
                    # crack tip first: the most-lifted spots are the ones at the front
                    order = np.argsort(-cand_lift)[:PEEL_RATE]
                    cand = cand[order]
                broken = cand
                if broken.size:
                    self.adhered.difference_update(broken.tolist())
                    # Do NOT cut a broken node loose in one step (that releases its full
                    # stored spring force as one impulse -> local twitch). Move it to the
                    # fade-out set; _push_adhesion carries it at a decaying stiffness.
                    for b in broken.tolist():
                        self.peel_fade[int(b)] = ADHESION_STIFF * PEEL_FADE
                    self._push_adhesion()
                    if t - self.last_log_t >= 0.5:
                        print(f"[Peel] t={t:.2f}s  {len(self.adhered)} spots still "
                              f"glued to the lens")
                        self.last_log_t = t
                if not self.adhered and not self.fully_peeled:
                    print(f"[Peel] t={t:.2f}s  membrane fully peeled off the lens")
                    self.fully_peeled = True
                    # Endgame: the free sheet still carries the pull momentum. Remove
                    # the momentum (not the geometry): arrest velocity, ramp damping,
                    # drop the now-pointless lens obstacle.
                    self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.mo.position.value)
                    self.damper.dampingCoefficient.value = PEEL_SETTLE_DAMPING
                    lens = self.mo.getContext().getObject("LensObstacle")
                    if lens is not None:
                        lens.stiffness.value = 0.0

            # Advance the peel fade-outs: decay each fading node's stiffness, drop it
            # once negligible. Independent of the adhered set, so the tail of a full
            # peel still fades cleanly.
            if self.peel_fade and not self.frozen:
                for nd in list(self.peel_fade):
                    self.peel_fade[nd] *= PEEL_FADE
                    if self.peel_fade[nd] < PEEL_FADE_MIN:
                        del self.peel_fade[nd]
                self._push_adhesion()

            # Slide the adhesion anchors along the lens NORMAL so the spring can only pull
            # in the surface plane (see ADH_TANGENTIAL). anchor = rest + n*((P-rest).n), which
            # by construction leaves the spring force k*(anchor-P) with no normal component.
            if self.anchor_mo is not None:
                try:
                    P = np.asarray(pos, dtype=float)
                    R = self._rest_now()
                    m = min(len(P), len(R))
                    if m:
                        # outward normal of the oblate lens at the REST spot
                        n = np.stack([R[:m, 0] / (G.A * G.A),
                                      R[:m, 1] / (G.A * G.A),
                                      (R[:m, 2] - G.Z0) / (G.C * G.C)], axis=1)
                        ln = np.linalg.norm(n, axis=1, keepdims=True)
                        n = n / np.maximum(ln, 1e-12)
                        d = P[:m] - R[:m]
                        anch = R[:m] + n * (d * n).sum(axis=1, keepdims=True)
                        cur_a = np.asarray(self.anchor_mo.position.value, dtype=float)
                        if len(cur_a) != len(P):
                            # a split appended vertices: grow the anchors to match
                            if len(cur_a) < len(P):
                                pad = np.asarray(P[len(cur_a):], dtype=float)
                                cur_a = np.vstack([cur_a, pad]) if len(cur_a) else pad
                            cur_a = cur_a[:len(P)]
                        cur_a[:m] = anch
                        self.anchor_mo.position.value = cur_a.tolist()
                except Exception:  # noqa: BLE001
                    pass

            # Publish what is still stuck to the lens (see _ADH_STATE).
            if self.adhesion is not None and self.adhered is not None:
                n = len(pos)
                if _ADH_STATE["n"] != n or self.step % 3 == 0:
                    a = np.full(n, ord("0"), dtype=np.uint8)
                    idx = np.fromiter(self.adhered, dtype=int, count=len(self.adhered))
                    if idx.size:
                        a[idx[idx < n]] = ord("1")
                    _ADH_STATE["glued"] = a.tobytes().decode("ascii")
                    _ADH_STATE["n"] = n

            # Where is the instrument pulling right now? (see _PULL_STATE)
            try:
                F = np.asarray(self.mo.force.value, dtype=float)
                if F.ndim == 2 and len(F):
                    mag = np.linalg.norm(F, axis=1)
                    k = int(np.argmax(mag))
                    t_now = float(self.mo.getContext().getTime())
                    if self._is_grabbing() and k < len(pos):
                        if _PULL_SEG["cur"] < 0 or t_now - _PULL_SEG["last_t"] > PULL_GAP:
                            _PULL_SEG["n"] += 1
                            _PULL_SEG["cur"] = _PULL_SEG["n"]
                        _PULL_SEG["last_t"] = t_now
                        r0 = self._rest_now()
                        rx, ry = (float(r0[k][0]), float(r0[k][1])) if k < len(r0) else (0.0, 0.0)
                        _PULL_STATE.update(on=True, x=round(rx, 3), y=round(ry, 3),
                                           fx=round(float(F[k][0]), 1),
                                           fy=round(float(F[k][1]), 1),
                                           mag=round(float(mag[k]), 1),
                                           seg=_PULL_SEG["cur"])
                    else:
                        if (_PULL_SEG["cur"] > 0
                                and t_now - _PULL_SEG["last_t"] > PULL_GAP):
                            _PULL_SEG["cur"] = -1
                        _PULL_STATE["on"] = False
                        _PULL_STATE["seg"] = _PULL_SEG["cur"]
            except Exception:  # noqa: BLE001
                _PULL_STATE["on"] = False

            self.step += 1

            # --- camera: probe / freeze-while-grabbing (both normally off) ----------
            if CAM_PROBE:
                cur = self._obj_paths()
                if self._probe_prev is not None:
                    added = [x for x in cur if x not in self._probe_prev]
                    removed = [x for x in self._probe_prev if x not in cur]
                    if added or removed:
                        print(f"[CamProbe] {len(self._probe_prev)}->{len(cur)} "
                              f"ADDED={added} REMOVED={removed}", flush=True)
                self._probe_prev = cur

            if self.camera is not None and not LOCK_CAMERA:
                if self.cam_home is None:      # capture start view once (R = re-centre)
                    try:
                        self.cam_home = (list(self.camera.position.value),
                                         list(self.camera.lookAt.value))
                    except Exception:  # noqa: BLE001
                        self.cam_home = None
                # orbit off while manually locked (V) or mid-grab; write on change only
                grabbing = self._is_grabbing() if FREEZE_CAMERA_WHILE_PULLING else False
                want_active = not (self.cam_lock or grabbing)
                if want_active != self.cam_active:
                    self.camera.activated.value = want_active
                    self.cam_active = want_active

            # --- real tearing: advance the crack from its tip -----------------------
            if CAP_TEAR and not self.frozen and self.step % TEAR_EVERY == 0:
                try:
                    self._tear_update(t)
                except Exception as e:  # noqa: BLE001
                    print(f"[Tear] skipped this step: {type(e).__name__}: {e}")
                # A split GROWS the position/rest arrays, and pos/rest were captured at the
                # top of this handler -- everything below (the stress observer, the peel
                # logic) must use the new ones or it indexes the new triangle list with the
                # old vertex arrays.
                pos = self.mo.position.value
                rest = self.mo.rest_position.value

            # --- stress observer (foundation for the tear criterion) ----------------
            if SHOW_STRESS and self.step % STRESS_EVERY == 0:
                # a split changes the triangle count, so the cached list must follow it
                if self.tris is None or len(self.tris) != len(self.topo.triangles.value):
                    self.tris = np.array(self.topo.triangles.value)
                if len(self.tris):
                    E_obs, nu_obs = self._stress_material()
                    s1, s2, sdir, aratio = principal_stress(np.asarray(pos),
                                                            np.asarray(rest), self.tris,
                                                            E=E_obs, nu=nu_obs)
                    self.sigma1_max = float(s1.max())
                    if self.display is not None:
                        self.display.triangleData.value = s1.tolist()
                    if STRESS_UI:
                        self._publish_stress(s1, s2, sdir, aratio, t)

                    # peak + direction is all a tear needs (crack runs perp to sigma1)
                    P = np.asarray(pos)
                    cen = P[self.tris].mean(axis=1)          # triangle centroids
                    order = np.argsort(-s1)
                    hot = order[:max(1, STRESS_TOP_N + 1)]
                    self.hot_tri = int(order[0])
                    self.hot_pos = cen[order[0]]
                    self.hot_dir = sdir[order[0]]
                    if self.probe is not None:
                        pts = [cen[i].tolist() for i in hot]
                        # last point: offset along sigma1 -> shows the direction; the
                        # crack would advance perpendicular to this pair.
                        pts.append((cen[order[0]] + self.hot_dir * 0.8).tolist())
                        need = STRESS_TOP_N + 2
                        pts = (pts + [pts[-1]] * need)[:need]
                        self.probe.position.value = pts

                    if t - self.last_stress_log >= STRESS_LOG_EVERY:
                        self.last_stress_log = t
                        bad = (aratio < DEGEN_LO) | (aratio > DEGEN_HI)
                        good = ~bad
                        healthy = float(s1[good].max()) if good.any() else 0.0
                        if healthy < 1.0:
                            # nothing is loaded: sigma1 and its direction are meaningless
                            print(f"[sigma1] t={t:6.2f} idle (nothing being pulled)")
                            return
                        print(f"[sigma1] t={t:6.2f} healthyMax={healthy:8.1f} "
                              f"p99={float(np.percentile(s1, 99)):7.1f} "
                              f"p50={float(np.percentile(s1, 50)):6.1f} | "
                              f"rawMax={self.sigma1_max:10.1f} "
                              f"degenerateTris={int(bad.sum())}")
                        # the LOADED REGION: which cells actually carry load right now
                        if healthy > 1e-6:
                            hotm = good & (s1 > STRESS_HOT_FRAC * healthy)
                            nh = int(hotm.sum())
                            if nh:
                                rr = np.linalg.norm(cen[hotm][:, :2], axis=1)
                                print(f"         loaded region: {nh} cells above "
                                      f"{STRESS_HOT_FRAC:.0%} of peak, r={rr.min():.2f}..{rr.max():.2f}")
                        # per-cell: how hard, and WHICH WAY the crack would run.
                        # sigma1 direction vs the RADIAL direction is what decides whether
                        # the tear stays curvilinear or runs away to the periphery.
                        for k in order[:STRESS_TABLE_N]:
                            c = cen[k]
                            rad = c[:2]
                            rn = float(np.linalg.norm(rad))
                            if rn > 1e-9 and not bad[k]:
                                rad = rad / rn
                                d2 = sdir[k][:2]
                                dn = float(np.linalg.norm(d2))
                                if dn > 1e-9:
                                    ang = np.degrees(np.arccos(
                                        min(1.0, abs(float(np.dot(d2 / dn, rad))))))
                                else:
                                    ang = float('nan')
                            else:
                                ang = float('nan')
                            # crack runs PERPENDICULAR to sigma1
                            if ang != ang:
                                crack = "?"
                            elif ang < 30:
                                crack = "CIRCUMFERENTIAL (good, curvilinear)"
                            elif ang > 60:
                                crack = "RADIAL (runs to the periphery!)"
                            else:
                                crack = "oblique"
                            flag = "  <-- DEGENERATE, sigma1 is garbage" if bad[k] else ""
                            print(f"         tri {int(k):5d} sigma1={s1[k]:9.1f} "
                                  f"areaRatio={aratio[k]:5.2f} r={rn:5.2f} "
                                  f"z={float(c[2]):5.2f} sigma1_vs_radial={ang:5.1f}deg "
                                  f"-> crack {crack}{flag}")

            # Automatic plasticity (every PLASTIC_EVERY steps): already-peeled nodes
            # slowly adopt their current shape as their rest shape, so letting go
            # barely springs back; glued nodes keep their rest on the lens.
            if (not self.frozen and self.plastic_rate > 0.0
                    and self.step % PLASTIC_EVERY == 0 and self.adhered is not None):
                free = np.setdiff1d(np.arange(len(pos)),
                                    np.fromiter(self.adhered, dtype=int)
                                    if self.adhered else np.empty(0, dtype=int),
                                    assume_unique=False)
                # Health guard: never let creep bake an unhealthy (spiked/flattened)
                # triangle into the rest shape -- that would make the damage permanent.
                # Nodes touching a triangle outside DEGEN_LO..DEGEN_HI skip this update.
                if free.size and self.tri_idx is None:
                    self._build_tri_areas()
                if free.size and self.tri_idx is not None and len(self.tri_idx):
                    tI = self.tri_idx
                    ca = 0.5 * np.linalg.norm(
                        np.cross(pos[tI[:, 1]] - pos[tI[:, 0]],
                                 pos[tI[:, 2]] - pos[tI[:, 0]]), axis=1)
                    ratio = ca / np.maximum(self.tri_rest_area, 1e-12)
                    sick = (ratio < DEGEN_LO) | (ratio > DEGEN_HI)
                    if sick.any():
                        unsafe = np.unique(tI[sick].ravel())
                        free = np.setdiff1d(free, unsafe, assume_unique=False)
                if free.size:
                    newrest = np.array(rest, copy=True)
                    newrest[free] += self.plastic_rate * (pos[free] - rest[free])
                    self.mo.rest_position.value = newrest
                    # Re-bake ONLY the bending rest (folds become permanent). NOT
                    # springs.reinit(): edge rest lengths stay original, otherwise
                    # plastic flow has no yield and the membrane permanently grows.
                    self.bending.reinit()

            if SCRIPTED_PULL and FREEZE_T is not None and not self.frozen and t >= FREEZE_T:
                self._freeze(f"t={t:.2f}s auto")

    return _C(name="CapAdhesionController")


def createScene(root):
    import Sofa

    root.gravity = [0.0, 0.0, GRAVITY_Z]
    # dt = 0.02 on purpose: implicit Euler's numerical dissipation scales with dt,
    # so a SMALLER step is measurably MORE explosive under a hard yank. Keep it.
    root.dt = float(os.environ.get("CAP_DT", "0.02"))
    # one collapsible node for the ~20 RequiredPlugin entries (GUI tidiness)
    _plugins = root.addChild("RequiredPlugins")
    for name in PLUGINS:
        _plugins.addObject("RequiredPlugin", name=name)

    root.addObject("VisualStyle",
                   displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    # Steep camera angle = stable picking (a grazing ray skims across the flat lens
    # and the grab "runs around"). computeZClip=False + pinned zNear/zFar: clip
    # planes derived from the scene bbox break zoom the moment one stray vertex
    # inflates the bbox ("mesh vanishes when zooming in").
    _camera = root.addObject("InteractiveCamera", position=[8.0, -8.0, 9.0], lookAt=[0, 0, 0],
                   activated=not LOCK_CAMERA,
                   computeZClip=False, zNear=0.3, zFar=500.0)

    if ENABLE_MOUSE:
        # Collision funnel, coarse -> fine: BroadPhase overlaps AABBs (cheap cull),
        # NarrowPhase walks BVH trees down to close triangle pairs, Intersection
        # runs exact distance tests (alarm = start tracking, contact = target
        # separation), Response turns each contact into a penalty force. With
        # selfCollision off and the lens visual-only, the funnel is normally
        # EMPTY -- its real job here is serving the Shift+drag ray-pick below.
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=ALARM_DISTANCE,
                       contactDistance=CONTACT_DISTANCE)
        # Shift+left-drag = ray-pick the nearest collision triangle (only the
        # membrane has one), then a spring of this stiffness to a virtual mouse
        # particle that moves in the screen plane. arrowSize draws the spring.
        _mouse = root.addObject("AttachBodyButtonSetting", stiffness=MOUSE_STIFFNESS,
                                arrowSize=0.3)

    # The lens: VISUAL ONLY (no MechanicalObject -> unpickable, no contact). Its
    # solidity comes from the EllipsoidForceField in the Cap node; the membrane lies
    # flush because both meshes sample the same analytic surface.
    ball = root.addChild("Lens")
    ball.addObject("MeshOBJLoader", name="bloader", filename=LENS_OBJ)
    ball.addObject("OglModel", name="lensVisual", src="@bloader",
                   color=[0.45, 0.55, 0.75, 0.45])

    # The CAP membrane.
    root.addObject("MeshOBJLoader", name="loader", filename=CAP_OBJ)

    cap = root.addChild("Cap")
    # Implicit (backward) Euler: every step solves
    #     [(1+h*rM)*M - h*(B + rK*K) - h^2*K] * dv  =  h*f(x,v) + h^2*K*v
    # where K = df/dx and B = df/dv are summed over ALL force fields below (FEM or
    # springs alike -- the integrator is mode-agnostic). Stiffness sits inside the
    # matrix, so any k is stable at any dt; explicit would need w*dt < 2 and this
    # mesh runs at w*dt ~ 9-16. Rayleigh terms = uniform numerical damping (rK*K
    # kills high-frequency mesh modes, rM*M calms drift).
    # rayleighStiffness damps HIGH-FREQUENCY modes specifically -- the ones this mesh cannot
    # resolve. With EDGE_STIFFNESS 2500 and massDensity 1, omega = sqrt(k/m) = 50 rad/s, a
    # period of 0.126 s, which at dt=0.02 is only 6.3 STEPS PER PERIOD. Implicit Euler is
    # unconditionally STABLE there but not SMOOTH: anything that disturbs the sheet -- a tear
    # split, an adhesion release, a jerk of the hand -- rings at close to the step rate and
    # reads as buzz. That is the "everything shakes" report, and it is not something SOFA does
    # to us; it is this k/m/dt combination.
    # RAISED 0.2 -> 1.0. Measured on an identical jerky 900-step pull, twice, bit-identical
    # both times: displacement clamps 14401 -> 8011, speed clamps 3525 -> 1755, and runaway
    # REWINDS 29 -> 1. Those clamps ARE the visible jitter -- 14401 over 900 steps is sixteen
    # nodes teleported every single step, which is a safety net that has stopped being a net
    # and become part of the dynamics. And it costs nothing elsewhere: the tear got LONGER
    # (111 -> 144 vertices) and the flap lifted higher (3.62 -> 6.57), because the solver
    # spends its budget on the pull instead of on modes it cannot represent.
    # Do NOT go to 2.0: measured there, the run collapses into 500 rewinds and freezes
    # (speed p99 0.0, lift 1.15). 1.5 tears more still (234, lift 10.63) but sits next to that
    # cliff at 5.1% degenerate elements, so 1.0 is the shipped value.
    # Env-tunable for measured sweeps: CAP_RAYLEIGH_K / CAP_RAYLEIGH_M / CAP_DT.
    cap.addObject("EulerImplicitSolver",
                  rayleighStiffness=float(os.environ.get("CAP_RAYLEIGH_K", "1.0")),
                  rayleighMass=float(os.environ.get("CAP_RAYLEIGH_M", "0.2")))
    # CG solves that system MATRIX-FREE: each iteration asks for one product
    # (M - h*B - h^2*K)*p, computed by a scene traversal (addMdx + addDForce) --
    # the matrix is never assembled. 30 iterations suffice at this condition
    # number (~1 + h^2*w^2, up to ~250); tolerance = relative-residual stop,
    # threshold = tiny-denominator guard.
    cap.addObject("CGLinearSolver", iterations=30, tolerance=1e-8, threshold=1e-8)

    topo = cap.addObject("TriangleSetTopologyContainer", name="topo", src="@../loader")
    cap.addObject("TriangleSetTopologyModifier")

    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    # Open the mesh through the OFFICIAL topology API when the Capsulorhexis plugin is
    # loadable. Writing topo.triangles directly leaves the container's edge list stale, and
    # those stale edges become springs stapling the cut shut (docs 4.24). The API is only
    # reachable from C++, hence the plugin; without it the scene falls back to the direct
    # write and simply behaves as before.
    splitter = None
    if TOPO_API:
        try:
            root.addObject("RequiredPlugin", name="Capsulorhexis")
            splitter = cap.addObject("TopologySplitEngine", name="Splitter")
            print("[Topology] official API in use (TopologySplitEngine); "
                  "edges stay consistent across splits")
        except Exception as e:  # noqa: BLE001
            splitter = None
            print(f"[Topology] Capsulorhexis plugin unavailable ({str(e)[:60]}); "
                  f"falling back to direct topology writes")

    mo = cap.addObject("MechanicalObject", name="Mo", src="@../loader")
    cap.addObject("DiagonalMass",
                  massDensity=float(os.environ.get("CAP_MASS", "1.0")))

    # FEM only when USE_MASS_SPRING is off. Optim variant: bakes 1/area from the
    # REST mesh (no divide-by-zero on a collapsed current triangle) and takes
    # youngModulus as a scalar.
    fem = None
    if PAPER_MODE:
        # The paper's own material: transversely isotropic triangular FEM, co-rotational
        # ("large"), with the fibres running CONCENTRICALLY around the lens axis --
        # fiberCenter gives exactly that, so the fibre field needs no custom code.
        fem = cap.addObject("TriangularAnisotropicFEMForceField", name="FEM", method="large",
                            youngModulus=PAPER_E_FIBER,
                            transverseYoungModulus=PAPER_E_TRANSVERSE,
                            poissonRatio=PAPER_POISSON,
                            fiberCenter=[[0.0, 0.0, G.Z0]])
        print(f"[Paper] INRIA mode: transversely isotropic FEM, concentric fibres "
              f"(E_fiber={PAPER_E_FIBER:g}, E_transverse={PAPER_E_TRANSVERSE:g}, "
              f"nu={PAPER_POISSON:g}); NO adhesion, NO peeling -- the capsule is held only "
              f"at the zonular rim, exactly as in Dequidt 2013 / Marchal 2009.")
    elif not USE_MASS_SPRING:
        fem = cap.addObject("TriangularFEMForceFieldOptim", name="FEM", method="large",
                            youngModulus=CLOTH_YOUNG, poissonRatio=0.3)
        # SOFA's OWN principal-stress calc + vectors: an INDEPENDENT method to compare with
        # our geometric observer. computePrincipalStress turns it on; showStressVector draws
        # a per-triangle line along the FEM's principal-stress direction (so you get
        # direction, in 3D on the deforming mesh). Enable with CAP_FEM_STRESS_VIZ=1 (FEM
        # mode only). This is the true cross-check: same physics, two different stress
        # computations -- the hot regions and directions should agree.
        if os.environ.get("CAP_FEM_STRESS_VIZ", "0") == "1":
            fem.computePrincipalStress.value = True
            fem.showStressVector.value = True
    springs = cap.addObject("MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    bending = cap.addObject("TriangularBendingSprings", name="Bending",
                            stiffness=BEND_STIFFNESS)
    _damper = cap.addObject("UniformVelocityDampingForceField",
                            dampingCoefficient=DAMPING, implicit=DAMPING_IMPLICIT)

    # lens solidity: analytic ellipsoid repulsion (same A/C/Z0 as the lens surface)
    cap.addObject("EllipsoidForceField", name="LensObstacle",
                  center=[0.0, 0.0, G.Z0], vradius=[G.A, G.A, G.C],
                  stiffness=LENS_REPULSION, damping=1.0)

    # adhesion: springs holding every node to its spot on the lens. With ADH_TANGENTIAL the
    # anchors live in their own child node (no solver, no dynamics of their own) and the
    # controller slides them along the surface normal each step, which removes the normal
    # component of the spring force -- see ADH_TANGENTIAL.
    if PAPER_MODE:
        # No bond to the lens: the papers have none. The capsule is held only by the zonular
        # rim (FIX_OUTER_RIM below), and the lens stays as a one-sided obstacle so the membrane
        # cannot pass through it -- an obstacle only ever pushes, so it adds no hidden hold.
        anchor_mo = None
        adhesion = None
    elif ADH_TANGENTIAL:
        anchors = cap.addChild("AdhAnchors")
        anchor_mo = anchors.addObject("MechanicalObject", name="AdhAnchor", template="Vec3d",
                                      position=list(mo.rest_position.value))
        adhesion = cap.addObject("RestShapeSpringsForceField", name="Adhesion",
                                 stiffness=ADHESION_STIFF, drawSpring=False,
                                 external_rest_shape=anchor_mo.getLinkPath())
    else:
        anchor_mo = None
        adhesion = cap.addObject("RestShapeSpringsForceField", name="Adhesion",
                                 stiffness=ADHESION_STIFF, drawSpring=False)

    # Stitch springs hold the pre-slit tear circle closed (coincident vertex pairs,
    # rest length 0), angle-sorted so a scripted tear can run around progressively.
    import math as _math
    _pairs = G.stitch_pairs()
    _capV = None
    try:
        _capV = [ln.split()[1:4] for ln in open(CAP_OBJ) if ln.startswith("v ")]
    except Exception:  # noqa: BLE001
        pass
    if _capV is not None:
        def _ang(pr):
            x, y = float(_capV[pr[0]][0]), float(_capV[pr[0]][1])
            return _math.atan2(y, x)
        _pairs = sorted(_pairs, key=_ang)
    # Built via indices1/indices2 (the 'spring' Data is unbindable from Python);
    # a stitch is broken by flipping its 'enabled' flag.
    stitch = cap.addObject("SpringForceField", name="Stitch",
                           indices1=[int(a) for a, b in _pairs],
                           indices2=[int(b) for a, b in _pairs],
                           stiffness=[STITCH_K], damping=[1.0], showArrowSize=0.0)
    central = set(int(i) for i in G.central_indices())

    # Optional rim anchor (anatomically: zonular fibers). Off by default so the rim
    # itself can be grabbed, lifted and folded.
    if FIX_OUTER_RIM and _capV is not None:
        import math as _m2
        _outer = [i for i, xyz in enumerate(_capV)
                  if _m2.hypot(float(xyz[0]), float(xyz[1])) > RIM_ANCHOR_FRAC * G.R]
        if _outer:
            cap.addObject("FixedProjectiveConstraint", name="RimAnchor", indices=_outer,
                          showObject=False)
            print(f"[Zonules] rim anchored: {len(_outer)} nodes beyond r="
                  f"{RIM_ANCHOR_FRAC * G.R:.2f} of {G.R:.2f}")

    # Scripted lift of the freed central disc; must start only AFTER the circle is
    # fully torn (intact stitches at k=2500 would drag the rim up with it).
    lift = None
    if SCRIPTED_TEAR:
        cap.addObject("BoxROI", name="poleBox", box=[-1.0, -1.0, -1.0, 1.0, 1.0, 3.0],
                      drawBoxes=False)
        _t1 = TEAR_T + TEAR_DURATION + 0.3      # lift starts here
        lift = cap.addObject("LinearMovementProjectiveConstraint", name="lift",
                             indices="@poleBox.indices",
                             keyTimes=[0.0, _t1, _t1 + 3.0, 60.0],
                             movements=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                                        [0.0, 0.0, LIFT_HEIGHT], [0.0, 0.0, LIFT_HEIGHT]])

    # Peak-stress marker: a bare MechanicalObject drawn as spheres (nothing that can
    # crash the GUI); the controller moves it onto the hottest triangle.
    _probe = None
    if STRESS_MARKER:
        _pn = root.addChild("StressProbe")
        _probe = _pn.addObject("MechanicalObject", name="probe",
                               position=[[0, 0, 0]] * (STRESS_TOP_N + 2),
                               showObject=True, showObjectScale=0.25, drawMode=1,
                               showColor=[1.0, 0.15, 0.05, 1.0])

    pull = None
    if SCRIPTED_PULL:
        # scripted grab: lift the +x rim arc up/out to peel
        cap.addObject("BoxROI", name="grabRim",
                      box=[G.R - 0.9, -1.2, -0.5, G.R + 0.5, 1.2, 0.6],
                      drawBoxes=False)
        pull = cap.addObject("LinearMovementProjectiveConstraint", name="pull",
                             indices="@grabRim.indices",
                             keyTimes=[0.0, SWITCH_T, PULL_END_T, 60.0],
                             movements=[[0.0, 0.0, 0.0],
                                        [0.0, 0.0, 0.0],
                                        PULL_MOVE, PULL_MOVE])

    if ENABLE_MOUSE:
        # collision shell: what the mouse ray picks (and self-collision, if enabled)
        cap.addObject("TriangleCollisionModel", selfCollision=SELF_COLLISION,
                      contactStiffness=CONTACT_STIFFNESS)

    _display = None
    if STRESS_COLOR:
        # SOFA's OWN per-triangle sigma1 heatmap, colouring the DEFORMING 3D mesh. Placed in
        # a CHILD node with an IdentityMapping (the pattern from SOFA's own DataDisplay.scn /
        # AreaMapping.scn) -- adding DataDisplay directly to the Cap node clashed with its
        # MechanicalObject ("only one BaseState per node", behavior undefined). The
        # controller writes StressView.triangleData each step; OglColorMap auto-ranges off
        # the DataDisplay's currentMin/currentMax. Crashes the imgui GUI -> use qt/glfw.
        scv = cap.addChild("StressColor")
        scv.addObject("VisualStyle", displayFlags="hideWireframe")
        _display = scv.addObject("DataDisplay", name="StressView", maximalRange=False)
        scv.addObject("OglColorMap", name="StressMap", colorScheme="HSV", showLegend=True,
                      legendTitle="sigma1",
                      min="@StressView.currentMin", max="@StressView.currentMax")
        scv.addObject("IdentityMapping", input="@../Mo", output="@StressView")
    else:
        # The membrane's normal deformation view -- UNCHANGED by the stress UI, which
        # publishes over HTTP instead of drawing anything into this scene.
        visu = cap.addChild("Visual")
        visu.addObject("OglModel", name="visual", color=[0.92, 0.90, 0.82, 1.0])
        visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

    # Decoupled stress UI: publish the STATIC reference disc (rest-shape xy + triangles)
    # once, then start the local server the browser page polls. Physics/rendering above
    # are untouched. Geometry is taken from cap.obj so it needs no live SOFA state.
    if STRESS_UI:
        # A scene reset ENDS the current recording and starts a new SESSION -- SofaImGui's
        # "reload scene" re-runs createScene in the same process, so each reload is one pull
        # take. The finished frames are archived (not discarded) so the browser can choose
        # which take to replay; the live counter restarts at 0, which the page detects.
        global _STRESS_GEOMETRY, _STRESS_HISTORY, _STRESS_TOTAL, _STRESS_LOG_FH, _STRESS_LATEST
        global _STRESS_SESSIONS, _STRESS_SESSION_ID
        if _STRESS_HISTORY:
            try:
                _t0 = _json.loads(_STRESS_HISTORY[0]).get("t", 0.0)
                _t1 = _json.loads(_STRESS_HISTORY[-1]).get("t", 0.0)
            except Exception:  # noqa: BLE001
                _t0 = _t1 = 0.0
            _STRESS_SESSIONS.append({"id": _STRESS_SESSION_ID, "frames": list(_STRESS_HISTORY),
                                     "t0": _t0, "t1": _t1})
            # keep memory bounded: a session is up to STRESS_HISTORY frames of ~4000 floats
            while len(_STRESS_SESSIONS) > STRESS_SESSIONS_MAX:
                _STRESS_SESSIONS.pop(0)
            print(f"[StressUI] session {_STRESS_SESSION_ID} archived: "
                  f"{len(_STRESS_HISTORY)} frames, t {_t0:.2f}..{_t1:.2f}s "
                  f"(pick it in the browser's take selector)")
        _STRESS_SESSION_ID += 1
        _STRESS_HISTORY.clear()
        _STRESS_TOTAL = 0
        _STRESS_LATEST = "{}"
        if _STRESS_LOG_FH is not None:
            try:
                _STRESS_LOG_FH.close()
            except Exception:  # noqa: BLE001
                pass
            _STRESS_LOG_FH = None
        _verts, _tris = [], []
        for _ln in open(CAP_OBJ):
            if _ln.startswith("v "):
                _p = _ln.split()[1:4]
                _verts.append([round(float(_p[0]), 4), round(float(_p[1]), 4)])
            elif _ln.startswith("f "):
                _idx = [int(tok.split("/")[0]) - 1 for tok in _ln.split()[1:4]]
                _tris.append(_idx)
        _publish_geometry(_verts, _tris)      # versioned; republished after every tear split
        _start_stress_server(STRESS_UI_PORT, STRESS_UI_OPEN)

    # Say plainly whether the mesh can tear. Running -Heatmap without -Tear looks exactly
    # like broken tearing (the membrane just deforms), so do not leave it implicit.
    if CAP_TEAR:
        print(f"[Tear] ENABLED: sigma_bar_T={TEAR_THRESH:g} fiberRatio={TEAR_FIB_RATIO:g} "
              f"alpha={TEAR_FIB_ALPHA:g} turn<={TEAR_TURN_MAX:g}deg")
    else:
        print("[Tear] DISABLED -- the mesh will only DEFORM, it cannot tear.\n"
              "       Add -Tear to the launcher (e.g. run_cap.ps1 -Tear -Heatmap) "
              "or set CAP_TEAR=1.")

    cap.addObject(_make_controller(fem, springs, bending, mo, adhesion, pull,
                                   _mouse, _damper, topo, _display, _camera, root,
                                   _probe, stitch, central, lift,
                                   anchor_mo=anchor_mo, splitter=splitter))



    print(f"""
+===========================================================================+
| Shift + LEFT-DRAG = pull the membrane. Drag ACROSS (not just up) to fold   |
| it over; a near-top-down view makes the drag parallel to the membrane.     |
| Drag distance = pull force, so do not drag the cursor miles away.          |
+--- TUNE LIVE in the GUI: click the component, type, then PRESS ENTER ------+
|  Cap > Bending > stiffness          fold: small=floppy/creases  big=rigid  |
|                                     (now {BEND_STIFFNESS:g}; try 15 / 30 / 50)         |
|  Cap > Adhesion > stiffness         how strongly it sticks to the lens     |
|  Cap > UniformVelocityDam..> dampingCoefficient   viscosity                |
|  AttachBodyButtonSetting > stiffness              mouse pull strength      |
|  (ENTER is required -- ImGui does not commit the number until you do.)     |
+--- EDIT THE FILE (these are not SOFA Data, so the GUI cannot show them) ---+
|  cap_membrane.py : PLASTIC_RATE={PLASTIC_RATE:g}  BREAK_FORCE={BREAK_FORCE:g}  MAX_SPEED={MAX_SPEED:g}          |
|  generate_cap.py : C={G.C:g} (flatness)  CAP_ANGLE_DEG={G.CAP_ANGLE_DEG:g} (coverage)         |
|                    A={G.A:g} (size)  TARGET_EDGE={G.TARGET_EDGE:g} (mesh resolution)      |
|                    -> re-run run_cap.ps1; it regenerates the meshes.       |
+---------------------------------------------------------------------------+
| NOTE: keyboard shortcuts do NOT work here -- SofaImGui swallows the        |
| keyboard (KeypressedEvent is in SofaGLFW.dll but not SofaImGui.dll).       |
| Use the Data fields above instead.                                         |
+===========================================================================+""")
    return root


def main():
    import Sofa
    import Sofa.Gui
    import SofaRuntime
    SofaRuntime.importPlugin("Sofa.Component")
    SofaRuntime.importPlugin("Sofa.GL.Component.Rendering3D")
    SofaRuntime.importPlugin("SofaImGui")

    root = Sofa.Core.Node("root")
    createScene(root)
    Sofa.Simulation.init(root)
    Sofa.Gui.GUIManager.Init("cap_membrane", "imgui")
    Sofa.Gui.GUIManager.createGUI(root, __file__)
    Sofa.Gui.GUIManager.SetDimension(1000, 760)
    Sofa.Gui.GUIManager.MainLoop(root)
    Sofa.Gui.GUIManager.closeGUI()


try:
    import Sofa  # noqa: F401
except Exception:  # noqa: BLE001
    pass

if __name__ == "__main__":
    main()
