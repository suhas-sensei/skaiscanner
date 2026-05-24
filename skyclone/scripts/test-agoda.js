import '../src/env.js';
import { createAgodaProviderAdapter } from '../src/providers/agodaProvider.js';

const query = {
  origin: process.env.TEST_ORIGIN || 'DEL',
  destination: process.env.TEST_DESTINATION || 'BOM',
  date: process.env.TEST_DATE || new Date(Date.now() + 8 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  returnDate: process.env.TEST_RETURN_DATE || null,
  passengers: Number(process.env.TEST_PASSENGERS || 1)
};

const adapter = createAgodaProviderAdapter();

if (!adapter) {
  console.log(JSON.stringify({
    query,
    providerStats: [{ name: 'Agoda', status: 'not_configured', offerCount: 0 }],
    rawOfferCount: 0,
    firstOffer: null
  }, null, 2));
} else {
  const offers = await adapter.search(query);
  console.log(JSON.stringify({
    query,
    providerStats: [{ name: adapter.name, status: 'ok', offerCount: offers.length, mode: adapter.mode }],
    rawOfferCount: offers.length,
    firstOffer: offers[0] || null
  }, null, 2));
}
