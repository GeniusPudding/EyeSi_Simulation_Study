/******************************************************************************
 * TopologySplitEngine.cpp - see the header for why this component exists.     *
 ******************************************************************************/
#include <Capsulorhexis/TopologySplitEngine.h>
#include <sofa/core/ObjectFactory.h>
#include <sofa/simulation/AnimateBeginEvent.h>
#include <sofa/core/topology/TopologyChange.h>

namespace sofa::capsulorhexis
{

TopologySplitEngine::TopologySplitEngine()
    : d_splitPoint(initData(&d_splitPoint, -1, "splitPoint",
          "vertex to duplicate"))
    , d_movedTriangles(initData(&d_movedTriangles, "movedTriangles",
          "triangles that should attach to the duplicate instead of the original"))
    , d_request(initData(&d_request, 0, "request",
          "bump to ask for a split"))
    , d_newPoint(initData(&d_newPoint, -1, "newPoint",
          "vertex created by the last served request, or -1 on failure"))
    , d_served(initData(&d_served, 0, "served",
          "the request id that was actually carried out"))
{
    this->f_listening.setValue(true);
}

void TopologySplitEngine::init()
{
    Inherit1::init();
    this->getContext()->get(m_container);
    this->getContext()->get(m_modifier);
    if (!m_container)
        msg_error() << "no TriangleSetTopologyContainer in this context; splits will be refused";
    if (!m_modifier)
        msg_error() << "no TriangleSetTopologyModifier in this context; splits will be refused";
    m_lastRequest = d_request.getValue();
}

void TopologySplitEngine::handleEvent(core::objectmodel::Event* event)
{
    if (!simulation::AnimateBeginEvent::checkEventType(event))
        return;
    const int req = d_request.getValue();
    if (req == m_lastRequest)
        return;                       // nothing asked for
    m_lastRequest = req;
    const int nv = doSplit();
    d_newPoint.setValue(nv);
    d_served.setValue(req);
}

int TopologySplitEngine::doSplit()
{
    if (!m_container || !m_modifier)
        return -1;

    const int v = d_splitPoint.getValue();
    const auto& moved = d_movedTriangles.getValue();
    const int nbPoints = static_cast<int>(m_container->getNbPoints());
    if (v < 0 || v >= nbPoints || moved.empty())
        return -1;

    // Capture the triangles BEFORE anything changes: removeTriangles renumbers the
    // remaining ones (SOFA swaps the last into the freed slot), so ids captured after
    // the removal would refer to different triangles.
    type::vector<core::topology::BaseMeshTopology::Triangle> rebuilt;
    type::vector<TriangleID> toRemove;
    rebuilt.reserve(moved.size());
    toRemove.reserve(moved.size());
    const int nbTri = static_cast<int>(m_container->getNbTriangles());
    for (const unsigned int t : moved)
    {
        if (static_cast<int>(t) >= nbTri) continue;
        rebuilt.push_back(m_container->getTriangle(t));
        toRemove.push_back(static_cast<TriangleID>(t));
    }
    if (toRemove.empty())
        return -1;

    // 1. Duplicate the vertex. Giving the original as the sole ancestor makes SOFA
    //    interpolate the new DOF from it, so position AND rest position come out right
    //    without the scene having to patch them afterwards.
    const type::vector<type::vector<core::topology::BaseMeshTopology::PointID>> ancestors{
        { static_cast<core::topology::BaseMeshTopology::PointID>(v) } };
    const type::vector<type::vector<SReal>> coefs{ { 1.0 } };
    m_modifier->addPoints(1, ancestors, coefs, true);
    const auto newPoint =
        static_cast<core::topology::BaseMeshTopology::PointID>(m_container->getNbPoints() - 1);

    // 2. Detach one side: drop those triangles, then add them back pointing at the
    //    duplicate. removeIsolatedEdges=true is the whole point -- it is what keeps the
    //    container's EDGE list correct, which is what the springs are built from.
    m_modifier->removeTriangles(toRemove, true, false);

    for (auto& tri : rebuilt)
        for (int k = 0; k < 3; ++k)
            if (static_cast<int>(tri[k]) == v)
                tri[k] = newPoint;
    m_modifier->addTriangles(rebuilt);

    return static_cast<int>(newPoint);
}

void registerTopologySplitEngine(sofa::core::ObjectFactory* factory)
{
    factory->registerObjects(sofa::core::ObjectRegistrationData(
        "Open a triangle mesh at one vertex through the official topology API, so "
        "edges are rebuilt and every topology-dependent component is notified.")
        .add<TopologySplitEngine>());
}

} // namespace sofa::capsulorhexis
