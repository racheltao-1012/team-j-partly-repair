import asyncio
import json

import app.vision as vision_module
from app.vision import OpenAIVisionProvider, PhotoInput


class FakeResponse:
    is_error = False
    status_code = 200

    def json(self):
        structured = {
            "photos_are_usable": True,
            "quality_warnings": [],
            "impact_zone": "front_left",
            "impact_direction": "rearward",
            "impact_severity": 0.7,
            "detections": [
                {
                    "image_index": 0,
                    "part_name": "front bumper cover",
                    "damage_type": "deformation",
                    "confidence": 0.88,
                    "severity": 0.72,
                    "bounding_box": {
                        "x1": 0.1,
                        "y1": 0.4,
                        "x2": 0.8,
                        "y2": 0.9,
                    },
                    "visual_evidence": "Visible distortion",
                }
            ],
        }
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(structured),
                        }
                    ],
                }
            ]
        }


class FakeAsyncClient:
    last_request = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers, json):
        FakeAsyncClient.last_request = {
            "url": url,
            "headers": headers,
            "json": json,
        }
        return FakeResponse()


def test_openai_provider_sends_images_and_parses_structured_output(monkeypatch):
    monkeypatch.setattr(vision_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = OpenAIVisionProvider(
        api_key="test-key",
        model="test-vision-model",
    )
    result = asyncio.run(
        provider.analyse(
            images=[
                PhotoInput(
                    image_id="image-1",
                    content_type="image/jpeg",
                    body=b"test-image-bytes",
                )
            ],
            vehicle={
                "year": 2022,
                "make": "Toyota",
                "model": "Corolla",
                "trim": "GX",
            },
            impact_hint="front_left",
        )
    )

    request = FakeAsyncClient.last_request
    assert request is not None
    assert request["url"].endswith("/responses")
    assert request["json"]["store"] is False
    content = request["json"]["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert request["json"]["text"]["format"]["strict"] is True
    assert result.detections[0].part_name == "front bumper cover"
    assert result.detections[0].bounding_box.x2 == 0.8
