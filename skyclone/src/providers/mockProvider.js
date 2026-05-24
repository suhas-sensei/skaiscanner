const flightTemplates = [
  { airline: 'IndiGo', flightNumber: '6E 493', departureTime: '06:35', arrivalTime: '08:55', durationMinutes: 140, stops: 0 },
  { airline: 'Air India', flightNumber: 'AI 764', departureTime: '08:10', arrivalTime: '10:30', durationMinutes: 140, stops: 0 },
  { airline: 'SpiceJet', flightNumber: 'SG 8263', departureTime: '10:25', arrivalTime: '12:50', durationMinutes: 145, stops: 0 },
  { airline: 'Akasa Air', flightNumber: 'QP 1321', departureTime: '13:40', arrivalTime: '16:05', durationMinutes: 145, stops: 0 },
  { airline: 'Air India Express', flightNumber: 'IX 1187', departureTime: '16:20', arrivalTime: '18:55', durationMinutes: 155, stops: 0 },
  { airline: 'IndiGo', flightNumber: '6E 2214', departureTime: '19:15', arrivalTime: '21:40', durationMinutes: 145, stops: 0 },
  { airline: 'Air India', flightNumber: 'AI 401', departureTime: '21:55', arrivalTime: '00:25', durationMinutes: 150, stops: 0 }
];

function hash(input) {
  let value = 2166136261;
  for (const char of input) {
    value ^= char.charCodeAt(0);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

function priceFor(providerName, index, query, template) {
  const seed = hash(`${providerName}|${query.origin}|${query.destination}|${query.date}|${template.flightNumber}`);
  const routeSpread = (hash(`${query.origin}${query.destination}`) % 1800) + 2800;
  const providerSpread = (seed % 1400) + index * 17;
  const stopPenalty = template.stops * 1200;
  return routeSpread + providerSpread + stopPenalty;
}

function bookingUrl(providerName, query) {
  const slug = providerName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return `https://example.com/${slug}/search?from=${query.origin}&to=${query.destination}&date=${query.date}`;
}

export function createMockProvider({ name, index }) {
  return {
    name,
    mode: 'demo',
    async search(query) {
      const seed = hash(`${name}|${query.origin}|${query.destination}|${query.date}`);
      const latency = 90 + (seed % 420);
      await new Promise(resolve => setTimeout(resolve, latency));

      return flightTemplates
        .filter((template, templateIndex) => ((seed + templateIndex + index) % 4) !== 0)
        .map(template => ({
          provider: name,
          airline: template.airline,
          flightNumber: template.flightNumber,
          origin: query.origin,
          destination: query.destination,
          departureTime: template.departureTime,
          arrivalTime: template.arrivalTime,
          durationMinutes: template.durationMinutes,
          stops: template.stops,
          price: priceFor(name, index, query, template),
          currency: 'INR',
          bookingUrl: bookingUrl(name, query),
          scrapedAt: new Date().toISOString()
        }));
    }
  };
}
