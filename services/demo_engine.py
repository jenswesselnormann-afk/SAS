from __future__ import annotations
from datetime import date, timedelta
from hashlib import sha256
from typing import List, Dict, Any
from services.airports import airport_label

SAS_ROUTES = [
    ('OSL','EWR', True, 510), ('OSL','JFK', True, 500), ('CPH','JFK', True, 520), ('CPH','EWR', True, 510),
    ('ARN','EWR', True, 505), ('ARN','JFK', True, 500), ('OSL','NCE', True, 175), ('OSL','PMI', True, 205),
    ('OSL','TRD', True, 55), ('OSL','TOS', True, 110), ('BGO','OSL', True, 55), ('OSL','LHR', True, 135)
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
    ('CPH','JFK','Virgin Atlantic', False, 700, ['CPH-LHR', 'LHR-JFK'])
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


def find_results(provider: str, origin: str, destination: str, start_date: str, end_date: str, cabin: str, passengers: int, direct_only: bool) -> List[Dict[str, Any]]:
    cabin = cabin or 'Any'
    start = date.fromisoformat(start_date) if start_date else date.today()
    end = date.fromisoformat(end_date) if end_date else min(date.today() + timedelta(days=60), start + timedelta(days=30))
    if end > date.today() + timedelta(days=365):
        end = date.today() + timedelta(days=365)

    routes = SAS_ROUTES if provider == 'SAS' else SKYTEAM_ROUTES
    out = []
    for d in daterange(start, end):
        for route in routes:
            if provider == 'SAS':
                o, dest, direct, duration = route
                carrier = 'SAS'
                segments = [f'{o}-{dest}'] if direct else []
            else:
                o, dest, carrier, direct, duration, segments = route
            if origin and o != origin.upper():
                continue
            if destination and dest != destination.upper():
                continue
            if direct_only and not direct:
                continue

            seed = _seed(f'{provider}|{o}|{dest}|{d.isoformat()}|{cabin}')
            if seed % 7 not in (0, 1, 2):
                continue

            selected_cabin = _pick_cabin(cabin, seed, provider)
            seats = _seat_count(seed)
            if seats < passengers:
                continue

            points = _points(provider, selected_cabin, duration, seed)
            taxes = CASH_TAX_BASE.get(selected_cabin, 350) + (0 if direct else 250) + (seed % 170)
            row = {
                'provider': provider,
                'carrier': carrier,
                'origin': o,
                'destination': dest,
                'origin_label': airport_label(o),
                'destination_label': airport_label(dest),
                'date': d.isoformat(),
                'cabin': selected_cabin,
                'seats': seats,
                'points': points,
                'taxes': taxes,
                'direct': direct,
                'duration_minutes': duration,
                'segments': segments,
                'score': round(_value_score(selected_cabin, duration, points, seats, direct), 2),
                'calendar_price': points,
                'find_url': _find_url(provider, o, dest, d),
                'book_url': _book_url(provider, o, dest, d),
                'info_url': _info_url(provider, carrier),
                'booking_note': _booking_note(provider),
            }
            out.append(row)
    return sorted(out, key=lambda r: (r['date'], r['points'], -r['score']))


def build_calendar(results: List[Dict[str, Any]]):
    best_by_date = {}
    for r in results:
        cur = best_by_date.get(r['date'])
        if not cur or r['points'] < cur['points']:
            best_by_date[r['date']] = {
                'date': r['date'],
                'points': r['points'],
                'cabin': r['cabin'],
                'seats': r['seats'],
                'direct': r['direct'],
                'book_url': r['book_url'],
                'origin': r['origin'],
                'destination': r['destination'],
                'origin_label': r['origin_label'],
                'destination_label': r['destination_label'],
            }
    return [best_by_date[d] for d in sorted(best_by_date)]


def build_value_feed(all_rows: List[Dict[str, Any]]):
    rows = []
    for r in all_rows:
        if r['duration_minutes'] < 300:
            continue
        if r['cabin'] not in ('Premium', 'Business', 'First'):
            continue
        r = dict(r)
        r['value_tag'] = _value_tag(r)
        rows.append(r)
    return sorted(rows, key=lambda x: (-x['score'], x['points'], x['taxes']))[:60]


def _pick_cabin(cabin: str, seed: int, provider: str):
    if cabin and cabin != 'Any':
        return cabin
    options = ['Economy', 'Premium', 'Business'] if provider == 'SAS' else ['Economy', 'Business']
    return options[seed % len(options)]


def _seat_count(seed: int):
    return [1, 2, 2, 3, 4][seed % 5]


def _points(provider: str, cabin: str, duration: int, seed: int):
    if provider == 'SAS':
        base = POINTS_BASE_SAS[cabin]
        if duration < 180 and cabin == 'Economy':
            base = 5000 + (seed % 2) * 5000
        return base + (seed % 3) * 2500
    base = POINTS_BASE_SKY[cabin]
    if duration > 900:
        base += 35000 if cabin == 'Business' else 20000
    return base + (seed % 4) * 17500


def _value_score(cabin: str, duration: int, points: int, seats: int, direct: bool):
    cabin_bonus = {'Economy': 1.0, 'Premium': 1.35, 'Business': 2.25, 'First': 2.8}.get(cabin, 1.0)
    return ((duration / max(points, 1)) * 1000 * cabin_bonus) + (0.35 * seats) + (0.5 if direct else 0)


def _find_url(provider: str, origin: str, destination: str, d: date):
    if provider == 'SAS':
        return f'https://www.flysas.com/en/award-finder?from={origin}&to={destination}&month={d.strftime("%Y-%m")}'
    return 'https://www.flysas.com/ca-en/eurobonus/points/use/partner-award-flights/'


def _book_url(provider: str, origin: str, destination: str, d: date):
    if provider == 'SAS':
        return f'https://www.flysas.com/en/award-finder?from={origin}&to={destination}&month={d.strftime("%Y-%m")}'
    return 'https://www.flysas.com/en/award-finder'


def _info_url(provider: str, carrier: str):
    if provider == 'SAS':
        return 'https://www.flysas.com/en/travel-info/ticket-types/award-tickets'
    lookup = {
        'Air France': 'https://www.flysas.com/en/about-us/skyteam',
        'KLM': 'https://www.flysas.com/en/about-us/skyteam',
        'Delta': 'https://www.flysas.com/en/about-us/skyteam',
        'Korean Air': 'https://www.flysas.com/en/about-us/skyteam',
        'Virgin Atlantic': 'https://www.flysas.com/en/about-us/skyteam',
    }
    return lookup.get(carrier, 'https://www.flysas.com/ca-en/eurobonus/points/use/partner-award-flights/')


def _booking_note(provider: str):
    if provider == 'SAS':
        return 'SAS-awards kan normalt finnes og bookes via SAS Award Finder.'
    return 'SkyTeam-partnerreiser følger partner-award-reglene hos SAS. Start i SAS award/partner-flow, og bruk partnerinfosiden hvis direkte dyplenke ikke fungerer.'


def _value_tag(r):
    if r['cabin'] == 'Business' and r['duration_minutes'] >= 480 and r['direct']:
        return 'Langrute + business + direkte'
    if r['cabin'] == 'Business' and r['duration_minutes'] >= 900:
        return 'Svært god long-haul value'
    if r['points'] <= 60000 and r['cabin'] in ('Premium', 'Business'):
        return 'Lav poengpris'
    return 'God totalverdi'
