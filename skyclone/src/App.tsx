import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  ArrowLeftRight,
  ArrowRight,
  Bed,
  Bell,
  Calendar,
  Car,
  ChevronLeft,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Globe2,
  Heart,
  Info,
  MapPinned,
  Plane,
  Search,
  Sparkles,
  UserCircle
} from 'lucide-react';

import { getViewer, requestEmailOtp, searchFlights, signOut, verifyEmailOtp } from './api';
import type { FlightGroup, FlightOffer, ProviderOption, StopFareSummary, Viewer } from './types';

const defaultDate = new Date(Date.now() + 8 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

type DateFare = {
  date: string;
  label: string;
  priceAmount: string | null;
  currency: string;
  count: number;
};

type AirportOption = {
  code: string;
  city: string;
  name: string;
  country: string;
};

const emptyStopFareSummary: StopFareSummary = {
  direct: { key: 'direct', count: 0, priceAmount: null, currency: 'INR' },
  one: { key: 'one', count: 0, priceAmount: null, currency: 'INR' },
  multi: { key: 'multi', count: 0, priceAmount: null, currency: 'INR' }
};

const airportOptions: AirportOption[] = [
  { code: 'DEL', city: 'New Delhi', name: 'Indira Gandhi International', country: 'India' },
  { code: 'BOM', city: 'Mumbai', name: 'Chhatrapati Shivaji Maharaj International', country: 'India' },
  { code: 'BLR', city: 'Bengaluru', name: 'Kempegowda International', country: 'India' },
  { code: 'HYD', city: 'Hyderabad', name: 'Rajiv Gandhi International', country: 'India' },
  { code: 'CCU', city: 'Kolkata', name: 'Netaji Subhas Chandra Bose International', country: 'India' },
  { code: 'MAA', city: 'Chennai', name: 'Chennai International', country: 'India' },
  { code: 'AMD', city: 'Ahmedabad', name: 'Sardar Vallabhbhai Patel International', country: 'India' },
  { code: 'PNQ', city: 'Pune', name: 'Pune Airport', country: 'India' },
  { code: 'GOI', city: 'Goa', name: 'Dabolim Airport', country: 'India' },
  { code: 'COK', city: 'Kochi', name: 'Cochin International', country: 'India' },
  { code: 'JAI', city: 'Jaipur', name: 'Jaipur International', country: 'India' },
  { code: 'LKO', city: 'Lucknow', name: 'Chaudhary Charan Singh International', country: 'India' },
  { code: 'IXA', city: 'Agartala', name: 'Maharaja Bir Bikram Airport', country: 'India' },
  { code: 'IXB', city: 'Bagdogra', name: 'Bagdogra Airport', country: 'India' },
  { code: 'IXC', city: 'Chandigarh', name: 'Shaheed Bhagat Singh International', country: 'India' },
  { code: 'IXD', city: 'Prayagraj', name: 'Prayagraj Airport', country: 'India' },
  { code: 'IXE', city: 'Mangaluru', name: 'Mangaluru International', country: 'India' },
  { code: 'IXG', city: 'Belagavi', name: 'Belagavi Airport', country: 'India' },
  { code: 'IXI', city: 'Lilabari', name: 'North Lakhimpur Airport', country: 'India' },
  { code: 'IXJ', city: 'Jammu', name: 'Jammu Airport', country: 'India' },
  { code: 'IXL', city: 'Leh', name: 'Kushok Bakula Rimpochee Airport', country: 'India' },
  { code: 'IXM', city: 'Madurai', name: 'Madurai Airport', country: 'India' },
  { code: 'IXR', city: 'Ranchi', name: 'Birsa Munda Airport', country: 'India' },
  { code: 'IXS', city: 'Silchar', name: 'Silchar Airport', country: 'India' },
  { code: 'IXU', city: 'Aurangabad', name: 'Chhatrapati Sambhajinagar Airport', country: 'India' },
  { code: 'IXW', city: 'Jamshedpur', name: 'Sonari Airport', country: 'India' },
  { code: 'IXY', city: 'Kandla', name: 'Kandla Airport', country: 'India' },
  { code: 'IXZ', city: 'Port Blair', name: 'Veer Savarkar International', country: 'India' },
  { code: 'DXB', city: 'Dubai', name: 'Dubai International', country: 'United Arab Emirates' },
  { code: 'SIN', city: 'Singapore', name: 'Singapore Changi', country: 'Singapore' },
  { code: 'BKK', city: 'Bangkok', name: 'Suvarnabhumi Airport', country: 'Thailand' },
  { code: 'KUL', city: 'Kuala Lumpur', name: 'Kuala Lumpur International', country: 'Malaysia' },
  { code: 'LHR', city: 'London', name: 'Heathrow Airport', country: 'United Kingdom' },
  { code: 'JFK', city: 'New York', name: 'John F. Kennedy International', country: 'United States' },
  { code: 'SFO', city: 'San Francisco', name: 'San Francisco International', country: 'United States' },
  { code: 'CDG', city: 'Paris', name: 'Charles de Gaulle', country: 'France' },
  { code: 'FRA', city: 'Frankfurt', name: 'Frankfurt Airport', country: 'Germany' },
  { code: 'HND', city: 'Tokyo', name: 'Haneda Airport', country: 'Japan' }
];

const airportAliases: Record<string, string> = {
  AHM: 'AMD',
  AHMD: 'AMD',
  AHMEDABAD: 'AMD',
  AMDABAD: 'AMD',
  BANGALORE: 'BLR',
  BENGALURU: 'BLR',
  BOMBAY: 'BOM',
  CALCUTTA: 'CCU',
  CHENNAI: 'MAA',
  DELHI: 'DEL',
  KOL: 'CCU',
  KOLKATA: 'CCU',
  MUMBAI: 'BOM',
  NEWDELHI: 'DEL'
};

function formatPrice(value: string | null, currency: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return 'Price unavailable';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0
  }).format(amount);
}

function formatShortPrice(value: string | null, currency: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return 'No fares';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0
  }).format(amount);
}

function addDays(isoDate: string, offset: number) {
  const nextDate = new Date(`${isoDate}T00:00:00`);
  nextDate.setDate(nextDate.getDate() + offset);
  return nextDate.toISOString().slice(0, 10);
}

function addMonths(dateValue: Date, offset: number) {
  return new Date(dateValue.getFullYear(), dateValue.getMonth() + offset, 1);
}

function toIsoDate(dateValue: Date) {
  const year = dateValue.getFullYear();
  const month = String(dateValue.getMonth() + 1).padStart(2, '0');
  const day = String(dateValue.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function monthKey(dateValue: Date) {
  return `${dateValue.getFullYear()}-${dateValue.getMonth()}`;
}

function formatSearchDate(isoDate: string) {
  if (!isoDate) return 'Add date';
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  }).format(new Date(`${isoDate}T00:00:00`));
}

