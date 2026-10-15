# adaptive-agent

A small, dependency-free, self-improving agent that combines three published ideas:

| Idea | Source | Here |
|---|---|---|
| Long-term, self-editable memory | Letta / MemGPT | `memory.py`: SQLite *core memory* (key/value, always in the prompt) + *archival memory* (add / search / edit / delete). Agent code gets a `memory` handle. |
| Skill library | Voyager | `skills.py`: when a task succeeds and the model proposes a function, it is validated and saved with a description. Later tasks retrieve the top-k relevant skills and can call them. Use/success counts are tracked. |
| Self-critique + retry | Reflexion | `agent.py`: after each attempt an LLM critique judges success and writes a *lesson* to memory. On failure the next attempt sees the failed code, error and lesson; up to `--retries` attempts. |

Retrieval is a hashed bag-of-words embedding (256 dims) blended 50/50 with keyword Jaccard overlap. No vector DB or ML deps.

## Loop

```
task -> retrieve memories + skills -> LLM writes JSON {code, uses_skills, skill_*}
     -> exec solve() with tools/memory/skills -> LLM critique {success, lesson}
     -> lesson stored -> success? save skill + episode : retry with failure context
```

## Install & use

```bash
pip install -e '.[test]'
adaptive-agent run "add 2 and 3" --backend mock
adaptive-agent skills list
adaptive-agent skills show add_numbers
adaptive-agent memory search "add numbers"
adaptive-agent memory add "User prefers metric units" --kind fact
```

Backends: `--backend openai` uses any OpenAI-compatible `/chat/completions` endpoint configured by
`OPENAI_API_KEY`, `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) and `MODEL` (default `gpt-4o-mini`).
`--backend mock` is a deterministic rule-based backend (understands "add X and Y", "multiply X and Y",
"reverse 'text'", "count words in file F", "remember that ...") so the whole loop is testable offline.
Default: `openai` if `OPENAI_API_KEY` is set, otherwise `mock`. State lives in `$ADAPTIVE_AGENT_HOME` (default `~/.adaptive-agent`).

Tools available to agent code as `tools.*`: `read_file` / `write_file` (confined to the workdir),
`shell` (opt-in `--allow-shell`; timeout, scrubbed env, cwd=workdir), `web_fetch` (opt-in `--allow-web`; http(s) only, size capped).

## Honest limits

- **It does not make the model smarter.** The base model's reasoning is unchanged. Gains come from
  *repeated or similar tasks*: cached skills, recorded lessons, and retries that catch crashes.
- Novel one-off tasks get roughly base-model performance plus whatever retry-on-error buys you (at extra cost/latency).
- Self-critique is done by the same model; it can approve wrong answers or reject right ones. Only
  crashes are detected objectively. Add task-specific checks for anything important.
- Skills can be saved from tasks that *appeared* to succeed, so bad skills can accumulate. Inspect with
  `skills list/show`; usage/success counts help spot them.
- Retrieval is lexical-ish; paraphrases with no shared words retrieve poorly. Swap `embed.py` for a real embedding model if needed.
- **Generated code runs in-process via `exec`. This is not a security sandbox.** The shell "sandbox" is just
  a timeout + workdir + scrubbed env. Run it inside a container/VM if you use a real model with shell or web enabled.
- Memory grows unbounded; there is no summarisation/eviction yet.

## Tests

```bash
pytest -q   # fully offline, uses MockLLM
```

## License

MIT
