"""Minimal runtime-tear verification: a scripted crack tip advances along a line by
SPLITTING mesh vertices at runtime, and the tear opens.

This isolates the one unproven piece -- the split-propagation bookkeeping -- away from the
full cap demo. No mouse, no stress criterion: a flat square membrane, its bottom edge
fixed, its top edge pulled up; a crack runs left->right along the midline, and the severed
top half lifts as the crack unzips.

How a crack propagates by vertex splitting (the bookkeeping):
  A crack is a path of vertices with a TIP. Every vertex the crack has already passed is
  DOUBLED -- a top copy and a bottom copy -- and the triangles above the midline use the
  top copy, those below use the bottom copy, so the two sides are no longer connected
  there. The TIP itself stays single (that is what still holds the two sides together).
  Advancing = split the old tip, make the next vertex the new tip. New vertices come from a
  pool of PRE-ALLOCATED spare points (the MO size is fixed at init), so no resize is needed.
  After each split we reinit the FEM / springs / mass so they pick up the new topology
  (verified: this does NOT crash -- unlike the stock SplitAlongPath).

Run:  runSofa -l SofaPython3 -g imgui -a scenes\tear_propagate.py   (or via a launcher)
"""
import os
import sys

SOFA_ROOT = os.environ.get("SOFA_ROOT", r"C:\SOFA\SOFA_v25.12.00_Win64")
os.environ["SOFA_ROOT"] = SOFA_ROOT
sys.path.insert(0, os.path.join(SOFA_ROOT, "plugins", "SofaPython3", "lib", "python3", "site-packages"))
for _p in (os.path.join(SOFA_ROOT, "bin"),):
    if os.path.isdir(_p):
        if hasattr(os, "add_dll_directory"):  # Windows only
            os.add_dll_directory(_p)
for _plugin in ("SofaPython3", "SofaImGui"):
    _d = os.path.join(SOFA_ROOT, "plugins", _plugin, "bin")
    if os.path.isdir(_d):
        if hasattr(os, "add_dll_directory"):  # Windows only
            os.add_dll_directory(_d)

# --- membrane grid + tear params --------------------------------------------
NX, NY = 15, 11          # grid resolution
YOUNG = 800.0
EDGE_K = 1500.0
MAX_STRETCH = 1.6        # hard cap: no edge may exceed this x rest length
TEAR_START_T = 1.0       # [s] crack starts advancing
TEAR_STEP_DT = 0.25      # [s] between crack advances (one vertex each)
# The top edge is pulled UP AND BACK (+y,+z): straight up just tilts the sheet into a
# ramp and the crack barely gapes; pulling the top half away peels it back so the crack
# opens into a clear mouth (measured max gape 1.6 vs 0.4 for straight-up).
PULL_MOVE = [0.0, 6.0, 4.0]
PULL_END_T = 9.0

PLUGINS = [
    "Sofa.Component.StateContainer", "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward", "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic", "Sofa.Component.SolidMechanics.Spring",
    "Sofa.Component.Mass", "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Visual", "Sofa.Component.AnimationLoop", "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def _grid():
    """Grid verts + spare pool, triangles, per-vertex grid-row j, and the crack path."""
    verts, vj = [], []
    for j in range(NY):
        for i in range(NX):
            verts.append([float(i), float(j), 0.0])
            vj.append(j)
    n_real = len(verts)
    spare = NX                      # one spare per midline vertex is enough
    verts += [[-99.0, -99.0, -99.0]] * spare
    vj += [-1] * spare

    def vid(i, j):
        return j * NX + i

    tris = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            tris.append([vid(i, j), vid(i + 1, j), vid(i, j + 1)])
            tris.append([vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)])
    mid = NY // 2
    crack_path = [vid(i, mid) for i in range(NX)]      # left -> right along the midline
    bottom = [vid(i, 0) for i in range(NX)]
    top = [vid(i, NY - 1) for i in range(NX)]
    return verts, vj, tris, n_real, mid, crack_path, bottom, top


