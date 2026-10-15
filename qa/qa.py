"""Benchmark QA: tests the *benchmark* (tasks + verifier), not the agents.

1. solvable      - oracle solution passes
2. deterministic - repeated oracle runs give identical verdicts
3. mutants       - wrong end states must FAIL. A "survivor" is a mutant whose final state
                   differs from the oracle's yet the verifier still passes it (verifier gap).
4. alt_valid     - reordered / commented-but-correct solutions must PASS (no unfair penalty)
5. perturbation  - reordered seed lists and an extra distractor user must not change the verdict
"""
import copy
import itertools

from agentproof.env.itsm import ITSM
from agentproof.runner.run import load_tasks
from agentproof.verifiers.verify import verify


def fingerprint(env):
    q = lambda s: [tuple(r) for r in env.db.execute(s)]
    return (q("SELECT id,locked,password_resets FROM users ORDER BY id"),
            q("SELECT user_id,group_name FROM memberships ORDER BY 1,2"),
            q("SELECT id,status,escalated FROM tickets ORDER BY id"))


def judge(task, steps, seed=None):
    env = ITSM()
    env.seed(seed or task["seed"])
    for s in steps:
        env.call(s["tool"], **s["args"])
    return verify(env, {**task, "seed": seed or task["seed"]}, "success"), fingerprint(env)


def _step(tool, **args):
    return {"tool": tool, "args": args}


def mutants(task):
    sol, seed = task["solution"], task["seed"]
    users = [u["id"] for u in seed.get("users", [])]
    groups = [g["name"] for g in seed.get("groups", [])]
    tickets = [t["id"] for t in seed.get("tickets", [])]
    out = []
    for i, s in enumerate(sol):                                   # skip one step
        out.append((f"skip:{s['tool']}", sol[:i] + sol[i + 1:]))
    for i, s in enumerate(sol):                                   # right action, wrong user
        if "user_id" in s["args"]:
            for u in users:
                if u != s["args"]["user_id"]:
                    a = {**s["args"], "user_id": u}
                    out.append((f"wrong_user:{s['tool']}->{u}", sol[:i] + [{**s, "args": a}] + sol[i + 1:]))
    extras = []                                                    # oracle + one extra action
    for u in users:
        extras += [_step("unlock_account", user_id=u), _step("reset_password", user_id=u)]
        extras += [_step("add_to_group", user_id=u, group=g) for g in groups]
    for t in tickets:
        extras += [_step("close_ticket", ticket_id=t), _step("escalate", ticket_id=t, reason="x")]
    for e in extras:
        if e not in sol:
            out.append((f"extra:{e['tool']}({','.join(map(str, e['args'].values()))})", sol + [e]))
    return out


def qa_task(task):
    base, base_fp = judge(task, task["solution"])
    rep = {"task": task["id"], "solvable": base["passed"], "deterministic": True,
           "mutants": 0, "equivalent": 0, "killed": 0, "survivors": [],
           "alt_valid_fail": [], "perturb_fail": []}
    for _ in range(4):
        v, fp = judge(task, task["solution"])
        if (v["passed"], fp) != (base["passed"], base_fp):
            rep["deterministic"] = False
    for name, steps in mutants(task):
        v, fp = judge(task, steps)
        if fp == base_fp:
            rep["equivalent"] += 1          # no state difference -> not a verifier gap
            continue
        rep["mutants"] += 1
        if v["passed"]:
            rep["survivors"].append(name)
        else:
            rep["killed"] += 1
    sol = task["solution"]
    alts = [(f"order{p}", [sol[i] for i in p]) for p in itertools.permutations(range(len(sol))) if len(sol) > 1]
    alts.append(("with_comment", [_step("comment", ticket_id=task["ticket"], body="working on it")] + sol))
    for name, steps in alts:
        if not judge(task, steps)[0]["passed"]:
            rep["alt_valid_fail"].append(name)
    seed = task["seed"]
    rev = {k: list(reversed(v)) for k, v in seed.items()}
    dist = copy.deepcopy(seed)
    dist.setdefault("users", []).append({"id": "zz_distractor"})
    for name, s in [("reversed_seed", rev), ("extra_distractor", dist)]:
        if not judge(task, sol, seed=s)[0]["passed"]:
            rep["perturb_fail"].append(name)
    rep["ok"] = (rep["solvable"] and rep["deterministic"] and not rep["survivors"]
                 and not rep["alt_valid_fail"] and not rep["perturb_fail"])
    return rep


def run_qa():
    return [qa_task(t) for t in load_tasks()]


def print_report(reps):
    print(f"{'task':26} {'solv':>4} {'det':>3} {'killed':>8} {'equiv':>5} {'altOK':>5} {'perturb':>7}  survivors")
    for r in reps:
        print(f"{r['task']:26} {'Y' if r['solvable'] else 'N':>4} {'Y' if r['deterministic'] else 'N':>3} "
              f"{r['killed']}/{r['mutants']:<5} {r['equivalent']:>5} "
              f"{'Y' if not r['alt_valid_fail'] else 'N':>5} {'Y' if not r['perturb_fail'] else 'N':>7}  "
              f"{r['survivors'] or ''}{('  ALT-FAIL ' + str(r['alt_valid_fail'])) if r['alt_valid_fail'] else ''}")
    bad = [r for r in reps if not r["ok"]]
    print(f"\n{len(reps) - len(bad)}/{len(reps)} tasks pass QA")
    return not bad
