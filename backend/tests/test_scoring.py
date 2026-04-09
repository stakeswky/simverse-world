import pytest
from unittest.mock import MagicMock
from app.services.scoring_service import compute_star_rating, StarLevel


def _make_resident(**kwargs):
    defaults = {
        "ability_md": "",
        "persona_md": "",
        "soul_md": "",
        "total_conversations": 0,
        "avg_rating": 0.0,
    }
    defaults.update(kwargs)
    r = MagicMock()
    for k, v in defaults.items():
        setattr(r, k, v)
    return r


def test_star_1_all_empty():
    r = _make_resident()
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_1_only_ability():
    r = _make_resident(ability_md="# Ability\nSome ability content here")
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_1_layers_too_short():
    r = _make_resident(ability_md="# Ability\nOk", persona_md="# Persona\nOk", soul_md="# Soul\nOk")
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_2_three_layers_complete():
    r = _make_resident(
        ability_md="# Ability\n## Professional\n- Backend architecture design\n- High concurrency systems\n- API optimization and database tuning",
        persona_md="# Persona\n## Layer 0: Core\n- **Introverted but decisive**: Makes clear decisions\n\n## Layer 2: Expression\n- Concise, data-driven communication style",
        soul_md="# Soul\n## Values\n- Truth over comfort, always\n\n## Background\n- 10 years in technology industry building systems",
    )
    assert compute_star_rating(r) == StarLevel.OFFICIAL


def test_star_3_popular_and_maintained():
    ability = "# Ability\n## Professional\n- Backend architecture\n- System design and performance optimization\n- Distributed systems engineering"
    persona = "# Persona\n## Layer 0: Core\n- **Rigorous**: Never ships without proper testing\n\n## Layer 1: Identity\n- Senior engineering lead\n\n## Layer 2: Expression\n- Precise, avoids ambiguity"
    soul = "# Soul\n## Values\n- Engineering excellence matters\n- Knowledge sharing is fundamental\n\n## Experience\n- Built systems serving millions of users"
    r = _make_resident(ability_md=ability, persona_md=persona, soul_md=soul,
                       total_conversations=100, avg_rating=4.2)
    assert compute_star_rating(r) == StarLevel.STAR


def test_star_3_not_enough_conversations():
    ability = "# Ability\n## Professional\n- Backend architecture\n- System design and performance optimization\n- Distributed systems engineering"
    persona = "# Persona\n## Layer 0: Core\n- **Rigorous**: Never ships without testing\n\n## Layer 1: Identity\n- Engineer\n\n## Layer 2: Expression\n- Precise"
    soul = "# Soul\n## Values\n- Excellence always matters\n\n## Experience\n- Built reliable production systems"
    r = _make_resident(ability_md=ability, persona_md=persona, soul_md=soul,
                       total_conversations=5, avg_rating=4.5)
    assert compute_star_rating(r) == StarLevel.OFFICIAL


def test_star_3_low_rating():
    ability = "# Ability\n## Professional\n- Backend architecture\n- System design and performance\n- Distributed systems"
    persona = "# Persona\n## Layer 0: Core\n- **Rigorous**: Tests everything\n\n## Layer 1: Identity\n- Engineer\n\n## Layer 2: Expression\n- Precise"
    soul = "# Soul\n## Values\n- Excellence always matters\n\n## Experience\n- Built production systems"
    r = _make_resident(ability_md=ability, persona_md=persona, soul_md=soul,
                       total_conversations=200, avg_rating=2.1)
    assert compute_star_rating(r) == StarLevel.OFFICIAL
