/******************************************************************************
 * Capsulorhexis plugin for SOFA - faithful INRIA CCC tearing model            *
 * init.cpp - plugin entry points and component registration.                  *
 ******************************************************************************/
#include <Capsulorhexis/config.h>
#include <sofa/core/ObjectFactory.h>

namespace sofa::capsulorhexis
{

// Component registrations (defined in each component's .cpp).
void registerTriangularFiberFEMForceField(sofa::core::ObjectFactory* factory);
// FiberFractureEngine needs the Tearing dependency; guard it.
#ifdef CAPSULORHEXIS_HAVE_TEARING
void registerFiberFractureEngine(sofa::core::ObjectFactory* factory);
#endif

extern "C"
{
    SOFA_CAPSULORHEXIS_API void initExternalModule();
    SOFA_CAPSULORHEXIS_API const char* getModuleName();
    SOFA_CAPSULORHEXIS_API const char* getModuleVersion();
    SOFA_CAPSULORHEXIS_API const char* getModuleLicense();
    SOFA_CAPSULORHEXIS_API const char* getModuleDescription();
    SOFA_CAPSULORHEXIS_API void registerObjects(sofa::core::ObjectFactory* factory);
}

void initExternalModule()
{
    static bool first = true;
    if (first)
    {
        first = false;
    }
}

const char* getModuleName() { return MODULE_NAME; }
const char* getModuleVersion() { return MODULE_VERSION; }
const char* getModuleLicense() { return "GPL-3.0 (mirrors the Tearing plugin it extends)"; }
const char* getModuleDescription()
{
    return "Faithful reproduction of the Allard/Marchal/Cotin 2009 fiber-based "
           "soft-tissue tearing model for continuous curvilinear capsulorhexis "
           "(CCC), as used by Dequidt et al. 2013.";
}

void registerObjects(sofa::core::ObjectFactory* factory)
{
    // Each component's .cpp exposes a registerX(factory) forwarded here.
    registerTriangularFiberFEMForceField(factory);
#ifdef CAPSULORHEXIS_HAVE_TEARING
    registerFiberFractureEngine(factory);
#endif
}

} // namespace sofa::capsulorhexis
