from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from app.deps import (
    AuthHeaderDep,
    KeyDep,
    SessionDep,
    SettingsDep,
    StorageDep,
    UserDep,
    client_ip,
    get_http,
)
from app.http import command, dump
from app.modules.documents import service
from app.modules.documents.schemas import CompleteBody, UploadInitBody

router = APIRouter(tags=["documents"])


@router.post("/v1/cases/{case_id}/documents/uploads", status_code=201)
async def upload_init(
    case_id: UUID,
    body: UploadInitBody,
    actor: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    request: Request,
    key: KeyDep,
    authorization: AuthHeaderDep,
):
    http = get_http(request)

    async def run():
        return await service.initiate_upload(
            session,
            settings,
            storage,
            http,
            actor,
            case_id,
            body,
            authorization,
        )

    return await command(session, actor, key, body.model_dump(mode="json"), 201, run)


@router.put("/v1/documents/{document_id}/upload")
async def upload_bytes(
    document_id: UUID,
    token: str,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    request: Request,
):
    data = await request.body()
    content_type = request.headers.get("content-type")
    await service.put_upload_bytes(session, settings, storage, document_id, token, data, content_type)
    return {"status": "stored", "byteSize": len(data)}


@router.post("/v1/documents/{document_id}/complete")
async def complete(
    document_id: UUID,
    body: CompleteBody,
    actor: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    key: KeyDep,
):
    return await command(
        session,
        actor,
        key,
        body.model_dump(mode="json"),
        200,
        lambda: service.complete_upload(session, settings, storage, actor, document_id, body),
    )


@router.get("/v1/documents/{document_id}/url")
async def url(
    document_id: UUID,
    actor: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
):
    correlation = request.headers.get("x-correlation-id")
    return dump(
        await service.document_url(
            session,
            settings,
            actor,
            document_id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            correlation_id=correlation,
        )
    )


@router.get("/v1/documents/{document_id}/download")
async def download(
    document_id: UUID,
    token: str,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
):
    row, data = await service.download_bytes(session, settings, storage, document_id, token)
    return Response(
        content=data,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.get("/v1/cases/{case_id}/documents")
async def list_documents(
    case_id: UUID,
    actor: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    authorization: AuthHeaderDep,
    audience: str = Query(default="customer"),
):
    http = get_http(request)
    return dump(
        await service.list_case_documents(
            session,
            settings,
            http,
            actor,
            case_id,
            audience=audience,
            authorization=authorization,
        )
    )
