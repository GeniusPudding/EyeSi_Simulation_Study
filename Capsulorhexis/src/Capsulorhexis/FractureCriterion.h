/******************************************************************************
 * Capsulorhexis plugin for SOFA - faithful INRIA CCC tearing model            *
 *                                                                             *
 * FractureCriterion.h - Marchal 2009 fiber-based tearing criterion (Eq. 3-6). *
 *                                                                             *
 * Source: J. Allard, M. Marchal, S. Cotin, "Fiber-based Fracture Model for    *
 * Simulating Soft Tissue Tearing", MMVR 17, Stud. Health Technol. Inform.     *
 * 2009, section 2.2. Reused verbatim by Dequidt et al. 2013, section 4.       *
 ******************************************************************************/
#pragma once

// This header is deliberately SOFA-FREE (only <cmath>): it is the paper's math,
// nothing else, so it can be unit-tested standalone against the paper's own
// stated properties (the isotropic special case == maximum principal stress).
// The SOFA component (FiberFractureEngine) feeds it stress + fiber data.
#include <cmath>
#include <limits>

namespace sofa::capsulorhexis
{

/**
 * The paper, in its own notation. All quantities live in one triangular
 * element's local (co-rotational) 2D frame (x, y); n is the element normal.
 * The stress tensor is sigma = (sigma_x, sigma_y, tau_xy).
 *
 *  Eq.2  Fracture when  sigma_F > sigma_bar_F  or  sigma_T > sigma_bar_T
 *  Eq.3  Tearing occurs if  c(d, sigma, f, p) > 1
 *  Eq.4  c(d, sigma, f, p) = ( sigma_{d_perp} / sigma_bar_{d_perp} )
 *                            * H( (d . p) - cos theta_P ),   d_perp = d x n
 *  Eq.5  sigma_u = cos^2(t) sigma_x + sin^2(t) sigma_y + 2 sin(t) cos(t) tau_xy
 *  Eq.6  sigma_bar_u = sigma_bar_T + (sigma_bar_F - sigma_bar_T)
 *                      * [ 1 - (2/pi) acos(|u . f|) ]^alpha
 *        d_fracture = argmax_d c(d, sigma, f, p)              (section 2.2.2)
 *
 *  d       : candidate crack PROPAGATION direction (angle from local x).
 *  d_perp  : = d x n, the in-plane normal to the crack. A Mode-I crack is
 *            opened by the tensile stress ACROSS it -> the criterion uses
 *            sigma at angle (d + 90deg), not along d.
 *  p       : previous propagation direction; the Heaviside gate forbids turns
 *            larger than theta_P (stress/fiber are undirected, p fixes the sign).
 *
 * Paper's stated special case (the correctness oracle used in the tests):
 *   sigma_bar_F == sigma_bar_T and theta_P == 90deg  =>  argmax_d c reduces to
 *   the classical maximum-principal-stress criterion (crack opens normal to the
 *   largest principal stress). argmaxFractureDirection() reproduces that exactly.
 */
template <class Real>
struct MaterialStrength
{
    Real sigmaBarF;   ///< tensile strength ALONG the fibers (tough direction)
    Real sigmaBarT;   ///< tensile strength TRANSVERSE to fibers (weak; radial tear)
    Real alpha;       ///< interpolation power (peak steepness) for Eq.6

    MaterialStrength(Real F = Real(1), Real T = Real(1), Real a = Real(1))
        : sigmaBarF(F), sigmaBarT(T), alpha(a) {}

