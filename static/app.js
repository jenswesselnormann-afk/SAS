if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}

const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.panel');

tabs.forEach(tab => tab.addEventListener('click', () => {
  tabs.forEach(t => t.classList.remove('active'));
  panels.forEach(p => p.classList.remove('active'));
  tab.classList.add('active');
  document.getElementById(tab.dataset.tab)?.classList.add('active');
}));

const searchSections = {
  home: { panel: document.getElementById('home'), results: 'home-results', calendar: 'home-calendar' },
  sas: { panel: document.getElementById('sas'), results: 'sas-results', calendar: 'sas-calendar' },
  skyteam: { panel: document.getElementById('skyteam'), results: 'skyteam-results', calendar: 'skyteam-calendar' }
};

Object.entries(searchSections).forEach(([key, cfg]) => {
  const form = cfg.panel.querySelector('.search-form');
  const providerInput = form.querySelector('input[name="provider"]');
  const providerSelect = form.querySelector('select[name="provider_select"]');

  if (key === 'home') {
    providerInput.value = providerSelect?.value || 'SAS';
    providerSelect?.addEventListener('change', () => {
      providerInput.value = providerSelect.value;
    });
  } else {
    const forced = key === 'skyteam' ? 'SkyTeam' : 'SAS';
    providerInput.value = forced;
    if (providerSelect) {
      providerSelect.value = forced;
      providerSelect.disabled = true;
    }
  }

  setDefaultDates(form);
  wireSearchMode(form);
  wireAirportAutocomplete(form);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = formPayload(form);
    const data = await postJson('/api/search', payload);
    if (key === 'home') {
      const hint = document.getElementById('gateway-hint');
      hint.textContent = data.expanded_origins?.length > 1 ? `Sjekker også gateway-byer: ${data.expanded_origins.join(', ')}` : '';
    }
    renderCalendar(document.getElementById(cfg.calendar), data.calendar, payload.provider || 'SAS', payload);
    renderResults(document.getElementById(cfg.results), data.results, payload.mode);
    bindExport(form, payload);
  });
  bindExport(form, formPayload(form));
});

function setDefaultDates(form) {
  const s = form.querySelector('input[name="start_date"]');
  const e = form.querySelector('input[name="end_date"]');
  if (!s.value) {
    const now = new Date();
    const end = new Date();
    end.setDate(now.getDate() + 90);
    s.value = now.toISOString().slice(0, 10);
    e.value = end.toISOString().slice(0, 10);
  }
}

function bindExport(form, payload) {
  const link = form.querySelector('.export-link');
  if (!link) return;
  const qs = new URLSearchParams(payload);
  link.href = `/export.csv?${qs.toString()}`;
}

function wireSearchMode(form) {
  const mode = form.querySelector('select[name="mode"]');
  const destination = form.querySelector('input[name="destination"]');
  if (!mode || !destination) return;
  const sync = () => {
    const broad = mode.value === 'any_routes' || mode.value === 'most_hits';
    destination.required = !broad;
    destination.placeholder = broad ? 'Til, valgfritt for bredt søk' : 'Til, f.eks. JFK eller New York';
  };
  mode.addEventListener('change', sync);
  sync();
}

function formPayload(form) {
  const fd = new FormData(form);
  const provider = fd.get('provider') || fd.get('provider_select') || 'SAS';
  const mode = fd.get('mode') || 'route_search';
  const destination = normalizeAirportValue(fd.get('destination'));
  return {
    provider,
    mode,
    origin: normalizeAirportValue(fd.get('origin')),
    destination: (mode === 'any_routes' || mode === 'most_hits') ? '' : destination,
    start_date: fd.get('start_date') || '',
    end_date: fd.get('end_date') || '',
    cabin: fd.get('cabin') || 'Any',
    passengers: Number(fd.get('passengers') || 1),
    direct_only: fd.get('direct_only') === 'on',
    include_nearby: fd.get('include_nearby') === 'on'
  };
}

function normalizeAirportValue(v) {
  const txt = String(v || '').trim();
  const m = txt.match(/\b([A-Z]{3})\b/);
  return m ? m[1] : txt.toUpperCase();
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return await res.json();
}

function renderCalendar(target, rows, provider, payload) {
  if (!rows.length) {
    target.innerHTML = `<div class="card empty">Ingen kalenderfunn i dette intervallet. Prøv flere datoer, Any routes eller gateway-byer.</div>`;
    return;
  }
  const months = buildMonthBuckets(rows, payload.start_date, payload.end_date);
  const modeName = {
    route_search: 'Kalendersøk',
    any_routes: 'Any routes',
    best_value: 'Best value',
    most_hits: 'Flest hits'
  }[payload.mode] || 'Kalendersøk';
  target.innerHTML = `
    <div class="card calendar-wrap big-calendar">
      <div class="header"><div><h3>${modeName}</h3><div class="meta-line">Billigste award per dato · setetall vises i cellen</div></div><span class="tag ${providerClass(provider)}">${escapeHtml(provider)}</span></div>
      <div class="months-grid">${months.map(renderMonth).join('')}</div>
    </div>`;
}

