/******************************************************************************
 * Standalone (SOFA-free) test of FractureCriterion.h against the paper.        *
 *                                                                             *
 * The Marchal 2009 paper states (section 2.2.2) that for the isotropic special *
 * case (sigma_bar_F == sigma_bar_T and theta_P == 90deg) the argmax-c criterion *
 * is EQUIVALENT to the maximum-principal-stress criterion. We test exactly     *
 * that against an independent eigen-decomposition oracle, plus the anisotropic *
 * behaviours the paper describes (Eq.5/Eq.6 monotonicity, no-backtrack gate).  *
 *                                                                             *
 * Build & run:  see scripts/build.ps1  (target: Capsulorhexis_criterion_test)  *
 ******************************************************************************/
#define _USE_MATH_DEFINES   // MSVC: expose M_PI from <cmath>
#include <cmath>
#ifndef M_PI
#  define M_PI 3.14159265358979323846
#endif

#include <Capsulorhexis/FractureCriterion.h>

#include <cstdio>
#include <vector>

using namespace sofa::capsulorhexis;
using Real = double;

static int g_failures = 0;

static void check(bool cond, const char* msg)
{
    if (!cond) { std::printf("  FAIL: %s\n", msg); ++g_failures; }
    else       { std::printf("  ok  : %s\n", msg); }
}

static Real angleDiff(Real a, Real b)
{
    // smallest absolute difference between two undirected line angles (mod pi)
    Real d = std::fmod(std::fabs(a - b), M_PI);
    if (d > M_PI / 2) d = M_PI - d;
    return d;
}

// ---------------------------------------------------------------------------
// Oracle: for the isotropic case, the crack must open normal to the major
// principal stress, so the propagation direction d must be PARALLEL to the
// major principal eigenvector, and c_max must equal sigma1 / sigma_bar.
// ---------------------------------------------------------------------------
static void testIsotropicEqualsMaxPrincipalStress()
{
    std::printf("[isotropic special case == maximum principal stress]\n");
    const Real strength = 2.0;
    MaterialStrength<Real> mat(strength, strength, 3.0);  // alpha irrelevant when F==T

    struct Case { Real sx, sy, txy; };
    std::vector<Case> cases = {
        {5.0, 1.0, 0.0},    // aligned to axes, sx major
        {1.0, 5.0, 0.0},    // aligned to axes, sy major
        {3.0, 3.0, 2.0},    // pure shear on top of hydrostatic
        {4.0, 1.0, 1.5},    // general
        {2.0, 6.0, -2.5},   // general, negative shear
        {7.0, -1.0, 0.8},   // one compressive eigenvalue
    };

    for (const auto& c : cases)
    {
        Real sigma2, angle1;
        const Real sigma1 = principalStress(c.sx, c.sy, c.txy, &sigma2, &angle1);

        auto dec = argmaxFractureDirection<Real>(c.sx, c.sy, c.txy,
                                                 /*fiberAngle*/0.0, mat,
                                                 /*prevAngle*/std::nan(""),
                                                 /*thetaP*/M_PI / 2, 3600);

        // c_max should equal sigma1/strength (major principal, tensile).
        const Real expectedC = sigma1 / strength;
        check(std::fabs(dec.c - expectedC) < 1e-3,
              "c_max == sigma1 / strength");

        // Max-principal-stress criterion: the crack OPENS normal to sigma1, so
        // the tensile-carrying normal d_perp aligns with the major eigenvector
        // (angle1), which makes the PROPAGATION direction d perpendicular to it.
        const Real expectedD = angle1 - M_PI / 2;   // d _|_ major eigenvector
        check(angleDiff(dec.angle, expectedD) < 2e-3,
              "argmax propagation direction perpendicular to major principal eigenvector");
    }
}

