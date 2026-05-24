import { getAgodaApifyItems } from './agodaApifyDataset.js';

function required(value, message) {
  if (value === undefined || value === null || value === '') {
    throw new Error(message);
  }
  return value;
}

function firstValue(...values) {
  return values.find(value => value !== undefined && value !== null && value !== '');
}

function deepFind(value, keyPattern) {
  const seen = new Set();
  const stack = [value];

  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== 'object' || seen.has(current)) continue;
    seen.add(current);

    if (Array.isArray(current)) {
      stack.push(...current);
      continue;
    }

    for (const [key, childValue] of Object.entries(current)) {
      if (keyPattern.test(key) && childValue !== undefined && childValue !== null && childValue !== '') {
        return childValue;
      }
      if (childValue && typeof childValue === 'object') {
        stack.push(childValue);
      }
    }
  }

  return null;
}

function toNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/[^\d.]/g, ''));
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function parseDurationMinutes(value) {
  const numeric = toNumber(value);
  if (numeric !== null) return numeric;
  if (!value) return null;

  const text = String(value).toLowerCase();
  const hours = /(\d+)\s*h/.exec(text)?.[1];
  const minutes = /(\d+)\s*m/.exec(text)?.[1];
  const total = Number(hours || 0) * 60 + Number(minutes || 0);
  return total || null;
}

function parseRawPayload(rawOffer) {
  const raw = rawOffer.Raw || rawOffer.raw || rawOffer.rawJson || rawOffer.raw_json;
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw === 'string' && raw.trim()) {
    try {
      return JSON.parse(raw);
    } catch {
      return rawOffer;
    }
  }
  return rawOffer;
}

const airlineCodes = {
  'air india': 'AI',
  akasa: 'QP',
  'akasa air': 'QP',
  indigo: '6E',
  spicejet: 'SG',
  'air india express': 'IX'
};

function getOutboundLeg(raw) {
  return Array.isArray(raw?.legs) && raw.legs.length ? raw.legs[0] : null;
}

function getSegments(raw, leg = getOutboundLeg(raw)) {
  return (leg ? [leg] : raw?.legs || [])
    .flatMap(leg => leg?.segments || [])
    .filter(Boolean);
}

function formatTime(value) {
  if (!value) return null;
  const text = String(value);
  const timeMatch = /(\d{1,2}):(\d{2})/.exec(text);
  if (timeMatch) {
    return `${timeMatch[1].padStart(2, '0')}:${timeMatch[2]}`;
  }

  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) {
    return date.toISOString().slice(11, 16);
  }

  return null;
}

function minutesBetween(startTime, endTime) {
  if (!startTime || !endTime) return null;
  const [startHour, startMinute] = startTime.split(':').map(Number);
  const [endHour, endMinute] = endTime.split(':').map(Number);
  let minutes = (endHour * 60 + endMinute) - (startHour * 60 + startMinute);
  if (minutes < 0) minutes += 24 * 60;
  return minutes;
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function withDate(dateText, time) {
  return dateText && time ? `${dateText}T${time}` : time;
}

function normalizeFlightNumber(airline, flightNumber, segment) {
  const value = String(flightNumber || '').replace(/\s+/g, '').toUpperCase();
  if (!value) return value;
  if (/^[A-Z0-9]{2}/.test(value) && /[A-Z]/.test(value.slice(0, 2))) return value;

  const code = firstValue(
    segment?.airline?.code,
    segment?.airlineCode,
    airlineCodes[String(airline || '').toLowerCase()]
  );
  return code ? `${code}${value}` : value;
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

function buildAgodaBookingUrl(query) {
  const params = new URLSearchParams({
    origin: query.origin,
    destination: query.destination,
    departureDate: query.date,
    adults: String(query.passengers || 1)
  });
  if (query.returnDate) params.set('returnDate', query.returnDate);
  return `https://www.agoda.com/flights/results?${params.toString()}`;
}

function extractOffers(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.offers)) return payload.offers;
  if (Array.isArray(payload?.results)) return payload.results;
  if (Array.isArray(payload?.data)) return payload.data;
  if (Array.isArray(payload?.data?.offers)) return payload.data.offers;
  if (Array.isArray(payload?.data?.results)) return payload.data.results;
  return [];
}

