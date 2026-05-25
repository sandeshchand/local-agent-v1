from __future__ import annotations

import json

from agent.planner import Planner
from app.weather_tool import CurrentWeatherTool


class ChatClientStub:
    pass


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, params: dict, timeout: float) -> FakeResponse:
        self.urls.append(url)
        if "geocoding-api" in url:
            return FakeResponse(
                {
                    "results": [
                        {
                            "name": "Berlin",
                            "admin1": "Berlin",
                            "country": "Germany",
                            "latitude": 52.52,
                            "longitude": 13.41,
                            "timezone": "Europe/Berlin",
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "timezone": "Europe/Berlin",
                "current_units": {
                    "temperature_2m": "°C",
                    "apparent_temperature": "°C",
                    "relative_humidity_2m": "%",
                    "precipitation": "mm",
                    "wind_speed_10m": "km/h",
                },
                "current": {
                    "time": "2026-05-25T12:00",
                    "temperature_2m": 21.5,
                    "apparent_temperature": 20.8,
                    "relative_humidity_2m": 45,
                    "precipitation": 0.0,
                    "wind_speed_10m": 11.2,
                    "weather_code": 1,
                },
            }
        )


def main() -> None:
    session = FakeSession()
    tool = CurrentWeatherTool(session=session)
    output = json.loads(tool("Berlin"))

    assert output["tool"] == "get_current_weather"
    assert output["location"] == "Berlin, Berlin, Germany"
    assert output["temperature"] == "21.5 °C"
    assert output["condition"] == "Mainly clear"
    assert len(session.urls) == 2

    planner = Planner(chat_client=ChatClientStub())
    plan = planner.plan("What is the current weather in Berlin?")

    assert plan.mode == "tool_only"
    assert plan.tool_name == "get_current_weather"
    assert plan.tool_args["location"] == "Berlin"

    temperature_plan = planner.plan("What is the temperature in Berlin?")
    assert temperature_plan.mode == "tool_only"
    assert temperature_plan.tool_name == "get_current_weather"
    assert temperature_plan.tool_args["location"] == "Berlin"

    print("Weather tool smoke test passed.")


if __name__ == "__main__":
    main()
