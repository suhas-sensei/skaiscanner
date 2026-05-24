import { createBookingOptionFilteredProvider } from './bookingOptionFilteredProvider.js';

export function createAkbarTravelsProvider() {
  return createBookingOptionFilteredProvider({
    providerName: 'AkbarTravels.com',
    providerPatterns: [/akbar/i],
    fallbackEnabledEnv: 'AKBAR_TRAVELS_USE_AGODA_FALLBACK',
    fallbackResultCountEnv: 'AKBAR_TRAVELS_RESULT_COUNT',
    defaultBookingUrlBase: 'https://www.akbartravels.com/flights'
  });
}