    bool isotropic(Real tol = Real(1e-12)) const
    {
        return std::abs(sigmaBarF - sigmaBarT) <= tol;
    }
};

/// Eq.5 -- normal stress on a plane whose normal is at angle theta_u from x.
/// sigma = {sigma_x, sigma_y, tau_xy}. Its maximum over theta_u equals the
/// largest eigenvalue of the 2x2 stress tensor.
template <class Real>
inline Real projectStress(Real sigmaX, Real sigmaY, Real tauXY, Real thetaU)
{
    const Real c = std::cos(thetaU);
    const Real s = std::sin(thetaU);
    return c * c * sigmaX + s * s * sigmaY + Real(2) * s * c * tauXY;
}

/// Eq.6 -- tensile strength in the direction u (angle uAngle), given fiber angle.
/// |u . f| = |cos(uAngle - fiberAngle)|. Bracket is 1 for u||f, 0 for u _|_ f,
/// so strength runs from sigmaBarF (along fiber) to sigmaBarT (transverse).
template <class Real>
inline Real directionalStrength(Real uAngle, Real fiberAngle,
                                const MaterialStrength<Real>& mat)
{
    Real dot = std::abs(std::cos(uAngle - fiberAngle));
    if (dot > Real(1)) dot = Real(1);           // guard acos domain vs fp drift
    if (dot < Real(0)) dot = Real(0);
    const Real pi = Real(3.14159265358979323846);
    Real factor = Real(1) - (Real(2) / pi) * std::acos(dot);
    if (factor < Real(0)) factor = Real(0);     // guard fractional-power base
    const Real interp = std::pow(factor, mat.alpha);
    return mat.sigmaBarT + (mat.sigmaBarF - mat.sigmaBarT) * interp;
}

/// Eq.6, frame-free form -- strength given the cosine of the angle between the
/// stress-carrying direction u and the fiber f (i.e. absCos = |u . f| for unit
/// world vectors). The SOFA engine uses this directly: it has u and f as world
/// vectors and takes their dot product, avoiding any local-frame bookkeeping.
template <class Real>
inline Real directionalStrengthFromCos(Real absCos, const MaterialStrength<Real>& mat)
{
    if (absCos > Real(1)) absCos = Real(1);
    if (absCos < Real(0)) absCos = Real(0);
    const Real pi = Real(3.14159265358979323846);
    Real factor = Real(1) - (Real(2) / pi) * std::acos(absCos);
    if (factor < Real(0)) factor = Real(0);
    const Real interp = std::pow(factor, mat.alpha);
    return mat.sigmaBarT + (mat.sigmaBarF - mat.sigmaBarT) * interp;
}

/// H(a) with the paper's convention H(a-b)=1 iff a>=b, i.e. H(a>=0)=1.
template <class Real>
inline Real heaviside(Real a) { return a >= Real(0) ? Real(1) : Real(0); }

/**
 * Eq.4 -- the fracture criterion c for one candidate propagation direction d.
 *
 * @param dAngle     angle of crack propagation direction d (radians, from x)
 * @param prevAngle  angle of previous propagation direction p; pass NaN to
 *                   disable the Heaviside no-backtrack gate (fresh crack tip)
 * @param thetaP     max allowed turn from p (radians); default pi/2 is the value
 *                   at which the isotropic case == max principal stress.
 * @return c = (sigma_{d_perp} / sigma_bar_{d_perp}) * H((d.p) - cos thetaP);
 *         0 for compressive (non-opening) stress.
 */
template <class Real>
inline Real criterionC(Real dAngle,
                       Real sigmaX, Real sigmaY, Real tauXY,
                       Real fiberAngle,
                       const MaterialStrength<Real>& mat,
                       Real prevAngle = std::numeric_limits<Real>::quiet_NaN(),
                       Real thetaP = Real(1.57079632679489661923) /* pi/2 */)
{
    const Real pi = Real(3.14159265358979323846);
    const Real dPerp = dAngle + pi / Real(2);   // d_perp = d x n : 90deg from d

    const Real sigmaDPerp = projectStress(sigmaX, sigmaY, tauXY, dPerp);
    if (sigmaDPerp <= Real(0)) return Real(0);  // only tensile stress can tear

    const Real strength = directionalStrength(dPerp, fiberAngle, mat);
    if (strength <= Real(0)) return Real(0);

    Real gate = Real(1);
    if (!std::isnan(prevAngle))
        gate = heaviside(std::cos(dAngle - prevAngle) - std::cos(thetaP));

    return (sigmaDPerp / strength) * gate;
}

/// Result of the argmax search (Eq.3 + section 2.2.2).
template <class Real>
struct FractureDecision
{
    Real angle;   ///< best propagation-direction angle (radians); NaN if none
    Real c;       ///< the criterion value there; tears iff c > 1
    bool tears() const { return c > Real(1); }
};

/**
 * Eq.3 + section 2.2.2 -- d_fracture = argmax_d c(d, sigma, f, p).
 * Exhaustive search over propagation directions in [0, pi) (a crack line is
 * undirected; p resolves the propagation sign). nSamples sets the angular
 * resolution of the "exhaustive search on all the directions" of the paper.
 */
template <class Real>
inline FractureDecision<Real> argmaxFractureDirection(
    Real sigmaX, Real sigmaY, Real tauXY,
    Real fiberAngle,
    const MaterialStrength<Real>& mat,
    Real prevAngle = std::numeric_limits<Real>::quiet_NaN(),
    Real thetaP = Real(1.57079632679489661923),
    int nSamples = 720)
{
    const Real pi = Real(3.14159265358979323846);
    FractureDecision<Real> best{ std::numeric_limits<Real>::quiet_NaN(), Real(0) };
    for (int k = 0; k < nSamples; ++k)
    {
        const Real dAngle = pi * Real(k) / Real(nSamples);
        const Real c = criterionC(dAngle, sigmaX, sigmaY, tauXY,
                                  fiberAngle, mat, prevAngle, thetaP);
        if (c > best.c) { best.c = c; best.angle = dAngle; }
    }
    return best;
}

/// Eigen-decomposition of the 2x2 symmetric stress tensor [[sx,txy],[txy,sy]].
/// Returns the major principal stress and (via out params) minor + its angle.
/// Independent oracle for the isotropic special case; also the fast path when
/// the material is isotropic (Eq.2 degenerate).
template <class Real>
inline Real principalStress(Real sx, Real sy, Real txy,
                            Real* sigma2 = nullptr, Real* angle1 = nullptr)
{
    const Real avg = Real(0.5) * (sx + sy);
    const Real radius = std::hypot(Real(0.5) * (sx - sy), txy);
    if (sigma2) *sigma2 = avg - radius;
    if (angle1) *angle1 = Real(0.5) * std::atan2(Real(2) * txy, sx - sy);
    return avg + radius;   // sigma1 (major)
}

} // namespace sofa::capsulorhexis
