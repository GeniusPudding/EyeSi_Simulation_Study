"""Stress-driven runtime tearing: the crack path EMERGES from the stress field, not a
script. A flat membrane is pulled; at the crack tip we compute sigma1; if it exceeds a
threshold the tip advances one vertex in the direction PERPENDICULAR to sigma1 (Rankine:
a crack runs perpendicular to the max principal stress). The path curves according to the
stress -- this is the mechanism behind a curvilinear capsulorhexis.

Builds on tear_propagate.py (which proved runtime vertex-splitting works). The new piece is
a GENERAL tip split for an arbitrary crack direction: the fan of triangles around the tip
is divided by the two crack edges (to the previous vertex and to the next vertex) into two
lips; one lip keeps the vertex, the other gets a pre-allocated spare.

Run:  runSofa -l SofaPython3 -g imgui -a scenes\tear_stress.py   (or run_stress.ps1)
"""
import math
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

NX, NY = 17, 13
YOUNG = 800.0
EDGE_K = 1500.0
MAX_STRETCH = 1.6
STRESS_THRESHOLD = 120.0    # sigma1 the tip must exceed to advance (~15% local stretch
                            # at YOUNG=800; lower = tears more easily / sooner)
TEAR_CHECK_DT = 0.15        # [s] between tip advance checks
PULL_MOVE = [0.0, 6.0, 4.0]  # top edge pulled up-and-back to load the sheet
PULL_START_T = 1.0
PULL_END_T = 12.0

