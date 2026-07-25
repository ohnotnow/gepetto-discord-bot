import requests
import os
import datetime
import random
import logging
import json
from zoneinfo import ZoneInfo

logger = logging.getLogger('discord')

UK_TZ = ZoneInfo("Europe/London")
MPS_TO_MPH = 2.23694

# Local-time buckets the hourly forecast is summarised into. The daily
# endpoint collapses a day to day/night averages, so it cannot say "wet
# morning, bright afternoon" — the LLM was left inventing the timing.
# See scripts/try_weather.py to compare the two side by side.
HOURLY_BUCKETS = (
    ("Overnight", 0, 6),
    ("Morning", 6, 12),
    ("Afternoon", 12, 18),
    ("Evening", 18, 24),
)

MET_OFFICE_WEATHER_CODES = {
    0: "Clear night", 1: "Sunny day", 2: "Partly cloudy (night)",
    3: "Partly cloudy (day)", 5: "Mist", 6: "Fog", 7: "Cloudy",
    8: "Overcast", 9: "Light rain shower (night)", 10: "Light rain shower (day)",
    11: "Drizzle", 12: "Light rain", 13: "Heavy rain shower (night)",
    14: "Heavy rain shower (day)", 15: "Heavy rain", 16: "Sleet shower (night)",
    17: "Sleet shower (day)", 18: "Sleet", 19: "Hail shower (night)",
    20: "Hail shower (day)", 21: "Hail", 22: "Light snow shower (night)",
    23: "Light snow shower (day)", 24: "Light snow", 25: "Heavy snow shower (night)",
    26: "Heavy snow shower (day)", 27: "Heavy snow", 28: "Thunder shower (night)",
    29: "Thunder shower (day)", 30: "Thunder",
}


async def get_details_from_prompt(question, chatbot):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Today: {today}")
    system_prompt = (
        "You are a helpful assistant who is an expert at picking out UK town and city names from user prompts and extracting the date or date-range the user wants a UK weather forecast for. "
        f"Use today's date ({today}) to turn words like 'today', 'tomorrow', 'next three days' into ISO-dates."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "extract_weather_forecast_details",
                "description": "Extract the place-names and the date or date-range the user wants a UK weather forecast for.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "locations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "One or more UK place-names, e.g. ['Glasgow', 'Norwich']"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "ISO-8601 calendar date the forecast should start on, e.g. '2025-06-02'"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "ISO-8601 calendar date the forecast should end on (inclusive). If the user only gave one day use the same value as start_date."
                        }
                    },
                    "required": ["locations", "start_date", "end_date"],
                    "additionalProperties": False
                },
                "strict": True
            }
        }
    ]
    response = await chatbot.chat(messages, tools=tools)
    logger.debug(f"Response: {response}")

    # The tool is declared strict, but a model that answers in prose
    # instead of calling it would otherwise take the whole weather command
    # down with an IndexError. No locations sends the caller down its
    # existing path of just answering the question as a plain chat message.
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        logger.warning(f"No tool call in the location-extraction reply for '{question}'")
        return None, today, today
    try:
        arguments = json.loads(tool_calls[0].function.arguments)
    except (AttributeError, TypeError, json.JSONDecodeError) as e:
        logger.warning(f"Could not parse location-extraction arguments for '{question}': {e}")
        return None, today, today

    # `or today` rather than a .get() default: a present-but-null date
    # would still crash the caller's strptime().
    return arguments.get("locations"), arguments.get("start_date") or today, arguments.get("end_date") or today


async def find_lat_long_from_location(location: str) -> tuple[float, float] | None:
    try:
        with open("geocode_cache.json", "r") as f:
            geocode_cache = json.load(f)
    except FileNotFoundError:
        geocode_cache = {}
    if location in geocode_cache:
        return geocode_cache[location]
    headers = {
        "User-Agent": "gepetto-discord-bot/1.0"
    }
    url = f"http://nominatim.openstreetmap.org/search?q={location},GB&format=json&addressdetails=1&limit=1"
    response = requests.get(url, headers=headers)
    decoded = response.json()
    if len(decoded) == 0:
        return None
    latitude = decoded[0]["lat"]
    longitude = decoded[0]["lon"]
    geocode_cache[location] = (latitude, longitude)
    with open("geocode_cache.json", "w") as f:
        json.dump(geocode_cache, f)
    return latitude, longitude


