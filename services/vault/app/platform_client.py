from uuid import UUID

import httpx
from tc_common import Forbidden, NotFound, UpstreamUnavailable


async def fetch_case_customer_id(
    client: httpx.AsyncClient,
    *,
    platform_base_url: str,
    case_id: UUID,
    authorization: str,
) -> UUID:
    url = f"{platform_base_url.rstrip('/')}/v1/cases/{case_id}"
    try:
        response = await client.get(url, headers={"Authorization": authorization})
    except httpx.HTTPError as exc:
        raise UpstreamUnavailable("Platform is unavailable") from exc
    if response.status_code == 404:
        raise NotFound("Case not found")
    if response.status_code == 403:
        raise Forbidden("Case access denied")
    if response.status_code >= 400:
        raise UpstreamUnavailable(f"Platform returned {response.status_code}")
    body = response.json()
    raw = body.get("customerId") or body.get("customer_id")
    if not raw:
        raise UpstreamUnavailable("Platform case response missing customerId")
    return UUID(str(raw))
