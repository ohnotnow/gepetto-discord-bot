import requests
import os
import datetime
import random
import logging
import json

logger = logging.getLogger('discord')

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
    logger.info('QQQQQ')
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
    logger.info('AAAAAA')
    messages[0]["content"] = messages[0]["content"].format(today=today)
    logger.info('BBBBBB')
    response = await chatbot.chat(messages, tools=tools)
    logger.info('CCCCCC')
    logger.info(f"Response: {response}")
    tool_call = response.tool_calls[0]
    logger.info('DDDDDD')
    arguments = json.loads(tool_call.function.arguments)
    logger.info('EEEEEE')
    return arguments.get("locations"), arguments.get("start_date", today), arguments.get("end_date", today)


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
    print(f"Response: {response}")
    decoded = response.json()
    if len(decoded) == 0:
        return None
    latitude = decoded[0]["lat"]
    longitude = decoded[0]["lon"]
    geocode_cache[location] = (latitude, longitude)
    with open("geocode_cache.json", "w") as f:
        json.dump(geocode_cache, f)
    return latitude, longitude


async def get_forecast_met_office(lat: float, long: float) -> dict | None:
    api_key = os.getenv("MET_OFFICE_API_KEY")
    if not api_key:
        logger.info("MET_OFFICE_API_KEY not set, skipping Met Office forecast")
        return None
    url = (
        f"https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/daily"
        f"?latitude={lat}&longitude={long}"
        f"&includeLocationName=true&dataSource=BD1"
    )
    headers = {"accept": "application/json", "apikey": api_key}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Met Office API request failed: {e}")
        return None


def format_met_office_forecast(data: dict, dates: list[datetime.date]) -> str:
    features = data.get("features", [])
    if not features:
        return ""
    props = features[0].get("properties", {})
    location_name = props.get("locationName", "Unknown location")
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
            line += f" Wind: {wind_speed} m/s"
        if wind_gust is not None:
            line += f" (gusts {wind_gust} m/s)."
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

            if use_met_office:
                met_data = await get_forecast_met_office(float(lat), float(long))
                if met_data:
                    forecast += format_met_office_forecast(met_data, dates) + "\n"
                    logger.info(f"Using Met Office forecast for {location.strip()}")
                else:
                    logger.info(f"Met Office failed for {location.strip()}, falling back to OpenWeatherMap")
                    temp_forecast = await get_forecast_openweathermap(lat, long, dates)
                    forecast += json.dumps(temp_forecast) + "\n"
                    forecast_source = "OpenWeatherMap"
            else:
                temp_forecast = await get_forecast_openweathermap(lat, long, dates)
                forecast += json.dumps(temp_forecast) + "\n"
            logger.info(f"Forecast so far: {forecast}")

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

        question_text = f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. I have the following weather forecasts for you from the {forecast_source} API based on their question.  Could you make the a bit more natural - like a weather presenter would give at the end of a drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add any extra context - the user only wants to see the friendly, drive-time style forecast.  Convert wind speeds to MPH. Feel free to use weather-specific emoji.  If the user did not specify a date or range, then assume they just care about today's weather.  {personality}  FORECAST : ''{forecast}''"

        logger.info(f"Question: {question_text}")
        response = await chatbot.chat([
            {"role": "user", "content": question_text},
            {"role": "system", "content": f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not Fahrenheit for temperatures. Please take into account the likely average temperature and weather for the location and time of year (eg, don't say a forecast of 26C for June in Edinburgh is 'mild' - it's baking hot, relative to the average temperature for that time of year).  You MUST ONLY reply with the friendly forecast."}
        ])
        logger.info(f"Response: {response.message}")
        forecast = response.message + "\n" + response.usage_short
        total_tokens += response.tokens

    return forecast
