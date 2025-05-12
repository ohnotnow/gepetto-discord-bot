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
    today = datetime.date.today()
    if "today" in keyword.lower():
        return [today]
    elif "tomorrow" in keyword.lower():
        return [today + datetime.timedelta(days=1)]
    elif "week" in keyword.lower():
        return [today + datetime.timedelta(days=i) for i in range(7)]  # next 7 days
    else:
        return [today]  # default to today if unsure

def get_forecast_for_dates(forecast, target_dates):
    """
    Extracts forecast data for the specified dates from the API response.
    Returns a list of (date, period) tuples for all matching dates.
    Current Met Office API returns the following structure:
    {'SiteRep':
        {'Wx':
            {'Param': [
                {'name': 'FDm', 'units': 'C', '$': 'Feels Like Day Maximum Temperature'},
                {'name': 'FNm', 'units': 'C', '$': 'Feels Like Night Minimum Temperature'},
                {'name': 'Dm', 'units': 'C', '$': 'Day Maximum Temperature'},
                {'name': 'Nm', 'units': 'C', '$': 'Night Minimum Temperature'},
                {'name': 'Gn', 'units': 'mph', '$': 'Wind Gust Noon'},
                {'name': 'Gm', 'units': 'mph', '$': 'Wind Gust Midnight'},
                {'name': 'Hn', 'units': '%', '$': 'Screen Relative Humidity Noon'},
                {'name': 'Hm', 'units': '%', '$': 'Screen Relative Humidity Midnight'},
                {'name': 'V', 'units': '', '$': 'Visibility'},
                {'name': 'D', 'units': 'compass', '$': 'Wind Direction'},
                {'name': 'S', 'units': 'mph', '$': 'Wind Speed'},
                {'name': 'U', 'units': '', '$': 'Max UV Index'},
                {'name': 'W', 'units': '', '$': 'Weather Type'},
                {'name': 'PPd', 'units': '%', '$': 'Precipitation Probability Day'},
                {'name': 'PPn', 'units': '%', '$': 'Precipitation Probability Night'}
            ]},
            'DV': {'dataDate': '2025-05-12T04:00:00Z', 'type': 'Forecast'}
        }
    }
    """
    matched_periods = []
    logger.info("Looping over forecast periods")
    for period in forecast['SiteRep']['Wx']['Param']:
        period_date = datetime.datetime.strptime(period['DV']['dataDate'], "%Y-%m-%dT%H:%M:%SZ").date()
        logger.info(f"Checking period date: {period_date}")
        if isinstance(target_dates, list):
            logger.info(f"Target dates: {target_dates}")
            if period_date in target_dates:
                matched_periods.append((period_date, period))
        elif period_date == target_dates:
            logger.info(f"Period date matches target date: {period_date}")
            matched_periods.append((period_date, period))
            break  # Break if only looking for one date and it's found
    logger.info(f"Matched periods: {matched_periods}")
    return matched_periods

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
    response = requests.get(sitelist_url)
    sitelist = response.json()

    # 2. Find the ID for the location
    logger.info(f"Finding ID for {location_name}")
    location_id = None
    for location in sitelist['Locations']['Location']:
        if location['name'].lower() == location_name.lower():
            location_id = location['id']
            break

    if location_id is None:
        return f"Wut iz {location_name}? I dunno where that is.  Try again with a real place name, dummy."
    logger.info(f"Location ID: {location_id}")
    # 3. Request the forecast
    M = metoffer.MetOffer(API_KEY)
    logger.info(f"Requesting forecast for {location_id}")
    forecast = M.loc_forecast(location_id, metoffer.DAILY)
    logger.info(f"Forecast: {forecast}")
    logger.info(f"Getting forecast for dates: {dates}")
    # plain_forcasts = get_forecast_for_dates(forecast, dates)
    # logger.info(f"Plain forecasts: {plain_forcasts}")
    forecasts = []
    forecasts = json.dumps(forecast, indent=4)
    # for date, period in plain_forcasts:
    #     details = period['Rep'][0]  # Assuming you want the first representation of the day
    #     weather_code = metoffer.WEATHER_CODES[int(details['W'])]
    #     human_readable_date = date.strftime("%A %d %B %Y")
    #     forecast_str = f"Forecast for {location_name.capitalize()} on {human_readable_date}: {metoffer.WEATHER_CODES[int(details['W'])]}, chance of rain {details['PPd']}%, temperature {details['Dm']}C (feels like {details['FDm']}C). Humidity {details['Hn']}%, wind {details['S']} knots - gusting upto {details['Gn']}.\n"
    #     forecasts.append(forecast_str)
    logger.info(f"Forecasts: {forecasts}")
    # readable_forecast = "\n".join(forecasts)
    return forecasts
    # return readable_forecast

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
                        "location": {
                            "type": "string",
                            "description": "A csv list of one or more UK city or town, eg London,Edinburgh,Manchester",
                        },
                    },
                    "required": ["location"],
                },
            }
        }
    ]
    # Note: we always use the openai model for this as it's the only one that always has function calling enabled
    chatbot = gpt.GPTModel()
    response = await chatbot.function_call(messages, tools)
    return response.parameters.get("location").split(","), response.tokens

async def get_friendly_forecast(question, chatbot, locations):
    forecast = ""
    dates = get_relative_date(question)
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
        question = f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. I have the following plain weather forecasts for you based on their question.  Could you make the a bit more natural - like a weather presenter would give at the end of a drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add any extra context - the user only wants to see the friendly, drive-time style forecast.  If the wind speed is given in knots, convert it to MPH. Feel free to use weather-specific emoji.  {personality}  FORECAST : ''{forecast}''"
        logger.info(f"Question: {question}")
        response  = await chatbot.chat([{"role": "user", "content": question}, {"role": "system", "content": f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not Fahrenheit for temperatures. You MUST ONLY reply with the friendly forecast."}])
        logger.info(f"Response: {response.message}")
        forecast = response.message + "\n" + response.short_usage
    return forecast
