from pydantic import Field

from app.api_models import APIModel


class VendorView(APIModel):
    code: str
    display_name: str
    adapter_type: str
    product: str
    enabled: bool
    config: dict


class VendorUpdate(APIModel):
    enabled: bool


class VendorList(APIModel):
    vendors: list[VendorView] = Field(default_factory=list)
