import uuid

import pytest

from conftest import auth_headers, customer_token, finance_token


@pytest.mark.asyncio
async def test_health(api):
    client, _ = api
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upload_complete_and_download(api):
    client, _ = api
    case_id = uuid.uuid4()
    token = customer_token()
    init = await client.post(
        f"/v1/cases/{case_id}/documents/uploads",
        headers=auth_headers(token),
        json={
            "classification": "passport",
            "filename": "passport.pdf",
            "contentType": "application/pdf",
            "byteSize": 12,
        },
    )
    assert init.status_code == 201, init.text
    body = init.json()
    document_id = body["documentId"]
    assert body.get("uploadToken")
    put = await client.put(
        f"/v1/documents/{document_id}/upload",
        params={"token": body["uploadToken"]},
        content=b"hello vault",
        headers={"Content-Type": "application/pdf"},
    )
    assert put.status_code == 200

    complete = await client.post(
        f"/v1/documents/{document_id}/complete",
        headers=auth_headers(token),
        json={"byteSize": 11},
    )
    assert complete.status_code == 200
    assert complete.json()["scanStatus"] == "clean"

    url = await client.get(
        f"/v1/documents/{document_id}/url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert url.status_code == 200
    download_path = url.json()["url"].replace("http://test", "")
    file_response = await client.get(download_path)
    assert file_response.status_code == 200
    assert file_response.content == b"hello vault"

    listed = await client.get(
        f"/v1/cases/{case_id}/documents?audience=customer",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_finance_denied(api):
    client, _ = api
    response = await client.post(
        f"/v1/cases/{uuid.uuid4()}/documents/uploads",
        headers=auth_headers(finance_token()),
        json={
            "classification": "passport",
            "filename": "passport.pdf",
            "contentType": "application/pdf",
            "byteSize": 12,
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_wrong_customer_list_hidden(api):
    client, _ = api
    case_id = uuid.uuid4()
    owner = customer_token()
    other = customer_token(uuid.uuid4())

    init = await client.post(
        f"/v1/cases/{case_id}/documents/uploads",
        headers=auth_headers(owner),
        json={
            "classification": "visa",
            "filename": "visa.pdf",
            "contentType": "application/pdf",
            "byteSize": 4,
        },
    )
    assert init.status_code == 201
    doc = init.json()
    await client.put(
        f"/v1/documents/{doc['documentId']}/upload",
        params={"token": doc["uploadToken"]},
        content=b"visa",
        headers={"Content-Type": "application/pdf"},
    )
    document_id = init.json()["documentId"]
    await client.post(
        f"/v1/documents/{document_id}/complete",
        headers=auth_headers(owner),
        json={"byteSize": 4},
    )

    listed = await client.get(
        f"/v1/cases/{case_id}/documents?audience=customer",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert listed.status_code == 200
    assert listed.json() == []
