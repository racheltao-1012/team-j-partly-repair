from __future__ import annotations

from collections.abc import Iterable
from typing import Any


IMPACT_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("front bumper", "front fascia", "bumper cover"),
        ("reinforcement", "absorber", "bracket", "sensor", "radar"),
    ),
    (
        ("rear bumper", "rear fascia"),
        ("reinforcement", "absorber", "bracket", "sensor", "reflector"),
    ),
    (
        ("fender", "wing"),
        ("liner", "bracket", "lamp", "splash"),
    ),
    (
        ("hood", "bonnet"),
        ("hinge", "latch", "insulator", "striker"),
    ),
    (
        ("door",),
        ("hinge", "handle", "mirror", "sensor", "weatherstrip"),
    ),
    (
        ("headlamp", "headlight", "lamp"),
        ("bracket", "module", "bulb", "connector"),
    ),
    (
        ("wheel", "suspension", "tyre", "tire"),
        ("arm", "knuckle", "bearing", "strut", "sensor"),
    ),
)


def normalise_confidence(value: Any) -> float | None:
    """Return confidence as 0..1 when the source value is usable."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        try:
            number = float(cleaned)
        except ValueError:
            return None
        if "%" in value or number > 1:
            number /= 100
    elif isinstance(value, (int, float)):
        number = float(value)
        if number > 1:
            number /= 100
    else:
        return None
    return max(0.0, min(number, 1.0))


def get_assemblies(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Accept either {'assemblies': {...}} or the mapping itself."""
    assemblies = payload.get("assemblies", payload)
    if not isinstance(assemblies, dict):
        return {}
    return {
        str(part_id): value
        for part_id, value in assemblies.items()
        if isinstance(value, dict)
    }


def get_prediction_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Read the nested prediction shape documented in the event test script."""
    current: Any = payload
    for key in ("oem_parts", "completed", "data", "oem_parts"):
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    if not isinstance(current, list):
        return []
    return [item for item in current if isinstance(item, dict)]


def _candidate_sort_key(candidate: dict[str, Any]) -> float:
    return normalise_confidence(candidate.get("confidence")) or -1


def build_prediction_items(
    prediction_payload: dict[str, Any],
    assemblies_payload: dict[str, Any],
    *,
    max_candidates_per_damage: int = 3,
) -> list[dict[str, Any]]:
    """Join AI candidates to Partly catalogue records by part_id."""
    assemblies = get_assemblies(assemblies_payload)
    rows: list[dict[str, Any]] = []

    for group_index, group in enumerate(get_prediction_groups(prediction_payload), start=1):
        raw_name = str(group.get("raw_part_name") or "Unknown damaged area")
        candidates = group.get("associated_oem_parts") or []
        if not isinstance(candidates, list):
            continue
        valid_candidates = [c for c in candidates if isinstance(c, dict)]
        valid_candidates.sort(key=_candidate_sort_key, reverse=True)

        for rank, candidate in enumerate(
            valid_candidates[:max_candidates_per_damage],
            start=1,
        ):
            part_id = str(candidate.get("part_id") or "")
            part = assemblies.get(part_id, {})
            confidence = normalise_confidence(candidate.get("confidence"))
            diagram_id = candidate.get("diagram_id")
            hotspot = part.get("hotspot") if isinstance(part.get("hotspot"), dict) else None
            if not diagram_id and hotspot:
                diagram_id = hotspot.get("diagram_id")

            rows.append(
                {
                    "source": "ai_prediction",
                    "damage_group": group_index,
                    "candidate_rank": rank,
                    "raw_part_name": raw_name,
                    "predicted_part_id": part_id or None,
                    "predicted_part_name": (
                        part.get("display_name")
                        or candidate.get("part_name")
                        or "Unresolved catalogue part"
                    ),
                    "oem_number": part.get("manufacturer_part_number"),
                    "diagram_id": str(diagram_id) if diagram_id else None,
                    "diagram_url": None,
                    "ai_confidence": confidence,
                    "is_orderable": part.get("is_orderable"),
                    "ai_action": "Inspect; replace only if technician confirms",
                    "technician_decision": "Pending",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "",
                    "hotspot": hotspot,
                }
            )
    return rows


def _rule_terms(raw_part_name: str) -> tuple[str, ...]:
    lowered = raw_part_name.casefold()
    terms: list[str] = []
    for triggers, recommendations in IMPACT_RULES:
        if any(trigger in lowered for trigger in triggers):
            terms.extend(recommendations)
    return tuple(dict.fromkeys(terms))


def build_impact_suggestions(
    prediction_items: Iterable[dict[str, Any]],
    assemblies_payload: dict[str, Any],
    *,
    max_suggestions_per_damage: int = 2,
) -> list[dict[str, Any]]:
    """Match rule-based hidden-damage checks to real catalogue parts.

    These are explicitly inspection suggestions, not damage diagnoses.
    """
    assemblies = get_assemblies(assemblies_payload)
    direct_ids = {
        str(item["predicted_part_id"])
        for item in prediction_items
        if item.get("predicted_part_id")
    }
    raw_names = list(
        dict.fromkeys(
            str(item.get("raw_part_name") or "")
            for item in prediction_items
            if item.get("raw_part_name")
        )
    )
    suggestions: list[dict[str, Any]] = []
    used_ids = set(direct_ids)

    for raw_name in raw_names:
        terms = _rule_terms(raw_name)
        if not terms:
            continue
        matches: list[tuple[int, str, dict[str, Any]]] = []
        for part_id, part in assemblies.items():
            if part_id in used_ids:
                continue
            display_name = str(part.get("display_name") or "").casefold()
            score = sum(1 for term in terms if term in display_name)
            if score:
                matches.append((score, part_id, part))
        matches.sort(key=lambda item: (-item[0], str(item[2].get("display_name") or "")))

        for _score, part_id, part in matches[:max_suggestions_per_damage]:
            hotspot = part.get("hotspot") if isinstance(part.get("hotspot"), dict) else None
            diagram_id = hotspot.get("diagram_id") if hotspot else None
            suggestions.append(
                {
                    "source": "impact_path",
                    "damage_group": None,
                    "candidate_rank": None,
                    "raw_part_name": raw_name,
                    "predicted_part_id": part_id,
                    "predicted_part_name": part.get("display_name") or "Nearby component",
                    "oem_number": part.get("manufacturer_part_number"),
                    "diagram_id": str(diagram_id) if diagram_id else None,
                    "diagram_url": None,
                    "ai_confidence": None,
                    "is_orderable": part.get("is_orderable"),
                    "ai_action": "Inspect for hidden or propagated damage",
                    "technician_decision": "Needs inspection",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "",
                    "hotspot": hotspot,
                }
            )
            used_ids.add(part_id)
    return suggestions


def build_impact_checklist(raw_part_names: Iterable[str]) -> list[dict[str, Any]]:
    """Return human-readable checks even when no catalogue name matches."""
    checklist: list[dict[str, Any]] = []
    for raw_name in dict.fromkeys(raw_part_names):
        terms = _rule_terms(raw_name)
        if terms:
            checklist.append(
                {
                    "damage_area": raw_name,
                    "inspect": [term.title() for term in terms],
                    "disclaimer": "Inspection suggestion only; technician confirmation required.",
                }
            )
    return checklist
