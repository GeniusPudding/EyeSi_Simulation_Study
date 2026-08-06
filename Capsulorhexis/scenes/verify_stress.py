"""Verify our geometric sigma1 corresponds to SOFA's co-rotational FEM stress.

WHY: cap_membrane.py shows a per-triangle sigma1 heatmap computed by our own numpy
observer (principal_stress()). SOFA's TriangularFEMForceFieldOptim computes its OWN
principal stress (drawn by showStressVector, CAP_FEM_STRESS_VIZ=1), but it is NOT readable
from Python (triangleInfo returns "Invalid type"), so the two cannot be compared live. This
script instead reimplements SOFA's exact stress formula in numpy and compares it against our
observer on the SAME geometry -- a rigorous, offline cross-check of both magnitude and
direction. It needs numpy only (no SOFA); run:  py -3.12 scenes/verify_stress.py

THE TWO FORMULAS differ only in the strain measure (both remove rigid rotation via the same
deformation gradient F, both use the same isotropic plane-stress law sigma = C:eps):
  - OURS  (browser observer): Green-Lagrange strain  eps_G = 1/2 (F^T F - I)
  - SOFA  (co-rotational FEM): linear strain in the co-rotated frame  eps_L = U - I,
                               where U = sqrt(F^T F) is the right stretch tensor (F = R U).
eps_G and eps_L are both coaxial with U, so the PRINCIPAL DIRECTION is identical; only the
MAGNITUDE differs, and only at large strain (eps_G = eps_L + 1/2 eps^2 + ...).
"""
import os
import sys
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from cap_membrane import principal_stress   # the REAL shipped observer

CAP_OBJ = os.path.join(_HERE, "cap.obj")
E, NU = 1200.0, 0.3


def _read_obj(path):
    verts, faces = [], []
    for ln in open(path):
        if ln.startswith("v "):
            verts.append([float(x) for x in ln.split()[1:4]])
        elif ln.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in ln.split()[1:4]])
    return np.array(verts), np.array(faces)


def both_stresses(pos, rest, tris, E=E, nu=NU):
    """Per triangle, in each triangle's local 2D frame: (s1_green, ang_green, s1_corot,
    ang_corot, area_ratio). Green matches principal_stress(); corot is SOFA's formula."""
    def frame(P):
        e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
        n = np.cross(e1, e2)
        x = e1 / np.maximum(np.linalg.norm(e1, axis=1), 1e-12)[:, None]
        z = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
        return x, np.cross(z, x)

    def uv(P, x, y):
        e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
        return np.stack([np.stack([(e1 * x).sum(1), (e2 * x).sum(1)], 1),
                         np.stack([(e1 * y).sum(1), (e2 * y).sum(1)], 1)], 1)

    xr, yr = frame(rest[tris]); xc, yc = frame(pos[tris])
    Dm = uv(rest[tris], xr, yr); Ds = uv(pos[tris], xc, yc)
    F = Ds @ np.linalg.inv(Dm)
    C = np.einsum('tki,tkj->tij', F, F)                    # F^T F
    eps_G = 0.5 * (C - np.eye(2))
    w, V = np.linalg.eigh(C)                               # C symmetric PD
    U = V @ (np.sqrt(np.maximum(w, 1e-12))[:, :, None] * np.transpose(V, (0, 2, 1)))
    eps_L = U - np.eye(2)
    c = E / (1.0 - nu * nu)

    def principal(eps):
        sxx = c * (eps[:, 0, 0] + nu * eps[:, 1, 1])
        syy = c * (eps[:, 1, 1] + nu * eps[:, 0, 0])
        sxy = c * (1.0 - nu) * eps[:, 0, 1]
        mid = 0.5 * (sxx + syy)
        dev = np.sqrt(np.maximum(((sxx - syy) * 0.5) ** 2 + sxy ** 2, 0.0))
        ang = np.degrees(0.5 * np.arctan2(2.0 * sxy, sxx - syy))
        return mid + dev, ang

    s1g, ag = principal(eps_G); s1l, al = principal(eps_L)
    return s1g, ag, s1l, al, np.abs(np.linalg.det(F))


