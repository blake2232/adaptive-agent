"""The agent loop: retrieve memory+skills -> generate code -> execute -> self-critique -> retry/save."""
import contextlib, io, json, traceback
from dataclasses import dataclass, field
from .llm import parse_json

SYSTEM = """You are a self-improving coding agent. Solve the task by writing Python.
Reply with ONE JSON object:
{"thought": str, "code": "def solve(): ... return answer",
 "uses_skills": [names of existing skills you call],
 "skill_name": optional new reusable function name, "skill_description": str, "skill_code": "def <skill_name>(...): ..."}
Inside code you may use: `tools` (read_file, write_file, shell, web_fetch), `memory` (add, search, edit),
and any listed skill function by name. solve() must return the final answer."""


@dataclass
class Attempt:
    code: str
    result: object
    error: str
    success: bool
    lesson: str


@dataclass
class RunResult:
    task: str
    success: bool
    result: object
    attempts: list = field(default_factory=list)
    new_skill: str = None


class Agent:
    def __init__(self, llm, memory, skills, tools, max_retries=3, log=None):
        self.llm, self.memory, self.skills, self.tools = llm, memory, skills, tools
        self.max_retries, self.log = max_retries, log or (lambda s: None)

    def _prompt(self, task, mems, sks, failures):
        parts = [f"TASK: {task}", "", "## Core memory", json.dumps(self.memory.core_get()), "", "## Relevant memories"]
        parts += [f"* [{m['kind']}] {m['content']}" for m in mems] or ["(none)"]
        parts += ["", "## Skills available"]
        parts += [f"- {s['name']}(...): {s['description']}\n{s['code']}" for s in sks] or ["(none)"]
        if failures:
            parts += ["", "## PREVIOUS FAILED ATTEMPTS"]
            parts += [f"code:\n{a.code}\nerror: {a.error}\nlesson: {a.lesson}" for a in failures]
        parts += ["", "MODE: solve"]
        return "\n".join(parts)

    def _execute(self, plan):
        ns = {"tools": self.tools, "memory": self.memory, "__name__": "agent_task"}
        ns.update(self.skills.load_functions(plan.get("uses_skills") or []))
        if plan.get("skill_code"):
            exec(compile(plan["skill_code"], "<new skill>", "exec"), ns)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(plan["code"], "<task code>", "exec"), ns)
            return ns["solve"]()

    def _critique(self, task, code, result, error):
        p = (f"TASK: {task}\nCODE:\n{code}\nRESULT: {result!r}\nERROR: {error}\n"
             'Did this correctly solve the task? Reply JSON {"success": bool, "lesson": str} '
             "where lesson is a short reusable insight.\nMODE: critique")
        try:
            c = parse_json(self.llm.complete([{"role": "user", "content": p}]))
            return bool(c.get("success")), str(c.get("lesson", ""))
        except Exception as e:  # unparseable critique counts as failure
            return False, f"critique unparseable: {e}"

    def run(self, task):
        mems = self.memory.search(task, k=5)
        sks = self.skills.search(task, k=3)
        self.log(f"retrieved {len(mems)} memories, skills: {[s['name'] for s in sks] or 'none'}")
        attempts = []
        for i in range(1, self.max_retries + 1):
            prompt = self._prompt(task, mems, sks, [a for a in attempts if not a.success])
            raw = self.llm.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
            result, error, plan = None, None, {}
            try:
                plan = parse_json(raw)
                self.log(f"attempt {i}: {plan.get('thought', '')}")
                result = self._execute(plan)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                self.log(f"attempt {i} error: {error}")
            code = plan.get("code", raw)
            ok, lesson = self._critique(task, code, result, error)
            if error and ok:
                ok = False  # never trust a "success" verdict on a crashed run
            attempts.append(Attempt(code, result, error, ok, lesson))
            self.memory.add(f"Task: {task} | {'SUCCESS' if ok else 'FAILURE'} | Lesson: {lesson}", kind="lesson")
            for n in plan.get("uses_skills") or []:
                if self.skills.get(n):
                    self.skills.record_use(n, ok)
            self.log(f"attempt {i} critique: success={ok} lesson={lesson}")
            if ok:
                new = None
                if plan.get("skill_name") and plan.get("skill_code"):
                    try:
                        self.skills.save(plan["skill_name"], plan.get("skill_description", ""), plan["skill_code"])
                        self.skills.record_use(plan["skill_name"], True)
                        new = plan["skill_name"]
                        self.log(f"saved new skill: {new}")
                    except Exception as e:
                        self.log(f"skill not saved: {e}")
                self.memory.add(f"Task: {task} -> {result!r}", kind="episode")
                return RunResult(task, True, result, attempts, new)
        return RunResult(task, False, None, attempts)
