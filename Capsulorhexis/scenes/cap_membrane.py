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
TEAR_TURN_MAX = float(os.environ.get("CAP_TEAR_TURN", "70"))     # theta_P, max turn per advance
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
# _reach_drive). A load this far from the tip counts half.
TEAR_REACH = float(os.environ.get("CAP_TEAR_REACH", "3.0"))
# How many of the strongest weighted elements the drive averages. 1 = raw max,
# which lets a single near-degenerate triangle (~100x the bulk) drive the tear.
TEAR_DRIVE_TOPK = int(os.environ.get("CAP_TEAR_TOPK", "8"))
# How many of the most recent crack vertices are off-limits to the advancing tip.
# Only the tail: the tear must be able to reach its own START to close the circle.
TEAR_NOBACK = int(os.environ.get("CAP_TEAR_NOBACK", "8"))
# Minimum crack length before reaching the seed counts as the rhexis closing,
# so the tear cannot "complete" a few edges after it starts.
TEAR_CLOSE_MIN = int(os.environ.get("CAP_TEAR_CLOSEMIN", "40"))
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
TEAR_DEGEN_MAX = float(os.environ.get("CAP_TEAR_DEGEN_MAX", "0.04"))

# --- material ----------------------------------------------------------------
CLOTH_YOUNG = 120.0       # FEM-only: soft opening phase
PAPER_YOUNG = 1200.0      # FEM-only: stiffened at SWITCH_T; 4000+ risks blow-up
SWITCH_T = 1.0            # [s] cloth -> paper transition
EDGE_STIFFNESS = 2500.0   # per-edge in-plane stiffness = THE membrane stiffness in
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
DISP_CLAMP = 0.5

# Diagnostics: one CSV row per step (peaks + safety-net counters), overwritten each
# run; pair with run_last.log (console tee in run_cap.sh) to analyse a session.
LOG_DIAG = True
DIAG_PATH = os.path.join(_HERE, "diag_last.csv")

# Bending stiffness = "does the lifted flap flop over, or stand up stiff?"
# smaller -> floppy drape; bigger -> stiff wide curve. In-plane softness is a
# different knob (EDGE_STIFFNESS / PAPER_YOUNG).
BEND_STIFFNESS = 15.0

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
BREAK_FORCE = 60.0        # pull force at which a spot peels off
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
# Freeze-orbit-while-grabbing: both object-count-based grab detectors failed
# (SofaImGui keeps adding graph objects, so any count baseline goes stale and the
# camera locks forever). Needs a name-based detector (see CAM_PROBE); off until then.
FREEZE_CAMERA_WHILE_PULLING = False
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
                         # frame (the cap lives within ~15 even fully lifted). 0 = off
