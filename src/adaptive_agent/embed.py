"""Dependency-free hashed bag-of-words embedding + cosine similarity."""
import hashlib, math, re

DIM = 256
_TOKEN = re.compile(r"[a-z0-9_]+")
STOP = {"the", "a", "an", "and", "of", "to", "in", "is", "it", "for", "on", "with"}


def tokens(text):
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


def embed(text):
    v = [0.0] * DIM
    for t in tokens(text):
        h = int(hashlib.md5(t.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def score(query, text, qvec, tvec):
    """Blend of embedding cosine and keyword overlap (Jaccard)."""
    q, t = set(tokens(query)), set(tokens(text))
    jac = len(q & t) / len(q | t) if q | t else 0.0
    return 0.5 * cosine(qvec, tvec) + 0.5 * jac
