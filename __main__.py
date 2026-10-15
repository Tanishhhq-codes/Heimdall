import argparse
import sys

from agentproof.agents.baselines import AGENTS
from agentproof.runner.run import run_all, save, summarize


def main():
    p = argparse.ArgumentParser(prog="agentproof")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--agents", default=",".join(AGENTS))
    r.add_argument("-k", type=int, default=1, help="attempts per task (pass@k style)")
    r.add_argument("-j", type=int, default=1, help="parallel workers")
    r.add_argument("--docker", action="store_true", help="run each task in an isolated container")
    r.add_argument("-v", action="store_true", help="per-task results")
    sub.add_parser("qa", help="test the benchmark itself (tasks + verifier)")
    a = p.parse_args()

    if a.cmd == "qa":
        from agentproof.qa.qa import print_report, run_qa
        sys.exit(0 if print_report(run_qa()) else 1)

    results = run_all(a.agents.split(","), a.k, a.docker, a.j)
    run_id = save(results)
    if a.v:
        for x in results:
            print(f"{x['agent']:9} {x['task']:26} {x['category']:12} false_claim={x['false_claim']}")
    print(f"\nrun {run_id}  ({'docker' if a.docker else 'in-process'})")
    print(f"{'agent':9} {'pass':>6} {'false-claim':>12}  failure categories")
    for ag, s in summarize(results).items():
        cats = {c: n for c, n in s["cats"].items() if c != "pass"}
        print(f"{ag:9} {s['pass']}/{s['n']:<4} {s['false_claim']}/{s['n']:<10}  {cats}")


if __name__ == "__main__":
    main()
