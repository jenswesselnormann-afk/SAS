from __future__ import annotations
from datetime import date, timedelta
from hashlib import sha256
from typing import List, Dict, Any
from services.airports import airport_label
from services.gateways import expand_origins

SAS_ROUTES = [
    ('OSL','EWR', True, 510), ('OSL','JFK', True, 500), ('CPH','JFK', True, 520), ('CPH','EWR', True, 510),
    ('ARN','EWR', True, 505), ('ARN','JFK', True, 500), ('OSL','NCE', True, 175), ('OSL','PMI', True, 205),
    ('OSL','TRD', True, 55), ('OSL','TOS', True, 110), ('BGO','OSL', True, 55), ('OSL','LHR', True, 135),
    ('OSL','BKK', False, 760), ('CPH','HND', True, 720), ('CPH','BKK', True, 680), ('ARN','BKK', False, 720),
    ('OSL','MIA', False, 640), ('OSL','LAX', False, 820), ('OSL','SFO', False, 810), ('OSL','HND', False, 810)
]
SKYTEAM_ROUTES = [
    ('OSL','NRT','KLM', False, 950, ['OSL-AMS', 'AMS-NRT']),
    ('OSL','ICN','Korean Air', False, 930, ['OSL-CDG', 'CDG-ICN']),
    ('OSL','JFK','Air France', False, 700, ['OSL-CDG', 'CDG-JFK']),
    ('OSL','ATL','Delta', False, 720, ['OSL-AMS', 'AMS-ATL']),
    ('OSL','LAX','Virgin Atlantic', False, 880, ['OSL-LHR', 'LHR-LAX']),
    ('OSL','CUN','KLM', False, 940, ['OSL-AMS', 'AMS-CUN']),
    ('OSL','GRU','Air France', False, 1040, ['OSL-CDG', 'CDG-GRU']),
    ('OSL','SCL','Delta', False, 1180, ['OSL-ATL', 'ATL-SCL']),
    ('ARN','NRT','KLM', False, 900, ['ARN-AMS', 'AMS-NRT']),
    ('CPH','JFK','Virgin Atlantic', False, 700, ['CPH-LHR', 'LHR-JFK']),
    ('LHR','HND','Virgin Atlantic', True, 880, ['LHR-HND']), ('AMS','NRT','KLM', True, 830, ['AMS-NRT']),
    ('CDG','HND','Air France', True, 860, ['CDG-HND']), ('FRA','ICN','Korean Air', True, 700, ['FRA-ICN']),
    ('AMS','JFK','KLM', True, 500, ['AMS-JFK']), ('CDG','GRU','Air France', True, 720, ['CDG-GRU'])
]

CASH_TAX_BASE = {'Economy': 220, 'Premium': 390, 'Business': 690, 'First': 1100}
POINTS_BASE_SAS = {'Economy': 15000, 'Premium': 30000, 'Business': 50000, 'First': 90000}
POINTS_BASE_SKY = {'Economy': 70000, 'Premium': 105000, 'Business': 130000, 'First': 175000}


def _seed(text: str) -> int:
    return int(sha256(text.encode()).hexdigest()[:8], 16)


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def _pick_cabin(cabin: str, seed: int, provider: str) -> str:
    if cabin and cabin != 'Any':
        return cabin
    options = ['Economy', 'Premium', 'Business'] if provider == 'SAS' else ['Economy', 'Business', 'Business', 'Premium']
    return options[seed % len(options)]


def _seat_count(seed: int) -> int:
    return [1, 2, 2, 2, 3, 4][seed % 6]


def _points(provider: str, cabin: str, duration: int, seed: int) -> int:
    base = POINTS_BASE_SAS if provider == 'SAS' else POINTS_BASE_SKY
    raw = base[cabin] + int(duration * (18 if provider == 'SAS' else 9)) + (seed % 4000)
    return int(round(raw / 500.0) * 500)


def _taxes(cabin: str, seed: int) -> int:
    return CASH_TAX_BASE[cabin] + (seed % 120)


def _score(points: int, duration: int, cabin: str, seats: int, direct: bool, reposition_required: bool) -> float:
    cabin_bonus = {'Economy': 0.2, 'Premium': 0.45, 'Business': 1.0, 'First': 1.4}[cabin]
    duration_bonus = min(duration / 700.0, 2.0)
    seats_bonus = min(seats / 2.0, 2.0)
    direct_bonus = 0.2 if direct else 0.0
    reposition_penalty = 0.18 if reposition_required else 0.0
    return round((cabin_bonus + duration_bonus + seats_bonus + direct_bonus) - (points / 220000.0) - reposition_penalty, 2)


def _destination_match(requested: str, actual: str) -> bool:
    requested = (requested or '').upper().strip()
    if not requested:
        return True
    if requested == 'ANY':
        return True
    return actual == requested


