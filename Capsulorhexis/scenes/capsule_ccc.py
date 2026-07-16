"""Faithful capsulorhexis (CCC) scene: concentric-fiber capsule + FiberFractureEngine.

Reproduces the Allard/Marchal/Cotin 2009 model (as used by Dequidt et al. 2013):

  - transversely-isotropic co-rotational triangular FEM  (Marchal Eq.1)
      stock TriangularAnisotropicFEMForceField, same INRIA lineage
  - concentric fiber directions (every 0.5 mm)            (Dequidt sec.4.2)
      fiberCenter at the disc centre -> circumferential fibers, radial weak axis
  - implicit + CG integration
  - fiber-based argmax-c tearing criterion               (Marchal Eq.3-6)
      our FiberFractureEngine (Capsulorhexis plugin)

Run through runSofa (its GUI frames the disc and lets you Shift+drag to tear):

    ./scenes/run.ps1            # wraps: runSofa -l SofaPython3 scenes/capsule_ccc.py

The scene also runs a scripted central pull so it tears autonomously once a step.
Interact: Shift + left-drag on the membrane to pull and propagate the tear.
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
for _p in (os.path.join(SOFA_ROOT, "bin"),):
    if os.path.isdir(_p):
        os.add_dll_directory(_p)
for _plugin in ("SofaPython3", "SofaImGui", "Tearing",
                "Sofa.Component.SolidMechanics.FEM.Elastic"):
    _d = os.path.join(SOFA_ROOT, "plugins", _plugin, "bin")
    if os.path.isdir(_d):
        os.add_dll_directory(_d)

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_BUILD = os.path.join(os.path.dirname(_HERE), "build")
if os.path.isdir(_PLUGIN_BUILD):
    os.add_dll_directory(_PLUGIN_BUILD)

# Register the plugin location so RequiredPlugin "Capsulorhexis" resolves whether
# this scene is launched by runSofa or directly by Python.
try:
    import SofaRuntime
    SofaRuntime.PluginRepository.addFirstPath(_PLUGIN_BUILD)
except Exception:  # noqa: BLE001  (SofaRuntime not importable yet in some contexts)
    pass

CAPSULE_OBJ = os.path.join(_HERE, "capsule.obj")

# outer-ring (rim) vertex indices from generate_capsule.py (R=5, N=10, M=60).
N, M = 10, 60
RIM_INDICES = list(range(1 + (N - 1) * M, N * M + 1))


def _ring_vertex(ring, j):
    """0-based vertex id of ring (1..N), angular index j (mod M)."""
    return 1 + (ring - 1) * M + (j % M)


# A small OFF-CENTRE patch (a flap on the +x side, rings 2-4). Peeling this one
# flap out of plane breaks the symmetry and seeds a single, localised radial tear
# -- like a surgeon grabbing the edge of the initial capsulotomy and lifting it.
GRAB_PATCH = [_ring_vertex(r, j) for r in (2, 3, 4) for j in (-2, -1, 0, 1, 2)]

PLUGINS = [
    "Sofa.Component.IO.Mesh",
    "Sofa.Component.StateContainer",
    "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward",
    "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.Mass",
    "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Visual",
    "Sofa.Component.AnimationLoop",
    "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
    "Sofa.GL.Component.Rendering2D",
    "Tearing",
    "Capsulorhexis",
]


def createScene(root):
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = 0.02
    for name in PLUGINS:
        root.addObject("RequiredPlugin", name=name)

    root.addObject("VisualStyle", displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.08, 0.09, 0.12, 1.0])
    # Oblique view so the out-of-plane peel (and the tear opening) is visible.
    root.addObject("InteractiveCamera", position=[7, -11, 13], lookAt=[0, 0, 1])

    root.addObject("MeshOBJLoader", name="loader", filename=CAPSULE_OBJ)

    cap = root.addChild("Capsule")
    # Heavier stiffness-proportional (Rayleigh) damping + more CG iterations kill
    # the high-frequency jitter of the stiff anisotropic membrane.
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.5, rayleighMass=0.1)
    cap.addObject("CGLinearSolver", iterations=150, tolerance=1e-9, threshold=1e-9)

    cap.addObject("TriangleSetTopologyContainer", name="topo", src="@../loader")
    cap.addObject("TriangleSetTopologyModifier")
    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")

    cap.addObject("MechanicalObject", name="dofs", src="@../loader")
    cap.addObject("DiagonalMass", massDensity=0.2)

    # Marchal Eq.1: transversely-isotropic co-rotational FEM (our topology-robust
    # TriangularFiberFEMForceField). fiberCenter at the disc centre makes the
    # fibers concentric (circumferential = tough along-fiber axis); the radial
    # direction is the weak transverse axis, so the tear runs radially, exactly as
    # in real capsulorhexis. Unlike the stock anisotropic FEM, this one keeps its
    # fiber/material correct as the tear remeshes.
    cap.addObject("TriangularFiberFEMForceField", name="fem",
                  method="large",
                  youngModulus=5000.0,              # along fiber (circumferential), tough
                  transverseYoungModulus=1000.0,    # transverse (radial), weak
                  poissonRatio=0.45,
                  fiberCenter=[[0.0, 0.0, 0.0]],
                  computePrincipalStress=True,
                  showFiber=True)

    cap.addObject("FixedProjectiveConstraint", indices=RIM_INDICES)

    # Marchal Eq.3-6: the fiber-based argmax-c tearing engine.
    cap.addObject("FiberFractureEngine", name="tearing",
                  topology="@topo",
                  input_position="@dofs.position",
                  fiberCenter=[[0.0, 0.0, 0.0]],   # match the FEM: concentric fibers
                  stressThreshold=60.0,
                  sigmaBarF=8.0,      # tough along the fibers
                  sigmaBarT=2.0,      # weak across the fibers (radial tear)
                  alpha=4.0,          # Eq.6 peak steepness
                  thetaP=60.0,        # limit backtracking -> smooth curvilinear tear
                  nbFractureMax=8,
                  step=5,
                  fractureMaxLength=0.0,
                  showFracturePath=True,
                  showTearableCandidates=True)

    # Scripted peel of one off-centre flap (a surgeon lifting the capsulotomy
    # edge): a slow, bounded out-of-plane + outward pull that concentrates stress
    # at the flap boundary and seeds a single radial tear. Displacement-controlled
    # so it cannot blow up the simulation.
    cap.addObject("LinearMovementProjectiveConstraint", name="pull",
                  indices=GRAB_PATCH, keyTimes=[0.0, 0.5, 3.0],
                  movements=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.5, 0.0, 4.0]])

    visu = cap.addChild("Visual")
    visu.addObject("OglModel", name="visual", color="red")
    visu.addObject("IdentityMapping", input="@../dofs", output="@visual")

    return root


def main():
    import Sofa
    import Sofa.Gui
    import SofaRuntime
    SofaRuntime.PluginRepository.addFirstPath(_PLUGIN_BUILD)
    SofaRuntime.importPlugin("Sofa.Component")
    SofaRuntime.importPlugin("Sofa.GL.Component.Rendering3D")
    SofaRuntime.importPlugin("SofaImGui")
    SofaRuntime.importPlugin("Tearing")
    SofaRuntime.importPlugin("Capsulorhexis")

    root = Sofa.Core.Node("root")
    createScene(root)
    Sofa.Simulation.init(root)
    Sofa.Gui.GUIManager.Init("capsule_ccc", "imgui")
    Sofa.Gui.GUIManager.createGUI(root, __file__)
    Sofa.Gui.GUIManager.SetDimension(1000, 760)
    Sofa.Gui.GUIManager.MainLoop(root)
    Sofa.Gui.GUIManager.closeGUI()


if __name__ == "__main__":
    main()
