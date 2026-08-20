/******************************************************************************
 * Capsulorhexis plugin for SOFA                                               *
 * TopologySplitEngine.h - open a mesh at one vertex through the OFFICIAL       *
 * topology API, so every topology-dependent component is notified.             *
 *                                                                             *
 * WHY THIS EXISTS                                                             *
 * The Python scene used to open the mesh by writing topo.triangles directly.   *
 * That bypasses TriangleSetTopologyModifier, so the container never rebuilds   *
 * its EDGE list and no component receives a topology-change event. Measured    *
 * consequences on a torn capsule: topo.edges held 6321 entries against 6389    *
 * real triangle edges -- 129 stale ones, every single one within an edge       *
 * length of the crack and held at 1.04x rest, i.e. springs STAPLING the cut    *
 * shut so it could never open; and 197 real edges with no spring at all, which *
 * is where the runaway stretch came from.                                      *
 *                                                                             *
 * The fix has to be C++: SofaPython3 binds PointSetTopologyModifier            *
 * (addPoints/removePoints) but NOT TriangleSetTopologyModifier, so             *
 * addTriangles/removeTriangles are unreachable from a scene script.            *
 *                                                                             *
 * DATA-DRIVEN, for the same reason: Python cannot call arbitrary C++ methods   *
 * either. The scene writes the request into Data and bumps 'request'; this      *
 * component performs the split at the start of the next animation step and     *
 * reports the new vertex in 'newPoint'.                                        *
 ******************************************************************************/
#pragma once

#include <Capsulorhexis/config.h>
#include <sofa/core/objectmodel/BaseObject.h>
#include <sofa/core/objectmodel/Data.h>
#include <sofa/type/vector.h>
#include <sofa/component/topology/container/dynamic/TriangleSetTopologyContainer.h>
#include <sofa/component/topology/container/dynamic/TriangleSetTopologyModifier.h>

namespace sofa::capsulorhexis
{

class SOFA_CAPSULORHEXIS_API TopologySplitEngine : public core::objectmodel::BaseObject
{
public:
    SOFA_CLASS(TopologySplitEngine, core::objectmodel::BaseObject);

    using Container = component::topology::container::dynamic::TriangleSetTopologyContainer;
    using Modifier  = component::topology::container::dynamic::TriangleSetTopologyModifier;
    using TriangleID = core::topology::BaseMeshTopology::TriangleID;

    /// vertex to duplicate
    Data<int> d_splitPoint;
    /// triangles that must end up attached to the DUPLICATE instead of the original
    Data<type::vector<unsigned int>> d_movedTriangles;
    /// bump this to ask for a split; anything else is ignored
    Data<int> d_request;
    /// index of the vertex created by the last served request (-1 if it failed)
    Data<int> d_newPoint;
    /// the request id that was actually served, so the scene can tell it happened
    Data<int> d_served;

    void init() override;
    void handleEvent(core::objectmodel::Event* event) override;

protected:
    TopologySplitEngine();
    ~TopologySplitEngine() override = default;

    /// Perform one split. Returns the new vertex id, or -1 if it could not be done.
    int doSplit();

    Container* m_container { nullptr };
    Modifier*  m_modifier  { nullptr };
    int        m_lastRequest { 0 };
};

} // namespace sofa::capsulorhexis
