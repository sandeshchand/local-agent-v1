from __future__ import annotations

from difflib import SequenceMatcher
import json
import re
from typing import Any

import requests


class CurrentWeatherTool:
    """Read-only current weather tool backed by Open-Meteo."""

    geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
    forecast_url = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, session: Any | None = None, timeout_seconds: float = 10.0) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def __call__(self, location: str = "") -> str:
        location = self._clean_location(location)
        if not location:
            return "Please provide a location for the weather request."

        place = self._geocode_with_retry(location)
        if place is None:
            return f"Could not find a weather location matching '{location}'."

        weather = self._current_weather(place["latitude"], place["longitude"])
        if not weather:
            return f"Could not fetch current weather for {self._place_label(place)}."

        return self._format_weather(place, weather)

    def _clean_location(self, location: str) -> str:
        strip_chars = " ?.!,"
        location = re.sub(r"\s+", " ", location).strip(strip_chars)
        location = re.sub(r"^(?:of|in|for|at|near)\s+", "", location, flags=re.IGNORECASE)
        location = re.sub(
            r"\b(?:right now|now|today|currently|outside|weather|temperature|please)\b",
            "",
            location,
            flags=re.IGNORECASE,
        )
        location = location.strip()
        location = re.sub(r"^(?:of|in|for|at|near)\s+", "", location, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", location).strip(strip_chars)

    def _geocode_with_retry(self, location: str) -> dict[str, Any] | None:
        for candidate in self._location_candidates(location):
            place = self._geocode(candidate)
            if place is None:
                continue
            if self._looks_like_location_match(location, candidate, place):
                return place
        return None

    def _location_candidates(self, location: str) -> list[str]:
        candidates = [location]
        parts = location.split()
        if parts and len(parts[-1]) >= 5:
            shortened_parts = [*parts[:-1], parts[-1][:-1]]
            candidates.append(" ".join(shortened_parts))
        return list(dict.fromkeys(candidate for candidate in candidates if candidate))

    def _looks_like_location_match(
        self,
        original_location: str,
        candidate: str,
        place: dict[str, Any],
    ) -> bool:
        place_name = str(place.get("name") or "")
        if not place_name:
            return True
        original = self._compact_location(original_location)
        candidate_compact = self._compact_location(candidate)
        place_compact = self._compact_location(place_name)
        if place_compact.startswith(candidate_compact) or candidate_compact.startswith(place_compact):
            return True
        return SequenceMatcher(None, original, place_compact).ratio() >= 0.78

    def _compact_location(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _geocode(self, location: str) -> dict[str, Any] | None:
        response = self.session.get(
            self.geocoding_url,
            params={
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            return None
        return results[0]

    def _current_weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        response = self.session.get(
            self.forecast_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "precipitation,weather_code,wind_speed_10m"
                ),
                "timezone": "auto",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _format_weather(self, place: dict[str, Any], weather: dict[str, Any]) -> str:
        current = weather.get("current") or {}
        units = weather.get("current_units") or {}
        weather_code = current.get("weather_code")
        payload = {
            "tool": "get_current_weather",
            "location": self._place_label(place),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "timezone": weather.get("timezone") or place.get("timezone"),
            "time": current.get("time"),
            "temperature": self._with_unit(current.get("temperature_2m"), units.get("temperature_2m")),
            "apparent_temperature": self._with_unit(
                current.get("apparent_temperature"),
                units.get("apparent_temperature"),
            ),
            "relative_humidity": self._with_unit(
                current.get("relative_humidity_2m"),
                units.get("relative_humidity_2m"),
            ),
            "precipitation": self._with_unit(current.get("precipitation"), units.get("precipitation")),
            "wind_speed": self._with_unit(current.get("wind_speed_10m"), units.get("wind_speed_10m")),
            "condition": self._weather_code_label(weather_code),
            "source": "Open-Meteo forecast and geocoding APIs",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _place_label(self, place: dict[str, Any]) -> str:
        parts = [
            place.get("name"),
            place.get("admin1"),
            place.get("country"),
        ]
        return ", ".join(str(part) for part in parts if part)

    def _with_unit(self, value: Any, unit: str | None) -> str | None:
        if value is None:
            return None
        return f"{value} {unit}".strip() if unit else str(value)

    def _weather_code_label(self, code: Any) -> str:
        labels = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }
        try:
            return labels.get(int(code), f"Weather code {code}")
        except (TypeError, ValueError):
            return "Unknown"