// ---------------------------------------------------------------------------
// Eq.6 must interpolate monotonically from sigma_bar_T (transverse) to
// sigma_bar_F (along fiber) as u rotates onto the fiber.
// ---------------------------------------------------------------------------
static void testDirectionalStrengthInterpolation()
{
    std::printf("[Eq.6 directional strength endpoints & monotonicity]\n");
    MaterialStrength<Real> mat(10.0 /*F tough*/, 2.0 /*T weak*/, 1.0);
    const Real fiber = 0.0;

    const Real along = directionalStrength<Real>(0.0, fiber, mat);            // u || f
    const Real across = directionalStrength<Real>(M_PI / 2, fiber, mat);      // u _|_ f
    check(std::fabs(along - 10.0) < 1e-9, "strength along fiber == sigma_bar_F");
    check(std::fabs(across - 2.0) < 1e-9, "strength across fiber == sigma_bar_T");

    Real prev = across;
    bool monotone = true;
    for (int k = 45; k >= 0; --k)   // rotate from transverse (90deg) toward fiber (0)
    {
        const Real u = M_PI * k / 90.0;
        const Real s = directionalStrength<Real>(u, fiber, mat);
        if (s < prev - 1e-9) monotone = false;
        prev = s;
    }
    check(monotone, "strength increases monotonically transverse -> fiber");
}

// ---------------------------------------------------------------------------
// Anisotropy must bias the tear: with equal stress magnitude, a weak transverse
// direction should be preferred over a tough along-fiber one. Concretely, under
// EQUAL-BIAXIAL stress (no preferred stress direction) the crack must open
// across the fibers (the radial tear of capsulorhexis).
// ---------------------------------------------------------------------------
static void testFiberBiasesFractureDirection()
{
    std::printf("[anisotropy biases the tear across the weak (transverse) axis]\n");
    // Equal biaxial stress: sigma_x = sigma_y, no shear -> stress alone gives no
    // preferred direction; only the fiber strength breaks the tie.
    const Real sx = 4.0, sy = 4.0, txy = 0.0;
    const Real fiber = 0.0;   // fibers along x
    MaterialStrength<Real> mat(10.0, 2.0, 4.0);  // transverse much weaker

    auto dec = argmaxFractureDirection<Real>(sx, sy, txy, fiber, mat,
                                             std::nan(""), M_PI / 2, 3600);
    // Weak (transverse) strength is across the fiber; the crack OPENS across the
    // fiber, i.e. d_perp _|_ fiber, i.e. propagation d PARALLEL to the fiber.
    check(angleDiff(dec.angle, fiber) < 2e-3,
          "under equal biaxial stress the tear runs along the fiber (opens across it)");
    check(dec.tears() == (dec.c > 1.0), "tears() consistent with c>1");
}

// ---------------------------------------------------------------------------
// Heaviside no-backtrack gate (Eq.4): a candidate whose turn from p exceeds
// theta_P must be rejected (c == 0), so the argmax cannot suddenly reverse.
// ---------------------------------------------------------------------------
static void testNoBacktrackGate()
{
    std::printf("[Eq.4 Heaviside no-backtrack gate]\n");
    MaterialStrength<Real> mat(3.0, 3.0, 1.0);  // isotropic strength
    const Real sx = 5.0, sy = 1.0, txy = 0.0;   // major principal along x

    // previous propagation along x; allow only +/-30deg turns.
    const Real prev = 0.0;
    const Real thetaP = M_PI / 6;  // 30 degrees

    // A candidate 80deg away from p must be gated out.
    const Real cFar = criterionC<Real>(M_PI * 80 / 180, sx, sy, txy, 0.0, mat, prev, thetaP);
    check(cFar == 0.0, "candidate beyond theta_P is rejected (c==0)");

    // A candidate within the cone is allowed (c>0 where there is tensile stress).
    const Real cNear = criterionC<Real>(M_PI * 10 / 180, sx, sy, txy, 0.0, mat, prev, thetaP);
    check(cNear > 0.0, "candidate within theta_P is allowed (c>0)");
}

int main()
{
    testIsotropicEqualsMaxPrincipalStress();
    testDirectionalStrengthInterpolation();
    testFiberBiasesFractureDirection();
    testNoBacktrackGate();

    if (g_failures == 0)
        std::printf("\nALL TESTS PASSED\n");
    else
        std::printf("\n%d TEST(S) FAILED\n", g_failures);
    return g_failures == 0 ? 0 : 1;
}
