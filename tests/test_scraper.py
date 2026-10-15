import json
from pathlib import Path

from snap_watch.scraper import cart_request, newly_opened, page_props, parse_search_page

FIXTURES = Path(__file__).parent / "fixtures"


def page(name: str) -> str:
    return f'<html><script id="__NEXT_DATA__" type="application/json">{(FIXTURES / name).read_text()}</script></html>'


def test_parse_bookable_page_returns_windows_with_price_and_seats():
    result = parse_search_page(page("bookable.json"), "2026-10-17")
    assert result == {"status": "available", "windows": [
        {"start": "07:04", "end": "13:00", "price": 55, "seats": 9, "trains": ["9114 08:16-11:13"]},
        {"start": "13:00", "end": "19:34", "price": 55, "seats": 11, "trains": ["9158 19:34-22:35"]},
    ]}


def test_parse_sold_out_page_returns_nothing():
    assert parse_search_page(page("empty.json"), "2026-10-19") == {"status": "nothing"}


def test_parse_page_for_other_date_is_could_not_check_not_nothing():
    assert parse_search_page(page("empty.json"), "2026-10-18")["status"] == "could_not_check"


def test_parse_challenge_page_is_could_not_check():
    assert parse_search_page("<html>Forbidden</html>", "2026-10-18")["status"] == "could_not_check"


def test_newly_opened_flags_only_dates_that_became_bookable():
    previous = {"a": {"status": "nothing"}, "b": {"status": "available"}, "c": {"status": "could_not_check"}}
    current = {"a": {"status": "available"}, "b": {"status": "available"}, "c": {"status": "available"}, "d": {"status": "nothing"}}
    assert newly_opened(previous, current) == ["a", "c"]


def test_cart_request_uses_selected_window_fare_and_bounds():
    body = cart_request(page_props(page("bookable.json")), "13:00", 1)
    assert body["selectedOutboundFare"]["seats"] == 11
    assert body["snap"] == {"outbound": {"earliestTime": "2026-10-17 13:00", "latestTime": "2026-10-17 19:34"}}


def test_cart_request_for_sold_out_window_is_none():
    assert cart_request(page_props(page("empty.json")), "07:02", 1) is None
