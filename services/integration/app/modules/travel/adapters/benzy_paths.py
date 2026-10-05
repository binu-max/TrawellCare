"""Benzy B2B Revamp flight paths.

Locked from the June 2025 Postman collection
`B2B Revamp Flight API - Test` and the Web Connect Resource Center flight pages.
Casing matches the collection. ASP.NET accepts either case; we send the tested path.
"""

SIGNATURE = "/Utils/Signature"
EXPRESS_SEARCH = "/flights/ExpressSearch"
GET_EXP_SEARCH = "/flights/GetExpSearch"
SMART_PRICER = "/Flights/SmartPricer"
GET_SPRICER = "/Flights/GetSPricer"
CREATE_ITINERARY = "/Flights/CreateItinerary"
START_PAY = "/Payment/StartPay"
ITINERARY_STATUS = "/Payment/GetItineraryStatus"
RETRIEVE_BOOKING = "/Utils/RetrieveBooking"
CANCEL = "/Flights/Cancel"
