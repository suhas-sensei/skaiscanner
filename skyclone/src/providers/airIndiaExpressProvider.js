import {
  createAirlineFilteredProvider
} from './airlineFilteredProvider.js';

export function createAirIndiaExpressProvider() {
  return createAirlineFilteredProvider({
    providerName: 'Air India Express',
    airlineCodes: ['IX'],
    airlineNames: [/^Air India Express$/i],
    proxyEnvPrefix: 'AIR_INDIA_EXPRESS',
    fallbackEnabledEnv: 'AIR_INDIA_EXPRESS_USE_AGODA_FALLBACK',
    fallbackResultCountEnv: 'AIR_INDIA_EXPRESS_RESULT_COUNT',
    defaultBookingUrlBase: 'https://www.airindiaexpress.com/booking'
  });
}
