"""Metrics and reporting: reads results.db, computes pass rate, pass@k,
false-claim rate, side-effect rate, mean steps, per-difficulty breakdown.
Also computes verifier precision/recall using QA mutant data."""
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_results(db_path=ROOT / "results.db", run_id=None):
    if not Path(db_path).exists():
        return []
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    if run_id:
        rows = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchall()
    else:
        # latest run
        row = db.execute("SELECT run_id FROM runs ORDER BY ts DESC LIMIT 1").fetchone()
        if not row:
            return []
        rows = db.execute("SELECT * FROM runs WHERE run_id=?", (row[0],)).fetchall()
    db.close()
    return [dict(r) for r in rows]


def _load_tasks():
    from agentproof.runner.run import load_tasks
    return {t["id"]: t for t in load_tasks()}


def pass_at_k(results_by_agent_task):
    """Compute pass@k: probability at least one of k attempts passes."""
    out = {}
    for (agent, task), attempts in results_by_agent_task.items():
        n = len(attempts)
        c = sum(1 for a in attempts if a["passed"])
        if n == 1:
            out[(agent, task)] = float(c)
        else:
            # Unbiased estimator: 1 - C(n-c, k) / C(n, k) for k=n
            if c == 0:
                out[(agent, task)] = 0.0
            elif c == n:
                out[(agent, task)] = 1.0
            else:
                # pass@1 from multiple samples: mean of individual passes
                out[(agent, task)] = c / n
    return out


def compute_metrics(rows, tasks):
    agents = sorted({r["agent"] for r in rows})
    metrics = {}

    for agent in agents:
        agent_rows = [r for r in rows if r["agent"] == agent]
        by_task = defaultdict(list)
        for r in agent_rows:
            by_task[(agent, r["task"])].append(r)

        n = len(agent_rows)
        n_pass = sum(r["passed"] for r in agent_rows)
        n_false_claim = sum(r["false_claim"] for r in agent_rows)
        n_side_effect = sum(1 for r in agent_rows if r["category"] == "side_effect")
        mean_steps = sum(r["steps"] for r in agent_rows) / n if n else 0

        # pass@k
        pak = pass_at_k(by_task)
        mean_pak = sum(pak.values()) / len(pak) if pak else 0

        # per-difficulty breakdown
        diff_stats = defaultdict(lambda: {"n": 0, "pass": 0})
        for r in agent_rows:
            t = tasks.get(r["task"], {})
            diff = t.get("difficulty", "unknown")
            diff_stats[diff]["n"] += 1
            diff_stats[diff]["pass"] += r["passed"]

        # failure categories
        cats = defaultdict(int)
        for r in agent_rows:
            cats[r["category"]] += 1

        metrics[agent] = {
            "n": n,
            "pass_rate": n_pass / n if n else 0,
            "pass_n": n_pass,
            "false_claim_rate": n_false_claim / n if n else 0,
            "false_claim_n": n_false_claim,
            "side_effect_rate": n_side_effect / n if n else 0,
            "mean_steps": round(mean_steps, 2),
            "mean_pass_at_k": round(mean_pak, 3),
            "per_difficulty": {d: {"pass": s["pass"], "n": s["n"],
                                   "rate": round(s["pass"] / s["n"], 2) if s["n"] else 0}
                               for d, s in sorted(diff_stats.items())},
            "failure_categories": dict(cats),
        }
    return metrics


def verifier_precision_recall():
    """Use QA mutant data as labelled wrong states.
    Precision = killed / (killed + equivalent); Recall = killed / mutants."""
    from agentproof.qa.qa import run_qa
    reps = run_qa()
    total_mutants = sum(r["mutants"] for r in reps)
    total_killed = sum(r["killed"] for r in reps)
    total_equiv = sum(r["equivalent"] for r in reps)
    # Only non-equivalent mutants are true positives for detection
    precision = total_killed / (total_killed + total_equiv) if (total_killed + total_equiv) else 0
    recall = total_killed / total_mutants if total_mutants else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0
    return {
        "total_mutants": total_mutants,
        "killed": total_killed,
        "equivalent": total_equiv,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def _bar(rate, width=20):
    filled = round(rate * width)
    return "#" * filled + "." * (width - filled)


def print_report(run_id=None, db_path=ROOT / "results.db", include_verifier=False):
    rows = _load_results(db_path, run_id)
    if not rows:
        print("No results found. Run `agentproof run` first.")
        return

    rid = rows[0]["run_id"]
    tasks = _load_tasks()
    metrics = compute_metrics(rows, tasks)

    print(f"\n{'='*70}")
    print(f"  AgentProof Report  run {rid}")
    print(f"{'='*70}\n")

    # Summary table
    print(f"{'Agent':<12} {'Pass%':>6} {'Pass@k':>7} {'FalseClaim%':>12} {'SideEff%':>9} {'Steps':>6}")
    print(f"{'─'*12} {'─'*6} {'─'*7} {'─'*12} {'─'*9} {'─'*6}".replace('─', '-'))
    for agent, m in metrics.items():
        print(f"{agent:<12} {m['pass_rate']*100:>5.1f}% {m['mean_pass_at_k']:>7.3f} "
              f"{m['false_claim_rate']*100:>11.1f}% {m['side_effect_rate']*100:>8.1f}% "
              f"{m['mean_steps']:>6.1f}")

    # Per-agent detail
    for agent, m in metrics.items():
        print(f"\n  -- {agent} ({m['pass_n']}/{m['n']} pass) --")
        print(f"  Pass rate:   {_bar(m['pass_rate'])} {m['pass_rate']*100:.1f}%")
        print(f"  False claim: {_bar(m['false_claim_rate'])} {m['false_claim_rate']*100:.1f}%")
        print(f"  Side effect: {_bar(m['side_effect_rate'])} {m['side_effect_rate']*100:.1f}%")
        print(f"  Categories:  {m['failure_categories']}")
        if m["per_difficulty"]:
            diff_parts = [f"{d}:{s['pass']}/{s['n']}" for d, s in m["per_difficulty"].items()]
            print(f"  By difficulty: {', '.join(diff_parts)}")

    # Verifier metrics
    if include_verifier:
        print(f"\n{'-'*70}")
        print("  Verifier Quality (mutant analysis via QA suite)")
        v = verifier_precision_recall()
        print(f"  Mutants: {v['total_mutants']}  Killed: {v['killed']}  "
              f"Equivalent: {v['equivalent']}")
        print(f"  Precision: {v['precision']:.3f}  Recall: {v['recall']:.3f}  F1: {v['f1']:.3f}")

    print(f"\n{'='*70}\n")

    # JSON output
    return {"run_id": rid, "agents": metrics}


def write_json_report(run_id=None, db_path=ROOT / "results.db", out_path=None):
    rows = _load_results(db_path, run_id)
    if not rows:
        return None
    rid = rows[0]["run_id"]
    tasks = _load_tasks()
    metrics = compute_metrics(rows, tasks)
    payload = json.dumps({"run_id": rid, "agents": metrics}, indent=2)
    if out_path:
        Path(out_path).write_text(payload)
        print(f"JSON report written to {out_path}")
    return payload