function buildMonthBuckets(rows, startDate, endDate) {
  const byDate = Object.fromEntries(rows.map(r => [r.date, r]));
  const start = new Date(startDate || rows[0].date);
  const end = new Date(endDate || rows[rows.length - 1].date);
  const months = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cur <= end) {
    const year = cur.getFullYear();
    const month = cur.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const days = [];
    for (let i = 0; i < firstDay.getDay(); i++) days.push(null);
    for (let day = 1; day <= lastDay.getDate(); day++) {
      const date = new Date(year, month, day);
      const iso = date.toISOString().slice(0, 10);
      days.push(byDate[iso] || { date: iso, empty: true });
    }
    months.push({ label: firstDay.toLocaleDateString('nb-NO', { month: 'long', year: 'numeric' }), days });
    cur.setMonth(cur.getMonth() + 1);
  }
  return months;
}

function renderMonth(month) {
  return `
    <section class="month-card">
      <div class="month-title">${escapeHtml(month.label)}</div>
      <div class="weekdays"><span>Søn</span><span>Man</span><span>Tir</span><span>Ons</span><span>Tor</span><span>Fre</span><span>Lør</span></div>
      <div class="month-grid">${month.days.map(renderDay).join('')}</div>
    </section>`;
}

function renderDay(day) {
  if (!day) return `<div class="day-cell empty-slot"></div>`;
  const d = new Date(day.date);
  const label = d.getDate();
  if (day.empty) return `<div class="day-cell no-award"><div class="date-num">${label}</div><div class="micro muted">–</div></div>`;
  const reposition = day.origin && day.requested_origin && day.origin !== day.requested_origin;
  return `
    <a class="day-cell hit ${reposition ? 'reposition' : ''}" href="${day.book_url || '#'}" target="_blank" rel="noreferrer">
      <div class="date-num">${label}</div>
      <div class="points">${shortFmt(day.points)}</div>
      <div class="micro">${day.seats} seter</div>
      <div class="micro">${escapeHtml(day.origin || '')} → ${escapeHtml(day.destination || '')}</div>
    </a>`;
}

function renderResults(target, rows, mode = 'route_search') {
  if (!rows.length) {
    target.innerHTML = `<div class="card empty">Ingen treff akkurat nå. Prøv flere datoer, annen cabin, Any routes eller gateway-byer.</div>`;
    return;
  }
  const intro = {
    any_routes: 'Viser relevante ruter fra valgt avreiseflyplass og gateway-byer.',
    best_value: 'Rangert på poengmessig verdi, cabin, flytid og setetall.',
    most_hits: 'Sortert for å vise mest tilgjengelighet først.'
  }[mode] || 'Rangert etter dato og poeng.';
  target.innerHTML = `<div class="card" style="margin-bottom:12px"><div class="row between wrap gap"><div class="meta-line">${intro}</div><span class="tag">${rows.length} treff</span></div></div><div class="results-grid">${rows.map(r => cardHtml(r, mode)).join('')}</div>`;
}

