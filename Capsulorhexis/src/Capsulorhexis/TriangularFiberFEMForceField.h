/******************************************************************************
 * Capsulorhexis plugin for SOFA - faithful INRIA CCC tearing model            *
 *                                                                             *
 * TriangularFiberFEMForceField.h - transversely-isotropic co-rotational        *
 * triangular FEM (Marchal 2009 Eq.1), robust to topology changes (tearing).    *
 *                                                                             *
 * WHY THIS EXISTS: the stock TriangularAnisotropicFEMForceField stores the     *
 * fiber direction and transverse-modulus in per-triangle arrays that are NOT   *
 * grown when a tear adds triangles -- its own source admits "the topological   *
 * changes are not propagated through d_localFiberDirection" -- so it reads out *
 * of bounds and corrupts the forces during capsulorhexis. This class instead   *
 * subclasses the topology-ROBUST TriangularFEMForceField (whose d_triangleInfo *
 * TopologyData grows correctly) and overrides only the material-stiffness      *
 * computation, deriving the concentric fiber direction ON DEMAND from the      *
 * element's rest geometry + fiberCenter. There is no per-triangle fiber array  *
 * to fall out of sync, so multi-fracture anisotropic tearing stays stable.     *
 *                                                                             *
 * The anisotropic plane-stress stiffness matrix is Marchal Eq.1 (identical to  *
 * Dequidt 2013 sec.4): K rotated into the fiber frame (F along the fiber, T    *
 * transverse). fiberCenter at the disc centre => concentric fibers, i.e. the   *
 * circumferential direction is stiff/tough and the radial direction is weak,   *
 * so the tear runs radially exactly as in real continuous curvilinear          *
 * capsulorhexis.                                                              *
 ******************************************************************************/
#pragma once

#include <Capsulorhexis/config.h>
#include <sofa/component/solidmechanics/fem/elastic/TriangularFEMForceField.h>

namespace sofa::capsulorhexis
{

template <class DataTypes>
class TriangularFiberFEMForceField
    : public sofa::component::solidmechanics::fem::elastic::TriangularFEMForceField<DataTypes>
{
public:
    typedef sofa::component::solidmechanics::fem::elastic::TriangularFEMForceField<DataTypes> Inherited;
    SOFA_CLASS(SOFA_TEMPLATE(TriangularFiberFEMForceField, DataTypes),
               SOFA_TEMPLATE(sofa::component::solidmechanics::fem::elastic::TriangularFEMForceField, DataTypes));

    typedef typename DataTypes::Real Real;
    typedef typename DataTypes::Coord Coord;
    typedef typename DataTypes::Deriv Deriv;
    typedef typename DataTypes::VecCoord VecCoord;
    using Index = sofa::core::topology::BaseMeshTopology::Index;
    using Triangle = sofa::core::topology::BaseMeshTopology::Triangle;
    using Transformation = type::Mat<3, 3, Real>;

    /// Marchal Eq.1 material parameters. youngModulus / poissonRatio are the
    /// ALONG-fiber values, inherited from the base (BaseLinearElasticityFEMForceField).
    Data<Real> d_youngModulusTransverse;  ///< E_T: Young modulus transverse to the fibers (weak; radial tear)
    Data<VecCoord> d_fiberCenter;          ///< concentric-fiber centre (global). Empty => unidirectional (d_theta)
    Data<Real> d_theta;                    ///< fiber angle in the global frame (deg), used when fiberCenter is empty
    Data<bool> d_showFiber;                ///< draw the per-triangle fiber direction

    void init() override;
    void draw(const core::visual::VisualParams* vparams) override;

    /// Marchal Eq.1: build the transversely-isotropic plane-stress stiffness for
    /// element i, with the concentric fiber derived on demand from rest geometry.
    /// Called by the base's TriangleData creation callback for EVERY triangle,
    /// including tear-created ones -> topology robust.
    void computeMaterialStiffness(int i, Index& a, Index& b, Index& c) override;

    /// World-space fiber direction of an element at the CURRENT (deformed) config;
    /// used by FiberFractureEngine to evaluate the Eq.6 directional strength.
    void getFiberDir(int element, Deriv& dir) const;

protected:
    TriangularFiberFEMForceField();
    ~TriangularFiberFEMForceField() override = default;

    /// Fiber direction of element i in the global frame, from three positions.
    Coord fiberDirGlobal(const Coord& p0, const Coord& p1, const Coord& p2) const;
};

#if !defined(SOFA_CAPSULORHEXIS_TRIANGULARFIBERFEMFORCEFIELD_CPP)
extern template class SOFA_CAPSULORHEXIS_API TriangularFiberFEMForceField<defaulttype::Vec3Types>;
#endif

} // namespace sofa::capsulorhexis
