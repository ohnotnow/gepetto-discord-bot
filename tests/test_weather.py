"""Tests for src/content/weather.py — Met Office forecast formatting.

The bug these guard against: the daily endpoint collapses a day into
day/night averages, so a wet-morning-bright-afternoon day arrived at the
LLM as "Cloudy, 61% rain" and the LLM invented its own timing. The hourly
formatter exists to keep that timing intact.
"""

import datetime
import json
from types import SimpleNamespace

import pytest

from src.content import weather
from src.content.weather import (
    build_met_office_forecast,
    format_met_office_forecast,
    format_met_office_hourly_forecast,
    get_details_from_prompt,
)

# 25 July 2026 was a Saturday.
DAY = datetime.date(2026, 7, 25)
NEXT_DAY = datetime.date(2026, 7, 26)


def _hour(utc_hour: int, code: int = 7, temp: float = 15.0, rain: int = 10,
          wind: float = 5.0, gust: float = 10.0, precip: float = 0.0,
          uv: int = 1, day: int = 25) -> dict:
    return {
        "time": f"2026-07-{day:02d}T{utc_hour:02d}:00Z",
        "significantWeatherCode": code,
        "screenTemperature": temp,
        "feelsLikeTemperature": temp - 2,
        "probOfPrecipitation": rain,
        "totalPrecipAmount": precip,
        "windSpeed10m": wind,
        "windGustSpeed10m": gust,
        "uvIndex": uv,
    }


def _payload(hours: list[dict], name: str = "Glasgow") -> dict:
    return {"features": [{"properties": {"location": {"name": name}, "timeSeries": hours}}]}


def _daily_payload(entries: list[dict], name: str = "Glasgow") -> dict:
    return {"features": [{"properties": {"location": {"name": name}, "timeSeries": entries}}]}


