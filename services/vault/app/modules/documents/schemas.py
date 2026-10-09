from uuid import UUID

from pydantic import Field

from app.api_models import APIModel


class UploadInitBody(APIModel):
    classification: str
    filename: str
    content_type: str = Field(alias="contentType")
    byte_size: int = Field(alias="byteSize")
    requirement_id: UUID | None = Field(default=None, alias="requirementId")
    case_party_id: UUID | None = Field(default=None, alias="casePartyId")
    residency: str = "ae"


class UploadInitResponse(APIModel):
    document_id: UUID = Field(alias="documentId")
    upload_url: str = Field(alias="uploadUrl")
    upload_method: str = Field(default="PUT", alias="uploadMethod")
    upload_token: str = Field(alias="uploadToken")
    expires_at: str = Field(alias="expiresAt")


class CompleteBody(APIModel):
    byte_size: int | None = Field(default=None, alias="byteSize")
    checksum_sha256: str | None = Field(default=None, alias="checksumSha256")


class CompleteResponse(APIModel):
    document_id: UUID = Field(alias="documentId")
    upload_status: str = Field(alias="uploadStatus")
    scan_status: str = Field(alias="scanStatus")


class UrlResponse(APIModel):
    url: str
    expires_at: str = Field(alias="expiresAt")


class DocumentListItem(APIModel):
    document_id: UUID = Field(alias="documentId")
    classification: str
    filename: str
    upload_status: str = Field(alias="uploadStatus")
    scan_status: str = Field(alias="scanStatus")
    case_party_id: UUID | None = Field(default=None, alias="casePartyId")
    visible_to_customer: bool | None = Field(default=None, alias="visibleToCustomer")
