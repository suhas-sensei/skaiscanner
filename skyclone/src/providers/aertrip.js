const baseUrl = 'https://www.aertrip.com';
const userAgent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

export function createAertripProvider() {
  return {
    name: 'Aertrip',
    async search(query) {
      return searchAertrip(query);
    }
  };
}

async function searchAertrip(query) {
  const params = buildSearchParams(query);
  const searchUrl = `${baseUrl}/v2/flights?${params.toString()}`;
  const routeResponse = await fetch(searchUrl, {
    headers: commonHeaders(searchUrl)
  });
  const cookie = readSessionCookie(routeResponse);
  if (!cookie) {
    throw new Error('Aertrip did not issue a session cookie.');
  }

  const apiUrl = `${baseUrl}/api/v1/flights/search?${params.toString()}`;
  const searchResponse = await fetchJson(apiUrl, searchUrl, cookie);
  if (!searchResponse.success || !searchResponse.data?.sid) {
    throw new Error(`Aertrip search failed: ${JSON.stringify(searchResponse.errors || [])}`);
  }

  const { sid, vcodes_grp: groups, vcodes } = searchResponse.data;
  const resultGroups = Array.isArray(groups) && groups.length ? groups : [...(vcodes || []), 'search'];
  const offers = [];
  const seenOffers = new Set();

  for (let round = 0; round < 4; round += 1) {
    let done = false;
    for (const group of resultGroups) {
      const resultUrl = `${baseUrl}/api/v1/flights/results?${new URLSearchParams({
        sid,
        display_group_id: '1',
        vcodes_grp: group
      }).toString()}`;
      const result = await fetchJson(resultUrl, searchUrl, cookie);
      if (!result?.success || !result.data) continue;
      done = Boolean(result.data.done) || done;
      for (const offer of normalizeResultFlights(result.data.flights || [], searchUrl)) {
        const key = `${offer.provider}|${offer.flightNumber}|${offer.departureTime}|${offer.arrivalTime}|${offer.price}`;
        if (!seenOffers.has(key)) {
          seenOffers.add(key);
          offers.push(offer);
        }
      }
    }
    if (done || offers.length) break;
    await wait(1500);
  }

  return offers;
}

function buildSearchParams(query) {
  const params = new URLSearchParams({
    origin: query.origin,
    destination: query.destination,
    depart: toAertripDate(query.date),
    adult: String(query.passengers || 1),
    child: '0',
    infant: '0',
    trip_type: query.returnDate ? 'return' : 'single',
    cabinclass: 'Economy',
    pType: 'flight'
  });
  if (query.returnDate) params.set('return', toAertripDate(query.returnDate));
  return params;
}

function toAertripDate(date) {
  const [year, month, day] = date.split('-');
  return `${day}-${month}-${year}`;
}

function commonHeaders(referer) {
  return {
    accept: 'application/json',
    'accept-language': 'en-US',
    referer,
    'user-agent': userAgent
  };
}

async function fetchJson(url, referer, cookie) {
  const response = await fetch(url, {
    headers: {
      ...commonHeaders(referer),
      cookie
    }
  });
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Aertrip returned non-JSON response with status ${response.status}.`);
  }
}

function readSessionCookie(response) {
  const setCookie = response.headers.get('set-cookie') || '';
  const match = /AT_R_SESSID=([^;]+)/.exec(setCookie);
  return match ? `AT_R_SESSID=${match[1]}` : '';
}

function normalizeResultFlights(blocks, bookingUrl) {
  const offers = [];
  const scrapedAt = new Date().toISOString();
  for (const block of blocks) {
    for (const journey of block?.results?.j || []) {
      const firstLeg = journey.leg?.[0];
      const firstFlight = firstLeg?.flights?.[0];
      const lastLeg = journey.leg?.[journey.leg.length - 1];
      const lastFlight = lastLeg?.flights?.[lastLeg.flights?.length - 1] || firstFlight;
      if (!firstFlight || !lastFlight) continue;

      const price = Number(journey.fare?.grand_total?.value || journey.farepr || journey.net_fare);
      if (!Number.isFinite(price) || price <= 0) continue;

      offers.push({
        provider: 'Aertrip',
        airline: firstFlight.oc_name || firstFlight.al || journey.pca || 'Unknown airline',
        flightNumber: `${firstFlight.al || ''}${firstFlight.fn || ''}`.trim() || journey.fk,
        origin: firstFlight.fr,
        destination: lastFlight.to,
        departureTime: `${firstFlight.dd}T${firstFlight.dt}`,
        arrivalTime: `${lastFlight.ad}T${lastFlight.at}`,
        durationMinutes: minutesFromSeconds(journey.tt || firstLeg.tt || firstFlight.ft),
        stops: Number(journey.stp || firstLeg.stp || 0),
        price,
        currency: 'INR',
        bookingUrl,
        scrapedAt
      });
    }
  }
  return offers;
}

function minutesFromSeconds(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) ? Math.round(seconds / 60) : null;
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
