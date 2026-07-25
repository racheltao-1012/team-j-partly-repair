from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


ALIASES: dict[str, tuple[str, ...]] = {
    "front_bumper_cover": (
        "front bumper cover",
        "front bumper",
        "front fascia",
        "bumper cover front",
    ),
    "rear_bumper_cover": (
        "rear bumper cover",
        "rear bumper",
        "rear fascia",
        "bumper cover rear",
    ),
    "bumper_bracket": ("bumper bracket", "bumper mounting bracket"),
    "energy_absorber": (
        "energy absorber",
        "impact absorber",
        "bumper absorber",
        "absorber foam",
    ),
    "bumper_reinforcement": (
        "bumper reinforcement",
        "reinforcement bar",
        "bumper beam",
        "impact bar",
    ),
    "crash_box": ("crash box", "crash can", "impact box"),
    "front_rail": ("front rail", "front longitudinal", "chassis rail"),
    "radiator_support": (
        "radiator support",
        "core support",
        "radiator carrier",
        "front panel",
    ),
    "radiator": ("radiator",),
    "condenser": ("ac condenser", "a/c condenser", "condenser"),
    "headlamp": ("headlamp", "headlight", "front lamp"),
    "headlamp_bracket": (
        "headlamp bracket",
        "headlight bracket",
        "lamp mounting bracket",
    ),
    "fender": ("fender", "front wing"),
    "fender_liner": ("fender liner", "wheel arch liner", "splash shield"),
    "hood": ("hood", "bonnet"),
    "hood_hinge": ("hood hinge", "bonnet hinge"),
    "hood_latch": ("hood latch", "bonnet latch", "hood lock"),
    "door": ("door shell", "front door", "rear door", "door"),
    "door_hinge": ("door hinge",),
    "side_impact_beam": (
        "side impact beam",
        "door reinforcement",
        "door intrusion beam",
    ),
    "wheel": ("wheel", "rim"),
    "wheel_bearing": ("wheel bearing", "hub bearing"),
    "steering_knuckle": ("steering knuckle", "hub carrier"),
    "control_arm": ("control arm", "suspension arm", "wishbone"),
    "parking_sensor": ("parking sensor", "park assist sensor", "pdc sensor"),
    "radar_sensor": ("radar sensor", "adaptive cruise radar", "adas radar"),
    "tail_lamp": ("tail lamp", "taillight", "rear lamp"),
    "tail_lamp_bracket": ("tail lamp bracket", "rear lamp bracket"),
    "rear_body_panel": ("rear body panel", "rear panel", "back panel"),
    "boot_floor": ("boot floor", "trunk floor", "luggage floor"),
}


def normalise_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def canonical_part_name(value: str) -> str:
    normalised = normalise_text(value)
    best_key = normalised.replace(" ", "_") or "unknown_part"
    best_score = 0.0
    for key, aliases in ALIASES.items():
        for alias in aliases:
            candidate = normalise_text(alias)
            if candidate == normalised:
                return key
            if candidate in normalised or normalised in candidate:
                score = min(len(candidate), len(normalised)) / max(
                    len(candidate), len(normalised), 1
                )
            else:
                score = SequenceMatcher(None, candidate, normalised).ratio()
            if score > best_score:
                best_key = key
                best_score = score
    return best_key if best_score >= 0.62 else normalised.replace(" ", "_")


def display_part_name(canonical: str) -> str:
    aliases = ALIASES.get(canonical)
    return (aliases[0] if aliases else canonical.replace("_", " ")).title()


def catalogue_match(
    generic_name: str,
    parts: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    canonical = canonical_part_name(generic_name)
    search_terms = ALIASES.get(canonical, (normalise_text(generic_name),))
    best_part: dict[str, Any] | None = None
    best_score = 0.0
    for part in parts:
        part_name = normalise_text(str(part.get("part_name") or ""))
        if not part_name:
            continue
        for term in search_terms:
            candidate = normalise_text(term)
            candidate_tokens = set(candidate.split())
            part_tokens = set(part_name.split())
            overlap = len(candidate_tokens & part_tokens) / max(
                len(candidate_tokens), 1
            )
            substring = 1.0 if candidate in part_name else 0.0
            sequence = SequenceMatcher(None, candidate, part_name).ratio()
            score = max(substring, 0.62 * overlap + 0.38 * sequence)
            if score > best_score:
                best_part = part
                best_score = score
    if best_score < 0.46:
        return None, best_score
    return best_part, best_score