function getActorError(offer) {
  const summary = String(offer?.Summary || offer?.summary || '');
  return /^ERROR:/i.test(summary) && !/^ERROR:\s*Success\b/i.test(summary) ? summary : null;
}

function normalizeOffer(rawOffer, query) {
  const raw = parseRawPayload(rawOffer);
  const firstLeg = getOutboundLeg(raw) || {};
  const segments = getSegments(raw, firstLeg);
  const firstSegment = segments[0] || rawOffer.segment || rawOffer.segments?.[0] || rawOffer.legs?.[0] || rawOffer;
  const lastSegment = segments[segments.length - 1] || firstSegment;
  const priceBlock = raw?.price || rawOffer.price || {};
  const departureTime = formatTime(firstValue(
    firstSegment.departureTime,
    firstSegment.departure_time,
    firstSegment.departure,
    rawOffer.departureTime,
    rawOffer.departure_time,
    rawOffer.Departure,
    rawOffer['Departure Time'],
    deepFind(raw, /^departure(Time)?$/i)
  ));
  const arrivalTime = formatTime(firstValue(
    lastSegment.arrivalTime,
    lastSegment.arrival_time,
    lastSegment.arrival,
    rawOffer.arrivalTime,
    rawOffer.arrival_time,
    rawOffer.Arrival,
    rawOffer['Arrival Time'],
    deepFind(raw, /^arrival(Time)?$/i)
  ));
  const price = toNumber(firstValue(
    priceBlock.amount,
    priceBlock.total,
    priceBlock.price,
    rawOffer.totalPrice,
    rawOffer.total_price,
    rawOffer.price,
    rawOffer.Price,
    rawOffer.fare,
    deepFind(raw, /^(price|totalPrice|amount|fare)$/i)
  ));
  const airline = firstValue(
    firstSegment.airline?.name,
    firstSegment.airlineName,
    firstSegment.airline_name,
    firstSegment.airline,
    rawOffer.airlineName,
    rawOffer.airline_name,
    rawOffer.airline,
    rawOffer.Airline,
    rawOffer.Carrier,
    deepFind(raw, /^(airline(Name)?|carrier(Name)?)$/i)
  );
  const flightNumber = firstValue(
    firstSegment.flightNumber,
    firstSegment.flight_number,
    rawOffer.flightNumber,
    rawOffer.flight_number,
    rawOffer['Flight Number'],
    rawOffer.Flight,
    deepFind(raw, /^flight(Number)?$/i),
    rawOffer.resultId,
    rawOffer.ResultId,
    rawOffer['Result ID']
  );
  const normalizedFlightNumber = normalizeFlightNumber(airline, flightNumber, firstSegment);
  const normalizedPrice = normalizePrice(
    required(price, 'Agoda offer is missing price.'),
    firstValue(rawOffer.currency, priceBlock.currency, process.env.AGODA_CURRENCY, 'USD')
  );
  const arrivalDate = arrivalTime && departureTime && minutesBetween(departureTime, arrivalTime) < 24 * 60 &&
    toNumber(firstLeg.stops) === 0 &&
    arrivalTime < departureTime
    ? addDays(query.date, 1)
    : query.date;

  return {
    provider: 'Agoda',
    airline: required(airline, 'Agoda offer is missing airline.'),
    flightNumber: required(normalizedFlightNumber, 'Agoda offer is missing flight number.'),
    origin: firstValue(firstSegment.origin?.code, firstSegment.origin, firstSegment.from, rawOffer.origin, query.origin),
    destination: firstValue(lastSegment.destination?.code, lastSegment.destination, lastSegment.to, rawOffer.destination, query.destination),
    departureTime: required(withDate(query.date, departureTime), 'Agoda offer is missing departure time.'),
    arrivalTime: required(withDate(arrivalDate, arrivalTime), 'Agoda offer is missing arrival time.'),
    durationMinutes: parseDurationMinutes(firstValue(
      rawOffer.durationMinutes,
      rawOffer.duration_minutes,
      rawOffer.Duration,
      rawOffer['Total Duration'],
      firstLeg.durationMinutes,
      firstSegment.durationMinutes,
      deepFind(raw, /^duration(InMinutes|Minutes)?$/i)
    )) ||
      minutesBetween(departureTime, arrivalTime),
    stops: toNumber(firstValue(
      rawOffer.stops,
      rawOffer.stopCount,
      rawOffer.stop_count,
      rawOffer.Stops,
      firstLeg.stops,
      firstSegment.stops,
      deepFind(raw, /^(stops|stopCount)$/i)
    )) || 0,
    price: normalizedPrice.price,
    currency: normalizedPrice.currency,
    bookingUrl: firstValue(
      rawOffer.bookingUrl,
      rawOffer.booking_url,
      rawOffer.deepLink,
      rawOffer.deep_link,
      rawOffer['Agoda URL'],
      raw?.shareableUrl,
      rawOffer.Url,
      rawOffer.url,
      deepFind(raw, /^(bookingUrl|deepLink|url)$/i)
    ) ||
      buildAgodaBookingUrl(query),
    scrapedAt: new Date().toISOString()
  };
}

