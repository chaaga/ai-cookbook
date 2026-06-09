# MCP Crash Course for Python Developers

The Model Context Protocol (MCP) is a powerful framework that enables developers to build AI applications with large language models (LLMs) by providing a standardized way to connect models with external data sources and tools. This crash course will guide you through the fundamentals of MCP, from understanding its core concepts to implementing servers and clients that leverage prompts, resources, and tools.

## Table of Contents

1. [Introduction and Context](./1-introduction-and-context/README.md)
2. [Understanding MCP](./2-understanding-mcp/README.md)
3. [Simple Server Setup with Python SDK](./3-simple-server-setup/README.md)
4. [OpenAI Integration](./4-openai-integration/README.md)
5. [MCP vs Function Calling](./5-mcp-vs-function-calling/README.md)
6. [Running with Docker](./6-run-with-docker/README.md)
7. [Lifecycle Management](./7-lifecycle-management/README.md)

## Setting Up Your Development Environment

Let's start by setting up our environment. The MCP Python SDK provides everything we need to build both servers and clients.

First, create and activate a virtual environment in this folder (PowerShell):

```powershell
# Create the virtual environment
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1
```

Then install the dependencies:

```bash
# Using uv (recommended)
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

The MCP CLI tools provide helpful utilities for development and testing:

```bash
# Test a server with the MCP Inspector
mcp dev server.py

# Install a server in Claude Desktop
mcp install server.py

# Run a server directly
mcp run server.py
```

### Starting the MCP Inspector via npx

`mcp dev server.py` launches the Inspector by spawning your server through `uv run --with mcp mcp run server.py`. If `uv` isn't installed on your system, this fails with a `spawn uv ENOENT` error.

You can launch the Inspector directly via `npx` instead, which spawns your server using your active virtual environment's `python` (no `uv` required):

```powershell
npx @modelcontextprotocol/inspector python server.py
```

After it starts, open the URL printed in the terminal (it includes a `?MCP_PROXY_AUTH_TOKEN=...` query parameter — using a stale or bare URL like `http://localhost:6274` will fail with "Connection Error - Check if your MCP server is running and proxy token is correct").

**When to use which:**

- Use `mcp dev server.py` if you have `uv` installed — it's the standard, documented workflow.
- Use `npx @modelcontextprotocol/inspector python server.py` if `uv` isn't installed and you'd rather not add it, since your existing venv (with `mcp` installed via `pip install -r requirements.txt`) already has everything needed.

**Notes:**

- The Inspector connects over **stdio**, so make sure `transport = "stdio"` in your server's `if __name__ == "__main__":` block — if it's set to `"sse"` or `"streamable-http"`, the server won't perform the stdio handshake the Inspector expects, and you'll see the same "Connection Error" message.
- Don't `print()` to stdout in a stdio-transport server — stdout is the literal JSON-RPC channel, and any extra text breaks message parsing (`SyntaxError: ... is not valid JSON`). Send diagnostic output to stderr instead, e.g. `print("...", file=sys.stderr)`.
- The Inspector binds to fixed local ports by default (client UI on `6274`, proxy server on `6277`). Running a second instance while one is active fails with `Proxy Server PORT IS IN USE`. Either stop the first instance (`Ctrl+C`) before starting another, or set `CLIENT_PORT`/`SERVER_PORT` environment variables to run multiple instances side by side.

## Resources and Next Steps

Key resources for deepening your MCP knowledge:

- [Model Context Protocol documentation](https://modelcontextprotocol.io)
- [Model Context Protocol specification](https://spec.modelcontextprotocol.io)
- [Python SDK GitHub repository](https://github.com/modelcontextprotocol/python-sdk)
- [Officially supported servers](https://github.com/modelcontextprotocol/servers)
- [MCP Core Architecture](https://modelcontextprotocol.io/docs/concepts/architecture)
