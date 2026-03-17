# EuroBonus Award Explorer V3.1

V3.1 er laget for deling som webapp på Mac + iPhone.

## Hva som er nytt
- delbar webapp-struktur
- provider-valg fra forsiden
- bedre kalender med full flyplassvisning
- PWA-klargjort for iPhone hjemskjerm
- Render/Railway/Fly.io-klar deploy
- gunicorn + healthcheck
- enklere hosting uten at brukeren må kjøre lokalt

## Lokal kjøring
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Deploy til Render
1. Lag nytt GitHub-repo og last opp innholdet i denne mappen.
2. I Render: velg **New +** → **Blueprint**.
3. Koble GitHub-repoet.
4. Render leser `render.yaml` automatisk.
5. Når deploy er ferdig får du en offentlig URL du kan dele.

Startkommando er allerede satt til:
```bash
gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT app:app
```

## PWA på iPhone
Når appen er hostet:
1. åpne lenken i Safari
2. trykk Del
3. velg **Legg til på Hjem-skjerm**

## Telegram
Sett miljøvariabler på hosten:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Viktig
Denne versjonen er fortsatt testbar/prototype på datalaget.
UI, deling og hosting er hovedløftet i V3.1.
Neste steg er ekte live-kilder for SAS + SkyTeam.
