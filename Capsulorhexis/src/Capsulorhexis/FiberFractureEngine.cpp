/******************************************************************************
 * Capsulorhexis plugin for SOFA - FiberFractureEngine.cpp                      *
 * Explicit template instantiation + object-factory registration.              *
 ******************************************************************************/
#define SOFA_CAPSULORHEXIS_FIBERFRACTUREENGINE_CPP

#include <Capsulorhexis/FiberFractureEngine.inl>
#include <sofa/core/ObjectFactory.h>

namespace sofa::capsulorhexis
{

void registerFiberFractureEngine(sofa::core::ObjectFactory* factory)
{
    factory->registerObjects(sofa::core::ObjectRegistrationData(
        "Fiber-based soft-tissue tearing engine implementing the Allard/Marchal/"
        "Cotin 2009 argmax-c criterion (Eq.3-6) for continuous curvilinear "
        "capsulorhexis; a fiber-aware replacement for the isotropic TearingEngine.")
        .add< FiberFractureEngine<defaulttype::Vec3Types> >());
}

template class SOFA_CAPSULORHEXIS_API FiberFractureEngine<defaulttype::Vec3Types>;

} // namespace sofa::capsulorhexis