function buildRequestUrl(baseUrl, query) {
  const url = new URL(baseUrl);
  url.searchParams.set('origin', query.origin);
  url.searchParams.set('destination', query.destination);
  url.searchParams.set('date', query.date);
  url.searchParams.set('passengers', String(query.passengers || 1));
  if (query.returnDate) url.searchParams.set('returnDate', query.returnDate);
  if (process.env.AGODA_CURRENCY) url.searchParams.set('currency', process.env.AGODA_CURRENCY);
  return url;
}

function buildRequestBody(query) {
  return {
    origin: query.origin,
    destination: query.destination,
    date: query.date,
    returnDate: query.returnDate,
    passengers: query.passengers || 1,
    currency: process.env.AGODA_CURRENCY || 'INR'
  };
}

async function searchWithApify(query, context) {
  const items = await getAgodaApifyItems(query, context, process.env.APIFY_AGODA_FLIGHT_RESULT_COUNT);
  const errors = items.map(getActorError).filter(Boolean);
  const offers = items
    .filter(item => !getActorError(item))
    .filter(item => {
      const raw = parseRawPayload(item);
      return raw?.price && Array.isArray(raw?.legs) && raw.legs.length;
    })
    .map(offer => normalizeOffer(offer, query));

  if (!offers.length && errors.length) {
    throw new Error(`Apify Agoda actor failed: ${errors[0]}`);
  }

  return offers;
}

export function createAgodaProviderAdapter() {
  if (process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN) {
    return {
      name: 'Agoda',
      mode: 'apify',
      search: searchWithApify
    };
  }

  const endpoint = process.env.AGODA_FLIGHTS_API_URL;
  if (!endpoint) return null;

  return {
    name: 'Agoda',
    mode: 'live',
    async search(query) {
      const method = (process.env.AGODA_API_METHOD || 'GET').toUpperCase();
      const url = method === 'GET' ? buildRequestUrl(endpoint, query) : new URL(endpoint);
      const headers = { accept: 'application/json' };
      if (process.env.AGODA_API_KEY) {
        headers[process.env.AGODA_API_KEY_HEADER || 'x-api-key'] = process.env.AGODA_API_KEY;
      }

      const requestOptions = { method, headers };
      if (method !== 'GET') {
        headers['content-type'] = 'application/json';
        requestOptions.body = JSON.stringify(buildRequestBody(query));
      }

      const response = await fetch(url, requestOptions);
      if (!response.ok) {
        throw new Error(`Agoda returned HTTP ${response.status}`);
      }

      const payload = await response.json();
      return extractOffers(payload).map(offer => normalizeOffer(offer, query));
    }
  };
}
