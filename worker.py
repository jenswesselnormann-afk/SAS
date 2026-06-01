from __future__ import annotations
import json
from services.storage import (
    init_db,
    list_subscriptions,
    save_new_discoveries,
    list_offer_state,
    upsert_offer_state,
    record_notification_event,
    mark_notification_delivery,
)
from services.demo_engine import find_results
from services.telegram import send_message, is_configured
from services.notifications import normalize_channels


def route_key(r):
    return f"{r['provider']}|{r['date']}|{r['origin']}-{r['destination']}|{r['cabin']}|{r['points']}|{','.join(r.get('segments', []))}"


def offer_key(r):
    return f"{r['provider']}|{r['date']}|{r['origin']}-{r['destination']}|{','.join(r.get('segments', []))}"


def change_event_key(sub_id: int, key: str, change_type: str):
    return f'{sub_id}|{key}|{change_type}'


def event_dedupe_key(sub_id: int, event: dict):
    row = event['row']
    t = event['type']
    suffix = ''
    if t == 'seats_up':
        suffix = f"|seats={row.get('seats', 0)}"
    elif t == 'points_down':
        suffix = f"|points={row.get('points', 0)}"
    elif t == 'new_cabin':
        suffix = f"|cabin={row.get('cabin', '')}"
    elif t == 'gateway_found':
        suffix = f"|origin={row.get('origin', '')}"
    return change_event_key(sub_id, event['key'], t) + suffix


def detect_meaningful_changes(subscription, results, previous_state):
    events = []
    for r in results:
        if r.get('source_type') != 'live':
            continue
        key = offer_key(r)
        prev = previous_state.get(key)
        if not prev:
            events.append({'type': 'new_offer', 'row': r, 'key': key, 'reason': 'Nytt award-funn'})
            continue
        prev_payload = prev.get('payload', {}) or {}
        prev_seats = int(prev.get('seats') or 0)
        prev_points = int(prev.get('points') or 0)
        current_points = int(r.get('points') or 0)
        prev_cabin = prev.get('cabin') or prev_payload.get('cabin')
        prev_reposition = bool(prev.get('reposition_required'))
        if int(r.get('seats') or 0) > prev_seats:
            events.append({'type': 'seats_up', 'row': r, 'key': key, 'reason': f"Seter økte {prev_seats} → {r.get('seats', 0)}"})
        if prev_points > 0 and current_points > 0 and current_points < prev_points:
            events.append({'type': 'points_down', 'row': r, 'key': key, 'reason': f"Poengpris ned {prev_points} → {current_points}"})
        if prev_cabin and prev_cabin != r.get('cabin'):
            events.append({'type': 'new_cabin', 'row': r, 'key': key, 'reason': f"Ny cabin: {prev_cabin} → {r.get('cabin')}"})
        if not prev_reposition and bool(r.get('reposition_required')):
            events.append({'type': 'gateway_found', 'row': r, 'key': key, 'reason': 'Ny gateway/posisjoneringsmulighet'})
    return events


def build_alert(event):
    r = event['row']
    lines = [
        f"🛫 Award-varsel · {r['provider']}",
        f"Kilde: {r.get('source_name', 'ukjent')} · verifisering: {r.get('verification_level', 'ukjent')}",
        event.get('reason', 'Oppdatert funn'),
        f"{r['origin']} → {r['destination']} · {r['date']}",
        f"{r['cabin']} · {r['seats']} seter",
    ]
    if r.get('reposition_required'):
        lines.append(f"Posisjonering: {r.get('reposition_note')}")
    if r.get('segments'):
        lines.append(f"Segmenter: {' > '.join(r['segments'])}")
    lines.append(r['book_url'])
    return '\n'.join(lines)


def deliver_telegram(subscription, events):
    if not events:
        return {'ok': True, 'count': 0}
    title = f"Watcher {subscription['origin']} → {subscription['destination']}"
    body = [title]
    for ev in events[:4]:
        body.append(build_alert(ev))
    payload = '\n\n'.join(body)
    return send_message(payload)


def main():
    init_db()
    subs = list_subscriptions()
    total_events = 0
    for s in subs:
        results = find_results(
            s['provider'],
            s['origin'],
            s['destination'],
            s.get('start_date') or '',
            s.get('end_date') or '',
            s.get('cabin') or 'Any',
            s.get('passengers') or 1,
            bool(s.get('direct_only')),
            bool(s.get('include_nearby')),
        )
        results = [r for r in results if r.get('source_type') == 'live']
        results = [r for r in results if r.get('seats', 0) >= (s.get('min_seats') or 1)]
        previous_state = list_offer_state(s['id'])
        events = detect_meaningful_changes(s, results, previous_state)
        save_new_discoveries(s['id'], s['provider'], [(route_key(r), json.dumps(r, ensure_ascii=False)) for r in results])
        channels = normalize_channels(s)
        for ev in events:
            ev_key = event_dedupe_key(s['id'], ev)
            if not channels.get('telegram', {}).get('enabled'):
                continue
            if not record_notification_event(s['id'], 'telegram', ev['type'], ev_key, json.dumps(ev['row'], ensure_ascii=False)):
                continue
            if not is_configured():
                mark_notification_delivery(s['id'], 'telegram', ev['type'], ev_key, False, 'Telegram ikke konfigurert')
                continue
            result = deliver_telegram(s, [ev])
            ok = bool(result.get('ok'))
            mark_notification_delivery(s['id'], 'telegram', ev['type'], ev_key, ok, result.get('description') or result.get('error') or '')
            if ok:
                total_events += 1
        for r in results:
            upsert_offer_state(
                s['id'],
                offer_key(r),
                route_key(r),
                json.dumps(r, ensure_ascii=False),
                int(r.get('seats', 0)),
                int(r.get('points', 0)),
                r.get('cabin', ''),
                bool(r.get('reposition_required')),
            )
    print(f'Notification events sent: {total_events}')


if __name__ == '__main__':
    main()
