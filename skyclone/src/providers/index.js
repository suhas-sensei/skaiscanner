import { createAertripProvider } from './aertrip.js';
import { createAgodaProviderAdapter } from './agodaProvider.js';
import { createAirIndiaProvider } from './airIndiaProvider.js';
import { createAirIndiaExpressProvider } from './airIndiaExpressProvider.js';
import { createAkasaAirProvider } from './akasaAirProvider.js';
import { createAkbarTravelsProvider } from './akbarTravelsProvider.js';

const providerNames = [
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
];

export function getProviderNames() {
  return providerNames;
}

export function createProviderAdapters() {
  const selected = new Set(
    String(process.env.SKYCLONE_PROVIDERS || '')
      .split(',')
      .map(name => name.trim())
      .filter(Boolean)
  );
  return [
    createAertripProvider(),
    createAgodaProviderAdapter(),
    createAirIndiaProvider(),
    createAirIndiaExpressProvider(),
    createAkasaAirProvider(),
    createAkbarTravelsProvider()
  ].filter(Boolean).filter(adapter => !selected.size || selected.has(adapter.name));
}
