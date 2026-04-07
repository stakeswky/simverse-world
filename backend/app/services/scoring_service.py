"""
Quality scoring for residents.

Star rating system:
  1 star (临时居民): Has some content, format valid
  2 stars (正式居民): All three layers complete with substantive content (≥50 chars)
  3 stars (明星居民): Three layers complete + high conversations + high rating

Thresholds:
  - MIN_LAYER_LENGTH = 50 chars of non-header content per layer
  - STAR3_MIN_CONVERSATIONS = 50
  - STAR3_MIN_RATING = 3.5
"""
from enum import IntEnum


class StarLevel(IntEnum):
    TEMPORARY = 1   # 临时居民
    OFFICIAL = 2    # 正式居民
    STAR = 3        # 明星居民


MIN_LAYER_LENGTH = 50
STAR3_MIN_CONVERSATIONS = 50
STAR3_MIN_RATING = 3.5


def _strip_headers(md: str) -> str:
    """Remove markdown headers and whitespace, return concatenated content."""
    lines = md.strip().split("\n")
    content_lines = [
        line.strip() for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return " ".join(content_lines)


def _is_layer_substantive(md: str | None) -> bool:
    """Check if a markdown layer has meaningful content beyond headers."""
    if not md:
        return False
    content = _strip_headers(md)
    return len(content) >= MIN_LAYER_LENGTH


def compute_star_rating(resident) -> int:
    """
    Compute the star rating for a resident.

    Args:
        resident: Object with ability_md, persona_md, soul_md (str),
                  total_conversations (int), avg_rating (float) attributes.

    Returns:
        int: 1 (StarLevel.TEMPORARY), 2 (StarLevel.OFFICIAL), or 3 (StarLevel.STAR)
    """
    ability_ok = _is_layer_substantive(getattr(resident, 'ability_md', None))
    persona_ok = _is_layer_substantive(getattr(resident, 'persona_md', None))
    soul_ok = _is_layer_substantive(getattr(resident, 'soul_md', None))
    three_layers_complete = ability_ok and persona_ok and soul_ok

    total_conversations = getattr(resident, 'total_conversations', 0) or 0
    avg_rating = getattr(resident, 'avg_rating', 0.0) or 0.0

    # Star 3: three layers complete + high usage + high rating
    if (
        three_layers_complete
        and total_conversations >= STAR3_MIN_CONVERSATIONS
        and avg_rating >= STAR3_MIN_RATING
    ):
        return StarLevel.STAR

    # Star 2: three layers complete with substantive content
    if three_layers_complete:
        return StarLevel.OFFICIAL

    # Star 1: has some content or is new
    return StarLevel.TEMPORARY
