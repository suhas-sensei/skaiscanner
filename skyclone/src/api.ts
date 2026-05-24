import type { FlightSearchResponse } from './types';

type GraphQLResponse<T> = {
  data?: T;
  errors?: { message: string }[];
  detail?: string;
  error?: string;
};

export type FlightSearchParams = {
  origin: string;
  destination: string;
  date: string;
  sort: string;
};

export async function searchFlights(params: FlightSearchParams): Promise<FlightSearchResponse> {
  const query = `
    query FlightOffers($origin: String!, $destination: String!, $date: String!, $sort: String!) {
      flightOffers(origin: $origin, destination: $destination, date: $date, sort: $sort, limit: 5000) {
        id
        provider
        origin
        destination
        departureDate
        returnDate
        tripType
        airline
        flightNumber
        departureTime
        arrivalTime
        duration
        stops
        stopAirports
        priceAmount
        currency
        providerUrl
        providerOfferUrl
        providerSearchUrl
        providerLinkStatus
        providerOfferKey
      }
      routeProviders(origin: $origin, destination: $destination, date: $date)
      stopFareSummary(origin: $origin, destination: $destination, date: $date) {
        direct {
          key
          count
          priceAmount
          currency
        }
        one {
          key
          count
          priceAmount
          currency
        }
        multi {
          key
          count
          priceAmount
          currency
        }
      }
    }
  `;

  const response = await fetch('/graphql/', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      query,
      variables: params
    })
  });
  const data = await response.json();
  if (!response.ok || data.errors?.length) {
    throw new Error(data.detail || data.error || 'Flight search failed.');
  }
  return {
    count: data.data.flightOffers.length,
    results: data.data.flightOffers,
    providers: data.data.routeProviders,
    stopFares: data.data.stopFareSummary
  };
}

async function graphql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch('/graphql/', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ query, variables })
  });
  const data: GraphQLResponse<T> = await response.json();
  if (!response.ok || data.errors?.length || !data.data) {
    throw new Error(data.errors?.[0]?.message || data.detail || data.error || 'GraphQL request failed.');
  }
  return data.data;
}

export async function requestEmailOtp(email: string) {
  const data = await graphql<{ requestEmailOtp: { ok: boolean; expiresAt: string } }>(
    `
      mutation RequestEmailOTP($email: String!) {
        requestEmailOtp(email: $email) {
          ok
          expiresAt
        }
      }
    `,
    { email }
  );
  return data.requestEmailOtp;
}

export async function verifyEmailOtp(email: string, code: string) {
  const data = await graphql<{ verifyEmailOtp: { ok: boolean; user: { email: string } | null } }>(
    `
      mutation VerifyEmailOTP($email: String!, $code: String!) {
        verifyEmailOtp(email: $email, code: $code) {
          ok
          user { email }
        }
      }
    `,
    { email, code }
  );
  return data.verifyEmailOtp;
}

export async function getViewer() {
  const data = await graphql<{ viewer: { email: string } | null }>(
    `
      query Viewer {
        viewer { email }
      }
    `
  );
  return data.viewer;
}

export async function signOut() {
  const data = await graphql<{ signOut: { ok: boolean } }>(
    `
      mutation SignOut {
        signOut { ok }
      }
    `
  );
  return data.signOut;
}
