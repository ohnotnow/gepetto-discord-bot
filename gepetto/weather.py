import requests
import os
import datetime
import random
from gepetto import metoffer, gpt
import logging
import re
import json

logger = logging.getLogger('discord')

def get_relative_date(keyword):
    """Parse various date expressions from user input"""
    today = datetime.date.today()
    keyword_lower = keyword.lower()

    # Handle specific patterns
    if "today" in keyword_lower:
        return [today]
    elif "tomorrow" in keyword_lower:
        return [today + datetime.timedelta(days=1)]
    elif "next week" in keyword_lower or "this week" in keyword_lower:
        return [today + datetime.timedelta(days=i) for i in range(7)]

    # Handle "next X days" patterns
    import re
    next_days_match = re.search(r'next\s+(\w+)\s+days?', keyword_lower)
    if next_days_match:
        days_word = next_days_match.group(1)
        # Convert word numbers to integers
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }

        if days_word in word_to_num:
            num_days = word_to_num[days_word]
            logger.info(f"Parsed 'next {days_word} days' as {num_days} days")
            return [today + datetime.timedelta(days=i) for i in range(num_days)]
        elif days_word.isdigit():
            num_days = int(days_word)
            logger.info(f"Parsed 'next {days_word} days' as {num_days} days")
            return [today + datetime.timedelta(days=i) for i in range(num_days)]

    # Handle "X days" patterns (without "next")
    days_match = re.search(r'(\w+)\s+days?', keyword_lower)
    if days_match:
        days_word = days_match.group(1)
        word_to_num = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
        }

        if days_word in word_to_num:
            num_days = word_to_num[days_word]
            logger.info(f"Parsed '{days_word} days' as {num_days} days")
            return [today + datetime.timedelta(days=i) for i in range(num_days)]
        elif days_word.isdigit():
            num_days = int(days_word)
            logger.info(f"Parsed '{days_word} days' as {num_days} days")
            return [today + datetime.timedelta(days=i) for i in range(num_days)]

    # Default to today
    logger.info(f"No specific date pattern found in '{keyword}', defaulting to today")
    return [today]

def get_forecast_for_dates(forecast, target_dates):
    """
    Extracts forecast data for the specified dates from the API response.
    Returns a list of (date, period) tuples for all matching dates.
    """
    matched_periods = []

    # Check if we have the expected structure
    if 'SiteRep' not in forecast:
        logger.error("No SiteRep in forecast")
        return matched_periods

    if 'DV' not in forecast['SiteRep']:
        logger.error("No DV in SiteRep")
        return matched_periods

    if 'Location' not in forecast['SiteRep']['DV']:
        logger.error("No Location in DV - this might be a capabilities response or API issue")
        logger.error(f"DV contents: {forecast['SiteRep']['DV']}")
        return matched_periods

    if 'Period' not in forecast['SiteRep']['DV']['Location']:
        logger.error("No Period in Location")
        return matched_periods

    periods = forecast['SiteRep']['DV']['Location']['Period']

    # Handle case where periods might not be a list
    if not isinstance(periods, list):
        periods = [periods]

    logger.info(f"Found {len(periods)} periods in forecast")

    for period in periods:
        try:
            period_date = datetime.datetime.strptime(period['value'], "%Y-%m-%dZ").date()
            logger.info(f"Checking period date: {period_date} against targets: {target_dates}")
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing period date: {e}, period: {period}")
            continue

        if isinstance(target_dates, list):
            if period_date in target_dates:
                logger.info(f"Period date {period_date} matches target dates")
                matched_periods.append((period_date, period))
        elif period_date == target_dates:
            logger.info(f"Period date {period_date} matches single target date")
            matched_periods.append((period_date, period))
            break  # stop if looking for a single date

    logger.info(f"Found {len(matched_periods)} matching periods")
    return matched_periods