function cardHtml(r, mode = 'route_search') {
  const searchDetails = formatSearchDetails(r);
  const providerCls = providerClass(r.provider);
  const isValueMode = mode === 'best_value';
  const modeBadge = isValueMode ? `<span class="tag value-badge">Best value</span>` : '';
  const gatewayBadge = r.reposition_required ? `<span class="tag gateway-badge">Gateway</span>` : '';
  return `
    <article class="result ${r.reposition_required ? 'result-reposition' : ''}">
      <div class="row between wrap gap result-head">
        <div>
          <div class="result-badges">
            <span class="tag ${providerCls}">${r.provider}${r.carrier ? ` · ${escapeHtml(r.carrier)}` : ''}</span>
            ${modeBadge}
            ${gatewayBadge}
          </div>
          <h3>${escapeHtml(r.origin_label)} → ${escapeHtml(r.destination_label)}</h3>
          <div class="meta-line">${r.date} · ${r.cabin} · ${r.direct ? 'Direkte' : 'Ikke direkte'}</div>
        </div>
        <div class="good strong">Score ${Number(r.score || 0).toFixed(2)}</div>
      </div>
      <div class="results-grid mini-three">
        <div class="calendar-cell"><div class="day">Poeng</div><div class="price">${fmt(r.points)}</div></div>
        <div class="calendar-cell"><div class="day">Avgifter</div><div class="price">${fmt(r.taxes)}</div></div>
        <div class="calendar-cell"><div class="day">Seter</div><div class="price">${fmt(r.seats)}</div></div>
      </div>
      <div class="meta-line" style="margin-top:12px">Segmenter: ${escapeHtml((r.segments || []).join(' → ') || `${r.origin}-${r.destination}`)}</div>
      <div class="meta-line">Flytid: ${Math.floor((r.duration_minutes || 0) / 60)} t ${(r.duration_minutes || 0) % 60} m</div>
      ${r.reposition_required ? `<div class="meta-line warn">${escapeHtml(r.reposition_note || '')}</div>` : ''}
      <div class="meta-line">${escapeHtml(r.booking_note || '')}</div>
      <div class="meta-line subtle">${escapeHtml(linkScopeText(r.provider))}</div>
      <div class="row wrap gap" style="margin-top:12px">
        <a class="ghost-btn primary" href="${r.book_url}" target="_blank" rel="noreferrer">Åpne bookingflyt</a>
        <a class="ghost-btn" href="${r.find_url}" target="_blank" rel="noreferrer">Åpne søkeresultat</a>
        <button class="ghost-btn copy-itinerary" type="button" data-copy="${escapeHtmlAttr(searchDetails)}">Kopier reisedetaljer</button>
        <a class="ghost-btn" href="${r.info_url}" target="_blank" rel="noreferrer">Regler/info</a>
      </div>
    </article>`;
}

function formatSearchDetails(r) {
  return [
    `${r.provider} ${r.carrier ? `(${r.carrier})` : ''}`.trim(),
    `${r.origin} -> ${r.destination}`,
    `Dato: ${r.date}`,
    `Cabin: ${r.cabin}`,
    `Seter: ${r.seats}`,
    `Poeng: ${r.points}`,
    `Avgifter: ${r.taxes}`,
    `Direkte: ${r.direct ? 'Ja' : 'Nei'}`,
    `Segmenter: ${(r.segments || []).join(' > ') || `${r.origin}-${r.destination}`}`,
    `Book: ${r.book_url}`,
    `Finn: ${r.find_url}`
  ].join('\n');
}

function linkScopeText(provider) {
  if (provider === 'SAS') {
    return 'SAS-lenker åpner riktig rute + måned. Endelig flightvalg gjøres i SAS Award Finder.';
  }
  return 'Partnerlenker åpner SAS partnerflyt/regler. Verifiser flightdetaljer i SAS før booking.';
}

function providerClass(provider) {
  if (provider === 'SkyTeam') return 'provider-skyteam';
  if (provider === 'Both') return 'provider-both';
  return 'provider-sas';
}

function fmt(v) {
  return new Intl.NumberFormat('nb-NO').format(v || 0);
}
function shortFmt(v) {
  return v >= 1000 ? `${Math.round(v / 1000)}k` : String(v || 0);
}

function escapeHtml(t) {
  return String(t || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}
function escapeHtmlAttr(t) {
  return escapeHtml(String(t || '')).replaceAll('\n', '&#10;');
}

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.copy-itinerary');
  if (!btn) return;
  const text = btn.getAttribute('data-copy')?.replaceAll('&#10;', '\n') || '';
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = 'Kopiert';
    setTimeout(() => { btn.textContent = 'Kopier reisedetaljer'; }, 1500);
  } catch (_) {
    alert('Kunne ikke kopiere automatisk. Prøv igjen.');
  }
});

async function loadValue() {
  const data = await (await fetch('/api/value-feed')).json();
  const t = document.getElementById('value-results');
  if (!data.results.length) {
    t.innerHTML = `<div class="empty">Ingen value-funn akkurat nå.</div>`;
    return;
  }
  t.innerHTML = `<div class="results-grid">${data.results.map(r => cardHtml({ ...r, carrier: r.value_tag })).join('')}</div>`;
}

document.getElementById('refresh-value')?.addEventListener('click', loadValue);
loadValue();

async function loadTelegramStatus() {
  const data = await (await fetch('/api/telegram/status')).json();
  const status = document.getElementById('telegram-status');
  const help = document.getElementById('telegram-help');
  status.textContent = data.configured ? 'Telegram-kanal: aktiv.' : `Telegram-kanal: mangler konfig. (${(data.missing || []).join(', ')})`;
  help.textContent = data.configured
    ? `Test knappen sender en ekte melding til chat-id i miljøvariablene. ${data.worker_hint || ''}`
    : `Legg til manglende miljøvariabler og deploy på nytt. ${data.worker_hint || ''}`;
}
loadTelegramStatus();

