import json
from datetime import UTC, datetime

from app.modules.travel.adapters.types import FlightSearch, NormalizedOffer
from app.modules.travel.money import to_minor

_CABIN_TO_BENZY = {
    "economy": "E",
    "premium_economy": "PE",
    "premium": "PE",
    "business": "B",
    "first": "F",
    "e": "E",
    "pe": "PE",
    "b": "B",
    "f": "F",
}


def cabin_code(value: str) -> str:
    key = value.strip().lower().replace(" ", "_")
    if key not in _CABIN_TO_BENZY:
        allowed = "economy, premium_economy, business, first"
        raise ValueError(f"cabin must be one of {allowed}")
    return _CABIN_TO_BENZY[key]


def is_completed(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.lower() in {"true", "completed"}:
        return True
    return False


def is_ok(payload: dict) -> bool:
    code = payload.get("Code", payload.get("code"))
    if code is None:
        return True
    return str(code) == "200"


def upstream_message(payload: dict) -> str:
    msg = payload.get("Msg") or payload.get("msg") or payload.get("Message")
    if isinstance(msg, list):
        return "; ".join(str(item) for item in msg) or "Upstream request failed"
    if msg:
        return str(msg)
    return "Upstream request failed"


def parse_supplier_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def offers_from_search(payload: dict, query: FlightSearch) -> list[NormalizedOffer]:
    currency = str(payload.get("CurrencyCode") or payload.get("currencyCode") or "INR")
    search_tui = str(payload.get("TUI") or "")
    offers: list[NormalizedOffer] = []
    for trip in payload.get("Trips") or []:
        for journey in trip.get("Journey") or []:
            net = journey.get("NetFare")
            if net is None:
                net = journey.get("GrossFare") or 0
            index = str(journey.get("Index") or "")
            ref = json.dumps(
                {
                    "index": index,
                    "orderId": 1,
                    "netFare": net,
                    "searchTui": search_tui,
                },
                separators=(",", ":"),
                default=str,
            )
            airline = str(journey.get("VAC") or journey.get("MAC") or "").strip()
            flight_no = str(journey.get("FlightNo") or "").strip()
            offers.append(
                NormalizedOffer(
                    supplier_offer_ref=ref,
                    origin=str(journey.get("From") or query.origin),
                    destination=str(journey.get("To") or query.destination),
                    depart_at=parse_supplier_time(journey.get("DepartureTime")),
                    arrive_at=parse_supplier_time(journey.get("ArrivalTime")),
                    airline_code=airline,
                    flight_number=flight_no,
                    stops=int(journey.get("Stops") or 0),
                    cabin=query.cabin,
                    amount_minor=to_minor(net, currency),
                    currency=currency.upper(),
                    raw=journey,
                )
            )
    return offers


def load_offer_ref(raw: str) -> dict:
    return json.loads(raw)


def age_years(date_of_birth: str, today: datetime | None = None) -> int:
    born = datetime.fromisoformat(date_of_birth).date()
    current = (today or datetime.now(UTC)).date()
    years = current.year - born.year
    if (current.month, current.day) < (born.month, born.day):
        years -= 1
    return max(years, 0)


def first_pnr(payload: dict) -> str | None:
    found = _find_key(payload, "CRSPNR") or _find_key(payload, "APNR")
    if found:
        return str(found).strip() or None
    return None


def _find_key(value, key: str):
    if isinstance(value, dict):
        if value.get(key):
            return value[key]
        for item in value.values():
            found = _find_key(item, key)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_key(item, key)
            if found:
                return found
    return None


def cancel_trips(retrieve: dict) -> list[dict]:
    trips_out: list[dict] = []
    for trip in retrieve.get("Trips") or []:
        journeys_out = []
        for journey in trip.get("Journey") or []:
            segments_out = []
            for segment in journey.get("Segments") or []:
                flight = segment.get("Flight") or {}
                pnr = segment.get("CRSPNR") or flight.get("CRSPNR") or ""
                pax_rows = segment.get("Pax") or flight.get("Pax") or []
                pax = [
                    {"ID": row.get("ID"), "Ticket": row.get("Ticket") or ""}
                    for row in pax_rows
                    if isinstance(row, dict) and row.get("ID") is not None
                ]
                if pnr or pax:
                    segments_out.append({"CRSPNR": pnr, "Pax": pax})
            if segments_out:
                journeys_out.append({"Segments": segments_out})
        if journeys_out:
            trips_out.append({"Journey": journeys_out})
    return trips_out