async def get_forecast_met_office(lat: float, long: float, period: str = "daily") -> dict | None:
    """Fetch a site-specific forecast. `period` is 'daily' or 'hourly'.

    The hourly endpoint returns ~49 entries starting at the current hour,
    so it covers today and tomorrow but no further.
    """
    api_key = os.getenv("MET_OFFICE_API_KEY")
    if not api_key:
        logger.info("MET_OFFICE_API_KEY not set, skipping Met Office forecast")
        return None
    url = (
        f"https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/{period}"
        f"?latitude={lat}&longitude={long}"
        f"&includeLocationName=true&dataSource=BD1"
    )
    headers = {"accept": "application/json", "apikey": api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Met Office {period} API request failed: {e}")
        return None


def _mps_to_mph(value: float) -> int:
    return round(value * MPS_TO_MPH)


def _met_office_properties(data: dict) -> dict:
    features = data.get("features", [])
    if not features:
        return {}
    return features[0].get("properties", {})


def _met_office_location_name(props: dict) -> str:
    """The name sits at properties.location.name, not properties.locationName."""
    return (props.get("location") or {}).get("name", "")


def _uk_local_time(raw_time: str) -> datetime.datetime | None:
    """Met Office times are UTC; the day a user means is the local one."""
    try:
        parsed = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UK_TZ)


def _present_values(hours: list[dict], field: str) -> list:
    return [hour[field] for hour in hours if hour.get(field) is not None]


def _range_text(values: list[float]) -> str:
    low, high = round(min(values)), round(max(values))
    return f"{low}" if low == high else f"{low}-{high}"


def _condition_name(code) -> str:
    """Weather-code name without its (day)/(night) qualifier.

    The bucket label already says which part of the day it is, and
    "Partly cloudy (day)" inside an Evening bucket just reads as wrong.
    """
    name = MET_OFFICE_WEATHER_CODES.get(code, f"Code {code}")
    return name.replace(" (day)", "").replace(" (night)", "")


def _condition_run(hours: list[dict]) -> str:
    """Conditions in order, with consecutive repeats collapsed.

    Keeps the shape of the period ("Light rain -> Cloudy") rather than
    flattening it to one code, which is what misled the LLM before.
    """
    names = []
    for hour in hours:
        name = _condition_name(hour.get("significantWeatherCode"))
        if not names or names[-1] != name:
            names.append(name)
    if len(names) > 3:
        names = names[:3] + ["..."]
    return " -> ".join(names) if names else "Unknown"


def _format_current_conditions(entry: dict) -> str:
    bits = [_condition_name(entry.get("significantWeatherCode"))]
    temp = entry.get("screenTemperature")
    if temp is not None:
        feels = entry.get("feelsLikeTemperature")
        bits.append(f"{round(temp)}°C" + (f" (feels {round(feels)}°C)" if feels is not None else ""))
    rain = entry.get("probOfPrecipitation")
    if rain is not None:
        bits.append(f"{round(rain)}% chance of rain")
    wind = entry.get("windSpeed10m")
    if wind is not None:
        text = f"wind {_mps_to_mph(wind)}mph"
        gust = entry.get("windGustSpeed10m")
        if gust is not None:
            text += f" gusting {_mps_to_mph(gust)}mph"
        bits.append(text)
    return ", ".join(bits) + "."


