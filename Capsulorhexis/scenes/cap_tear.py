"""Stress-driven tearing on the CURVED CAP (the real capsulorhexis geometry).

This ports the mechanism proven flat in tear_stress.py onto the oblate cap-on-lens from
generate_cap.py. The tear RULE is identical and lives in one place (onAnimateBeginEvent):

    a crack has a TIP; each check we compute sigma1 (principal stress) at the hottest
    triangle touching the tip; if that sigma1 exceeds STRESS_THRESHOLD the tip advances by
    ONE vertex, in the direction PERPENDICULAR to sigma1 (Rankine). The crack PATH is never
    scripted -- it falls out of the stress field.

Why the SAME rule gives a straight cut on the flat sheet but a CURVED (curvilinear) tear
here: with the outer rim fixed (the zonular fibres) and the central disc lifted, the
membrane is in RADIAL tension, so sigma1 points radially and perpendicular-to-sigma1 is
CIRCUMFERENTIAL -- the crack curves around, which is exactly a continuous curvilinear
capsulorhexis (CCC). Nothing in the code draws a circle.

The three gotchas learned on the flat demo are carried over:
  * spare split-vertices parked INSIDE the mesh (not far away) so the GUI auto-frames it;
  * the new connectivity is pushed to the OglModel each split so the crack is VISIBLE;
  * sigma1 uses a per-triangle guarded 2x2 inverse so a degenerate triangle cannot crash.

v1 loads the cap with a SCRIPTED central lift so the curved tear is visible with no mouse.
Mouse-driven tearing (drag the flap like forceps) is the next step.

Run:  .\scenes\run_captear.ps1
"""
import math
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
import generate_cap as G   # A, C, Z0, R, EDGE_LEN, _build_raw()

# --- material (same feel as the flat paper / cap_membrane) ------------------
YOUNG = 1200.0            # in-plane stiffness ("paper", not stretchy)
POISSON = 0.3
EDGE_STIFFNESS = 2500.0   # per-edge springs -> triangles keep their size
BEND_STIFFNESS = 15.0     # low = the freed flap folds over instead of standing rigid
DAMPING = 2.0
LENS_REPULSION = 2000.0   # analytic lens obstacle (do NOT raise -> penalty blow-up)
MAX_STRETCH = 1.6         # hard edge-length cap (keeps the mesh from crushing)

# --- tear rule --------------------------------------------------------------
# sigma1 ~= YOUNG * local strain, so 90/1200 ~= 7.5% local stretch at the tip triggers a
# step. Lowered from 180 so a GENTLE mouse pull can drive the crack (the scripted symmetric
# lift used to slam sigma1 past 1000, which hid how high 180 really was for hand pulling).
STRESS_THRESHOLD = 90.0
TEAR_CHECK_DT = 0.12      # [s] between tip-advance checks
TEAR_SETTLE_T = 0.8       # [s] no tearing before this -> the mesh settles on load-in first
                          # (otherwise a startup transient at the pinned seed tears once)

# --- loading ----------------------------------------------------------------
# PULL_MODE decides WHERE the load comes from -- and this is the whole point of the user's
# question "why a fixed radius / circle?": the crack path is ALWAYS just perpendicular-to-
# sigma1; the SHAPE of the load is what makes the path a circle or not.
#   "mouse" : no scripted pull -- YOU drag the flap with Shift+left (forceps). The stress
#             field is whatever your pull makes it, so the crack follows your hand, NOT a
#             circle. This is the real free-tear mode (default).
#   "disc"  : symmetric -- rim fixed + whole central disc lifted. Axisymmetric stress ->
#             sigma1 radial everywhere -> crack runs circumferential at ~constant radius.
#             The "fixed circle" is a CONSEQUENCE of this symmetry, not a scripted path.
#   "patch" : a small OFF-CENTRE patch is pulled (a scripted "forceps grip"). Asymmetric
#             stress -> the crack follows the patch, NOT a circle. Used to prove the point
#             headlessly (no mouse needed).
PULL_MODE = "mouse"
LIFT_RADIUS = 4.5         # "disc" mode: nodes with planar r < this get lifted
LIFT_HEIGHT = 6.0         # "disc"/"patch" pull height (+z)
PULL_START_T = 1.0
PULL_END_T = 12.0
RIM_FRAC = 0.9            # nodes with r > RIM_FRAC*R are anchored (zonular fibres)

