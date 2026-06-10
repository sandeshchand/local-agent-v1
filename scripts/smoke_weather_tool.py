from __future__ import annotations

import json

from local_agent.agent.planner import Planner
from local_agent.tools import CurrentWeatherTool
from local_agent.answering import AnswerService


class ChatClientStub:
    def generate(self, prompt: str) -> str:
        raise AssertionError("Weather JSON should be answered deterministically.")


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
        self.names: list[str] = []

    def get(self, url: str, params: dict, timeout: float) -> FakeResponse:
        self.urls.append(url)
        if "geocoding-api" in url:
            name = params.get("name", "")
            self.names.append(name)
            if name.lower() == "stuttgat":
                return FakeResponse({"results": []})
            if name.lower() == "stuttga":
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "Stuttgart",
                                "admin1": "Baden-Wurttemberg",
                                "country": "Germany",
                                "latitude": 48.78,
                                "longitude": 9.18,
                                "timezone": "Europe/Berlin",
                            }
                        ]
                    }
                )
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
                    "temperature_2m": "degC",
                    "apparent_temperature": "degC",
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
    assert output["temperature"] == "21.5 degC"
    assert output["condition"] == "Mainly clear"
    assert len(session.urls) == 2

    typo_output = json.loads(tool("stuttgat"))
    assert typo_output["location"] == "Stuttgart, Baden-Wurttemberg, Germany"
    assert "stuttgat" in session.names
    assert "stuttga" in session.names

    planner = Planner(chat_client=ChatClientStub())
    plan = planner.plan("What is the current weather in Berlin?")

    assert plan.mode == "tool_only"
    assert plan.tool_name == "get_current_weather"
    assert plan.tool_args["location"] == "Berlin"

    temperature_plan = planner.plan("What is the temperature in Berlin?")
    assert temperature_plan.mode == "tool_only"
    assert temperature_plan.tool_name == "get_current_weather"
    assert temperature_plan.tool_args["location"] == "Berlin"

    temperature_of_plan = planner.plan("What is the temperature of Stuttgart?")
    assert temperature_of_plan.mode == "tool_only"
    assert temperature_of_plan.tool_name == "get_current_weather"
    assert temperature_of_plan.tool_args["location"] == "Stuttgart"

    of_plan = planner.plan("What is the current weather of stuttgat?")
    assert of_plan.mode == "tool_only"
    assert of_plan.tool_name == "get_current_weather"
    assert of_plan.tool_args["location"] == "stuttgat"

    answer_service = AnswerService(chat_client=ChatClientStub())
    answer = answer_service.answer_from_tool_result(
        query="What is the temperature of Berlin?",
        tool_context=json.dumps(output),
    )
    assert "21.5 degC" in answer
    assert "Berlin, Berlin, Germany" in answer
    assert "Mainly clear" in answer

    print("Weather tool smoke test passed.")


if __name__ == "__main__":
    main()
