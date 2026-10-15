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

    rep = sub.add_parser("report", help="print metrics for the latest (or specified) run")
    rep.add_argument("run_id", nargs="?", default=None, help="run ID (default: latest)")
    rep.add_argument("--json", metavar="FILE", default=None, help="write JSON report to FILE")
    rep.add_argument("--verifier", action="store_true",
                     help="include verifier precision/recall from QA mutants (slow)")

    a = p.parse_args()

    if a.cmd == "qa":
        from agentproof.qa.qa import print_report, run_qa
        sys.exit(0 if print_report(run_qa()) else 1)

    if a.cmd == "report":
        from agentproof.runner.report import print_report, write_json_report
        print_report(run_id=a.run_id, include_verifier=a.verifier)
        if a.json:
            write_json_report(run_id=a.run_id, out_path=a.json)
        return

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