# --- mouse (forceps) --------------------------------------------------------
ENABLE_MOUSE = True
MOUSE_STIFFNESS = 1500.0  # Shift+left-drag attach spring; no adhesion here, so this alone
                          # must load the tip -> a bit stiffer than cap_membrane's 1000.
ALARM_DISTANCE = 0.40 * G.EDGE_LEN
CONTACT_DISTANCE = 0.20 * G.EDGE_LEN

PLUGINS = [
    "Sofa.Component.StateContainer", "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward", "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.FEM.Elastic", "Sofa.Component.SolidMechanics.Spring",
    "Sofa.Component.Mass", "Sofa.Component.Constraint.Projective",
    "Sofa.Component.MechanicalLoad", "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Collision.Detection.Algorithm",
    "Sofa.Component.Collision.Detection.Intersection",
    "Sofa.Component.Collision.Geometry",
    "Sofa.Component.Collision.Response.Contact",
    "Sofa.GUI.Component",             # AttachBodyButtonSetting (mouse-pull strength)
    "Sofa.Component.Visual", "Sofa.Component.AnimationLoop", "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def sigma1_of(pos, rest, tris, E, nu):
    """Per-triangle principal stress sigma1 and its 3D direction (identical maths to
    cap_membrane.principal_stress / tear_stress.sigma1_of)."""
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
    # Per-triangle guarded 2x2 inverse: a degenerate rest triangle must not make the
    # batched inverse raise for the whole array.
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


def _geometry():
    """Continuous cap (NO pre-slit) + a spare pool parked at the apex, plus the vertex
    sets the scene needs: rim anchor, central lift disc, and the crack seed."""
    verts, faces, ring_base, ring_of = G._build_raw()
    verts = [list(v) for v in verts]
    n_real = len(verts)
    apex = list(verts[0])                      # park spares here (inside the bbox)
    verts += [list(apex) for _ in range(n_real)]

    import numpy as np
    P = np.array(verts[:n_real])
    r = np.hypot(P[:, 0], P[:, 1])
    rim = [i for i in range(n_real) if r[i] > RIM_FRAC * G.R]
    disc = [i for i in range(n_real) if r[i] < LIFT_RADIUS]

    # Seed the crack at a RIM vertex (an open boundary -> a clean half-fan to split) and
    # its most-inward neighbour. Pick the rim vertex near angle 180 deg so the crack has
    # the whole cap to run across.
    adj = {}
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
    ang = np.arctan2(P[:, 1], P[:, 0])
    start_b = min(rim, key=lambda i: abs((ang[i] - math.pi + math.pi) % (2 * math.pi) - math.pi))
    # inward neighbour = neighbour with the smallest planar radius
    start_tip = min((v for v in adj[start_b] if v < n_real), key=lambda v: r[v])
    return verts, faces, n_real, rim, disc, start_b, start_tip


def _make_controller(mo, topo, fem, springs, mass, visual, n_real, start_b, start_tip):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo = mo, topo
            self.fem, self.springs, self.mass = fem, springs, mass
            self.visual = visual
            self.next_spare = n_real
            self.crack = [start_b, start_tip]
            self.last_check = -1e9
            self.pairs = []
            self.edges = None
            self.edge_rest = None
            self.adj = None
            self.stopped = False

        def _build_adj(self):
            tris = np.array(self.topo.triangles.value)
            adj = {}
            for a, b, c in tris:
                for u, v in ((a, b), (b, c), (c, a)):
                    adj.setdefault(int(u), set()).add(int(v))
                    adj.setdefault(int(v), set()).add(int(u))
            self.adj = adj

        def _tip_normal(self, P, tris, touch):
            n = np.zeros(3)
            for k in touch:
                a, b, c = P[tris[k]]
                n += np.cross(b - a, c - a)
            nn = np.linalg.norm(n)
            return n / nn if nn > 1e-9 else np.array([0.0, 0.0, 1.0])

        def _split_tip(self, vtip, vprev, vnext):
            """Split vtip's triangle fan along the two crack edges (to vprev, to vnext).
            One lip keeps vtip, the other gets a fresh spare. Identical to tear_stress."""
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
            nrm = self._tip_normal(P, tris, touch)
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
                if ac > a_prev:
                    tris[k] = [spare if x == vtip else x for x in tris[k]]
                    moved += 1
            if moved == 0 or moved == len(touch):
                return None
            self.next_spare += 1
            P[spare] = P[vtip]
            R[spare] = R[vtip]
            self.mo.position.value = P.tolist()
            self.mo.rest_position.value = R.tolist()
            self.topo.triangles.value = tris.tolist()
            if self.visual is not None:
                self.visual.triangles.value = tris.tolist()
            self.fem.reinit(); self.springs.reinit(); self.mass.reinit()
            self.edges = None
            return spare

        def onAnimateBeginEvent(self, event):
            t = self.mo.getContext().getTime()
            if self.stopped or t < TEAR_SETTLE_T or t - self.last_check < TEAR_CHECK_DT:
                return
            self.last_check = t
            if self.adj is None:
                self._build_adj()
            P = np.array(self.mo.position.value)
            R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            s1, sdir = sigma1_of(P, R, tris, YOUNG, POISSON)

            tip, prev = self.crack[-1], self.crack[-2]
            touch = [k for k in range(len(tris)) if tip in tris[k]]
            if not touch:
                return
            khot = max(touch, key=lambda k: s1[k])
            if s1[khot] < STRESS_THRESHOLD:
                return                            # tip not stressed enough yet

            # crack runs PERPENDICULAR to sigma1, in the tip's LOCAL tangent plane (so it
            # follows the curved surface), forced FORWARD (away from prev).
            nrm = self._tip_normal(P, tris, touch)
            d = sdir[khot]
            perp = np.cross(nrm, d)
            if np.linalg.norm(perp) < 1e-6:
                return
            perp = perp / np.linalg.norm(perp)
            fwd = P[tip] - P[prev]
            if np.dot(perp, fwd) < 0:
                perp = -perp
            cands = [v for v in self.adj.get(tip, ()) if v not in self.crack and v < n_real]
            if not cands:
                self.stopped = True
                print(f"[Tear] t={t:.2f} reached a boundary/dead-end; stopping")
                return

            def align(v):
                w = P[v] - P[tip]
                return float(np.dot(w / (np.linalg.norm(w) + 1e-9), perp))

            vnext = max(cands, key=align)
            if align(vnext) < 0.2:
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
            rr = float(np.hypot(P[vnext, 0], P[vnext, 1]))
            aa = float(np.degrees(np.arctan2(P[vnext, 1], P[vnext, 0])))
            print(f"[Tear] t={t:5.2f} sigma1={s1[khot]:6.0f} tip v{tip}->v{vnext} "
                  f"(r={rr:4.1f} ang={aa:6.1f}deg z={P[vnext,2]:4.1f}); "
                  f"crack len={len(self.pairs)} max-gap={max(gaps):.2f}")

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

    return _C(name="CapTearController")


def createScene(root):
    import Sofa
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = 0.02
    _pl = root.addChild("RequiredPlugins")
    for name in PLUGINS:
        _pl.addObject("RequiredPlugin", name=name)
    root.addObject("VisualStyle", displayFlags="showVisual showWireframe showBehaviorModels")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    root.addObject("InteractiveCamera", position=[10.0, -10.0, 11.0], lookAt=[0, 0, 0])

    if ENABLE_MOUSE:
        # Shift+left-drag: SOFA rays from the camera through the cursor, grabs the nearest
        # cap triangle, and attaches a spring of MOUSE_STIFFNESS between it and a virtual
        # mouse particle you drag in the screen plane. There is NO adhesion here, so this
        # spring alone loads the crack tip -> pull the flap near the tip and it tears.
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=ALARM_DISTANCE,
                       contactDistance=CONTACT_DISTANCE)
        root.addObject("AttachBodyButtonSetting", stiffness=MOUSE_STIFFNESS, arrowSize=0.3)

    verts, faces, n_real, rim, disc, sb, stip = _geometry()

    # The lens (visual obstacle the flap folds up over).
    lens = root.addChild("Lens")
    lens.addObject("MeshOBJLoader", name="bloader", filename=os.path.join(_HERE, "lens.obj"))
    lens.addObject("OglModel", name="lensVisual", src="@bloader", color=[0.45, 0.55, 0.75, 0.45])

    cap = root.addChild("Cap")
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.2, rayleighMass=0.2)
    cap.addObject("CGLinearSolver", iterations=30, tolerance=1e-8, threshold=1e-8)
    topo = cap.addObject("TriangleSetTopologyContainer", name="topo",
                         position=verts, triangles=faces)
    cap.addObject("TriangleSetTopologyModifier")
    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    mo = cap.addObject("MechanicalObject", name="Mo", position=verts)
    mass = cap.addObject("DiagonalMass", massDensity=1.0)
    fem = cap.addObject("TriangularFEMForceField", name="FEM", method="large",
                        youngModulus=YOUNG, poissonRatio=POISSON)
    springs = cap.addObject("MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    cap.addObject("TriangularBendingSprings", name="Bending", stiffness=BEND_STIFFNESS)
    cap.addObject("UniformVelocityDampingForceField", dampingCoefficient=DAMPING)
    cap.addObject("EllipsoidForceField", name="LensObstacle",
                  center=[0.0, 0.0, G.Z0], vradius=[G.A, G.A, G.C],
                  stiffness=LENS_REPULSION, damping=1.0)

    # Zonular anchor: the outer rim is held fixed (so a pull tensions the membrane instead
    # of just dragging the whole cap away).
    cap.addObject("FixedProjectiveConstraint", name="RimAnchor", indices=rim, showObject=False)

    # WHERE the load comes from -- see PULL_MODE. The crack rule never changes; only the
    # shape of the load does, and THAT is what makes the path a circle ("disc") or free
    # ("mouse"/"patch").
    if PULL_MODE == "disc":
        cap.addObject("LinearMovementProjectiveConstraint", name="lift", indices=disc,
                      keyTimes=[0.0, PULL_START_T, PULL_END_T, 60.0],
                      movements=[[0, 0, 0], [0, 0, 0], [0, 0, LIFT_HEIGHT], [0, 0, LIFT_HEIGHT]])
    elif PULL_MODE == "patch":
        # ASYMMETRIC disc pull: lift the disc AND drag it sideways (+x). Same disc nodes as
        # "disc" (so they never overlap the fixed rim -> no constraint conflict), but the
        # sideways component breaks the axisymmetry, so sigma1 is no longer purely radial
        # and the crack does NOT hold a constant radius -> proof the path is not a hardcoded
        # circle, it is just perpendicular-to-sigma1 under whatever load is applied.
        cap.addObject("LinearMovementProjectiveConstraint", name="grip", indices=disc,
                      keyTimes=[0.0, PULL_START_T, PULL_END_T, 60.0],
                      movements=[[0, 0, 0], [0, 0, 0],
                                 [4.0, 0, LIFT_HEIGHT], [4.0, 0, LIFT_HEIGHT]])
    # PULL_MODE == "mouse": nothing scripted -- YOU drag it.

    if ENABLE_MOUSE:
        # The collision model the mouse ray picks (selfCollision off: cheap, and safer with
        # the runtime topology changes from tearing).
        cap.addObject("TriangleCollisionModel", selfCollision=False, contactStiffness=200.0)

    visu = cap.addChild("Visual")
    oglm = visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.82, 1.0], triangles=faces)
    visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

    cap.addObject(_make_controller(mo, topo, fem, springs, mass, oglm, n_real, sb, stip))

    print("=" * 68)
    print(" cap_tear.py  |  FREE stress-driven tearing (NO hardcoded circle)")
    print(f" PULL_MODE={PULL_MODE!r}  threshold={STRESS_THRESHOLD}  mouse={ENABLE_MOUSE}")
    if PULL_MODE == "mouse":
        print(" Shift + LEFT-DRAG the flap near the nick (outer edge, ~180deg) to tear.")
        print(" The crack follows YOUR pull. It prints [Tear] lines (never [Peel]).")
    print("=" * 68)
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
    Sofa.Gui.GUIManager.Init("cap_tear", "imgui")
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
