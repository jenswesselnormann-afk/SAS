from __future__ import annotations
from datetime import date, datetime, timedelta
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from services.airports import airport_label
from services.gateways import expand_origins

LOG = logging.getLogger(__name__)

SAS_BASE_URL = os.environ.get("SAS_AWARD_BASE_URL", "https://future.flysas.com").rstrip("/")
SAS_MARKET = os.environ.get("SAS_AWARD_MARKET", "no-no")
HTTP_TIMEOUT_SECONDS = float(os.environ.get("SAS_AWARD_TIMEOUT_SECONDS", "15"))
MAX_MONTHS = int(os.environ.get("SAS_AWARD_MAX_MONTHS", "12"))

CABIN_TO_CODE = {
    "Economy": "AG",
    "Premium": "AP",
    "Business": "AB",
}
CODE_TO_CABIN = {
    "AG": "Economy",
    "AP": "Premium",
    "AB": "Business",
}
ORDERED_CABIN_CODES = ("AB", "AP", "AG")


def find_results(
    provider: str,
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
    cabin: str,
    passengers: int,
    direct_only: bool,
    include_nearby: bool = False,
    mode: str = "route_search",
) -> List[Dict[str, Any]]:
    mode = mode if mode in {"route_search", "any_routes", "most_hits"} else "route_search"
    requested_origin = _iata(origin)
    requested_destination = _iata(destination)
    passengers = max(1, int(passengers or 1))
    requested_cabin = (cabin or "Any").strip()
    checked_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    if provider == "SkyTeam":
        return []

    origins = _resolve_origins(requested_origin, include_nearby)
    if not origins:
        return []

    broad_mode = mode in {"any_routes", "most_hits"}
    if not broad_mode and not requested_destination:
        return []

    start, end = _date_bounds(start_date, end_date)
    month_tokens = _month_tokens(start, end)
    out: List[Dict[str, Any]] = []

    for search_origin in origins:
        for month in month_tokens:
            try:
                destinations_payload = _fetch_destinations(
                    market=SAS_MARKET,
                    origin=search_origin,
                    destinations=[requested_destination] if requested_destination else [],
                    selected_month=month,
                    passengers=passengers,
                    direct=bool(direct_only),
                )
            except Exception as exc:
                LOG.warning("SAS destinations request failed for %s/%s: %s", search_origin, month, exc)
                continue

            for destination_row in destinations_payload:
                airport_code = _iata(destination_row.get("airportCode", ""))
                city_code = _iata(destination_row.get("cityCode", ""))
                if requested_destination and airport_code != requested_destination and city_code != requested_destination:
                    continue
                availability = destination_row.get("availability", {}) or {}
                for day in availability.get("outbound", []) or []:
                    flight_date = day.get("date", "")
                    if not _in_date_window(flight_date, start, end):
                        continue
                    chosen = _pick_cabin_and_seats(day, requested_cabin, passengers)
                    if not chosen:
                        continue
                    chosen_code, seats = chosen
                    out.append(
                        _build_row(
                            requested_origin=requested_origin,
                            actual_origin=search_origin,
                            destination_airport=airport_code,
                            flight_date=flight_date,
                            cabin_code=chosen_code,
                            seats=seats,
                            passengers=passengers,
                            direct_filter=bool(direct_only),
                            checked_at=checked_at,
                            city_name=destination_row.get("cityName", ""),
                            airport_name=destination_row.get("airportName", ""),
                        )
                    )

    rows = _dedupe_rows(out)
    if mode == "most_hits":
        rows.sort(key=lambda row: (row["date"], -row.get("seats", 0), row.get("destination", "")))
    else:
        rows.sort(key=lambda row: (row["date"], row.get("destination", ""), -row.get("seats", 0)))
    return rows[:600]


def build_calendar(results: List[Dict[str, Any]]):
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        if result.get("source_type") != "live":
            continue
        grouped.setdefault(result["date"], []).append(result)

    calendar = []
    for day in sorted(grouped):
        rows = grouped[day]
        best = sorted(rows, key=lambda row: (-row.get("seats", 0), row.get("destination", "")))[0]
        calendar.append(
            {
                "date": best["date"],
                "points": None,
                "cabin": best["cabin"],
                "seats": best.get("seats", 0),
                "direct": best.get("direct"),
                "book_url": best["book_url"],
                "origin": best["origin"],
                "destination": best["destination"],
                "origin_label": best["origin_label"],
                "destination_label": best["destination_label"],
                "requested_origin": best.get("requested_origin", best["origin"]),
                "hit_count": len(rows),
                "best_score": None,
                "source_type": best.get("source_type"),
                "source_name": best.get("source_name"),
                "checked_at": best.get("checked_at"),
                "verification_level": best.get("verification_level"),
            }
        )
    return calendar


def build_value_feed(all_rows: List[Dict[str, Any]]):
    return []