def _format_bucket(label: str, hours: list[dict], expected_hours: int) -> str:
    first = _uk_local_time(hours[0].get("time", ""))
    last = _uk_local_time(hours[-1].get("time", ""))
    span = f"{first:%H:%M}-{last:%H:%M}" if first and last else "?"
    # Flag short buckets so the LLM doesn't describe a whole morning when
    # we only hold data from 08:00 — the hourly feed starts at "now".
    partial = ", partial" if len(hours) < expected_hours else ""
    line = f"  {label} ({span}{partial}): {_condition_run(hours)}."

    temps = _present_values(hours, "screenTemperature")
    if temps:
        line += f" {_range_text(temps)}°C"
        feels = _present_values(hours, "feelsLikeTemperature")
        if feels:
            line += f" (feels {_range_text(feels)}°C)"
        line += "."

    rain = _present_values(hours, "probOfPrecipitation")
    if rain:
        line += f" Rain chance up to {round(max(rain))}%"
        total_rain = sum(_present_values(hours, "totalPrecipAmount"))
        if total_rain > 0:
            line += f" ({total_rain:.1f}mm expected)"
        line += "."

    wind = _present_values(hours, "windSpeed10m")
    if wind:
        line += f" Wind {_range_text([_mps_to_mph(w) for w in wind])}mph"
        gusts = _present_values(hours, "max10mWindGust") or _present_values(hours, "windGustSpeed10m")
        if gusts:
            line += f", gusts to {_mps_to_mph(max(gusts))}mph"
        line += "."

    uv = _present_values(hours, "uvIndex")
    if uv and max(uv) > 0:
        line += f" UV up to {round(max(uv))}."

    return line


def format_met_office_hourly_forecast(data: dict, dates: list[datetime.date], location_name: str = "",
                                      include_following_night: bool = True) -> str:
    """Summarise the hourly feed into named parts of the day.

    `include_following_night` appends the small hours after the last
    requested day. Turn it off when a daily section already covers that
    date, or the two describe the same day and read as contradictory.
    """
    props = _met_office_properties(data)
    if not props:
        return ""
    location_name = location_name or _met_office_location_name(props) or "Unknown location"
    time_series = props.get("timeSeries", [])
    if not time_series:
        return ""

    hours_by_date: dict[datetime.date, list[tuple[datetime.datetime, dict]]] = {}
    for entry in time_series:
        local = _uk_local_time(entry.get("time", ""))
        if local is None:
            continue
        hours_by_date.setdefault(local.date(), []).append((local, entry))

    today = datetime.datetime.now(UK_TZ).date()
    lines = [f"Met Office hourly forecast for {location_name}:"]
    matched_dates = []
    for target in dates:
        hours = hours_by_date.get(target)
        if not hours:
            continue
        matched_dates.append(target)
        if target == today:
            now_local, now_entry = hours[0]
            lines.append(f"\nConditions right now ({now_local:%H:%M}): {_format_current_conditions(now_entry)}")
        lines.append(f"\n{target.isoformat()} ({target:%A}):")
        for label, start_hour, end_hour in HOURLY_BUCKETS:
            in_bucket = [entry for local, entry in hours if start_hour <= local.hour < end_hour]
            if in_bucket:
                lines.append(_format_bucket(label, in_bucket, end_hour - start_hour))

    if not matched_dates:
        return ""

    # The small hours that follow the last requested day fall on the *next*
    # calendar date, so "what's the weather today?" would otherwise stop at
    # 23:00 and lose tonight's rain — which the daily endpoint did report,
    # because its "night" period belongs to the same entry as its "day".
    tail_date = max(matched_dates) + datetime.timedelta(days=1)
    if include_following_night and tail_date not in dates:
        overnight = [entry for local, entry in hours_by_date.get(tail_date, []) if local.hour < 6]
        if overnight:
            lines.append(f"\nOvernight into {tail_date:%A} ({tail_date.isoformat()}):")
            lines.append(_format_bucket("Overnight", overnight, 6))

    return "\n".join(lines)


