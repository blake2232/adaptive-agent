"""Voyager-style skill library: named Python functions with descriptions, retrieved by relevance."""
import json, sqlite3, time
from .embed import embed, score


class SkillLibrary:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS skills(
                 name TEXT PRIMARY KEY, description TEXT, code TEXT,
                 uses INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, created REAL, vec TEXT)"""
        )
        self.db.commit()

    @staticmethod
    def validate(name, code):
        ns = {}
        exec(compile(code, f"<skill {name}>", "exec"), ns)
        if not callable(ns.get(name)):
            raise ValueError(f"skill code must define a function named {name!r}")

    def save(self, name, description, code):
        if not name.isidentifier():
            raise ValueError(f"invalid skill name {name!r}")
        self.validate(name, code)
        self.db.execute(
            """INSERT INTO skills(name,description,code,created,vec) VALUES(?,?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET description=excluded.description,
               code=excluded.code, vec=excluded.vec""",
            (name, description, code, time.time(), json.dumps(embed(name.replace("_", " ") + " " + description))),
        )
        self.db.commit()

    def get(self, name):
        r = self.db.execute("SELECT name,description,code,uses,successes FROM skills WHERE name=?", (name,)).fetchone()
        return dict(zip(("name", "description", "code", "uses", "successes"), r)) if r else None

    def list(self):
        rows = self.db.execute("SELECT name,description,uses,successes FROM skills ORDER BY name").fetchall()
        return [dict(zip(("name", "description", "uses", "successes"), r)) for r in rows]

    def search(self, query, k=3, min_score=0.1):
        qv = embed(query)
        hits = []
        for n, d, c, v in self.db.execute("SELECT name,description,code,vec FROM skills"):
            s = score(query, n.replace("_", " ") + " " + d, qv, json.loads(v))
            if s >= min_score:
                hits.append(dict(name=n, description=d, code=c, score=round(s, 3)))
        return sorted(hits, key=lambda h: -h["score"])[:k]

    def record_use(self, name, success):
        self.db.execute("UPDATE skills SET uses=uses+1, successes=successes+? WHERE name=?", (int(success), name))
        self.db.commit()

    def load_functions(self, names):
        ns = {}
        for n in names:
            s = self.get(n)
            if s:
                exec(compile(s["code"], f"<skill {n}>", "exec"), ns)
        return {n: ns[n] for n in names if n in ns}
