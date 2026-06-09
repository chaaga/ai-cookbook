import asyncio
import json
from contextlib import AsyncExitStack
import logging
from typing import Any, Dict, List

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import AsyncOpenAI

# Load environment variables
load_dotenv("../.env")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class MCPOpenAIClient:
    """Client for interacting with OpenAI models using tools from multiple MCP servers."""

    # Standing instructions sent as the first ("system") message on every query.
    # Outranks the user message, so it shapes behavior across the whole agent loop.
    SYSTEM_PROMPT = (
        "You are a helpful assistant with access to tools from multiple MCP servers. "
        "Prefer calling a tool to get real, current information over answering from "
        "your own knowledge, especially for weather, the company knowledge base, and "
        "GitHub repositories (via DeepWiki). When you use a tool, briefly state which "
        "tool you used in your final answer."
    )

    def __init__(self, model: str = "gpt-4o"):
        """Initialize the OpenAI MCP client.

        Args:
            model: The OpenAI model to use.
        """
        # Logger named after the class, so log lines show "%(name)s" == class name.
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("Starting MCPOpenAIClient initialization")
        # Maps each tool name to the MCP session that provides it, so we can
        # route a tool call to the right server.
        self.tool_to_session: Dict[str, ClientSession] = {}
        # All tools across every server, pre-formatted for the OpenAI API.
        self.openai_tools: List[Dict[str, Any]] = []
        self.exit_stack = AsyncExitStack()
        self.openai_client = AsyncOpenAI()
        self.model = model

    async def __aenter__(self):
        """Enter the async context; resources are acquired via connect_to_server."""
        return self

    async def __aexit__(self, *exc):
        """Exit the async context, tearing down all sessions and connections."""
        await self.exit_stack.aclose()

    async def connect_to_server(self, name: str, server_url: str):
        """Connect to an MCP server over Streamable HTTP and register its tools.

        Args:
            name: A label used to identify this server in logs.
            server_url: The server's Streamable HTTP endpoint, e.g. "http://localhost:8050/mcp".
        """
        self.logger.debug(f"connect_to_server: {name} at {server_url}")
        # streamablehttp_client yields a third value (a get_session_id callback)
        # that we don't need here, hence the trailing "_".
        read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(server_url)
        )
        session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        # List the server's tools once, at connect time: remember which session
        # serves each tool and cache its OpenAI-format definition.
        tools_result = await session.list_tools()
        self.logger.info(f"Connected to '{name}' ({server_url}) with tools:{tools_result.tools}")
        for tool in tools_result.tools:
            self.logger.info(f"  - {tool.name}: {tool.description}")
            self.tool_to_session[tool.name] = session
            self.openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
            )

    async def process_query(self, query: str, max_turns: int = 10) -> str:
        """Process a query as an agent loop using OpenAI and MCP tools.

        Each turn the model may request tool calls, which we execute and feed
        back so the next turn can reason over the results. The loop ends when
        the model returns a final answer with no tool calls (or we hit
        ``max_turns``, a safety cap on model<->tool round trips).

        Args:
            query: The user query.
            max_turns: Maximum number of model calls before giving up.

        Returns:
            The model's final answer.
        """
        messages: List[Any] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        self.logger.info(
            f"process_query: Received query: {query} "
            f"({len(self.openai_tools)} tools available, max_turns={max_turns})"
        )

        for turn in range(1, max_turns + 1):
            # Same call every turn: on turn 1 it's the initial query; on later
            # turns `messages` also carries prior tool results, so this is the
            # model reasoning over those results. tool_choice="auto" lets the
            # model either request more tools or produce a final answer.
            # messages mixes plain dicts with a pydantic ChatCompletionMessage;
            # default=... lets json serialize the pydantic object via model_dump().
            self.logger.info(
                f"process_query inside for loop: [Turn {turn}] Calling model with messages:\n"
                f"{json.dumps(messages, indent=2, default=lambda o: o.model_dump())}"
            )
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.openai_tools,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message
            messages.append(assistant_message)
            # model_dump_json(indent=2) pretty-prints; exclude_none drops the
            # many null fields the response carries, so the log stays readable.
            self.logger.info(
                f"process_query inside for loop: [Turn {turn}] Model response:\n"
                f"{response.model_dump_json(indent=2, exclude_none=True)}\n"
            )

            # No tool calls -> the model has produced its final answer; exit.
            if not assistant_message.tool_calls:
                self.logger.info(f"process_query inside for loop: Final answer after {turn} turn(s).")
                return assistant_message.content

            # Otherwise run every requested tool, routing each to the server
            # that owns it, and append the results for the next turn to use.
            for tool_call in assistant_message.tool_calls:
                session = self.tool_to_session[tool_call.function.name]
                self.logger.info(
                    f"process_query based on LLM response: [Turn {turn}] Calling tool: "
                    f"{tool_call.function.name} with args {tool_call.function.arguments}"
                )
                result = await session.call_tool(
                    tool_call.function.name,
                    arguments=json.loads(tool_call.function.arguments),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content[0].text,
                    }
                )

        # Fell through the cap without the model settling on a final answer.
        self.logger.warning(
            f"process_query: Reached max_turns={max_turns} without a final answer."
        )
        return "Sorry, I couldn't complete that within the allowed number of steps."


async def main():
    """Main entry point for the client."""
    # `async with` guarantees connections are torn down on exit, even if an
    # error is raised mid-way.
    async with MCPOpenAIClient() as client:
        # Local servers (each must already be running with transport="streamable-http")
        await client.connect_to_server("knowledge_base", "http://localhost:8050/mcp")
        await client.connect_to_server("weather", "http://localhost:8051/mcp")
        # Public, no-auth remote server — tools we didn't write, plugged in by URL.
        await client.connect_to_server("deepwiki", "https://mcp.deepwiki.com/mcp")

        print("\nType a query, or 'exit' / 'quit' to stop.")
        while True:
            try:
                query = input("\nQuery: ").strip()
            except (EOFError, KeyboardInterrupt):
                # Ctrl-D / Ctrl-C -> exit cleanly
                print()
                break

            if query.lower() in {"exit", "quit"}:
                break
            if not query:
                continue

            response = await client.process_query(query)
            logger.info(f"\nResponse from main: {response}")


if __name__ == "__main__":
    asyncio.run(main())
