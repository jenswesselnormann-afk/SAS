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
  wireAirportAutocomplete(form);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = formPayload(form);
    const data = await postJson('/api/search', payload);
    renderCalendar(document.getElementById(cfg.calendar), data.calendar, payload.provider || 'SAS');
    renderResults(document.getElementById(cfg.results), data.results);
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
    end.setDate(now.getDate() + 60);
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

function formPayload(form) {
  const fd = new FormData(form);
  const provider = fd.get('provider') || fd.get('provider_select') || 'SAS';
  return {
    provider,
    origin: normalizeAirportValue(fd.get('origin')),
    destination: normalizeAirportValue(fd.get('destination')),
    start_date: fd.get('start_date') || '',
    end_date: fd.get('end_date') || '',
    cabin: fd.get('cabin') || 'Any',
    passengers: Number(fd.get('passengers') || 1),
    direct_only: fd.get('direct_only') === 'on'
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

function renderCalendar(target, rows, provider) {
  if (!rows.length) {
    target.innerHTML = `<div class="card empty">Ingen kalenderfunn i dette intervallet.</div>`;
    return;
  }
  target.innerHTML = `
    <div class="card calendar-wrap">
      <div class="header"><div><h3>Kalenderoversikt</h3><div class="meta-line">Laveste poengpris per dato</div></div><span class="tag">${escapeHtml(provider)}</span></div>
      <div class="calendar-grid">${rows.map(r => `
        <a class="calendar-cell ghost-btn" href="${r.book_url}" target="_blank" rel="noreferrer">
          <div class="day">${r.date}</div>
          <div class="price">${fmt(r.points)}</div>
          <div class="meta-line">${escapeHtml(r.origin_label)} → ${escapeHtml(r.destination_label)}</div>
          <div class="meta-line">${r.cabin} · ${r.seats} seter</div>
          <div class="meta-line">${r.direct ? 'Direkte' : 'Ikke direkte'}</div>
        </a>`).join('')}</div>
    </div>`;
}

function renderResults(target, rows) {
  if (!rows.length) {
    target.innerHTML = `<div class="card empty">Ingen treff akkurat nå. Prøv flere datoer, annen cabin eller annen rute.</div>`;
    return;
  }
  target.innerHTML = `<div class="results-grid">${rows.map(cardHtml).join('')}</div>`;
}

function cardHtml(r) {
  return `
    <article class="result">
      <div class="row between wrap gap">
        <div>
          <div class="tag">${r.provider}${r.carrier ? ` · ${escapeHtml(r.carrier)}` : ''}</div>
          <h3>${escapeHtml(r.origin_label)} → ${escapeHtml(r.destination_label)}</h3>
          <div class="meta-line">${r.date} · ${r.cabin} · ${r.direct ? 'Direkte' : 'Ikke direkte'}</div>
        </div>
        <div class="good">Score ${Number(r.score || 0).toFixed(2)}</div>
      </div>
      <div class="results-grid mini-three">
        <div class="calendar-cell"><div class="day">Poeng</div><div class="price">${fmt(r.points)}</div></div>
        <div class="calendar-cell"><div class="day">Avgifter</div><div class="price">${fmt(r.taxes)}</div></div>
        <div class="calendar-cell"><div class="day">Seter</div><div class="price">${fmt(r.seats)}</div></div>
      </div>
      <div class="meta-line" style="margin-top:12px">Segmenter: ${escapeHtml((r.segments || []).join(' → ') || `${r.origin}-${r.destination}`)}</div>
      <div class="meta-line">Flytid: ${Math.floor((r.duration_minutes || 0) / 60)} t ${(r.duration_minutes || 0) % 60} m</div>
      <div class="meta-line">${escapeHtml(r.booking_note || '')}</div>
      <div class="row wrap gap" style="margin-top:12px">
        <a class="ghost-btn" href="${r.book_url}" target="_blank" rel="noreferrer">Book</a>
        <a class="ghost-btn" href="${r.find_url}" target="_blank" rel="noreferrer">Finn</a>
        <a class="ghost-btn" href="${r.info_url}" target="_blank" rel="noreferrer">Info</a>
      </div>
    </article>`;
}

function fmt(v) {
  return new Intl.NumberFormat('nb-NO').format(v || 0);
}

function escapeHtml(t) {
  return String(t || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

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
  document.getElementById('telegram-status').textContent = data.configured ? 'Telegram: konfigurert' : 'Telegram: ikke konfigurert';
}
loadTelegramStatus();

document.getElementById('telegram-test')?.addEventListener('click', async () => {
  const res = await fetch('/api/telegram/test', { method: 'POST' });
  const data = await res.json();
  alert(data.ok ? 'Telegram-test sendt' : (data.error || 'Kunne ikke sende'));
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
    payload.telegram_enabled = true;
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
    t.innerHTML = `<div class="empty">Ingen abonnement ennå.</div>`;
    return;
  }
  t.innerHTML = data.results.map(s => `
    <div class="result">
      <div class="row between wrap gap">
        <div>
          <div class="tag">${s.provider}</div>
          <strong>${s.origin} → ${s.destination}</strong>
          <div class="meta-line">${s.start_date || 'åpen start'} til ${s.end_date || 'åpen slutt'} · ${s.cabin} · ${s.passengers} pax</div>
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
  t.innerHTML = data.results.map(d => `<div class="result"><div class="tag">${d.provider}</div><div class="meta-line">${escapeHtml(d.route_key)}</div><div class="meta-line">${d.first_seen_at}</div></div>`).join('');
}
loadDiscoveries();

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
