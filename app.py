from __future__ import annotations
import csv
import io
import os
from flask import Flask, jsonify, render_template, request, Response, send_from_directory
from services.storage import init_db, add_subscription, list_subscriptions, delete_subscription, list_discoveries
from services.airports import search_airports
from services.demo_engine import find_results, build_calendar, build_value_feed
from services.telegram import is_configured, send_message

app = Flask(__name__)
init_db()


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


@app.route('/api/search', methods=['POST'])
def api_search():
    payload = request.get_json(force=True)
    provider = payload.get('provider', 'SAS')
    results = find_results(
        provider,
        payload.get('origin', ''),
        payload.get('destination', ''),
        payload.get('start_date', ''),
        payload.get('end_date', ''),
        payload.get('cabin', 'Any'),
        int(payload.get('passengers', 1)),
        bool(payload.get('direct_only', False)),
    )
    return jsonify({'results': results, 'calendar': build_calendar(results), 'count': len(results), 'provider': provider})


@app.route('/api/value-feed')
def api_value_feed():
    sas = find_results('SAS', '', '', '', '', 'Any', 1, False)
    sky = find_results('SkyTeam', '', '', '', '', 'Any', 1, False)
    rows = build_value_feed(sas + sky)
    return jsonify({'results': rows, 'count': len(rows)})


@app.route('/api/subscriptions', methods=['GET', 'POST'])
def api_subscriptions():
    if request.method == 'POST':
        payload = request.get_json(force=True)
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
    return jsonify({'configured': is_configured()})


@app.route('/api/telegram/test', methods=['POST'])
def api_telegram_test():
    result = send_message('✅ Testvarsel fra EuroBonus Award Explorer V3.1')
    status = 200 if result.get('ok') else 400
    return jsonify(result), status


@app.route('/export.csv')
def export_csv():
    results = find_results(
        request.args.get('provider', 'SAS'),
        request.args.get('origin', ''),
        request.args.get('destination', ''),
        request.args.get('start_date', ''),
        request.args.get('end_date', ''),
        request.args.get('cabin', 'Any'),
        int(request.args.get('passengers', 1)),
        request.args.get('direct_only', 'false').lower() == 'true',
    )
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=['provider', 'carrier', 'origin_label', 'destination_label', 'date', 'cabin', 'seats', 'points', 'taxes', 'direct', 'segments', 'score', 'book_url']
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
