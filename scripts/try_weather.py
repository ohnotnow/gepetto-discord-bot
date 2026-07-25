#!/usr/bin/env python3
"""Dev tool for checking what the Met Office actually tells us, and what
survives the trip into the LLM prompt.

Walks the same stages as the bot's `get_weather_forecast` tool, printing
each one, so you can tell a bad-data problem from a bad-translation
problem:

    1. location + dates   (from args, or from the LLM with --question)
    2. lat/long           (Nominatim, via find_lat_long_from_location)
    3. raw daily payload  (via get_forecast_met_office — the real code path)
    4. per-day fields     (every key the API returned, with the ones
                           format_met_office_forecast() actually reads
                           marked "USED" — the rest never reach the LLM)
    5. prompt text        (exactly the string the LLM is handed, via
                           build_met_office_forecast: hourly buckets for
                           today and tomorrow, daily summaries beyond)
    6. hourly rows        (--hourly; the raw per-hour data behind those
                           buckets, in UTC and UK local time)
    7. friendly forecast  (--llm; the production final chat call)

Steps 1-6 are free unless you pass --question. Only --llm and --question
spend tokens.

Examples:
    uv run python scripts/try_weather.py Glasgow
    uv run python scripts/try_weather.py Glasgow --hourly
    uv run python scripts/try_weather.py Glasgow --days 3 --hourly
    uv run python scripts/try_weather.py Glasgow --hourly --llm
    uv run python scripts/try_weather.py --question "weather in Glasgow and Norwich tomorrow?"

Env loading:
    Reads `.env` from the project root if present (KEY=value lines, #
    comments and blanks ignored). Existing shell env wins. Needs
    MET_OFFICE_API_KEY.

Outputs:
    Raw JSON is written to ./samples/output/weather_<timestamp>/ as
    daily_<location>.json and hourly_<location>.json, plus
    llm_input_<location>.txt (the step 5 string). `samples/` is
    gitignored.
"""

import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.content.weather import (  # noqa: E402  (sys.path tweak above)
    MET_OFFICE_WEATHER_CODES,
    _met_office_location_name,
    build_met_office_forecast,
    find_lat_long_from_location,
    get_details_from_prompt,
    get_forecast_met_office,
)

UK = ZoneInfo("Europe/London")

# The only fields format_met_office_forecast() reads. Anything else the
# API sends is dropped before the LLM ever sees it.
DAILY_FIELDS_USED = {
    "daySignificantWeatherCode",
    "nightSignificantWeatherCode",
    "dayMaxScreenTemperature",
    "nightMinScreenTemperature",
    "dayMaxFeelsLikeTemp",
    "nightMinFeelsLikeTemp",
    "midday10MWindSpeed",
    "midday10MWindGust",
    "dayProbabilityOfRain",
    "nightProbabilityOfRain",
    "middayRelativeHumidity",
    "maxUvIndex",
}

# Preferred column order for the hourly table. Driven off the keys that
# are actually present, so a renamed field shows up in "other keys"
# rather than silently vanishing.
HOURLY_COLUMNS = [
    ("significantWeatherCode", "weather", 22),
    ("screenTemperature", "temp", 6),
    ("feelsLikeTemperature", "feels", 6),
    ("probOfPrecipitation", "rain%", 6),
    ("precipitationRate", "mm/h", 6),
    ("windSpeed10m", "wind", 12),
    ("windGustSpeed10m", "gust", 12),
    ("screenRelativeHumidity", "hum%", 6),
    ("uvIndex", "uv", 3),
]

MPS_TO_MPH = 2.23694


def _load_dotenv_if_present() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _setup_logging(verbose: bool) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    ))
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    discord_logger.addHandler(handler)
    discord_logger.propagate = False
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _get_chatbot():
    """Mirror main.get_chatbot() without dragging in the rest of main.py."""
    from src.providers import claude, gpt, groq, openrouter

    provider = os.getenv("BOT_PROVIDER", "openai")
    if provider == "groq":
        return groq.GroqModel()
    if provider == "anthropic":
        return claude.ClaudeModel()
    if provider == "openrouter":
        return openrouter.OpenrouterModel()
    return gpt.GPTModel()


