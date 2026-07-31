import pytest

from graph.schemas import RunStatus, TimeRangePeriod


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


@pytest.mark.parametrize("value", ["1h", "24h", "7d", "30d"])
def test_time_range_period_round_trips_through_its_string_value(value: str) -> None:
    period = TimeRangePeriod(value)
    assert period.value == value
    assert TimeRangePeriod(period.value) is period
