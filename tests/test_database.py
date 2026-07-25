import csv
import io

from app.database import Database


def test_case_round_trip_and_csv(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    case_id = database.create_case(
        {
            "vehicle_slug": "test-vehicle",
            "vehicle_make": "Test",
            "vehicle_model": "Car",
            "vehicle_year": "2026",
            "vehicle_trim": "Demo",
            "vin": "VIN-DEMO",
            "items": [
                {
                    "source": "ai_prediction",
                    "raw_part_name": "Front bumper",
                    "predicted_part_id": "part-1",
                    "predicted_part_name": "Front Bumper Cover",
                    "oem_number": "OEM-001",
                    "diagram_id": "diagram-1",
                    "ai_confidence": 0.9,
                    "ai_action": "Inspect",
                    "technician_decision": "Confirm",
                    "rejection_reason": "",
                    "corrected_part_id": "",
                    "corrected_part_name": "",
                    "technician_note": "Cracked",
                    "hotspot": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
                    "damage_type": "crack",
                    "severity": 0.7,
                    "evidence_image_id": "image-1",
                    "evidence_box": {
                        "x1": 0.1,
                        "y1": 0.2,
                        "x2": 0.3,
                        "y2": 0.4,
                    },
                    "reason": "Visible split line",
                    "propagation_path": [
                        "Front Bumper Cover",
                        "Energy Absorber",
                    ],
                    "probability_band": "medium",
                }
            ],
            "manual_regions": [
                {
                    "diagram_id": "diagram-1",
                    "x1": 0.1,
                    "y1": 0.2,
                    "x2": 0.3,
                    "y2": 0.4,
                    "technician_note": "",
                }
            ],
        }
    )

    saved = database.get_case(case_id)
    assert saved is not None
    assert saved["items"][0]["oem_number"] == "OEM-001"
    assert saved["items"][0]["damage_type"] == "crack"
    assert saved["items"][0]["evidence_box"]["x1"] == 0.1
    assert saved["items"][0]["propagation_path"][-1] == "Energy Absorber"
    assert saved["manual_regions"][0]["diagram_id"] == "diagram-1"

    csv_body = database.export_csv(case_id)
    assert csv_body is not None
    rows = list(csv.DictReader(io.StringIO(csv_body)))
    assert rows[0]["technician_decision"] == "Confirm"
    assert rows[0]["technician_note"] == "Cracked"

    history = database.history("test-vehicle")
    assert history["past_case_count"] == 1
    assert history["decisions"]["Confirm"] == 1


def test_local_vehicle_and_catalogue_import(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    vehicle = database.create_vehicle(
        {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2022,
            "trim": "GX",
            "vin": "",
        }
    )

    first_import = database.import_parts(
        vehicle["vehicle_id"],
        [
            {
                "part_name": "Front bumper cover",
                "oem_number": "52119-TEST",
                "category": "body",
                "diagram_url": "",
            },
            {
                "part_name": "Left headlamp",
                "oem_number": "81150-TEST",
                "category": "lighting",
                "diagram_url": "https://example.com/headlamp.png",
            },
        ],
    )
    assert first_import["created_count"] == 2
    assert first_import["total_part_count"] == 2

    second_import = database.import_parts(
        vehicle["vehicle_id"],
        [
            {
                "part_name": "Front bumper cover",
                "oem_number": "52119-TEST",
                "category": "body-exterior",
                "diagram_url": "",
            }
        ],
    )
    assert second_import["updated_count"] == 1
    assert len(database.get_parts(vehicle["vehicle_id"])) == 2

    refreshed = database.get_local_vehicle(vehicle["vehicle_id"])
    assert refreshed is not None
    assert refreshed["part_count"] == 2
    assert refreshed["diagram_count"] == 1


def test_similar_history_requires_matching_photo_pattern(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    database.create_photo_assessment(
        run_id="past-photo-run",
        vehicle_id="local:test",
        provider="test",
        model="test",
        impact_zone="front_left",
        impact_direction="rearward",
        impact_severity=0.72,
        images=[],
        result={},
    )
    database.create_case(
        {
            "vehicle_slug": "local:test",
            "vehicle_make": "Test",
            "vehicle_model": "Car",
            "vehicle_year": "2022",
            "photo_run_id": "past-photo-run",
            "items": [
                {
                    "source": "visible_damage",
                    "raw_part_name": "Front bumper cover",
                    "predicted_part_name": "Front bumper cover",
                    "damage_type": "deformation",
                    "severity": 0.7,
                    "technician_decision": "Confirm",
                },
                {
                    "source": "impact_path",
                    "raw_part_name": "From front bumper cover",
                    "predicted_part_name": "Radiator support",
                    "oem_number": "OEM-RADIATOR",
                    "technician_decision": "Confirm",
                },
            ],
        }
    )

    similar = database.find_similar_cases(
        vehicle_slug="local:test",
        impact_zone="front_left",
        impact_severity=0.68,
        visible_items=[
            {
                "raw_part_name": "Front bumper",
                "damage_type": "deformation",
            }
        ],
    )
    assert similar["match_count"] == 1
    assert similar["recommendations"][0]["part_name"] == "Radiator support"
    assert similar["recommendations"][0]["support_count"] == 1

    dissimilar = database.find_similar_cases(
        vehicle_slug="local:test",
        impact_zone="rear_right",
        impact_severity=0.7,
        visible_items=[
            {
                "raw_part_name": "Rear door",
                "damage_type": "scratch",
            }
        ],
    )
    assert dissimilar["match_count"] == 0
    assert dissimilar["recommendations"] == []
