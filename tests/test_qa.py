import pytest

from agentproof.qa.qa import qa_task
from agentproof.runner.run import load_tasks


@pytest.mark.parametrize("task", load_tasks(), ids=lambda t: t["id"])
def test_task_passes_qa(task):
    r = qa_task(task)
    assert r["solvable"], "oracle solution must pass"
    assert r["deterministic"]
    assert not r["survivors"], f"verifier accepts wrong end states: {r['survivors']}"
    assert not r["alt_valid_fail"], f"valid alternatives rejected: {r['alt_valid_fail']}"
    assert not r["perturb_fail"], f"verdict changed under perturbation: {r['perturb_fail']}"
