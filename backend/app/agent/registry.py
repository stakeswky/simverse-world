"""Plugin registry: YAML config loading + importlib dynamic plugin instantiation."""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from app.agent.phases.base import PhasePlugin
    from app.models.resident import Resident

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "configs"


@dataclass
class AgentConfig:
    name: str
    description: str
    phase_order: list[str]
    phases: dict[str, dict[str, Any]]


def _parse_yaml(path: Path) -> AgentConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AgentConfig(
        name=data["name"],
        description=data.get("description", ""),
        phase_order=data["phase_order"],
        phases=data["phases"],
    )


def _import_class(dotted_path: str) -> type:
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def resolve_config_name(resident: Resident) -> str:
    meta = resident.meta_json or {}
    explicit = meta.get("agent_config")
    if explicit:
        return explicit
    sbti = meta.get("sbti", {})
    dims = sbti.get("dimensions", {})
    so1 = dims.get("So1", "M")
    ac3 = dims.get("Ac3", "M")
    if so1 == "L":
        return "introvert"
    elif so1 == "H" and ac3 == "H":
        return "extravert"
    return "default"


class PluginRegistry:
    def __init__(self):
        self._configs: dict[str, AgentConfig] = {}
        self._phase_cache: dict[str, list[PhasePlugin]] = {}

    def load_all(self) -> None:
        self._configs.clear()
        self._phase_cache.clear()
        for yaml_file in sorted(CONFIG_DIR.glob("*.yaml")):
            try:
                config = _parse_yaml(yaml_file)
                self._configs[config.name] = config
                logger.info("Loaded agent config: %s (%s)", config.name, yaml_file.name)
            except Exception as e:
                logger.error("Failed to load agent config %s: %s", yaml_file, e)

    def get_phases(self, resident: Resident) -> list[PhasePlugin]:
        config_name = resolve_config_name(resident)
        if config_name not in self._phase_cache:
            config = self._configs.get(config_name)
            if config is None:
                config = self._configs.get("default")
            if config is None:
                raise RuntimeError("No agent configs loaded. Call registry.load_all() first.")
            self._phase_cache[config_name] = self._build_phases(config)
        return self._phase_cache[config_name]

    def _build_phases(self, config: AgentConfig) -> list[PhasePlugin]:
        phases = []
        for phase_name in config.phase_order:
            phase_def = config.phases[phase_name]
            plugin_path = phase_def["plugin"]
            params = phase_def.get("params", {})
            cls = _import_class(plugin_path)
            instance = cls(params=params)
            phases.append(instance)
            logger.debug("Instantiated %s for phase '%s'", cls.__name__, phase_name)
        return phases


registry = PluginRegistry()
