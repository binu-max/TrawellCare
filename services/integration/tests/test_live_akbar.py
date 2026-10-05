import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LIVE_AKBAR") != "1", reason="set RUN_LIVE_AKBAR=1 to call Akbar")


async def test_live_signature_and_search(api):
    client, _app = api
    case_id = str(uuid.uuid4())
    created = await client.post(
        f"/v1/cases/{case_id}/travel-requests",
        json={
            "vendorCode": "akbar",
            "search": {
                "origin": "BOM",
                "destination": "DEL",
                "departDate": "2026-12-15",
                "adults": 1,
                "cabin": "economy",
            },
        },
    )
    assert created.status_code == 201
    searched = await client.post(f"/v1/travel-requests/{created.json()['id']}/search")
    assert searched.status_code == 200
    assert "options" in searched.json()
