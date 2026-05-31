from __future__ import annotations

GATEWAY_GROUPS = {
    'OSL': ['OSL', 'ARN', 'CPH', 'LHR', 'AMS', 'CDG', 'FRA'],
    'TRD': ['TRD', 'OSL', 'ARN', 'CPH', 'LHR', 'AMS'],
    'BGO': ['BGO', 'OSL', 'ARN', 'CPH', 'LHR', 'AMS'],
    'SVG': ['SVG', 'OSL', 'CPH', 'AMS', 'LHR'],
    'ARN': ['ARN', 'OSL', 'CPH', 'LHR', 'AMS', 'CDG'],
    'CPH': ['CPH', 'OSL', 'ARN', 'LHR', 'AMS', 'CDG'],
}

DEFAULT_GATEWAYS = ['LHR', 'AMS', 'CDG', 'FRA', 'CPH', 'ARN']


def expand_origins(origin: str, include_nearby: bool = False):
    code = (origin or '').upper().strip()
    if not code:
        return []
    if not include_nearby:
        return [code]
    if code in GATEWAY_GROUPS:
        return GATEWAY_GROUPS[code]
    out = [code]
    for g in DEFAULT_GATEWAYS:
        if g != code:
            out.append(g)
    return out
