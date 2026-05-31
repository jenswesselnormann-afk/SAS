from __future__ import annotations
import os
import requests


def is_configured():
    return bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))


def send_message(text: str):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return {'ok': False, 'error': 'Telegram ikke konfigurert'}
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    resp = requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=20)
    try:
        data = resp.json()
    except Exception:
        data = {'ok': False, 'error': resp.text}
    return data
