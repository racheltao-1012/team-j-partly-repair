from app.assessment import (
    build_impact_checklist,
    build_impact_suggestions,
    build_prediction_items,
    normalise_confidence,
)


def prediction_fixture():
    return {
        "oem_parts": {
            "completed": {
                "data": {
                    "oem_parts": [
                        {
                            "raw_part_name": "Front bumper cover",
                            "associated_oem_parts": [
                                {
                                    "part_id": "part-cover",
                                    "diagram_id": "diagram-front",
                                    "part_name": "Cover",
                                    "confidence": 0.91,
                                }
                            ],
                        }
                    ]
                }
            }
        }
    }


def assemblies_fixture():
    return {
        "assemblies": {
            "part-cover": {
                "display_name": "Front Bumper Cover",
                "manufacturer_part_number": "52119-TEST",
                "is_orderable": True,
                "hotspot": {
                    "diagram_id": "diagram-front",
                    "x1": 100,
                    "y1": 120,
                    "x2": 240,
                    "y2": 210,
                },
            },
            "part-sensor": {
                "display_name": "Front Parking Sensor",
                "manufacturer_part_number": "89341-TEST",
                "is_orderable": True,
                "hotspot": {
                    "diagram_id": "diagram-front",
                    "x1": 250,
                    "y1": 130,
                    "x2": 275,
                    "y2": 155,
                },
            },
        }
    }


def test_confidence_normalisation():
    assert normalise_confidence(0.92) == 0.92
    assert normalise_confidence(92) == 0.92
    assert normalise_confidence("92%") == 0.92
    assert normalise_confidence("unknown") is None


def test_prediction_joins_to_catalogue_and_oem():
    rows = build_prediction_items(prediction_fixture(), assemblies_fixture())
    assert len(rows) == 1
    assert rows[0]["predicted_part_id"] == "part-cover"
    assert rows[0]["predicted_part_name"] == "Front Bumper Cover"
    assert rows[0]["oem_number"] == "52119-TEST"
    assert rows[0]["diagram_id"] == "diagram-front"
    assert rows[0]["technician_decision"] == "Pending"


def test_impact_path_is_an_inspection_suggestion():
    direct = build_prediction_items(prediction_fixture(), assemblies_fixture())
    suggestions = build_impact_suggestions(direct, assemblies_fixture())
    assert len(suggestions) == 1
    assert suggestions[0]["predicted_part_id"] == "part-sensor"
    assert suggestions[0]["technician_decision"] == "Needs inspection"
    assert "hidden" in suggestions[0]["ai_action"].lower()


def test_checklist_keeps_safety_disclaimer():
    checklist = build_impact_checklist(["Front bumper cover"])
    assert checklist
    assert "technician" in checklist[0]["disclaimer"].lower()

