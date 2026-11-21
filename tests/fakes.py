"""Tiny in-memory stand-in for Supabase so the matcher can be tested offline."""
import math
import uuid
from collections import defaultdict


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload, self.filters = "select", None, []

    def select(self, *a, **k): self.op = "select"; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, vals): self.op, self.payload = "update", vals; return self
    def eq(self, col, val): self.filters.append(lambda r: r.get(col) == val); return self
    def in_(self, col, vals): self.filters.append(lambda r: r.get(col) in vals); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self

    def execute(self):
        rows = self.db.tables[self.name]
        if self.op == "insert":
            row = {**self.payload, "id": str(uuid.uuid4())}
            rows.append(row)
            return Result([row])
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
        return Result(hit)


class Rpc:
    def __init__(self, data): self._data = data
    def execute(self): return Result(self._data)


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class FakeDB:
    def __init__(self):
        self.tables = defaultdict(list)

    def table(self, name): return Query(self, name)

    def rpc(self, name, p):
        assert name == "match_items"
        out = []
        for r in self.tables["items"]:
            if r["status"] != "searching" or r["intent"] != p["match_intent"]:
                continue
            sim = cosine(r["embedding"], p["query_embedding"])
            if sim >= p["match_threshold"]:
                out.append({**{k: r[k] for k in ("id", "item_name", "category", "summary", "sender_email")},
                            "similarity": sim})
        out.sort(key=lambda x: -x["similarity"])
        return Rpc(out[: p["max_results"]])