document.getElementById('telegram-test')?.addEventListener('click', async () => {
  const res = await fetch('/api/telegram/test', { method: 'POST' });
  const data = await res.json();
  if (data.ok) {
    alert('Telegram-test sendt. Sjekk chatten din.');
  } else {
    const missing = (data.missing || []).join(', ');
    alert(data.error || `Kunne ikke sende. Mangler: ${missing}`);
  }
});

const subForm = document.getElementById('subscription-form');
if (subForm) {
  setDefaultDates(subForm);
  wireAirportAutocomplete(subForm);
  subForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(subForm);
    const payload = Object.fromEntries(fd.entries());
    payload.origin = normalizeAirportValue(payload.origin);
    payload.destination = normalizeAirportValue(payload.destination);
    payload.direct_only = fd.get('direct_only') === 'on';
    payload.include_nearby = fd.get('include_nearby') === 'on';
    payload.telegram_enabled = fd.get('telegram_enabled') === 'on';
    payload.passengers = Number(payload.passengers || 1);
    payload.min_seats = Number(payload.min_seats || 1);
    const data = await postJson('/api/subscriptions', payload);
    if (data.ok) {
      subForm.reset();
      setDefaultDates(subForm);
      loadSubscriptions();
    }
  });
}

async function loadSubscriptions() {
  const data = await (await fetch('/api/subscriptions')).json();
  const t = document.getElementById('subscriptions');
  if (!data.results.length) {
    t.innerHTML = `<div class="empty">Ingen watchers ennå.</div>`;
    return;
  }
  t.innerHTML = data.results.map(s => `
    <div class="result">
      <div class="row between wrap gap">
        <div>
          <div class="tag ${providerClass(s.provider)}">${s.provider}</div>
          <strong>${s.origin} → ${s.destination}</strong>
          <div class="meta-line">${s.start_date || 'åpen start'} til ${s.end_date || 'åpen slutt'} · ${s.cabin} · ${s.passengers} pax · min ${s.min_seats} seter</div>
          <div class="meta-line">${s.include_nearby ? 'Gateway-byer er slått på' : 'Kun valgt avreiseflyplass'}</div>
          <div class="meta-line">Varslingskanaler: ${renderChannels(s.channels, s.telegram_enabled)}</div>
        </div>
        <button onclick="deleteSub(${s.id})">Slett</button>
      </div>
    </div>`).join('');
}
window.deleteSub = async (id) => {
  await fetch(`/api/subscriptions/${id}`, { method: 'DELETE' });
  loadSubscriptions();
};
loadSubscriptions();

async function loadDiscoveries() {
  const data = await (await fetch('/api/discoveries')).json();
  const t = document.getElementById('discoveries');
  if (!data.results.length) {
    t.innerHTML = `<div class="empty">Ingen nye funn ennå. Worker vil fylle dette når appen kjører hostet.</div>`;
    return;
  }
  t.innerHTML = data.results.map(d => `<div class="result"><div class="tag ${providerClass(d.provider)}">${d.provider}</div><div class="meta-line">${escapeHtml(d.route_key)}</div><div class="meta-line">${d.first_seen_at}</div></div>`).join('');
}
loadDiscoveries();

function renderChannels(channels, telegramEnabled) {
  const rows = Array.isArray(channels) ? channels : [];
  if (!rows.length) {
    return telegramEnabled ? 'Telegram (legacy)' : 'Ingen aktive';
  }
  const names = rows
    .filter(c => c.enabled)
    .map(c => c.channel === 'push' ? 'Push (ikke aktivert ennå)' : 'Telegram');
  return names.length ? names.join(', ') : 'Ingen aktive';
}

function wireAirportAutocomplete(container) {
  container.querySelectorAll('.combo input[name="origin"], .combo input[name="destination"]').forEach(input => {
    const box = input.parentElement.querySelector('.airport-suggestions');
    let timer = null;
    input.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = input.value.trim();
        if (!q) {
          box.classList.remove('open');
          box.innerHTML = '';
          return;
        }
        const data = await (await fetch(`/api/airports?q=${encodeURIComponent(q)}`)).json();
        if (!data.results.length) {
          box.classList.remove('open');
          box.innerHTML = '';
          return;
        }
        box.innerHTML = data.results.map(a => `<div class="airport-option" data-value="${a.code} · ${a.city} — ${a.name}"><div><span class="code">${a.code}</span> · ${escapeHtml(a.city)}</div><div class="meta-line">${escapeHtml(a.name)} · ${escapeHtml(a.country)}</div></div>`).join('');
        box.classList.add('open');
        box.querySelectorAll('.airport-option').forEach(opt => opt.addEventListener('click', () => {
          input.value = opt.dataset.value;
          box.classList.remove('open');
        }));
      }, 150);
    });
    document.addEventListener('click', (e) => {
      if (!input.parentElement.contains(e.target)) box.classList.remove('open');
    });
  });
}
