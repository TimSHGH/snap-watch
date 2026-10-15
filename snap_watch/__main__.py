"""One poll: check each target date, compare to state.json, notify on new availability.

Usage: uv run python -m snap_watch [--config config.json] [--state state.json]
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from curl_cffi import requests
from dotenv import load_dotenv

from .scraper import check_date, create_cart, newly_opened, search_url

logger = logging.getLogger("snap_watch")
ROOT = Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")


def notify(title: str, message: str) -> None:
    """Mac notification + iMessage to ALERT_TO (macOS only), and ntfy.sh push to NTFY_TOPIC if set."""
    if sys.platform == "darwin":
        q = lambda text: json.dumps(text, ensure_ascii=False)
        subprocess.run(["osascript", "-e", f"display notification {q(message)} with title {q(title)} sound name \"Glass\""], check=False)
        to = os.environ.get("ALERT_TO")
        if to:
            script = f'tell application "Messages" to send {q(f"{title}: {message}")} to participant {q(to)} of (1st account whose service type = iMessage)'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            if result.returncode:
                logger.warning("iMessage failed: %s", result.stderr.strip())
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=message.encode(), headers={"Title": title, "Priority": "urgent", "Tags": "train"}, timeout=15)
        except requests.RequestsError as e:
            logger.warning("ntfy failed: %s", e)


def describe(date: str, state: dict) -> str:
    day = Date.fromisoformat(date).strftime("%a %d %b")
    if state["status"] != "available":
        return f"{day}: {state['status'].replace('_', ' ')}"
    windows = ", ".join(f"{w['start']} to {w['end']} £{w['price']} ({w['seats']} left, train {' + '.join(w['trains'])})" for w in state["windows"])
    return f"{day}: {windows}"


def line_up_ticket(session: requests.Session, cfg: dict, date: str, state: dict) -> bool:
    """Basket the cheapest window on `date` (if auto_cart) and open it in Chrome. Returns True if basketed."""
    cheapest = min(state["windows"], key=lambda w: (w["price"], w["start"]))
    url = search_url(cfg["origin"], cfg["destination"], date, cfg["adult"], cheapest["start"])
    cart_url = create_cart(session, cfg["origin"], cfg["destination"], date, cfg["adult"], cheapest["start"]) if cfg.get("auto_cart") else None
    logger.info("Opening %s", cart_url or url)
    if cfg.get("open_browser"):
        subprocess.run(["open", "-a", "Google Chrome", cart_url or url], check=False)
    return cart_url is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--state", type=Path, default=ROOT / "state.json")
    parser.add_argument("--test-alert", action="store_true", help="send a test alert and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv(ROOT / ".env")
    if args.test_alert:
        notify("Eurostar Snap: TEST", "alert test, nothing booked")
        return

    cfg = json.loads(args.config.read_text())
    previous = json.loads(args.state.read_text())["dates"] if args.state.exists() else {}
    session = requests.Session(impersonate="chrome")
    current = {d: check_date(session, cfg["origin"], cfg["destination"], d, cfg["adult"]) for d in cfg["dates"]}
    now = datetime.now(UK)

    # opened follows cfg["dates"], which is in preference order: basket them all first, then text
    opened = newly_opened(previous, current)
    basketed = {d: line_up_ticket(session, cfg, d, current[d]) for d in opened}
    for d in opened:
        logger.info("NEW: %s", describe(d, current[d]))
        status = "Basket open in Chrome, held ~30 min." if basketed[d] else "Not basketed, search page opened."
        notify("Eurostar Snap: NEW", f'{describe(d, current[d])}. {status} {search_url(cfg["origin"], cfg["destination"], d, cfg["adult"])}')

    if all(s["status"] == "could_not_check" for s in current.values()):
        logger.warning("%s: could not check any date: %s", now.strftime("%H:%M"), {d: s.get("reason") for d, s in current.items()})
    else:
        headline = "changed" if opened else "no change"
        logger.info("%s: %s | %s", now.strftime("%H:%M"), headline, " | ".join(describe(d, s) for d, s in current.items()))

    # a failed check says nothing about availability, so keep the last real result for that date
    saved = {d: previous[d] if s["status"] == "could_not_check" and d in previous else s for d, s in current.items()}
    args.state.write_text(json.dumps({"checked_at": now.isoformat(timespec="seconds"), "dates": saved}, indent=2))


if __name__ == "__main__":
    main()
