from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from .models import FlightOffer, FlightSearch


class FlightSearchApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.search = FlightSearch.objects.create(
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            source="yatra",
            status="success",
            offers_found=2,
        )
        FlightOffer.objects.create(
            search=self.search,
            source="yatra",
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            airline="Air India",
            flight_number="AI 101",
            departure_time="09:00",
            arrival_time="11:00",
            duration="2h",
            stops="nonstop",
            price_amount=Decimal("5000.00"),
            provider_offer_url="https://example.com/air-india",
        )
        FlightOffer.objects.create(
            search=self.search,
            source="yatra",
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            airline="Akasa Air",
            flight_number="QP 202",
            departure_time="07:00",
            arrival_time="09:00",
            duration="2h",
            stops="nonstop",
            price_amount=Decimal("4500.00"),
            provider_search_url="https://example.com/akasa-search",
        )
        other_search = FlightSearch.objects.create(
            origin="DEL",
            destination="BLR",
            departure_date="2026-05-29",
            source="yatra",
            status="success",
            offers_found=1,
        )
        FlightOffer.objects.create(
            search=other_search,
            source="yatra",
            origin="DEL",
            destination="BLR",
            departure_date="2026-05-29",
            airline="IndiGo",
            price_amount=Decimal("6000.00"),
        )

    def graphql(self, query, variables=None):
        return self.client.post(
            "/graphql/",
            data={"query": query, "variables": variables or {}},
            content_type="application/json",
        )

    def test_search_filters_route_and_date(self):
        response = self.graphql(
            """
            query FlightOffers($origin: String!, $destination: String!, $date: String!) {
              flightOffers(origin: $origin, destination: $destination, date: $date) {
                airline
              }
            }
            """,
            {"origin": "DEL", "destination": "BOM", "date": "2026-05-29"},
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]["flightOffers"]
        self.assertEqual(len(results), 2)
        self.assertEqual(
            {offer["airline"] for offer in results},
            {"Air India", "Akasa Air"},
        )

    def test_search_sorts_by_price_by_default(self):
        response = self.graphql(
            """
            query FlightOffers {
              flightOffers(destination: "BOM") {
                airline
                providerUrl
              }
            }
            """
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]["flightOffers"]
        self.assertEqual(results[0]["airline"], "Akasa Air")
        self.assertEqual(results[0]["providerUrl"], "https://example.com/akasa-search")

    def test_search_can_sort_by_departure(self):
        response = self.graphql(
            """
            query FlightOffers {
              flightOffers(destination: "BOM", sort: "departure") {
                departureTime
              }
            }
            """
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["flightOffers"][0]["departureTime"], "07:00")

    def test_metadata_queries_use_existing_offers(self):
        response = self.graphql(
            """
            query Metadata {
              airports
              airlines
              providers
            }
            """
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["airports"], ["BLR", "BOM", "DEL"])
        self.assertEqual(data["airlines"], ["Air India", "Akasa Air", "IndiGo"])
        self.assertEqual(data["providers"], ["yatra"])

    def test_stop_fare_summary_uses_lowest_positive_price_per_category(self):
        FlightOffer.objects.create(
            search=self.search,
            source="yatra",
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            airline="IndiGo",
            stops="1 Stop",
            price_amount=Decimal("0.00"),
        )
        FlightOffer.objects.create(
            search=self.search,
            source="yatra",
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            airline="IndiGo",
            stops="1 Stop",
            price_amount=Decimal("7200.00"),
        )
        FlightOffer.objects.create(
            search=self.search,
            source="yatra",
            origin="DEL",
            destination="BOM",
            departure_date="2026-05-29",
            airline="SpiceJet",
            stops="2 Stops",
            price_amount=Decimal("6900.00"),
        )

        response = self.graphql(
            """
            query StopFareSummary($origin: String!, $destination: String!, $date: String!) {
              stopFareSummary(origin: $origin, destination: $destination, date: $date) {
                direct { count priceAmount currency }
                one { count priceAmount currency }
                multi { count priceAmount currency }
              }
            }
            """,
            {"origin": "DEL", "destination": "BOM", "date": "2026-05-29"},
        )

        self.assertEqual(response.status_code, 200)
        summary = response.json()["data"]["stopFareSummary"]
        self.assertEqual(summary["direct"]["priceAmount"], "4500.00")
        self.assertEqual(summary["one"]["count"], 1)
        self.assertEqual(summary["one"]["priceAmount"], "7200.00")
        self.assertEqual(summary["multi"]["priceAmount"], "6900.00")