function formatDateLabel(isoDate: string) {
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short'
  }).format(new Date(`${isoDate}T00:00:00`));
}

function cheapestOffer(offers: FlightOffer[]) {
  return offers.reduce<FlightOffer | null>((cheapest, offer) => {
    if (!cheapest) return offer;
    return priceNumber(offer.priceAmount) < priceNumber(cheapest.priceAmount) ? offer : cheapest;
  }, null);
}

function stopsCount(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized.includes('non') || normalized === 'direct') return 0;
  const numeric = Number.parseInt(normalized, 10);
  return Number.isFinite(numeric) ? numeric : 0;
}

function stopsLabel(value: string) {
  const count = stopsCount(value);
  if (count === 0) return 'Direct';
  if (count === 1) return '1 stop';
  return `${count} stops`;
}

function stopoverLabel(flight: FlightGroup) {
  const baseLabel = stopsLabel(flight.stops);
  if (stopsCount(flight.stops) === 0 || flight.stopAirports.length === 0) return baseLabel;
  return `${baseLabel} via ${flight.stopAirports.join(', ')}`;
}

function formatDuration(value: string) {
  const trimmed = value.trim();
  const minuteMatch = trimmed.match(/^(\d+)\s*m$/i);
  if (minuteMatch) {
    const totalMinutes = Number(minuteMatch[1]);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${hours}h ${String(minutes).padStart(2, '0')}m`;
  }

  const hourMinuteMatch = trimmed.match(/^(\d+):(\d{2})$/);
  if (hourMinuteMatch) {
    return `${Number(hourMinuteMatch[1])}h ${hourMinuteMatch[2]}m`;
  }

  return trimmed;
}

function normalizeAirport(value: string) {
  return value.toUpperCase().replace(/[^A-Z\s]/g, '').slice(0, 40);
}

function airportCodeFromInput(value: string) {
  const normalized = normalizeAirport(value).trim();
  const compact = normalized.replace(/\s+/g, '');
  if (airportAliases[compact]) return airportAliases[compact];
  const exactCode = airportOptions.find(airport => airport.code === compact);
  if (exactCode) return exactCode.code;
  const exactText = airportOptions.find(airport => {
    const city = airport.city.toUpperCase();
    const name = airport.name.toUpperCase();
    return city === normalized || name === normalized || `${city} ${airport.code}` === normalized || city.replace(/\s+/g, '') === compact;
  });
  if (exactText) return exactText.code;
  const prefixText = airportOptions.find(airport => {
    const city = airport.city.toUpperCase().replace(/\s+/g, '');
    const name = airport.name.toUpperCase().replace(/\s+/g, '');
    return airport.code.startsWith(compact) || city.startsWith(compact) || name.startsWith(compact);
  });
  if (prefixText) return prefixText.code;
  return compact.slice(0, 3);
}

function airportDisplay(value: string) {
  const code = airportCodeFromInput(value);
  const airport = airportOptions.find(option => option.code === code);
  return airport ? `${airport.city} (${airport.code})` : code;
}

function airportMatches(airport: AirportOption, query: string) {
  const normalized = normalizeAirport(query).trim();
  if (!normalized) return true;
  const haystack = `${airport.code} ${airport.city} ${airport.name} ${airport.country}`.toUpperCase();
  return haystack.includes(normalized);
}

function airportSuggestions(query: string) {
  const normalized = normalizeAirport(query).trim();
  const matches = airportOptions
    .filter(airport => airportMatches(airport, query))
    .sort((a, b) => {
      const aCode = a.code.startsWith(normalized) ? 0 : 1;
      const bCode = b.code.startsWith(normalized) ? 0 : 1;
      return aCode - bCode || a.city.localeCompare(b.city);
    });
  return (matches.length ? matches : airportOptions).slice(0, 6);
}

function providerUrl(offer: FlightOffer) {
  return offer.providerUrl || offer.providerOfferUrl || offer.providerSearchUrl;
}

const providerLabels: Record<string, string> = {
  aertrip: 'Aertrip',
  agoda: 'Agoda',
  air_india: 'Air India',
  air_india_express: 'Air India Express',
  akasa_air: 'Akasa Air',
  booking: 'Booking.com',
  vakatrip: 'VakaTrip.com',
  yatra: 'Yatra',
  yatra_lowest_fare: 'Yatra Lowest Fare'
};

const airlineLogos: Record<string, string> = {
  ai: '/airlines/air-india.svg',
  ix: '/airlines/air-india-express.svg',
  qp: '/airlines/akasa-air.svg',
  '6e': '/airlines/indigo.svg',
  sg: '/airlines/spicejet.svg',
  'air india limited': '/airlines/air-india.svg',
  'air india': '/airlines/air-india.svg',
  airindia: '/airlines/air-india.svg',
  'air india express': '/airlines/air-india-express.svg',
  airindiaexpress: '/airlines/air-india-express.svg',
  'airindia express': '/airlines/air-india-express.svg',
  akasa: '/airlines/akasa-air.svg',
  'akasa air': '/airlines/akasa-air.svg',
  akasaair: '/airlines/akasa-air.svg',
  'alliance air': '/airlines/alliance-air.svg',
  indigo: '/airlines/indigo.svg',
  'interglobe aviation': '/airlines/indigo.svg',
  spicejet: '/airlines/spicejet.svg',
  spice: '/airlines/spicejet.svg',
  'star air': '/airlines/star-air.svg'
};

function providerKey(name: string) {
  return name.trim().toLowerCase().replace(/[\s.-]+/g, '_');
}

function airlineKey(name: string) {
  return name.trim().toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function airlineLogo(name: string) {
  const key = airlineKey(name);
  return airlineLogos[key] || airlineLogos[key.replace(/\s+/g, '')];
}

function providerLabel(name: string) {
  const key = providerKey(name);
  return providerLabels[key] || name;
}

function priceNumber(value: string | null) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : Number.POSITIVE_INFINITY;
}

type DatePickerTarget = 'depart' | 'return';
type AirportField = 'origin' | 'destination';

type CalendarDay = {
  date: Date;
  isoDate: string;
  day: number;
  outsideMonth: boolean;
  disabled: boolean;
  priceLevel: 'low' | 'medium' | 'high';
};

const weekDays = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
const todayIso = toIsoDate(new Date());

function fareLevel(isoDate: string): CalendarDay['priceLevel'] {
  const day = Number(isoDate.slice(-2));
  if (day % 5 === 2 || day % 7 === 1) return 'low';
  if (day % 11 === 0 || day % 13 === 0) return 'high';
  return 'medium';
}

function getCalendarDays(monthDate: Date): CalendarDay[] {
  const firstDay = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const mondayOffset = (firstDay.getDay() + 6) % 7;
  const gridStart = new Date(firstDay);
  gridStart.setDate(firstDay.getDate() - mondayOffset);

  return Array.from({ length: 42 }, (_, index) => {
    const dateValue = new Date(gridStart);
    dateValue.setDate(gridStart.getDate() + index);
    const isoDate = toIsoDate(dateValue);
    return {
      date: dateValue,
      isoDate,
      day: dateValue.getDate(),
      outsideMonth: dateValue.getMonth() !== monthDate.getMonth(),
      disabled: isoDate < todayIso,
      priceLevel: fareLevel(isoDate)
    };
  });
}

function flightKey(offer: FlightOffer) {
  return [
    offer.airline,
    offer.flightNumber,
    offer.origin,
    offer.destination,
    offer.departureTime,
    offer.arrivalTime,
    offer.duration,
    offer.stops
  ].join('|');
}

function groupOffers(offers: FlightOffer[]): FlightGroup[] {
  const groups = new Map<string, FlightGroup>();

  for (const offer of offers) {
    const key = flightKey(offer);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        airline: offer.airline || 'Unknown airline',
        flightNumber: offer.flightNumber || '',
        origin: offer.origin,
        destination: offer.destination,
        departureTime: offer.departureTime,
        arrivalTime: offer.arrivalTime,
        duration: offer.duration,
        stops: offer.stops,
        stopAirports: offer.stopAirports || [],
        cheapestPriceAmount: offer.priceAmount,
        currency: offer.currency,
        offerCount: 0,
        providers: []
      });
    }

    const group = groups.get(key)!;
    group.offerCount += 1;
    if (group.stopAirports.length === 0 && offer.stopAirports?.length) {
      group.stopAirports = offer.stopAirports;
    }
    if (priceNumber(offer.priceAmount) < priceNumber(group.cheapestPriceAmount)) {
      group.cheapestPriceAmount = offer.priceAmount;
      group.currency = offer.currency;
      group.stopAirports = offer.stopAirports || group.stopAirports;
    }

    const normalizedProviderName = providerLabel(offer.provider);
    const normalizedProviderKey = providerKey(offer.provider);
    const existingProvider = group.providers.find(provider => provider.name === normalizedProviderName);
    if (existingProvider) {
      existingProvider.offerCount += 1;
      if (priceNumber(offer.priceAmount) < priceNumber(existingProvider.priceAmount)) {
        existingProvider.priceAmount = offer.priceAmount;
        existingProvider.currency = offer.currency;
        existingProvider.providerUrl = providerUrl(offer);
        existingProvider.linkStatus = offer.providerLinkStatus;
      }
    } else {
      group.providers.push({
        name: normalizedProviderName,
        priceAmount: offer.priceAmount,
        currency: offer.currency,
        providerUrl: providerUrl(offer),
        linkStatus: offer.providerLinkStatus,
        offerCount: 1,
        sourceKey: normalizedProviderKey
      });
    }
  }

  return [...groups.values()]
    .map(group => ({
      ...group,
      providers: group.providers.sort(
        (a, b) => priceNumber(a.priceAmount) - priceNumber(b.priceAmount) || a.name.localeCompare(b.name)
      )
    }))
    .sort(
      (a, b) =>
        priceNumber(a.cheapestPriceAmount) - priceNumber(b.cheapestPriceAmount) ||
        a.departureTime.localeCompare(b.departureTime)
  );
}

function DatePickerDialog({
  activeTarget,
  visibleMonth,
  departDate,
  returnDate,
  onTargetChange,
  onMonthChange,
  onSelectDate,
  onApply
}: {
  activeTarget: DatePickerTarget;
  visibleMonth: Date;
  departDate: string;
  returnDate: string;
  onTargetChange: (target: DatePickerTarget) => void;
  onMonthChange: (month: Date) => void;
  onSelectDate: (target: DatePickerTarget, value: string) => void;
  onApply: () => void;
}) {
  const months = [visibleMonth, addMonths(visibleMonth, 1)];
  const activeLabel = activeTarget === 'depart' ? 'departure' : 'return';

  return (
    <div className="date-picker-popover" role="dialog" aria-modal="false" aria-label="Choose travel dates">
      <div className="date-picker-toolbar">
        <div className="date-trip-select">
          <select aria-label="Trip type" value="return" onChange={() => undefined}>
            <option value="return">Return</option>
            <option value="one_way">One way</option>
          </select>
          <ChevronDown aria-hidden="true" size={17} strokeWidth={2.6} />
        </div>

        <div className="date-mode-tabs" role="tablist" aria-label="Date search mode">
          <button className="active" type="button" role="tab" aria-selected="true">Specific dates</button>
          <button type="button" role="tab" aria-selected="false">Flexible dates</button>
        </div>

        <div className="fare-legend" aria-label="Indicative fare levels">
          <span className="fare-pill low">₹</span>
          <span className="fare-pill medium">₹₹</span>
          <span className="fare-pill high">₹₹₹</span>
          <Info aria-hidden="true" size={16} fill="currentColor" />
        </div>
      </div>

      <div className="calendar-stage">
        <button
          className="calendar-nav prev"
          type="button"
          aria-label="Previous month"
          onClick={() => onMonthChange(addMonths(visibleMonth, -1))}
        >
          <ChevronLeft aria-hidden="true" size={30} strokeWidth={2.1} />
        </button>
        <button
          className="calendar-nav next"
          type="button"
          aria-label="Next month"
          onClick={() => onMonthChange(addMonths(visibleMonth, 1))}
        >
          <ChevronRight aria-hidden="true" size={30} strokeWidth={2.1} />
        </button>

        <div className="calendar-months">
          {months.map(monthDate => (
            <section className="calendar-month" key={monthKey(monthDate)}>
              <h2>
                {new Intl.DateTimeFormat('en-GB', { month: 'long' }).format(monthDate)}
              </h2>
              <div className="weekday-row" aria-hidden="true">
                {weekDays.map((dayLabel, index) => (
                  <span key={`${dayLabel}-${index}`}>{dayLabel}</span>
                ))}
              </div>
              <div className="day-grid">
                {getCalendarDays(monthDate).map(day => {
                  const isDepart = day.isoDate === departDate;
                  const isReturn = day.isoDate === returnDate;
                  const selected = isDepart || isReturn;
                  const disabled = day.disabled || (activeTarget === 'return' && day.isoDate < departDate);
                  return (
                    <button
                      className={[
                        'calendar-day',
                        day.outsideMonth ? 'outside-month' : '',
                        disabled ? 'disabled' : `fare-${day.priceLevel}`,
                        selected ? 'selected' : '',
                        isDepart && activeTarget === 'depart' ? 'active-date' : '',
                        isReturn && activeTarget === 'return' ? 'active-date' : ''
                      ].filter(Boolean).join(' ')}
                      disabled={disabled}
                      type="button"
                      key={day.isoDate}
                      aria-label={`${day.day} ${new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric' }).format(day.date)}`}
                      onClick={() => {
                        onSelectDate(activeTarget, day.isoDate);
                        if (activeTarget === 'depart') onTargetChange('return');
                      }}
                    >
                      {day.day}
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </div>

      <div className="date-picker-footer">
        <span>Select a {activeLabel} date</span>
        <div className="selected-date-summary">
          <button
            className={activeTarget === 'depart' ? 'active' : ''}
            type="button"
            onClick={() => onTargetChange('depart')}
          >
            {formatSearchDate(departDate)}
          </button>
          <ArrowRight aria-hidden="true" size={16} strokeWidth={2.5} />
          <button
            className={activeTarget === 'return' ? 'active' : ''}
            type="button"
            onClick={() => onTargetChange('return')}
          >
            {returnDate ? formatSearchDate(returnDate) : 'Return date'}
          </button>
        </div>
        <button className="apply-date-button" type="button" onClick={onApply}>Apply</button>
      </div>
    </div>
  );
}

function AirportDropdown({
  field,
  query,
  onSelect
}: {
  field: AirportField;
  query: string;
  onSelect: (airport: AirportOption) => void;
}) {
  const suggestions = airportSuggestions(query);
  return (
    <div className={`airport-dropdown airport-dropdown-${field}`} role="listbox" aria-label={`${field} airport suggestions`}>
      <div className="airport-dropdown-heading">Suggested airports</div>
      {suggestions.map(airport => (
        <button
          className="airport-option"
          type="button"
          role="option"
          key={airport.code}
          onMouseDown={event => {
            event.preventDefault();
            onSelect(airport);
          }}
        >
          <span className="airport-option-icon" aria-hidden="true">
            <Plane size={17} fill="currentColor" strokeWidth={2.2} />
          </span>
          <span className="airport-option-main">
            <strong>{airport.city}</strong>
            <span>{airport.name}</span>
          </span>
          <span className="airport-option-code">{airport.code}</span>
        </button>
      ))}
    </div>
  );
}

export default function App() {
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [viewerLoaded, setViewerLoaded] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [email, setEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [authStatus, setAuthStatus] = useState('We will send a one-time sign-in code.');
  const [otpRequested, setOtpRequested] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [otpExpiresAt, setOtpExpiresAt] = useState<number | null>(null);
  const [otpWrong, setOtpWrong] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [origin, setOrigin] = useState('DEL');
  const [destination, setDestination] = useState('BOM');
  const [activeAirportField, setActiveAirportField] = useState<AirportField | null>(null);
  const [date, setDate] = useState(defaultDate);
  const [returnDate, setReturnDate] = useState('');
  const [datePickerOpen, setDatePickerOpen] = useState(false);
  const [activeDateTarget, setActiveDateTarget] = useState<DatePickerTarget>('depart');
  const [visibleMonth, setVisibleMonth] = useState(() => new Date(new Date(defaultDate).getFullYear(), new Date(defaultDate).getMonth(), 1));
  const [sort, setSort] = useState('price');
  const [offers, setOffers] = useState<FlightOffer[]>([]);
  const [stopFares, setStopFares] = useState<StopFareSummary>(emptyStopFareSummary);
  const [selectedFlightKey, setSelectedFlightKey] = useState<string | null>(null);
  const [status, setStatus] = useState('Enter a route and date to search stored flight prices.');
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchEditorOpen, setSearchEditorOpen] = useState(false);
  const [dateFares, setDateFares] = useState<DateFare[]>([]);
  const [stopFilters, setStopFilters] = useState({
    direct: true,
    one: true,
    multi: true
  });

  const providers = useMemo(() => new Set(offers.map(offer => providerKey(offer.provider))).size, [offers]);
  const groupedFlights = useMemo(() => groupOffers(offers), [offers]);
  const filteredFlights = useMemo(
    () =>
      groupedFlights.filter(flight => {
        const count = stopsCount(flight.stops);
        if (count === 0) return stopFilters.direct;
        if (count === 1) return stopFilters.one;
        return stopFilters.multi;
      }),
    [groupedFlights, stopFilters]
  );
  const selectedFlight = filteredFlights.find(group => group.key === selectedFlightKey) || filteredFlights[0];

  useEffect(() => {
    getViewer()
      .then(user => {
        setViewer(user);
        setViewerLoaded(true);
      })
      .catch(() => {
        setViewer(null);
        setViewerLoaded(true);
      });
  }, []);

  useEffect(() => {
    if (!viewerLoaded || viewer) return;
    const timer = window.setTimeout(() => setShowAuthModal(true), 2000);
    return () => window.clearTimeout(timer);
  }, [viewer, viewerLoaded]);

  useEffect(() => {
    if (!otpExpiresAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [otpExpiresAt]);

  const otpSecondsLeft = otpExpiresAt ? Math.max(0, Math.ceil((otpExpiresAt - now) / 1000)) : 0;
  const otpCountdown = `${Math.floor(otpSecondsLeft / 60)}:${String(otpSecondsLeft % 60).padStart(2, '0')}`;

  async function handleRequestOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthLoading(true);
    setAuthStatus('Sending sign-in code...');
    try {
      const result = await requestEmailOtp(email);
      if (result.ok) {
        setOtpRequested(true);
        setOtpExpiresAt(new Date(result.expiresAt).getTime());
        setNow(Date.now());
        setAuthStatus('Code sent.');
      } else {
        setAuthStatus('Could not send code. Check the email address and try again.');
      }
    } catch (error) {
      setAuthStatus(error instanceof Error ? error.message : 'Could not send code.');
    } finally {
      setAuthLoading(false);
    }
  }

  async function submitOtp(code = otpCode) {
    if (code.length < 6 || authLoading || otpSecondsLeft === 0) return;
    setAuthLoading(true);
    setOtpWrong(false);
    setAuthStatus('Verifying code...');
    try {
      const result = await verifyEmailOtp(email, code);
      if (!result.ok || !result.user) {
        setOtpWrong(true);
        setAuthStatus(otpSecondsLeft > 0 ? 'Wrong code. Try again.' : 'Code expired. Request a new code.');
        return;
      }
      setViewer(result.user);
      setOtpCode('');
      setOtpRequested(false);
      setOtpExpiresAt(null);
      setShowAuthModal(false);
      setAuthStatus(`Signed in as ${result.user.email}.`);
    } catch (error) {
      setOtpWrong(true);
      setAuthStatus(error instanceof Error ? error.message : 'Could not verify code.');
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleVerifyOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitOtp();
  }

  function handleOtpInput(index: number, value: string) {
    const digit = value.replace(/\D/g, '').slice(-1);
    const nextCode = otpCode.padEnd(6, ' ').split('');
    nextCode[index] = digit || ' ';
    const compactCode = nextCode.join('').replace(/\s/g, '');
    setOtpCode(compactCode);
    setOtpWrong(false);
    if (digit && index < 5) {
      document.getElementById(`otp-${index + 1}`)?.focus();
    }
    if (digit && index === 5 && compactCode.length === 6) {
      void submitOtp(compactCode);
    }
  }

  function handleOtpKeyDown(index: number, key: string) {
    if (key !== 'Backspace' || otpCode[index]) return;
    document.getElementById(`otp-${Math.max(0, index - 1)}`)?.focus();
  }

  async function handleSignOut() {
    await signOut();
    setViewer(null);
    setAuthStatus('We will send a one-time sign-in code.');
    setOtpExpiresAt(null);
    setOtpWrong(false);
    setShowAuthModal(true);
  }

  async function performSearch(searchDate = date) {
    const originCode = airportCodeFromInput(origin);
    const destinationCode = airportCodeFromInput(destination);
    setOrigin(originCode);
    setDestination(destinationCode);
    setIsLoading(true);
    setHasSearched(true);
    setDate(searchDate);
    setStatus('Searching stored flight offers...');

    try {
      const data = await searchFlights({ origin: originCode, destination: destinationCode, date: searchDate, sort });
      setOffers(data.results);
      setStopFares(data.stopFares);
      setSelectedFlightKey(null);
      const routeProviders = [...new Set(data.providers.map(provider => providerLabel(provider)))].sort();
      const providerCount = routeProviders.length;
      const groupedCount = groupOffers(data.results).length;
      const stripDates = [-3, -2, -1, 0, 1, 2, 3].map(offset => addDays(searchDate, offset));
      const fareRows = await Promise.all(
        stripDates.map(async stripDate => {
          const stripData = stripDate === searchDate
            ? data
            : await searchFlights({ origin: originCode, destination: destinationCode, date: stripDate, sort });
          const cheapest = cheapestOffer(stripData.results);
          return {
            date: stripDate,
            label: formatDateLabel(stripDate),
            priceAmount: cheapest?.priceAmount || null,
            currency: cheapest?.currency || 'INR',
            count: stripData.count
          };
        })
      );
      setDateFares(fareRows);
      setStatus(
        data.count
          ? `Found ${data.count} offers from ${providerCount} stored provider${providerCount === 1 ? '' : 's'} (${routeProviders.join(', ')}), grouped into ${groupedCount} flights.`
          : 'No offers found.'
      );
    } catch (error) {
      setOffers([]);
      setStopFares(emptyStopFareSummary);
      setStatus(error instanceof Error ? error.message : 'Flight search failed.');
    } finally {
      setIsLoading(false);
      setSearchEditorOpen(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await performSearch(date);
  }

  return (
    <main className={`app-shell ${hasSearched ? 'search-mode' : ''} ${searchEditorOpen ? 'search-editor-open' : ''}`}>
      <section className="hero-search">
        <header className="hero-topbar">
          <div className="brand-mark">
            <img src="/image.png" alt="" />
            <span>Skaiscanner</span>
          </div>
          <nav className="hero-actions" aria-label="Account">
            <button className="hero-icon-button" type="button" aria-label="Help">
              <CircleHelp aria-hidden="true" size={20} strokeWidth={2.4} />
            </button>
            <button className="hero-icon-button" type="button" aria-label="Language and region">
              <Globe2 aria-hidden="true" size={20} strokeWidth={2.4} />
            </button>
            <button className="hero-icon-button" type="button" aria-label="Saved">
              <Heart aria-hidden="true" size={20} strokeWidth={2.6} />
            </button>
            {viewer ? (
              <button className="hero-login" type="button" onClick={handleSignOut}>
                <UserCircle aria-hidden="true" size={22} strokeWidth={2.4} />
                <span>{viewer.email}</span>
              </button>
            ) : (
              <button className="hero-login" type="button" onClick={() => setShowAuthModal(true)}>
                <UserCircle aria-hidden="true" size={22} strokeWidth={2.4} />
                <span>Log in</span>
              </button>
            )}
          </nav>
        </header>

        <div className="product-tabs" aria-label="Travel products">
          <button className="active" type="button">Flights</button>
          <button type="button">Hotels</button>
          <button type="button">Cars</button>
        </div>

        <h1>Millions of cheap flights. One simple search.</h1>

        <form className="search-panel" onSubmit={handleSubmit}>
          <button
            className="compact-search-trigger"
            type="button"
            aria-expanded={searchEditorOpen}
            aria-label="Edit search"
            onClick={() => setSearchEditorOpen(open => !open)}
          >
            <Search aria-hidden="true" size={19} strokeWidth={3} />
          </button>

          <div className="trip-row">
            <select aria-label="Trip type" defaultValue="return">
              <option value="return">Return</option>
              <option value="one_way">One way</option>
            </select>
            <ChevronDown aria-hidden="true" className="trip-chevron" size={18} strokeWidth={2.6} />
          </div>

          <div className="flight-search-grid">
            <div className="search-route-summary">
              {airportDisplay(origin)} - {airportDisplay(destination)} · 1 adult, Economy
            </div>
            <label className={`airport-field ${activeAirportField === 'origin' ? 'active' : ''}`}>
              <span>From</span>
              <input
                autoComplete="off"
                value={origin}
                onBlur={() => window.setTimeout(() => setActiveAirportField(null), 120)}
                onChange={event => {
                  setOrigin(normalizeAirport(event.target.value));
                  setActiveAirportField('origin');
                }}
                onFocus={() => setActiveAirportField('origin')}
                required
              />
              {activeAirportField === 'origin' ? (
                <AirportDropdown
                  field="origin"
                  query={origin}
                  onSelect={airport => {
                    setOrigin(airport.code);
                    setActiveAirportField(null);
                  }}
                />
              ) : null}
            </label>
            <button
              className="swap-button"
              type="button"
              aria-label="Swap route"
              onClick={() => {
                setOrigin(airportCodeFromInput(destination));
                setDestination(airportCodeFromInput(origin));
              }}
            >
              <ArrowLeftRight aria-hidden="true" size={22} strokeWidth={2.6} />
            </button>
            <label className={`airport-field ${activeAirportField === 'destination' ? 'active' : ''}`}>
              <span>To</span>
              <input
                autoComplete="off"
                value={destination}
                onBlur={() => window.setTimeout(() => setActiveAirportField(null), 120)}
                onChange={event => {
                  setDestination(normalizeAirport(event.target.value));
                  setActiveAirportField('destination');
                }}
                onFocus={() => setActiveAirportField('destination')}
                required
              />
              {activeAirportField === 'destination' ? (
                <AirportDropdown
                  field="destination"
                  query={destination}
                  onSelect={airport => {
                    setDestination(airport.code);
                    setActiveAirportField(null);
                  }}
                />
              ) : null}
            </label>
            <label>
              <span>Depart</span>
              <button
                className="date-field-button"
                type="button"
                onClick={() => {
                  setActiveDateTarget('depart');
                  setVisibleMonth(new Date(new Date(date).getFullYear(), new Date(date).getMonth(), 1));
                  setDatePickerOpen(true);
                }}
              >
                {formatSearchDate(date)}
              </button>
            </label>
            <label>
              <span>Return</span>
              <button
                className={`date-field-button ${returnDate ? '' : 'placeholder'}`}
                type="button"
                onClick={() => {
                  const baseDate = returnDate || addDays(date, 7);
                  setActiveDateTarget('return');
                  setVisibleMonth(new Date(new Date(baseDate).getFullYear(), new Date(baseDate).getMonth(), 1));
                  setDatePickerOpen(true);
                }}
              >
                {returnDate ? formatSearchDate(returnDate) : 'Add date'}
              </button>
            </label>
            <label className="travellers-field">
              <span>Travellers and cabin class</span>
              <strong>1 Adult, Economy</strong>
            </label>
            <button className="search-button" disabled={isLoading}>{isLoading ? 'Searching...' : 'Search'}</button>

            {datePickerOpen ? (
              <DatePickerDialog
                activeTarget={activeDateTarget}
                visibleMonth={visibleMonth}
                departDate={date}
                returnDate={returnDate}
                onTargetChange={setActiveDateTarget}
                onMonthChange={setVisibleMonth}
                onSelectDate={(target, value) => {
                  if (target === 'depart') {
                    setDate(value);
                    if (returnDate && returnDate < value) setReturnDate('');
                  } else {
                    setReturnDate(value);
                  }
                }}
                onApply={() => setDatePickerOpen(false)}
              />
            ) : null}
          </div>

          <div className="search-options">
            <label><input type="checkbox" /> Add nearby airports</label>
            <label><input type="checkbox" /> Add nearby airports</label>
            <label><input type="checkbox" /> Direct flights</label>
            <label><input type="checkbox" defaultChecked /> Add a hotel</label>
          </div>
        </form>
      </section>

      {!hasSearched ? (
        <>
          <section className="homepage-content" aria-label="Travel inspiration">
            <div className="quick-links">
              <button type="button">
                <Sparkles aria-hidden="true" size={26} strokeWidth={2.4} />
                <span>New - AI search!</span>
              </button>
              <button type="button">
                <Bed aria-hidden="true" size={25} strokeWidth={2.4} />
                <span>Hotels</span>
              </button>
              <button type="button">
                <Car aria-hidden="true" size={25} strokeWidth={2.4} />
                <span>Cars</span>
              </button>
              <button type="button">
                <MapPinned aria-hidden="true" size={25} strokeWidth={2.4} />
                <span>Explore everywhere</span>
              </button>
            </div>

            <article className="summer-banner">
              <div className="summer-copy">
                <h2>Being Summer Smarter starts here</h2>
                <p>Get the tips and tricks to fly cheaper, beat the crowds and unlock unique experiences.</p>
                <button type="button">You in?</button>
              </div>
              <div className="summer-wordmark" aria-hidden="true">
                <span>Get more from your summer</span>
                <strong>SUMMER</strong>
                <em>smarter</em>
              </div>
            </article>

            <h2 className="booking-heading">Booking flights with Skyscanner</h2>
            <div className="faq-grid" aria-label="Booking flights FAQ">
              {[
                'How does Skyscanner work?',
                'How can I find the cheapest flight using Skyscanner?',
                'Where should I book a flight to right now?',
                'Do I book my flight with Skyscanner?',
                'What happens after I have booked my flight?',
                'Does Skyscanner do hotels too?',
                'What about car hire?',
                "What's a Price Alert?",
                'Can I book a flexible flight ticket?',
                'Can I book flights that emit less CO2?'
              ].map(question => (
                <button type="button" key={question}>
                  <span>{question}</span>
                  <ChevronDown aria-hidden="true" size={18} strokeWidth={2.6} />
                </button>
              ))}
            </div>

            <section className="international-sites" aria-label="International sites">
              <div className="section-heading-row">
                <h2>Our international sites</h2>
                <ChevronDown aria-hidden="true" className="collapse-up" size={18} strokeWidth={2.6} />
              </div>
              <div className="site-grid">
                {[
                  ['GB', '(GB) Cheap flights'],
                  ['HK', '(HK) Hong Kong - flights'],
                  ['JP', '(JP) Japan - flights'],
                  ['NZ', '(NZ) New Zealand - Cheap flights'],
                  ['SG', '(SG) Singapore - flights'],
                  ['TH', '(TH) Thailand - flights'],
                  ['AU', '(AU) Australia - Cheap flights'],
                  ['IN', '(IN) India - Flight tickets'],
                  ['MY', '(MY) Malaysia - flights'],
                  ['PH', '(PH) Philippines - flights'],
                  ['KR', '(KR) South Korea - flights'],
                  ['US', '(US) USA - flights'],
                  ['CN', '(CN) China - flights'],
                  ['ID', '(ID) Indonesia - Tiket Pesawat'],
                  ['MX', '(MX) Mexico - vuelos'],
                  ['RU', '(RU) Russia - flights'],
                  ['TW', '(TW) Taiwan - flights'],
                  ['VN', '(VN) Vietnam - flights']
                ].map(([code, label]) => (
                  <a href="#" key={label}>
                    <span className="flag-dot">{code}</span>
                    <span>{label}</span>
                  </a>
                ))}
              </div>
            </section>

            <section className="adventure-planner" aria-label="Start planning your adventure">
              <h2>Start planning your adventure</h2>
              <div className="planner-tabs">
                <button className="active" type="button">Airport</button>
                <button type="button">Region</button>
                <button type="button">Country</button>
                <button type="button">City</button>
              </div>
              <div className="planner-links">
                <a href="#">Kathmandu Airport car hire</a>
                <a href="#">Best car hire at Kolkata Airport</a>
                <a href="#">Cheap return flights to Hyderabad</a>
                <a href="#">Bhubaneswar Airport car hire</a>
                <a href="#">Singapore Changi Airport car hire</a>
                <a href="#">Cheap tickets to Phuket</a>
                <a href="#">Best car hire at London Heathrow Airport</a>
                <a href="#">Best car hire at Udaipur Airport</a>
                <a href="#">Cheap return tickets to Bali (Denpasar)</a>
              </div>
              <div className="planner-controls" aria-hidden="true">
                <span className="muted-arrow">&lt;</span>
                <span className="pager active"></span>
                <span className="pager"></span>
                <span className="pager"></span>
                <span className="pager"></span>
                <span className="pager"></span>
                <span>&gt;</span>
              </div>
            </section>
          </section>

          <footer className="site-footer">
            <div className="footer-grid">
              <button className="locale-button" type="button">India - English (UK) - INR</button>
              <nav aria-label="Account links">
                <a href="#">Help</a>
                <a href="#">Privacy Settings</a>
                <a href="#">Log in</a>
              </nav>
              <nav aria-label="Legal links">
                <a href="#">Cookie policy</a>
                <a href="#">Privacy policy</a>
                <a href="#">Terms of service</a>
                <a href="#">Company Details</a>
              </nav>
              <nav aria-label="Explore links">
                <a href="#">Explore <ChevronDown aria-hidden="true" size={16} /></a>
                <a href="#">Company <ChevronDown aria-hidden="true" size={16} /></a>
                <a href="#">Partners <ChevronDown aria-hidden="true" size={16} /></a>
                <a href="#">Trips <ChevronDown aria-hidden="true" size={16} /></a>
                <a href="#">International Sites <ChevronDown aria-hidden="true" size={16} /></a>
              </nav>
            </div>
            <p>Cheap flight booking from anywhere, to everywhere</p>
            <p>© Skyscanner Ltd 2002 - 2026</p>
          </footer>
        </>
      ) : null}

      {showAuthModal && !viewer ? (
        <div className="modal-backdrop" role="presentation">
          <section className="login-modal" role="dialog" aria-modal="true" aria-labelledby="login-title">
            <button className="modal-close" type="button" aria-label="Close" onClick={() => setShowAuthModal(false)}>
              x
            </button>
            <div className="modal-copy">
              <div className="modal-brand">SkaiScanner</div>
              {!otpRequested ? (
                <>
                  <h2 id="login-title">Book flights at the prices of trains, pay in crypto</h2>
                  <p>Login to access flights from 24+ providers, instead of manually searching across</p>
                  <form onSubmit={handleRequestOtp}>
                    <label>
                      Email
                      <input
                        autoFocus
                        type="email"
                        value={email}
                        onChange={event => setEmail(event.target.value)}
                        placeholder="Enter your email"
                        required
                      />
                    </label>
                    <button disabled={authLoading}>{authLoading ? 'Sending...' : 'Continue'}</button>
                  </form>
                </>
              ) : (
                <form className="otp-form" onSubmit={handleVerifyOtp}>
                  <div>
                    <h2>Verify your account</h2>
                    <p>
                      Enter the verification code we sent to <strong>{email}</strong> to continue.
                    </p>
                  </div>
                  <label>
                    6-digit verification code
                    <div className={`otp-grid ${otpWrong ? 'wrong' : ''}`}>
                      {Array.from({ length: 6 }).map((_, index) => (
                        <input
                          id={`otp-${index}`}
                          // eslint-disable-next-line react/no-array-index-key
                          key={index}
                          autoFocus={index === 0}
                          inputMode="numeric"
                          maxLength={1}
                          value={otpCode[index] || ''}
                          onChange={event => handleOtpInput(index, event.target.value)}
                          onKeyDown={event => handleOtpKeyDown(index, event.key)}
                          required
                        />
                      ))}
                    </div>
                  </label>
                  <span className="resend-row">
                    Didn't get the code?{' '}
                    <button
                      type="button"
                      disabled={authLoading}
                      onClick={() => {
                        setOtpRequested(false);
                        setOtpExpiresAt(null);
                        setOtpCode('');
                        setOtpWrong(false);
                        setAuthStatus('We will send a one-time sign-in code.');
                      }}
                    >
                      Resend code
                    </button>
                  </span>
                  <button disabled={authLoading || otpSecondsLeft === 0 || otpCode.length < 6}>
                    {authLoading ? 'Verifying...' : 'Verify code'}
                  </button>
                </form>
              )}
              <span className="modal-status">
                {otpRequested && otpExpiresAt
                  ? otpSecondsLeft > 0
                    ? `Code sent. Expires in ${otpCountdown}.`
                    : 'Code expired. Request a new code.'
                  : authStatus}
              </span>
            </div>
            <div className="modal-image" aria-hidden="true">
              <span>@</span>
            </div>
          </section>
        </div>
      ) : null}

      {hasSearched ? (
        <section className="results-page">
          <div className="date-strip" aria-label="Flexible date prices">
            {(dateFares.length ? dateFares : [-3, -2, -1, 0, 1, 2, 3].map(offset => {
              const stripDate = addDays(date, offset);
              return { date: stripDate, label: formatDateLabel(stripDate), priceAmount: null, currency: 'INR', count: 0 };
            })).map(row => {
              const allPrices = dateFares.map(fare => priceNumber(fare.priceAmount)).filter(Number.isFinite);
              const isCheapest = allPrices.length > 0 && priceNumber(row.priceAmount) === Math.min(...allPrices);
              return (
              <button
                className={`${row.date === date ? 'selected' : ''} ${isCheapest && row.date !== date ? 'cheap' : ''}`}
                disabled={isLoading}
                type="button"
                key={row.date}
                onClick={() => {
                  void performSearch(row.date);
                }}
              >
                <span>{row.label}</span>
                <strong>{formatShortPrice(row.priceAmount, row.currency)}</strong>
              </button>
              );
            })}
            <button className="flexible-dates" type="button">
              <Calendar aria-hidden="true" size={18} strokeWidth={2.4} />
              <span>Flexible dates</span>
            </button>
          </div>

          <div className="results-shell">
            <aside className="filters-panel">
              <button className="price-alert-button" type="button">
                <Bell aria-hidden="true" size={18} fill="currentColor" />
                <span>Get Price Alerts</span>
              </button>

              <section className="filter-group">
                <h2>Stops <ChevronDown aria-hidden="true" className="filter-caret" size={17} /></h2>
                <label>
                  <input
                    type="checkbox"
                    checked={stopFilters.direct}
                    onChange={event => setStopFilters(current => ({ ...current, direct: event.target.checked }))}
                  />
                  <span>
                    Direct
                    <small>
                      {stopFares.direct.count
                        ? `from ${formatShortPrice(stopFares.direct.priceAmount, stopFares.direct.currency)}`
                        : 'No fares'}
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={stopFilters.one}
                    onChange={event => setStopFilters(current => ({ ...current, one: event.target.checked }))}
                  />
                  <span>
                    1 stop
                    <small>
                      {stopFares.one.count
                        ? `from ${formatShortPrice(stopFares.one.priceAmount, stopFares.one.currency)}`
                        : 'No fares'}
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={stopFilters.multi}
                    onChange={event => setStopFilters(current => ({ ...current, multi: event.target.checked }))}
                  />
                  <span>
                    2+ stops
                    <small>
                      {stopFares.multi.count
                        ? `from ${formatShortPrice(stopFares.multi.priceAmount, stopFares.multi.currency)}`
                        : 'No fares'}
                    </small>
                  </span>
                </label>
              </section>

              <section className="filter-group">
                <h2>Baggage <ChevronDown aria-hidden="true" className="filter-caret" size={17} /></h2>
                <div className="filter-actions"><button type="button">Select all</button><button type="button" disabled>Clear all</button></div>
                <label><input type="checkbox" /> <span>Cabin bag</span></label>
                <label><input type="checkbox" /> <span>Checked bag</span></label>
              </section>

              <section className="filter-group">
                <h2>Departure times <ChevronDown aria-hidden="true" className="filter-caret" size={17} /></h2>
                <p>Outbound<br />00:00 - 23:59</p>
                <div className="range-line"><span></span><span></span></div>
              </section>
            </aside>

            <section className="flight-results-column" aria-label="Flight results">
              <div className="results-summary">
                <span>{filteredFlights.length} results sorted by Best</span>
                <Info aria-hidden="true" size={16} fill="currentColor" />
                <a href="#">Show whole month</a>
              </div>

              <div className="sort-tabs">
                <button className="active" type="button">
                  <span>Best</span>
                  <strong>{selectedFlight ? formatPrice(selectedFlight.cheapestPriceAmount, selectedFlight.currency) : '₹--'}</strong>
                  <small>{selectedFlight ? formatDuration(selectedFlight.duration) : '2h 20m'}</small>
                </button>
                <button type="button">
                  <span>Cheapest</span>
                  <strong>{selectedFlight ? formatPrice(selectedFlight.cheapestPriceAmount, selectedFlight.currency) : '₹--'}</strong>
                  <small>{selectedFlight ? formatDuration(selectedFlight.duration) : '2h 20m'}</small>
                </button>
                <button type="button">
                  <span>Fastest</span>
                  <strong>{selectedFlight ? formatPrice(selectedFlight.cheapestPriceAmount, selectedFlight.currency) : '₹--'}</strong>
                  <small>{selectedFlight ? formatDuration(selectedFlight.duration) : '2h 20m'}</small>
                </button>
                <button className="sort-menu" type="button">Sort <ChevronDown aria-hidden="true" size={16} /></button>
              </div>

              <div className="skyscanner-results">
                {filteredFlights.length ? filteredFlights.map(flight => (
                  <article
                    className={`result-flight-card ${selectedFlight?.key === flight.key ? 'active' : ''}`}
                    key={flight.key}
                    onClick={() => setSelectedFlightKey(flight.key)}
                  >
                    <div className="airline-logo">
                      {airlineLogo(flight.airline) ? (
                        <img src={airlineLogo(flight.airline)} alt={flight.airline} />
                      ) : (
                        <span>{flight.airline.slice(0, 10)}</span>
                      )}
                    </div>
                    <div className="result-times">
                      <div>
                        <strong>{flight.departureTime || '--:--'}</strong>
                        <span>{flight.origin}</span>
                      </div>
                      <div className="flight-line">
                        <small>{flight.duration ? formatDuration(flight.duration) : 'Duration unavailable'}</small>
                        <span className={stopsCount(flight.stops) > 0 ? 'has-stops' : ''}>
                          {stopsCount(flight.stops) > 0 ? <i aria-hidden="true"></i> : null}
                          <Plane aria-hidden="true" size={15} fill="currentColor" />
                        </span>
                        <small className={stopsCount(flight.stops) > 0 ? 'stopover-label' : ''}>
                          {stopoverLabel(flight)}
                        </small>
                      </div>
                      <div>
                        <strong>{flight.arrivalTime || '--:--'}</strong>
                        <span>{flight.destination}</span>
                      </div>
                    </div>
                    <div className="result-deal">
                      <button className="save-flight" type="button" aria-label="Save flight">
                        <Heart aria-hidden="true" size={23} />
                      </button>
                      <span>{flight.offerCount} deals from</span>
                      <strong>{formatPrice(flight.cheapestPriceAmount, flight.currency)}</strong>
                      <button type="button">Select -&gt;</button>
                    </div>
                  </article>
                )) : (
                  <div className="no-filter-results">
                    No flights match the selected stop filters.
                  </div>
                )}
              </div>
            </section>

            <aside className="results-side-panel">
              <div className="hotel-promo">
                <div className="hotel-icons" aria-hidden="true"><span>B.</span><span>Trip.</span><span>H</span></div>
                <h2>Found flights? Now find a hotel</h2>
                <p>Get results from all the top hotel sites right here on Skyscanner.</p>
                <button type="button">Explore hotels</button>
              </div>

              {selectedFlight ? (
                <div className="provider-panel results-provider-panel">
                  <h2>{selectedFlight.airline} {selectedFlight.flightNumber}</h2>
                  <p>{selectedFlight.origin} to {selectedFlight.destination} - {selectedFlight.departureTime} to {selectedFlight.arrivalTime}</p>
                  <div className="provider-list">
                    {selectedFlight.providers.map((provider: ProviderOption) => (
                      <div className="provider-row" key={provider.name}>
                        <div>
                          <strong>{provider.name}</strong>
                          <span>{provider.offerCount} offer{provider.offerCount === 1 ? '' : 's'} - {provider.linkStatus.replaceAll('_', ' ')}</span>
                        </div>
                        <div>
                          <strong>{formatPrice(provider.priceAmount, provider.currency)}</strong>
                          {provider.providerUrl ? (
                            <a href={provider.providerUrl} target="_blank" rel="noreferrer">
                              Checkout
                            </a>
                          ) : (
                            <span>No checkout link</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </aside>
          </div>
        </section>
      ) : null}
    </main>
  );
}