PLUGINS = [
    "Sofa.Component.StateContainer", "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward", "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic", "Sofa.Component.SolidMechanics.Spring",
    "Sofa.Component.Mass", "Sofa.Component.Constraint.Projective",
    "Sofa.Component.Mapping.Linear", "Sofa.Component.Visual",
    "Sofa.Component.AnimationLoop", "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def sigma1_of(pos, rest, tris, E, nu):
    """Per-triangle sigma1 and its 3D direction (same maths as cap_membrane)."""
    import numpy as np

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
    # Per-triangle guarded 2x2 inverse: one degenerate rest triangle must not make the
    # batched inverse raise for the whole array (see cap_membrane.py for the full note).
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
    ang = 0.5 * np.arctan2(2.0 * sxy, np.maximum(sxx - syy, 1e-12))
    d3 = np.cos(ang)[:, None] * xc + np.sin(ang)[:, None] * yc
    return s1, d3


def _grid():
    # Centre the grid on the ORIGIN so it frames correctly regardless of which camera the
    # GUI ends up using (SofaImGui's default camera looks at the origin and ignores a
    # scripted InteractiveCamera lookAt -- an off-origin grid lands in a screen corner).
    cx, cy = (NX - 1) * 0.5, (NY - 1) * 0.5
    verts = []
    for j in range(NY):
        for i in range(NX):
            verts.append([float(i) - cx, float(j) - cy, 0.0])
    n_real = len(verts)
    # Spare pool for runtime splits. Park them at the ORIGIN (inside the sheet), NOT far
    # away: the GUI's auto-frame includes every MechanicalObject point in the bounding box,
    # so spares at e.g. (-99,-99,-99) blow the bbox up and the camera zooms miles out,
    # making the sheet a speck. A split overwrites the spare's position anyway.
    verts += [[0.0, 0.0, 0.0]] * (NX * NY)            # generous spare pool

    def vid(i, j):
        return j * NX + i

    tris = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            tris.append([vid(i, j), vid(i + 1, j), vid(i, j + 1)])
            tris.append([vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)])
    bottom = [vid(i, 0) for i in range(NX)]
    top = [vid(i, NY - 1) for i in range(NX)]
    # start the crack from the middle of the LEFT edge, one vertex in
    start_boundary = vid(0, NY // 2)
    start_tip = vid(1, NY // 2)
    return verts, tris, n_real, bottom, top, start_boundary, start_tip


def _make_controller(mo, topo, fem, springs, mass, n_real, start_b, start_tip, visual):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo = mo, topo
            self.fem, self.springs, self.mass = fem, springs, mass
            self.visual = visual
            self.next_spare = n_real
            self.crack = [start_b, start_tip]     # [.., prev, tip]
            self.last_check = -1e9
            self.pairs = []                       # (orig, spare) for gap logging
            self.edges = None
            self.adj = None                       # vertex -> set(neighbour vertices)
            self.stopped = False

        def _build_adj(self):
            tris = np.array(self.topo.triangles.value)
            adj = {}
            for a, b, c in tris:
                for u, v in ((a, b), (b, c), (c, a)):
                    adj.setdefault(int(u), set()).add(int(v))
                    adj.setdefault(int(v), set()).add(int(u))
            self.adj = adj

        def _split_tip(self, vtip, vprev, vnext):
            """Split vtip's triangle fan along the two crack edges (to vprev, to vnext)."""
            if self.next_spare >= len(self.mo.position.value):
                return None
            spare = self.next_spare
            P = np.array(self.mo.position.value)
            R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            touch = [k for k in range(len(tris)) if vtip in tris[k]]
            if len(touch) < 2:
                return None
            o = P[vtip]
            nrm = np.zeros(3)
            for k in touch:
                a, b, c = P[tris[k]]
                nrm += np.cross(b - a, c - a)
            nrm = nrm / (np.linalg.norm(nrm) + 1e-9)
            xax = P[vnext] - o
            xax = xax - nrm * np.dot(xax, nrm)
            xax = xax / (np.linalg.norm(xax) + 1e-9)
            yax = np.cross(nrm, xax)

            def ang(pt):
                w = pt - o
                return math.atan2(float(np.dot(w, yax)), float(np.dot(w, xax))) % (2 * math.pi)

            a_prev = ang(P[vprev])               # a_next == 0 by construction
            moved = 0
            for k in touch:
                ac = ang(P[tris[k]].mean(axis=0))
                if ac > a_prev:                  # the lip on the far side of vprev
                    tris[k] = [spare if x == vtip else x for x in tris[k]]
                    moved += 1
            if moved == 0 or moved == len(touch):
                return None                      # cut edges didn't separate the fan
            self.next_spare += 1
            P[spare] = P[vtip]
            R[spare] = R[vtip]
            self.mo.position.value = P.tolist()
            self.mo.rest_position.value = R.tolist()
            self.topo.triangles.value = tris.tolist()
            # Push the new connectivity to the OglModel too: we edit topo.triangles
            # directly (not via the topology-modifier API), so the visual model never gets
            # a topology-change event and would keep drawing the OLD triangles -- the crack
            # opens mechanically but the rendered skin stays bridged. Setting its triangle
            # Data makes the gap actually show.
            if self.visual is not None:
                self.visual.triangles.value = tris.tolist()
            self.fem.reinit(); self.springs.reinit(); self.mass.reinit()
            self.edges = None
            return spare

        def onAnimateBeginEvent(self, event):
            t = self.mo.getContext().getTime()
            if self.stopped or t - self.last_check < TEAR_CHECK_DT:
                return
            self.last_check = t
            if self.adj is None:
                self._build_adj()
            P = np.array(self.mo.position.value)
            R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            s1, sdir = sigma1_of(P, R, tris, YOUNG, 0.3)

            tip, prev = self.crack[-1], self.crack[-2]
            touch = [k for k in range(len(tris)) if tip in tris[k]]
            if not touch:
                return
            khot = max(touch, key=lambda k: s1[k])   # hottest triangle at the tip
            if s1[khot] < STRESS_THRESHOLD:
                return                                # not stressed enough yet

            # crack runs PERPENDICULAR to sigma1, forced FORWARD (away from prev)
            d = sdir[khot]
            perp = np.cross(np.array([0.0, 0.0, 1.0]), d)   # membrane ~ in-plane; z up
            if np.linalg.norm(perp) < 1e-6:
                return
            perp = perp / np.linalg.norm(perp)
            fwd = P[tip] - P[prev]
            if np.dot(perp, fwd) < 0:
                perp = -perp
            # pick the tip neighbour best aligned with perp, not already cracked
            cands = [v for v in self.adj.get(tip, ()) if v not in self.crack and v < n_real]
            if not cands:
                self.stopped = True
                print(f"[Tear] t={t:.2f} crack reached a boundary/dead-end; stopping")
                return
            def align(v):
                w = P[v] - P[tip]
                return float(np.dot(w / (np.linalg.norm(w) + 1e-9), perp))
            vnext = max(cands, key=align)
            if align(vnext) < 0.2:                    # no forward neighbour -> stop
                self.stopped = True
                print(f"[Tear] t={t:.2f} no forward direction; stopping")
                return
            sp = self._split_tip(tip, prev, vnext)
            if sp is None:
                self.stopped = True
                print(f"[Tear] t={t:.2f} split failed at v{tip}; stopping")
                return
            self.pairs.append((tip, sp))
            self.crack.append(vnext)
            P = np.array(self.mo.position.value)
            gaps = [float(np.linalg.norm(P[a] - P[b])) for a, b in self.pairs]
            print(f"[Tear] t={t:5.2f} sigma1={s1[khot]:6.0f} tip v{tip}->v{vnext} "
                  f"(at x={P[vnext,0]:.1f} y={P[vnext,1]:.1f}); crack len={len(self.pairs)} "
                  f"max-gap={max(gaps):.2f}")

        def onAnimateEndEvent(self, event):
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
                dd = P[e1] - P[e0]
                L = np.linalg.norm(dd, axis=1)
                over = L > limit
                if not over.any():
                    break
                n = dd[over] / L[over][:, None]
                ex = (L[over] - limit[over])[:, None]
                np.add.at(P, e0[over], 0.5 * ex * n)
                np.add.at(P, e1[over], -0.5 * ex * n)
            self.mo.position.value = P.tolist()

    return _C(name="StressTearController")


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
    root.addObject("InteractiveCamera", position=[0, 0, 28], lookAt=[0, 0, 0])

    verts, tris, n_real, bottom, top, sb, stip = _grid()
    m = root.addChild("Membrane")
    m.addObject("EulerImplicitSolver", rayleighStiffness=0.2, rayleighMass=0.2)
    m.addObject("CGLinearSolver", iterations=50, tolerance=1e-8, threshold=1e-8)
    topo = m.addObject("TriangleSetTopologyContainer", name="topo", position=verts, triangles=tris)
    m.addObject("TriangleSetTopologyModifier")
    m.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    mo = m.addObject("MechanicalObject", name="mo", position=verts)
    mass = m.addObject("DiagonalMass", massDensity=1.0)
    fem = m.addObject("TriangularFEMForceField", name="fem", method="large",
                      youngModulus=YOUNG, poissonRatio=0.3)
    springs = m.addObject("MeshSpringForceField", name="springs", linesStiffness=EDGE_K, linesDamping=1.0)
    m.addObject("FixedProjectiveConstraint", indices=bottom, showObject=False)
    m.addObject("LinearMovementProjectiveConstraint", name="pull", indices=top,
                keyTimes=[0.0, PULL_START_T, PULL_END_T, 60.0],
                movements=[[0, 0, 0], [0, 0, 0], PULL_MOVE, PULL_MOVE])

    visu = m.addChild("Visual")
    oglm = visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.82, 1.0],
                          triangles=tris)
    visu.addObject("IdentityMapping", input="@../mo", output="@visual")

    m.addObject(_make_controller(mo, topo, fem, springs, mass, n_real, sb, stip, oglm))
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
    Sofa.Gui.GUIManager.Init("tear_stress", "imgui")
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
