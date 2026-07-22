"""Round version of the adhesion-peel demo: a CIRCULAR membrane shaped as a shallow cap,
stuck to an OBLATE (flattened) LENS. Same physics as the flat paper (paper_gel_tear.py).

On opening, NOTHING moves: the membrane just sits stuck to the lens, held by an adhesion
with a force THRESHOLD. Shift + left-drag to pull it:
  - pull gently  -> below the threshold, the adhesion holds and it stays stuck;
  - pull harder  -> the adhesion snaps and that spot peels off and folds UP.
The lens is a solid obstacle (analytic EllipsoidForceField), so the membrane folds up
over it instead of sinking through it.

Springback is handled AUTOMATICALLY (no key press): the already-peeled part slowly
adopts its current shape as its rest shape (viscoplastic creep), so when you let go it
barely springs back. Pressing F is only an optional shortcut to freeze everything at once.

Geometry comes from generate_cap.py, which emits cap.obj (membrane) and lens.obj (the
flattened base) from the SAME analytic ellipsoid, so the membrane lies exactly flush.

Run:  .\scenes\run_cap.ps1     # runSofa -l SofaPython3 -g imgui -a scenes\cap_membrane.py
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
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

# --- membrane in-plane model: FEM vs mass-spring ----------------------------
# USE_MASS_SPRING swaps the in-plane physics from the co-rotational triangle FEM to a pure
# mass-spring membrane (edge springs + bending springs only, NO FEM).
#
# WHY this is the real cure for "pull -> it blows up / disappears": the FEM computes each
# triangle's force by dividing by its area (1/area in the strain-displacement matrix), so a
# triangle driven collinear or inverted by a hard pull produces an infinite/NaN force that
# runs away to 1e150 -- the blow-up no clamp can fully catch because it is born INSIDE the
# solve. A spring's force is just F = k*(length - rest): there is NO area in the denominator,
# so a squashed/inverted triangle can never divide by zero or self-amplify. The mesh may fold
# oddly under an extreme yank, but it physically CANNOT explode.
#
# What you DON'T lose: the tear criterion reads the principal-stress field computed in numpy
# from geometry (rest vs current positions) in principal_stress() -- it never touched the FEM
# -- so it works identically under mass-spring. A triangle with three fixed edge lengths is
# rigid, so edge springs alone already give full in-plane (stretch+shear) stiffness; bending
# springs give the out-of-plane fold. Both components already exist below.
USE_MASS_SPRING = True    # True = drop the FEM, run a pure mass-spring membrane (blow-up-proof)

# --- material presets (same feel as the flat paper) -------------------------
CLOTH_YOUNG = 120.0
PAPER_YOUNG = 1200.0      # do NOT use 4000+ (NaN blow-up risk) -- FEM path only
SWITCH_T = 1.0
EDGE_STIFFNESS = 2500.0   # per-edge -> the membrane does not stretch (in-plane). In mass-
                          # spring mode this ALSO carries all the in-plane stiffness the FEM
                          # used to add, so raise it if the sheet feels too soft.
DAMPING = 2.0

# THE knob for "does the lifted flap flop over, or stand up stiff in the air?"
# = TriangularBendingSprings.stiffness.
#   SMALLER -> floppy: the flap folds over easily and drapes back onto the membrane
#   BIGGER  -> stiff : the flap stands up straight and holds a gentle, wide curve
# (This is NOT in-plane softness -- that is PAPER_YOUNG/EDGE_STIFFNESS.)
# Lowered 600 -> 120 so the flap folds over instead of standing rigid.
BEND_STIFFNESS = 15.0

# Gravity is deliberately 0. Tested as a way to make the lifted flap flop over: it does
# NOT work. Weak gravity (-2..-10) cannot bend the flap at all once plasticity has set
# its shape; gravity strong enough to bend it (-40) also beats the adhesion threshold
# and rips the WHOLE membrane off the lens (glued 865->1, it just falls away). Gravity
# and BREAK_FORCE share the same force budget, so it is the wrong knob. Fold the flap
# over by DRAGGING IT ACROSS with the mouse instead -- plasticity then keeps it folded.
GRAVITY_Z = 0.0

# The lens acts as a solid obstacle so the membrane cannot sink through it: an analytic
# ellipsoid repulsion (cheap + robust, no mesh collision needed). SOFA convention
# (EllipsoidForceField.h): stiffness POSITIVE = repulse OUTWARD, negative = inward.
# Without this the membrane bends down and passes straight through the lens.
# STABILITY CEILING: this is a PENALTY force, so force = stiffness * penetration depth.
# 8000 explodes the membrane on a fast mouse yank (a node gets shoved deep inside for
# one step -> enormous force; measured max|coord| 2402, and bisecting proved this was
# THE cause, not self-collision/creep/solver). 2000 is stable across BEND 3..600 under
# a deliberately violent drag, and still sinks in only ~0.15mm in normal use.
# Do NOT raise this to chase the last 0.1mm of sink-in.
LENS_REPULSION = 2000.0

# --- adhesion of the membrane to the BALL -----------------------------------
ADHESION_STIFF = 120.0
BREAK_FORCE = 60.0        # pull force needed to peel off the ball

# --- how you pull -----------------------------------------------------------
# OFF by default: on opening, the membrane just sits STUCK to the lens and nothing
# moves until YOU pull it. (With this True the scripted rim-lift starts at t=1s and,
# because the GUI runs at hundreds of FPS, the membrane looks like it floats up by
# itself the moment the app opens -- that is not the physics, just the scripted demo.)
SCRIPTED_PULL = False
PULL_END_T = 6.0
PULL_MOVE = [1.5, 0.0, 3.0]   # lift the +x rim up (+z) and outward (+x) to peel

ENABLE_MOUSE = True
# Let the folded flap land ON the membrane below instead of passing through it.
# (Costs some FPS: self-collision is checked every step.)
# TEMPORARILY OFF (2026-07-22): the post-full-peel blow-up to 1e11 coords happens with the
# membrane FREE and IDLE (no FEM, no mouse) -- the only stiff force left that can pump a
# folded free sheet is the self-collision PENALTY (two layers pressed close -> deep-
# penetration penalty -> divergence). Turning it off to confirm it is the source. If the
# blow-up disappears, we re-enable it with a SOFTER/constraint-based contact instead of the
# raw penalty. Trade-off while off: a folded flap passes THROUGH the membrane instead of
# resting on it.
SELF_COLLISION = False
CONTACT_STIFFNESS = 200.0   # penalty contact strength; also silences the SceneCheck warning
# Self-collision proximity MUST stay well BELOW the mesh edge length, or NEIGHBOURING
# triangles fall inside each other's alarm radius and the membrane pushes against itself
# (jitter + wasted contacts; fixing this once took the scene 184 -> 374 steps/s).
# DERIVED from the mesh so that changing generate_cap.TARGET_EDGE can never silently
# break self-collision again.
ALARM_DISTANCE = 0.40 * G.EDGE_LEN
CONTACT_DISTANCE = 0.20 * G.EDGE_LEN

# Mouse-pull strength. The GUI's default attach spring is far too weak to beat the
# adhesion, which is why the membrane felt "拉不動". This spring must be able to lift a
# node past BREAK_FORCE (= ADHESION_STIFF * break lift), so keep it well above that.
# BUT it is also a penalty spring (F = stiffness * how far you drag past the node), so
# too high + a fast drag = the same explosion as LENS_REPULSION=8000 gave. BUT measured:
# a FAST FLICK explodes it at 400, 1000 AND 2000 alike (max|coord| 41 / 77 / 108), and
# raising rayleighStiffness 0.2->0.5 does not save it either. So lowering this does NOT
# buy stability -- it only makes the membrane hard to pull. Keep it pullable at 1000 and
# DRAG SMOOTHLY; a hard flick is a single huge penalty impulse no stiffness value fixes.
# HISTORY: this was 400 in the smooth-feeling 6787996 ("safer mouse pull, less recoil"), then
# reverted to 1000 in c9c9101 because lowering it did not, by itself, stop the blow-up. Back to
# 400 for the low recoil that makes SMOOTH dragging pleasant. Honest caveat: a hard/fast flick
# on this FEM sheet can still diverge (giant-triangle inflation -> coords to millions) at any
# stiffness; the only real cure is swapping FEM for mass-spring, as the tear demos did.
MOUSE_STIFFNESS = 400.0

# --- camera ------------------------------------------------------------------
# SofaGLFW hard-codes "left-drag = orbit the camera", and it is NOT remappable from the
# scene (InteractiveCamera has no button/modifier Data), nor can we intercept Ctrl
# because SofaImGui swallows the keyboard. So to stop the view spinning while you pull,
# lock the camera outright: every left-drag is then purely a pull on the membrane.
# LOCK_CAMERA = True kills orbiting entirely -- too blunt. Instead we FREEZE THE CAMERA
# ONLY WHILE YOU ARE PULLING: when you Shift+drag, SOFA's AttachBodyPerformer inserts its
# interaction spring into the scene graph (BaseAttachBodyPerformer::m_interactionObject),
# so the controller watches for that object appearing and sets InteractiveCamera.activated
# False for as long as the grab lasts, then True again. Result: orbit normally, but the
# view holds still while you pull.
LOCK_CAMERA = False            # True = never allow orbiting at all
# FREEZE_CAMERA_WHILE_PULLING: freeze the orbit ONLY while you are Shift+dragging to pull,
# so the view never spins out from under you mid-pull; released, you orbit normally.
# The old attempt failed because it fixed a baseline object count on the FIRST step -- but
# SofaImGui keeps adding its own persistent objects afterwards, so the count sat permanently
# above that stale baseline and the camera locked forever. Fixed here by tracking the
# self-calibrating RESTING (minimum) object count instead: a Shift+drag adds one transient
# attach object that pushes the live count ABOVE the resting min -> that is the grab signal,
# and it auto-adapts to whatever the GUI's idle object count happens to be. See _is_grabbing.
#
# DISABLED AGAIN (2nd attempt failed): SofaImGui keeps ADDING objects for seconds after
# startup, so the running-min stays pinned at the startup low and every later step reads
# "above min" -> the detector says you are grabbing forever and the camera locks solid.
# Object count -- min, fixed, or otherwise -- is simply not a usable grab signal in this GUI.
# The reliable fix needs to spot the SPECIFIC attach object by name (see the CAM_PROBE
# diagnostic) rather than count anything. Left OFF so the orbit works normally meanwhile.
FREEZE_CAMERA_WHILE_PULLING = False
# Diagnostic: when True, print how the object count changes and (on an increase) the names
# of the objects that appeared. Do ONE Shift+drag with this on, paste the log, and we can
# build a name-based grab detector that actually works. Off in normal use.
CAM_PROBE = False
# Camera keyboard controls (best effort -- SofaImGui may only deliver keys when the 3D
# viewport has focus; if arrows/letters do nothing, click the viewport first, or rely on the
# auto-freeze + mouse orbit). Arrow keys OR W/A/S/D pan the view; R re-centres to the start
# view; V toggles the orbit lock manually.
CAM_PAN_STEP = 1.5             # world units the camera pans per key press

# --- stress field (this is what the tear criterion will be built on) ----------
# We compute the per-triangle principal stress OURSELVES in numpy, because the FEM's own
# stress is unreachable: fem.triangleInfo / fem.vertexInfo are C++ structs that
# SofaPython3 cannot bind ("Invalid type") -- that is exactly why this repo needed a C++
# plugin. Strain is a purely GEOMETRIC quantity (rest vs current), so it does not matter
# which component carries the load, and we need no FEM internals at all.
# Observation is deliberately MINIMAL: a full colormap of 4000+ triangles is unreadable
# in realtime, and tearing only ever cares about ONE thing -- WHERE the stress peaks and
# WHICH WAY it points, because that is where a crack starts and it runs perpendicular to
# sigma1. So we draw a marker at the hottest triangle plus a direction probe, and print
# sigma1 stats. (Also avoids DataDisplay, which aborts this build's GUI.)
STRESS_MARKER = False    # no 3D marker: terminal only (red spheres were unreadable)
STRESS_TOP_N = 0         # extra markers beyond the peak. 0 = just the peak + its
                         # direction. (6 scattered red balls were unreadable.)
STRESS_TABLE_N = 5       # how many triangles to print in the terminal table
DEGEN_LO, DEGEN_HI = 0.25, 4.0   # area_ratio outside this = collapsed/blown-up
STRESS_LOG_EVERY = 1.0   # [s] how often to print the sigma1 report
STRESS_HOT_FRAC = 0.5    # a triangle counts as 'loaded' above this fraction of the peak
SHOW_STRESS = True       # compute sigma1 every STRESS_EVERY steps (the tear criterion
                         # will run on this). Cheap, headless-safe, no GUI involvement.
# Colouring the mesh by sigma1 via DataDisplay CRASHES this SOFA build: SIGABRT in
# DataDisplay::computeNormals during VisualModel::updateVisual / initTextures, i.e. at
# GUI visual init. Batch mode never initialises visuals, which is why a headless test
# passed and the app still would not open. Left OFF until a safe visualisation exists.
STRESS_COLOR = False
STRESS_EVERY = 3         # steps between stress updates (it is ~O(triangles) numpy)
STRESS_E = 1200.0        # Young's modulus used for sigma = C:eps
STRESS_NU = 0.3

# --- the safety net that actually stops "一瞬間出現超大三角形" -----------------
# The mouse attach is a PENALTY spring: F = MOUSE_STIFFNESS * (how far you drag the cursor
# past the grabbed point). Pull harder = drag further = the force grows with NO LIMIT, so
# one node gets a huge impulse, flies in a single step, and you see a giant triangle. No
# stiffness value fixes this (measured: it explodes at 400, 1000 and 2000 alike).
# So we cap the SYMPTOM instead: no node may ever exceed MAX_SPEED. Normal dragging runs
# at ~1-3 units/s, so this never touches ordinary use -- it only clips the runaway spike.
# (The textbook fix is a constraint-based/Lagrangian attach, which needs
# FreeMotionAnimationLoop + an LCP solver: a much bigger rework.)
MAX_SPEED = 25.0         # units/s; 0 disables the clamp
# MAGNITUDE net -- the cure for the SILENT disappearance (mesh vanishes, NO error). A
# triangle that INVERTS (flips through collinear) under a hard pull gets pushed the WRONG
# way by the co-rotational FEM, so it inflates without bound: positions run to ~1e150 in a
# few steps. That is HUGE but still FINITE, so np.isfinite() is True and the NaN-rollback
# never fires -- the sheet just flies off-screen (confirmed by "overflow encountered in
# square" once |coord| passes ~1e154). The whole cap lives within |coord| < ~15 in normal
# use (radius 7, lifted a few mm), so any node past MAX_COORD is a runaway: rewind to the
# last healthy frame WHILE it is still small enough to recover, instead of after it hits 1e150.
MAX_COORD = 50.0         # units; a node past this = runaway blow-up -> rewind. 0 disables.
                         # The whole cap lives within |coord| < ~15 even when a flap is
                         # peeled and lifted, so 50 is a wide safety margin. Was 300, which
                         # let a node fly to z=-72 (off-screen = "mesh disappeared") before
                         # the net caught it; 50 rewinds it while it is still on-screen.

# STRAIN CLAMP -- stops the membrane crushing into a knot. When the adhesion avalanche
# unglues the whole sheet, nothing holds its shape, and the mouse spring + self-collision
# keep cramming it against the lens with no in-plane strain limit, so triangles inflate to
# 8x-33x their rest area and invert (measured: areaRatio 33, then 3056/4166 dead). A
# membrane is inextensible-ish, so forbid a node from moving so far that its edges stretch
# past MAX_STRETCH x rest length: project the offending node back. This is a hard geometric
# backstop, independent of any stiffness. (The real cure is tearing; until then this keeps
# the sim from exploding.)
MAX_STRETCH = 1.6        # an edge may not exceed this multiple of its rest length; 0 = off
STRAIN_ITERS = 3         # relaxation passes per step
# ANTI-COLLAPSE (min-area) clamp -- the MISSING TWIN of MAX_STRETCH. MAX_STRETCH stops a
# triangle from INFLATING, but nothing stopped it COLLAPSING: three nodes can drift
# collinear with every edge still a perfectly normal length, giving a ZERO-AREA triangle.
# The FEM's computeStrainDisplacementLocal then divides by that zero -> the "Null
# determinant / Division by zero" flood, and the mesh vanishes (NaN forces spread every-
# where). Any triangle whose area drops below MIN_AREA_FRAC x its ORIGINAL rest area gets
# its flattest vertex pushed back off the opposite edge, so no triangle ever reaches zero
# area. This is the direct cure for the "拉一陣子突然無限 ERROR + 幾何消失" crash.
MIN_AREA_FRAC = 0.05     # repair a triangle below 5% of its rest area; 0 = off
# When MORE than this many triangles collapse in a SINGLE step, it is not a stray sliver
# but an acute blow-up (a hard mouse flick spiking a whole cluster). Local repair only
# band-aids that into a frozen "撕碎" mesh, so instead REWIND the whole sheet -- positions
# AND rest shape -- to the last healthy frame and kill the velocity. A handful (<= this)
# is treated as a stray and just locally repaired.
SEVERE_COLLAPSE = 5
# What actually floods "Null determinant in computeStrainDisplacementLocal" is the ENDGAME: the
# instant the cap fully peels off the lens it is a free stiff FEM sheet carrying the pull momentum;
# that momentum drives a triangle collinear (zero area -> singular FEM) every step. A gently
# released free sheet is stable, so the cure is to remove the momentum, not to patch geometry:
# on full peel we zero the velocity, ramp damping to settle it, and drop the (now pointless) lens
# obstacle -- see the full-peel branch in the controller. PEEL_SETTLE_DAMPING is that ramp.
PEEL_SETTLE_DAMPING = 60.0

# --- RUNG 1 TEARING: break the pre-slit r~5 circle, then lift the central disc --------
# generate_cap pre-slits the mesh at TEAR_RADIUS: the tear-ring vertices are doubled
# (inner copy = the central disc, outer copy = the anchored rim), coincident and held
# together by these STITCH springs so it looks continuous. "Tearing the circle" = drop the
# stitches, progressively around the ring, so the central disc separates and lifts,
# deforming with the SAME physics. This is the simplest rung: it can only tear this one
# pre-designed circle; runtime splitting along an arbitrary path is a later rung.
SCRIPTED_TEAR = False    # OFF: the pre-slit fixed-circle tear was artificial (the
                         # user is right -- the tear should follow the instrument).
                         # Kept only as reference; runtime instrument-driven tearing
                         # is the next build (feasibility proven: numpy split works).
STITCH_K = 2500.0        # stiffness holding the slit closed (match EDGE_STIFFNESS)
TEAR_T = 3.0             # [s] start tearing the circle
TEAR_DURATION = 3.0      # [s] to tear all the way around
LIFT_HEIGHT = 4.5        # how high the freed central disc is lifted
FIX_OUTER_RIM = False    # NOTHING is clamped -- the membrane just sits on the lens held by the
                         # breakable adhesion, so you can Shift+left-drag the RIM, lift it and
                         # fold it over. (True hard-anchors the outer ring instead.)

# --- AUTOMATIC plasticity: "拉完就不太彈回", no key press needed --------------
# A purely elastic membrane snaps back to its rest shape the moment you let go. Real
# tissue/gel does not. So the part that has ALREADY PEELED off the lens slowly adopts
# its current shape as its new rest shape (viscoplastic creep): while you drag it the
# rest keeps catching up, so when you let go there is almost nothing left to spring
# back. Only peeled nodes creep -- nodes still glued keep their rest ON the lens, so
# the adhesion still holds them down.
#   PLASTIC_RATE: 0 = fully elastic (springs back), 1 = instantly plastic (putty).
PLASTIC_RATE = 0.35      # fraction of the remaining springback forgotten per update
PLASTIC_EVERY = 5        # STEPS (not seconds) between plasticity updates -> the creep
                         # rate is coupled to dt; changing dt changes the plastic feel.

# Pressing F still force-freezes the WHOLE membrane instantly (optional shortcut).
FREEZE_T = None          # None = never auto-freeze on a timer (creep handles it)
RELEASE_AFTER_FREEZE = True
# ---------------------------------------------------------------------------

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
    """Per-triangle max principal stress sigma1 and its in-plane direction.

    Co-rotational membrane stress computed from GEOMETRY ALONE:
      build a local 2D frame on the rest and current triangle -> in-plane deformation
      gradient F -> Green strain eps = (F^T F - I)/2 -> plane-stress sigma = C:eps ->
      principal values. Verified: sigma1 == 0 at rest, and peaks exactly where you pull.

    Returns (sigma1, dir3d, area_ratio). area_ratio = |det F| (1.0 = undeformed): far
    from 1 means the triangle collapsed or blew up and its sigma1 is NOT physical. The tear
    criterion will run on this: crack direction is perpendicular to sigma1 (Rankine), and
    a fiber weighting can be layered on later (Marchal argmax c) without touching this.
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
    # Per-triangle guarded 2x2 inverse. A degenerate REST triangle (collinear/zero-area,
    # e.g. after a crush or a plastic-freeze onto a collapsed cell) makes Dm singular; a
    # batched np.linalg.inv would then raise for the WHOLE array and kill the observer.
    # Here a bad triangle just gets Dm_inv=0 -> F=0 -> area_ratio=0 -> flagged degenerate
    # and excluded downstream, while every healthy triangle is still measured.
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
    area_ratio = np.abs(np.linalg.det(F))     # 1.0 = undeformed area
    # principal direction (2D angle) mapped back into 3D via the current frame
    ang = 0.5 * np.arctan2(2.0 * sxy, np.maximum(sxx - syy, 1e-12))
    d3 = np.cos(ang)[:, None] * xc + np.sin(ang)[:, None] * yc
    return s1, d3, area_ratio


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

        def _freeze(self, why):
            self.mo.rest_position.value = self.mo.position.value
            self.springs.reinit()
            self.bending.reinit()
            if self.adhered is not None:
                self.adhered.clear()
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
            # STRICT test for "safe to snapshot as a rewind target". A rewind can only
            # rescue the sheet if the frame it rewinds TO is genuinely good, so this must
            # reject BOTH failure directions -- not just collapse. A blow-up inflates
            # triangles (area ratio in the thousands) with finite, sub-MAX_COORD coords, so
            # the old "finite and not collapsed" test happily cached the exploding frame as
            # last_good; the runaway net then rewound straight back into the explosion and
            # stuck at the same |coord| forever. Require: finite, coords bounded, and every
            # triangle's area within [MIN_AREA_FRAC, DEGEN_HI] x its rest area.
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
            # Restore the last HEALTHY frame -- positions, rest shape, and zero velocity.
            # Used by every safety net (NaN, unrepairable collapse, acute cluster blow-up).
            # Restoring the REST too is what un-bakes a plasticity-frozen blow-up: without it
            # the FEM equilibrium would still be the shredded shape.
            if self.last_good is None:
                return
            self.mo.position.value = self.last_good
            if self.last_good_rest is not None:
                self.mo.rest_position.value = self.last_good_rest
                self.bending.reinit()
            self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.last_good)
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
            # Self-calibrating grab detector: track the RESTING (minimum) object count seen,
            # and treat any live count above it as "an attach object is present = you are
            # Shift+dragging". This adapts to whatever idle object count SofaImGui settles at
            # (which is why the old fixed-first-step baseline locked the camera forever).
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

        def onAnimateEndEvent(self, event):
            # (0) NaN-rollback net. Once the membrane is FULLY peeled off the lens it is a
            # completely free stiff FEM sheet; residual momentum + lens repulsion can push a
            # triangle degenerate -> "Null determinant" -> the solve returns NaN, and NaN is
            # sticky (the clamps below compute NaN>limit == False and cannot repair it). So if
            # this step went non-finite, restore the last all-finite positions and kill the
            # velocity, turning a permanent blow-up into a recoverable hiccup.
            P0 = np.array(self.mo.position.value)
            # Runaway net (whole-mesh rewind on |coord|>MAX_COORD). Kept ON for mass-spring
            # too: it turns out a mass-spring sheet CAN still blow up -- not from the springs,
            # but from the self-collision penalty on tight folds -- so this remains the
            # last-resort catch (its earlier "loop" was it correctly catching that recurring
            # blow-up; the real cure is removing the source, see SELF_COLLISION).
            runaway = (MAX_COORD > 0.0 and P0.size > 0
                       and np.isfinite(P0).all() and np.abs(P0).max() > MAX_COORD)
            if not np.isfinite(P0).all() or runaway:
                if runaway and self.step % 15 == 0:
                    print(f"[Runaway] a node passed |coord|>{MAX_COORD:g} "
                          f"(max {float(np.abs(P0).max()):.1f}) -> rewound before it "
                          f"flew off-screen")
                self._rewind()
                return

            # (1) Velocity clamp: clip a runaway node's speed before it flies a long way in
            # one step and becomes a giant triangle.
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

            # (2) Strain clamp: forbid any edge from stretching past MAX_STRETCH x its rest
            # length, so a triangle can never inflate to 8x-33x area and invert. A few
            # Gauss-Seidel passes over the over-stretched edges, pulling their endpoints
            # back along the edge. Rest edge lengths cached once from rest_position.
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
                        # split the correction between the two endpoints
                        np.add.at(P, e0[over], 0.5 * excess * n)
                        np.add.at(P, e1[over], -0.5 * excess * n)
                    if moved:
                        self.mo.position.value = P.tolist()

            # (2b) ANTI-COLLAPSE (min-area) clamp -- the twin of the MAX_STRETCH clamp above.
            # MAX_STRETCH stops a triangle inflating; this stops it COLLAPSING to zero area,
            # which is exactly what makes computeStrainDisplacementLocal divide by zero ("Null
            # determinant" flood) and the mesh disappear. Repair the flattest vertex of any
            # near-collinear triangle; if one is so collapsed it cannot be repaired (its base
            # edge is gone too), roll the whole sheet back to the last HEALTHY state rather
            # than let the FEM choke on it forever.
            # Anti-collapse + severe-rewind is also FEM-only: a collapsed triangle only
            # matters because the FEM divides by its area. Mass-spring does not, so the local
            # apex-pushing and the whole-sheet rewind here are unnecessary and only jitter /
            # snap-back the sheet -- disable them under mass-spring and let the springs relax.
            degenerate_after = None       # None = not yet known; (3) will check if needed
            if MIN_AREA_FRAC > 0.0 and not USE_MASS_SPRING:
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
                        # ACUTE blow-up (a whole cluster collapsed this step): local repair
                        # would only band-aid it into a frozen shredded mesh. Rewind the whole
                        # sheet -- positions AND rest -- to the last healthy frame instead.
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
                            # repair could not save every triangle -> escape to safety
                            self._rewind()
                            return
                    else:
                        degenerate_after = False

            # (3) Cache this finite state as the rollback target for (0) -- but ONLY if it is
            # also NON-DEGENERATE. Caching a finite-but-collinear state would make (0)/(2b)
            # roll back INTO the same zero-area trap forever (the infinite flood). Requiring
            # healthy triangles guarantees every rollback escapes to a solvable configuration.
            # Snapshot as a rewind target ONLY when the whole frame is genuinely healthy --
            # not merely finite-and-not-collapsed. This is what stops last_good being
            # poisoned by an inflating blow-up (which the runaway net then rewinds straight
            # back into, sticking at a fixed |coord| forever). See _is_healthy.
            Pn = np.array(self.mo.position.value)
            if self._is_healthy(Pn):
                self.last_good = Pn.tolist()
                # Snapshot the rest shape TOO, so a rewind restores a matching
                # (position, rest) pair -- otherwise a rewind of positions onto a
                # plasticity-drifted rest would itself be a mismatch.
                self.last_good_rest = list(self.mo.rest_position.value)

        def onAnimateBeginEvent(self, event):
            # Time from the MechanicalObject's context (works whether or not a FEM exists --
            # in mass-spring mode self.fem is None).
            t = self.mo.getContext().getTime()

            # Make the GUI's Bending->stiffness field actually WORK. TriangularBendingSprings
            # bakes ks into per-edge data (ei.ks = getKs()), so typing a new value in the
            # Data panel changes nothing until reinit() re-reads it. Poll it and re-bake.
            # (Hotkeys are unreliable here: SofaImGui swallows the keyboard unless the 3D
            # viewport has focus, so editing the Data field is the dependable route.)
            ks_now = float(self.bending.stiffness.value)
            if self.last_ks is None:
                self.last_ks = ks_now
            elif abs(ks_now - self.last_ks) > 1e-9:
                self.bending.reinit()
                self.last_ks = ks_now
                print(f"[Tune] BEND_STIFFNESS -> {ks_now:.1f} (applied)")

            if not self.paper_done and t >= SWITCH_T:
                # Stiffen cloth -> paper. In mass-spring mode (fem is None) the edge springs
                # carry the stiffness, so only linesStiffness matters; skip the FEM setter.
                if self.fem is not None:
                    # FEMOptim takes youngModulus as a SCALAR; the plain version took a vector.
                    # Try scalar first, fall back to the list form so either class survives.
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
                        # the moment the tear starts, unglue the central disc from the lens
                        # so it can be lifted; the rim stays glued and anchored.
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
            if self.adhered and not self.frozen:
                idx = np.fromiter(self.adhered, dtype=int)
                lift = np.linalg.norm(pos[idx] - rest[idx], axis=1)
                broken = idx[lift > self.break_lift]
                if broken.size:
                    self.adhered.difference_update(broken.tolist())
                    # IMPORTANT: an EMPTY 'points' list makes RestShapeSpringsForceField
                    # apply to ALL nodes, which would snap the whole membrane back onto
                    # the lens. So when the last spot peels, kill the stiffness instead.
                    if self.adhered:
                        self.adhesion.points.value = sorted(self.adhered)
                    else:
                        self.adhesion.stiffness.value = [0.0]
                    if t - self.last_log_t >= 0.5:
                        print(f"[Peel] t={t:.2f}s  {len(self.adhered)} spots still "
                              f"glued to the lens")
                        self.last_log_t = t
                if not self.adhered and not self.fully_peeled:
                    print(f"[Peel] t={t:.2f}s  membrane fully peeled off the lens")
                    self.fully_peeled = True
                    # ENDGAME STABILISER. A fully-free stiff FEM sheet carrying the pull
                    # momentum drives a triangle collinear -> "Null determinant" flood. A gently
                    # released free sheet is stable, so remove the momentum rather than patch the
                    # geometry: arrest the velocity, ramp damping so it settles, and drop the lens
                    # obstacle it is no longer resting on (it would only fight the free disc now).
                    self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.mo.position.value)
                    self.damper.dampingCoefficient.value = PEEL_SETTLE_DAMPING
                    lens = self.mo.getContext().getObject("LensObstacle")
                    if lens is not None:
                        lens.stiffness.value = 0.0

            # AUTOMATIC plasticity: the already-peeled part slowly adopts its current
            # shape as its rest shape, so letting go barely springs back. Nodes still
            # glued keep their rest on the lens (adhesion must still hold them).
            self.step += 1

            # --- freeze the camera ONLY while you are actually pulling --------------
            # Shift+drag makes AttachBodyPerformer insert its interaction spring into the
            # graph; that new object is our "a grab is in progress" signal. We cannot read
            # the mouse directly (SofaPython3 does not bind onMouseEvent) and the
            # left-drag=orbit binding is hard-coded in SofaGLFW, so this is the way to
            # stop the view spinning out from under you mid-pull.
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
                # Capture the start view once, for R = re-centre.
                if self.cam_home is None:
                    try:
                        self.cam_home = (list(self.camera.position.value),
                                         list(self.camera.lookAt.value))
                    except Exception:  # noqa: BLE001
                        self.cam_home = None
                # Orbit is disabled when EITHER you manually locked it (V) OR you are
                # currently Shift+dragging to pull. Write activated only on a change.
                grabbing = self._is_grabbing() if FREEZE_CAMERA_WHILE_PULLING else False
                want_active = not (self.cam_lock or grabbing)
                if want_active != self.cam_active:
                    self.camera.activated.value = want_active
                    self.cam_active = want_active

            # --- STRESS FIELD: the foundation the tear criterion will run on -------
            # Computed from geometry (rest vs current), so it is independent of which
            # component carries the load, and needs no FEM internals (which Python
            # cannot read anyway).
            if SHOW_STRESS and self.step % STRESS_EVERY == 0:
                if self.tris is None:
                    self.tris = np.array(self.topo.triangles.value)
                if len(self.tris):
                    s1, sdir, aratio = principal_stress(np.asarray(pos),
                                                       np.asarray(rest), self.tris)
                    self.sigma1_max = float(s1.max())
                    if self.display is not None:
                        self.display.triangleData.value = s1.tolist()

                    # Where is it hottest, and which way does it point? That -- not the
                    # whole field -- is what decides where a crack starts and where it
                    # goes (crack runs PERPENDICULAR to sigma1).
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

            if (not self.frozen and self.plastic_rate > 0.0
                    and self.step % PLASTIC_EVERY == 0 and self.adhered is not None):
                free = np.setdiff1d(np.arange(len(pos)),
                                    np.fromiter(self.adhered, dtype=int)
                                    if self.adhered else np.empty(0, dtype=int),
                                    assume_unique=False)
                # PLASTICITY HEALTH GUARD. Creep bakes the CURRENT shape into the rest, so
                # if a hard yank momentarily blows a cluster of triangles up (or squashes
                # them flat), letting the rest adopt that broken shape makes the damage
                # PERMANENT: the FEM's equilibrium becomes the shredded shape, the anti-
                # collapse clamp then fights it forever and the mesh stays torn (the frozen
                # "撕碎" state). So exclude any node touching an unhealthy triangle
                # (area ratio outside DEGEN_LO..DEGEN_HI): its rest stays clean, and once
                # the spike passes the FEM pulls that cluster back to a good shape instead
                # of setting the blow-up in stone. Uses the current-vs-rest area ratio.
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
                    # Re-bake ONLY the bending rest (so folds become permanent).
                    # Deliberately NOT springs.reinit(): that would let the EDGE rest
                    # lengths adopt the stretched positions, i.e. unbounded plastic flow
                    # with no yield -- the membrane permanently grows and a hard yank
                    # explodes it (measured max|coord| 2402). Keeping the edge rest
                    # lengths original also enforces "the paper must not stretch".
                    self.bending.reinit()

            if SCRIPTED_PULL and FREEZE_T is not None and not self.frozen and t >= FREEZE_T:
                self._freeze(f"t={t:.2f}s auto")

    return _C(name="CapAdhesionController")