def source_summary_for(provider: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    provider = provider if provider in {"SAS", "SkyTeam", "Both"} else "SAS"
    has_live = any(row.get("source_type") == "live" for row in results)
    notices: List[str] = []
    if provider in {"SkyTeam", "Both"}:
        notices.append("SkyTeam/partner-data er ikke live-integrert i denne versjonen og er derfor deaktivert.")
    if provider == "SkyTeam":
        notices.append("Velg SAS for verifiserte live-resultater.")
    if provider in {"SAS", "Both"} and not has_live:
        notices.append("Ingen live SAS-tilgjengelighet funnet i valgt intervall.")
    return {
        "provider": provider,
        "has_live": has_live,
        "notices": notices,
    }


def _fetch_destinations(
    market: str,
    origin: str,
    destinations: List[str],
    selected_month: str,
    passengers: int,
    direct: bool,
) -> List[Dict[str, Any]]:
    params = {
        "market": market,
        "origin": origin,
        "destinations": ",".join([code for code in destinations if code]),
        "selectedMonth": selected_month,
        "passengers": str(max(1, int(passengers))),
        "direct": str(bool(direct)).lower(),
        "availability": "true",
    }
    return _request_json("/bff/award-finder/destinations/v1", params)


def _request_json(path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    url = f"{SAS_BASE_URL}{path}"
    last_error: Optional[Exception] = None
    for _ in range(2):
        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
            if response.status_code == 429:
                raise RuntimeError("SAS endpoint rate limited request (429)")
            if response.status_code >= 500:
                raise RuntimeError(f"SAS endpoint returned {response.status_code}")
            if response.status_code != 200:
                return []
            payload = response.json()
            if isinstance(payload, list):
                return payload
            return []
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def _resolve_origins(requested_origin: str, include_nearby: bool) -> List[str]:
    if not requested_origin:
        return []
    if not include_nearby:
        return [requested_origin]
    out = []
    for origin in expand_origins(requested_origin, True):
        code = _iata(origin)
        if code and code not in out:
            out.append(code)
    return out or [requested_origin]


def _date_bounds(start_date: str, end_date: str) -> Tuple[date, date]:
    today = date.today()
    start = date.fromisoformat(start_date) if start_date else today
    end = date.fromisoformat(end_date) if end_date else min(start + timedelta(days=90), today + timedelta(days=365))
    if end < start:
        end = start
    max_end = today + timedelta(days=365)
    if end > max_end:
        end = max_end
    return start, end


def _month_tokens(start: date, end: date) -> List[str]:
    months: List[str] = []
    cur = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cur <= last and len(months) < MAX_MONTHS:
        months.append(f"{cur.year}{cur.month:02d}")
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return months


def _in_date_window(raw_date: str, start: date, end: date) -> bool:
    try:
        parsed = date.fromisoformat(raw_date)
        return start <= parsed <= end
    except ValueError:
        return False


def _pick_cabin_and_seats(day: Dict[str, Any], requested_cabin: str, passengers: int) -> Optional[Tuple[str, int]]:
    if requested_cabin == "First":
        return None
    if requested_cabin in CABIN_TO_CODE:
        code = CABIN_TO_CODE[requested_cabin]
        seats = int(day.get(code) or 0)
        if seats >= passengers:
            return code, seats
        return None

    for code in ORDERED_CABIN_CODES:
        seats = int(day.get(code) or 0)
        if seats >= passengers:
            return code, seats
    return None


def _build_row(
    requested_origin: str,
    actual_origin: str,
    destination_airport: str,
    flight_date: str,
    cabin_code: str,
    seats: int,
    passengers: int,
    direct_filter: bool,
    checked_at: str,
    city_name: str,
    airport_name: str,
) -> Dict[str, Any]:
    destination_label = airport_label(destination_airport)
    if city_name and airport_name and destination_airport:
        destination_label = f"{city_name} ({destination_airport})"

    book_url = _book_url(actual_origin, destination_airport, flight_date, passengers, direct_filter)
    return {
        "provider": "SAS",
        "carrier": "SAS",
        "origin": actual_origin,
        "destination": destination_airport,
        "origin_label": airport_label(actual_origin),
        "destination_label": destination_label,
        "date": flight_date,
        "cabin": CODE_TO_CABIN.get(cabin_code, "Economy"),
        "seats": int(seats),
        "points": None,
        "taxes": None,
        "direct": True if direct_filter else None,
        "duration_minutes": None,
        "segments": [],
        "score": None,
        "calendar_price": None,
        "find_url": _find_url(actual_origin, destination_airport, flight_date),
        "book_url": book_url,
        "info_url": "https://www.flysas.com/en/eurobonus/points/fly-with-points/point-chart",
        "booking_note": "Resultatet er hentet live fra SAS Award Finder beta-endepunkt.",
        "requested_origin": requested_origin or actual_origin,
        "reposition_required": bool(requested_origin and actual_origin != requested_origin),
        "reposition_note": _reposition_note(requested_origin, actual_origin),
        "source_type": "live",
        "source_name": "SAS Award Finder BFF",
        "checked_at": checked_at,
        "verification_level": "live_api",
    }


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for row in rows:
        key = (row["provider"], row["date"], row["origin"], row["destination"])
        existing = unique.get(key)
        if not existing or row.get("seats", 0) > existing.get("seats", 0):
            unique[key] = row
    return list(unique.values())


def _find_url(origin: str, destination: str, flight_date: str) -> str:
    month = flight_date[:7].replace("-", "")
    return (
        f"{SAS_BASE_URL}/{SAS_MARKET}/award-finder"
        f"?origin={origin}&destination={destination}&month={month}"
    )


def _book_url(origin: str, destination: str, flight_date: str, passengers: int, direct_only: bool) -> str:
    return (
        f"{SAS_BASE_URL}/{SAS_MARKET}/book-new/revenue/flights"
        f"?origin={origin}&destination={destination}&adults={max(1, int(passengers))}&payWithPoints=&direct={str(direct_only).lower()}"
        f"&outboundDate={flight_date}&tripType=one-way"
    )


def _reposition_note(requested_origin: str, actual_origin: str):
    if not requested_origin or requested_origin == actual_origin:
        return ""
    return f"Starter fra {actual_origin}. Vurder posisjoneringsfly fra {requested_origin}."


def _iata(raw: str) -> str:
    text = (raw or "").strip().upper()
    match = re.search(r"\b([A-Z]{3})\b", text)
    return match.group(1) if match else text
