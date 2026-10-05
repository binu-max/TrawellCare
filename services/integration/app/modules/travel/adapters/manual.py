from tc_common import RuleFailed

from app.modules.travel.adapters.types import (
    BookResult,
    Contact,
    FlightSearch,
    NormalizedOffer,
    Passenger,
    PollResult,
    PricedOffer,
)


class ManualTravelAdapter:
    code = "manual"

    async def search(self, query: FlightSearch, *, request_id) -> list[NormalizedOffer]:
        raise RuleFailed(
            "The manual vendor does not search live inventory. Add an option instead.",
            code="MANUAL_VENDOR",
        )

    async def price(self, offer_ref: str, session_state: dict, *, request_id) -> PricedOffer:
        raise RuleFailed(
            "Manual options keep the amount you entered. Confirm with a supplier reference.",
            code="MANUAL_VENDOR",
        )

    async def book(
        self,
        *,
        offer_ref: str,
        session_state: dict,
        contact: Contact,
        passengers: list[Passenger],
        request_id,
    ) -> BookResult:
        raise RuleFailed(
            "Pass supplierReference to confirm a manual booking.",
            code="SUPPLIER_REFERENCE_REQUIRED",
        )

    async def poll(self, session_state: dict, *, request_id) -> PollResult:
        raise RuleFailed("Manual bookings are not polled.", code="MANUAL_VENDOR")

    async def cancel(self, session_state: dict, *, remarks: str, request_id) -> dict:
        raise RuleFailed(
            "Record the supplier cancellation outside this adapter, then store the reference.",
            code="MANUAL_VENDOR",
        )