def createScene(root):
    import Sofa

    # Gentle gravity so a peeled flap actually flops over onto the membrane instead of
    # hanging in mid-air. Small enough that it never peels anything by itself.
    root.gravity = [0.0, 0.0, GRAVITY_Z]
    # dt = 0.02 on purpose. Halving it to 0.01 makes the membrane MORE explosive under a
    # hard yank, not less (measured: bend=60 -> max|coord| 110 vs 12.9 at dt=0.02).
    # Implicit Euler's numerical dissipation scales with dt, so the larger step is quietly
    # damping the yank's energy away. Do not "improve" this to a smaller dt.
    root.dt = 0.02
    # Group the ~20 RequiredPlugin entries into one collapsible node, otherwise they
    # bury the actual components under a long row in the GUI's Scene Graph.
    _plugins = root.addChild("RequiredPlugins")
    for name in PLUGINS:
        _plugins.addObject("RequiredPlugin", name=name)

    root.addObject("VisualStyle",
                   displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    # Camera elevation matters for PICKING, not just looks. Shift+drag casts a ray from
    # the camera through the cursor and grabs the nearest collision triangle. At a
    # grazing angle (low camera) that ray skims along this flat, wide lens, so one pixel
    # of mouse movement slides the hit point millimetres across the membrane and it
    # jumps between triangles -> the grab feels like it "runs around". A steeper angle
    # hits the membrane closer to perpendicular and the pick is stable.
    # computeZClip=False + fixed zNear/zFar: DO NOT auto-derive the near/far clip planes from
    # the scene bounding box. A single node that blows out (even transiently, before the
    # rewind catches it) inflates the bbox, which pushes the near plane far from the camera;
    # then zooming IN puts the real mesh nearer than that near plane and it vanishes ("content
    # is there but scrolling to zoom makes it disappear"). Pinning zNear/zFar keeps the clip
    # planes stable no matter what a stray vertex does, so zoom always works. zNear small
    # enough to zoom right up to the ~7-radius cap; zFar large enough to still show it.
    # Camera pulled a little closer (was [10,-10,11]) so the disc fills more of the viewport.
    _camera = root.addObject("InteractiveCamera", position=[8.0, -8.0, 9.0], lookAt=[0, 0, 0],
                   activated=not LOCK_CAMERA,
                   computeZClip=False, zNear=0.3, zFar=500.0)

    if ENABLE_MOUSE:
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=ALARM_DISTANCE,
                       contactDistance=CONTACT_DISTANCE)
        # Shift+left-drag: SOFA casts a ray from the camera through the cursor, takes the
        # nearest hit on a collision model (only the membrane has one -- the lens is
        # visual, so it can never be grabbed), and attaches a SpringForceField of this
        # stiffness between that point and a virtual "mouse" particle you drag. The mouse
        # particle moves in a plane PARALLEL TO THE SCREEN at the picked depth, so you
        # can only drag within the screen plane. arrowSize>0 draws that spring, so you
        # can SEE exactly which spot it grabbed.
        _mouse = root.addObject("AttachBodyButtonSetting", stiffness=MOUSE_STIFFNESS,
                                arrowSize=0.3)

    # The flattened (oblate) LENS the membrane sticks to. Generated from the SAME
    # analytic surface as cap.obj and finely tessellated, so the membrane lies exactly
    # flush on it (a coarse stock sphere.obj would let the cap float above its facets).
    # Visual only: the membrane is held on it by the adhesion springs, not by contact.
    ball = root.addChild("Lens")
    ball.addObject("MeshOBJLoader", name="bloader", filename=LENS_OBJ)
    ball.addObject("OglModel", name="lensVisual", src="@bloader",
                   color=[0.45, 0.55, 0.75, 0.45])

    # The CAP membrane.
    root.addObject("MeshOBJLoader", name="loader", filename=CAP_OBJ)

    cap = root.addChild("Cap")
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.2, rayleighMass=0.2)
    cap.addObject("CGLinearSolver", iterations=30, tolerance=1e-8, threshold=1e-8)

    topo = cap.addObject("TriangleSetTopologyContainer", name="topo", src="@../loader")
    cap.addObject("TriangleSetTopologyModifier")
    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")

    mo = cap.addObject("MechanicalObject", name="Mo", src="@../loader")
    cap.addObject("DiagonalMass", massDensity=1.0)

    # TriangularFEMForceFieldOptim (NOT the plain TriangularFEMForceField): the Optim
    # rewrite internally guards the 1/area term in the strain-displacement matrix, so a
    # degenerate/inverting triangle no longer throws "Null determinant in
    # computeStrainDisplacementLocal" and NaN-floods the whole sheet. Same corotational
    # physics; the principal-stress field the tear criterion needs is computed in numpy here
    # (principal_stress), independent of the FEM class. On Optim, youngModulus is a SCALAR
    # (not the per-triangle vector the plain version takes) -- see the ClothToPaper setter.
    # In mass-spring mode the FEM is dropped entirely (fem=None): the edge springs below
    # carry all the in-plane stiffness (a triangle with fixed edge lengths is rigid), and no
    # component divides by triangle area, so the sheet cannot explode. See USE_MASS_SPRING.
    fem = None
    if not USE_MASS_SPRING:
        fem = cap.addObject("TriangularFEMForceFieldOptim", name="FEM", method="large",
                            youngModulus=CLOTH_YOUNG, poissonRatio=0.3)
    springs = cap.addObject("MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    bending = cap.addObject("TriangularBendingSprings", name="Bending",
                            stiffness=BEND_STIFFNESS)
    _damper = cap.addObject("UniformVelocityDampingForceField",
                            dampingCoefficient=DAMPING)

    # The lens as a SOLID obstacle: analytic ellipsoid repulsion pushes any membrane
    # node that dips inside back out, so the membrane folds UP over the lens instead of
    # bending down through it. Same A/C/Z0 as the lens surface the cap was built on.
    cap.addObject("EllipsoidForceField", name="LensObstacle",
                  center=[0.0, 0.0, G.Z0], vradius=[G.A, G.A, G.C],
                  stiffness=LENS_REPULSION, damping=1.0)

    # Adhesion of every cap node to its spot on the ball (= its rest position).
    adhesion = cap.addObject("RestShapeSpringsForceField", name="Adhesion",
                             stiffness=ADHESION_STIFF, drawSpring=False)

    # STITCH springs holding the pre-slit tear circle closed. Each entry is
    # [inner_vid, outer_vid, ks, kd, restLength=0] (the pair is coincident). Breaking a
    # stitch = removing it from this list. Angle-sorted so the tear can run around the
    # circle progressively.
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
    # Build with indices1/indices2 (the 'spring' Data cannot be read back from Python --
    # "Invalid type" -- but indices1/indices2/stiffness/enabled all can). Break a stitch by
    # flipping its 'enabled' bool. Pairs are angle-sorted, so disabling the first k tears
    # the first k of the circle = the tear runs around progressively.
    stitch = cap.addObject("SpringForceField", name="Stitch",
                           indices1=[int(a) for a, b in _pairs],
                           indices2=[int(b) for a, b in _pairs],
                           stiffness=[STITCH_K], damping=[1.0], showArrowSize=0.0)
    central = set(int(i) for i in G.central_indices())

    # Anchor the OUTER rim (anatomically: the capsule is held by the zonular fibers). This
    # keeps the rim planted while the central disc tears free and lifts -- without it the
    # rim creeps up (self-collision as the torn edge passes it) -- and it also bounds the
    # adhesion avalanche. Fix the outermost ring of nodes (planar r near the cap edge R).
    if FIX_OUTER_RIM and _capV is not None:
        import math as _m2
        _outer = [i for i, xyz in enumerate(_capV)
                  if _m2.hypot(float(xyz[0]), float(xyz[1])) > 0.9 * G.R]
        if _outer:
            cap.addObject("FixedProjectiveConstraint", name="RimAnchor", indices=_outer,
                          showObject=False)

    # Lift handle: the central pole nodes. After the circle tears, this pulls the freed
    # disc up so you see it come off round.
    lift = None
    if SCRIPTED_TEAR:
        cap.addObject("BoxROI", name="poleBox", box=[-1.0, -1.0, -1.0, 1.0, 1.0, 3.0],
                      drawBoxes=False)
        # Lift only AFTER the circle is fully torn. If the lift overlaps the tear, the
        # still-intact stiff stitches (k=2500) drag the rim up faster than the weak
        # adhesion (120) can hold it down, so the rim rises too. Tear first, then lift.
        _t1 = TEAR_T + TEAR_DURATION + 0.3      # lift starts here
        lift = cap.addObject("LinearMovementProjectiveConstraint", name="lift",
                             indices="@poleBox.indices",
                             keyTimes=[0.0, _t1, _t1 + 3.0, 60.0],
                             movements=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
                                        [0.0, 0.0, LIFT_HEIGHT], [0.0, 0.0, LIFT_HEIGHT]])

    # Peak-stress marker. A plain MechanicalObject that draws itself as spheres: no
    # visual model, no mapping, nothing that can crash the GUI. The controller moves these
    # points onto the hottest triangles each step. Point 0 = the peak; the last point is
    # offset along the sigma1 direction, so the pair shows you the crack direction.
    _probe = None
    if STRESS_MARKER:
        _pn = root.addChild("StressProbe")
        _probe = _pn.addObject("MechanicalObject", name="probe",
                               position=[[0, 0, 0]] * (STRESS_TOP_N + 2),
                               showObject=True, showObjectScale=0.25, drawMode=1,
                               showColor=[1.0, 0.15, 0.05, 1.0])

    pull = None
    if SCRIPTED_PULL:
        # Grab the +x rim arc and lift it up/out to peel the cap off the ball.
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
        # selfCollision=True lets the folded-over flap REST ON the membrane underneath
        # instead of passing through it (default is False = it would interpenetrate).
        # This model is also what the mouse ray picks.
        cap.addObject("TriangleCollisionModel", selfCollision=SELF_COLLISION,
                      contactStiffness=CONTACT_STIFFNESS)

    _display = None
    if STRESS_COLOR:
        # DataDisplay colours each triangle by the scalar we push into triangleData
        # (our sigma1). OglColorMap draws the legend. Red = high stress = where a tear
        # would start.
        _display = cap.addObject("DataDisplay", name="StressView", maximalRange=False)
        cap.addObject("OglColorMap", name="StressMap", colorScheme="HSV",
                      showLegend=True, legendTitle="sigma1")
    if not STRESS_COLOR:
        visu = cap.addChild("Visual")
        visu.addObject("OglModel", name="visual", color=[0.92, 0.90, 0.82, 1.0])
        visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

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
