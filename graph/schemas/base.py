from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Shared base for every schema in this package: rejects unexpected
    fields outright (`extra="forbid"`) rather than silently dropping them.
    Matters most at trust boundaries (LLM structured output, external resume
    payloads) but is applied uniformly so no future schema can forget it."""

    model_config = ConfigDict(extra="forbid")
