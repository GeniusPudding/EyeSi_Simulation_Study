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
MAX_SPEED = 25.0          # hard per-node velocity cap: a hard mouse yank is one big penalty
                          # impulse that would otherwise blow a triangle up mid-step (NaN,
                          # "picture vanished"); clamping speed absorbs it. 0 disables.

# --- tear rule --------------------------------------------------------------
# sigma1 ~= YOUNG * local strain, so 90/1200 ~= 7.5% local stretch at the tip triggers a
# step. Lowered from 180 so a GENTLE mouse pull can drive the crack (the scripted symmetric
# lift used to slam sigma1 past 1000, which hid how high 180 really was for hand pulling).
STRESS_THRESHOLD = 10.0    # sigma1 the tip must exceed to advance. Measured: idle tip sigma1
                           # is 0 (the tip is only stressed when you pull near it), so this
                           # can be low without auto-tearing -- with the gain below the real
                           # bar is ~7, and a near-tip pull gives ~10-14, so it keeps tearing
                           # even as your grab drifts a bit from the advancing tip.
TIP_STRESS_GAIN = 1.5      # a real crack tip has a stress SINGULARITY that a coarse mesh
                           # smears/underestimates; this concentration factor multiplies the
                           # tip sigma1 before the threshold test, so a hand pull tears more
                           # readily (raise to make tearing easier)
TEAR_CHECK_DT = 0.10       # [s] between tip-advance checks
MAX_ADVANCE_PER_CHECK = 6  # unzip up to this many vertices per check while the tip stays
                           # over threshold -> a firm pull tears a RUN, not one vertex
PULL_LOG_DT = 0.3          # [s] between [Pull] diagnostic lines (only while you are pulling)
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
NICK_RADIUS = 5.0         # the initial nick (cystotome puncture) sits at this planar radius
                          # -- inside the fixed rim, in the operating region, so a forceps
                          # pull can actually stress the tip (a rim-pinned seed cannot tear)
# Keep the crack in the OPERATING ANNULUS. Below R_MIN is the central pole -- a mesh
# singularity where all rings converge; splitting there makes a degenerate sliver whose
# co-rotational FEM force explodes to inf and NaNs the whole mesh (the 'scene vanished'
# bug). Above R_MAX is the fixed rim. A capsulorhexis is a ring at r~5 anyway, so the path
# still emerges from perpendicular-to-sigma1 -- it just cannot run into the pole or the rim.
TEAR_R_MIN = 3.0
TEAR_R_MAX = 6.0
LIFT_RADIUS = 4.5         # "disc" mode: nodes with planar r < this get lifted
LIFT_HEIGHT = 6.0         # "disc"/"patch" pull height (+z)
PULL_START_T = 1.0
PULL_END_T = 12.0
RIM_FRAC = 0.9            # nodes with r > RIM_FRAC*R are anchored (zonular fibres)

# --- mouse (forceps) --------------------------------------------------------
SHOW_TIP_MARKER = True    # small red dot on the crack tip = where to grab (set False to hide)
ENABLE_MOUSE = True
MOUSE_STIFFNESS = 700.0   # Shift+left-drag attach spring. Softer than before: a stiff spring
                          # + a fast yank is one big penalty impulse that NaNs the mesh
                          # ("whole scene disappears"). Softer = you must drag a bit further
                          # but it will not explode.
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
    # Overflow guard: a collapsed/inverted triangle gives a garbage huge sigma1 (even inf);
    # scrub non-finite and cap it so it cannot poison the tear test, the marker or the log.
    s1 = np.clip(np.nan_to_num(s1, nan=0.0, posinf=0.0, neginf=0.0), -1.0e6, 1.0e6)
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

    # Seed the crack as an INTERIOR nick near r=NICK_RADIUS, angle 0 -- well inside the
    # fixed rim, in the operating region, where a hand pull can actually stress the tip.
    # (Seeding on the fixed rim is why it was un-tearable: a pinned tip never reaches the
    # sigma1 threshold no matter how hard you pull.) seed_v is the nick centre; v_a and v0
    # are two opposite neighbours -- the controller opens the closed fan along the line
    # v_a - seed_v - v0 into a slit, making v0 a real crack tip.
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
    v_a = max(nb, key=lambda v: P[v, 1] - P[seed_v, 1])   # neighbour toward +y
    v0 = min(nb, key=lambda v: P[v, 1] - P[seed_v, 1])    # opposite neighbour toward -y
    return verts, faces, n_real, rim, disc, seed_v, v_a, v0


