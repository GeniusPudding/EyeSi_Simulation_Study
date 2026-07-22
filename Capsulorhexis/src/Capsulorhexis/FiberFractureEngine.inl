/******************************************************************************
 * Capsulorhexis plugin for SOFA - FiberFractureEngine.inl                      *
 * Implementation of the Marchal 2009 fiber-based tearing engine (Eq.3-6).      *
 ******************************************************************************/
#pragma once

#include <Capsulorhexis/FiberFractureEngine.h>
#include <Tearing/BaseTearingEngine.inl>

#include <cmath>

namespace sofa::capsulorhexis
{

using sofa::type::Vec3;
using sofa::type::cross;

template <class DataTypes>
FiberFractureEngine<DataTypes>::FiberFractureEngine()
    : d_sigmaBarF(initData(&d_sigmaBarF, Real(1.0), "sigmaBarF",
        "Marchal Eq.6: tensile strength ALONG the fibers (tough direction)"))
    , d_sigmaBarT(initData(&d_sigmaBarT, Real(1.0), "sigmaBarT",
        "Marchal Eq.6: tensile strength TRANSVERSE to the fibers (weak; the radial CCC tear)"))
    , d_alpha(initData(&d_alpha, Real(1.0), "alpha",
        "Marchal Eq.6: peak steepness of the directional-strength interpolation"))
    , d_thetaP(initData(&d_thetaP, Real(90.0), "thetaP",
        "Marchal Eq.4: max turn per propagation step in degrees (Heaviside no-backtrack gate)"))
    , d_angularSamples(initData(&d_angularSamples, 720, "angularSamples",
        "Angular resolution of the exhaustive argmax search over propagation directions"))
    , d_fiberCenter(initData(&d_fiberCenter, "fiberCenter",
        "Concentric-fiber centre in the global frame (set to match the FEM's fiberCenter). "
        "Empty => the Eq.6 fiber term degenerates and the criterion is maximum principal stress."))
    , m_previousDir(Coord())
{
}

template <class DataTypes>
void FiberFractureEngine<DataTypes>::init()
{
    // Base does all the topology / FEM / tearing-algorithm wiring.
    sofa::component::engine::BaseTearingEngine<DataTypes>::init();

    // The fiber direction for the Eq.6 strength term is derived from d_fiberCenter
    // (the concentric-fiber centre), computed on demand per triangle -- identical
    // to how TriangularFiberFEMForceField defines the material anisotropy, so the
    // criterion and the deformation share the same fibers without any coupling to
    // the FEM object (avoids fragile cross-module casts).
    if (d_fiberCenter.getValue().empty())
        msg_info() << "No fiberCenter set: the Eq.6 fiber term degenerates "
                      "(criterion = maximum principal stress).";
    else
        msg_info() << "Concentric fibers about " << d_fiberCenter.getValue()[0]
                   << " used for the Eq.6 directional-strength term.";

    m_previousDir = Coord();
}

template <class DataTypes>
bool FiberFractureEngine<DataTypes>::computeFiberFractureDirection(Coord& outDir, Real& outC)
{
    if (m_maxStressTriangleIndex == sofa::InvalidID || m_triangularFEM == nullptr)
        return false;

    auto* topo = this->getTopology();
    const VecCoord& x = d_input_positions.getValue();
    const Triangle& tri = topo->getTriangle(m_maxStressTriangleIndex);

    const Coord v0 = x[tri[0]];
    const Coord e01 = x[tri[1]] - v0;
    const Coord e02 = x[tri[2]] - v0;

    Coord n = cross(e01, e02);
    const Real nnorm = n.norm();
    if (nnorm < std::numeric_limits<Real>::epsilon())
        return false;              // degenerate triangle
    n /= nnorm;                    // unit normal

    Coord e0 = e01;
    e0.normalize();                // in-plane basis x
    Coord e1 = cross(n, e0);       // in-plane basis y (already unit)

    // Stress tensor of this element (local frame; SOFA projects world dirs into it).
    const type::Vec<3, Real> stress = m_triangleInfoTearing[m_maxStressTriangleIndex].stress;

    // Fiber direction (world-space) from the concentric-fiber centre: the tangent
    // of the circle through this element's centroid, in the element plane -- the
    // same definition the FEM uses for the material anisotropy. Empty fiberCenter
    // => no fiber term (isotropic maximum-principal-stress criterion).
    Coord fiber;
    bool haveFiber = false;
    if (!d_fiberCenter.getValue().empty())
    {
        const Coord centroid = (x[tri[0]] + x[tri[1]] + x[tri[2]]) * (Real(1) / Real(3));
        const Coord fcenter = d_fiberCenter.getValue()[0];
        fiber = cross(n, fcenter - centroid);   // concentric tangent, in-plane (n is unit)
        const Real fn = fiber.norm();
        if (fn > std::numeric_limits<Real>::epsilon()) { fiber /= fn; haveFiber = true; }
    }

    const MaterialStrength<Real> mat(d_sigmaBarF.getValue(), d_sigmaBarT.getValue(), d_alpha.getValue());

    // No-backtrack gate parameters (Eq.4).
    Coord prev = m_previousDir;
    const Real prevNorm = prev.norm();
    const bool hasPrev = prevNorm > std::numeric_limits<Real>::epsilon();
    if (hasPrev) prev /= prevNorm;
    const Real cosThetaP = std::cos(d_thetaP.getValue() * Real(M_PI) / Real(180.0));

    const int samples = std::max(8, d_angularSamples.getValue());
    Real bestC = Real(0);
    Coord bestDir;

    for (int k = 0; k < samples; ++k)
    {
        const Real theta = Real(M_PI) * Real(k) / Real(samples);   // [0, pi)
        Coord d = e0 * std::cos(theta) + e1 * std::sin(theta);     // world propagation dir (unit)

        // sigma_{d_perp}: opening (Mode-I) stress across d. SOFA applies Eq.5.
        Real sigmaAcross = 0;
        m_triangularFEM->computeStressAcrossDirection(sigmaAcross, m_maxStressTriangleIndex, d, stress);
        if (sigmaAcross <= Real(0))
            continue;              // only tensile stress can open a crack

        // Directional strength sigma_bar_{d_perp} (Eq.6). u = d_perp = d x n.
        Real absCos = Real(0);
        if (haveFiber)
        {
            Coord u = cross(d, n);
            u.normalize();
            absCos = std::abs(u * fiber);   // |u . f|
        }
        const Real strength = directionalStrengthFromCos(absCos, mat);
        if (strength <= Real(0))
            continue;

        // Heaviside no-backtrack gate.
        Real gate = Real(1);
        if (hasPrev)
            gate = heaviside((d * prev) - cosThetaP);

        const Real c = (sigmaAcross / strength) * gate;
        if (c > bestC) { bestC = c; bestDir = d; }
    }

    if (bestC <= Real(0))
        return false;

    outDir = bestDir;
    outC = bestC;
    return true;
}

template <class DataTypes>
bool FiberFractureEngine<DataTypes>::computeEndpointsAlong(const Coord& Pa, const Coord& dir,
                                                           Coord& Pb, Coord& Pc)
{
    Coord d = dir;
    const Real dn = d.norm();
    if (dn < std::numeric_limits<Real>::epsilon())
        return false;
    d /= dn;

    if (d_fractureMaxLength.getValue() > Real(0))
    {
        // Fixed-length symmetric cut (paper: bounded fracture length per step).
        Pb = Pa + d * d_fractureMaxLength.getValue();
        Pc = Pa - d * d_fractureMaxLength.getValue();
        return true;
    }

    // Otherwise run the cut to the boundary of the neighbouring triangles.
    auto* algo = this->getTearingAlgo();
    const auto tB = algo->computeIntersectionNeighborTriangle(m_maxStressVertexIndex, Pa,  d, Pb);
    const auto tC = algo->computeIntersectionNeighborTriangle(m_maxStressVertexIndex, Pa, -d, Pc);
    if (tB == sofa::InvalidID || tC == sofa::InvalidID)
    {
        msg_warning() << "Could not build the fracture path through neighbouring triangles.";
        return false;
    }
    return true;
}

template <class DataTypes>
void FiberFractureEngine<DataTypes>::computeFracturePath()
{
    this->clearFracturePath();
    if (m_maxStressTriangleIndex == sofa::InvalidID)
        return;

    Coord dir; Real c;
    if (!computeFiberFractureDirection(dir, c))
        return;

    const VecCoord& x = d_input_positions.getValue();
    const Coord Pa = x[m_maxStressVertexIndex];
    Coord Pb, Pc;
    if (!computeEndpointsAlong(Pa, dir, Pb, Pc))
        return;

    this->m_fracturePath.ptA = Vec3(DataTypes::getCPos(Pa));
    this->m_fracturePath.ptB = Vec3(DataTypes::getCPos(Pb));
    this->m_fracturePath.ptC = Vec3(DataTypes::getCPos(Pc));
    this->m_fracturePath.triIdA = m_maxStressTriangleIndex;

    this->getTearingAlgo()->computeFracturePath(this->m_fracturePath);
    this->m_stepCounter++;
}

template <class DataTypes>
void FiberFractureEngine<DataTypes>::algoFracturePath()
{
    helper::ReadAccessor< Data<type::vector<Index>> > candidate(d_triangleIdsOverThreshold);
    if (candidate.empty() || m_maxStressTriangleIndex == sofa::InvalidID)
        return;

    Coord dir; Real c;
    if (!computeFiberFractureDirection(dir, c))
        return;

    const VecCoord& x = d_input_positions.getValue();
    const int indexA = int(m_maxStressVertexIndex);
    const Coord Pa = x[indexA];
    Coord Pb, Pc;
    if (!computeEndpointsAlong(Pa, dir, Pb, Pc))
        return;

    // Side-classification normal used by TearingAlgorithms: in-plane and
    // PERPENDICULAR to the propagation direction (so triangles either side of
    // the cut line are separated). n_cut = n x d.
    const Triangle& tri = this->getTopology()->getTriangle(m_maxStressTriangleIndex);
    Coord n = cross(x[tri[1]] - x[tri[0]], x[tri[2]] - x[tri[0]]);
    n.normalize();
    Coord cutNormal = cross(n, dir);
    cutNormal.normalize();

    this->getTearingAlgo()->algoFracturePath(Pa, indexA, Pb, Pc,
        m_maxStressTriangleIndex, cutNormal, d_input_positions.getValue());

    // No FEM re-sync needed: TriangularFiberFEMForceField derives the fiber and
    // material stiffness on demand from geometry (no stored per-triangle array),
    // so newly torn triangles are handled automatically by the base's topology
    // callback -> our computeMaterialStiffness. (The stock anisotropic FEM needed
    // a reinit hack here because its fiber array did not follow topology changes.)

    // Remember the propagation direction for the next step's no-backtrack gate.
    m_previousDir = dir;
    m_maxStressTriangleIndex = sofa::InvalidID;
}

} // namespace sofa::capsulorhexis
