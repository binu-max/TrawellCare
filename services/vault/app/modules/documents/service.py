import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tc_common import Forbidden, NotFound, RuleFailed, ValidationFailed
from tc_common.jwt import TokenActor

from app.modules.documents.models import Document, DocumentAccessLog
from app.modules.documents.policy import (
    assert_classification,
    assert_content_type,
    assert_customer_case,
    assert_not_finance,
    assert_staff,
    can_view_document,
)
from app.modules.documents.schemas import (
    CompleteBody,
    CompleteResponse,
    DocumentListItem,
    UploadInitBody,
    UploadInitResponse,
    UrlResponse,
)
from app.platform_client import fetch_case_customer_id
from app.settings import Settings
from app.signing import issue_download_token, issue_upload_token, verify_download_token, verify_upload_token
from app.storage.local import LocalFilesystemStorage


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_case_customer(
    settings: Settings,
    http: httpx.AsyncClient,
    actor: TokenActor,
    *,
    case_id: UUID,
    authorization: str,
) -> UUID:
    if not settings.platform_case_check_enabled:
        if actor.kind == "customer" and actor.customer_id is not None:
            return actor.customer_id
        raise ValidationFailed("Platform case check is disabled for staff requests")
    return await fetch_case_customer_id(
        http,
        platform_base_url=settings.platform_base_url,
        case_id=case_id,
        authorization=authorization,
    )


async def initiate_upload(
    session: AsyncSession,
    settings: Settings,
    storage: LocalFilesystemStorage,
    http: httpx.AsyncClient,
    actor: TokenActor,
    case_id: UUID,
    body: UploadInitBody,
    authorization: str,
) -> UploadInitResponse:
    assert_not_finance(actor)
    assert_classification(body.classification)
    assert_content_type(body.content_type)
    if body.byte_size <= 0 or body.byte_size > settings.vault_max_upload_bytes:
        raise ValidationFailed("File size is out of range")

    case_customer_id = await _resolve_case_customer(
        settings, http, actor, case_id=case_id, authorization=authorization
    )
    if actor.kind == "customer":
        assert_customer_case(actor, case_customer_id)
    elif actor.kind != "staff":
        raise Forbidden("Invalid token")

    row = Document(
        case_id=case_id,
        customer_id=case_customer_id,
        case_party_id=body.case_party_id,
        requirement_id=body.requirement_id,
        classification=body.classification,
        filename=body.filename,
        content_type=body.content_type,
        byte_size=None,
        object_key="pending",
        residency=body.residency,
        scan_status="pending",
        upload_status="initiated",
        uploaded_by_kind=actor.kind,
        uploaded_by_id=actor.id,
        visible_to_customer=actor.kind == "customer" or body.classification not in ("signoff_pdf",),
    )
    session.add(row)
    await session.flush()
    row.object_key = f"cases/{case_id}/{row.id}/{body.filename}"
    storage.reserve(row.object_key)

    token = issue_upload_token(
        settings.vault_service_api_key,
        row.id,
        ttl_seconds=settings.upload_token_ttl_seconds,
        max_bytes=settings.vault_max_upload_bytes,
    )
    expires = _now() + timedelta(seconds=settings.upload_token_ttl_seconds)
    upload_url = (
        f"{settings.vault_public_base_url.rstrip('/')}/v1/documents/{row.id}/upload"
        f"?token={token}"
    )
    return UploadInitResponse(
        document_id=row.id,
        upload_url=upload_url,
        upload_method="PUT",
        upload_token=token,
        expires_at=expires.isoformat(),
    )


async def put_upload_bytes(
    session: AsyncSession,
    settings: Settings,
    storage: LocalFilesystemStorage,
    document_id: UUID,
    token: str,
    data: bytes,
    content_type: str | None,
) -> None:
    row = await session.get(Document, document_id)
    if row is None:
        raise NotFound("Document not found")
    if row.upload_status != "initiated":
        raise RuleFailed("Upload already completed", code="CONFLICT", status=409)
    try:
        verify_upload_token(
            settings.vault_service_api_key,
            document_id,
            token,
            max_bytes=settings.vault_max_upload_bytes,
        )
    except ValueError as exc:
        raise Forbidden(str(exc), code="UPLOAD_EXPIRED") from exc
    if len(data) > settings.vault_max_upload_bytes:
        raise ValidationFailed("File exceeds maximum size")
    if content_type and content_type.split(";")[0].strip() != row.content_type:
        raise ValidationFailed("Content-Type does not match")
    storage.write_bytes(row.object_key, data)
    row.byte_size = len(data)


