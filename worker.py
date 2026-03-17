from __future__ import annotations
import json
from services.storage import init_db, list_subscriptions, save_new_discoveries
from services.demo_engine import find_results
from services.telegram import send_message, is_configured


def route_key(r):
    return f"{r['provider']}|{r['date']}|{r['origin']}-{r['destination']}|{r['cabin']}|{r['points']}|{','.join(r.get('segments', []))}"


def main():
    init_db()
    subs = list_subscriptions()
    total_new = 0
    messages = []
    for s in subs:
        results = find_results(s['provider'], s['origin'], s['destination'], s.get('start_date') or '', s.get('end_date') or '', s.get('cabin') or 'Any', s.get('passengers') or 1, bool(s.get('direct_only')))
        results = [r for r in results if r.get('seats', 0) >= (s.get('min_seats') or 1)]
        inserted = save_new_discoveries(s['id'], s['provider'], [(route_key(r), json.dumps(r, ensure_ascii=False)) for r in results])
        if inserted:
            total_new += len(inserted)
            for _, payload_json in inserted[:5]:
                r = json.loads(payload_json)
                messages.append(f"🛫 Nytt funn {r['provider']}\n{r['origin']} → {r['destination']} {r['date']}\n{r['cabin']} · {r['points']} poeng · {r['seats']} seter\n{r['book_url']}")
    if messages and is_configured():
        send_message('\n\n'.join(messages[:8]))
    print(f'New discoveries: {total_new}')


if __name__ == '__main__':
    main()
