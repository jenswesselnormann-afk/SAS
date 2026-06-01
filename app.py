from __future__ import annotations
import csv
import io
import os
from flask import Flask, jsonify, render_template, request, Response, send_from_directory
from services.storage import init_db, add_subscription, list_subscriptions, delete_subscription, list_discoveries
from services.airports import search_airports
from services.demo_engine import find_results, build_calendar, build_value_feed, source_summary_for
from services.telegram import config_status, send_message
from services.notifications import build_notification_prefs
from services.gateways import expand_origins

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
init_db()


def _asset_version() -> str:
    static_dir = os.path.join(app.root_path, 'static')
    candidates = ('app.js', 'styles.css', 'sw.js', 'manifest.json')
    mtimes = []
    for filename in candidates:
        path = os.path.join(static_dir, filename)
        try:
            mtimes.append(int(os.path.getmtime(path)))
        except OSError:
            continue
    return str(max(mtimes, default=0))


@app.context_processor
def template_globals():
    return {'asset_version': _asset_version()}


@app.after_request
def disable_response_caching(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/healthz')
def healthz():
    return {'ok': True}


@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')


@app.route('/sw.js')
def sw():
    return send_from_directory('static', 'sw.js')


@app.route('/api/airports')
def api_airports():
    return jsonify({'results': search_airports(request.args.get('q', ''))})


@app.route('/api/gateways')
def api_gateways():
    origin = request.args.get('origin', '').upper()
    include = request.args.get('include_nearby', 'true').lower() == 'true'
    return jsonify({'origin': origin, 'results': expand_origins(origin, include)})


def _search_payload(payload: dict):
    provider = payload.get('provider', 'SAS')
    include_nearby = bool(payload.get('include_nearby', False))
    mode = payload.get('mode', 'route_search')
    return find_results(
        provider,
        payload.get('origin', ''),
        payload.get('destination', ''),
        payload.get('start_date', ''),
        payload.get('end_date', ''),
        payload.get('cabin', 'Any'),
        int(payload.get('passengers', 1)),
        bool(payload.get('direct_only', False)),
        include_nearby,
        mode=mode,
    )


@app.route('/api/search', methods=['POST'])
def api_search():
    payload = request.get_json(force=True)
    results = _search_payload(payload)
    summary = source_summary_for(payload.get('provider', 'SAS'), results)
    return jsonify({
        'results': results,
        'calendar': build_calendar(results),
        'count': len(results),
        'provider': payload.get('provider', 'SAS'),
        'expanded_origins': expand_origins(payload.get('origin', ''), bool(payload.get('include_nearby', False))),
        'mode': payload.get('mode', 'route_search'),
        'source_summary': summary,
        'notices': summary.get('notices', []),
    })


@app.route('/api/value-feed')
def api_value_feed():
    rows = build_value_feed([])
    return jsonify({
        'results': rows,
        'count': len(rows),
        'disabled': True,
        'reason': 'Value-feed er deaktivert til poeng- og avgiftsdata er verifisert live.',
    })


@app.route('/api/subscriptions', methods=['GET', 'POST'])
def api_subscriptions():
    if request.method == 'POST':
        payload = request.get_json(force=True)
        payload['notification_prefs'] = build_notification_prefs(payload)
        new_id = add_subscription(payload)
        return jsonify({'ok': True, 'id': new_id})
    return jsonify({'results': list_subscriptions()})


@app.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def api_delete_subscription(sub_id: int):
    delete_subscription(sub_id)
    return jsonify({'ok': True})


@app.route('/api/discoveries')
def api_discoveries():
    return jsonify({'results': list_discoveries()})


@app.route('/api/telegram/status')
def api_telegram_status():
    status = config_status()
    status['worker_hint'] = 'Sett opp periodisk kjøring av worker.py for automatiske varsler.'
    status['channels_ready'] = ['telegram'] if status.get('configured') else []
    return jsonify(status)


@app.route('/api/telegram/test', methods=['POST'])
def api_telegram_test():
    status = config_status()
    if not status.get('configured'):
        return jsonify({
            'ok': False,
            'error': f"Telegram ikke konfigurert. Mangler: {', '.join(status.get('missing', []))}",
            'missing': status.get('missing', []),
        }), 400
    result = send_message('✅ Testvarsel fra EuroBonus Award Explorer\nDette bekrefter at Telegram-kanalen er aktiv.')
    status = 200 if result.get('ok') else 400
    return jsonify(result), status


@app.route('/export.csv')
def export_csv():
    payload = dict(request.args)
    payload['include_nearby'] = request.args.get('include_nearby', 'false').lower() == 'true'
    payload['direct_only'] = request.args.get('direct_only', 'false').lower() == 'true'
    payload['passengers'] = int(request.args.get('passengers', 1))
    results = _search_payload(payload)
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=[
            'provider', 'carrier', 'origin_label', 'destination_label', 'date', 'cabin', 'seats',
            'points', 'taxes', 'direct', 'segments', 'reposition_required', 'reposition_note',
            'score', 'book_url', 'source_type', 'source_name', 'checked_at', 'verification_level'
        ]
    )
    writer.writeheader()
    for r in results:
        row = dict(r)
        row['segments'] = ' > '.join(row.get('segments', []))
        writer.writerow({k: row.get(k, '') for k in writer.fieldnames})
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=awards.csv'})


@app.route('/api/meta/partner-info')
def api_partner_info():
    return jsonify({
        'title': 'Bestilling av partnerreiser (SkyTeam) med EuroBonus',
        'text': 'Bonusreiser med SkyTeam-partnere følger SAS sine partner-award-regler. Skatter og avgifter betales separat. Enkelte reiser kan kreve at du starter fra SAS sin partner-side eller award-booking.',
        'info_url': 'https://www.flysas.com/ca-en/eurobonus/points/use/partner-award-flights/',
        'book_url': 'https://www.flysas.com/en/award-finder',
        'skyteam_url': 'https://www.flysas.com/en/about-us/skyteam'
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    app.run(host='0.0.0.0', port=port, debug=False)
