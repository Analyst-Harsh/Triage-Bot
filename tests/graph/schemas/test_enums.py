from graph.schemas import RunStatus


def test_terminal_statuses_contains_every_terminal_value() -> None:
    assert RunStatus.terminal_statuses() == {
        RunStatus.AUTO_POSTED,
        RunStatus.APPROVED_AND_POSTED,
        RunStatus.REJECTED,
        RunStatus.FAILED,
    }


def test_terminal_statuses_excludes_in_flight_statuses() -> None:
    in_flight = {
        RunStatus.RECEIVED,
        RunStatus.PLANNING,
        RunStatus.RESEARCHING,
        RunStatus.DRAFTING,
        RunStatus.RISK_CHECK,
        RunStatus.PENDING_APPROVAL,
    }
    assert RunStatus.terminal_statuses().isdisjoint(in_flight)
