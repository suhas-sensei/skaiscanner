import { createAirlineFilteredProvider } from './airlineFilteredProvider.js';

export function createAkasaAirProvider() {
  return createAirlineFilteredProvider({
    providerName: 'Akasa Air',
    airlineCodes: ['QP'],
    airlineNames: [/^Akasa Air$/i],
    proxyEnvPrefix: 'AKASA_AIR',
    fallbackEnabledEnv: 'AKASA_AIR_USE_AGODA_FALLBACK',
    fallbackResultCountEnv: 'AKASA_AIR_RESULT_COUNT',
    defaultBookingUrlBase: 'https://www.akasaair.com'
  });
}
