from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.part_matching import canonical_part_name, catalogue_match, display_part_name


DEFAULT_RELATIONS: tuple[tuple[str, str, str, float, str], ...] = (
    ("front_bumper_cover", "bumper_bracket", "attached_to", 0.90, "front"),
    ("front_bumper_cover", "energy_absorber", "behind", 0.86, "front"),
    ("front_bumper_cover", "parking_sensor", "embedded_in", 0.66, "front"),
    ("front_bumper_cover", "radar_sensor", "adjacent_to", 0.58, "front"),
    ("front_bumper_cover", "headlamp_bracket", "adjacent_to", 0.54, "front"),
    ("energy_absorber", "bumper_reinforcement", "load_path", 0.82, "front"),
    ("bumper_reinforcement", "crash_box", "load_path", 0.72, "front"),
    ("crash_box", "front_rail", "structural_path", 0.58, "front"),
    ("bumper_reinforcement", "radiator_support", "adjacent_to", 0.52, "front"),
    ("radiator_support", "radiator", "mounted_to", 0.48, "front"),
    ("radiator_support", "condenser", "mounted_to", 0.43, "front"),
    ("headlamp", "headlamp_bracket", "mounted_to", 0.88, "front"),
    ("headlamp", "radiator_support", "adjacent_to", 0.40, "front"),
    ("fender", "fender_liner", "attached_to", 0.82, "side"),
    ("fender", "headlamp_bracket", "adjacent_to", 0.55, "front"),
    ("hood", "hood_hinge", "attached_to", 0.72, "front"),
    ("hood", "hood_latch", "attached_to", 0.62, "front"),
    ("hood", "radiator_support", "adjacent_to", 0.46, "front"),
    ("door", "door_hinge", "attached_to", 0.66, "side"),
    ("door", "side_impact_beam", "behind", 0.76, "side"),
    ("wheel", "wheel_bearing", "load_path", 0.78, "side"),
    ("wheel", "steering_knuckle", "load_path", 0.68, "side"),
    ("steering_knuckle", "control_arm", "load_path", 0.62, "side"),
    ("rear_bumper_cover", "bumper_bracket", "attached_to", 0.90, "rear"),
    ("rear_bumper_cover", "energy_absorber", "behind", 0.86, "rear"),
    ("rear_bumper_cover", "parking_sensor", "embedded_in", 0.66, "rear"),
    ("energy_absorber", "bumper_reinforcement", "load_path", 0.82, "rear"),
    ("bumper_reinforcement", "crash_box", "load_path", 0.68, "rear"),
    ("crash_box", "rear_body_panel", "structural_path", 0.56, "rear"),
    ("rear_body_panel", "boot_floor", "structural_path", 0.46, "rear"),
    ("tail_lamp", "tail_lamp_bracket", "mounted_to", 0.86, "rear"),
    ("tail_lamp", "rear_body_panel", "adjacent_to", 0.42, "rear"),
)


def _direction_factor(relation_zone: str, impact_zone: str) -> float:
    if relation_zone == "any" or impact_zone == "unknown":
        return 0.85
    if relation_zone in impact_zone or impact_zone in relation_zone:
        return 1.0
    if relation_zone == "side" and any(
        side in impact_zone for side in ("left", "right", "side")
    ):
        return 1.0
    return 0.62


def _band(probability: float) -> str:
    if probability >= 0.50:
        return "high"
    if probability >= 0.25:
        return "medium"
    return "low"


class ImpactPropagationService:
    def __init__(self, database: Any) -> None:
        self.database = database

    def propagate(
        self,
        *,
        detections: list[dict[str, Any]],
        impact_zone: str,
        impact_severity: float,
        catalogue_parts: list[dict[str, Any]],
        max_hops: int = 3,
        minimum_probability: float = 0.08,
    ) -> list[dict[str, Any]]:
        relations = self.database.list_part_relations()
        adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relation in relations:
            adjacency[str(relation["source_part"])].append(relation)

        visible_canonical = {
            canonical_part_name(str(item.get("part_name") or ""))
            for item in detections
        }
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for detection in detections:
            root = canonical_part_name(str(detection.get("part_name") or ""))
            root_confidence = float(detection.get("confidence") or 0)
            severity = max(
                float(detection.get("severity") or 0),
                float(impact_severity or 0),
            )
            root_strength = root_confidence * (0.45 + 0.55 * severity)
            queue: list[tuple[str, float, list[str], list[str], int]] = [
                (root, root_strength, [root], [], 0)
            ]
            best_seen = {root: root_strength}

            while queue:
                node, score, path, relations_used, hops = queue.pop(0)
                if hops >= max_hops:
                    continue
                for relation in adjacency.get(node, []):
                    target = str(relation["target_part"])
                    weight = float(relation["propagation_weight"])
                    direction = _direction_factor(
                        str(relation["impact_zone"]),
                        impact_zone,
                    )
                    next_score = (
                        score
                        * weight
                        * direction
                        * math.exp(-0.18 * hops)
                    )
                    if next_score <= best_seen.get(target, 0):
                        continue
                    best_seen[target] = next_score
                    next_path = path + [target]
                    next_relations = relations_used + [
                        str(relation["relation_type"])
                    ]
                    queue.append(
                        (
                            target,
                            next_score,
                            next_path,
                            next_relations,
                            hops + 1,
                        )
                    )
                    if (
                        target not in visible_canonical
                        and next_score >= minimum_probability
                    ):
                        candidates[target].append(
                            {
                                "probability": next_score,
                                "source_visible_part": root,
                                "path": next_path,
                                "relations": next_relations,
                            }
                        )

        suggestions: list[dict[str, Any]] = []
        for target, paths in candidates.items():
            combined = 1.0
            for path in paths:
                combined *= 1.0 - min(float(path["probability"]), 0.95)
            combined = 1.0 - combined
            best_path = max(paths, key=lambda item: item["probability"])
            matched_part, match_score = catalogue_match(
                display_part_name(target),
                catalogue_parts,
            )
            suggestions.append(
                {
                    "target_part": target,
                    "display_name": (
                        matched_part.get("part_name")
                        if matched_part
                        else display_part_name(target)
                    ),
                    "probability": round(min(combined, 0.95), 4),
                    "probability_band": _band(combined),
                    "source_visible_part": display_part_name(
                        str(best_path["source_visible_part"])
                    ),
                    "path": [
                        display_part_name(node)
                        for node in best_path["path"]
                    ],
                    "relations": best_path["relations"],
                    "catalogue_part": matched_part,
                    "catalogue_match_score": round(match_score, 4),
                }
            )
        suggestions.sort(key=lambda item: item["probability"], reverse=True)
        return suggestions[:8]
