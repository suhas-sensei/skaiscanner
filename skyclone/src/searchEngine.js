import { createProviderAdapters } from './providers/index.js';

function flightKey(offer) {
  return [
    offer.airline,
    offer.flightNumber,
    offer.origin,
    offer.destination,
    offer.departureTime,
    offer.arrivalTime
  ].join('|');
}

function groupOffers(offers) {
  const groups = new Map();

  for (const offer of offers) {
    const key = flightKey(offer);
    if (!groups.has(key)) {
      groups.set(key, {
        flightKey: key,
        airline: offer.airline,
        flightNumber: offer.flightNumber,
        origin: offer.origin,
        destination: offer.destination,
        departureTime: offer.departureTime,
        arrivalTime: offer.arrivalTime,
        durationMinutes: offer.durationMinutes,
        stops: offer.stops,
        cheapestPrice: offer.price,
        currency: offer.currency,
        offers: []
      });
    }

    const group = groups.get(key);
    group.cheapestPrice = Math.min(group.cheapestPrice, offer.price);
    group.offers.push({
      name: offer.provider,
      price: offer.price,
      currency: offer.currency,
      bookingUrl: offer.bookingUrl,
      scrapedAt: offer.scrapedAt
    });
  }

  return [...groups.values()]
    .map(group => {
      const providers = groupProviders(group.offers);
      return {
        ...group,
        offerCount: group.offers.length,
        sourceCount: providers.length,
        providerCount: providers.length,
        providers
      };
    })
    .sort((a, b) => a.cheapestPrice - b.cheapestPrice || a.departureTime.localeCompare(b.departureTime));
}

function groupProviders(offers) {
  const providers = new Map();

  for (const offer of offers) {
    if (!providers.has(offer.name)) {
      providers.set(offer.name, {
        name: offer.name,
        price: offer.price,
        currency: offer.currency,
        bookingUrl: offer.bookingUrl,
        scrapedAt: offer.scrapedAt,
        offerCount: 0,
        offers: []
      });
    }

    const provider = providers.get(offer.name);
    provider.offerCount += 1;
    provider.offers.push(offer);
    if (offer.price < provider.price) {
      provider.price = offer.price;
      provider.currency = offer.currency;
      provider.bookingUrl = offer.bookingUrl;
      provider.scrapedAt = offer.scrapedAt;
    }
  }

  return [...providers.values()]
    .map(provider => ({
      ...provider,
      offers: provider.offers.sort((a, b) => a.price - b.price)
    }))
    .sort((a, b) => a.price - b.price || a.name.localeCompare(b.name));
}

export async function runFlightSearch(query) {
  const adapters = createProviderAdapters();
  if (!adapters.length) {
    return {
      flights: [],
      rawOfferCount: 0,
      providerStats: getUnconfiguredProviderStats()
    };
  }
  const settled = await Promise.allSettled(adapters.map(async adapter => {
    try {
      return {
        provider: adapter.name,
        offers: await adapter.search(query)
      };
    } catch (error) {
      error.provider = adapter.name;
      throw error;
    }
  }));

  const offers = [];
  const providerStats = [];

  for (const result of settled) {
    if (result.status === 'fulfilled') {
      offers.push(...result.value.offers);
      providerStats.push({
        name: result.value.provider,
        status: 'ok',
        offerCount: result.value.offers.length
      });
    } else {
      providerStats.push({
        name: result.reason?.provider || 'unknown',
        status: 'error',
        error: result.reason?.message || String(result.reason)
      });
    }
  }

  const configuredProviders = new Set(adapters.map(adapter => adapter.name));
  providerStats.push(
    ...getUnconfiguredProviderStats().filter(provider => !configuredProviders.has(provider.name))
  );

  return {
    flights: groupOffers(offers),
    rawOfferCount: offers.length,
    providerStats: providerStats.sort((a, b) => a.name.localeCompare(b.name))
  };
}

function getUnconfiguredProviderStats() {
  return [
    'Aertrip',
    'Agoda',
    'Air India',
    'Air India Express',
    'Akasa Air',
    'AkbarTravels.com',
    'Booking.com',
    'BudgetTicket',
    'Cleartrip',
    'Flightnetwork',
    'Flights Mojo',
    'Goibibo',
    'Gotogate',
    'Happyfares',
    'IndiGo',
    'Kiwi.com',
    'MakeMyTrip',
    'Paytm Travel',
    'skyticket',
    'TeaFlight',
    'Travomint',
    'Tripify',
    'VakaTrip.com',
    'Yatra.com'
  ].map(name => ({
    name,
    status: 'not_configured',
    offerCount: 0
  }));
}
