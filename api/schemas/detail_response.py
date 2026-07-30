from graph.schemas.base import StrictBaseModel


class DetailResponse(StrictBaseModel):
    """Generic `{"detail": ...}` body for a webhook delivery that didn't put
    a run in flight: an ignored event type, an ignored issue action, or a
    duplicate/already-in-progress redelivery."""

    detail: str
