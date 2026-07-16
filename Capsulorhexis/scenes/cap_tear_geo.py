"""GEOMETRIC flap-tear: the crack FOLLOWS THE FORCEPS (mouse) -- no stress computation.

This is the simplest, most robust "tear a flap like the EyeSi video": you Shift+drag the
flap and the tear front chases where you pull; the freed flap follows and folds. Because the
crack direction comes from a GEOMETRIC rule (toward the grabbed point), there is no
"the force never reaches the crack tip" problem that the stress-driven cap_tear.py hits --
you drag it, it tears there.

Decoupled, like this repo's JS demo (docs/implementation/2_freetear_demo.md):
  - RULE (where the crack goes): each check, find the most-pulled node = the forceps grip;
    advance the tip one vertex toward it, staying in the operating annulus. Pure geometry.
  - PHYSICS (how the membrane looks): mass-spring ONLY (edge springs + bending), NO
    TriangularFEMForceField -- that FEM's polar decomposition is what threw 'Null determinant'
    and vanished the scene; springs never do.
  - The freed flap is dragged + folded by the same mouse pull; a disc-lift reveals the hole
    once you have torn most of the ring.

Run:  .\scenes\run_captear_geo.ps1   (or ./scenes/run_cap.ps1 -Scene cap_tear_geo.py)
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

# --- membrane physics --------------------------------------------------------
# USE_FEM: True = the original co-rotational membrane FEM ("paper" feel, resists shear);
# False = mass-spring only (robust, never null-determinants). Try FEM here with the TENSION
# rim below, which keeps the membrane taut and is gentler on the FEM than a rigid clamp.
USE_FEM = True
YOUNG = 800.0             # FEM in-plane stiffness (only used if USE_FEM)
EDGE_STIFFNESS = 1200.0   # edge springs (always on; the only in-plane stiffness if not FEM)
BEND_STIFFNESS = 8.0      # low = freed flap folds/peels over instead of standing rigid
DAMPING = 2.0
LENS_REPULSION = 2000.0
MAX_STRETCH = 1.5         # edge may not exceed this x rest length
MAX_SPEED = 25.0          # per-node velocity cap (absorbs a violent yank)
MAX_DISP = 8.0            # HARD cap on how far any node may move from its rest position.
                          # Stops a far mouse yank (the pull=48 blow-up) cold, while still
                          # allowing the flap to lift/fold (needs ~6). 0 disables.
AREA_MIN_FRAC = 0.30      # a triangle may not shrink below this fraction of its rest area

# --- boundary: the zonular fibres pull the capsule OUTWARD (not a rigid clamp) --
# RIM_MODE "tension": each rim node is softly anchored to its rest (so it cannot drift) AND
# pulled radially OUTWARD -> the membrane is taut and the tear GAPES open as it runs (you can
# see it), like the real zonular tension. "fixed" = the old rigid clamp.
RIM_MODE = "tension"      # "tension" | "fixed"
RIM_ANCHOR_STIFF = 60.0   # soft anchor of each rim node to its rest position
RIM_TENSION = 45.0        # outward radial force per rim node (the zonular pull)

# --- geometry / seed ---------------------------------------------------------
NICK_RADIUS = 5.0
TEAR_R_MIN = 3.0          # crack stays in this annulus (away from the exploding pole / rim)
TEAR_R_MAX = 6.0
RIM_FRAC = 0.9            # nodes with r > RIM_FRAC*R are anchored (zonular fibres)
PRE_TEAR_DEG = 100.0      # pre-open this much of the circle at startup (a starting flap)

# --- the GEOMETRIC crack rule (follow the forceps) ---------------------------
PULL_TRIGGER = 0.35       # min EXTRA displacement (beyond the tension-settled shape) of the
                          # grabbed node before the crack advances
ALIGN_MIN = 0.25          # the next vertex must point at least this much toward the pull
SETTLE_T = 1.5            # [s] let the outward tension settle, then measure YOUR pull as the
                          # displacement BEYOND that baseline (else the tension auto-tears)
TEAR_CHECK_DT = 0.08      # [s] between advance checks
MAX_ADVANCE_PER_CHECK = 4 # unzip up to this many vertices per check while you keep pulling
PULL_LOG_DT = 0.4

# --- mouse (forceps) ---------------------------------------------------------
ENABLE_MOUSE = True
MOUSE_STIFFNESS = 550.0
SHOW_TIP_MARKER = False
ALARM_DISTANCE = 0.40 * G.EDGE_LEN
CONTACT_DISTANCE = 0.20 * G.EDGE_LEN

# --- reveal the hole once mostly torn ----------------------------------------
LIFT_AFTER_CRACKLEN = 75
DISC_LIFT_Z = 14.0
LIFT_RADIUS = 4.5

PLUGINS = [
    "Sofa.Component.StateContainer", "Sofa.Component.Topology.Container.Dynamic",
    "Sofa.Component.ODESolver.Backward", "Sofa.Component.LinearSolver.Iterative",
    "Sofa.Component.SolidMechanics.Spring", "Sofa.Component.SolidMechanics.FEM.Elastic",
    "Sofa.Component.Mass",
    "Sofa.Component.Constraint.Projective", "Sofa.Component.MechanicalLoad",
    "Sofa.Component.Mapping.Linear",
    "Sofa.Component.Collision.Detection.Algorithm",
    "Sofa.Component.Collision.Detection.Intersection",
    "Sofa.Component.Collision.Geometry", "Sofa.Component.Collision.Response.Contact",
    "Sofa.GUI.Component",
    "Sofa.Component.Visual", "Sofa.Component.AnimationLoop", "Sofa.Component.Setting",
    "Sofa.GL.Component.Rendering3D",
]


def _geometry():
    """Continuous cap (no pre-slit) + spare pool + rim/disc sets + interior nick seed."""
    verts, faces, ring_base, ring_of = G._build_raw()
    verts = [list(v) for v in verts]
    n_real = len(verts)
    apex = list(verts[0])
    verts += [list(apex) for _ in range(n_real)]

    import numpy as np
    P = np.array(verts[:n_real])
    r = np.hypot(P[:, 0], P[:, 1])
    rim = [i for i in range(n_real) if r[i] > RIM_FRAC * G.R]
    disc = [i for i in range(n_real) if r[i] < LIFT_RADIUS]

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


def _make_controller(mo, topo, springs, mass, bending, visual, n_real,
                     seed_v, v_a, v0, marker, root, fem):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo = mo, topo
            self.springs, self.mass, self.bending = springs, mass, bending
            self.fem = fem
            self.visual, self.marker, self.root = visual, marker, root
            self.next_spare = n_real
            self.crack = [v_a, seed_v]
            self.first_fwd = v0
            self.seeded = False
            self.pairs = []
            self.adj = None
            self.edges = None
            self.edge_rest = None
            self.tri_arr = None
            self.rest_area = None
            self._rest_r = None            # per-node REST planar radius (material, never moves)
            self.stopped = False
            self.last_check = -1e9
            self.last_pull_log = -1e9
            self.last_good_pos = None
            self.lifting = False
            self.step = 0
            self.baseline = None           # tension-settled shape; YOUR pull is measured vs this

        # ---- topology helpers (identical to the proven cap_tear.py) ---------
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

            a_prev = ang(P[vprev])
            moved = 0
            for k in touch:
                if ang(P[tris[k]].mean(axis=0)) > a_prev:
                    tris[k] = [spare if x == vtip else x for x in tris[k]]
                    moved += 1
            if moved == 0 or moved == len(touch):
                return None
            self.next_spare += 1
            P[spare] = P[vtip]; R[spare] = R[vtip]
            self.mo.position.value = P.tolist()
            self.mo.rest_position.value = R.tolist()
            self.topo.triangles.value = tris.tolist()
            if self.visual is not None:
                self.visual.triangles.value = tris.tolist()
            if self.fem is not None:
                self.fem.reinit()
            self.springs.reinit(); self.mass.reinit()
            self.edges = None
            self.adj = None                # topology changed -> adjacency is stale, rebuild
            return spare

        def _annulus_cands(self, tip):
            # Use the REST planar radius (material coordinate), NOT the deformed position:
            # under a pull the mesh moves and current r drifts out of [R_MIN,R_MAX], which
            # made the crack falsely hit a 'boundary' and stop. Rest radius never moves.
            if self.adj is None:
                self._build_adj()
            if self._rest_r is None:
                R = np.array(self.mo.rest_position.value)
                self._rest_r = np.hypot(R[:, 0], R[:, 1])
            rr = self._rest_r
            return [v for v in self.adj.get(tip, ())
                    if v not in self.crack and v < n_real and TEAR_R_MIN <= rr[v] <= TEAR_R_MAX]

        def _pretear(self, n_steps):
            """Geometrically pre-open n_steps vertices circumferentially (the starting flap)."""
            if self.adj is None:
                self._build_adj()
            for _ in range(max(0, n_steps)):
                P = np.array(self.mo.position.value)
                tip, prev = self.crack[-1], self.crack[-2]
                rad = P[tip, :2]; rn = float(np.linalg.norm(rad))
                if rn < 1e-6:
                    break
                rad = rad / rn
                tang = np.array([-rad[1], rad[0], 0.0])
                if np.dot(tang, P[tip] - P[prev]) < 0:
                    tang = -tang
                cands = self._annulus_cands(tip)
                if not cands:
                    break

                def al(v):
                    w = P[v] - P[tip]
                    return float(np.dot(w / (np.linalg.norm(w) + 1e-9), tang))

                vnext = max(cands, key=al)
                if al(vnext) < 0.2:
                    break
                sp = self._split_tip(tip, prev, vnext)
                if sp is None:
                    break
                self.pairs.append((tip, sp)); self.crack.append(vnext)
            P = np.array(self.mo.position.value)
            aa = float(np.degrees(np.arctan2(P[self.crack[-1], 1], P[self.crack[-1], 0])))
            print(f"[Tear] pre-torn {len(self.pairs)} verts (starting flap); tip at ang={aa:.0f}deg. "
                  f"Shift+drag the flap; the tear follows your forceps.")

        # ---- the GEOMETRIC advance: follow the forceps ----------------------
        def _advance_once(self, t):
            P = np.array(self.mo.position.value)
            tip, prev = self.crack[-1], self.crack[-2]
            # forceps grip = the node displaced most BEYOND the tension-settled baseline
            # (measuring from rest would mistake the steady outward tension for a pull).
            ref = self.baseline if self.baseline is not None else np.array(self.mo.rest_position.value)[:n_real]
            disp = np.linalg.norm(P[:n_real] - ref, axis=1)
            jmax = int(np.argmax(disp))
            if disp[jmax] < PULL_TRIGGER:
                return "no_pull"
            want = P[jmax] - P[tip]                       # tear TOWARD the forceps
            wn = np.linalg.norm(want)
            if wn < 1e-6:
                return "no_pull"
            want = want / wn
            cands = self._annulus_cands(tip)
            if not cands:
                self.stopped = True
                print(f"[Tear] t={t:.2f} reached a boundary; stopping")
                return "dead_end"
            fwd = P[tip] - P[prev]

            def score(v):
                w = P[v] - P[tip]
                w = w / (np.linalg.norm(w) + 1e-9)
                # align with the pull, but never reverse the crack sharply
                if np.dot(w, fwd) < -0.4 * np.linalg.norm(fwd):
                    return -9.0
                return float(np.dot(w, want))

            vnext = max(cands, key=score)
            if score(vnext) < ALIGN_MIN:
                return "no_forward"                        # you are not pulling it forward yet
            sp = self._split_tip(tip, prev, vnext)
            if sp is None:
                return "split_fail"
            self.pairs.append((tip, sp)); self.crack.append(vnext)
            if t - self.last_pull_log >= PULL_LOG_DT:
                self.last_pull_log = t
                P = np.array(self.mo.position.value)
                rr = float(np.hypot(P[vnext, 0], P[vnext, 1]))
                aa = float(np.degrees(np.arctan2(P[vnext, 1], P[vnext, 0])))
                gaps = [float(np.linalg.norm(P[a] - P[b])) for a, b in self.pairs]
                print(f"[Tear] t={t:5.2f} follow forceps -> tip@r{rr:.1f},{aa:.0f}deg "
                      f"| crack len={len(self.pairs)} max-gap={max(gaps):.2f} pull={disp[jmax]:.1f}")
            return "advanced"

        def onAnimateBeginEvent(self, event):
            t = self.mo.getContext().getTime()
            # rollback safety net
            Pcur = np.array(self.mo.position.value)
            if not np.isfinite(Pcur).all():
                if self.last_good_pos is not None:
                    self.mo.position.value = self.last_good_pos
                    self.mo.velocity.value = [[0.0, 0.0, 0.0]] * len(self.last_good_pos)
                    print("[Tear] recovered from an unstable step -- drag more gently")
                return
            self.step += 1
            if self.stopped:
                return
            if self.marker is not None:
                self.marker.position.value = [Pcur[self.crack[-1]].tolist()]
            if not self.seeded:
                self.seeded = True
                sp = self._split_tip(self.crack[-1], self.crack[-2], self.first_fwd)
                if sp is not None:
                    self.pairs.append((self.crack[-1], sp))
                    self.crack.append(self.first_fwd)
                    if PRE_TEAR_DEG > 0:
                        self._pretear(int(PRE_TEAR_DEG / 360.0 * (2.0 * math.pi * NICK_RADIUS / G.EDGE_LEN)))
                return
            # once the outward tension has settled, snapshot it as the baseline; from here a
            # crack advance needs displacement BEYOND this (= your actual pull), not the
            # steady tension.
            if self.baseline is None and t >= SETTLE_T:
                self.baseline = Pcur[:n_real].copy()
            if self.baseline is None or t - self.last_check < TEAR_CHECK_DT:
                return
            self.last_check = t
            self.last_check = t
            if self.adj is None:
                self._build_adj()
            for _ in range(MAX_ADVANCE_PER_CHECK):
                if self._advance_once(t) != "advanced":
                    break

        def onAnimateEndEvent(self, event):
            if MAX_SPEED > 0:
                Vel = np.array(self.mo.velocity.value)
                if Vel.size:
                    sp = np.linalg.norm(Vel, axis=1)
                    hot = sp > MAX_SPEED
                    if hot.any():
                        Vel[hot] *= (MAX_SPEED / sp[hot])[:, None]
                        self.mo.velocity.value = Vel.tolist()
            if self.edges is None:
                tris = np.array(self.topo.triangles.value)
                E = set()
                for a, b, c in tris:
                    for u, w in ((a, b), (b, c), (c, a)):
                        E.add((min(u, w), max(u, w)))
                self.edges = np.array(sorted(E), dtype=int)
                R = np.array(self.mo.rest_position.value)
                self.edge_rest = np.linalg.norm(R[self.edges[:, 1]] - R[self.edges[:, 0]], axis=1)
                self.tri_arr = tris
                self.rest_area = 0.5 * np.linalg.norm(np.cross(
                    R[tris[:, 1]] - R[tris[:, 0]], R[tris[:, 2]] - R[tris[:, 0]]), axis=1)
            P = np.array(self.mo.position.value)
            if MAX_STRETCH > 0:                            # edge strain clamp
                e0, e1 = self.edges[:, 0], self.edges[:, 1]
                limit = self.edge_rest * MAX_STRETCH
                for _ in range(3):
                    dd = P[e1] - P[e0]; L = np.linalg.norm(dd, axis=1)
                    over = L > limit
                    if not over.any():
                        break
                    n = dd[over] / L[over][:, None]; ex = (L[over] - limit[over])[:, None]
                    np.add.at(P, e0[over], 0.5 * ex * n); np.add.at(P, e1[over], -0.5 * ex * n)
            if AREA_MIN_FRAC > 0:                          # area clamp (no collapse/inversion)
                T = self.tri_arr; floor = AREA_MIN_FRAC * self.rest_area
                for _ in range(2):
                    A = P[T[:, 0]]; B = P[T[:, 1]]; C = P[T[:, 2]]
                    area = 0.5 * np.linalg.norm(np.cross(B - A, C - A), axis=1)
                    bad = area < floor
                    if not bad.any():
                        break
                    Tb = T[bad]
                    cen = (P[Tb[:, 0]] + P[Tb[:, 1]] + P[Tb[:, 2]]) / 3.0
                    s = np.sqrt(np.maximum(floor[bad] / np.maximum(area[bad], 1e-9), 1.0))[:, None]
                    corr = np.zeros_like(P); cnt = np.zeros(len(P))
                    for j in range(3):
                        np.add.at(corr, Tb[:, j], (cen + s * (P[Tb[:, j]] - cen)) - P[Tb[:, j]])
                        np.add.at(cnt, Tb[:, j], 1.0)
                    m = cnt > 0
                    P[m] += corr[m] / cnt[m][:, None]
            if MAX_DISP > 0:                               # cap how far any node leaves rest
                R = np.array(self.mo.rest_position.value)
                d = P - R
                dn = np.linalg.norm(d, axis=1)
                far = dn > MAX_DISP
                if far.any():
                    P[far] = R[far] + d[far] * (MAX_DISP / dn[far])[:, None]
            self.mo.position.value = P.tolist()

            if not self.lifting and len(self.pairs) >= LIFT_AFTER_CRACKLEN:
                self.lifting = True
                self.root.gravity.value = [0.0, 0.0, DISC_LIFT_Z]
                print(f"[Tear] circle mostly cut ({len(self.pairs)} verts) -> lifting the disc off")

            Pnow = np.array(self.mo.position.value)
            if np.isfinite(Pnow).all():
                self.last_good_pos = Pnow.tolist()

    return _C(name="CapTearGeoController")


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
        root.addObject("CollisionPipeline")
        root.addObject("BruteForceBroadPhase")
        root.addObject("BVHNarrowPhase")
        root.addObject("CollisionResponse", response="PenalityContactForceField")
        root.addObject("MinProximityIntersection", alarmDistance=ALARM_DISTANCE,
                       contactDistance=CONTACT_DISTANCE)
        root.addObject("AttachBodyButtonSetting", stiffness=MOUSE_STIFFNESS, arrowSize=0.3)

    verts, faces, n_real, rim, disc, seed_v, seed_a, seed_fwd = _geometry()

    lens = root.addChild("Lens")
    lens.addObject("MeshOBJLoader", name="bloader", filename=os.path.join(_HERE, "lens.obj"))
    lens.addObject("OglModel", name="lensVisual", src="@bloader", color=[0.45, 0.55, 0.75, 0.45])

    cap = root.addChild("Cap")
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.4, rayleighMass=0.2)
    cap.addObject("CGLinearSolver", iterations=30, tolerance=1e-8, threshold=1e-8)
    topo = cap.addObject("TriangleSetTopologyContainer", name="topo", position=verts, triangles=faces)
    cap.addObject("TriangleSetTopologyModifier")
    cap.addObject("TriangleSetGeometryAlgorithms", template="Vec3d")
    mo = cap.addObject("MechanicalObject", name="Mo", position=verts)
    mass = cap.addObject("DiagonalMass", massDensity=1.0)
    # Optional co-rotational FEM ("original paper feel"); mass-spring edge/bending always on.
    fem = (cap.addObject("TriangularFEMForceField", name="FEM", method="large",
                         youngModulus=YOUNG, poissonRatio=0.3) if USE_FEM else None)
    springs = cap.addObject("MeshSpringForceField", name="EdgeSprings",
                            linesStiffness=EDGE_STIFFNESS, linesDamping=1.0)
    bending = cap.addObject("TriangularBendingSprings", name="Bending", stiffness=BEND_STIFFNESS)
    cap.addObject("UniformVelocityDampingForceField", dampingCoefficient=DAMPING)
    cap.addObject("EllipsoidForceField", name="LensObstacle",
                  center=[0.0, 0.0, G.Z0], vradius=[G.A, G.A, G.C],
                  stiffness=LENS_REPULSION, damping=1.0)

    # Boundary: the zonular fibres. RIM_MODE "tension" = soft anchor + outward radial pull
    # (taut, and the tear gapes open as it runs); "fixed" = old rigid clamp.
    if RIM_MODE == "tension":
        cap.addObject("RestShapeSpringsForceField", name="RimAnchor",
                      points=rim, stiffness=RIM_ANCHOR_STIFF)
        import numpy as _np
        Vr = _np.array(verts)
        rimf = []
        for i in rim:
            d = Vr[i, :2]; nn = float(_np.linalg.norm(d))
            d = d / nn if nn > 1e-6 else _np.array([0.0, 0.0])
            rimf.append([float(d[0] * RIM_TENSION), float(d[1] * RIM_TENSION), 0.0])
        cap.addObject("ConstantForceField", name="RimTension", indices=rim, forces=rimf)
    else:
        cap.addObject("FixedProjectiveConstraint", name="RimAnchor", indices=rim, showObject=False)
    if ENABLE_MOUSE:
        cap.addObject("TriangleCollisionModel", selfCollision=False, contactStiffness=200.0)

    visu = cap.addChild("Visual")
    oglm = visu.addObject("OglModel", name="visual", color=[0.9, 0.9, 0.82, 1.0], triangles=faces)
    visu.addObject("IdentityMapping", input="@../Mo", output="@visual")

    mk = root.addChild("TipMarker")
    marker = mk.addObject("MechanicalObject", name="mk", position=[list(verts[seed_v])],
                          showObject=SHOW_TIP_MARKER, showObjectScale=0.25, drawMode=1,
                          showColor=[1.0, 0.15, 0.1, 1.0])

    cap.addObject(_make_controller(mo, topo, springs, mass, bending, oglm, n_real,
                                   seed_v, seed_a, seed_fwd, marker, root, fem))

    print("=" * 70)
    print(" cap_tear_geo.py | GEOMETRIC tear: the crack FOLLOWS your forceps (no stress)")
    print(" Shift + LEFT-DRAG the flap; drag around the ring and the tear follows.")
    print("=" * 70)
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
    Sofa.Gui.GUIManager.Init("cap_tear_geo", "imgui")
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
