"""Container entrypoint. Reads /work/task.json (checks stripped), runs the agent,
writes /work/result.json and a copy of the final DB to /work/state.db. Never sees the verifier."""
import json
import sqlite3
import sys
import time
from pathlib import Path

from agentproof.env.session import run_agent


def main(agent_name, work="/work"):
    work = Path(work)
    task = json.loads((work / "task.json").read_text())
    t0 = time.time()
    env, claim, timed_out, trace = run_agent(task, agent_name)
    dst = sqlite3.connect(work / "state.db")
    env.db.backup(dst)
    dst.close()
    (work / "result.json").write_text(json.dumps(
        {"claim": claim, "timed_out": timed_out, "trace": trace, "seconds": round(time.time() - t0, 3)}))


if __name__ == "__main__":
    main(sys.argv[1])
