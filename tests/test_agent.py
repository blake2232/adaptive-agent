import pytest
from adaptive_agent import Agent, MemoryStore, SkillLibrary, MockLLM
from adaptive_agent.tools import Tools, ToolError
from adaptive_agent.llm import parse_json
from adaptive_agent.cli import main


@pytest.fixture
def agent(tmp_path):
    return Agent(MockLLM(), MemoryStore(), SkillLibrary(), Tools(tmp_path), max_retries=3)


def test_memory_crud_and_search():
    m = MemoryStore()
    i = m.add("The user prefers tabs over spaces")
    m.add("Paris is the capital of France")
    assert m.search("does the user like tabs or spaces")[0]["id"] == i
    assert m.edit(i, "The user prefers spaces")
    assert "spaces" in m.get(i)["content"]
    assert m.delete(i) and m.get(i) is None
    m.core_set("persona", "helpful")
    assert m.core_get() == {"persona": "helpful"}


def test_skill_validation_and_search():
    s = SkillLibrary()
    s.save("reverse_string", "Reverse a string", "def reverse_string(s):\n    return s[::-1]\n")
    with pytest.raises(ValueError):
        s.save("bad", "x", "def other(): pass")
    assert s.search("reverse this string")[0]["name"] == "reverse_string"
    assert s.load_functions(["reverse_string"])["reverse_string"]("ab") == "ba"


def test_solves_and_saves_skill(agent):
    r = agent.run("add 2 and 3")
    assert r.success and r.result == 5 and r.new_skill == "add_numbers"
    assert agent.memory.list(kind="lesson")


def test_reuses_skill_on_repeat(agent):
    agent.run("add 2 and 3")
    r = agent.run("add 10 and 20")
    assert r.success and r.result == 30 and r.new_skill is None
    assert agent.skills.get("add_numbers")["uses"] == 2


def test_reflexion_retry_then_first_try_success(agent):
    r1 = agent.run("multiply 4 and 5")
    assert r1.success and r1.result == 20 and len(r1.attempts) == 2
    assert "ZeroDivisionError" in r1.attempts[0].error
    assert any("FAILURE" in m["content"] for m in agent.memory.list(kind="lesson"))
    r2 = agent.run("multiply 6 and 7")  # skill now exists -> no failure
    assert r2.success and r2.result == 42 and len(r2.attempts) == 1


def test_gives_up_after_max_retries(agent):
    r = agent.run("compose a symphony")
    assert not r.success and len(r.attempts) == 3


def test_file_tool_task(agent, tmp_path):
    (tmp_path / "f.txt").write_text("one two three")
    assert agent.run("count words in file f.txt").result == 3


def test_agent_writes_memory(agent):
    agent.run("remember that the deploy key lives in vault")
    assert agent.memory.search("where is the deploy key", kind="fact")


def test_tools_sandboxing(tmp_path):
    t = Tools(tmp_path)
    t.write_file("a/b.txt", "hi")
    assert t.read_file("a/b.txt") == "hi"
    with pytest.raises(ToolError):
        t.read_file("../../etc/passwd")
    with pytest.raises(ToolError):
        t.shell("echo hi")
    with pytest.raises(ToolError):
        t.web_fetch("https://example.com")
    assert Tools(tmp_path, allow_shell=True).shell("echo hi")["stdout"].strip() == "hi"
    with pytest.raises(ToolError):
        Tools(tmp_path, allow_web=True).web_fetch("file:///etc/passwd")


def test_parse_json():
    assert parse_json('sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('x {"b": 2} y') == {"b": 2}


def test_cli(tmp_path, capsys):
    h = ["--home", str(tmp_path)]
    assert main(h + ["run", "reverse 'hello'", "--backend", "mock", "-q"]) == 0
    assert "'olleh'" in capsys.readouterr().out
    main(h + ["skills", "list"])
    assert "reverse_string" in capsys.readouterr().out
    main(h + ["memory", "search", "reverse hello"])
    assert "lesson" in capsys.readouterr().out