def try_alternative_api_call(location_id, API_KEY):
    """
    Try alternative ways to get forecast data if the main call fails
    """
    logger.info(f"Trying alternative API calls for location {location_id}")

    # Try direct API call instead of metoffer library
    try:
        # Try 3-hourly forecast first
        url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/{location_id}?res=3hourly&key={API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if 'SiteRep' in data and 'DV' in data['SiteRep'] and 'Location' in data['SiteRep']['DV']:
            logger.info("3-hourly API call successful")
            return data
        else:
            logger.warning(f"3-hourly API returned unexpected structure: {data}")

    except Exception as e:
        logger.error(f"3-hourly API call failed: {e}")

    # Try daily forecast with direct API call
    try:
        url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/{location_id}?res=daily&key={API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if 'SiteRep' in data and 'DV' in data['SiteRep'] and 'Location' in data['SiteRep']['DV']:
            logger.info("Direct daily API call successful")
            return data
        else:
            logger.warning(f"Direct daily API returned unexpected structure: {data}")

    except Exception as e:
        logger.error(f"Direct daily API call failed: {e}")

    return None

def get_forecast(location_name = None, dates = []):
    if not location_name:
        return "Wut?  I need a location name.  Asshat."
    if not dates:
        dates = [datetime.date.today()]

    # strip any non-alphanumeric characters from the location name
    location_name = re.sub(r'[^a-zA-Z0-9]', '', location_name)
    API_KEY = os.getenv('MET_OFFICE_API_KEY')

    # 1. Download the Sitelist
    logger.info(f"Getting sitelist for {location_name}")
    sitelist_url = f'http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/sitelist?key={API_KEY}'

    try:
        response = requests.get(sitelist_url)
        response.raise_for_status()
        sitelist = response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching sitelist: {e}")
        return "Sorry, I can't get the weather data right now. Please try again later."

    # 2. Find the ID for the location
    logger.info(f"Finding ID for {location_name}")
    location_id = None

    if 'Locations' not in sitelist or 'Location' not in sitelist['Locations']:
        logger.error(f"Unexpected sitelist structure: {sitelist}")
        return "Sorry, I can't find location data. Please try again later."

    for location in sitelist['Locations']['Location']:
        if location['name'].lower() == location_name.lower():
            location_id = location['id']
            break

    if location_id is None:
        return f"Wut iz {location_name}? I dunno where that is. Try again with a real place name, dummy."

    logger.info(f"Location ID: {location_id}")

    # 3. Request the forecast
    forecast = None
    try:
        M = metoffer.MetOffer(API_KEY)
        logger.info(f"Requesting forecast for {location_id}")
        forecast = M.loc_forecast(location_id, metoffer.DAILY)

        # Debug the structure
        logger.info(f"Forecast structure check:")
        logger.info(f"- SiteRep keys: {forecast.get('SiteRep', {}).keys()}")
        if 'SiteRep' in forecast and 'DV' in forecast['SiteRep']:
            logger.info(f"- DV keys: {forecast['SiteRep']['DV'].keys()}")
            if 'Location' in forecast['SiteRep']['DV']:
                logger.info(f"- Location keys: {forecast['SiteRep']['DV']['Location'].keys()}")
            else:
                logger.error(f"- Location missing from DV: {forecast['SiteRep']['DV']}")
                # Try alternative API calls
                forecast = try_alternative_api_call(location_id, API_KEY)
                if forecast is None:
                    return f"Sorry, I can't get forecast data for {location_name} right now. The weather service might be having issues with this location."

    except Exception as e:
        logger.error(f"Error getting forecast: {e}")
        # Try alternative API calls
        forecast = try_alternative_api_call(location_id, API_KEY)
        if forecast is None:
            return "Sorry, I can't get the weather forecast right now. Please try again later."

    logger.info(f"Getting forecast for dates: {dates}")

    try:
        plain_forecasts = get_forecast_for_dates(forecast, dates)

        if not plain_forecasts:
            logger.warning("No forecast data found for the requested dates")
            return f"Sorry, I couldn't find forecast data for {location_name} on the requested dates."

        forecasts = []

        for date, period in plain_forecasts:
            if 'Rep' not in period:
                logger.error(f"No Rep data in period: {period}")
                continue

            reps = period['Rep']
            if not isinstance(reps, list):
                reps = [reps]

            # For daily forecasts, we want the day forecast (not night)
            day_forecast = None
            for rep in reps:
                if rep.get('$') == 'Day':
                    day_forecast = rep
                    break

            # If no specific day forecast, use the first available
            if day_forecast is None and reps:
                day_forecast = reps[0]
                logger.warning(f"No specific day forecast found, using first available: {day_forecast}")

            if day_forecast:
                try:
                    weather_code = metoffer.WEATHER_CODES.get(int(day_forecast['W']), "Unknown")
                    human_readable_date = date.strftime("%A %d %B %Y")
                    forecast_str = (
                        f"Forecast for {location_name.capitalize()} on {human_readable_date}: "
                        f"{weather_code}, chance of rain {day_forecast.get('PPd', 'N/A')}%, temperature {day_forecast.get('Dm', 'N/A')}C "
                        f"(feels like {day_forecast.get('FDm', 'N/A')}C). Humidity {day_forecast.get('Hn', 'N/A')}%, wind {day_forecast.get('S', 'N/A')} mph "
                        f"- gusting up to {day_forecast.get('Gn', 'N/A')} mph."
                    )
                    forecasts.append(forecast_str)
                except (KeyError, ValueError) as e:
                    logger.error(f"Error processing forecast rep: {e}, rep: {day_forecast}")
                    continue

        if not forecasts:
            return f"Sorry, I couldn't process the forecast data for {location_name}."

        logger.info(f"Forecasts: {forecasts}")
        readable_forecast = "\n".join(forecasts)
        return readable_forecast

    except Exception as e:
        logger.error(f"Error processing forecast data: {e}")
        return "Sorry, I encountered an error processing the weather data."

async def get_weather_location_from_prompt(prompt, chatbot):
    messages = [
        {"role": "system", "content": "You are a helpful assistant who is an expert at picking out UK town and city names from user prompts"},
        {"role": "user", "content": prompt}
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_location_for_forecast",
                "description": "figure out what town or city the user wants the weather for",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "locations": {
                            "type": "array",
                            "description": "A list of one or more UK city or town, eg ['London','Edinburgh','Manchester']",
                            "items": {
                                "type": "string",
                                "description": "A UK city or town, eg London,Edinburgh,Manchester",
                            },
                        },
                    },
                    "required": ["locations"],
                },
            }
        }
    ]
    # Note: we always use the openai model for this as it's the only one that always has function calling enabled
    chatbot = gpt.GPTModel()
    response = await chatbot.function_call(messages, tools)
    return response.parameters.get("locations"), response.tokens

