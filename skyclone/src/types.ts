export type FlightOffer = {
  id: number;
  provider: string;
  origin: string;
  destination: string;
  departureDate: string;
  returnDate: string | null;
  tripType: string;
  airline: string;
  flightNumber: string;
  departureTime: string;
  arrivalTime: string;
  duration: string;
  stops: string;
  stopAirports: string[];
  priceAmount: string | null;
  currency: string;
  providerUrl: string;
  providerOfferUrl: string;
  providerSearchUrl: string;
  providerLinkStatus: string;
  providerOfferKey: string;
};

export type FlightSearchResponse = {
  count: number;
  results: FlightOffer[];
  providers: string[];
  stopFares: StopFareSummary;
};

export type Viewer = {
  email: string;
};

export type StopFare = {
  key: 'direct' | 'one' | 'multi';
  count: number;
  priceAmount: string | null;
  currency: string;
};

export type StopFareSummary = {
  direct: StopFare;
  one: StopFare;
  multi: StopFare;
};

export type ProviderOption = {
  name: string;
  sourceKey: string;
  priceAmount: string | null;
  currency: string;
  providerUrl: string;
  linkStatus: string;
  offerCount: number;
};

export type FlightGroup = {
  key: string;
  airline: string;
  flightNumber: string;
  origin: string;
  destination: string;
  departureTime: string;
  arrivalTime: string;
  duration: string;
  stops: string;
  stopAirports: string[];
  cheapestPriceAmount: string | null;
  currency: string;
  offerCount: number;
  providers: ProviderOption[];
};
