# AgentProof: Project Plan

A miniature benchmark-development and evaluation system for AI agents, aimed at Ressl AI's work (Harbor-style Docker tasks, hidden verifiers, ITSMBench-style IT ticket resolution).

**One-line pitch:** AgentProof gives an agent a simulated IT-support system, records what it does, and independently verifies the final state, so "I'm done" is never taken at face value. It also tests its own benchmark for broken tasks and verifiers.

**Stack (all free):** Python 3.12, SQLite, Docker, FastAPI, Next.js (or HTMX if short on time), pytest, Ollama (local model), GitHub Actions.

---

## 1. Architecture

```
Task YAML (seed, solution, checks)
   -> runner: fresh environment per run (in-process or Docker, no network)
   -> agent acts through tools (get_ticket, unlock_account, reset_password,
      add_to_group, comment, close_ticket, escalate); every call traced + audit-logged
   -> hidden verifier (host side, never inside the container) reads the final DB
   -> result: pass/fail, failure category, false-claim flag, per-check detail
   -> results DB -> CLI report / dashboard
Benchmark QA runs on tasks + verifier, separate from agent runs.
```

Key design rules:
- The container receives the task with `checks` stripped; the verifier runs outside it.
- The verifier never trusts the agent's claim. It reads state and the audit log.
- Default-deny on side effects: any state change not explained by an outcome check fails.
- Failure categories: `wrong_action`, `missed_step`, `side_effect`, `timeout`; plus a separate `false_claim` flag.

## 2. Status

| Area | State |
|---|---|
| Mock ITSM (SQLite, 8 tools, audit log) | Done |
| Task format + 8 tasks (easy, medium, traps, over-refusal counterpart) | Done |
| Verifier (outcome checks, side-effect checks, default-deny state diff, failure taxonomy) | Done |
| Baseline agents: oracle, liar, rules, escalator | Done |
| In-process runner, parallel workers, results DB, CLI (`run`, `qa`) | Done |
| Docker runner (no network, read-only, memory/pid limits, verifier on host) | Written; **not yet run on a real Docker daemon** (registry was blocked in the build sandbox) |
| Benchmark QA suite (mutants, alt-valid solutions, perturbations, determinism) + pytest | Done; 8/8 tasks pass |
| Dashboard | Not started |
| Ollama agent | Not started |
| Tasks 9-20 | Not started |
| README, methodology, demo, write-up | Not started |

Current baseline results (8 tasks): oracle 8/8, liar 0/8, rules 4/8, escalator 2/8.

## 3. Remaining work, in order

### Step A: Prove Docker mode works (30 min, on your machine)
1. `docker build -t agentproof-env -f agentproof/env/Dockerfile .`
2. `python3 -m agentproof run --docker -j 4` and confirm results match in-process.
3. Add one test that runs a single task through Docker and compares verdicts (skip automatically if Docker is absent).
4. Add a wall-clock timeout test: an agent that loops forever must produce `timeout`.

### Step B: Grow the task bank to ~20 (Day 1-2)
Design each task with a trap or edge case, then give it an oracle solution and checks. Run `agentproof qa` after every few tasks.

Ideas to cover:
- **Policy:** approver-only groups (done), expired-account requests, requests from a non-owner for someone else's account, two tickets referencing the same user.
- **Injection:** instruction hidden in ticket text (done), injection in a comment or user name field, fake "admin approved" claims in ticket text.
- **Missing or ambiguous data:** non-existent user (done), two users with similar names, nonexistent group, ticket already closed.
- **Multi-step:** unlock + group + close (done), reset + comment + close, escalate with a required reason.
- **Over-refusal pairs:** for every trap, a near-identical legitimate version (t03/t08 pattern).
- **Difficulty labels:** easy / medium / hard / trap, so results can be broken down by difficulty.

Add a small task generator (Python, seeded randomness) that produces variants of a template with different names and IDs. This mirrors Ressl's "data generation" work and gives pass@k something to measure.

### Step C: Metrics and reporting (Day 3)
- pass rate, pass@k, false-claim rate, side-effect rate, mean steps, per-difficulty breakdown.
- Precision/recall for the verifier itself, using the QA mutants as labelled bad states.
- `agentproof report <run_id>` printing markdown and writing JSON.