def _angdiff(a, b):
    d = np.abs(a - b) % 180.0
    return np.minimum(d, 180.0 - d)


def _c_of(d_deg, s1, s2, ang1_deg, fib_deg, sT, sL, alpha):
    """c(d) for a per-element array of candidate crack angles d (Eq.1-4). Shared by the
    coarse scan and the refinement so both evaluate exactly the same function."""
    u = d_deg + 90.0
    psi = np.radians(u - ang1_deg)
    sigma_u = s1 * np.cos(psi) ** 2 + s2 * np.sin(psi) ** 2
    duf = np.radians(u - fib_deg)
    fold = np.arccos(np.abs(np.cos(duf)))
    thr = sT + (sL - sT) * (1.0 - fold / (np.pi / 2)) ** alpha
    return np.where(sigma_u > 0.0, sigma_u / thr, 0.0)


def inria_c(s1, s2, ang1_deg, fib_deg, sT, sL, alpha, dstep=5.0, refine=0):
    """INRIA anisotropic tear criterion (Dequidt 2013 Eq.1-4), nucleation form (H=1).

    For each element, search candidate CRACK directions d (0..180 deg, step dstep). The
    stress that OPENS a crack along d is the normal stress across it, i.e. along u = d+90:
        sigma_u = s1 cos^2(psi) + s2 sin^2(psi),  psi = angle(u, sigma1-dir)      (Eq.3,
    rewritten in principal axes -- identical to the paper's x/y form). The direction-
    dependent strength is interpolated between the transverse and fiber-longitudinal
    thresholds by the angle between u and the fiber f:
        sigma_bar_u = sT + (sL - sT) * (1 - (2/pi) * acos|u.f|)^alpha              (Eq.4)
    c(d) = sigma_u / sigma_bar_u; tearing if max_d c >= 1, crack runs along argmax d
    (Eq.1-2 with the history term H=1: nucleation, no previous direction p yet).

    Returns (cmax, dstar_deg) arrays. Vectorised over elements x directions.
    """
    ds = np.arange(0.0, 180.0, dstep)                    # candidate crack angles [deg]
    u = ds + 90.0                                        # opening-normal angles  [deg]
    psi = np.radians(u[None, :] - ang1_deg[:, None])     # angle(u, sigma1-dir)
    sigma_u = s1[:, None] * np.cos(psi) ** 2 + s2[:, None] * np.sin(psi) ** 2
    duf = np.radians(u[None, :] - fib_deg[:, None])
    fold = np.arccos(np.abs(np.cos(duf)))                # angle(u, f) folded to [0, pi/2]
    thr = sT + (sL - sT) * (1.0 - fold / (np.pi / 2)) ** alpha
    c = np.where(sigma_u > 0.0, sigma_u / thr, 0.0)      # compression cannot open a crack
    k = np.argmax(c, axis=1)
    best_c, best_d = c[np.arange(len(s1)), k], ds[k]
    # LOCAL REFINEMENT: the coarse scan alone is not accurate enough -- at 5 deg the argmax
    # direction is off by ~1.2 deg (median) and c by up to 27%, and a crack path accumulates
    # that error every step. c(d) has kinks (the fold at u = fiber), so use bracket bisection
    # rather than a derivative method: each pass samples inside the current bracket and
    # shrinks it, converging geometrically and staying correct across a kink.
    if refine:
        half = dstep
        for _ in range(refine):
            half *= 0.5
            cand = np.stack([best_d - half, best_d, best_d + half], axis=1)
            cc = np.stack([_c_of(cand[:, j], s1, s2, ang1_deg, fib_deg, sT, sL, alpha)
                           for j in range(3)], axis=1)
            j = np.argmax(cc, axis=1)
            idx = np.arange(len(s1))
            best_d, best_c = cand[idx, j] % 180.0, cc[idx, j]
    return best_c, best_d


