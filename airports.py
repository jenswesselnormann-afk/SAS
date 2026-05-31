from __future__ import annotations
import json
from pathlib import Path

AIRPORTS = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'airports.json').read_text())
BY_CODE = {a['code']: a for a in AIRPORTS}


def search_airports(query: str):
    q = (query or '').strip().lower()
    if not q:
        return AIRPORTS[:15]
    out = []
    for a in AIRPORTS:
        hay = f"{a['code']} {a['city']} {a['name']} {a['country']}".lower()
        if q in hay:
            out.append(a)
    return out[:20]


def airport_label(code: str):
    row = BY_CODE.get(code.upper())
    return f"{row['code']} · {row['city']} — {row['name']}" if row else code.upper()