def _make_controller(mo, topo, fem, springs, mass, vj, mid, crack_path, n_real):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo, self.fem, self.springs, self.mass = mo, topo, fem, springs, mass
            self.vj = list(vj)
            self.mid = mid
            self.path = crack_path
            self.tip = 1                       # index into path; path[0] is the free edge
            self.next_spare = n_real
            self.last_tear = -1e9
            self.split_pairs = []              # (top_vid, bottom_vid) for gap logging
            # cache rest edge lengths for the strain clamp (built lazily)
            self.edges = None
            self.edge_rest = None

        def _split_vertex(self, v):
            """Double vertex v: keep v for the ABOVE-midline triangles, give a fresh spare
            to the BELOW-midline triangles. Returns the spare (bottom copy)."""
            if self.next_spare >= len(self.mo.position.value):
                return None
            spare = self.next_spare
            self.next_spare += 1
            tris = np.array(self.topo.triangles.value)
            for k in range(len(tris)):
                if v in tris[k]:
                    mean_j = np.mean([self.vj[x] for x in tris[k]])
                    if mean_j < self.mid:                 # below the midline
                        tris[k] = [spare if x == v else x for x in tris[k]]
            # spare inherits v's position AND rest position, and its grid row
            P = np.array(self.mo.position.value); R = np.array(self.mo.rest_position.value)
            P[spare] = P[v]; R[spare] = R[v]
            self.vj[spare] = self.vj[v]
            self.mo.position.value = P.tolist()
            self.mo.rest_position.value = R.tolist()
            self.topo.triangles.value = tris.tolist()
            self.fem.reinit(); self.springs.reinit(); self.mass.reinit()
            self.edges = None                             # rest edges changed
            return spare

        def onAnimateBeginEvent(self, event):
            t = self.mo.getContext().getTime()
            if (t >= TEAR_START_T and self.tip < len(self.path) - 1
                    and t - self.last_tear >= TEAR_STEP_DT):
                self.last_tear = t
                v = self.path[self.tip]                   # split the CURRENT tip vertex
                sp = self._split_vertex(v)
                self.tip += 1
                if sp is not None:
                    self.split_pairs.append((v, sp))
                    P = np.array(self.mo.position.value)
                    gaps = [float(np.linalg.norm(P[a] - P[b])) for a, b in self.split_pairs]
                    print(f"[Tear] t={t:5.2f} tip->{self.tip}/{len(self.path)-1} "
                          f"split v{v} (spare {sp}); crack length {self.tip-1}, "
                          f"max side-gap={max(gaps):.3f}")

        def onAnimateEndEvent(self, event):
            # strain clamp: no edge past MAX_STRETCH x rest (keeps it from crushing)
            if MAX_STRETCH <= 0:
                return
            if self.edges is None:
                tris = np.array(self.topo.triangles.value)
                E = set()
                for a, b, c in tris:
                    for u, w in ((a, b), (b, c), (c, a)):
                        E.add((min(u, w), max(u, w)))
                self.edges = np.array(sorted(E), dtype=int)
                R = np.array(self.mo.rest_position.value)
                self.edge_rest = np.linalg.norm(R[self.edges[:, 1]] - R[self.edges[:, 0]], axis=1)
            P = np.array(self.mo.position.value)
            e0, e1 = self.edges[:, 0], self.edges[:, 1]
            limit = self.edge_rest * MAX_STRETCH
            for _ in range(3):
                d = P[e1] - P[e0]; L = np.linalg.norm(d, axis=1)
                over = L > limit
                if not over.any():
                    break
                n = d[over] / L[over][:, None]; ex = (L[over] - limit[over])[:, None]
                np.add.at(P, e0[over], 0.5 * ex * n); np.add.at(P, e1[over], -0.5 * ex * n)
            self.mo.position.value = P.tolist()

    return _C(name="TearController")


def createScene(root):
    import Sofa
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = 0.02
    for name in PLUGINS:
        root.addObject("RequiredPlugin", name=name)
    root.addObject("VisualStyle", displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.09, 0.10, 0.13, 1.0])
    root.addObject("InteractiveCamera", position=[NX / 2, NY / 2, 22], lookAt=[NX / 2, NY / 2, 0])

    verts, vj, tris, n_real, mid, crack_path, bottom, top = _grid()

    m = root.addChild("Membrane")
    m.addObject("EulerImplicitSolver", rayleighStiffness=0.2, rayleighMass=0.2)
    m.addObject("CGLinearSolver", iterations=50, tolerance=1e-8, threshold=1e-8)
    topo = m.addObject("TriangleSetTopologyContainer", name="topo",
                       position=verts, triangles=tris)
    m.addObject("TriangleSetTopologyModifier")
    m.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    mo = m.addObject("MechanicalObject", name="mo", position=verts)
    mass = m.addObject("DiagonalMass", massDensity=1.0)
    fem = m.addObject("TriangularFEMForceField", name="fem", method="large",
                      youngModulus=YOUNG, poissonRatio=0.3)
    springs = m.addObject("MeshSpringForceField", name="springs",
                          linesStiffness=EDGE_K, linesDamping=1.0)
    m.addObject("FixedProjectiveConstraint", indices=bottom, showObject=False)
    m.addObject("LinearMovementProjectiveConstraint", name="pull", indices=top,
                keyTimes=[0.0, TEAR_START_T, PULL_END_T, 60.0],
                movements=[[0, 0, 0], [0, 0, 0], PULL_MOVE, PULL_MOVE])
    m.addObject(_make_controller(mo, topo, fem, springs, mass, vj, mid, crack_path, n_real))

    visu = m.addChild("Visual")
    visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.82, 1.0])
    visu.addObject("IdentityMapping", input="@../mo", output="@visual")
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
    Sofa.Gui.GUIManager.Init("tear_propagate", "imgui")
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
