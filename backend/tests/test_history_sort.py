"""TDD: history list sorts newest-first by created_at.

The /history endpoint returned rows in arbitrary filesystem order; this
helper sorts them so the latest run is always first.
"""
from app.utils.history_sort import sort_by_created_desc


def test_sorts_newest_first():
    rows = [
        {"simulation_id": "a", "created_at": "2026-07-06T21:59:00"},
        {"simulation_id": "b", "created_at": "2026-07-16T13:37:00"},
        {"simulation_id": "c", "created_at": "2026-06-29T00:12:00"},
    ]
    out = sort_by_created_desc(rows)
    assert [r["simulation_id"] for r in out] == ["b", "a", "c"]


def test_missing_or_blank_dates_sink_to_bottom():
    rows = [
        {"simulation_id": "x"},                                  # no date
        {"simulation_id": "y", "created_at": "2026-07-01T00:00:00"},
        {"simulation_id": "z", "created_at": ""},                # blank
    ]
    out = sort_by_created_desc(rows)
    assert out[0]["simulation_id"] == "y"
    assert {r["simulation_id"] for r in out[1:]} == {"x", "z"}


def test_does_not_mutate_input():
    rows = [
        {"simulation_id": "a", "created_at": "2026-01-01T00:00:00"},
        {"simulation_id": "b", "created_at": "2026-02-01T00:00:00"},
    ]
    original = list(rows)
    sort_by_created_desc(rows)
    assert rows == original  # input untouched (returns a new list)