def _heading(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def _fetch_hourly(lat: float, long: float) -> dict | None:
    """Probe the hourly endpoint.

    Deliberately *not* in src/content/weather.py: the bot only calls the
    daily endpoint, and this script shouldn't pre-empt the fix. Same
    base URL / auth / dataSource as get_forecast_met_office().
    """
    api_key = os.getenv("MET_OFFICE_API_KEY")
    if not api_key:
        print("MET_OFFICE_API_KEY not set — cannot fetch hourly", file=sys.stderr)
        return None
    url = (
        f"https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly"
        f"?latitude={lat}&longitude={long}"
        f"&includeLocationName=true&dataSource=BD1"
    )
    try:
        response = requests.get(url, headers={"accept": "application/json", "apikey": api_key})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Hourly request failed: {e}", file=sys.stderr)
        return None


def _properties(data: dict) -> dict:
    features = data.get("features", [])
    if not features:
        return {}
    return features[0].get("properties", {})


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _wind(value, unit_hint: str) -> str:
    """Show a wind value alongside its mph conversion.

    The prompt asks the LLM to do this conversion itself, so seeing the
    arithmetic here tells you whether it got it right.
    """
    if value is None:
        return "-"
    if "metre" in unit_hint.lower() or "m/s" in unit_hint.lower() or not unit_hint:
        return f"{_fmt(value)} ({value * MPS_TO_MPH:.0f}mph)"
    return f"{_fmt(value)} {unit_hint}"


def _unit_map(data: dict) -> dict[str, str]:
    """field -> unit label, from the payload's own metadata.

    `parameters` sits at the top level of the response, NOT inside
    features[0].properties. weather.py assumes wind is m/s; this is where
    you confirm that from the payload rather than trusting it.
    """
    parameters = data.get("parameters") or []
    if isinstance(parameters, list):
        parameters = {k: v for entry in parameters for k, v in entry.items()}
    units = {}
    for name, meta in parameters.items():
        if not isinstance(meta, dict):
            continue
        unit = meta.get("unit") or {}
        symbol = unit.get("symbol") or {}
        units[name] = symbol.get("type") or unit.get("label") or ""
    return units


def _print_units(units: dict[str, str]) -> None:
    if not units:
        print("(no 'parameters' unit metadata in payload)")
        return
    for name in sorted(units):
        print(f"  {name:<34} {units[name]}")


def _print_daily_entries(props: dict, units: dict[str, str], date_strs: set[str]) -> None:
    """Dump every field the API gave us for the requested days.

    USED / dropped tells you whether a mismatch is the API's fault or
    ours — a 'dropped' field that contradicts the bot's forecast means
    the data was there and we threw it away.
    """
    matched = 0
    for entry in props.get("timeSeries", []):
        entry_date = entry.get("time", "")[:10]
        if entry_date not in date_strs:
            continue
        matched += 1
        print(f"\n--- {entry_date}  (raw time: {entry.get('time')}) ---")
        for key in sorted(entry):
            if key == "time":
                continue
            marker = "USED   " if key in DAILY_FIELDS_USED else "dropped"
            value = entry[key]
            if "Wind" in key and "Direction" not in key:
                shown = _wind(value, units.get(key, ""))
            elif "WindDirection" in key:
                shown = f"{_fmt(value)}° (from)"
            elif key.endswith("SignificantWeatherCode"):
                shown = f"{_fmt(value)} = {MET_OFFICE_WEATHER_CODES.get(value, '?')}"
            else:
                shown = _fmt(value)
            print(f"  [{marker}] {key:<34} {shown}")
    if matched == 0:
        available = sorted({e.get("time", "")[:10] for e in props.get("timeSeries", [])})
        print(f"\nNo timeSeries entries matched {sorted(date_strs)}.")
        print(f"Dates the payload actually covers: {available}")


def _print_hourly_entries(props: dict, units: dict[str, str], date_strs: set[str]) -> None:
    """Hourly table in both UTC and UK local time.

    The API talks UTC; the bot's date filtering slices the UTC string.
    In BST those disagree, so both are shown.
    """
    series = props.get("timeSeries", [])
    if not series:
        print("(no hourly timeSeries in payload)")
        return

    present = [c for c in HOURLY_COLUMNS if c[0] in series[0]]
    known = {c[0] for c in HOURLY_COLUMNS} | {"time"}
    others = sorted(k for k in series[0] if k not in known)
    if others:
        print(f"Not shown in table (present in payload): {', '.join(others)}")
    missing = sorted(c[0] for c in HOURLY_COLUMNS if c[0] not in series[0])
    if missing:
        print(f"Expected but absent (field renamed?): {', '.join(missing)}")
    print()

    header = f"{'UTC':<17}{'UK local':<17}" + "".join(f"{label:<{width + 2}}" for _, label, width in present)
    print(header)
    print("-" * len(header))

    for entry in series:
        raw_time = entry.get("time", "")
        try:
            when = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            continue
        local = when.astimezone(UK)
        # Filter on local date — that's the day the user means.
        if local.date().isoformat() not in date_strs:
            continue
        row = f"{when.strftime('%Y-%m-%d %H:%MZ'):<17}{local.strftime('%Y-%m-%d %H:%M'):<17}"
        for field, _, width in present:
            value = entry.get(field)
            if field == "significantWeatherCode":
                shown = MET_OFFICE_WEATHER_CODES.get(value, _fmt(value))
            elif "wind" in field.lower() and "direction" not in field.lower():
                shown = _wind(value, units.get(field, ""))
            else:
                shown = _fmt(value)
            row += f"{shown:<{width + 2}}"
        print(row)


def _build_dates(start: datetime.date, days: int) -> list[datetime.date]:
    return [start + datetime.timedelta(days=offset) for offset in range(days)]


async def _friendly_forecast(question: str, forecast_text: str, chatbot) -> str:
    """The production final chat call from get_friendly_forecast_openweathermap().

    Kept verbatim apart from the random personality, which is dropped so
    runs are comparable.
    """
    date_and_time = datetime.datetime.now().strftime("%A %d %B %Y at %H:%M")
    question_text = (
        f"It is currently {date_and_time}. The user asked me ''{question.strip()}''. "
        f"I have the following weather forecasts for you from the Met Office API based on their question.  "
        f"Could you make the a bit more natural - like a weather presenter would give at the end of a "
        f"drive-time news segment on the radio or TV?  ONLY reply with the rewritten forecast.  NEVER add "
        f"any extra context - the user only wants to see the friendly, drive-time style forecast.  Convert "
        f"wind speeds to MPH. Feel free to use weather-specific emoji.  If the user did not specify a date "
        f"or range, then assume they just care about today's weather.    FORECAST : ''{forecast_text}''"
    )
    response = await chatbot.chat([
        {"role": "user", "content": question_text},
        {"role": "system", "content": (
            f"You are a helpful assistant called '{chatbot.name}' who specialises in providing chatty and "
            f"friendly weather forecasts for UK towns and cities.  ALWAYS use degrees Celcius and not "
            f"Fahrenheit for temperatures. Please take into account the likely average temperature and "
            f"weather for the location and time of year (eg, don't say a forecast of 26C for June in "
            f"Edinburgh is 'mild' - it's baking hot, relative to the average temperature for that time of "
            f"year).  You MUST ONLY reply with the friendly forecast."
        )},
    ])
    return response.message


async def _run(args: argparse.Namespace) -> int:
    chatbot = None
    question = args.question

    if args.question:
        chatbot = _get_chatbot()
        _heading("STAGE 1 — location + dates, extracted by the LLM")
        locations, start_date, end_date = await get_details_from_prompt(args.question, chatbot)
        print(f"locations:  {locations}")
        print(f"start_date: {start_date}")
        print(f"end_date:   {end_date}")
        if not locations:
            print("No locations extracted — nothing to fetch.", file=sys.stderr)
            return 1
        start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)
        dates = _build_dates(start, (end - start).days + 1)
    else:
        locations = args.locations
        start = datetime.date.fromisoformat(args.start) if args.start else datetime.date.today()
        dates = _build_dates(start, args.days)
        _heading("STAGE 1 — location + dates, from the command line")
        print(f"locations: {locations}")
        print(f"dates:     {[d.isoformat() for d in dates]}")
        question = f"What's the weather in {', '.join(locations)}?"

    print(f"\ntoday (local): {datetime.date.today().isoformat()}   "
          f"now: {datetime.datetime.now(UK).strftime('%Y-%m-%d %H:%M %Z')}   "
          f"UTC: {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%MZ')}")

    date_strs = {d.isoformat() for d in dates}
    out_dir = PROJECT_ROOT / "samples" / "output" / f"weather_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)

    for location in locations:
        location = location.strip()
        slug = location.lower().replace(" ", "_")

        _heading(f"STAGE 2 — geocoding '{location}' (Nominatim)")
        coords = await find_lat_long_from_location(location)
        if not coords or coords[0] is None:
            print(f"Failed to geocode '{location}'", file=sys.stderr)
            continue
        lat, long = float(coords[0]), float(coords[1])
        print(f"lat/long: {lat}, {long}")
        print(f"check it:  https://www.openstreetmap.org/?mlat={lat}&mlon={long}#map=13/{lat}/{long}")

        _heading(f"STAGE 3 — raw daily payload for {location}")
        daily = await get_forecast_met_office(lat, long)
        if not daily:
            print("No daily payload returned (missing MET_OFFICE_API_KEY, or the request failed "
                  "— rerun with -v for the logged reason).", file=sys.stderr)
            continue
        daily_path = out_dir / f"daily_{slug}.json"
        daily_path.write_text(json.dumps(daily, indent=2))
        props = _properties(daily)
        units = _unit_map(daily)
        print(f"location:     {_met_office_location_name(props)!r}  (properties.location.name)")
        print(f"modelRunDate: {props.get('modelRunDate')}")
        print(f"requested:    {lat}, {long}")
        geometry = daily.get("features", [{}])[0].get("geometry", {}).get("coordinates")
        if geometry:
            print(f"grid point:   {geometry[1]}, {geometry[0]}  (lat, long — the API snaps to its grid)")
        print(f"point distance: {props.get('requestPointDistance')}m from the requested lat/long")
        print(f"days in payload: {len(props.get('timeSeries', []))}")
        print(f"raw JSON: {daily_path}")
        print("\nUnits, per the payload's own metadata:")
        _print_units(units)

        _heading(f"STAGE 4 — daily fields for {location}: USED by the bot vs dropped")
        _print_daily_entries(props, units, date_strs)

        _heading(f"STAGE 5 — the exact text the LLM receives")
        print("(via build_met_office_forecast — hourly buckets for today/tomorrow, daily beyond)\n")
        forecast_text = await build_met_office_forecast(lat, long, dates, location)
        llm_input_path = out_dir / f"llm_input_{slug}.txt"
        llm_input_path.write_text(forecast_text)
        print(forecast_text if forecast_text.strip() else "(empty!)")
        print(f"\nsaved to: {llm_input_path}")

        if args.hourly:
            _heading(f"STAGE 6 — the raw hourly rows behind those buckets, for {location}")
            hourly = _fetch_hourly(lat, long)
            if hourly:
                hourly_path = out_dir / f"hourly_{slug}.json"
                hourly_path.write_text(json.dumps(hourly, indent=2))
                print(f"raw JSON: {hourly_path}\n")
                _print_hourly_entries(_properties(hourly), _unit_map(hourly), date_strs)

        if args.llm:
            _heading(f"STAGE 7 — friendly forecast for {location} (LLM)")
            chatbot = chatbot or _get_chatbot()
            print(await _friendly_forecast(question, forecast_text, chatbot))

    print(f"\nAll output: {out_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the Met Office forecast the bot fetches, stage by stage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Stages 1-6 are free. --llm and --question cost tokens.",
    )
    parser.add_argument("locations", nargs="*", help="UK place-name(s), e.g. Glasgow Norwich")
    parser.add_argument("--question", help="Run the LLM prompt-parsing stage on a full user question instead")
    parser.add_argument("--days", type=int, default=1, help="How many days from the start date (default: 1)")
    parser.add_argument("--start", help="Start date as YYYY-MM-DD (default: today)")
    parser.add_argument("--hourly", action="store_true", help="Also show the raw per-hour rows behind the buckets")
    parser.add_argument("--llm", action="store_true", help="Also run the final friendly-forecast chat call")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show the bot's own debug logging")
    args = parser.parse_args()

    if not args.locations and not args.question:
        parser.error("give at least one location, or use --question")

    _load_dotenv_if_present()
    _setup_logging(args.verbose)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
