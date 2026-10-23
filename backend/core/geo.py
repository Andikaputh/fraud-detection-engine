"""Geo utilities used by the velocity / impossible-travel features.

A real deployment would call a geocoding service and keep a country-risk feed.
The demo ships a compact centroid table so the scorer stays deterministic and
offline-capable.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Jakarta": (-6.2088, 106.8456),
    "Surabaya": (-7.2575, 112.7521),
    "Bandung": (-6.9175, 107.6191),
    "Medan": (3.5952, 98.6722),
    "Denpasar": (-8.6705, 115.2126),
    "Singapore": (1.3521, 103.8198),
    "Kuala Lumpur": (3.139, 101.6869),
    "Bangkok": (13.7563, 100.5018),
    "Manila": (14.5995, 120.9842),
    "Ho Chi Minh City": (10.8231, 106.6297),
}

COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "ID": (-6.2088, 106.8456),
    "SG": (1.3521, 103.8198),
    "MY": (3.139, 101.6869),
    "TH": (13.7563, 100.5018),
    "PH": (14.5995, 120.9842),
    "VN": (10.8231, 106.6297),
    "US": (37.0902, -95.7129),
    "GB": (55.3781, -3.436),
    "AU": (-25.2744, 133.7751),
    "JP": (36.2048, 138.2529),
    "CN": (35.8617, 104.1954),
    "RU": (61.524, 105.3188),
    "NG": (9.082, 8.6753),
    "BR": (-14.235, -51.9253),
    "IN": (20.5937, 78.9629),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def coords_for(country: str | None, city: str | None = None) -> tuple[float, float]:
    if city and city in CITY_COORDS:
        return CITY_COORDS[city]
    if country and country in COUNTRY_COORDS:
        return COUNTRY_COORDS[country]
    return COUNTRY_COORDS["ID"]
