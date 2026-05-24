function queryKey(query) {
  return [
    query.origin,
    query.destination,
    query.date,
    query.returnDate || '',
    query.passengers || 1
  ].join('|');
}

function buildApifyActorId() {
  return (process.env.APIFY_AGODA_ACTOR_ID || 'one-api/agoda-scraper').replace('/', '~');
}

function buildApifyInput(query, resultCount) {
  const searchInput = `${query.origin}-${query.destination},${query.date}${query.returnDate ? `,${query.returnDate}` : ''}`;

  return {
    flights_search_inputs: [searchInput],
    flights_search_adults: query.passengers || 1,
    flights_search_children: Number(process.env.APIFY_AGODA_FLIGHT_CHILDREN || 0),
    flights_search_infants: Number(process.env.APIFY_AGODA_FLIGHT_INFANTS || 0),
    flights_search_cabin: process.env.APIFY_AGODA_FLIGHT_CABIN || 'Economy',
    flights_search_sortOrder: process.env.APIFY_AGODA_FLIGHT_SORT || 'best',
    flights_search_resultCount: Number(resultCount || process.env.APIFY_AGODA_FLIGHT_RESULT_COUNT || 30),
    flights_details_inputs: []
  };
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

export async function getAgodaApifyItems(query, context = {}, resultCount = null) {
  const key = queryKey(query);
  context.agodaApifyItemsByQuery ||= new Map();
  if (context.agodaApifyItemsByQuery.has(key)) {
    return context.agodaApifyItemsByQuery.get(key);
  }

  const token = process.env.APIFY_TOKEN || process.env.APIFY_API_TOKEN;
  if (!token) throw new Error('APIFY_TOKEN is required for Agoda Apify source.');

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
    body: JSON.stringify(buildApifyInput(query, resultCount))
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Apify Agoda actor returned HTTP ${response.status}: ${errorText.slice(0, 300)}`);
  }

  const items = extractItems(await response.json());
  context.agodaApifyItemsByQuery.set(key, items);
  return items;
}
