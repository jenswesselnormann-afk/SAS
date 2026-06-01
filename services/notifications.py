from __future__ import annotations
import json
from typing import Dict, Any


SUPPORTED_CHANNELS = ('telegram', 'push')


def build_notification_prefs(payload: dict) -> dict:
    telegram_enabled = bool(payload.get('telegram_enabled', True))
    prefs = payload.get('notification_prefs')
    if isinstance(prefs, dict):
        return prefs
    return {
        'channels': {
            'telegram': {'enabled': telegram_enabled},
            'push': {'enabled': False},
        }
    }


def normalize_channels(subscription: dict) -> Dict[str, Dict[str, Any]]:
    # Prefer explicit channel rows, fallback to notification_prefs / telegram_enabled.
    channels = {}
    for row in subscription.get('channels', []) or []:
        channels[row.get('channel')] = {
            'enabled': bool(row.get('enabled')),
            'config': row.get('config') or {},
        }
    if channels:
        for ch in SUPPORTED_CHANNELS:
            channels.setdefault(ch, {'enabled': False, 'config': {}})
        return channels

    prefs = subscription.get('notification_prefs') or {}
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except Exception:
            prefs = {}
    pref_channels = prefs.get('channels', {}) if isinstance(prefs, dict) else {}
    telegram_enabled = bool(subscription.get('telegram_enabled', True))
    return {
        'telegram': {'enabled': bool(pref_channels.get('telegram', {}).get('enabled', telegram_enabled)), 'config': {}},
        'push': {'enabled': bool(pref_channels.get('push', {}).get('enabled', False)), 'config': {}},
    }

