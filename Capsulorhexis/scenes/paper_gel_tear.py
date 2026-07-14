"""Simple CCC-flavoured demo: a square paper lying on a BASE, stuck to it by an
ADHESION with a force THRESHOLD. Pull an edge up; where the pulling force exceeds the
adhesion threshold, the paper PEELS off the base (like peeling tape, or the lens
capsule off the cortex). Below the threshold it stays stuck.

Built from stock SOFA only (no Capsulorhexis.dll). The four behaviours:

  1. cloth -> paper (elastic -> less elastic): TriangularFEMForceField.youngModulus is
     ramped CLOTH_YOUNG -> PAPER_YOUNG at t=SWITCH_T by a small controller.
  2. "set every edge's stiffness / triangles must not stretch": MeshSpringForceField
     puts a spring on every edge; TriangularBendingSprings adds out-of-plane stiffness.
  3. ADHESION TO A BASE with a threshold: a RestShapeSpringsForceField pulls every node
     toward its spot on the base (rest = the flat sheet). A controller SNAPS a node's
     adhesion spring the instant its force exceeds BREAK_FORCE -> that spot peels off.
  4. light viscous damping so the motion is soft and does not wobble.

Run it:

    .\scenes\run_paper.ps1        # runSofa -l SofaPython3 -g imgui -a scenes\paper_gel_tear.py

The scripted demo lifts the LEFT edge so you watch the peel front advance. You can also
Shift + left-drag any spot in the GUI to pull it yourself: pull gently and it stays
stuck; pull hard enough and the adhesion snaps and it lifts off.
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

SQUARE_MSH = os.path.join(SOFA_ROOT, "share", "sofa", "mesh", "square3.msh")

# --- material presets (tune to taste) --------------------------------------
CLOTH_YOUNG = 120.0      # soft, stretchy fabric
PAPER_YOUNG = 1200.0     # stiff, barely-stretching paper (do NOT use 4000+: the huge
                         # reaction forces can invert a triangle -> NaN blow-up)
SWITCH_T = 1.0           # [s] cloth -> paper happens here
EDGE_STIFFNESS = 2500.0  # per-edge spring stiffness -> the paper does not stretch
DAMPING = 2.0            # light viscous damping (f=-c*v) -> soft, no wobble

# --- adhesion to the base ---------------------------------------------------
# Every node is glued to its spot on the base by a spring of stiffness ADHESION_STIFF.
# The adhesion SNAPS when its force (= ADHESION_STIFF * lift distance) exceeds
# BREAK_FORCE. So: pull gently (force < BREAK_FORCE) -> stays stuck; pull hard
# (force > BREAK_FORCE) -> peels off. Effective break lift = BREAK_FORCE/ADHESION_STIFF.
ADHESION_STIFF = 120.0
BREAK_FORCE = 60.0       # raise -> stickier (harder to peel); lower -> peels easily

# --- the scripted demo pull -------------------------------------------------
SCRIPTED_PULL = True     # lift the left edge automatically to show the peel
PULL_HEIGHT = 5.0        # how high the grabbed edge is lifted
PULL_END_T = 6.0         # reaches PULL_HEIGHT at this time (slow -> watch it peel)
ENABLE_MOUSE = True      # Shift+left-drag to pull spots yourself

# --- keeping the deformed shape (plasticity) --------------------------------
# An elastic paper springs back to flat on release. To make the peeled shape STAY,
# we "freeze" it: set the rest shape = the current shape, so the springs no longer
# pull it back. The membrane FEM has no bending stiffness, so a bent (peeled) flap is
# held flat mainly by the BENDING springs -- which reinit() CAN re-freeze.
# Auto-freeze the scripted demo at FREEZE_T (after the lift); interactively, press F
# to freeze the current shape yourself, then let go and it stays.
FREEZE_T = 7.0           # [s] auto-freeze the peeled shape (scripted demo)
RELEASE_AFTER_FREEZE = True   # drop the pull after freezing, to prove it stays
# ---------------------------------------------------------------------------

PLUGINS = [
    "Sofa.Component.IO.Mesh",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.SolidMechanics.Spring",     # MeshSpring/Bending/RestShapeSprings
    "Sofa.Component.MechanicalLoad",            # UniformVelocityDampingForceField
    "Sofa.Component.Mass",
    "Sofa.Component.Constraint.Projective",     # Fixed / LinearMovement constraints
    "Sofa.Component.Engine.Select",             # BoxROI
    "Sofa.Component.Mapping.Linear",            # IdentityMapping (visual)
    "Sofa.Component.Collision.Detection.Algorithm",
    "Sofa.Component.Collision.Detection.Intersection",
    "Sofa.Component.Collision.Geometry",
    "Sofa.Component.Collision.Response.Contact",
    "Sofa.Component.Visual",
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def _make_controller(fem, springs, bending, mo, adhesion, pull):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.fem = fem
            self.springs = springs
            self.bending = bending
            self.mo = mo
            self.adhesion = adhesion
            self.pull = pull
            self.paper_done = False
            self.adhered = None          # set of still-glued node indices
            self.break_lift = BREAK_FORCE / ADHESION_STIFF
            self.last_log_t = -1.0
            self.fully_peeled = False
            self.frozen = False

        def _freeze(self, why):
            # Adopt the current shape as the new rest shape so the springs stop
            # pulling it back to flat -> the deformed/peeled shape stays put.
            self.mo.rest_position.value = self.mo.position.value
            self.springs.reinit()   # edge-spring rest lengths <- current
            self.bending.reinit()   # bending rest angles <- current (the key one)
            # Drop the base adhesion: once frozen, the springs hold the shape; leaving
            # adhesion on would keep pulling nodes back down to the flat base.
            if self.adhered is not None:
                self.adhered.clear()
            self.adhesion.points.value = []
            self.adhesion.stiffness.value = [0.0]
            if RELEASE_AFTER_FREEZE and self.pull is not None:
                self.pull.indices.value = []   # let go
            self.frozen = True
            print(f"[Freeze] {why}: shape frozen; it will now stay deformed")

        def onKeypressedEvent(self, event):
            if event["key"] in ("F", "f") and not self.frozen:
                self._freeze("key F pressed")

        def onAnimateBeginEvent(self, event):
            t = self.fem.getContext().getTime()

            # (1) cloth -> paper.
            if not self.paper_done and t >= SWITCH_T:
                self.fem.youngModulus.value = [PAPER_YOUNG]   # per-element vector Data
                self.fem.reinit()
                self.springs.linesStiffness.value = EDGE_STIFFNESS  # scalar Data
                self.paper_done = True
                print(f"[ClothToPaper] t={t:.2f}s -> paper (young={PAPER_YOUNG})")

            # (3) breakable adhesion: snap the glue wherever the lift exceeds the
            #     force threshold (force = ADHESION_STIFF * lift distance).
            pos = self.mo.position.value
            rest = self.mo.rest_position.value
            if self.adhered is None:
                self.adhered = set(range(len(pos)))
                self.adhesion.points.value = sorted(self.adhered)
            if self.adhered:
                idx = np.fromiter(self.adhered, dtype=int)
                lift = np.linalg.norm(pos[idx] - rest[idx], axis=1)
                broken = idx[lift > self.break_lift]
                if broken.size:
                    self.adhered.difference_update(broken.tolist())
                    self.adhesion.points.value = sorted(self.adhered)
                    # Throttle logging to ~2 Hz so the console is not flooded.
                    if t - self.last_log_t >= 0.5:
                        print(f"[Peel] t={t:.2f}s  {len(self.adhered)} spots still "
                              f"glued to the base")
                        self.last_log_t = t
                if not self.adhered and not self.fully_peeled:
                    print(f"[Peel] t={t:.2f}s  paper fully peeled off the base")
                    self.fully_peeled = True

            # Auto-freeze the scripted demo once the lift is done -> the peeled shape
            # stays instead of springing back flat.
            if SCRIPTED_PULL and not self.frozen and t >= FREEZE_T:
                self._freeze(f"t={t:.2f}s auto")

    return _C(name="AdhesionController")


def createScene(root):
    import Sofa

    root.gravity = [0.0, 0.0, 0.0]   # the base holds the paper; no gravity needed
    root.dt = 0.02
    for name in PLUGINS:
        root.addObject("RequiredPlugin", name=name)

    root.addObject("VisualStyle",
                   displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.10, 0.11, 0.13, 1.0])
    # Oblique view so the paper (flat on the z=0 base) and the lifting peel are visible.
    root.addObject("InteractiveCamera", position=[16, -8, 15], lookAt=[5, 5, 0])

    if ENABLE_MOUSE:
        # Minimal collision pipeline so Shift+left-drag can pick and pull the paper.
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=0.5, contactDistance=0.2)

    root.addObject("MeshGmshLoader", name="loader", filename=SQUARE_MSH,
                   scale=10.0, createSubelements=True)

    sheet = root.addChild("Sheet")
    sheet.addObject("EulerImplicitSolver", rayleighStiffness=0.2, rayleighMass=0.2)
    # 30 iterations is plenty for this small mesh (was 150 -> that is what tanked FPS).
    sheet.addObject("CGLinearSolver", iterations=30, tolerance=1e-8, threshold=1e-8)

    sheet.addObject("TriangleSetTopologyContainer", name="topo", src="@../loader")
    sheet.addObject("TriangleSetTopologyModifier")
    sheet.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")

    mo = sheet.addObject("MechanicalObject", name="Mo", src="@../loader")
    sheet.addObject("DiagonalMass", massDensity=1.0)

    # (1) in-plane elasticity (cloth first, stiffened to paper by the controller).
    fem = sheet.addObject("TriangularFEMForceField", name="FEM", method="large",
                          youngModulus=CLOTH_YOUNG, poissonRatio=0.3)

    # (2) every edge stiff -> the paper does not stretch out of shape.
    springs = sheet.addObject("MeshSpringForceField", name="EdgeSprings",
                              linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    bending = sheet.addObject("TriangularBendingSprings", name="Bending", stiffness=200.0)

    # light viscous damping -> soft, no wobble.
    sheet.addObject("UniformVelocityDampingForceField", dampingCoefficient=DAMPING)

    # (3) ADHESION to the base: a spring from every node to its spot on the flat base
    #     (the rest shape). The controller snaps these when the lift force crosses the
    #     threshold. Empty 'points' initially means "all nodes"; the controller then
    #     manages the list, removing indices as they peel.
    adhesion = sheet.addObject("RestShapeSpringsForceField", name="Adhesion",
                               stiffness=ADHESION_STIFF, drawSpring=False)

    pull = None
    if SCRIPTED_PULL:
        # Grab the whole LEFT edge (x ~ 0) and lift it up (+z). As it rises the peel
        # front advances rightward; adhesion snaps where the force beats the threshold.
        e = 0.15
        sheet.addObject("BoxROI", name="grabEdge", box=[-e, -e, -e, e, 10 + e, e],
                        drawBoxes=False)
        pull = sheet.addObject("LinearMovementProjectiveConstraint", name="pull",
                               indices="@grabEdge.indices",
                               keyTimes=[0.0, SWITCH_T, PULL_END_T, 60.0],
                               movements=[[0.0, 0.0, 0.0],
                                          [0.0, 0.0, 0.0],
                                          [0.0, 0.0, PULL_HEIGHT],
                                          [0.0, 0.0, PULL_HEIGHT]])   # held after lift

    if ENABLE_MOUSE:
        sheet.addObject("TriangleCollisionModel")

    sheet.addObject(_make_controller(fem, springs, bending, mo, adhesion, pull))

    visu = sheet.addChild("Visual")
    visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.85, 1.0])
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
    Sofa.Gui.GUIManager.Init("paper_gel_tear", "imgui")
    Sofa.Gui.GUIManager.createGUI(root, __file__)
    Sofa.Gui.GUIManager.SetDimension(1000, 760)
    Sofa.Gui.GUIManager.MainLoop(root)
    Sofa.Gui.GUIManager.closeGUI()


try:
    import Sofa  # noqa: F401  (available under runSofa; header above enables direct run)
except Exception:  # noqa: BLE001
    pass

if __name__ == "__main__":
    main()
