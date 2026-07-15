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

# How SHARPLY the membrane folds when you lift it = TriangularBendingSprings.stiffness.
#   BIGGER  -> resists bending -> a GENTLER, rounder, wider fold (no tight crease)
#   SMALLER -> floppier        -> a TIGHTER, sharper crease ("太彎")
# NOTE: this is NOT the same as "soft". In-plane softness is PAPER_YOUNG/EDGE_STIFFNESS;
# fold sharpness is this. If the fold looks too sharply curled, RAISE this.
BEND_STIFFNESS = 600.0

# The lens acts as a solid obstacle so the membrane cannot sink through it: an analytic
# ellipsoid repulsion (cheap + robust, no mesh collision needed). SOFA convention
# (EllipsoidForceField.h): stiffness POSITIVE = repulse OUTWARD, negative = inward.
# Without this the membrane bends down and passes straight through the lens.
LENS_REPULSION = 800.0

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
# Mouse-pull strength. The GUI's default attach spring is far too weak to beat the
# adhesion, which is why the membrane felt "拉不動". This spring must be able to lift a
# node past BREAK_FORCE (= ADHESION_STIFF * break lift), so keep it well above that.
MOUSE_STIFFNESS = 1000.0

# --- AUTOMATIC plasticity: "拉完就不太彈回", no key press needed --------------
# A purely elastic membrane snaps back to its rest shape the moment you let go. Real
# tissue/gel does not. So the part that has ALREADY PEELED off the lens slowly adopts
# its current shape as its new rest shape (viscoplastic creep): while you drag it the
# rest keeps catching up, so when you let go there is almost nothing left to spring
# back. Only peeled nodes creep -- nodes still glued keep their rest ON the lens, so
# the adhesion still holds them down.
#   PLASTIC_RATE: 0 = fully elastic (springs back), 1 = instantly plastic (putty).
PLASTIC_RATE = 0.25      # fraction of the remaining springback forgotten per update
PLASTIC_EVERY = 5        # steps between plasticity updates (cheap: reinit is O(edges))

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
    "Sofa.GL.Component.Rendering3D",
]


def _make_controller(fem, springs, bending, mo, adhesion, pull):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.fem, self.springs, self.bending = fem, springs, bending
            self.mo, self.adhesion, self.pull = mo, adhesion, pull
            self.paper_done = False
            self.adhered = None
            self.break_lift = BREAK_FORCE / ADHESION_STIFF
            self.last_log_t = -1.0
            self.fully_peeled = False
            self.frozen = False
            self.step = 0

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

        def onKeypressedEvent(self, event):
            if event["key"] in ("F", "f") and not self.frozen:
                self._freeze("key F pressed")

        def onAnimateBeginEvent(self, event):
            t = self.fem.getContext().getTime()

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
            if (not self.frozen and PLASTIC_RATE > 0.0
                    and self.step % PLASTIC_EVERY == 0 and self.adhered is not None):
                free = np.setdiff1d(np.arange(len(pos)),
                                    np.fromiter(self.adhered, dtype=int)
                                    if self.adhered else np.empty(0, dtype=int),
                                    assume_unique=False)
                if free.size:
                    newrest = np.array(rest, copy=True)
                    newrest[free] += PLASTIC_RATE * (pos[free] - rest[free])
                    self.mo.rest_position.value = newrest
                    self.springs.reinit()
                    self.bending.reinit()

            if SCRIPTED_PULL and FREEZE_T is not None and not self.frozen and t >= FREEZE_T:
                self._freeze(f"t={t:.2f}s auto")

    return _C(name="CapAdhesionController")


def createScene(root):
    import Sofa

    root.gravity = [0.0, 0.0, 0.0]     # the ball adhesion holds the cap; no gravity
    root.dt = 0.02
    for name in PLUGINS:
        root.addObject("RequiredPlugin", name=name)

    root.addObject("VisualStyle",
                   displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    root.addObject("InteractiveCamera", position=[11.0, -11.0, 8.5], lookAt=[0, 0, -1.0])

    if ENABLE_MOUSE:
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=0.5, contactDistance=0.2)
        # Make Shift+left-drag strong enough to actually rip a spot off the lens.
        root.addObject("AttachBodyButtonSetting", stiffness=MOUSE_STIFFNESS)

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

    cap.addObject("TriangleSetTopologyContainer", name="topo", src="@../loader")
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
    cap.addObject("UniformVelocityDampingForceField", dampingCoefficient=DAMPING)

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
        cap.addObject("TriangleCollisionModel")

    cap.addObject(_make_controller(fem, springs, bending, mo, adhesion, pull))

    visu = cap.addChild("Visual")
    visu.addObject("OglModel", name="visual", color=[0.92, 0.90, 0.82, 1.0])
    visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

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