def find_results(provider: str, origin: str, destination: str, start_date: str, end_date: str, cabin: str, passengers: int, direct_only: bool, include_nearby: bool=False, mode: str='route_search') -> List[Dict[str, Any]]:
    cabin = cabin or 'Any'
    start = date.fromisoformat(start_date) if start_date else date.today()
    end = date.fromisoformat(end_date) if end_date else min(date.today() + timedelta(days=180), start + timedelta(days=60))
    if end > date.today() + timedelta(days=365):
        end = date.today() + timedelta(days=365)

    routes = SAS_ROUTES if provider == 'SAS' else SKYTEAM_ROUTES
    requested_origin = (origin or '').upper().strip()
    allowed_origins = set(expand_origins(requested_origin, include_nearby)) if requested_origin else set()
    if mode == 'most_hits' and provider == 'Both':
        providers = ['SAS', 'SkyTeam']
    else:
        providers = [provider]
    out = []
    for chosen_provider in providers:
        chosen_routes = SAS_ROUTES if chosen_provider == 'SAS' else SKYTEAM_ROUTES
        for d in daterange(start, end):
            for route in chosen_routes:
                if chosen_provider == 'SAS':
                    o, dest, direct, duration = route
                    carrier = 'SAS'
                    segments = [f'{o}-{dest}'] if direct else [f'{o}-CPH', f'CPH-{dest}'] if o != 'CPH' and dest not in ('TRD','TOS','NCE','PMI','LHR') else [f'{o}-{dest}']
                else:
                    o, dest, carrier, direct, duration, segments = route
                if requested_origin and o not in allowed_origins:
                    continue
                if not _destination_match(destination, dest):
                    continue
                if direct_only and not direct:
                    continue
                seed = _seed(f'{chosen_provider}|{o}|{dest}|{d.isoformat()}|{cabin}|{mode}')
                availability_mod = 7 if mode == 'route_search' else 4 if mode == 'most_hits' else 5
                if seed % availability_mod not in (0,1,2):
                    continue
                selected_cabin = _pick_cabin(cabin, seed, chosen_provider)
                seats = _seat_count(seed)
                if seats < passengers:
                    continue
                points = _points(chosen_provider, selected_cabin, duration, seed)
                taxes = _taxes(selected_cabin, seed)
                reposition_required = bool(requested_origin and o != requested_origin)
                score = _score(points, duration, selected_cabin, seats, direct, reposition_required)
                find_url = 'https://www.flysas.com/en/award-finder'
                info_url = 'https://www.flysas.com/ca-en/eurobonus/points/use/partner-award-flights/' if chosen_provider != 'SAS' else 'https://www.flysas.com/en/award-finder'
                out.append({
                    'provider': chosen_provider,
                    'carrier': carrier,
                    'origin': o,
                    'destination': dest,
                    'origin_label': airport_label(o),
                    'destination_label': airport_label(dest),
                    'requested_origin': requested_origin,
                    'date': d.isoformat(),
                    'cabin': selected_cabin,
                    'seats': seats,
                    'points': points,
                    'taxes': taxes,
                    'direct': direct,
                    'segments': segments,
                    'duration_minutes': duration,
                    'reposition_required': reposition_required,
                    'reposition_note': f'Starter fra {airport_label(o)} i stedet for {airport_label(requested_origin)}.' if reposition_required else '',
                    'booking_note': 'Best effort: verifiser hos SAS før booking.' if chosen_provider != 'SAS' else 'Kan ofte finnes direkte via SAS Award Finder.',
                    'score': score,
                    'book_url': 'https://www.flysas.com/en/award-finder',
                    'find_url': find_url,
                    'info_url': info_url,
                })
    if mode == 'best_value':
        out.sort(key=lambda x: (-x['score'], x['points'], -x['seats']))
    elif mode == 'most_hits':
        out.sort(key=lambda x: (x['date'], -x['seats'], x['points']))
    else:
        out.sort(key=lambda x: (x['date'], x['points'], -x['seats']))
    return out[:600]


def build_calendar(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for r in results:
        existing = best.get(r['date'])
        if not existing or r['points'] < existing['points'] or (r['points'] == existing['points'] and r['seats'] > existing['seats']):
            best[r['date']] = r
    return [best[k] for k in sorted(best.keys())]


def build_value_feed(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = sorted(rows, key=lambda x: (-x['score'], x['points'], -x['seats']))
    out = []
    for r in ranked[:24]:
        rr = dict(r)
        rr['value_tag'] = 'Høy value' if rr['score'] >= 2.2 else 'Bra value' if rr['score'] >= 1.8 else 'Verdt å følge'
        out.append(rr)
    return out