async def complete_upload(
    session: AsyncSession,
    settings: Settings,
    storage: LocalFilesystemStorage,
    actor: TokenActor,
    document_id: UUID,
    body: CompleteBody,
) -> CompleteResponse:
    row = await session.get(Document, document_id)
    if row is None:
        raise NotFound("Document not found")
    if row.uploaded_by_id != actor.id and actor.kind != "staff":
        raise Forbidden("Only the uploader can complete this upload")
    assert_not_finance(actor)
    can_view_document(actor, customer_id=row.customer_id, visible_to_customer=row.visible_to_customer)

    try:
        size = storage.size(row.object_key)
    except FileNotFoundError as exc:
        raise RuleFailed("Upload bytes missing", code="UPLOAD_INCOMPLETE", status=422) from exc

    if body.byte_size is not None and body.byte_size != size:
        raise ValidationFailed("byteSize does not match stored file")
    if body.checksum_sha256:
        digest = hashlib.sha256(storage.read_bytes(row.object_key)).hexdigest()
        if digest.lower() != body.checksum_sha256.lower():
            raise ValidationFailed("Checksum mismatch")

    row.byte_size = size
    row.upload_status = "completed"
    row.scan_status = "clean"
    return CompleteResponse(document_id=row.id, upload_status=row.upload_status, scan_status=row.scan_status)


async def document_url(
    session: AsyncSession,
    settings: Settings,
    actor: TokenActor,
    document_id: UUID,
    *,
    ip: str | None,
    user_agent: str | None,
    correlation_id: str | None,
) -> UrlResponse:
    row = await session.get(Document, document_id)
    if row is None:
        raise NotFound("Document not found")
    can_view_document(actor, customer_id=row.customer_id, visible_to_customer=row.visible_to_customer)
    if row.upload_status != "completed":
        raise RuleFailed("Upload is not complete", code="UPLOAD_INCOMPLETE", status=422)
    if row.scan_status == "quarantined":
        raise RuleFailed("Document is quarantined", code="DOCUMENT_QUARANTINED", status=403)
    if row.scan_status != "clean":
        raise RuleFailed("Scan is not complete", code="SCAN_PENDING", status=409)

    token = issue_download_token(
        settings.vault_service_api_key,
        row.id,
        ttl_seconds=settings.download_url_ttl_seconds,
    )
    expires = _now() + timedelta(seconds=settings.download_url_ttl_seconds)
    url = (
        f"{settings.vault_public_base_url.rstrip('/')}/v1/documents/{row.id}/download"
        f"?token={token}"
    )
    session.add(
        DocumentAccessLog(
            document_id=row.id,
            actor_kind=actor.kind,
            actor_id=actor.id,
            action="download",
            ip=ip,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
    )
    return UrlResponse(url=url, expires_at=expires.isoformat())


async def download_bytes(
    session: AsyncSession,
    settings: Settings,
    storage: LocalFilesystemStorage,
    document_id: UUID,
    token: str,
) -> tuple[Document, bytes]:
    row = await session.get(Document, document_id)
    if row is None:
        raise NotFound("Document not found")
    if row.scan_status != "clean" or row.upload_status != "completed":
        raise Forbidden("Document is not available")
    try:
        verify_download_token(settings.vault_service_api_key, document_id, token)
    except ValueError as exc:
        raise Forbidden(str(exc), code="UPLOAD_EXPIRED") from exc
    return row, storage.read_bytes(row.object_key)


async def list_case_documents(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    actor: TokenActor,
    case_id: UUID,
    *,
    audience: str,
    authorization: str,
) -> list[DocumentListItem]:
    assert_not_finance(actor)
    if audience not in ("customer", "staff"):
        raise ValidationFailed("audience must be customer or staff")
    if audience == "customer":
        if actor.kind != "customer" or actor.customer_id is None:
            raise Forbidden("Customer token required")
    else:
        assert_staff(actor)

    case_customer_id = await _resolve_case_customer(
        settings, http, actor, case_id=case_id, authorization=authorization
    )
    if actor.kind == "customer":
        assert_customer_case(actor, case_customer_id)

    rows = list(await session.scalars(select(Document).where(Document.case_id == case_id)))
    items: list[DocumentListItem] = []
    for row in rows:
        if audience == "customer":
            if not row.visible_to_customer or row.customer_id != actor.customer_id:
                continue
        items.append(
            DocumentListItem(
                document_id=row.id,
                classification=row.classification,
                filename=row.filename,
                upload_status=row.upload_status,
                scan_status=row.scan_status,
                case_party_id=row.case_party_id if audience == "staff" else None,
                visible_to_customer=row.visible_to_customer if audience == "staff" else None,
            )
        )
    return items
