from __future__ import annotations
import json
from services.storage import init_db, list_subscriptions, save_new_discoveries
from services.demo_engine import find_results
from services.telegram import send_message, is_configured


def route_key(r):
    return f"{r['provider']}|{r['date']}|{r['origin']}-{r['destination']}|{r['cabin']}|{r['points']}|{','.join(r.get('segments', []))}"


def build_alert(r):
    lines = [
        f"🛫 Nytt award-funn · {r['provider']}",
        f"{r['origin']} → {r['destination']} · {r['date']}",
        f"{r['cabin']} · {r['points']} poeng · {r['taxes']} avgifter · {r['seats']} seter",
    ]
    if r.get('reposition_required'):
        lines.append(f"Posisjonering: {r.get('reposition_note')}")
    if r.get('segments'):
        lines.append(f"Segmenter: {' > '.join(r['segments'])}")
    lines.append(r['book_url'])
    return '\n'.join(lines)


def main():
    init_db()
    subs = list_subscriptions()
    total_new = 0
    messages = []
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
        results = [r for r in results if r.get('seats', 0) >= (s.get('min_seats') or 1)]
        inserted = save_new_discoveries(s['id'], s['provider'], [(route_key(r), json.dumps(r, ensure_ascii=False)) for r in results])
        if inserted:
            total_new += len(inserted)
            decoded = [json.loads(payload_json) for _, payload_json in inserted[:3]]
            summary = f"Watcher {s['origin']} → {s['destination']} fant {len(inserted)} nye treff"
            messages.append(summary + "\n" + "\n\n".join(build_alert(r) for r in decoded))
    if messages and is_configured():
        send_message('\n\n'.join(messages[:5]))
    print(f'New discoveries: {total_new}')


if __name__ == '__main__':
    main()
