# EuroBonus Award Explorer

Denne versjonen prioriterer sannferdighet:
- SAS-resultater hentes live fra `future.flysas.com/bff/award-finder/*`.
- Kalenderen bygges kun fra verifiserte live-resultater.
- SkyTeam/partner-resultater er ikke live-integrert og markeres/deaktiveres.
- Value-feed er deaktivert inntil poeng/avgift kan hentes live.

## Konfigurasjon
- `SAS_AWARD_BASE_URL` (default: `https://future.flysas.com`)
- `SAS_AWARD_MARKET` (default: `no-no`)
- `SAS_AWARD_TIMEOUT_SECONDS` (default: `15`)
- `SAS_AWARD_MAX_MONTHS` (default: `12`)
