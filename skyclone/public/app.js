const form = document.querySelector('#searchForm');
const statusEl = document.querySelector('#status');
const flightList = document.querySelector('#flightList');
const resultCount = document.querySelector('#resultCount');
const providerDrawer = document.querySelector('#providerDrawer');
const providerCount = document.querySelector('#providerCount');

let currentSearch = null;

function formatPrice(price, currency = 'INR') {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0
  }).format(price);
}

function minutesToDuration(minutes) {
  if (!Number.isFinite(Number(minutes))) return '';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${mins.toString().padStart(2, '0')}m`;
}

function formatDateTime(value) {
  if (!value) return '';
  const [date, time = ''] = String(value).split('T');
  return `
    <div class="date">${date}</div>
    <div class="clock">${time.slice(0, 5)}</div>
  `;
}

function plural(count, singular, pluralText = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralText}`;
}

function setStatus(message, type = 'neutral') {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function renderFlights(flights) {
  flightList.innerHTML = '';
  resultCount.textContent = `${flights.length} grouped flights`;

  for (const flight of flights) {
    const sourceCount = flight.sourceCount || flight.providerCount || 0;
    const offerCount = flight.offerCount || 0;
    const card = document.createElement('article');
    card.className = 'flight-card';
    card.dataset.flightKey = flight.flightKey;
    card.innerHTML = `
      <div>
        <div class="airline">${flight.airline}</div>
        <div class="flight-number">${flight.flightNumber}</div>
      </div>
      <div class="times">
        <div>
          <div class="time">${formatDateTime(flight.departureTime)}</div>
          <div class="meta">${flight.origin}</div>
        </div>
        <div>
          <div class="route-line"></div>
          <div class="meta">${minutesToDuration(flight.durationMinutes)}</div>
        </div>
        <div>
          <div class="time">${formatDateTime(flight.arrivalTime)}</div>
          <div class="meta">${flight.destination}</div>
        </div>
      </div>
      <div class="price">
        <span class="meta">${plural(sourceCount, 'source')} · ${plural(offerCount, 'offer')} from</span>
        <strong>${formatPrice(flight.cheapestPrice, flight.currency)}</strong>
        <span class="badge">${flight.stops === 0 ? 'Direct' : `${flight.stops} stop`}</span>
      </div>
    `;
    card.addEventListener('click', () => showProviders(flight.flightKey));
    flightList.append(card);
  }
}

function renderProviderDrawer(flight, providers) {
  providerDrawer.innerHTML = `
    <h3>${flight.airline} ${flight.flightNumber}</h3>
    <div class="provider-meta">${flight.origin} to ${flight.destination} · ${flight.departureTime} to ${flight.arrivalTime}</div>
    <div class="provider-list">
      ${providers.map((provider, index) => `
        <div class="provider-row">
          <div>
            <strong>${provider.name}</strong>
            <div class="provider-meta">
              ${index === 0 ? 'Cheapest source' : 'Source price'}
              ${provider.offerCount > 1 ? ` · ${plural(provider.offerCount, 'fare offer')}` : ''}
            </div>
          </div>
          <div class="provider-price">${formatPrice(provider.price, provider.currency)}</div>
        </div>
      `).join('')}
    </div>
  `;
}

async function showProviders(flightKey) {
  if (!currentSearch) return;

  document.querySelectorAll('.flight-card').forEach(card => {
    card.classList.toggle('active', card.dataset.flightKey === flightKey);
  });

  const flight = currentSearch.flights.find(item => item.flightKey === flightKey);
  providerDrawer.innerHTML = '<div class="empty-state">Loading provider prices...</div>';

  const response = await fetch(`/api/search/${currentSearch.searchId}/flights/${encodeURIComponent(flightKey)}/providers`);
  const data = await response.json();
  if (!response.ok) {
    providerDrawer.innerHTML = `<div class="empty-state">${data.error || 'Could not load providers.'}</div>`;
    return;
  }

  renderProviderDrawer(flight, data.providers);
}

async function loadProviders() {
  const response = await fetch('/api/providers');
  const data = await response.json();
  providerCount.textContent = `${data.providers.length} known providers`;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  button.disabled = true;
  flightList.innerHTML = '';
  providerDrawer.innerHTML = '<div class="empty-state">Select a flight to see provider prices.</div>';
  resultCount.textContent = '';
  setStatus('Searching providers in parallel...');

  const body = Object.fromEntries(new FormData(form).entries());
  try {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Search failed.');

    currentSearch = data;
    renderFlights(data.flights);
    const liveProviders = data.providerStats.filter(provider => provider.status === 'ok' && provider.offerCount > 0);
    const failedProviders = data.providerStats.filter(provider => provider.status === 'error');
    if (!data.flights.length) {
      setStatus(failedProviders.length
        ? `No prices returned. ${plural(failedProviders.length, 'live source')} failed.`
        : 'No live source prices were returned.',
        'warning');
    } else {
      setStatus(`${plural(liveProviders.length, 'live source')} returned ${plural(data.rawOfferCount, 'offer')}. Grouped into ${plural(data.flights.length, 'flight')}.`);
    }
  } catch (error) {
    setStatus(error.message, 'warning');
  } finally {
    button.disabled = false;
  }
});

function setDefaultDate() {
  const dateInput = form.elements.date;
  const date = new Date();
  date.setDate(date.getDate() + 8);
  dateInput.value = date.toISOString().slice(0, 10);
}

document.querySelectorAll('input[name="origin"], input[name="destination"]').forEach(input => {
  input.addEventListener('input', () => {
    input.value = input.value.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
  });
});

setDefaultDate();
loadProviders();
