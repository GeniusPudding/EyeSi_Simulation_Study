/******************************************************************************
 * Capsulorhexis plugin for SOFA - faithful INRIA CCC tearing model            *
 *                                                                             *
 * FiberFractureEngine.h - the Marchal 2009 fiber-based tearing ENGINE.        *
 *                                                                             *
 * Subclasses the Tearing plugin's BaseTearingEngine to reuse its (working)    *
 * stress extraction, threshold filtering and fracture-start-vertex selection, *
 * but replaces the isotropic maximum-principal-stress direction with the      *
 * paper's fiber-based argmax-c criterion (Eq.3-6), and drives the topology cut *
 * with PROPERLY computed endpoints (the stock TearingEngine passes            *
 * uninitialised endpoints to the cut algorithm).                              *
 *                                                                             *
 * Direction convention (all world-space): the criterion is evaluated for      *
 * candidate propagation directions d in the max-stress triangle's plane. The  *
 * opening (Mode-I) stress across d is sigma_{d_perp}, which SOFA computes for  *
 * us via TriangularFEMForceField::computeStressAcrossDirection. The fiber      *
 * direction is read (world-space, mesh-deformed) via getFiberDir on the       *
 * anisotropic FEM. See FractureCriterion.h for the equations.                 *
 ******************************************************************************/
#pragma once

#include <Capsulorhexis/config.h>
#include <Capsulorhexis/FractureCriterion.h>

#include <Tearing/BaseTearingEngine.h>

namespace sofa::capsulorhexis
{

/**
 * FiberFractureEngine<DataTypes> : BaseTearingEngine<DataTypes>
 *
 * New Data (the paper's tearing-criterion parameters):
 *   d_sigmaBarF  sigma_bar_F : tensile strength ALONG the fibers (tough)
 *   d_sigmaBarT  sigma_bar_T : tensile strength TRANSVERSE to fibers (weak; the
 *                              radial tear of capsulorhexis runs here)
 *   d_alpha      alpha       : peak steepness of the Eq.6 strength interpolation
 *   d_thetaP     theta_P     : max turn per propagation step (Eq.4 Heaviside),
 *                              in degrees; default 90 (isotropic-equivalent)
 *   d_angularSamples         : resolution of the exhaustive argmax search
 *
 * When d_sigmaBarF == d_sigmaBarT and theta_P == 90deg the engine provably
 * reduces to the maximum-principal-stress criterion of the stock TearingEngine
 * (verified by the standalone unit test).
 */
template <class DataTypes>
class FiberFractureEngine : public sofa::component::engine::BaseTearingEngine<DataTypes>
{
public:
    SOFA_CLASS(SOFA_TEMPLATE(FiberFractureEngine, DataTypes),
               SOFA_TEMPLATE(sofa::component::engine::BaseTearingEngine, DataTypes));

    typedef typename DataTypes::Real Real;
    typedef typename DataTypes::Coord Coord;
    typedef typename DataTypes::VecCoord VecCoord;
    typedef typename DataTypes::Deriv Deriv;

    using Index = sofa::core::topology::BaseMeshTopology::Index;
    using Triangle = sofa::core::topology::BaseMeshTopology::Triangle;

    void init() override;

    /// Tearing-criterion parameters (Marchal Eq.6 / Eq.4).
    Data<Real> d_sigmaBarF;         ///< tensile strength along the fibers
    Data<Real> d_sigmaBarT;         ///< tensile strength transverse to the fibers
    Data<Real> d_alpha;             ///< Eq.6 interpolation power (peak steepness)
    Data<Real> d_thetaP;            ///< max turn per step (deg), Eq.4 Heaviside gate
    Data<int>  d_angularSamples;    ///< exhaustive-search angular resolution
    Data<VecCoord> d_fiberCenter;   ///< concentric-fiber centre (match the FEM's); empty => isotropic criterion

protected:
    FiberFractureEngine();
    ~FiberFractureEngine() override = default;

    /// BaseTearingEngine pure-virtuals: our fiber-aware implementations.
    void computeFracturePath() override;
    void algoFracturePath() override;

    /// Evaluate Eq.3-6 at the current max-stress triangle and return the
    /// world-space propagation direction d_fracture (argmax_d c). Returns false
    /// if there is no valid candidate (no tensile opening / all gated out).
    bool computeFiberFractureDirection(Coord& outDir, Real& outC);

    /// Endpoints Pb, Pc of the cut segment along +/- dir from Pa, using the
    /// neighbour-triangle intersection of the reused TearingAlgorithms.
    bool computeEndpointsAlong(const Coord& Pa, const Coord& dir, Coord& Pb, Coord& Pc);

    /// Previous propagation direction p (world). Zero => no gate (fresh crack).
    Coord m_previousDir;

    // Base-class members used here (pulled into scope for readability).
    using sofa::component::engine::BaseTearingEngine<DataTypes>::m_maxStressTriangleIndex;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::m_maxStressVertexIndex;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::m_triangleInfoTearing;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::m_triangularFEM;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::d_input_positions;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::d_triangleIdsOverThreshold;
    using sofa::component::engine::BaseTearingEngine<DataTypes>::d_fractureMaxLength;
};

#if !defined(SOFA_CAPSULORHEXIS_FIBERFRACTUREENGINE_CPP)
extern template class SOFA_CAPSULORHEXIS_API FiberFractureEngine<defaulttype::Vec3Types>;
#endif

} // namespace sofa::capsulorhexis
