"""LLM backends: OpenAI-compatible HTTP client and a deterministic offline mock."""
import json, os, re, urllib.request


class LLM:
    name = "base"

    def complete(self, messages):  # messages: list of {"role","content"}
        raise NotImplementedError


class OpenAICompatLLM(LLM):
    name = "openai"

    def __init__(self, api_key=None, base_url=None, model=None, temperature=0.2):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.environ.get("MODEL") or "gpt-4o-mini"
        self.temperature = temperature
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

    def complete(self, messages):
        body = json.dumps({"model": self.model, "messages": messages, "temperature": self.temperature}).encode()
        req = urllib.request.Request(self.base_url + "/chat/completions", data=body, headers={"User-Agent": "adaptive-agent/0.1",
            "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]


class MockLLM(LLM):
    """Deterministic rule-based stand-in. Understands a few task shapes so the full
    loop (skill creation, reuse, failure, reflexion retry) can be tested offline.
    "multiply" is deliberately buggy on a first attempt with no failure feedback."""
    name = "mock"

    def __init__(self):
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        prompt = messages[-1]["content"]
        if "MODE: critique" in prompt:
            return self._critique(prompt)
        return self._solve(prompt)

    def _critique(self, p):
        ok = "ERROR: None" in p and "RESULT: None" not in p
        if ok:
            return json.dumps({"success": True, "lesson": "Approach worked; reuse the saved skill for similar tasks."})
        err = re.search(r"ERROR: (.*)", p).group(1)
        return json.dumps({"success": False, "lesson": f"Attempt failed with {err}; check edge cases and operators before returning."})

    def _solve(self, p):
        task = re.search(r"TASK: (.*)", p).group(1)
        have = set(re.findall(r"^- (\w+)\(", p, re.M))
        retry = "PREVIOUS FAILED ATTEMPTS" in p

        def out(name, desc, fn_code, call):
            if name in have:
                return json.dumps({"thought": f"reuse skill {name}", "code": f"def solve():\n    return {call}\n", "uses_skills": [name]})
            return json.dumps({"thought": f"write new skill {name}", "skill_name": name, "skill_description": desc,
                               "skill_code": fn_code, "code": f"def solve():\n    return {call}\n", "uses_skills": [name]})

        if m := re.search(r"add (-?\d+) and (-?\d+)", task):
            return out("add_numbers", "Add two numbers and return the sum.",
                       "def add_numbers(a, b):\n    return a + b\n", f"add_numbers({m[1]}, {m[2]})")
        if m := re.search(r"multiply (-?\d+) and (-?\d+)", task):
            if "multiply_numbers" not in have and not retry:  # buggy first draft
                return json.dumps({"thought": "quick attempt", "code": f"def solve():\n    return {m[1]} * {m[2]} / 0\n"})
            return out("multiply_numbers", "Multiply two numbers and return the product.",
                       "def multiply_numbers(a, b):\n    return a * b\n", f"multiply_numbers({m[1]}, {m[2]})")
        if m := re.search(r"reverse (?:the string )?'(.*)'", task):
            return out("reverse_string", "Reverse a string.", "def reverse_string(s):\n    return s[::-1]\n",
                       f"reverse_string({m[1]!r})")
        if m := re.search(r"count words in file (\S+)", task):
            return out("count_words_in_file", "Count whitespace-separated words in a file using tools.read_file.",
                       "def count_words_in_file(tools, path):\n    return len(tools.read_file(path).split())\n",
                       f"count_words_in_file(tools, {m[1]!r})")
        if m := re.search(r"remember that (.*)", task):
            return json.dumps({"thought": "store fact", "code": f"def solve():\n    memory.add({m[1]!r}, kind='fact')\n    return 'stored'\n"})
        return json.dumps({"thought": "unknown task", "code": "def solve():\n    raise NotImplementedError('mock cannot solve this')\n"})


def get_backend(name=None):
    name = name or ("openai" if os.environ.get("OPENAI_API_KEY") else "mock")
    if name == "mock":
        return MockLLM()
    if name == "openai":
        return OpenAICompatLLM()
    raise ValueError(f"unknown backend {name}")


def parse_json(text):
    """Extract the first JSON object from model output (tolerates ```json fences / prose)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(cand)
