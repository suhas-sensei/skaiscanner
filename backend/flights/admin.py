from django.contrib import admin

from .models import FlightOffer, FlightSearch


@admin.register(FlightSearch)
class FlightSearchAdmin(admin.ModelAdmin):
    list_display = ("origin", "destination", "departure_date", "status", "offers_found", "scraped_at")
    list_filter = ("status", "origin", "destination", "departure_date")
    search_fields = ("origin", "destination")
    readonly_fields = ("scraped_at",)


@admin.register(FlightOffer)
class FlightOfferAdmin(admin.ModelAdmin):
    list_display = (
        "origin",
        "destination",
        "departure_date",
        "airline",
        "flight_number",
        "price_amount",
        "currency",
        "stops",
        "provider_link_status",
        "scraped_at",
    )
    list_filter = ("source", "origin", "destination", "departure_date", "airline", "currency", "provider_link_status")
    search_fields = ("airline", "flight_number", "origin", "destination", "provider_offer_key")
    readonly_fields = ("scraped_at",)