async def get_friendly_forecast(question, chatbot, locations: list[str]):
    forecast = ""
    dates = get_relative_date(question)
    total_tokens = 0  # Initialize total_tokens

    logger.info(f"Parsed dates from question '{question}': {dates}")

    if locations is None:
        response = await chatbot.chat([{"role": "user", "content": question}])
        forecast = response.message
        total_tokens += response.tokens
    else:
        for location in locations:
            logger.info(f"Getting forecast for {location.strip()}")
            temp_forecast = get_forecast(location.strip(), dates)
            logger.info(f"Temp forecast: {temp_forecast}")
            forecast += temp_forecast + "\n"

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

        question_text = f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. I have the following plain weather forecasts for you based on their question.  Could you make the a bit more natural - like a weather presenter would give at the end of a drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add any extra context - the user only wants to see the friendly, drive-time style forecast.  If the wind speed is given in knots, convert it to MPH. Feel free to use weather-specific emoji.  {personality}  FORECAST : ''{forecast}''"

        logger.info(f"Question: {question_text}")
        response = await chatbot.chat([
            {"role": "user", "content": question_text},
            {"role": "system", "content": f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not Fahrenheit for temperatures. You MUST ONLY reply with the friendly forecast."}
        ])
        logger.info(f"Response: {response.message}")
        forecast = response.message + "\n" + response.usage_short
        total_tokens += response.tokens

    return forecast
