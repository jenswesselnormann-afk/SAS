from __future__ import annotations
import json
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
        include_nearby INTEGER DEFAULT 1,
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
    cur.execute('''CREATE TABLE IF NOT EXISTS subscription_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        config_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(subscription_id, channel)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS watcher_offer_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        offer_key TEXT NOT NULL,
        route_key TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        seats INTEGER NOT NULL DEFAULT 0,
        points INTEGER NOT NULL DEFAULT 0,
        cabin TEXT,
        reposition_required INTEGER NOT NULL DEFAULT 0,
        first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(subscription_id, offer_key)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS notification_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_key TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        delivered_at TEXT,
        delivery_status TEXT DEFAULT 'pending',
        delivery_error TEXT,
        UNIQUE(subscription_id, channel, event_type, event_key)
    )''')
    # Backward-compatible in-place migrations
    cols = {r['name'] for r in conn.execute("PRAGMA table_info(subscriptions)")}
    if 'notification_prefs' not in cols:
        conn.execute("ALTER TABLE subscriptions ADD COLUMN notification_prefs TEXT DEFAULT '{}'")
    conn.commit()
    conn.close()


def add_subscription(payload):
    conn = connect()
    cur = conn.cursor()
    notification_prefs = payload.get('notification_prefs') or {
        'channels': {
            'telegram': {'enabled': bool(payload.get('telegram_enabled', True))},
            'push': {'enabled': False},
        }
    }
    cur.execute(
        '''INSERT INTO subscriptions (provider, origin, destination, start_date, end_date, cabin, passengers, direct_only, min_seats, include_nearby, telegram_enabled, notification_prefs)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            payload['provider'], payload['origin'].upper(), payload['destination'].upper(), payload.get('start_date'), payload.get('end_date'),
            payload.get('cabin', 'Any'), int(payload.get('passengers', 1)), 1 if payload.get('direct_only') else 0,
            int(payload.get('min_seats', 1)), 1 if payload.get('include_nearby', True) else 0,
            1 if payload.get('telegram_enabled', True) else 0,
            json.dumps(notification_prefs, ensure_ascii=False),
        )
    )
    conn.commit()
    sub_id = cur.lastrowid
    set_subscription_channel(sub_id, 'telegram', bool(payload.get('telegram_enabled', True)))
    set_subscription_channel(sub_id, 'push', False)
    conn.close()
    return sub_id


def list_subscriptions():
    conn = connect()
    rows = [dict(r) for r in conn.execute('SELECT * FROM subscriptions ORDER BY created_at DESC')]
    for row in rows:
        row['channels'] = list_subscription_channels(row['id'], conn=conn)
    conn.close()
    return rows


def delete_subscription(sub_id: int):
    conn = connect()
    conn.execute('DELETE FROM subscriptions WHERE id=?', (sub_id,))
    conn.execute('DELETE FROM discoveries WHERE subscription_id=?', (sub_id,))
    conn.execute('DELETE FROM subscription_channels WHERE subscription_id=?', (sub_id,))
    conn.execute('DELETE FROM watcher_offer_state WHERE subscription_id=?', (sub_id,))
    conn.execute('DELETE FROM notification_events WHERE subscription_id=?', (sub_id,))
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


def set_subscription_channel(subscription_id: int, channel: str, enabled: bool, config_json: str = '{}'):
    conn = connect()
    conn.execute(
        '''INSERT INTO subscription_channels (subscription_id, channel, enabled, config_json, updated_at)
           VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(subscription_id, channel) DO UPDATE SET
             enabled=excluded.enabled,
             config_json=excluded.config_json,
             updated_at=CURRENT_TIMESTAMP''',
        (subscription_id, channel, 1 if enabled else 0, config_json),
    )
    if channel == 'telegram':
        conn.execute('UPDATE subscriptions SET telegram_enabled=? WHERE id=?', (1 if enabled else 0, subscription_id))
    conn.commit()
    conn.close()


def list_subscription_channels(subscription_id: int, conn=None):
    owns_conn = conn is None
    conn = conn or connect()
    rows = [dict(r) for r in conn.execute(
        'SELECT channel, enabled, config_json, updated_at FROM subscription_channels WHERE subscription_id=? ORDER BY channel',
        (subscription_id,),
    )]
    if not rows:
        sub = conn.execute('SELECT telegram_enabled FROM subscriptions WHERE id=?', (subscription_id,)).fetchone()
        if sub is not None:
            rows = [
                {'channel': 'push', 'enabled': 0, 'config_json': '{}', 'updated_at': None},
                {'channel': 'telegram', 'enabled': int(sub['telegram_enabled'] or 0), 'config_json': '{}', 'updated_at': None},
            ]
    if owns_conn:
        conn.close()
    for r in rows:
        try:
            r['config'] = json.loads(r.get('config_json') or '{}')
        except Exception:
            r['config'] = {}
        r['enabled'] = bool(r.get('enabled'))
    return rows


def list_offer_state(subscription_id: int):
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        '''SELECT offer_key, route_key, payload_json, seats, points, cabin, reposition_required
           FROM watcher_offer_state WHERE subscription_id=?''',
        (subscription_id,),
    )]
    conn.close()
    out = {}
    for row in rows:
        try:
            row['payload'] = json.loads(row.get('payload_json') or '{}')
        except Exception:
            row['payload'] = {}
        out[row['offer_key']] = row
    return out


def upsert_offer_state(subscription_id: int, offer_key: str, route_key: str, payload_json: str, seats: int, points: int, cabin: str, reposition_required: bool):
    conn = connect()
    conn.execute(
        '''INSERT INTO watcher_offer_state (subscription_id, offer_key, route_key, payload_json, seats, points, cabin, reposition_required)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(subscription_id, offer_key) DO UPDATE SET
             route_key=excluded.route_key,
             payload_json=excluded.payload_json,
             seats=excluded.seats,
             points=excluded.points,
             cabin=excluded.cabin,
             reposition_required=excluded.reposition_required,
             last_seen_at=CURRENT_TIMESTAMP''',
        (subscription_id, offer_key, route_key, payload_json, int(seats or 0), int(points or 0), cabin, 1 if reposition_required else 0),
    )
    conn.commit()
    conn.close()


def record_notification_event(subscription_id: int, channel: str, event_type: str, event_key: str, payload_json: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        '''INSERT OR IGNORE INTO notification_events (subscription_id, channel, event_type, event_key, payload_json)
           VALUES (?, ?, ?, ?, ?)''',
        (subscription_id, channel, event_type, event_key, payload_json),
    )
    inserted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return inserted


def mark_notification_delivery(subscription_id: int, channel: str, event_type: str, event_key: str, ok: bool, error: str = ''):
    conn = connect()
    conn.execute(
        '''UPDATE notification_events
           SET delivered_at=CURRENT_TIMESTAMP,
               delivery_status=?,
               delivery_error=?
           WHERE subscription_id=? AND channel=? AND event_type=? AND event_key=?''',
        ('sent' if ok else 'failed', error or '', subscription_id, channel, event_type, event_key),
    )
    conn.commit()
    conn.close()
