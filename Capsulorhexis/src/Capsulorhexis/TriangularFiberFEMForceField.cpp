/******************************************************************************
 * Capsulorhexis plugin for SOFA - TriangularFiberFEMForceField.cpp             *
 * Explicit template instantiation + object-factory registration.              *
 ******************************************************************************/
#define SOFA_CAPSULORHEXIS_TRIANGULARFIBERFEMFORCEFIELD_CPP

#include <Capsulorhexis/TriangularFiberFEMForceField.inl>
#include <sofa/core/ObjectFactory.h>

namespace sofa::capsulorhexis
{

void registerTriangularFiberFEMForceField(sofa::core::ObjectFactory* factory)
{
    factory->registerObjects(sofa::core::ObjectRegistrationData(
        "Transversely-isotropic co-rotational triangular FEM (Marchal 2009 Eq.1) "
        "with concentric fibers, robust to topology changes (tearing) -- a "
        "topology-safe replacement for TriangularAnisotropicFEMForceField for use "
        "with the FiberFractureEngine during continuous curvilinear capsulorhexis.")
        .add< TriangularFiberFEMForceField<defaulttype::Vec3Types> >());
}

template class SOFA_CAPSULORHEXIS_API TriangularFiberFEMForceField<defaulttype::Vec3Types>;

} // namespace sofa::capsulorhexis