def main():
    rest, tris = _read_obj(CAP_OBJ)

    # (0) self-check: the inline Green sigma1 must equal the shipped principal_stress()
    pos = rest.copy(); pos[:, 0] *= 1.1; pos[:, 1] *= 1.1
    s1g, _, _, _, _ = both_stresses(pos, rest, tris)
    s1_real, _, _, _ = principal_stress(pos, rest, tris, E=E, nu=NU)
    err = float(np.max(np.abs(s1g - s1_real)))
    print(f"self-check vs shipped principal_stress(): max |diff| = {err:.2e}  "
          f"({'OK' if err < 1e-6 else 'MISMATCH'})")

    print("\n=== ours (Green) vs SOFA co-rotational (linear), uniform stretch s ===")
    print(" s      strain   dir diff (deg)     sigma1 ratio corot/green")
    print("                 median   max       median   min")
    for s in (1.02, 1.05, 1.10, 1.20, 1.35, 1.50):
        pos = rest.copy(); pos[:, 0] *= s; pos[:, 1] *= s
        s1g, ag, s1l, al, ar = both_stresses(pos, rest, tris)
        good = (ar > 0.25) & (ar < 4.0) & (s1g > 1.0)
        dd = _angdiff(ag[good], al[good]); ratio = s1l[good] / s1g[good]
        print(f" {s:4.2f}   {s - 1:5.0%}    {np.median(dd):6.3f}  {dd.max():6.3f}    "
              f"{np.median(ratio):6.3f}  {ratio.min():6.3f}")

    print("\n=== analytic ground truth (single triangle, uniaxial x-stretch lam) ===")
    R1 = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]); T1 = np.array([[0, 1, 2]])
    for lam in (1.05, 1.20):
        P1 = R1.copy(); P1[1, 0] = lam
        s1g, ag, _, _, _ = both_stresses(P1, R1, T1)
        analytic = E / (1 - NU * NU) * 0.5 * (lam * lam - 1)   # Green uniaxial sigma1
        print(f" lam={lam}: analytic={analytic:8.1f}  ours={s1g[0]:8.1f}  "
              f"dir ours={ag[0]:.1f} deg (analytic 0)")

    print("\nCONCLUSION: direction is identical (both coaxial with the stretch U); magnitude "
          "agrees within ~1% at small strain and ours (Green) runs up to ~20% higher at 50% "
          "strain; ours matches the analytic solution exactly.")

    # ------------------------------------------------------------------------------
    # INRIA anisotropic argmax-c criterion (Dequidt 2013 Eq.1-4): correctness checks
    # ------------------------------------------------------------------------------
    rng = np.random.default_rng(7)
    N = 5000
    s1r = rng.uniform(0.5, 100.0, N)
    s2r = s1r - rng.uniform(0.1, 80.0, N)          # s2 < s1, may be negative
    a1r = rng.uniform(-90.0, 90.0, N)              # sigma1 direction
    fbr = rng.uniform(-90.0, 90.0, N)              # fiber direction
    sT = 10.0

    print("\n=== INRIA argmax-c: isotropic special case must reduce to Rankine ===")
    # Paper: with sigma_bar_F = sigma_bar_T the criterion IS max-principal-stress. So with
    # sL == sT the argmax crack direction must be perpendicular to sigma1 and c = s1/sT.
    cmax, dstar = inria_c(s1r, s2r, a1r, fbr, sT, sT, alpha=2.0, dstep=1.0)
    want_dir = (a1r + 90.0) % 180.0                # Rankine: crack perp to sigma1
    dd = _angdiff(dstar, want_dir)
    cerr = np.abs(cmax - s1r / sT)
    # Exact discretisation bound for a 1-deg search: the best sampled direction is at most
    # 0.5 deg off, where sigma_u = s1 - (s1-s2) sin^2(0.5 deg) -> c short of s1/sT by at
    # most max(s1-s2)/sT * sin^2(0.5 deg). Anything under that bound IS Rankine.
    bound = float(np.max(s1r - s2r)) / sT * np.sin(np.radians(0.5)) ** 2
    print(f"  {N} random states: dir err max = {dd.max():.3f} deg (search step 1.0), "
          f"c err max = {cerr.max():.2e} (discretisation bound {bound:.2e})  -> "
          f"{'REDUCES TO RANKINE: OK' if dd.max() <= 0.5 + 1e-9 and cerr.max() <= bound else 'FAIL'}")

    print("\n=== fiber effect 1: crack ACROSS fibers is suppressed by sL/sT ===")
    # Uniaxial tension along the fiber: the Rankine crack (perp sigma1) would have its
    # opening normal u parallel to f -> threshold sL. c must drop from s1/sT toward s1/sL.
    one = np.array([50.0]); zero = np.array([0.0])
    for ratio in (1.0, 2.0, 4.0):
        cmax, dstar = inria_c(one, zero, zero, zero, sT, sT * ratio, alpha=2.0, dstep=1.0)
        print(f"  sL/sT={ratio:3.1f}: c = {cmax[0]:6.2f} (isotropic would be {50.0/sT:.2f}) "
              f"crack dir = {dstar[0]:5.1f} deg")

    print("\n=== direction search: coarse scan is NOT enough, refinement fixes it ===")
    # A crack path accumulates the direction error at every step, so the argmax must be
    # resolved far better than the scan step. Compare against a 0.01 deg reference.
    rc, rd = inria_c(s1r, s2r, a1r, fbr, sT, 2.5 * sT, alpha=2.0, dstep=0.01)
    print("  config              dir err med/max (deg)     c rel-err med/max")
    for step, ref in ((5.0, 0), (5.0, 6), (3.0, 6)):
        cc, dd_ = inria_c(s1r, s2r, a1r, fbr, sT, 2.5 * sT, alpha=2.0,
                          dstep=step, refine=ref)
        e = _angdiff(dd_, rd)
        rel = np.abs(cc - rc) / np.maximum(rc, 1e-9)
        print(f"  step {step:4.1f} refine {ref}   {np.median(e):8.4f} / {e.max():7.3f}"
              f"      {np.median(rel):.1e} / {rel.max():.1e}")
    # A large direction error is legitimate where TWO local maxima are nearly tied -- the
    # argmax then flips basin while c is essentially unchanged, which is ambiguity in the
    # problem, not error in the search. Judge on the well-separated cases, and report how
    # many ties there were (their c agrees to <1%, so the tear decision is unaffected).
    cc, dd_ = inria_c(s1r, s2r, a1r, fbr, sT, 2.5 * sT, alpha=2.0, dstep=3.0, refine=6)
    e = _angdiff(dd_, rd)
    rel = np.abs(cc - rc) / np.maximum(rc, 1e-9)
    # Only directions that differ MATERIALLY are suspicious; of those, a case is a genuine
    # tie (two equally tear-prone directions) if our c matches the reference c anyway --
    # a real search failure would return a strictly SMALLER c.
    big = e > 0.5
    bad = big & (rel > 1e-3)
    print(f"  -> shipped (3 deg + 6 refine): median dir err {np.median(e):.4f} deg; "
          f"{big.sum()}/{len(e)} differ >0.5 deg, of which {bad.sum()} are real search "
          f"failures (c lower than reference)  {'OK' if bad.sum() == 0 else 'FAIL'}")

    print("\n=== fiber effect 2: concentric fibers keep the tear CIRCUMFERENTIAL ===")
    # The capsule case: fibers tangential (concentric), test a RADIAL-pull stress state
    # (sigma1 radial). Crack along the circumference has opening normal u radial = perp f
    # -> threshold sT (easy); a radial crack has u tangential = along f -> sL (hard). The
    # argmax must pick the circumferential direction.
    th = rng.uniform(0.0, 360.0, 200)              # element azimuths around the disc
    fib = (th + 90.0) % 180.0                      # tangential fiber direction
    sig1dir = th % 180.0                           # sigma1 radial
    s1c = np.full(200, 60.0); s2c = np.full(200, 20.0)
    cmax, dstar = inria_c(s1c, s2c, sig1dir, fib, sT, 3.0 * sT, alpha=2.0, dstep=1.0)
    dd = _angdiff(dstar, fib)                      # crack should run ALONG the fiber
    print(f"  200 elements, sL/sT=3: crack-vs-fiber angle max = {dd.max():.2f} deg, "
          f"c = {cmax[0]:.2f} (= s1/sT = {60.0/sT:.2f})  -> "
          f"{'STAYS CURVILINEAR: OK' if dd.max() <= 1.0 else 'FAIL'}")


if __name__ == "__main__":
    main()
