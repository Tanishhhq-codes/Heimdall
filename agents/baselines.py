"""Baseline agents. Interface: agent.run(task_view, call) -> 'success' | 'fail'."""
import re


class Oracle:
    """Replays the task's scripted solution. Proves tasks are solvable and verifiers accept it."""
    name = "oracle"

    def __init__(self, task):
        self.solution = task["solution"]

    def run(self, view, call):
        for step in self.solution:
            call(step["tool"], **step["args"])
        return "success"


class Liar:
    """Takes no action, claims success. Proves the verifier ignores claims."""
    name = "liar"

    def __init__(self, task):
        pass

    def run(self, view, call):
        return "success"


class RuleBased:
    """Keyword -> action. No AI. Naive: has no concept of policy, so it falls for the trap task."""
    name = "rules"

    def __init__(self, task):
        pass

    def run(self, view, call):
        t = call("get_ticket", ticket_id=view["ticket_id"])
        text, who = t["text"].lower(), t["requester"]
        m = re.search(r"add (\w+) to ([\w-]+)", text)
        if m:
            call("add_to_group", user_id=m.group(1), group=m.group(2))
        elif "locked" in text:
            call("unlock_account", user_id=who)
        elif "password" in text:
            call("reset_password", user_id=who)
        else:
            call("escalate", ticket_id=view["ticket_id"], reason="unrecognized request")
            return "success"
        call("close_ticket", ticket_id=view["ticket_id"])
        return "success"


class Escalator:
    """Escalates everything. Catches benchmarks that reward over-refusal."""
    name = "escalator"

    def __init__(self, task):
        pass

    def run(self, view, call):
        call("escalate", ticket_id=view["ticket_id"], reason="always escalate")
        return "success"


AGENTS = {"oracle": Oracle, "liar": Liar, "rules": RuleBased, "escalator": Escalator}
