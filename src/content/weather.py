import requests
import os
import datetime
import random
import logging
import json

logger = logging.getLogger('discord')


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
        for location in locations:
            logger.info(f"Getting forecast for {location.strip()}")
            lat, long = await find_lat_long_from_location(location.strip())
            if lat is None or long is None:
                logger.error(f"Failed to find lat/long for {location.strip()}")
                continue
            temp_forecast = await get_forecast_openweathermap(lat, long, dates)
            logger.info(f"Temp forecast: {temp_forecast}")
            forecast += json.dumps(temp_forecast) + "\n"

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

        question_text = f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. I have the following JSON weather forecasts for you from the OpenWeatherMap API based on their question.  Could you make the a bit more natural - like a weather presenter would give at the end of a drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add any extra context - the user only wants to see the friendly, drive-time style forecast.  If the wind speed is given in knots, convert it to MPH. Feel free to use weather-specific emoji.  If the user did not specify a date or range, then assume they just care about today's weather.  {personality}  FORECAST : ''{forecast}''"

        logger.info(f"Question: {question_text}")
        response = await chatbot.chat([
            {"role": "user", "content": question_text},
            {"role": "system", "content": f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not Fahrenheit for temperatures. Please take into account the likely average temperature and weather for the location and time of year (eg, don't say a forecast of 26C for June in Edinburgh is 'mild' - it's baking hot, relative to the average temperature for that time of year).  You MUST ONLY reply with the friendly forecast."}
        ])
        logger.info(f"Response: {response.message}")
        forecast = response.message + "\n" + response.usage_short
        total_tokens += response.tokens

    return forecast
