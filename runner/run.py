"""Runner: fresh env per run, agent acts, verifier checks, results persisted.
Two modes: in-process (fast, for debugging) and Docker (isolated; verifier stays on the host)."""
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from agentproof.env.session import run_agent
from agentproof.verifiers.verify import verify

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "agentproof-env"


class _State:
    """Read-only view over a DB file copied out of a container; same .db shape the verifier expects."""
    def __init__(self, path):
        self.db = sqlite3.connect(path)


def load_tasks(directory=ROOT / "tasks"):
    return [yaml.safe_load(p.read_text()) for p in sorted(Path(directory).glob("*.yaml"))]


def ensure_image():
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        subprocess.run(["docker", "build", "-q", "-t", IMAGE, "-f", str(ROOT / "env" / "Dockerfile"),
                        str(ROOT.parent)], check=True)


def _record(task, agent_name, attempt, claim, steps, seconds, verdict, trace):
    return {"task": task["id"], "agent": agent_name, "attempt": attempt, "claim": claim,
            "steps": steps, "seconds": seconds, "trace": trace, **verdict}


def run_one(task, agent_name, attempt=0):
    t0 = time.time()
    env, claim, timed_out, trace = run_agent(task, agent_name)
    verdict = verify(env, task, claim, timed_out)
    return _record(task, agent_name, attempt, claim, len(trace), round(time.time() - t0, 3), verdict, trace)


def run_one_docker(task, agent_name, attempt=0):
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        hidden = {k: v for k, v in task.items() if k != "checks"}   # container never sees the checks
        (Path(d) / "task.json").write_text(json.dumps(hidden))
        os.chmod(d, 0o777)
        cmd = ["docker", "run", "--rm", "--network", "none", "--memory", "256m", "--pids-limit", "64",
               "--cpus", "1", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{d}:/work", IMAGE, agent_name]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:      # wall-clock kill counts as a timeout
            env = _State(":memory:")
            verdict = verify(_empty_env(task), task, "fail", timed_out=True)
            return _record(task, agent_name, attempt, "fail", 0, round(time.time() - t0, 3), verdict, [])
        res = json.loads((Path(d) / "result.json").read_text())
        state = _State(Path(d) / "state.db")
        verdict = verify(state, task, res["claim"], res["timed_out"])
        state.db.close()
    return _record(task, agent_name, attempt, res["claim"], len(res["trace"]),
                   round(time.time() - t0, 3), verdict, res["trace"])


def _empty_env(task):
    from agentproof.env.itsm import ITSM
    e = ITSM()
    e.seed(task["seed"])
    return e


def save(results, db_path=ROOT / "results.db"):
    db = sqlite3.connect(db_path)
    db.execute("""CREATE TABLE IF NOT EXISTS runs(run_id TEXT, ts REAL, agent TEXT, task TEXT,
                  attempt INT, passed INT, category TEXT, false_claim INT, steps INT,
                  trace TEXT, checks TEXT)""")
    run_id = uuid.uuid4().hex[:8]
    for r in results:
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (run_id, time.time(), r["agent"], r["task"], r["attempt"], int(r["passed"]),
                    r["category"], int(r["false_claim"]), r["steps"],
                    json.dumps(r["trace"]), json.dumps(r["checks"])))
    db.commit()
    return run_id


def run_all(agents, k=1, docker=False, workers=1):
    fn = run_one_docker if docker else run_one
    if docker:
        ensure_image()
    jobs = [(t, a, i) for a in agents for t in load_tasks() for i in range(k)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda j: fn(*j), jobs))


def summarize(results):
    out = {}
    for r in results:
        s = out.setdefault(r["agent"], {"n": 0, "pass": 0, "false_claim": 0, "cats": {}})
        s["n"] += 1
        s["pass"] += r["passed"]
        s["false_claim"] += r["false_claim"]
        s["cats"][r["category"]] = s["cats"].get(r["category"], 0) + 1
    return out
