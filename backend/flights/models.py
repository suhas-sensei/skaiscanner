from django.db import models


class FlightSearch(models.Model):
    STATUS_CHOICES = [
        ("success", "Success"),
        ("no_results", "No results"),
        ("failed", "Failed"),
    ]

    origin = models.CharField(max_length=8, db_index=True)
    destination = models.CharField(max_length=8, db_index=True)
    departure_date = models.DateField(db_index=True)
    return_date = models.DateField(null=True, blank=True, db_index=True)
    trip_type = models.CharField(max_length=16, default="one_way", db_index=True)
    source = models.CharField(max_length=32, default="yatra")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    offers_found = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    search_url = models.URLField(max_length=1000, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-scraped_at"]
        indexes = [
            models.Index(fields=["origin", "destination", "departure_date", "trip_type"]),
        ]

    def __str__(self):
        return f"{self.origin}-{self.destination} {self.departure_date} {self.trip_type} ({self.status})"


class FlightOffer(models.Model):
    LINK_STATUS_CHOICES = [
        ("exact", "Exact provider offer link"),
        ("search_page", "Provider search page fallback"),
        ("session_required", "Provider session required"),
        ("unavailable", "Unavailable"),
    ]

    search = models.ForeignKey(FlightSearch, on_delete=models.CASCADE, related_name="offers")
    source = models.CharField(max_length=32, default="yatra", db_index=True)
    origin = models.CharField(max_length=8, db_index=True)
    destination = models.CharField(max_length=8, db_index=True)
    departure_date = models.DateField(db_index=True)
    return_date = models.DateField(null=True, blank=True, db_index=True)
    trip_type = models.CharField(max_length=16, default="one_way", db_index=True)
    airline = models.CharField(max_length=120, blank=True, db_index=True)
    flight_number = models.CharField(max_length=40, blank=True)
    departure_time = models.CharField(max_length=20, blank=True)
    arrival_time = models.CharField(max_length=20, blank=True)
    duration = models.CharField(max_length=80, blank=True)
    stops = models.CharField(max_length=80, blank=True)
    price_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, db_index=True)
    currency = models.CharField(max_length=8, default="INR")
    provider_offer_url = models.URLField(max_length=2000, blank=True)
    provider_search_url = models.URLField(max_length=2000, blank=True)
    provider_link_status = models.CharField(
        max_length=32,
        choices=LINK_STATUS_CHOICES,
        default="unavailable",
        db_index=True,
    )
    provider_offer_key = models.CharField(max_length=512, blank=True, db_index=True)
    raw_text = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["price_amount", "departure_time", "airline"]
        indexes = [
            models.Index(fields=["origin", "destination", "departure_date", "trip_type", "price_amount"]),
        ]

    def __str__(self):
        price = f"{self.currency} {self.price_amount}" if self.price_amount else "price unknown"
        return f"{self.airline or 'Unknown'} {self.origin}-{self.destination} {price}"
