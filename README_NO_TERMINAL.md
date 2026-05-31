# Delbar nettversjon uten terminal

Dette er den enkleste veien til en offentlig lenke du kan sende til Sarah.

## Det du trenger
- en GitHub-konto
- en Render-konto

## Del 1: Last opp til GitHub i nettleseren
1. Gå til GitHub og lag et nytt **public** eller **private** repo.
2. Pakk ut zip-filen lokalt.
3. Inne på repoet i GitHub: trykk **Add file** → **Upload files**.
4. Dra inn **alle filene inni mappen** `sas_award_v3_1_shareable`.
5. Trykk **Commit changes**.

## Del 2: Få offentlig lenke i Render
1. Gå til Render.
2. Velg **New +** → **Blueprint**.
3. Koble GitHub-kontoen din.
4. Velg repoet du nettopp lastet opp.
5. Render finner `render.yaml` automatisk.
6. Trykk **Apply** / **Create**.
7. Vent til deploy er ferdig.
8. Du får en offentlig URL som ser omtrent slik ut:
   `https://sas-award-v3-1.onrender.com`

Den linken kan du sende direkte til Sarah.

## iPhone
Når siden er live:
1. Åpne linken i Safari.
2. Trykk **Del**.
3. Velg **Legg til på Hjem-skjerm**.

Da oppfører den seg mer som en app.

## Telegram-varsler
Legg disse inn i Render under Environment Variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Viktig
Jeg kan ikke publisere appen til en offentlig URL fra chatten her.
Jeg kan gjøre koden helt klar for hosting, men selve publiseringen må skje i GitHub/Render-kontoen din.
