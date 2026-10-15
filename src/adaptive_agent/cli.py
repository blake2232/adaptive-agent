import argparse, os, sys
from pathlib import Path
from .agent import Agent
from .llm import get_backend
from .memory import MemoryStore
from .skills import SkillLibrary
from .tools import Tools


def _home(args):
    h = Path(args.home or os.environ.get("ADAPTIVE_AGENT_HOME") or Path.home() / ".adaptive-agent")
    h.mkdir(parents=True, exist_ok=True)
    return h


def main(argv=None):
    ap = argparse.ArgumentParser(prog="adaptive-agent")
    ap.add_argument("--home", help="state dir (default $ADAPTIVE_AGENT_HOME or ~/.adaptive-agent)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a task")
    r.add_argument("task")
    r.add_argument("--backend", choices=["mock", "openai"])
    r.add_argument("--retries", type=int, default=3)
    r.add_argument("--workdir", default=None)
    r.add_argument("--allow-shell", action="store_true")
    r.add_argument("--allow-web", action="store_true")
    r.add_argument("-q", "--quiet", action="store_true")
    s = sub.add_parser("skills").add_subparsers(dest="sub", required=True)
    s.add_parser("list")
    sh = s.add_parser("show"); sh.add_argument("name")
    m = sub.add_parser("memory").add_subparsers(dest="sub", required=True)
    ms = m.add_parser("search"); ms.add_argument("query"); ms.add_argument("-k", type=int, default=5)
    ma = m.add_parser("add"); ma.add_argument("text"); ma.add_argument("--kind", default="note")
    ml = m.add_parser("list"); ml.add_argument("--kind")
    me = m.add_parser("edit"); me.add_argument("id", type=int); me.add_argument("text")
    md = m.add_parser("delete"); md.add_argument("id", type=int)
    a = ap.parse_args(argv)

    home = _home(a)
    mem, lib = MemoryStore(str(home / "memory.db")), SkillLibrary(str(home / "skills.db"))
    if a.cmd == "run":
        tools = Tools(a.workdir or home / "workspace", allow_shell=a.allow_shell, allow_web=a.allow_web)
        llm = get_backend(a.backend)
        log = (lambda x: None) if a.quiet else (lambda x: print(f"[agent] {x}", file=sys.stderr))
        res = Agent(llm, mem, lib, tools, max_retries=a.retries, log=log).run(a.task)
        print(f"{'SUCCESS' if res.success else 'FAILED'} after {len(res.attempts)} attempt(s): {res.result!r}")
        return 0 if res.success else 1
    if a.cmd == "skills":
        if a.sub == "list":
            for k in lib.list() or []:
                print(f"{k['name']:<24} uses={k['uses']} ok={k['successes']}  {k['description']}")
            if not lib.list():
                print("(no skills yet)")
        else:
            k = lib.get(a.name)
            print(k["code"] if k else f"no skill {a.name}")
        return 0
    if a.sub == "search":
        for h in mem.search(a.query, k=a.k):
            print(f"#{h['id']} [{h['kind']}] ({h['score']}) {h['content']}")
    elif a.sub == "add":
        print(f"added #{mem.add(a.text, kind=a.kind)}")
    elif a.sub == "list":
        for h in mem.list(kind=a.kind):
            print(f"#{h['id']} [{h['kind']}] {h['content']}")
    elif a.sub == "edit":
        print("ok" if mem.edit(a.id, a.text) else "not found")
    elif a.sub == "delete":
        print("ok" if mem.delete(a.id) else "not found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
