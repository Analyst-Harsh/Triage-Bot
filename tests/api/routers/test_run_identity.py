from api.routers.runs import RunIdentity


def test_run_identity_derives_thread_id_from_owner_repo_issue_number() -> None:
    run = RunIdentity("octo", "repo", 42)

    assert run.owner == "octo"
    assert run.repo == "repo"
    assert run.issue_number == 42
    assert run.thread_id == "octo/repo#42"


def test_run_identity_from_repo_full_name_splits_owner_and_repo() -> None:
    run = RunIdentity.from_repo_full_name("octo/repo", 42)

    assert run.owner == "octo"
    assert run.repo == "repo"
    assert run.thread_id == "octo/repo#42"


def test_run_identity_from_repo_full_name_only_splits_on_first_slash() -> None:
    # A repo name containing a literal "/" (contrived, but worth pinning)
    # must not have the owner/repo split applied past the first segment.
    run = RunIdentity.from_repo_full_name("octo/repo/with/slashes", 1)

    assert run.owner == "octo"
    assert run.repo == "repo/with/slashes"
