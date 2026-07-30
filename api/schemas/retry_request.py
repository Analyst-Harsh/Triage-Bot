from graph.schemas.base import StrictBaseModel


class RetryRequest(StrictBaseModel):
    """Body for `POST /runs/{owner}/{repo}/{issue_number}/retry`. `dry_run`
    of `None` (the default -- omitted entirely is equivalent) means "reuse
    whatever `dry_run` the failed run itself used"; an explicit value
    overrides it."""

    dry_run: bool | None = None