### Step D: Dashboard (Day 4-5)
FastAPI backend reading `results.db`; frontend in Next.js (HTMX is fine if time is short). Don't polish before the data is real.
- **Runs page:** list of runs, agent, pass rate, false-claim rate, timestamp.
- **Run detail:** per-task table with category badges and filters (failed only, by category).
- **Trace viewer:** ordered tool calls with arguments and results, plus the checks that failed and why.
- **Compare view:** two agents or two runs side by side, per-task diff.
- **Launch button:** starts a run via the CLI as a background job.
- **QA page:** latest QA report (survivors, alt-valid failures).

### Step E: Ollama agent (Day 6-7)
- Agent loop: system prompt with tool schemas, parse tool calls from the model, execute, feed results back, stop on a final message or the step limit.
- Models: Qwen2.5 7B or Llama 3.1 8B if you have 8 GB+ RAM; 3-4B models on CPU-only machines.
- The model must never see checks, solutions, or other tasks. Same view as the rules agent.
- Handle malformed tool calls as a recorded failure, not a crash.
- Run with `-k 3` to measure reliability. Small models will fail a lot; that is expected and useful data.
- Optional: an adapter exposing the ITSM as an MCP server so other agent harnesses can be evaluated.

### Step F: Harbor compatibility (Day 7, optional but valuable)
- Read Harbor's task format and add an exporter that writes each task as a Harbor-style directory (environment Dockerfile, instruction, verifier script).
- Goal: show the benchmark can run in Ressl's tooling, not just your own runner.

### Step G: CI (Day 8)
GitHub Actions: install, run `pytest`, run `agentproof qa`, run the baseline agents and assert oracle = 100% and liar = 0%. Free for public repos.

### Step H: Polish and ship (Day 9-10)
- **README:** what it is, quickstart, architecture diagram, results table, limitations.
- **docs/METHODOLOGY.md:** task design rules, verifier design, failure taxonomy, QA methodology, how the benchmark avoids rewarding over-refusal.
- **Demo GIF:** `run`, `qa`, then dashboard trace of a caught false claim.
- **Short write-up (1 page):** the bugs QA found in the verifier (for example, the unrequested password reset that originally passed) and how they were fixed.
- Freeze features at Day 9. Day 10 is polish only.

## 4. Rules to protect scope
- Do not build: browser or desktop agents, auth, multi-tenancy, cloud deploy, remote sweeps (Daytona-style is future work).
- Do not add LangChain, LangGraph, or vector databases.
- The oracle must pass 100% before any agent score is trusted.
- Every new task must pass `agentproof qa` before it is counted.
- Test the verifier with deliberately wrong end states, not just wrong agents.

## 5. What makes it stand out
1. **Benchmark QA:** it tests its own tasks and verifier, and has a real bug-found-and-fixed story.
2. **False-claim rate** as the headline metric.
3. **Trap tasks with over-refusal counterparts**, so refusing everything scores poorly.
4. **Side-effect detection** by default-deny state diff, not just "ticket closed".
5. **pass@k** to separate reliability from luck.

Be honest about overlap: New Measure already does simulated business environments. Differentiate on the QA layer, the task design, and the analysis, not on the concept.

## 6. Ressl application checklist
- Public GitHub repo with a clear README and a demo GIF.
- One-page write-up of what QA caught.
- A short email to Ressl linking the repo and naming the three most relevant pieces: hidden verifier, benchmark QA, trap tasks.
- Be ready to explain every design choice; the take-home (2-3 hours) and interview will probe it.

## 7. Study list (only what you need)
- **Harbor:** task format and environment lifecycle.
- **Inspect AI:** scorers and log viewer.
- **New Measure's SalesforceBench write-up:** how they seed state and verify outcomes.
- **Ressl's ITSMBench job description:** the target domain.

## 8. Files
```
agentproof/
  env/          itsm.py, session.py, Dockerfile
  tasks/        t01..t08 YAML (growing to ~20)
  verifiers/    verify.py
  agents/       baselines.py (+ ollama.py to come)
  runner/       run.py, container.py
  qa/           qa.py
  tests/        test_qa.py
  dashboard/    (to come)
  docs/         METHODOLOGY.md (to come)
```

Run from the folder containing `agentproof/`:
```
python3 -m agentproof run -v
python3 -m agentproof qa
python3 -m pytest agentproof/tests
python3 -m agentproof run --docker -j 4
```
