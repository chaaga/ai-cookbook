import json
import os

import requests
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

"""
docs: https://platform.openai.com/docs/guides/function-calling

Sample questions to try:
  - If I purchase an item today, June 1st, what is the last day I can return it?
  - Tell me the current temperature in Fahrenheit in Boston and your return policy
  - What is 2 + 2?   (does not trigger any tool)
"""

# --------------------------------------------------------------
# Configuration
# --------------------------------------------------------------

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-4o"
SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions from the knowledge base "
    "about our e-commerce store and from the weather tool for weather information."
)


# --------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------


def get_weather(latitude, longitude):
    """This is a publically available API that returns the weather for a given location."""
    response = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
    )
    data = response.json()
    return data["current"]


def load_kb():
    """Load the whole knowledge base from the JSON file."""
    with open("kb.json", "r") as f:
        return json.load(f)


# --------------------------------------------------------------
# Tool schemas (what we expose to the model) and dispatch
# --------------------------------------------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "load_kb",
            "description": "Load the entire knowledge base to get the answer to the user's question.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for provided coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]


def call_function(name, args):
    if name == "load_kb":
        return load_kb()
    if name == "get_weather":
        return get_weather(**args)


# --------------------------------------------------------------
# Structured output schema
# --------------------------------------------------------------


class KBResponse(BaseModel):
    answer: str = Field(description="The answer to the user's question.")
    source: int = Field(description="The record id of the answer.")


# --------------------------------------------------------------
# Orchestration: one full request -> tool calls -> final answer
# --------------------------------------------------------------


def run_conversation(user_question: str) -> KBResponse:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_question},
    ]

    # Step 1: Call the model with the tools defined.
    completion = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
    )

    # Step 2 & 3: If the model asked for tools, execute them and feed
    # the results back into the conversation.
    tool_calls = completion.choices[0].message.tool_calls

    if tool_calls is None:
        print("Model did not call any tools.")
    else:
        messages.append(completion.choices[0].message)

        for tool_call in tool_calls:
            name = tool_call.function.name
            print(f"Model called tool: {name}")
            args = json.loads(tool_call.function.arguments)

            result = call_function(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

    # Step 4 & 5: Call the model again with the tool results and parse
    # the final answer into our structured schema.
    completion_2 = client.beta.chat.completions.parse(
        model=MODEL,
        messages=messages,
        tools=tools,
        response_format=KBResponse,
    )

    return completion_2.choices[0].message.parsed


def main():
    user_question = input("Ask a question: ")
    response = run_conversation(user_question)
    print(response.answer)
    print(response.source)


if __name__ == "__main__":
    main()
