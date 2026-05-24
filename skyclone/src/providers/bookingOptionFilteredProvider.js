function firstValue(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '');
}

function toNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/[^\d.]/g, ''));
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function formatTime(value) {
  if (!value) return null;
  const text = String(value);
  const match = /(\d{1,2}):(\d{2})/.exec(text);
  if (match) return `${match[1].padStart(2, '0')}:${match[2]}`;

  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) return date.toISOString().slice(11, 16);

  return null;
}

function parseRawPayload(item) {
  const raw = item.Raw || item.raw || item.rawJson || item.raw_json;
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw === 'string' && raw.trim()) {
    try {
      return JSON.parse(raw);
    } catch {
      return item;
    }
  }
  return item;
}

function extractItems(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.offers)) return payload.offers;
  if (Array.isArray(payload?.results)) return payload.results;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.data?.offers)) return payload.data.offers;
  if (Array.isArray(payload?.data?.results)) return payload.data.results;
  return [];
}

function getOutboundLeg(raw) {
  return Array.isArray(raw?.legs) && raw.legs.length ? raw.legs[0] : null;
}

function getSegments(raw, leg = null) {
  return (leg ? [leg] : raw?.legs || [])
    .flatMap(currentLeg => currentLeg?.segments || [])
    .filter(Boolean);
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function withDate(dateText, time) {
  return dateText && time ? `${dateText}T${time}` : time;
}

function normalizePrice(price, currency) {
  const normalizedCurrency = String(currency || 'USD').toUpperCase();
  if (normalizedCurrency !== 'USD') return { price, currency: normalizedCurrency };

  const usdToInrRate = Number(process.env.USD_TO_INR_RATE || 83.5);
  return {
    price: Math.round(price * usdToInrRate),
    currency: 'INR'
  };
}

function normalizeFlightNumber(flightNumber, segment) {
  const value = String(flightNumber || '').replace(/\s+/g, '').toUpperCase();
  if (!value) return value;
  if (/^[A-Z0-9]{2}/.test(value) && /[A-Z]/.test(value.slice(0, 2))) return value;

  const code = firstValue(segment?.airline?.code, segment?.airlineCode);
  return code ? `${code}${value}` : value;
}

function normalizeBookingUrl(url) {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) return url;
  return `https://flights.agoda.com${url.startsWith('/') ? '' : '/'}${url}`;
}

function buildProviderUrl(baseUrl, query) {
  const params = new URLSearchParams({
    origin: query.origin,
    destination: query.destination,
    departureDate: query.date,
    adults: String(query.passengers || 1)
  });
  if (query.returnDate) params.set('returnDate', query.returnDate);
  return `${baseUrl}?${params.toString()}`;
}

function providerMatches(option, providerPatterns) {
  const provider = String(option?.provider || option?.providerName || option?.name || '');
  return providerPatterns.some(pattern => pattern.test(provider));
}

function normalizeOffer(item, option, query, providerName, defaultBookingUrlBase) {
  const raw = parseRawPayload(item);
  const firstLeg = getOutboundLeg(raw) || {};
  const segments = getSegments(raw, firstLeg);
  const firstSegment = segments[0] || item.segment || item.segments?.[0] || item;
  const lastSegment = segments[segments.length - 1] || firstSegment;
  const departureTime = formatTime(firstValue(firstSegment.departure, item.departureTime, item.departure_time));
  const arrivalTime = formatTime(firstValue(lastSegment.arrival, item.arrivalTime, item.arrival_time));
  const price = toNumber(firstValue(option.price, option.amount, option.total, option.priceFormatted));
  const normalizedPrice = normalizePrice(price, firstValue(option.currency, 'USD'));
  const arrivalDate = departureTime && arrivalTime && arrivalTime < departureTime ? addDays(query.date, 1) : query.date;

  return {
    provider: providerName,
    airline: firstValue(firstSegment.airline?.name, firstSegment.airlineName, item.airlineName, item.airline, 'Unknown airline'),
    flightNumber: normalizeFlightNumber(firstValue(firstSegment.flightNumber, item.flightNumber, item.flight_number, raw?.resultId), firstSegment),
    origin: firstValue(firstSegment.origin?.code, firstSegment.origin, item.origin, query.origin),
    destination: firstValue(lastSegment.destination?.code, lastSegment.destination, item.destination, query.destination),
    departureTime: withDate(query.date, departureTime),
    arrivalTime: withDate(arrivalDate, arrivalTime),
    durationMinutes: toNumber(firstValue(firstLeg.durationMinutes, firstSegment.durationMinutes, item.durationMinutes, item.duration_minutes)),
    stops: toNumber(firstValue(firstLeg.stops, firstSegment.stops, item.stops, item.stopCount, item.stop_count)) || 0,
    price: normalizedPrice.price,
    currency: normalizedPrice.currency,
    bookingUrl: normalizeBookingUrl(option.bookingUrl) || firstValue(raw?.shareableUrl, item['Agoda URL']) || buildProviderUrl(defaultBookingUrlBase, query),
    scrapedAt: new Date().toISOString()
  };
}

function buildApifyActorId() {
  return (process.env.APIFY_AGODA_ACTOR_ID || 'one-api/agoda-scraper').replace('/', '~');
}

function buildApifyInput(query, resultCountEnv) {
  return {
    flights_search_inputs: [`${query.origin}-${query.destination},${query.date}${query.returnDate ? `,${query.returnDate}` : ''}`],
    flights_search_adults: query.passengers || 1,
    flights_search_children: Number(process.env.APIFY_AGODA_FLIGHT_CHILDREN || 0),
    flights_search_infants: Number(process.env.APIFY_AGODA_FLIGHT_INFANTS || 0),
    flights_search_cabin: process.env.APIFY_AGODA_FLIGHT_CABIN || 'Economy',
    flights_search_sortOrder: process.env.APIFY_AGODA_FLIGHT_SORT || 'best',
    flights_search_resultCount: Number(process.env[resultCountEnv] || process.env.APIFY_AGODA_FLIGHT_RESULT_COUNT || 30),
    flights_details_inputs: []
  };
}

export function createBookingOptionFilteredProvider({
  providerName,
  providerPatterns,
  fallbackEnabledEnv,
  fallbackResultCountEnv,
  defaultBookingUrlBase
}) {
  async function searchWithApifyAgodaFallback(query) {
    const token = process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN;
    const url = new URL(`https://api.apify.com/v2/acts/${buildApifyActorId()}/run-sync-get-dataset-items`);
    url.searchParams.set('token', token);
    url.searchParams.set('format', 'json');
    url.searchParams.set('clean', 'true');

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json'
      },
      body: JSON.stringify(buildApifyInput(query, fallbackResultCountEnv))
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${providerName} Apify fallback returned HTTP ${response.status}: ${text.slice(0, 300)}`);
    }

    return extractItems(await response.json())
      .flatMap(item => {
        const raw = parseRawPayload(item);
        if (!raw?.price || !Array.isArray(raw?.legs)) return [];
        return (raw.bookingOptions || [])
          .filter(option => providerMatches(option, providerPatterns))
          .map(option => normalizeOffer(item, option, query, providerName, defaultBookingUrlBase));
      })
      .filter(offer => offer.price && offer.departureTime && offer.arrivalTime);
  }

  if ((process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN) && process.env[fallbackEnabledEnv] === '1') {
    return {
      name: providerName,
      mode: 'apify-agoda-booking-option',
      search: searchWithApifyAgodaFallback
    };
  }

  return null;
}