def _make_controller(mo, topo, fem, springs, mass, visual, n_real, seed_v, v_a, v0, marker):
    import Sofa
    import numpy as np

    class _C(Sofa.Core.Controller):
        def __init__(self, *a, **k):
            Sofa.Core.Controller.__init__(self, *a, **k)
            self.mo, self.topo = mo, topo
            self.fem, self.springs, self.mass = fem, springs, mass
            self.visual = visual
            self.marker = marker
            self.next_spare = n_real
            self.crack = [v_a, seed_v]        # prev, tip -- v0 is opened in on the 1st step
            self.first_fwd = v0
            self.seeded = False
            self.last_check = -1e9
            self.last_pull_log = -1e9
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
            if self.stopped:
                return
            # One-time: open the interior nick. seed_v's fan is a CLOSED ring; splitting it
            # along the line v_a - seed_v - v0 turns it into an OPEN slit, so v0 becomes a
            # real crack tip that a pull can drive. Coincident spare -> nothing moves until
            # you pull.
            # keep the bright marker on the current crack tip (where to grab / pull toward)
            if self.marker is not None:
                self.marker.position.value = [
                    np.array(self.mo.position.value)[self.crack[-1]].tolist()]
            if not self.seeded:
                self.seeded = True
                sp = self._split_tip(self.crack[-1], self.crack[-2], self.first_fwd)
                if sp is not None:
                    self.pairs.append((self.crack[-1], sp))
                    self.crack.append(self.first_fwd)
                    print(f"[Tear] nick opened at v{self.crack[-2]} (r"
                          f"={float(np.hypot(*np.array(self.mo.position.value)[self.crack[-2], :2])):.1f}); "
                          f"Shift+drag the flap near it to tear")
                return
            if t < TEAR_SETTLE_T or t - self.last_check < TEAR_CHECK_DT:
                return
            self.last_check = t
            if self.adj is None:
                self._build_adj()

            # --- PULL DIAGNOSTIC: is your pull even reaching the tip? ------------------
            # Prints, while you are pulling: the stress AT THE TIP (what the tear test uses),
            # WHERE the stress is actually highest, and WHERE you are pulling + its distance
            # to the tip. If tipSigma1 stays tiny while you pull far from the tip, the tear
            # criterion is behaving correctly -- the load just is not reaching the crack.
            P = np.array(self.mo.position.value)
            R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            s1, _ = sigma1_of(P, R, tris, YOUNG, POISSON)
            pull = np.linalg.norm(P[:n_real] - R[:n_real], axis=1)
            jmax = int(np.argmax(pull)) if pull.size else 0
            if pull.size and pull[jmax] > 0.12 and t - self.last_pull_log >= PULL_LOG_DT:
                self.last_pull_log = t
                tip = self.crack[-1]
                touch = [k for k in range(len(tris)) if tip in tris[k]]
                tipS = max((s1[k] for k in touch), default=0.0)
                kmax = int(np.argmax(s1))
                cen = P[tris].mean(axis=1)
                gr = float(np.hypot(cen[kmax, 0], cen[kmax, 1]))
                ga = float(np.degrees(np.arctan2(cen[kmax, 1], cen[kmax, 0])))
                tr = float(np.hypot(P[tip, 0], P[tip, 1]))
                ta = float(np.degrees(np.arctan2(P[tip, 1], P[tip, 0])))
                pr = float(np.hypot(P[jmax, 0], P[jmax, 1]))
                pa = float(np.degrees(np.arctan2(P[jmax, 1], P[jmax, 0])))
                d2t = float(np.hypot(P[jmax, 0] - P[tip, 0], P[jmax, 1] - P[tip, 1]))
                print(f"[Pull] tipSigma1={tipS:5.0f} (x{TIP_STRESS_GAIN}={tipS * TIP_STRESS_GAIN:5.0f} "
                      f"vs thr {STRESS_THRESHOLD:.0f}) tip@r{tr:.1f},{ta:.0f}d | "
                      f"maxSigma1={s1[kmax]:5.0f}@r{gr:.1f},{ga:.0f}d | "
                      f"youPull {pull[jmax]:.1f}@r{pr:.1f},{pa:.0f}d dist-to-tip={d2t:.1f} | "
                      f"crackLen={len(self.pairs)}")

            # --- ADVANCE: unzip up to MAX_ADVANCE_PER_CHECK while the tip stays loaded ----
            for _ in range(MAX_ADVANCE_PER_CHECK):
                if self._advance_once(t) != "advanced":
                    break

        def _advance_once(self, t):
            """Try to advance the crack tip ONE vertex. Returns 'advanced' on success, or a
            reason string. Only a true dead-end (no neighbours left) stops the crack for
            good; 'below_threshold'/'no_forward' just wait for a better pull."""
            P = np.array(self.mo.position.value)
            R = np.array(self.mo.rest_position.value)
            tris = np.array(self.topo.triangles.value)
            s1, sdir = sigma1_of(P, R, tris, YOUNG, POISSON)
            tip, prev = self.crack[-1], self.crack[-2]
            touch = [k for k in range(len(tris)) if tip in tris[k]]
            if not touch:
                return "no_touch"
            khot = max(touch, key=lambda k: s1[k])
            if s1[khot] * TIP_STRESS_GAIN < STRESS_THRESHOLD:
                return "below_threshold"
            nrm = self._tip_normal(P, tris, touch)
            perp = np.cross(nrm, sdir[khot])
            if np.linalg.norm(perp) < 1e-6:
                return "no_perp"
            perp = perp / np.linalg.norm(perp)
            if np.dot(perp, P[tip] - P[prev]) < 0:
                perp = -perp
            cands = [v for v in self.adj.get(tip, ()) if v not in self.crack and v < n_real]
            if not cands:
                self.stopped = True
                print(f"[Tear] t={t:.2f} reached a boundary; stopping")
                return "dead_end"
            # stay in the operating annulus: never step toward the central pole (explodes)
            # or onto the fixed rim
            rc = np.hypot(P[:, 0], P[:, 1])
            cands = [v for v in cands if TEAR_R_MIN <= rc[v] <= TEAR_R_MAX]
            if not cands:
                return "out_of_annulus"      # crack hit the ring edge -> wait, do not force

            def align(v):
                w = P[v] - P[tip]
                return float(np.dot(w / (np.linalg.norm(w) + 1e-9), perp))

            vnext = max(cands, key=align)
            if align(vnext) < 0.2:
                return "no_forward"           # wait for a better pull, do NOT stop for good
            sp = self._split_tip(tip, prev, vnext)
            if sp is None:
                return "split_fail"
            self.pairs.append((tip, sp))
            self.crack.append(vnext)
            P = np.array(self.mo.position.value)
            gaps = [float(np.linalg.norm(P[a] - P[b])) for a, b in self.pairs]
            rr = float(np.hypot(P[vnext, 0], P[vnext, 1]))
            aa = float(np.degrees(np.arctan2(P[vnext, 1], P[vnext, 0])))
            print(f"[Tear] t={t:5.2f} sigma1={s1[khot]:5.0f} tip v{tip}->v{vnext} "
                  f"(r={rr:4.1f} ang={aa:6.1f}deg z={P[vnext,2]:4.1f}); "
                  f"crack len={len(self.pairs)} max-gap={max(gaps):.2f}")
            return "advanced"

        def onAnimateEndEvent(self, event):
            # Velocity clamp first: catch a violent mouse yank before it can blow a triangle
            # up (an in-plane tear pull is fine; a hard up-yank used to NaN the whole mesh).
            if MAX_SPEED > 0:
                Vel = np.array(self.mo.velocity.value)
                if Vel.size:
                    sp = np.linalg.norm(Vel, axis=1)
                    hot = sp > MAX_SPEED
                    if hot.any():
                        Vel[hot] *= (MAX_SPEED / sp[hot])[:, None]
                        self.mo.velocity.value = Vel.tolist()
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

    verts, faces, n_real, rim, disc, seed_v, seed_a, seed_fwd = _geometry()

    # The lens (visual obstacle the flap folds up over).
    lens = root.addChild("Lens")
    lens.addObject("MeshOBJLoader", name="bloader", filename=os.path.join(_HERE, "lens.obj"))
    lens.addObject("OglModel", name="lensVisual", src="@bloader", color=[0.45, 0.55, 0.75, 0.45])

    cap = root.addChild("Cap")
    cap.addObject("EulerImplicitSolver", rayleighStiffness=0.4, rayleighMass=0.2)
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

    # A bright marker sitting on the crack TIP so you can SEE where to grab (the nick is a
    # coincident slit -- invisible until pulled). The controller moves it onto the tip.
    mk = root.addChild("TipMarker")
    marker = mk.addObject("MechanicalObject", name="mk", position=[list(verts[seed_v])],
                          showObject=SHOW_TIP_MARKER, showObjectScale=0.25, drawMode=1,
                          showColor=[1.0, 0.15, 0.1, 1.0])

    cap.addObject(_make_controller(mo, topo, fem, springs, mass, oglm, n_real,
                                   seed_v, seed_a, seed_fwd, marker))

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
