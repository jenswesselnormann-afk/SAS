from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).resolve().parents[1] / 'app.db'


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        start_date TEXT,
        end_date TEXT,
        cabin TEXT,
        passengers INTEGER DEFAULT 1,
        direct_only INTEGER DEFAULT 0,
        min_seats INTEGER DEFAULT 1,
        telegram_enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS discoveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        route_key TEXT NOT NULL,
        payload_json TEXT,
        first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(subscription_id, route_key)
    )''')
    conn.commit()
    conn.close()


def add_subscription(payload):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO subscriptions (provider, origin, destination, start_date, end_date, cabin, passengers, direct_only, min_seats, telegram_enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            payload['provider'], payload['origin'].upper(), payload['destination'].upper(), payload.get('start_date'), payload.get('end_date'),
            payload.get('cabin', 'Any'), int(payload.get('passengers', 1)), 1 if payload.get('direct_only') else 0,
            int(payload.get('min_seats', 1)), 1 if payload.get('telegram_enabled', True) else 0
        )
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return sub_id


def list_subscriptions():
    conn = connect()
    rows = [dict(r) for r in conn.execute('SELECT * FROM subscriptions ORDER BY created_at DESC')]
    conn.close()
    return rows


def delete_subscription(sub_id: int):
    conn = connect()
    conn.execute('DELETE FROM subscriptions WHERE id=?', (sub_id,))
    conn.execute('DELETE FROM discoveries WHERE subscription_id=?', (sub_id,))
    conn.commit()
    conn.close()


def list_discoveries():
    conn = connect()
    rows = [dict(r) for r in conn.execute('SELECT * FROM discoveries ORDER BY first_seen_at DESC LIMIT 100')]
    conn.close()
    return rows


def save_new_discoveries(subscription_id: int, provider: str, records: Iterable[tuple[str, str]]):
    conn = connect()
    cur = conn.cursor()
    inserted = []
    for route_key, payload_json in records:
        try:
            cur.execute(
                'INSERT INTO discoveries (subscription_id, provider, route_key, payload_json) VALUES (?, ?, ?, ?)',
                (subscription_id, provider, route_key, payload_json)
            )
            inserted.append((route_key, payload_json))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return inserted
