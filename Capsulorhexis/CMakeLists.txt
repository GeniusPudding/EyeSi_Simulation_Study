cmake_minimum_required(VERSION 3.22)
project(Capsulorhexis VERSION 0.1 LANGUAGES CXX)

# ---------------------------------------------------------------------------
# Capsulorhexis - a faithful SOFA plugin reproducing the INRIA fiber-based
# soft-tissue tearing model (Allard/Marchal/Cotin 2009; Dequidt et al. 2013)
# for continuous curvilinear capsulorhexis (CCC).
#
# Build against a local SOFA binary SDK. Point CMAKE_PREFIX_PATH at the SOFA
# install (see scripts/build.ps1, which sets it from SOFA_ROOT). SOFA's own
# CMake config packages provide the imported targets we link.
# ---------------------------------------------------------------------------

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- SOFA dependencies (imported targets from the SOFA SDK) ----------------
find_package(Sofa.Core REQUIRED)
find_package(Sofa.Component.SolidMechanics.FEM.Elastic REQUIRED)
find_package(Sofa.Component.Topology.Container.Dynamic REQUIRED)

# The Tearing plugin (InfinyTech3D) provides BaseTearingEngine, which our
# FiberFractureEngine subclasses. Its TearingTargets.cmake references these
# imported targets but TearingConfig.cmake omits their find_package calls, so we
# import them first (otherwise find_package(Tearing) reports NOT FOUND).
find_package(Sofa.Component.MechanicalLoad REQUIRED)
find_package(Sofa.Component.StateContainer REQUIRED)
find_package(Sofa.Component.Constraint.Projective REQUIRED)
find_package(Tearing QUIET)

# --- plugin sources --------------------------------------------------------
set(HEADER_FILES
    src/Capsulorhexis/config.h
    src/Capsulorhexis/FractureCriterion.h
    src/Capsulorhexis/TriangularFiberFEMForceField.h
    src/Capsulorhexis/TriangularFiberFEMForceField.inl
)
set(SOURCE_FILES
    src/Capsulorhexis/init.cpp
    src/Capsulorhexis/TriangularFiberFEMForceField.cpp
)

# FiberFractureEngine (Marchal Eq.3-6) needs the Tearing plugin's BaseTearingEngine.
if(Tearing_FOUND)
    list(APPEND HEADER_FILES
        src/Capsulorhexis/FiberFractureEngine.h
        src/Capsulorhexis/FiberFractureEngine.inl
    )
    list(APPEND SOURCE_FILES
        src/Capsulorhexis/FiberFractureEngine.cpp
    )
endif()

add_library(${PROJECT_NAME} SHARED ${SOURCE_FILES} ${HEADER_FILES})

target_include_directories(${PROJECT_NAME}
    PUBLIC "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>"
    PUBLIC "$<INSTALL_INTERFACE:include>"
)

# Export macro so config.h switches to SOFA_EXPORT_DYNAMIC_LIBRARY when building.
target_compile_definitions(${PROJECT_NAME} PRIVATE SOFA_BUILD_CAPSULORHEXIS)

target_link_libraries(${PROJECT_NAME}
    PUBLIC Sofa.Core
    PUBLIC Sofa.Component.SolidMechanics.FEM.Elastic
    PUBLIC Sofa.Component.Topology.Container.Dynamic
)
if(Tearing_FOUND)
    target_link_libraries(${PROJECT_NAME} PUBLIC Tearing)
    target_compile_definitions(${PROJECT_NAME} PRIVATE CAPSULORHEXIS_HAVE_TEARING)
endif()

# ---------------------------------------------------------------------------
# Standalone (SOFA-free) unit test of the Marchal criterion math. Depends on
# nothing but FractureCriterion.h, so it verifies the physics independently of
# the SOFA build/link.
# ---------------------------------------------------------------------------
option(CAPSULORHEXIS_BUILD_TESTS "Build the standalone criterion unit test" ON)
if(CAPSULORHEXIS_BUILD_TESTS)
    add_executable(Capsulorhexis_criterion_test tests/test_fracture_criterion.cpp)
    target_include_directories(Capsulorhexis_criterion_test
        PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    enable_testing()
    add_test(NAME criterion COMMAND Capsulorhexis_criterion_test)
endif()

message(STATUS "Capsulorhexis: Tearing plugin ${Tearing_FOUND}")
