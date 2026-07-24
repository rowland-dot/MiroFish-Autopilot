"""TDD: permanent history-card delete (cascade).

Removes a card's project + simulation + report folders and best-effort deletes
the Zep graph. Local delete always succeeds even if the Zep delete fails.
"""
import os

from app.utils.history_delete import delete_history_records


def _mk(root, sub, rid, fname="x.json"):
    d = os.path.join(root, sub, rid)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
        f.write("data")
    return d


def test_removes_all_three_folders(tmp_path):
    root = str(tmp_path)
    _mk(root, "simulations", "sim_1")
    _mk(root, "projects", "proj_1")
    _mk(root, "reports", "report_1")

    res = delete_history_records(root, "sim_1", project_id="proj_1", report_id="report_1")

    assert not os.path.exists(os.path.join(root, "simulations", "sim_1"))
    assert not os.path.exists(os.path.join(root, "projects", "proj_1"))
    assert not os.path.exists(os.path.join(root, "reports", "report_1"))
    assert set(res["removed"]) == {"simulations/sim_1", "projects/proj_1", "reports/report_1"}


def test_missing_folders_are_skipped(tmp_path):
    root = str(tmp_path)
    _mk(root, "simulations", "sim_1")   # only the sim exists
    res = delete_history_records(root, "sim_1", project_id="proj_gone", report_id=None)
    assert res["removed"] == ["simulations/sim_1"]


def test_zep_graph_deleted_best_effort(tmp_path):
    root = str(tmp_path)
    _mk(root, "simulations", "sim_1")
    calls = []
    res = delete_history_records(root, "sim_1", graph_id="g1", zep_delete=lambda g: calls.append(g))
    assert calls == ["g1"]
    assert res["graph_deleted"] is True


def test_local_delete_succeeds_even_if_zep_fails(tmp_path):
    root = str(tmp_path)
    _mk(root, "simulations", "sim_1")
    def boom(g):
        raise RuntimeError("zep down / credit exhausted")
    res = delete_history_records(root, "sim_1", graph_id="g1", zep_delete=boom)
    assert res["removed"] == ["simulations/sim_1"]   # local still gone
    assert res["graph_deleted"] is False


def test_path_traversal_ids_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        delete_history_records(str(tmp_path), "../evil")