class TestHourlyBucketing:
    def test_hours_land_in_their_local_time_bucket(self):
        # 05:00Z is 06:00 BST — morning, not overnight.
        text = format_met_office_hourly_forecast(_payload([_hour(5)]), [DAY], "Glasgow")
        assert "Morning (06:00-06:00" in text
        assert "Overnight" not in text

    def test_rain_timing_survives_into_the_summary(self):
        """The whole point: wet morning and dry afternoon stay distinguishable."""
        hours = [_hour(h, code=12, rain=90, precip=0.5) for h in range(7, 11)]
        hours += [_hour(h, code=3, rain=2) for h in range(11, 17)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")

        morning, afternoon = [line for line in text.splitlines() if "Morning" in line or "Afternoon" in line]
        assert "Light rain" in morning
        assert "up to 90%" in morning
        assert "2.0mm expected" in morning
        assert "Light rain" not in afternoon
        assert "up to 2%" in afternoon

    def test_condition_changes_are_kept_in_order(self):
        hours = [_hour(7, code=12), _hour(8, code=12), _hour(9, code=7), _hour(10, code=1)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Light rain -> Cloudy -> Sunny day" in text

    def test_long_condition_runs_are_truncated(self):
        hours = [_hour(7, code=12), _hour(8, code=7), _hour(9, code=1), _hour(10, code=15)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Light rain -> Cloudy -> Sunny day -> ..." in text

    def test_day_night_qualifiers_are_stripped(self):
        """"Partly cloudy (day)" inside an Evening bucket reads as wrong."""
        text = format_met_office_hourly_forecast(_payload([_hour(18, code=3)]), [DAY], "Glasgow")
        assert "Partly cloudy." in text
        assert "(day)" not in text

    def test_short_bucket_is_flagged_as_partial(self):
        """The feed starts at the current hour, so today's first bucket is a stub."""
        text = format_met_office_hourly_forecast(_payload([_hour(10)]), [DAY], "Glasgow")
        assert "partial" in text

    def test_complete_bucket_is_not_flagged_partial(self):
        hours = [_hour(h) for h in range(11, 17)]  # 12:00-17:00 BST
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Afternoon (12:00-17:00):" in text
        assert "partial" not in text

    def test_wind_is_converted_to_mph_not_left_in_mps(self):
        text = format_met_office_hourly_forecast(
            _payload([_hour(13, wind=7.04, gust=12.31)]), [DAY], "Glasgow")
        assert "Wind 16mph" in text
        assert "gusts to 28mph" in text
        assert "m/s" not in text

    def test_zero_uv_is_omitted(self):
        text = format_met_office_hourly_forecast(_payload([_hour(1, uv=0)]), [DAY], "Glasgow")
        assert "UV" not in text

    def test_dry_bucket_omits_the_millimetre_figure(self):
        text = format_met_office_hourly_forecast(_payload([_hour(13, rain=0, precip=0.0)]), [DAY], "Glasgow")
        assert "mm expected" not in text

    def test_multiple_days_are_reported_separately(self):
        hours = [_hour(13, day=25), _hour(13, day=26)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY, NEXT_DAY], "Glasgow")
        assert "2026-07-25 (Saturday):" in text
        assert "2026-07-26 (Sunday):" in text

    def test_only_requested_dates_appear(self):
        hours = [_hour(13, day=25), _hour(13, day=26)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "2026-07-25 (Saturday):" in text
        assert "2026-07-26 (Sunday):" not in text


class TestTonightIsNotLost:
    """Tonight's small hours fall on tomorrow's date. Asking for "today"
    must still mention them — the daily endpoint always did, because its
    "night" period sits in the same entry as its "day"."""

    def test_overnight_after_the_requested_day_is_appended(self):
        hours = [_hour(13, day=25)]
        hours += [_hour(h, code=15, rain=88, precip=1.2, day=26) for h in range(1, 4)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Overnight into Sunday (2026-07-26):" in text
        assert "Heavy rain" in text
        assert "up to 88%" in text

    def test_only_the_small_hours_are_appended_not_the_whole_day(self):
        hours = [_hour(13, day=25), _hour(2, day=26), _hour(13, code=1, day=26)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Overnight into Sunday" in text
        assert "Sunny day" not in text

    def test_not_appended_when_the_next_day_was_requested_anyway(self):
        hours = [_hour(13, day=25), _hour(2, day=26), _hour(13, day=26)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY, NEXT_DAY], "Glasgow")
        assert "Overnight into" not in text
        assert "2026-07-26 (Sunday):" in text

    def test_absent_when_the_feed_has_no_small_hours(self):
        text = format_met_office_hourly_forecast(_payload([_hour(13, day=25)]), [DAY], "Glasgow")
        assert "Overnight into" not in text

    def test_suppressed_when_a_daily_section_covers_that_date(self):
        """Otherwise "clear overnight" and "light rain all day" collide."""
        hours = [_hour(13, day=25), _hour(2, day=26)]
        text = format_met_office_hourly_forecast(
            _payload(hours), [DAY], "Glasgow", include_following_night=False)
        assert "Overnight into" not in text
        assert "2026-07-25 (Saturday):" in text

    @pytest.mark.asyncio
    async def test_routing_suppresses_the_tail_when_daily_days_follow(self, monkeypatch):
        async def fake_fetch(lat, long, period="daily"):
            if period == "hourly":
                return _payload([_hour(13, day=25), _hour(13, day=26), _hour(2, day=27)])
            return _daily_payload([{"time": "2026-07-27T00:00Z", "dayMaxScreenTemperature": 18.0}])

        monkeypatch.setattr(weather, "get_forecast_met_office", fake_fetch)
        monkeypatch.setattr(weather.datetime, "date", _fake_date_class())

        dates = [DAY + datetime.timedelta(days=n) for n in range(3)]
        text = await build_met_office_forecast(55.86, -4.25, dates, "Glasgow")
        assert "Overnight into" not in text
        assert "2026-07-27:" in text

    def test_current_conditions_shown_when_today_is_requested(self, monkeypatch):
        real_datetime = datetime.datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 7, 25, 8, 30, tzinfo=weather.UK_TZ)

        monkeypatch.setattr(weather.datetime, "datetime", FakeDatetime)
        text = format_met_office_hourly_forecast(
            _payload([_hour(7, code=12, temp=14.68, rain=61)]), [DAY], "Glasgow")
        assert "Conditions right now (08:00): Light rain, 15°C" in text
        assert "61% chance of rain" in text

    def test_no_current_conditions_for_a_future_day(self, monkeypatch):
        real_datetime = datetime.datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 7, 25, 8, 30, tzinfo=weather.UK_TZ)

        monkeypatch.setattr(weather.datetime, "datetime", FakeDatetime)
        text = format_met_office_hourly_forecast(_payload([_hour(13, day=26)]), [NEXT_DAY], "Glasgow")
        assert "right now" not in text

    def test_location_name_read_from_payload_when_not_supplied(self):
        """It lives at properties.location.name, not properties.locationName."""
        text = format_met_office_hourly_forecast(_payload([_hour(13)], name="Norwich"), [DAY])
        assert "forecast for Norwich" in text

    @pytest.mark.parametrize("payload", [{}, {"features": []}, {"features": [{"properties": {}}]}])
    def test_empty_payloads_return_empty_string(self, payload):
        assert format_met_office_hourly_forecast(payload, [DAY], "Glasgow") == ""

    def test_unmatched_dates_return_empty_string_not_a_bare_header(self):
        """An empty header would tell the LLM there is a forecast when there isn't."""
        assert format_met_office_hourly_forecast(_payload([_hour(13)]), [datetime.date(2030, 1, 1)]) == ""

    def test_unparseable_timestamps_are_skipped(self):
        hours = [{"time": "not-a-date", "significantWeatherCode": 7}, _hour(13)]
        text = format_met_office_hourly_forecast(_payload(hours), [DAY], "Glasgow")
        assert "Afternoon" in text

    def test_missing_fields_do_not_raise(self):
        text = format_met_office_hourly_forecast(
            _payload([{"time": "2026-07-25T13:00Z"}]), [DAY], "Glasgow")
        assert "Afternoon" in text


class TestDailyFormatting:
    def test_wind_converted_to_mph(self):
        entry = {"time": "2026-07-25T00:00Z", "midday10MWindSpeed": 7.04, "midday10MWindGust": 12.31}
        text = format_met_office_forecast(_daily_payload([entry]), [DAY], "Glasgow")
        assert "Wind: 16mph (gusts 28mph)." in text
        assert "m/s" not in text

    def test_location_name_read_from_payload(self):
        entry = {"time": "2026-07-25T00:00Z", "dayMaxScreenTemperature": 18.25}
        text = format_met_office_forecast(_daily_payload([entry], name="Norwich"), [DAY])
        assert "forecast for Norwich" in text


class TestForecastRouting:
    """Hourly for today/tomorrow, daily beyond, daily if hourly is missing."""

    @pytest.fixture
    def calls(self, monkeypatch):
        recorded = []

        async def fake_fetch(lat, long, period="daily"):
            recorded.append(period)
            if period == "hourly":
                return _payload([_hour(13, day=25), _hour(13, day=26)])
            return _daily_payload([
                {"time": f"2026-07-{d}T00:00Z", "dayMaxScreenTemperature": 18.0}
                for d in ("25", "26", "27", "28")
            ])

        monkeypatch.setattr(weather, "get_forecast_met_office", fake_fetch)
        monkeypatch.setattr(weather.datetime, "date", _fake_date_class())
        return recorded

    @pytest.mark.asyncio
    async def test_today_only_uses_hourly_alone(self, calls):
        text = await build_met_office_forecast(55.86, -4.25, [DAY], "Glasgow")
        assert calls == ["hourly"]
        assert "hourly forecast" in text

    @pytest.mark.asyncio
    async def test_a_week_uses_both_endpoints(self, calls):
        dates = [DAY + datetime.timedelta(days=n) for n in range(4)]
        text = await build_met_office_forecast(55.86, -4.25, dates, "Glasgow")
        assert calls == ["hourly", "daily"]
        assert "hourly forecast" in text
        assert "Met Office forecast for Glasgow" in text

    @pytest.mark.asyncio
    async def test_distant_dates_skip_the_hourly_call(self, calls):
        text = await build_met_office_forecast(55.86, -4.25, [DAY + datetime.timedelta(days=5)], "Glasgow")
        assert calls == ["daily"]
        assert "hourly" not in text

    @pytest.mark.asyncio
    async def test_falls_back_to_daily_when_hourly_is_unavailable(self, monkeypatch):
        recorded = []

        async def fake_fetch(lat, long, period="daily"):
            recorded.append(period)
            if period == "hourly":
                return None
            return _daily_payload([{"time": "2026-07-25T00:00Z", "dayMaxScreenTemperature": 18.0}])

        monkeypatch.setattr(weather, "get_forecast_met_office", fake_fetch)
        monkeypatch.setattr(weather.datetime, "date", _fake_date_class())

        text = await build_met_office_forecast(55.86, -4.25, [DAY], "Glasgow")
        assert recorded == ["hourly", "daily"]
        assert "Met Office forecast for Glasgow" in text

    @pytest.mark.asyncio
    async def test_returns_empty_when_both_endpoints_fail(self, monkeypatch):
        async def fake_fetch(lat, long, period="daily"):
            return None

        monkeypatch.setattr(weather, "get_forecast_met_office", fake_fetch)
        monkeypatch.setattr(weather.datetime, "date", _fake_date_class())
        assert await build_met_office_forecast(55.86, -4.25, [DAY], "Glasgow") == ""


class TestPromptExtractionGuards:
    """A model that answers in prose instead of calling the tool used to
    take the whole weather command down with an IndexError."""

    class FakeChat:
        def __init__(self, response):
            self.response = response
            self.name = "Gepetto"

        async def chat(self, messages, tools=None):
            return self.response

    @staticmethod
    def _tool_response(arguments: str):
        return SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(arguments=arguments))])

    @pytest.mark.asyncio
    async def test_extracts_locations_and_dates_normally(self):
        chatbot = self.FakeChat(self._tool_response(json.dumps({
            "locations": ["Glasgow"], "start_date": "2026-07-25", "end_date": "2026-07-26",
        })))
        locations, start, end = await get_details_from_prompt("weather in Glasgow?", chatbot)
        assert locations == ["Glasgow"]
        assert (start, end) == ("2026-07-25", "2026-07-26")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response", [
        SimpleNamespace(tool_calls=None),
        SimpleNamespace(tool_calls=[]),
        SimpleNamespace(message="It looks lovely out!"),
    ])
    async def test_a_reply_without_a_tool_call_returns_no_locations(self, response):
        locations, start, end = await get_details_from_prompt("weather?", self.FakeChat(response))
        assert locations is None
        assert start == end

    @pytest.mark.asyncio
    async def test_unparseable_arguments_return_no_locations(self):
        chatbot = self.FakeChat(self._tool_response("{not json"))
        locations, _, _ = await get_details_from_prompt("weather?", chatbot)
        assert locations is None

    @pytest.mark.asyncio
    async def test_dates_always_come_back_as_strptime_safe_strings(self):
        """The caller runs strptime() on these *before* checking locations,
        so a present-but-null date has to be replaced, not passed through."""
        chatbot = self.FakeChat(self._tool_response(json.dumps({
            "locations": ["Glasgow"], "start_date": None, "end_date": None,
        })))
        _, start, end = await get_details_from_prompt("weather in Glasgow?", chatbot)
        for value in (start, end):
            assert datetime.datetime.strptime(value, "%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_fallback_dates_are_strptime_safe_too(self):
        _, start, end = await get_details_from_prompt("weather?", self.FakeChat(SimpleNamespace(tool_calls=[])))
        for value in (start, end):
            assert datetime.datetime.strptime(value, "%Y-%m-%d")


def _fake_date_class():
    """datetime.date with today() pinned to 25 July 2026."""
    real_date = datetime.date

    class FakeDate(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 7, 25)

    return FakeDate
