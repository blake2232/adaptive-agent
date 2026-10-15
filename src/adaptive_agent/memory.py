"""Letta/MemGPT-style memory: editable core blocks + searchable archival memory (SQLite)."""
import json, sqlite3, time
from .embed import embed, score


class MemoryStore:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS memories(
                 id INTEGER PRIMARY KEY, kind TEXT, content TEXT, created REAL, vec TEXT);
               CREATE TABLE IF NOT EXISTS core(key TEXT PRIMARY KEY, value TEXT);"""
        )
        self.db.commit()

    # --- archival memory ---
    def add(self, content, kind="note"):
        cur = self.db.execute(
            "INSERT INTO memories(kind,content,created,vec) VALUES(?,?,?,?)",
            (kind, content, time.time(), json.dumps(embed(content))),
        )
        self.db.commit()
        return cur.lastrowid

    def edit(self, mem_id, content):
        cur = self.db.execute("UPDATE memories SET content=?, vec=? WHERE id=?",
                              (content, json.dumps(embed(content)), mem_id))
        self.db.commit()
        return cur.rowcount == 1

    def delete(self, mem_id):
        cur = self.db.execute("DELETE FROM memories WHERE id=?", (mem_id,))
        self.db.commit()
        return cur.rowcount == 1

    def get(self, mem_id):
        r = self.db.execute("SELECT id,kind,content FROM memories WHERE id=?", (mem_id,)).fetchone()
        return dict(id=r[0], kind=r[1], content=r[2]) if r else None

    def list(self, kind=None, limit=50):
        q, args = "SELECT id,kind,content FROM memories", ()
        if kind:
            q, args = q + " WHERE kind=?", (kind,)
        rows = self.db.execute(q + " ORDER BY id DESC LIMIT ?", args + (limit,)).fetchall()
        return [dict(id=a, kind=b, content=c) for a, b, c in rows]

    def search(self, query, k=5, kind=None, min_score=0.05):
        qv = embed(query)
        q, args = "SELECT id,kind,content,vec FROM memories", ()
        if kind:
            q, args = q + " WHERE kind=?", (kind,)
        hits = []
        for i, kd, c, v in self.db.execute(q, args):
            s = score(query, c, qv, json.loads(v))
            if s >= min_score:
                hits.append(dict(id=i, kind=kd, content=c, score=round(s, 3)))
        return sorted(hits, key=lambda h: -h["score"])[:k]

    # --- core memory (always in context, editable) ---
    def core_set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO core VALUES(?,?)", (key, value))
        self.db.commit()

    def core_get(self):
        return dict(self.db.execute("SELECT key,value FROM core").fetchall())
