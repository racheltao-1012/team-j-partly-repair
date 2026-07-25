import asyncio

from app.database import Database
from app.impact_graph import ImpactPropagationService
from app.services.photo_assessment_service import PhotoAssessmentService
from app.vision import PhotoInput


class FakeVehicleService:
    async def get_vehicle(self, vehicle_id):
        if vehicle_id != "local:test":
            return None
        return {
            "id": vehicle_id,
            "provider_key": "test",
            "display_name": "2022 Test Car",
            "make": "Test",
            "model": "Car",
            "year": 2022,
            "trim": "",
            "source": "local_catalogue",
            "part_count": 3,
            "diagram_count": 0,
        }

    async def get_parts(self, vehicle_id):
        assert vehicle_id == "local:test"
        return [
            {
                "part_id": "cover",
                "part_name": "Front bumper cover",
                "oem_number": "OEM-COVER",
                "diagram_id": None,
                "diagram_url": None,
            },
            {
                "part_id": "absorber",
                "part_name": "Front bumper energy absorber",
                "oem_number": "OEM-ABSORBER",
                "diagram_id": None,
                "diagram_url": None,
            },
            {
                "part_id": "beam",
                "part_name": "Front bumper reinforcement bar",
                "oem_number": "OEM-BEAM",
                "diagram_id": None,
                "diagram_url": None,
            },
        ]


class UnconfiguredProvider:
    name = "test_provider"
    model = "test_model"
    configured = False

    async def analyse(self, **_kwargs):
        raise AssertionError("Guided mode should not call the vision provider")


def test_probability_graph_returns_traceable_hidden_checks(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    service = ImpactPropagationService(database)
    suggestions = service.propagate(
        detections=[
            {
                "part_name": "Front bumper cover",
                "confidence": 0.92,
                "severity": 0.75,
            }
        ],
        impact_zone="front_left",
        impact_severity=0.75,
        catalogue_parts=asyncio.run(
            FakeVehicleService().get_parts("local:test")
        ),
    )

    assert suggestions
    assert suggestions[0]["probability"] > suggestions[-1]["probability"]
    assert suggestions[0]["path"][0] == "Front Bumper Cover"
    assert all(item["probability"] < 1 for item in suggestions)
    assert any(
        item["catalogue_part"]
        and item["catalogue_part"]["oem_number"] == "OEM-ABSORBER"
        for item in suggestions
    )


def test_guided_photo_flow_is_labelled_and_persisted(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    service = PhotoAssessmentService(
        database=database,
        vehicle_service=FakeVehicleService(),
        vision_provider=UnconfiguredProvider(),
        storage_dir=tmp_path / "photos",
    )
    result = asyncio.run(
        service.analyse(
            vehicle_id="local:test",
            images=[
                PhotoInput(
                    image_id="image-1",
                    content_type="image/jpeg",
                    body=b"sanitised-test-image",
                )
            ],
            mode="guided",
            impact_hint="front_left",
            guided_visible_part="Front bumper cover",
            guided_damage_type="deformation",
            guided_severity=0.7,
        )
    )

    photo = result["photo_assessment"]
    assert result["workflow_mode"] == "guided_photo_workflow"
    assert photo["provider"] == "technician_guided_demo"
    assert "not image inference" in photo["quality_warnings"][0].lower()
    assert result["items"][0]["source"] == "manual"
    assert result["items"][0]["oem_number"] == "OEM-COVER"
    assert any(
        item["source"] == "impact_path"
        and item["technician_decision"] == "Needs inspection"
        for item in result["items"]
    )

    saved = service.get(photo["run_id"])
    assert saved is not None
    image_row = database.get_photo_image(photo["run_id"], "image-1")
    assert image_row is not None


def test_photo_flow_adds_only_similarity_gated_history_checks(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    database.create_photo_assessment(
        run_id="past-run",
        vehicle_id="local:test",
        provider="test",
        model="test",
        impact_zone="front_left",
        impact_direction="rearward",
        impact_severity=0.7,
        images=[],
        result={},
    )
    database.create_case(
        {
            "vehicle_slug": "local:test",
            "vehicle_make": "Test",
            "vehicle_model": "Car",
            "vehicle_year": "2022",
            "photo_run_id": "past-run",
            "items": [
                {
                    "source": "visible_damage",
                    "raw_part_name": "Front bumper cover",
                    "predicted_part_name": "Front bumper cover",
                    "damage_type": "deformation",
                    "technician_decision": "Confirm",
                },
                {
                    "source": "impact_path",
                    "predicted_part_name": "Hood latch support",
                    "technician_decision": "Confirm",
                },
            ],
        }
    )
    service = PhotoAssessmentService(
        database=database,
        vehicle_service=FakeVehicleService(),
        vision_provider=UnconfiguredProvider(),
        storage_dir=tmp_path / "photos",
    )
    result = asyncio.run(
        service.analyse(
            vehicle_id="local:test",
            images=[
                PhotoInput(
                    image_id="current-image",
                    content_type="image/jpeg",
                    body=b"sanitised-test-image",
                )
            ],
            mode="guided",
            impact_hint="front_left",
            guided_visible_part="Front bumper",
            guided_damage_type="deformation",
            guided_severity=0.68,
        )
    )

    assert result["similar_cases"]["match_count"] == 1
    history_rows = [
        item for item in result["items"]
        if item["source"] == "historical_case"
    ]
    assert history_rows[0]["predicted_part_name"] == "Hood latch support"
    assert history_rows[0]["technician_decision"] == "Needs inspection"
    assert "not photo-confirmed" in history_rows[0]["ai_action"]
