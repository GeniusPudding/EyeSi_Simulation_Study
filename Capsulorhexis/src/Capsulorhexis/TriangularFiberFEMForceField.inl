/******************************************************************************
 * Capsulorhexis plugin for SOFA - TriangularFiberFEMForceField.inl             *
 * Marchal 2009 Eq.1 transversely-isotropic co-rotational triangular FEM.       *
 ******************************************************************************/
#pragma once

#include <Capsulorhexis/TriangularFiberFEMForceField.h>
#include <sofa/component/solidmechanics/fem/elastic/TriangularFEMForceField.inl>
#include <sofa/core/visual/VisualParams.h>
#include <sofa/helper/accessor.h>

#include <cmath>

namespace sofa::capsulorhexis
{

using sofa::type::cross;

template <class DataTypes>
TriangularFiberFEMForceField<DataTypes>::TriangularFiberFEMForceField()
    : d_youngModulusTransverse(initData(&d_youngModulusTransverse, Real(1000.0), "transverseYoungModulus",
        "Marchal Eq.1: Young modulus TRANSVERSE to the fibers (weak axis; the radial CCC tear runs here)"))
    , d_fiberCenter(initData(&d_fiberCenter, "fiberCenter",
        "Concentric-fiber centre in the global frame (put at the disc centre for capsulorhexis). Empty => unidirectional fibers at angle theta"))
    , d_theta(initData(&d_theta, Real(0.0), "fiberAngle",
        "Fiber angle in the global frame (degrees), used only when fiberCenter is empty"))
    , d_showFiber(initData(&d_showFiber, false, "showFiber",
        "Draw the per-triangle fiber direction"))
{
}

template <class DataTypes>
void TriangularFiberFEMForceField<DataTypes>::init()
{
    // The base wires up topology, mstate, the (topology-robust) d_triangleInfo
    // TopologyData and its creation callback -> our computeMaterialStiffness.
    Inherited::init();
}

template <class DataTypes>
typename DataTypes::Coord TriangularFiberFEMForceField<DataTypes>::fiberDirGlobal(
    const Coord& p0, const Coord& p1, const Coord& p2) const
{
    if (!d_fiberCenter.getValue().empty())
    {
        // Concentric fibers: tangent of the circle centred at fiberCenter,
        // i.e. perpendicular to the radial direction, in the element plane.
        const Coord centroid = (p0 + p1 + p2) * (Real(1) / Real(3));
        const Coord fcenter = d_fiberCenter.getValue()[0];
        const Coord normal = cross(p1 - p0, p2 - p0);
        return cross(normal, fcenter - centroid);
    }
    // Unidirectional fibers at a fixed global angle.
    const Real th = d_theta.getValue() * Real(M_PI) / Real(180.0);
    return Coord(std::cos(th), std::sin(th), Real(0));
}

template <class DataTypes>
void TriangularFiberFEMForceField<DataTypes>::computeMaterialStiffness(int i, Index& a, Index& b, Index& c)
{
    auto triangleInf = sofa::helper::getWriteAccessor(this->d_triangleInfo);
    auto& tinfo = triangleInf[i];

    // Rest positions of this element's three vertices.
    const VecCoord& x0 = this->mstate->read(core::vec_id::read_access::restPosition)->getValue();
    const Coord p0 = x0[a];
    const Coord p1 = x0[b];
    const Coord p2 = x0[c];

    // --- reduced plane-stress moduli in the fiber (F,T) frame (Marchal Eq.1) ---
    const Real young  = this->getYoungModulusInElement(i);     // E_F (along fiber)
    const Real poisson = this->getPoissonRatioInElement(i);    // nu_F
    Real young2 = d_youngModulusTransverse.getValue();         // E_T (transverse)
    if (young2 <= Real(0)) young2 = young;                     // guard
    // constraint from the paper: nu_T / E_T = nu_F / E_F  => nu_T = nu_F * E_T/E_F
    const Real poisson2 = poisson * (young2 / young);

    const Real denom = Real(1) - poisson * poisson2;
    const Real Q11 = young  / denom;
    const Real Q12 = poisson * young2 / denom;
    const Real Q22 = young2 / denom;
    const Real Q66 = young / (Real(2) * (Real(1) + poisson));   // shear modulus G_F

    // --- fiber direction expressed in the element's local orthonormal frame ---
    Coord fGlobal = fiberDirGlobal(p0, p1, p2);

    Transformation T;
    T[0] = p1 - p0;
    T[1] = p2 - p0;
    T[2] = cross(T[0], T[1]);
    T[1] = cross(T[2], T[0]);
    T[0].normalize();
    T[1].normalize();
    T[2].normalize();
    T.transpose();
    Transformation Tinv;
    Tinv.invert(T);

    Coord fLocal = Tinv * fGlobal;
    fLocal[2] = 0;
    const Real fn = fLocal.norm();
    Real cc = Real(1), ss = Real(0);
    if (fn > std::numeric_limits<Real>::epsilon())
    {
        fLocal /= fn;
        cc = fLocal[0];
        ss = fLocal[1];
    }

    // --- rotate the (F,T) moduli into the local frame by the fiber angle -------
    const Real c2 = cc * cc, s2 = ss * ss;
    const Real c3 = c2 * cc, s3 = s2 * ss;
    const Real c4 = c2 * c2, s4 = s2 * s2;

    const Real K11 = c4 * Q11 + Real(2) * c2 * s2 * (Q12 + Real(2) * Q66) + s4 * Q22;
    const Real K12 = c2 * s2 * (Q11 + Q22 - Real(4) * Q66) + (c4 + s4) * Q12;
    const Real K22 = s4 * Q11 + Real(2) * c2 * s2 * (Q12 + Real(2) * Q66) + c4 * Q22;
    const Real K16 = ss * c3 * (Q11 - Q12 - Real(2) * Q66) + s3 * cc * (Q12 - Q22 + Real(2) * Q66);
    const Real K26 = s3 * cc * (Q11 - Q12 - Real(2) * Q66) + ss * c3 * (Q12 - Q22 + Real(2) * Q66);
    const Real K66 = c2 * s2 * (Q11 + Q22 - Real(2) * Q12 - Real(2) * Q66) + (c4 + s4) * Q66;

    tinfo.materialMatrix(0, 0) = K11;
    tinfo.materialMatrix(0, 1) = K12;
    tinfo.materialMatrix(0, 2) = K16;
    tinfo.materialMatrix(1, 0) = K12;
    tinfo.materialMatrix(1, 1) = K22;
    tinfo.materialMatrix(1, 2) = K26;
    tinfo.materialMatrix(2, 0) = K16;
    tinfo.materialMatrix(2, 1) = K26;
    tinfo.materialMatrix(2, 2) = K66;

    // Fold in the element area, exactly as the base isotropic FEM does, so the
    // stress / force magnitudes (and thus the tearing threshold) are on the same
    // scale as the rest of SOFA. (The stock anisotropic FEM omits this, which
    // makes it ~1/area too stiff.)
    tinfo.materialMatrix *= tinfo.area;
}

template <class DataTypes>
void TriangularFiberFEMForceField<DataTypes>::getFiberDir(int element, Deriv& dir) const
{
    const VecCoord& x = this->mstate->read(core::vec_id::read_access::position)->getValue();
    const Triangle& t = this->l_topology->getTriangle(element);
    dir = fiberDirGlobal(x[t[0]], x[t[1]], x[t[2]]);   // world-space, deformed config
}

template <class DataTypes>
void TriangularFiberFEMForceField<DataTypes>::draw(const core::visual::VisualParams* vparams)
{
    Inherited::draw(vparams);
    if (!d_showFiber.getValue() || !this->l_topology)
        return;

    const VecCoord& x = this->mstate->read(core::vec_id::read_access::position)->getValue();
    const auto nbTri = this->l_topology->getNbTriangles();
    std::vector<type::Vec3> lines;
    for (Index i = 0; i < nbTri; ++i)
    {
        const Triangle& t = this->l_topology->getTriangle(i);
        const Coord centroid = (x[t[0]] + x[t[1]] + x[t[2]]) * (Real(1) / Real(3));
        Deriv f;
        getFiberDir(int(i), f);
        const Real n = f.norm();
        if (n < std::numeric_limits<Real>::epsilon()) continue;
        f *= (Real(0.3) / n);
        lines.emplace_back(centroid - f);
        lines.emplace_back(centroid + f);
    }
    vparams->drawTool()->drawLines(lines, 1.0f, sofa::type::RGBAColor(1.0f, 0.8f, 0.1f, 1.0f));
}

} // namespace sofa::capsulorhexis
