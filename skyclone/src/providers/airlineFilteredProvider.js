import { getAgodaApifyItems } from './agodaApifyDataset.js';

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

function getOutboundLeg(raw) {
  return Array.isArray(raw?.legs) && raw.legs.length ? raw.legs[0] : null;
}

function getSegments(raw, leg = null) {
  return (leg ? [leg] : raw?.legs || [])
    .flatMap(leg => leg?.segments || [])
    .filter(Boolean);
}

function isMatchingAirline(raw, airlineCodes, airlineNames) {
  return getSegments(raw).some(segment => {
    const airlineName = String(segment?.airline?.name || segment?.airlineName || segment?.airline || '');
    const airlineCode = String(segment?.airline?.code || segment?.airlineCode || '');
    return airlineCodes.includes(airlineCode) || airlineNames.some(pattern => pattern.test(airlineName));
  });
}

function buildBookingUrl(baseUrl, query) {
  const params = new URLSearchParams({
    origin: query.origin,
    destination: query.destination,
    departureDate: query.date,
    adults: String(query.passengers || 1)
  });
  if (query.returnDate) params.set('returnDate', query.returnDate);
  return `${baseUrl}?${params.toString()}`;
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
  if (normalizedCurrency !== 'USD') {
    return { price, currency: normalizedCurrency };
  }

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

function normalizeOffer(item, query, providerName, defaultBookingUrlBase, currencyEnv) {
  const raw = parseRawPayload(item);
  const firstLeg = getOutboundLeg(raw) || {};
  const segments = getSegments(raw, firstLeg);
  const firstSegment = segments[0] || item.segment || item.segments?.[0] || item;
  const lastSegment = segments[segments.length - 1] || firstSegment;
  const priceBlock = raw?.price || item.price || {};
  const departureTime = formatTime(firstValue(firstSegment.departure, item.departureTime, item.departure_time));
  const arrivalTime = formatTime(firstValue(lastSegment.arrival, item.arrivalTime, item.arrival_time));
  const price = toNumber(firstValue(priceBlock.price, priceBlock.amount, priceBlock.total, item.totalPrice, item.total_price, item.price, item.Price));
  const normalizedPrice = normalizePrice(price, firstValue(priceBlock.currency, item.currency, process.env[currencyEnv], 'USD'));
  const arrivalDate = departureTime && arrivalTime && arrivalTime < departureTime ? addDays(query.date, 1) : query.date;

  return {
    provider: providerName,
    airline: firstValue(firstSegment.airline?.name, firstSegment.airlineName, item.airlineName, item.airline, providerName),
    flightNumber: normalizeFlightNumber(firstValue(firstSegment.flightNumber, item.flightNumber, item.flight_number, raw?.resultId), firstSegment),
    origin: firstValue(firstSegment.origin?.code, firstSegment.origin, item.origin, query.origin),
    destination: firstValue(lastSegment.destination?.code, lastSegment.destination, item.destination, query.destination),
    departureTime: withDate(query.date, departureTime),
    arrivalTime: withDate(arrivalDate, arrivalTime),
    durationMinutes: toNumber(firstValue(firstLeg.durationMinutes, firstSegment.durationMinutes, item.durationMinutes, item.duration_minutes)),
    stops: toNumber(firstValue(firstLeg.stops, firstSegment.stops, item.stops, item.stopCount, item.stop_count)) || 0,
    price: normalizedPrice.price,
    currency: normalizedPrice.currency,
    bookingUrl: firstValue(item.bookingUrl, item.booking_url, raw?.shareableUrl) || buildBookingUrl(defaultBookingUrlBase, query),
    scrapedAt: new Date().toISOString()
  };
}

function envName(prefix, suffix) {
  return `${prefix}_${suffix}`;
}

function buildProxyUrl(baseUrl, query, currencyEnv) {
  const url = new URL(baseUrl);
  url.searchParams.set('origin', query.origin);
  url.searchParams.set('destination', query.destination);
  url.searchParams.set('date', query.date);
  url.searchParams.set('passengers', String(query.passengers || 1));
  if (query.returnDate) url.searchParams.set('returnDate', query.returnDate);
  if (process.env[currencyEnv]) url.searchParams.set('currency', process.env[currencyEnv]);
  return url;
}

function buildProxyBody(query, currencyEnv) {
  return {
    origin: query.origin,
    destination: query.destination,
    date: query.date,
    returnDate: query.returnDate,
    passengers: query.passengers || 1,
    currency: process.env[currencyEnv] || 'INR'
  };
}

export function createAirlineFilteredProvider({
  providerName,
  airlineCodes,
  airlineNames,
  proxyEnvPrefix,
  fallbackEnabledEnv,
  fallbackResultCountEnv,
  defaultBookingUrlBase
}) {
  const urlEnv = envName(proxyEnvPrefix, 'FLIGHTS_API_URL');
  const methodEnv = envName(proxyEnvPrefix, 'API_METHOD');
  const keyEnv = envName(proxyEnvPrefix, 'API_KEY');
  const keyHeaderEnv = envName(proxyEnvPrefix, 'API_KEY_HEADER');
  const currencyEnv = envName(proxyEnvPrefix, 'CURRENCY');

  async function searchWithProxy(query) {
    const method = (process.env[methodEnv] || 'GET').toUpperCase();
    const url = method === 'GET' ? buildProxyUrl(process.env[urlEnv], query, currencyEnv) : new URL(process.env[urlEnv]);
    const headers = { accept: 'application/json' };
    if (process.env[keyEnv]) headers[process.env[keyHeaderEnv] || 'x-api-key'] = process.env[keyEnv];

    const options = { method, headers };
    if (method !== 'GET') {
      headers['content-type'] = 'application/json';
      options.body = JSON.stringify(buildProxyBody(query, currencyEnv));
    }

    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`${providerName} endpoint returned HTTP ${response.status}`);
    return extractItems(await response.json())
      .map(item => normalizeOffer(item, query, providerName, defaultBookingUrlBase, currencyEnv))
      .filter(offer => offer.price && offer.departureTime && offer.arrivalTime);
  }

  async function searchWithApifyAgodaFallback(query, context) {
    return (await getAgodaApifyItems(query, context, process.env[fallbackResultCountEnv]))
      .map(item => ({ item, raw: parseRawPayload(item) }))
      .filter(({ raw }) => raw?.price && Array.isArray(raw?.legs) && isMatchingAirline(raw, airlineCodes, airlineNames))
      .map(({ item }) => normalizeOffer(item, query, providerName, defaultBookingUrlBase, currencyEnv))
      .filter(offer => offer.price && offer.departureTime && offer.arrivalTime);
  }

  if (process.env[urlEnv]) {
    return {
      name: providerName,
      mode: 'live',
      search: searchWithProxy
    };
  }

  if ((process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN) && process.env[fallbackEnabledEnv] === '1') {
    return {
      name: providerName,
      mode: 'apify-agoda-filter',
      search: searchWithApifyAgodaFallback
    };
  }

  return null;
}
