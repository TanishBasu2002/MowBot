import os
import aiohttp
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# OpenWeatherMap API key - you'll need to sign up for a free API key at https://openweathermap.org/
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

# Cache weather data to avoid excessive API calls
weather_cache = {}
CACHE_EXPIRY = 3600  # Cache weather data for 1 hour

async def get_weather_forecast(location, days=1):
    """
    Get weather forecast for a location
    
    Args:
        location (str): Location name or coordinates (e.g., "Bristol,UK" or "51.4545,-2.5879")
        days (int): Number of days to forecast (1-5)
    
    Returns:
        dict: Weather forecast data or None if error
    """
    if not WEATHER_API_KEY:
        logger.warning("Weather API key not set. Weather forecast unavailable.")
        return None
    
    # Check cache first
    cache_key = f"{location}_{days}"
    current_time = datetime.now()
    if cache_key in weather_cache:
        cached_data, timestamp = weather_cache[cache_key]
        if current_time - timestamp < timedelta(seconds=CACHE_EXPIRY):
            return cached_data
    
    # Format API URL
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={location}&appid={WEATHER_API_KEY}&units=metric&cnt={days*8}"
    
    # For coordinates instead of city name
    if "," in location and all(c.replace('.', '').replace('-', '').isdigit() for c in location.split(",")):
        lat, lon = location.split(",")
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&cnt={days*8}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Process the data to make it more usable
                    processed_data = process_weather_data(data)
                    
                    # Cache the result
                    weather_cache[cache_key] = (processed_data, current_time)
                    
                    return processed_data
                else:
                    logger.error(f"Weather API error: {response.status} - {await response.text()}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return None

def process_weather_data(data):
    """Process raw weather API data into a more usable format"""
    if not data or 'list' not in data:
        return None
    
    forecast_list = data['list']
    days_forecast = {}
    
    for forecast in forecast_list:
        # Convert timestamp to datetime
        dt = datetime.fromtimestamp(forecast['dt'])
        date_str = dt.strftime('%Y-%m-%d')
        time_str = dt.strftime('%H:%M')
        
        # Initialize day data if not exists
        if date_str not in days_forecast:
            days_forecast[date_str] = {
                'date': date_str,
                'forecasts': [],
                'min_temp': float('inf'),
                'max_temp': float('-inf'),
                'rain_chance': 0,
                'main_weather': '',
                'weather_icon': '',
                'wind_speed': 0
            }
        
        # Extract relevant data
        temp = forecast['main']['temp']
        weather = forecast['weather'][0]['main']
        weather_desc = forecast['weather'][0]['description']
        weather_icon = forecast['weather'][0]['icon']
        wind_speed = forecast['wind']['speed']
        rain_chance = forecast.get('pop', 0) * 100  # Probability of precipitation (0-1)
        
        # Update day summary
        days_forecast[date_str]['min_temp'] = min(days_forecast[date_str]['min_temp'], temp)
        days_forecast[date_str]['max_temp'] = max(days_forecast[date_str]['max_temp'], temp)
        days_forecast[date_str]['rain_chance'] = max(days_forecast[date_str]['rain_chance'], rain_chance)
        
        # Add forecast to list
        days_forecast[date_str]['forecasts'].append({
            'time': time_str,
            'temp': temp,
            'weather': weather,
            'description': weather_desc,
            'icon': weather_icon,
            'wind_speed': wind_speed,
            'rain_chance': rain_chance
        })
    
    # Determine main weather for each day (most frequent)
    for date_str, day_data in days_forecast.items():
        weather_count = {}
        icon_count = {}
        wind_total = 0
        
        for forecast in day_data['forecasts']:
            weather = forecast['weather']
            icon = forecast['icon']
            wind_total += forecast['wind_speed']
            
            weather_count[weather] = weather_count.get(weather, 0) + 1
            icon_count[icon] = icon_count.get(icon, 0) + 1
        
        # Get most common weather and icon
        day_data['main_weather'] = max(weather_count.items(), key=lambda x: x[1])[0]
        day_data['weather_icon'] = max(icon_count.items(), key=lambda x: x[1])[0]
        day_data['wind_speed'] = wind_total / len(day_data['forecasts'])
    
    # Convert to list and sort by date
    result = list(days_forecast.values())
    result.sort(key=lambda x: x['date'])
    
    return result

def get_weather_emoji(weather_main):
    """Convert weather condition to emoji"""
    weather_emojis = {
        'Clear': '☀️',
        'Clouds': '☁️',
        'Rain': '🌧️',
        'Drizzle': '🌦️',
        'Thunderstorm': '⛈️',
        'Snow': '❄️',
        'Mist': '🌫️',
        'Fog': '🌫️',
        'Haze': '🌫️',
        'Smoke': '🌫️',
        'Dust': '🌫️',
        'Sand': '🌫️',
        'Ash': '🌫️',
        'Squall': '💨',
        'Tornado': '🌪️'
    }
    return weather_emojis.get(weather_main, '🌡️')

def format_weather_message(weather_data, job_name):
    """Format weather data into a readable message"""
    if not weather_data or not weather_data[0]:
        return "Weather forecast unavailable."
    
    today = weather_data[0]
    
    # Format the message
    weather_emoji = get_weather_emoji(today['main_weather'])
    
    message = [
        f"🌤️ Weather Forecast for {job_name}:",
        f"{weather_emoji} {today['main_weather']} ({today['min_temp']:.1f}°C to {today['max_temp']:.1f}°C)",
        f"💧 Chance of Rain: {today['rain_chance']:.0f}%",
        f"💨 Wind Speed: {today['wind_speed']:.1f} m/s"
    ]
    
    # Add work recommendation based on weather
    if today['rain_chance'] > 70 or today['main_weather'] in ['Thunderstorm', 'Snow', 'Tornado']:
        message.append("⚠️ Weather Warning: Consider rescheduling outdoor work.")
    elif today['rain_chance'] > 40 or today['main_weather'] in ['Rain', 'Drizzle']:
        message.append("⚠️ Weather Alert: Prepare for possible rain.")
    elif today['wind_speed'] > 10:
        message.append("⚠️ Weather Alert: High winds expected.")
    else:
        message.append("✅ Weather looks suitable for outdoor work.")
    
    return "\n".join(message)
