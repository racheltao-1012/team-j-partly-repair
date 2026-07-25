from __future__ import annotations

import re
from typing import Any


TOKEN_ALIASES = {
    "bumper": "bumper",
    "cover": "cover",
    "fascia": "cover",
    "lamp": "lamp",
    "light": "lamp",
    "headlamp": "headlamp",
    "headlight": "headlamp",
    "fender": "fender",
    "wing": "fender",
    "reinforcement": "reinforcement",
    "beam": "reinforcement",
}

IGNORED_TOKENS = {
    "assembly",
    "assy",
    "car",
    "component",
    "left",
    "part",
    "right",
    "the",
    "vehicle",
}


def normalised_tokens(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return {
        TOKEN_ALIASES.get(token, token)
        for token in tokens
        if token not in IGNORED_TOKENS
    }


def text_similarity(left: str, right: str) -> float:
    left_tokens = normalised_tokens(left)
    right_tokens = normalised_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def best_part_overlap(current_parts: list[str], past_parts: list[str]) -> float:
    return max(
        (
            text_similarity(current, past)
            for current in current_parts
            for past in past_parts
        ),
        default=0.0,
    )


def _zone_family(zone: str) -> set[str]:
    return set(str(zone or "").lower().replace("-", "_").split("_")) - {
        "",
        "unknown",
    }


def zone_similarity(current_zone: str, past_zone: str) -> float:
    current = str(current_zone or "").lower()
    past = str(past_zone or "").lower()
    if not current or not past or "unknown" in {current, past}:
        return 0.0
    if current == past:
        return 1.0
    current_family = _zone_family(current)
    past_family = _zone_family(past)
    if current_family & past_family:
        return 0.55
    return 0.0


def case_similarity(
    *,
    current_zone: str,
    current_severity: float,
    current_parts: list[str],
    current_damage_types: list[str],
    past_zone: str,
    past_severity: float,
    past_parts: list[str],
    past_damage_types: list[str],
) -> tuple[float, list[str]]:
    zone_score = zone_similarity(current_zone, past_zone)
    part_score = best_part_overlap(current_parts, past_parts)
    damage_score = best_part_overlap(
        current_damage_types,
        past_damage_types,
    )
    severity_score = max(
        0.0,
        1.0 - abs(float(current_severity) - float(past_severity)),
    )

    # A case cannot become "similar" from severity alone. It needs the same
    # impact region or a recognisably similar directly visible part.
    if zone_score == 0 and part_score < 0.5:
        return 0.0, []

    score = (
        0.35 * zone_score
        + 0.40 * part_score
        + 0.10 * damage_score
        + 0.15 * severity_score
    )
    signals: list[str] = []
    if zone_score == 1:
        signals.append("same impact zone")
    elif zone_score:
        signals.append("related impact region")
    if part_score >= 0.5:
        signals.append("matching visible part")
    if damage_score >= 0.5:
        signals.append("matching damage type")
    if severity_score >= 0.8:
        signals.append("similar visual severity")
    return round(score, 4), signals


def confirmed_part_name(item: dict[str, Any]) -> str:
    return str(
        item.get("corrected_part_name")
        or item.get("predicted_part_name")
        or item.get("raw_part_name")
        or ""
    ).strip()
