from app.modules.travel.adapters.normalize import is_completed, offers_from_search
from app.modules.travel.adapters.types import FlightSearch
from app.modules.travel.money import to_minor
from app.modules.travel.redact import redact


def test_money_uses_currency_exponent():
    assert to_minor("15000.50", "INR") == 1500050
    assert to_minor("1.234", "OMR") == 1234
    assert to_minor(10, "JPY") == 10


def test_redact_hides_signature_secrets():
    cleaned = redact({"ApiKey": "secret", "Password": "staging", "Key": "abc", "From": "MCT"})
    assert cleaned["ApiKey"] == "***"
    assert cleaned["Password"] == "***"
    assert cleaned["Key"] == "***"
    assert cleaned["From"] == "MCT"


def test_search_completion_flags():
    assert is_completed("True")
    assert is_completed("Completed")
    assert is_completed(True)
    assert not is_completed("False")
    assert not is_completed(False)


def test_offers_from_express_search_sample():
    payload = {
        "TUI": "search-tui",
        "Completed": "True",
        "CurrencyCode": "INR",
        "Trips": [
            {
                "Journey": [
                    {
                        "Index": "6E|1",
                        "Stops": 0,
                        "FlightNo": " 123",
                        "VAC": "6E",
                        "DepartureTime": "2026-11-15T10:00:00",
                        "ArrivalTime": "2026-11-15T14:00:00",
                        "From": "MCT",
                        "To": "COK",
                        "NetFare": 15000.5,
                    }
                ]
            }
        ],
    }
    offers = offers_from_search(
        payload,
        FlightSearch(origin="MCT", destination="COK", depart_date="2026-11-15", cabin="E"),
    )
    assert len(offers) == 1
    assert offers[0].airline_code == "6E"
    assert offers[0].flight_number == "123"
    assert offers[0].amount_minor == 1500050
    assert "6E|1" in offers[0].supplier_offer_ref
