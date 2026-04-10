import pytest
from unittest.mock import MagicMock
from app.models.resident import Resident
from app.models.memory import Memory
from app.llm.prompt import assemble_system_prompt, format_memory_context


def _make_resident():
    r = MagicMock(spec=Resident)
    r.name = "TestNPC"
    r.district = "engineering"
    r.soul_md = "Seeks truth"
    r.persona_md = "Quiet thinker"
    r.ability_md = "Python expert"
    return r


def _make_memory(content, type="event", importance=0.5, metadata_json=None):
    m = MagicMock(spec=Memory)
    m.content = content
    m.type = type
    m.importance = importance
    m.metadata_json = metadata_json
    return m


def test_format_memory_context_with_all_layers():
    relationship = _make_memory(
        "A curious beginner who likes cats",
        type="relationship",
        metadata_json={"affinity": 0.5, "trust": 0.6, "tags": ["beginner", "cat-lover"]},
    )
    reflections = [
        _make_memory("People here are always busy", type="reflection", importance=0.8),
        _make_memory("I enjoy teaching newcomers", type="reflection", importance=0.7),
    ]
    events = [
        _make_memory("Discussed async patterns yesterday", type="event"),
        _make_memory("They showed me a cat photo", type="event"),
    ]

    ctx = {"relationship": relationship, "reflections": reflections, "events": events}
    result = format_memory_context(ctx)

    assert "A curious beginner who likes cats" in result
    assert "People here are always busy" in result
    assert "Discussed async patterns yesterday" in result


def test_format_memory_context_empty():
    ctx = {"relationship": None, "reflections": [], "events": []}
    result = format_memory_context(ctx)
    assert result == ""


def test_assemble_prompt_with_memory():
    r = _make_resident()
    ctx = {
        "relationship": _make_memory("A kind visitor", type="relationship"),
        "reflections": [_make_memory("I like deep talks", type="reflection")],
        "events": [_make_memory("Chatted about AI", type="event")],
    }

    prompt = assemble_system_prompt(r, memory_context=ctx)

    assert "A kind visitor" in prompt
    assert "I like deep talks" in prompt
    assert "Chatted about AI" in prompt
    assert "TestNPC" in prompt


def test_assemble_prompt_without_memory():
    r = _make_resident()
    prompt = assemble_system_prompt(r)

    assert "TestNPC" in prompt
    assert "Seeks truth" in prompt
    # No memory section when no context provided
    assert "记忆" not in prompt
