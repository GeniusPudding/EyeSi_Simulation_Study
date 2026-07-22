/******************************************************************************
 * Capsulorhexis plugin for SOFA - faithful INRIA CCC tearing model            *
 * config.h - export macros and module identity.                               *
 ******************************************************************************/
#pragma once

#include <sofa/config.h>

// Bring the SOFA namespace in, as SOFA plugins conventionally do.
using namespace sofa;

#ifdef SOFA_BUILD_CAPSULORHEXIS
#  define SOFA_TARGET Capsulorhexis
#  define SOFA_CAPSULORHEXIS_API SOFA_EXPORT_DYNAMIC_LIBRARY
#else
#  define SOFA_CAPSULORHEXIS_API SOFA_IMPORT_DYNAMIC_LIBRARY
#endif

namespace sofa::capsulorhexis
{
    constexpr const char* MODULE_NAME = "Capsulorhexis";
    constexpr const char* MODULE_VERSION = "0.1";
} // namespace sofa::capsulorhexis
