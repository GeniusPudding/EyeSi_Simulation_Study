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


def main():
    rest, tris = _read_obj(CAP_OBJ)

    # (0) self-check: the inline Green sigma1 must equal the shipped principal_stress()
    pos = rest.copy(); pos[:, 0] *= 1.1; pos[:, 1] *= 1.1
    s1g, _, _, _, _ = both_stresses(pos, rest, tris)
    s1_real, _, _ = principal_stress(pos, rest, tris, E=E, nu=NU)
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


if __name__ == "__main__":
    main()
