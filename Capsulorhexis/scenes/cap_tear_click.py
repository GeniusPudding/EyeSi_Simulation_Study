"""CLICK-driven capsulorhexis tear -- stable by construction (no penalty-spring mouse).

Why this exists: SofaImGui's built-in mouse is a penalty spring whose force is UNBOUNDED, so a
hard pull diverges the solver and the mesh big-bangs. And it delivers only click DOWN events to
a Python controller (no continuous drag). So instead:

  - We read the mouse ourselves (onMouseEvent), un-project the click through the camera to a
    world point on the membrane, and the crack tip ADVANCES toward that point (geometric).
  - The freed inner lip is nudged up KINEMATICALLY (a clamped position move, NOT a force), so it
    peels visibly. A kinematic move injects no unbounded force -> the solver CANNOT diverge.
  - Membrane = mass-spring (never null-determinants). Rim fixed; tear the middle.

Interaction: left-CLICK a spot on the ring where you want the tear to go next; it tears toward
there and the flap peels. Click your way around the circle -- like leading with the forceps.

Run:  .\scenes\run_captear_click.ps1
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
import generate_cap as G

# --- physics (mass-spring, robust) -------------------------------------------
EDGE_STIFFNESS = 3000.0
BEND_STIFFNESS = 8.0
DAMPING = 3.0
LENS_REPULSION = 2000.0
MAX_STRETCH = 1.5
MAX_SPEED = 25.0
MAX_DISP = 8.0
AREA_MIN_FRAC = 0.30

# --- geometry / seed ---------------------------------------------------------
NICK_RADIUS = 5.0
TEAR_R_MIN = 3.0
TEAR_R_MAX = 6.0
RIM_FRAC = 0.9
PRE_TEAR_DEG = 60.0

# --- click-driven tear -------------------------------------------------------
ADVANCE_PER_CLICK = 8      # how many vertices one click tears toward the target
CLICK_PLANE_Z = 1.0        # the membrane plane the click ray is intersected with
PEEL_LIFT = 0.6            # how far (kinematic, clamped) the fresh inner lip is nudged up
PEEL_STEP = 0.15           # max kinematic move per step (clamped -> cannot explode)
LIFT_AFTER_CRACKLEN = 90   # after this, buoyancy lifts the freed disc to reveal the hole
DISC_LIFT_Z = 12.0

PLUGINS = [
    "Sofa.Component.StateContainer", "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward", "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.Spring", "Sofa.Component.Mass",
    "Sofa.Component.Constraint.Projective", "Sofa.Component.MechanicalLoad",
    "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Visual", "Sofa.Component.AnimationLoop", "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def _geometry():
    verts, faces, ring_base, ring_of = G._build_raw()
    verts = [list(v) for v in verts]
    n_real = len(verts)
    verts += [list(verts[0]) for _ in range(n_real)]
    import numpy as np
    P = np.array(verts[:n_real])
    r = np.hypot(P[:, 0], P[:, 1])
    rim = [i for i in range(n_real) if r[i] > RIM_FRAC * G.R]
    disc = [i for i in range(n_real) if r[i] < 4.5]
    adj = {}
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
    ang = np.arctan2(P[:, 1], P[:, 0])
    cand = [i for i in range(n_real) if abs(r[i] - NICK_RADIUS) < 0.5 and abs(ang[i]) < 0.35]
    if not cand:
        cand = [min(range(n_real), key=lambda i: abs(r[i] - NICK_RADIUS) + abs(ang[i]))]
    seed_v = min(cand, key=lambda i: abs(r[i] - NICK_RADIUS))
    nb = [v for v in adj[seed_v] if v < n_real]
    v_a = max(nb, key=lambda v: P[v, 1] - P[seed_v, 1])
    v0 = min(nb, key=lambda v: P[v, 1] - P[seed_v, 1])
    return verts, faces, n_real, rim, disc, seed_v, v_a, v0


def _make_controller(mo, topo, springs, mass, visual, cam, n_real, seed_v, v_a, v0, root):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo, self.springs, self.mass = mo, topo, springs, mass
            self.visual, self.cam, self.root = visual, cam, root
            self.next_spare = n_real
            self.crack = [v_a, seed_v]
            self.first_fwd = v0
            self.seeded = False
            self.pairs = []
            self.adj = None
            self.edges = self.edge_rest = self.tri_arr = self.rest_area = self._rest_r = None
            self.stopped = False
            self.click_world = None       # pending click target (world xy) to tear toward
            self.peel = []                # (node, target_z) fresh lips being nudged up
            self.last_good = None
            self.lifting = False

        # ---- proven topology helpers -------------------------------------
        def _build_adj(self):
            tris = np.array(self.topo.triangles.value)
            adj = {}
            for a, b, c in tris:
                for u, v in ((a, b), (b, c), (c, a)):
                    adj.setdefault(int(u), set()).add(int(v)); adj.setdefault(int(v), set()).add(int(u))
            self.adj = adj

        def _tip_normal(self, P, tris, touch):
            n = np.zeros(3)
            for k in touch:
                a, b, c = P[tris[k]]
                n += np.cross(b - a, c - a)
            nn = np.linalg.norm(n)
            return n / nn if nn > 1e-9 else np.array([0.0, 0.0, 1.0])

        def _annulus_cands(self, tip):
            if self.adj is None:
                self._build_adj()
            if self._rest_r is None:
                R = np.array(self.mo.rest_position.value)
                self._rest_r = np.hypot(R[:, 0], R[:, 1])
            rr = self._rest_r
            return [v for v in self.adj.get(tip, ())
                    if v not in self.crack and v < n_real and TEAR_R_MIN <= rr[v] <= TEAR_R_MAX]

        def _split_tip(self, vtip, vprev, vnext):
            if self.next_spare >= len(self.mo.position.value):
                return None
            spare = self.next_spare
            P = np.array(self.mo.position.value); R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            touch = [k for k in range(len(tris)) if vtip in tris[k]]
            if len(touch) < 2:
                return None
            o = P[vtip]; nrm = self._tip_normal(P, tris, touch)
            xax = P[vnext] - o; xax = xax - nrm * np.dot(xax, nrm); xax = xax / (np.linalg.norm(xax) + 1e-9)
            yax = np.cross(nrm, xax)

            def ang(pt):
                w = pt - o
                return math.atan2(float(np.dot(w, yax)), float(np.dot(w, xax))) % (2 * math.pi)

            a_prev = ang(P[vprev]); moved = 0
            for k in touch:
                if ang(P[tris[k]].mean(axis=0)) > a_prev:
                    tris[k] = [spare if x == vtip else x for x in tris[k]]; moved += 1
            if moved == 0 or moved == len(touch):
                return None
            self.next_spare += 1
            P[spare] = P[vtip]; R[spare] = R[vtip]
            self.mo.position.value = P.tolist(); self.mo.rest_position.value = R.tolist()
            self.topo.triangles.value = tris.tolist()
            if self.visual is not None:
                self.visual.triangles.value = tris.tolist()
            self.springs.reinit(); self.mass.reinit()
            self.edges = None; self.adj = None
            return spare

        def _advance_toward(self, wx, wy):
            """Advance the tip ONE vertex toward world point (wx,wy). Returns True if it moved."""
            P = np.array(self.mo.position.value)
            tip, prev = self.crack[-1], self.crack[-2]
            cands = self._annulus_cands(tip)
            if not cands:
                return False
            want = np.array([wx - P[tip, 0], wy - P[tip, 1]])
            wn = np.linalg.norm(want)
            if wn < 1e-6:
                return False
            want = want / wn
            fwd = P[tip, :2] - P[prev, :2]

            def score(v):
                w = P[v, :2] - P[tip, :2]; w = w / (np.linalg.norm(w) + 1e-9)
                if np.dot(w, fwd) < -0.5 * (np.linalg.norm(fwd) + 1e-9):
                    return -9.0
                return float(np.dot(w, want))

            vnext = max(cands, key=score)
            if score(vnext) < 0.0:
                return False
            sp = self._split_tip(tip, prev, vnext)
            if sp is None:
                return False
            self.pairs.append((tip, sp)); self.crack.append(vnext)
            # peel: nudge the fresh spare (inner lip) up to a FIXED small height above its REST
            # z (not above the ever-rising tip -- that cascades to the sky).
            rz = float(np.array(self.mo.rest_position.value)[sp, 2])
            self.peel.append([sp, rz + PEEL_LIFT])
            return True

        def _pretear(self, n):
            if self.adj is None:
                self._build_adj()
            for _ in range(max(0, n)):
                P = np.array(self.mo.position.value)
                tip, prev = self.crack[-1], self.crack[-2]
                rad = P[tip, :2]; rn = float(np.linalg.norm(rad))
                if rn < 1e-6:
                    break
                rad = rad / rn; tang = np.array([-rad[1], rad[0], 0.0])
                if np.dot(tang, P[tip] - P[prev]) < 0:
                    tang = -tang
                cands = self._annulus_cands(tip)
                if not cands:
                    break

                def al(v):
                    w = P[v] - P[tip]; return float(np.dot(w / (np.linalg.norm(w) + 1e-9), tang))

                vnext = max(cands, key=al)
                if al(vnext) < 0.2:
                    break
                sp = self._split_tip(tip, prev, vnext)
                if sp is None:
                    break
                self.pairs.append((tip, sp)); self.crack.append(vnext)
            print(f"[Tear] starting flap = {len(self.pairs)} verts. LEFT-CLICK around the ring to tear.")

        # ---- mouse: un-project the click to a world point on the membrane ----
        def _unproject(self, px, py):
            try:
                W = float(self.cam.widthViewport.value); H = float(self.cam.heightViewport.value)
                mv = np.array(self.cam.modelViewMatrix.value, dtype=float).reshape(4, 4).T   # GL col-major
                pr = np.array(self.cam.projectionMatrix.value, dtype=float).reshape(4, 4).T
            except Exception:  # noqa: BLE001
                return None
            if W < 1 or H < 1 or not np.isfinite(mv).all() or not np.isfinite(pr).all():
                return None
            M = pr @ mv
            try:
                Minv = np.linalg.inv(M)
            except Exception:  # noqa: BLE001
                return None
            ny = H - py                                   # GL y is bottom-up
            ndc = lambda z: np.array([2 * px / W - 1, 2 * ny / H - 1, 2 * z - 1, 1.0])

            def world(z):
                w = Minv @ ndc(z)
                return w[:3] / w[3] if abs(w[3]) > 1e-9 else None

            a = world(0.0); b = world(1.0)
            if a is None or b is None:
                return None
            d = b - a
            if abs(d[2]) < 1e-9:
                return None
            t = (CLICK_PLANE_Z - a[2]) / d[2]              # intersect membrane plane
            p = a + t * d
            return float(p[0]), float(p[1])

        def onMouseEvent(self, event):
            if event.get('State', -1) != 1:               # only LEFT DOWN
                return
            w = self._unproject(float(event.get('mouseX', 0)), float(event.get('mouseY', 0)))
            if w is None:
                print("[Tear] click un-project failed (camera matrices not ready?)")
                return
            self.click_world = w
            print(f"[Tear] click -> world ({w[0]:.1f},{w[1]:.1f}); tearing toward it")

        # ---- per step ----------------------------------------------------
        def onAnimateBeginEvent(self, event):
            Pc = np.array(self.mo.position.value)
            if not np.isfinite(Pc).all():
                if self.last_good is not None:
                    self.mo.position.value = self.last_good
                    self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.last_good)
                return
            if not self.seeded:
                self.seeded = True
                sp = self._split_tip(self.crack[-1], self.crack[-2], self.first_fwd)
                if sp is not None:
                    self.pairs.append((self.crack[-1], sp)); self.crack.append(self.first_fwd)
                    if PRE_TEAR_DEG > 0:
                        self._pretear(int(PRE_TEAR_DEG / 360.0 * (2.0 * math.pi * NICK_RADIUS / G.EDGE_LEN)))
                return
            # a pending click -> tear a burst toward it
            if self.click_world is not None and not self.stopped:
                wx, wy = self.click_world; self.click_world = None
                n = 0
                for _ in range(ADVANCE_PER_CLICK):
                    if not self._advance_toward(wx, wy):
                        break
                    n += 1
                if n:
                    P = np.array(self.mo.position.value); tip = self.crack[-1]
                    print(f"[Tear] +{n} verts -> tip@r{np.hypot(P[tip,0],P[tip,1]):.1f},"
                          f"{math.degrees(math.atan2(P[tip,1],P[tip,0])):.0f}deg  crack={len(self.pairs)}")

        def onAnimateEndEvent(self, event):
            P = np.array(self.mo.position.value)
            if not np.isfinite(P).all():
                return
            # kinematic peel: move each fresh lip toward its target z by a CLAMPED step
            still = []
            for node, tz in self.peel:
                dz = tz - P[node, 2]
                if abs(dz) < 0.02:
                    continue
                P[node, 2] += max(-PEEL_STEP, min(PEEL_STEP, dz))
                still.append([node, tz])
            self.peel = still
            # velocity clamp
            if MAX_SPEED > 0:
                Vel = np.array(self.mo.velocity.value)
                if Vel.size:
                    s = np.linalg.norm(Vel, axis=1); hot = s > MAX_SPEED
                    if hot.any():
                        Vel[hot] *= (MAX_SPEED / s[hot])[:, None]; self.mo.velocity.value = Vel.tolist()
            # strain + area clamps
            if self.edges is None:
                tris = np.array(self.topo.triangles.value); E = set()
                for a, b, c in tris:
                    for u, w in ((a, b), (b, c), (c, a)):
                        E.add((min(u, w), max(u, w)))
                self.edges = np.array(sorted(E), dtype=int)
                R = np.array(self.mo.rest_position.value)
                self.edge_rest = np.linalg.norm(R[self.edges[:, 1]] - R[self.edges[:, 0]], axis=1)
                self.tri_arr = tris
                self.rest_area = 0.5 * np.linalg.norm(np.cross(
                    R[tris[:, 1]] - R[tris[:, 0]], R[tris[:, 2]] - R[tris[:, 0]]), axis=1)
            e0, e1 = self.edges[:, 0], self.edges[:, 1]; limit = self.edge_rest * MAX_STRETCH
            for _ in range(3):
                dd = P[e1] - P[e0]; L = np.linalg.norm(dd, axis=1); over = L > limit
                if not over.any():
                    break
                nrm = dd[over] / L[over][:, None]; ex = (L[over] - limit[over])[:, None]
                np.add.at(P, e0[over], 0.5 * ex * nrm); np.add.at(P, e1[over], -0.5 * ex * nrm)
            T = self.tri_arr; floor = AREA_MIN_FRAC * self.rest_area
            for _ in range(2):
                A = P[T[:, 0]]; B = P[T[:, 1]]; C = P[T[:, 2]]
                area = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1); bad = area < floor
                if not bad.any():
                    break
                Tb = T[bad]; cen = (P[Tb[:, 0]] + P[Tb[:, 1]] + P[Tb[:, 2]]) / 3.0
                s = np.sqrt(np.maximum(floor[bad] / np.maximum(area[bad], 1e-9), 1.0))[:, None]
                corr = np.zeros_like(P); cnt = np.zeros(len(P))
                for j in range(3):
                    np.add.at(corr, Tb[:, j], (cen + s * (P[Tb[:, j]] - cen)) - P[Tb[:, j]])
                    np.add.at(cnt, Tb[:, j], 1.0)
                m = cnt > 0; P[m] += corr[m] / cnt[m][:, None]
            if MAX_DISP > 0:
                R = np.array(self.mo.rest_position.value); d = P - R; dn = np.linalg.norm(d, axis=1)
                far = np.isfinite(dn) & (dn > MAX_DISP)
                if far.any():
                    P[far] = R[far] + d[far] * (MAX_DISP / dn[far])[:, None]
            self.mo.position.value = P.tolist()
            if not self.lifting and len(self.pairs) >= LIFT_AFTER_CRACKLEN:
                self.lifting = True; self.root.gravity.value = [0.0, 0.0, DISC_LIFT_Z]
                print(f"[Tear] circle mostly cut -> lifting the disc off to reveal the hole")
            Pn = np.array(self.mo.position.value)
            if np.isfinite(Pn).all():
                self.last_good = Pn.tolist()

    return _C(name="CapTearClickController")


def createScene(root):
    import Sofa
    root.gravity = [0.0, 0.0, 0.0]
    root.dt = 0.02
    _pl = root.addChild("RequiredPlugins")
    for name in PLUGINS:
        _pl.addObject("RequiredPlugin", name=name)
    root.addObject("VisualStyle", displayFlags="showVisual showWireframe")
    root.addObject("DefaultAnimationLoop")
    root.addObject("DefaultVisualManagerLoop")
    root.addObject("BackgroundSetting", color=[0.06, 0.09, 0.12, 1.0])
    # TOP-DOWN camera: look straight down -z so a click maps cleanly onto the membrane.
    cam = root.addObject("InteractiveCamera", position=[0, 0, 22], lookAt=[0, 0, 0],
                         projectionType=0)

    verts, faces, n_real, rim, disc, seed_v, seed_a, seed_fwd = _geometry()

    lens = root.addChild("Lens")
    lens.addObject("MeshOBJLoader", name="bloader", filename=os.path.join(_HERE, "lens.obj"))
    lens.addObject("OglModel", name="lensVisual", src="@bloader", color=[0.45, 0.55, 0.75, 0.4])

    cap = root.addChild("Cap")
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.5, rayleighMass=0.2)
    cap.addObject("CGLinearSolver", iterations=40, tolerance=1e-8, threshold=1e-8)
    topo = cap.addObject("TriangleSetTopologyContainer", name="topo", position=verts, triangles=faces)
    cap.addObject("TriangleSetTopologyModifier")
    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    mo = cap.addObject("MechanicalObject", name="Mo", position=verts)
    mass = cap.addObject("DiagonalMass", massDensity=1.0)
    springs = cap.addObject("MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    cap.addObject("TriangularBendingSprings", name="Bending", stiffness=BEND_STIFFNESS)
    cap.addObject("UniformVelocityDampingForceField", dampingCoefficient=DAMPING)
    cap.addObject("EllipsoidForceField", name="LensObstacle", center=[0.0, 0.0, G.Z0],
                  vradius=[G.A, G.A, G.C], stiffness=LENS_REPULSION, damping=1.0)
    cap.addObject("FixedProjectiveConstraint", name="RimAnchor", indices=rim, showObject=False)

    visu = cap.addChild("Visual")
    oglm = visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.82, 1.0], triangles=faces)
    visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

    cap.addObject(_make_controller(mo, topo, springs, mass, oglm, cam, n_real,
                                   seed_v, seed_a, seed_fwd, root))
    print("=" * 68)
    print(" cap_tear_click.py | LEFT-CLICK where you want the tear to go (no drag needed).")
    print(" Stable by design: kinematic peel, no penalty spring -> cannot explode.")
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
    Sofa.Gui.GUIManager.Init("cap_tear_click", "imgui")
    Sofa.Gui.GUIManager.createGUI(root, __file__)
    Sofa.Gui.GUIManager.SetDimension(1000, 820)
    Sofa.Gui.GUIManager.MainLoop(root)
    Sofa.Gui.GUIManager.closeGUI()


try:
    import Sofa  # noqa: F401
except Exception:  # noqa: BLE001
    pass

if __name__ == "__main__":
    main()
