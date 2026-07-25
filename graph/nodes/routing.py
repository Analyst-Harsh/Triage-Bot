from langgraph.graph import END

from graph.nodes.node_names import NodeName
from graph.schemas import PostOutcome
from graph.state import TriageState


def route_after_auto_post(state: TriageState) -> NodeName | str:
    """Conditional edge out of `auto_post`: only routes to
    `approval_queue` when at least one drafted action was left
    `PostOutcome.QUEUED` (i.e. non-LOW risk). Keeps `ApprovalQueueNode`'s
    own contract pure -- if it runs, it always interrupts -- rather than
    making the pause conditional inside the node body, and keeps an
    all-LOW-risk run's trace free of a no-op approval step.

    Return type is `NodeName | str`, not `NodeName | Literal["__end__"]`:
    langgraph's `END` constant is declared as a plain interned `str`, not
    a `Literal`, so a narrower annotation here wouldn't actually match it.
    """
    post_results = state["post_results"]
    if post_results is None:
        raise ValueError("route_after_auto_post called before post_results was set")
    if any(result.outcome == PostOutcome.QUEUED for result in post_results.action_results):
        return NodeName.APPROVAL_QUEUE
    return END
