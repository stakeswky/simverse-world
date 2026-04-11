import pytest
from app.agent.registry import PluginRegistry, resolve_config_name


def _make_resident_stub(agent_config=None, so1="M", ac3="M"):
    class R:
        meta_json = {
            "sbti": {"dimensions": {"So1": so1, "Ac3": ac3}}
        }
    if agent_config:
        R.meta_json["agent_config"] = agent_config
    return R()


def test_load_all_finds_yaml_configs():
    reg = PluginRegistry()
    reg.load_all()
    assert "default" in reg._configs
    assert "introvert" in reg._configs
    assert "extravert" in reg._configs


def test_config_has_expected_phases():
    reg = PluginRegistry()
    reg.load_all()
    cfg = reg._configs["default"]
    assert cfg.phase_order == ["perceive", "plan", "decide", "execute", "memorize"]
    assert "perceive" in cfg.phases
    assert "plugin" in cfg.phases["perceive"]


def test_resolve_config_explicit_override():
    r = _make_resident_stub(agent_config="introvert")
    assert resolve_config_name(r) == "introvert"


def test_resolve_config_introvert_from_sbti():
    r = _make_resident_stub(so1="L")
    assert resolve_config_name(r) == "introvert"


def test_resolve_config_extravert_from_sbti():
    r = _make_resident_stub(so1="H", ac3="H")
    assert resolve_config_name(r) == "extravert"


def test_resolve_config_default_fallback():
    r = _make_resident_stub(so1="M", ac3="M")
    assert resolve_config_name(r) == "default"


def test_resolve_config_no_sbti():
    class R:
        meta_json = None
    assert resolve_config_name(R()) == "default"
