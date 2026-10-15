"""Check Eurostar Snap availability from the page's server-rendered __NEXT_DATA__.

Plain HTTP clients get a 403 from AWS WAF; curl_cffi impersonating Chrome's TLS
fingerprint gets the full page, and the server honours the `outbound` date.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from curl_cffi import requests

logger = logging.getLogger(__name__)

CART_URL = "https://snap.eurostar.com/api/createCart"
SEARCH_URL = "https://snap.eurostar.com/uk-en/search?adult={adult}&origin={origin}&destination={destination}&outbound={date}"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def search_url(origin: str, destination: str, date: str, adult: int = 1, slot: Optional[str] = None) -> str:
    url = SEARCH_URL.format(adult=adult, origin=origin, destination=destination, date=date)
    return f"{url}&outslot={slot}" if slot else url


def page_props(html: str) -> Optional[Dict]:
    match = NEXT_DATA_RE.search(html)
    return json.loads(match.group(1))["props"]["pageProps"] if match else None


def parse_search_page(html: str, date: str) -> Dict:
    """Turn a search page into {"status": available|nothing|could_not_check, "windows": [...]}."""
    props = page_props(html)
    if props is None:
        return {"status": "could_not_check", "reason": "no __NEXT_DATA__ (bot challenge?)"}
    rendered = (props.get("searchValues") or {}).get("outbound")
    if rendered != date:
        return {"status": "could_not_check", "reason": f"page rendered {rendered}"}
    windows = [
        {
            "start": slot["departureWindow"]["earliest"][-5:],
            "end": slot["departureWindow"]["latest"][-5:],
            "price": slot["fare"]["prices"]["displayPrice"],
            "seats": slot["fare"]["seats"],
            "trains": [f'{leg["serviceName"]} {leg["timing"]["departureTime"]}-{leg["timing"]["arrivalTime"]}' for leg in slot["fare"]["legs"]],
        }
        for slot in props.get("outboundTimeSlots") or []
        if slot.get("fare")
    ]
    return {"status": "available", "windows": windows} if windows else {"status": "nothing"}


def check_date(session: requests.Session, origin: str, destination: str, date: str, adult: int) -> Dict:
    try:
        resp = session.get(search_url(origin, destination, date, adult), timeout=30)
    except requests.RequestsError as e:
        logger.warning("Request failed for %s: %s", date, e)
        return {"status": "could_not_check", "reason": str(e)}
    if resp.status_code != 200:
        return {"status": "could_not_check", "reason": f"HTTP {resp.status_code}"}
    return parse_search_page(resp.text, date)


def newly_opened(previous: Dict[str, Dict], current: Dict[str, Dict]) -> List[str]:
    """Dates that are bookable now but were not bookable last time."""
    return [
        date for date, state in current.items()
        if state["status"] == "available" and previous.get(date, {}).get("status") != "available"
    ]


def cart_request(props: Dict, start: str, adult: int) -> Optional[Dict]:
    """Body the Snap page POSTs to /api/createCart when Continue is clicked, for the window starting at `start`."""
    slot = next((x for x in props.get("outboundTimeSlots") or [] if x.get("fare") and x["id"].endswith(start)), None)
    if slot is None:
        return None
    return {
        "locale": "uk-en",
        "adults": adult,
        "selectedOutboundFare": slot["fare"],
        "snap": {"outbound": {"earliestTime": slot["departureWindow"]["earliest"], "latestTime": slot["departureWindow"]["latest"]}},
    }


def create_cart(session: requests.Session, origin: str, destination: str, date: str, adult: int, start: str) -> Optional[str]:
    """Put one ticket in a basket (same call as clicking Continue). Returns the checkout URL; never pays."""
    url = search_url(origin, destination, date, adult)
    props = page_props(session.get(url, timeout=30).text)
    body = cart_request(props, start, adult) if props else None
    if body is None:
        logger.warning("Window %s on %s gone before basket", start, date)
        return None
    resp = session.post(CART_URL, json=body, timeout=30, headers={"Accept": "application/json", "Origin": "https://snap.eurostar.com", "Referer": url})
    if resp.status_code != 200:
        logger.warning("createCart HTTP %s: %s", resp.status_code, resp.text[:200])
        return None
    return resp.json().get("url")