def format_met_office_forecast(data: dict, dates: list[datetime.date], location_name: str = "") -> str:
    props = _met_office_properties(data)
    if not props:
        return ""
    location_name = location_name or _met_office_location_name(props) or "Unknown location"
    time_series = props.get("timeSeries", [])

    date_strs = {d.isoformat() for d in dates}
    lines = [f"Met Office forecast for {location_name}:"]
    for entry in time_series:
        entry_date = entry.get("time", "")[:10]
        if entry_date not in date_strs:
            continue

        day_code = entry.get("daySignificantWeatherCode")
        night_code = entry.get("nightSignificantWeatherCode")
        day_weather = MET_OFFICE_WEATHER_CODES.get(day_code, f"Code {day_code}") if day_code is not None else None
        night_weather = MET_OFFICE_WEATHER_CODES.get(night_code, f"Code {night_code}") if night_code is not None else None

        day_max = entry.get("dayMaxScreenTemperature")
        night_min = entry.get("nightMinScreenTemperature")
        feels_like_max = entry.get("dayMaxFeelsLikeTemp")
        feels_like_min = entry.get("nightMinFeelsLikeTemp")
        wind_speed = entry.get("midday10MWindSpeed")
        wind_gust = entry.get("midday10MWindGust")
        rain_day = entry.get("dayProbabilityOfRain")
        rain_night = entry.get("nightProbabilityOfRain")
        humidity = entry.get("middayRelativeHumidity")
        uv = entry.get("maxUvIndex")

        line = f"\n{entry_date}:"
        if day_weather:
            line += f" Day: {day_weather}."
        if night_weather:
            line += f" Night: {night_weather}."
        if day_max is not None:
            line += f" High: {day_max}°C."
        if night_min is not None:
            line += f" Low: {night_min}°C."
        if feels_like_max is not None:
            line += f" Feels like: {feels_like_max}°C (day)"
        if feels_like_min is not None:
            line += f" / {feels_like_min}°C (night)."
        if wind_speed is not None:
            line += f" Wind: {_mps_to_mph(wind_speed)}mph"
        if wind_gust is not None:
            line += f" (gusts {_mps_to_mph(wind_gust)}mph)."
        if rain_day is not None:
            line += f" Rain chance: {rain_day}% (day)"
        if rain_night is not None:
            line += f" / {rain_night}% (night)."
        if humidity is not None:
            line += f" Humidity: {humidity}%."
        if uv is not None:
            line += f" UV index: {uv}."

        lines.append(line)

    return "\n".join(lines)


def _met_office_can_cover(dates: list[datetime.date]) -> bool:
    if not dates:
        return False
    today = datetime.date.today()
    max_met_date = today + datetime.timedelta(days=7)
    return all(today <= d <= max_met_date for d in dates)


async def build_met_office_forecast(lat: float, long: float, dates: list[datetime.date], location_name: str) -> str:
    """Hourly detail for today and tomorrow, daily summaries beyond that.

    The hourly feed only reaches ~48 hours, but it is the only place the
    intraday shape lives: a daily entry says "Cloudy, 61% rain" for a day
    that is actually wet until noon and bright after it.
    """
    today = datetime.date.today()
    hourly_cutoff = today + datetime.timedelta(days=1)
    hourly_dates = [d for d in dates if today <= d <= hourly_cutoff]
    daily_dates = [d for d in dates if d not in hourly_dates]

    sections = []
    if hourly_dates:
        hourly_data = await get_forecast_met_office(lat, long, period="hourly")
        hourly_text = format_met_office_hourly_forecast(
            hourly_data, hourly_dates, location_name,
            # A daily section, if there is one, already covers that date.
            include_following_night=not daily_dates,
        ) if hourly_data else ""
        if hourly_text:
            sections.append(hourly_text)
        else:
            logger.warning(f"No Met Office hourly data for {location_name}, falling back to daily")
            daily_dates = list(dates)

    if daily_dates:
        daily_data = await get_forecast_met_office(lat, long, period="daily")
        daily_text = format_met_office_forecast(daily_data, daily_dates, location_name) if daily_data else ""
        if daily_text:
            sections.append(daily_text)

    return "\n\n".join(sections)


