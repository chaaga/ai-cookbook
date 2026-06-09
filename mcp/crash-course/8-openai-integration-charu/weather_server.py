import os
import sys
import requests
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv("../.env")

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")

# Create an MCP server
mcp = FastMCP(
    name="WeatherAssistant",
    host="0.0.0.0",  # only used for SSE transport (localhost)
    port=8051,  # only used for SSE transport (set this to any port)
)

@mcp.prompt()
def compare_weather_prompt(location_a: str, location_b: str) -> str:
    """
    Generates a clear, comparative summary of the weather between two specified locations.
    This is the best choice when a user asks to compare, contrast, or see the difference in weather between two places.
    
    Args:
        location_a: The first city for comparison (e.g., "London").
        location_b: The second city for comparison (e.g., "Paris").
    """
    return f"""
    You are a weather analyst. You MUST call the get_weather tool separately for EACH location before answering.

    The user wants to compare the weather between "{location_a}" and "{location_b}".

    Follow these steps exactly:
    1.  In a SINGLE step, call get_weather for BOTH locations simultaneously — call get_weather("{location_a}") AND get_weather("{location_b}") at the same time as parallel tool calls.
    2.  Wait for BOTH tool results to come back before doing anything else.
    3.  Only after you have real tool results for BOTH locations, synthesize them into a comparison.
    4.  Never use memory or training knowledge for weather data — always use the tool results.
    5.  Present the comparison as a markdown table highlighting temperature, conditions, and wind speed.
    """

@mcp.tool()
def get_weather(location: str) -> dict:
    """
    Fetches the current weather for a specified location using the OpenWeatherMap API.

    Args:
        location: The city name and optional country code (e.g., "London,uk").

    Returns:
        A dictionary containing weather information or an error message.
    """
    print(f"\n[weather_server] Tool called: get_weather(location='{location}')", file=sys.stderr, flush=True)
    if not OPENWEATHERMAP_API_KEY:
        return {"error": "OpenWeatherMap API key is not configured on the server."}

    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": location,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": "metric"  # Use "imperial" for Fahrenheit
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        data = response.json()

        # Extracting relevant weather information
        weather_description = data["weather"][0]["description"]
        temperature = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]

        result = {
            "location": data["name"],
            "weather": weather_description,
            "temperature_celsius": f"{temperature}°C",
            "feels_like_celsius": f"{feels_like}°C",
            "humidity": f"{humidity}%",
            "wind_speed_mps": f"{wind_speed} m/s"
        }
        print(f"[weather_server] Returning result: {result}", file=sys.stderr, flush=True)
        return result

    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            return {"error": f"Could not find weather data for '{location}'. Please check the location name."}
        elif response.status_code == 401:
            return {"error": "Authentication failed. The API key is likely invalid or inactive."}
        else:
            return {"error": f"An HTTP error occurred: {http_err}"}
    except requests.exceptions.RequestException as req_err:
        return {"error": f"A network error occurred: {req_err}"}
    except KeyError:
        return {"error": "Received unexpected data format from the weather API."}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}


# Run the server
if __name__ == "__main__":
    transport = "streamable-http"
    if transport == "stdio":
        print("Running server with stdio transport")
        mcp.run(transport="stdio")
    elif transport == "sse":
        print("Running server with SSE transport")
        mcp.run(transport="sse")
    elif transport == "streamable-http":
        print("Running server with Streamable HTTP transport")
        mcp.run(transport="streamable-http")
    else:
        raise ValueError(f"Unknown transport: {transport}")