# Strain clamp: no edge may stretch past MAX_STRETCH x its rest length -- the
# membrane is inextensible-ish, and without this an adhesion avalanche lets
# triangles inflate 8-33x and invert. Projected back per step, Gauss-Seidel style.
MAX_STRETCH = 1.6        # 0 = off
STRAIN_ITERS = 3         # relaxation passes per step
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
        "crack": list(_TEAR_PATH["path"]),   # ordered vertex chain = the cut edges
        "lips": list(_TEAR_PATH["lips"]),    # [duplicate, original] split pairs
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
_TEAR_STATE = {"on": False, "len": 0, "c": 0.0, "thr": 0.0, "tipr": 0.0, "why": "off"}
# The crack itself, for the browser to DRAW rather than just count. A tear is a CHAIN OF
# MESH EDGES: "path" is the ordered vertex list, so consecutive entries are the edges the
# tear has cut, and the last entry is the live tip. "lips" pairs each duplicated vertex with
# the original it was split from -- the two sides of the cut, whose separation is the crack
# opening. Both index the CURRENT reference disc, so they are only meaningful together with
# the frame's "gver".
_TEAR_PATH = {"path": [], "lips": []}


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
                # ONE FILE PER TAKE: stress_log_<session>.jsonl, so a reset never overwrites
                # the pull you wanted to analyse. stress_log.jsonl stays as a copy of the
                # newest take for the existing tools/docs that reference that name.
                if _STRESS_SESSION_ID > 0:
                    path = STRESS_LOG_PATH.replace(".jsonl", f"_{_STRESS_SESSION_ID}.jsonl")
                else:
                    path = STRESS_LOG_PATH
                    if os.path.exists(path):
                        try:
                            os.replace(path, path + ".prev")
                        except OSError:
                            pass
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
                    self._send(_json.dumps({"sessions": out}).encode(), "application/json")
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
                     topo, display, camera, root, probe, stitch, central, lift):
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
            self.rest0 = None          # PRISTINE rest shape for the reference disc. NOT
                                       # rest_position: plasticity creeps that toward the
                                       # deformed shape, which was warping the "undeformed"
                                       # map in the browser. Grows with duplicates only.
            self.crack = None          # vertex path of the tear; last entry is the live tip
            self.closed = False        # True once the tear has met its own path
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
            # Grab detector via graph-object count above the resting minimum.
            # Unreliable under SofaImGui (see FREEZE_CAMERA_WHILE_PULLING); kept for
            # a future name-based version.
            n = self._count_objs()
            if self.rest_objs is None or n < self.rest_objs:
                self.rest_objs = n
            return n > self.rest_objs

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
            """vertex -> triangles map, and the neighbour map, for the current topology."""
            T = np.array(self.topo.triangles.value)
            n = len(self.mo.position.value)
            self.vtris = [[] for _ in range(n)]
            nbr = [set() for _ in range(n)]
            from collections import Counter
            ecount = Counter()
            for ti, (a, b, c) in enumerate(T.tolist()):
                for v in (a, b, c):
                    self.vtris[v].append(ti)
                nbr[a].update((b, c)); nbr[b].update((a, c)); nbr[c].update((a, b))
                for u, w in ((a, b), (b, c), (c, a)):
                    ecount[(u, w) if u < w else (w, u)] += 1
            self.nbr = [np.fromiter(x, dtype=int) for x in nbr]
            # boundary must be rebuilt together with nbr: the peel logic guards only on
            # self.nbr, so leaving boundary stale/None here made it fail with a TypeError
            # on every step after the first split.
            self.boundary = {u for (u, w), k in ecount.items() if k == 1} | \
                            {w for (u, w), k in ecount.items() if k == 1}
            self.tris = T

        def _rest_now(self):
            """rest_position as an array, cached per step: it is read several times per
            advance and the SOFA Data -> numpy conversion is not free."""
            if (self._rest_cache is None or self._rest_cache[0] != self.step
                    or len(self._rest_cache[1]) != len(self.mo.position.value)):
                self._rest_cache = (self.step, np.array(self.mo.rest_position.value))
            return self._rest_cache[1]

        def _field_now(self, P):
            """Whole-mesh stress field for this step, solved once and reused. _reach_drive
            needs the FULL field (its kernel has no cutoff), and it runs once per advance with
            up to TEAR_MAX_ADVANCE advances per opportunity -- so without this the same solve
            would repeat several times over identical positions. The key includes both array
            lengths, so a vertex split invalidates it automatically."""
            key = (self.step, len(P), len(self.tris))
            if self._field_cache is None or self._field_cache[0] != key:
                E_obs, nu_obs = self._stress_material()
                s1, _s2, _sd, ar = principal_stress(P, self._rest_now(), self.tris,
                                                    E=E_obs, nu=nu_obs)
                cen = P[self.tris][:, :, :2].mean(axis=1)
                self._field_cache = (key, s1, ar, cen)
            return self._field_cache[1], self._field_cache[2], self._field_cache[3]

        def _reach_drive(self, P, x, y):
            """Load delivered to the crack tip from anywhere on the sheet, attenuated by
            distance. This kernel is the single biggest lever on how the tear FEELS.

            It used to be a HARD CUTOFF: elements within TEAR_REACH=2.5 counted with a linear
            falloff to zero, everything beyond counted for nothing. That one line was what made
            the capsule feel untearable. Measured with a faithful mouse spring (k=600 on ONE
            node, the way AttachBodyButtonSetting actually pulls) while varying grab-to-tip
            distance: the FIELD barely changed (p98 325 -> 149, about 2x) but the drive
            collapsed from 2407 to 25 and the tear from 223 crack vertices to 13. A pull 4
            units from the tip is a perfectly hard pull that simply never arrived. Widening the
            reach to 8 on the same pull took the drive 25 -> 2199 and the tear 13 -> 87.
            Ruled out in the same sweep: the anchored rim, which is innocent (unanchoring
            moved 13 -> 14).

            So there is no cutoff now. Load in a thin sheet spreads with distance instead of
            stopping at a radius, so the weight is 1/(1+(d/lambda)^2) and TEAR_REACH is that
            decay LENGTH. Grabbing near the tip is still much more effective -- it just no
            longer goes to exactly zero a third of the way across the disc.

            Robust peak rather than the raw max: isolated near-degenerate elements reach ~100x
            the bulk (the same reason the heatmap's colour ramp uses p98), and with no cutoff
            the max would let one bad triangle anywhere drive the whole tear. Averaging the
            TEAR_DRIVE_TOPK largest weighted values keeps it a peak detector that no single
            element can carry."""
            if self.tris is None or not len(self.tris):
                return None
            s1, ar, cen = self._field_now(P)
            keep = (ar >= DEGEN_LO) & (ar <= DEGEN_HI)
            if not keep.any():
                return None
            d = np.hypot(cen[keep, 0] - x, cen[keep, 1] - y)
            v = s1[keep] / (1.0 + (d / max(TEAR_REACH, 1e-9)) ** 2)
            k = int(min(max(TEAR_DRIVE_TOPK, 1), v.size))
            return float(np.mean(np.partition(v, -k)[-k:]))

        def _tip_stress(self, P, x, y, radius=None):
            """Crack-tip neighbourhood average (Dequidt section 4.3), returned as principal
            values + angle. Averaging the TENSOR COMPONENTS, not the principal values: the
            neighbours have different principal axes, so averaging s1/s2 would invent
            anisotropy (two states 90 deg apart average to isotropic, not to the larger)."""
            if self.tris is None or not len(self.tris):
                return None
            rad = TEAR_TIP_RADIUS if radius is None else radius
            cen = P[self.tris][:, :, :2].mean(axis=1)
            d2 = (cen[:, 0] - x) ** 2 + (cen[:, 1] - y) ** 2
            m = np.flatnonzero(d2 <= rad ** 2)
            if not m.size:
                return None
            # Select FIRST, then solve. This used to run principal_stress over all ~4166
            # triangles and throw away everything outside the disc -- twice per advance, in a
            # loop -- which was the bulk of the tearing cost in the GUI. The neighbourhood is
            # typically a few dozen elements.
            E_obs, nu_obs = self._stress_material()
            s1, s2, sdir, ar = principal_stress(P, self._rest_now(), self.tris[m],
                                                E=E_obs, nu=nu_obs)
            keep = (ar >= DEGEN_LO) & (ar <= DEGEN_HI)
            if not keep.any():
                return None
            s1, s2, sdir = s1[keep], s2[keep], sdir[keep]
            th = np.arctan2(sdir[:, 1], sdir[:, 0])
            c, s = np.cos(th), np.sin(th)
            w = 1.0 / (1.0 + np.sqrt(d2[m][keep]) / max(rad, 1e-9))
            ws = w.sum()
            sxx = float((w * (s1 * c * c + s2 * s * s)).sum() / ws)
            syy = float((w * (s1 * s * s + s2 * c * c)).sum() / ws)
            sxy = float((w * ((s1 - s2) * s * c)).sum() / ws)
            mid = 0.5 * (sxx + syy)
            dev = float(np.hypot((sxx - syy) * 0.5, sxy))
            return mid + dev, mid - dev, np.degrees(0.5 * np.arctan2(2 * sxy, sxx - syy))

        def _argmax_c(self, S1, S2, th1_deg, fib_deg, heading):
            """INRIA criterion (Eq.1-4). Returns (c, unit direction) for the crack direction
            that maximises c, restricted to turns within TEAR_TURN_MAX of the heading
            (Eq.2's H term -- this is what stops the tear doubling back on itself)."""
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
            return best, vec(ba)

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
            self.mo.position.value = np.vstack([P, P[v]]).tolist()
            self.mo.rest_position.value = np.vstack([R, R[v]]).tolist()
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
            """Rebuild everything that caches the topology after a split."""
            for comp in (self.springs, self.bending):
                try:
                    comp.reinit()
                except Exception:  # noqa: BLE001
                    pass
            self._push_visual()
            self._build_vtris()
            self.edges = self.edge_rest = None      # strain clamp rebuilds
            self.tri_idx = self.tri_rest_area = None
            self.last_good = self.last_good_rest = None
            self.prev_pos = None
            # Hand the browser the crack itself, not just its length, so the tear can be seen
            # and replayed edge by edge on the timeline.
            _TEAR_PATH["path"] = [int(v) for v in self.crack] if self.crack else []
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
            """Move the tip one edge along self.crack_dir, splitting the vertex left behind."""
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
                return False
            pv = P[tip][:2]
            best, bj = -2.0, -1
            for j in cand:
                e = P[j][:2] - pv
                n = np.linalg.norm(e)
                if n < 1e-9:
                    continue
                dot = float(e @ self.crack_dir / n)
                if dot > best:
                    best, bj = dot, j
            if bj < 0:
                return False
            if not forced and np.degrees(np.arccos(np.clip(best, -1, 1))) > TEAR_TURN_MAX:
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
                S1, S2, th1 = S
                # Coarse-mesh tip correction, plus a wider "reach": if the hand is pulling
                # further away than the tip disc, use the strongest loaded patch within
                # TEAR_REACH to drive the crack. Without this the tear only responds when you
                # grab exactly on the tip, which is not how the flap is held in surgery.
                far = self._reach_drive(P, P[tip][0], P[tip][1])
                if far is not None and far > S1:
                    S1 = far
                S1 *= TEAR_TIP_GAIN
                S2 *= TEAR_TIP_GAIN
                fib = np.degrees(np.arctan2(P[tip][1], P[tip][0])) + 90.0   # concentric fibers
                c, d = self._argmax_c(S1, S2, th1, fib, self.crack_dir)
                _TEAR_STATE.update(on=True, len=len(self.crack), c=round(float(c), 2),
                                   thr=TEAR_THRESH,
                                   tipr=round(float(np.hypot(P[tip][0], P[tip][1])), 2),
                                   why="tearing" if c >= 1.0 else "c<1: pull harder near the tip")
                if c < 1.0:
                    return                                   # not tearing right now
                # Unstable propagation: the further past the criterion, the further the crack
                # runs. Scaled gently (c/4) rather than linearly -- the tip gain and reach can
                # push c into the tens, which at full budget every step shredded the mesh
                # (430 crack vertices in 200 steps) instead of tearing it.
                budget = min(budget, max(1, 1 + int(c / 4.0)))
                self.crack_dir = d
                if not self._advance_to_best_neighbour(P):
                    return
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
            runaway = (MAX_COORD > 0.0 and P0.size > 0
                       and np.isfinite(P0).all() and np.abs(P0).max() > MAX_COORD)
            # A rewind restores a snapshot; after a split the snapshot has the OLD vertex
            # count, so restoring it would undo the tear (and mis-size every array). Only
            # rewind when the snapshot still matches the current mesh.
            if (not np.isfinite(P0).all() or runaway) and (
                    self.last_good is None or len(self.last_good) == len(P0)):
                if runaway and self.step % 15 == 0:
                    print(f"[Runaway] a node passed |coord|>{MAX_COORD:g} "
                          f"(max {float(np.abs(P0).max()):.1f}) -> rewound before it "
                          f"flew off-screen")
                self._rewind()
                return

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
                    if not self.tear_detached and self.adhered is not None:
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
            if self.adhered is None:
                self.adhered = set(range(len(pos)))
                self.adhesion.points.value = sorted(self.adhered)

            # --- diagnostics CSV: one numeric row per step, analysed offline after a
            # session (peaks + safety-net counters; see LOG_DIAG at the top).
            if LOG_DIAG:
                if self.diag is None:
                    # line-buffered, so closing the app mid-session loses no rows
                    self.diag = open(DIAG_PATH, "w", buffering=1)
                    self.diag.write("step,t,maxcoord,maxspeed,maxstretch,maxjump,glued,"
                                    "rewinds,vclamped,dclamped\n")
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
                self.diag.write(f"{self.step},{t:.3f},{float(np.abs(P).max()):.3f},"
                                f"{maxspeed:.3f},{maxstretch:.3f},{self.last_jump:.3f},"
                                f"{len(self.adhered)},{self.rewinds},"
                                f"{self.clamped},{self.disp_clamped}\n")
            if self.adhered and not self.frozen:
                idx = np.fromiter(self.adhered, dtype=int)
                lift = np.linalg.norm(pos[idx] - rest[idx], axis=1)
                sel = np.flatnonzero(lift > self.break_lift)
                cand, cand_lift = idx[sel], lift[sel]
                if PEEL_FRONT_ONLY and cand.size:
                    if self.nbr is None:
                        self._build_peel_adjacency()
                    adh = self.adhered
                    # Only spots at the edge of the still-bonded region may let go:
                    # on the mesh boundary, or with a neighbour already debonded.
                    keep = [k for k, i in enumerate(cand.tolist())
                            if i in self.boundary
                            or any(int(j) not in adh for j in self.nbr[int(i)])]
                    cand, cand_lift = cand[keep], cand_lift[keep]
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
    # rayleighStiffness damps HIGH-FREQUENCY modes specifically (the ones this mesh cannot
    # resolve: omega = sqrt(k/m) ~ 172 rad/s = 1.8 steps per period at dt=0.02), so it is the
    # lever aimed straight at the pull-snap, without the sluggishness of raising global
    # damping. Env-tunable for measured sweeps: CAP_RAYLEIGH_K / CAP_RAYLEIGH_M / CAP_DT.
    cap.addObject("EulerImplicitSolver",
                  rayleighStiffness=float(os.environ.get("CAP_RAYLEIGH_K", "0.2")),
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

    mo = cap.addObject("MechanicalObject", name="Mo", src="@../loader")
    cap.addObject("DiagonalMass",
                  massDensity=float(os.environ.get("CAP_MASS", "1.0")))

    # FEM only when USE_MASS_SPRING is off. Optim variant: bakes 1/area from the
    # REST mesh (no divide-by-zero on a collapsed current triangle) and takes
    # youngModulus as a scalar.
    fem = None
    if not USE_MASS_SPRING:
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

    # adhesion: springs pulling every node to its rest spot on the lens
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
                                   _probe, stitch, central, lift))



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
