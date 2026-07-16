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

# --- material presets (same feel as the flat paper) -------------------------
CLOTH_YOUNG = 120.0
PAPER_YOUNG = 1200.0      # do NOT use 4000+ (NaN blow-up risk)
SWITCH_T = 1.0
EDGE_STIFFNESS = 2500.0   # per-edge -> the membrane does not stretch (in-plane)
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
SELF_COLLISION = True
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
MOUSE_STIFFNESS = 1000.0

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
# FREEZE_CAMERA_WHILE_PULLING: DISABLED -- it does not work and it broke orbiting.
# The idea was to spot AttachBodyPerformer's interaction spring appearing in the graph and
# freeze the camera only for the duration of a grab. Headless it behaves (object count is
# a stable 56, never misfires), but in the GUI the count sits permanently above the
# baseline -- SofaGLFW/SofaImGui add their own mouse-interactor objects -- so it decides
# you are grabbing forever and the camera stays locked. A global object COUNT is simply
# the wrong signal; it must match the attach spring specifically. Off until that is done.
FREEZE_CAMERA_WHILE_PULLING = False

# --- stress field (this is what the tear criterion will be built on) ----------
# We compute the per-triangle principal stress OURSELVES in numpy, because the FEM's own
# stress is unreachable: fem.triangleInfo / fem.vertexInfo are C++ structs that
# SofaPython3 cannot bind ("Invalid type") -- that is exactly why this repo needed a C++
# plugin. Strain is a purely GEOMETRIC quantity (rest vs current), so it does not matter
# which component carries the load, and we need no FEM internals at all.
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

    Returns (sigma1, dir3d) with dir3d the 3D direction of sigma1 per triangle. The tear
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
    F = Ds @ np.linalg.inv(Dm)
    eps = 0.5 * (np.einsum('tki,tkj->tij', F, F) - np.eye(2))
    c = E / (1.0 - nu * nu)
    sxx = c * (eps[:, 0, 0] + nu * eps[:, 1, 1])
    syy = c * (eps[:, 1, 1] + nu * eps[:, 0, 0])
    sxy = c * (1.0 - nu) * eps[:, 0, 1]
    mid = 0.5 * (sxx + syy)
    dev = np.sqrt(np.maximum(((sxx - syy) * 0.5) ** 2 + sxy ** 2, 0.0))
    s1 = mid + dev
    # principal direction (2D angle) mapped back into 3D via the current frame
    ang = 0.5 * np.arctan2(2.0 * sxy, np.maximum(sxx - syy, 1e-12))
    d3 = np.cos(ang)[:, None] * xc + np.sin(ang)[:, None] * yc
    return s1, d3


def _make_controller(fem, springs, bending, mo, adhesion, pull, mouse, damper,
                     topo, display, camera, root):
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
            self.base_objs = None      # graph snapshot taken on the first step
            self.grabbing = False
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

        def onAnimateEndEvent(self, event):
            # Velocity clamp: the last line of defence against a runaway node. Runs AFTER
            # the step, so it clips the spike the solver just produced before it can turn
            # into a giant triangle next step.
            if MAX_SPEED <= 0.0:
                return
            v = self.mo.velocity.value
            if len(v) == 0:
                return
            speed = np.linalg.norm(v, axis=1)
            hot = speed > MAX_SPEED
            if hot.any():
                v2 = np.array(v, copy=True)
                v2[hot] *= (MAX_SPEED / speed[hot])[:, None]
                self.mo.velocity.value = v2
                self.clamped += int(hot.sum())

        def onAnimateBeginEvent(self, event):
            t = self.fem.getContext().getTime()

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
                self.fem.youngModulus.value = [PAPER_YOUNG]
                self.fem.reinit()
                self.springs.linesStiffness.value = EDGE_STIFFNESS
                self.paper_done = True
                print(f"[ClothToPaper] t={t:.2f}s -> paper (young={PAPER_YOUNG})")

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
            if FREEZE_CAMERA_WHILE_PULLING and not LOCK_CAMERA and self.camera is not None:
                now = self._count_objs()
                if self.base_objs is None:
                    self.base_objs = now
                grabbing = now > self.base_objs
                if grabbing != self.grabbing:
                    self.grabbing = grabbing
                    self.camera.activated.value = not grabbing

            # --- STRESS FIELD: the foundation the tear criterion will run on -------
            # Computed from geometry (rest vs current), so it is independent of which
            # component carries the load, and needs no FEM internals (which Python
            # cannot read anyway).
            if SHOW_STRESS and self.step % STRESS_EVERY == 0:
                if self.tris is None:
                    self.tris = np.array(self.topo.triangles.value)
                if len(self.tris):
                    s1, _d = principal_stress(np.asarray(pos), np.asarray(rest), self.tris)
                    self.sigma1_max = float(s1.max())
                    if self.display is not None:
                        self.display.triangleData.value = s1.tolist()

            if (not self.frozen and self.plastic_rate > 0.0
                    and self.step % PLASTIC_EVERY == 0 and self.adhered is not None):
                free = np.setdiff1d(np.arange(len(pos)),
                                    np.fromiter(self.adhered, dtype=int)
                                    if self.adhered else np.empty(0, dtype=int),
                                    assume_unique=False)
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
    _camera = root.addObject("InteractiveCamera", position=[10.0, -10.0, 11.0], lookAt=[0, 0, 0],
                   activated=not LOCK_CAMERA)

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

    fem = cap.addObject("TriangularFEMForceField", name="FEM", method="large",
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
                                   _mouse, _damper, topo, _display, _camera, root))


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