async def get_forecast_openweathermap(lat: float, long: float, dates: list[datetime.date]) -> dict:
    """
    https://api.openweathermap.org/data/2.5/forecast?lat=44.34&lon=10.99&appid={API key}
    """
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if api_key is None:
        raise ValueError("OPENWEATHERMAP_API_KEY is not set")
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={long}&appid={api_key}"
    response = requests.get(url)
    logger.info(f"Response: {response}")
    return response.json()


async def get_friendly_forecast_openweathermap(question: str, chatbot):
    logger.info(f"Getting friendly forecast for '{question}'")
    forecast = ""
    locations, start_date, end_date = await get_details_from_prompt(question, chatbot)
    total_tokens = 0  # Initialize total_tokens

    logger.info(f"Parsed dates from question '{question}': {start_date} to {end_date}")
    logger.info(f"Parsed locations from question '{question}': {locations}")

    # build a list of dates from start_date to end_date
    dates = []
    current_date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    while current_date <= datetime.datetime.strptime(end_date, "%Y-%m-%d"):
        dates.append(current_date.date())
        current_date += datetime.timedelta(days=1)

    if not locations:
        response = await chatbot.chat([{"role": "user", "content": question}])
        forecast = response.message
        total_tokens += response.tokens
    else:
        use_met_office = _met_office_can_cover(dates)
        forecast_source = "Met Office" if use_met_office else "OpenWeatherMap"

        for location in locations:
            logger.info(f"Getting forecast for {location.strip()}")
            lat, long = await find_lat_long_from_location(location.strip())
            if lat is None or long is None:
                logger.error(f"Failed to find lat/long for {location.strip()}")
                continue

            met_forecast = ""
            if use_met_office:
                met_forecast = await build_met_office_forecast(float(lat), float(long), dates, location.strip())
                if met_forecast:
                    forecast += met_forecast + "\n"
                    logger.info(f"Using Met Office forecast for {location.strip()}")
                else:
                    logger.info(f"Met Office failed for {location.strip()}, falling back to OpenWeatherMap")
                    forecast_source = "OpenWeatherMap"
            if not met_forecast:
                temp_forecast = await get_forecast_openweathermap(lat, long, dates)
                forecast += json.dumps(temp_forecast) + "\n"
            logger.debug(f"Forecast so far: {forecast}")

        date_and_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")
        personality = ""
        if random.random() < 0.1:
            personality = "A secret agent"
        elif random.random() < 0.1:
            personality = "A secret alcoholic"
        elif random.random() < 0.1:
            personality = "Only telling the forecast because the station has kidnapped your family"
        elif random.random() < 0.1:
            personality = "A man who loves the Cumbrian countryside and being with his true love, Fanny"
        elif random.random() < 0.1:
            personality = "An anxious depressive who is always on the edge of a breakdown"

        if personality:
            personality = f" You should take on subtle hints of this personality for writing your forecast *but don't be too obvious* : {personality}."

        question_text = f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. I have the following weather forecasts for you from the {forecast_source} API based on their question.  Could you make the a bit more natural - like a weather presenter would give at the end of a drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add any extra context - the user only wants to see the friendly, drive-time style forecast.  Wind speeds are already in MPH - do not convert them. Where the forecast breaks the day into named periods, keep that timing intact - say when the rain arrives or clears rather than averaging it across the whole day. Feel free to use weather-specific emoji.  If the user did not specify a date or range, then assume they just care about today's weather.  {personality}  FORECAST : ''{forecast}''"

        logger.debug(f"Question: {question_text}")
        response = await chatbot.chat([
            {"role": "user", "content": question_text},
            {"role": "system", "content": f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not Fahrenheit for temperatures. Please take into account the likely average temperature and weather for the location and time of year (eg, don't say a forecast of 26C for June in Edinburgh is 'mild' - it's baking hot, relative to the average temperature for that time of year).  You MUST ONLY reply with the friendly forecast."}
        ])
        logger.info(f"Response: {response.message}")
        forecast = response.message + "\n" + response.usage_short
        total_tokens += response.tokens

    return forecast
