# Multi-Server MCP + OpenAI Integration

This project extends the [OpenAI Integration example](../4-openai-integration) with three additions:

1. **Multiple local MCP servers** — a knowledge-base server and a weather server run simultaneously, each on its own port.
2. **An external (remote) MCP server** — [DeepWiki](https://mcp.deepwiki.com/mcp) is connected by URL, no local setup required.
3. **Exposed to Claude Code via `.mcp.json`** — the local servers are also registered in the project's `.mcp.json` so Claude Code itself can call them as MCP tools during the chat session.

## Architecture

```
┌─────────────────────────────────────────────┐
│                  client.py                  │
│           MCPOpenAIClient (gpt-4o)          │
└──────┬──────────────┬──────────────┬────────┘
       │              │              │
       ▼              ▼              ▼
 kb_server.py   weather_server.py   https://mcp.deepwiki.com/mcp
 port 8050       port 8051          (remote, no auth)
 tools:          tools:             tools: ask_github_repo, …
  get_knowledge   get_weather
  _base           compare_weather
  get_office      _prompt (prompt)
  _location
```

All three connections use **Streamable HTTP** transport. The client keeps a `tool_to_session` map so each tool call is routed to the correct server.

## Files

| File | Purpose |
|------|---------|
| `kb_server.py` | FastMCP server on port 8050 — exposes `get_knowledge_base` and `get_office_location` tools backed by `data/kb.json` |
| `weather_server.py` | FastMCP server on port 8051 — exposes `get_weather` tool (OpenWeatherMap API) and a `compare_weather_prompt` MCP prompt |
| `client.py` | Production client — `MCPOpenAIClient` class with multi-server support, an agent loop (`max_turns`), structured logging, and async context management |
| `client-simple.py` | Earlier single-server version using stdio transport — useful to see the minimal pattern before multi-server was added |
| `client-sse-no-llm.py` | Bare MCP client over SSE — connects and calls a tool directly without any LLM; good for verifying a server works |
| `data/kb.json` | Company Q&A pairs (vacation policy, expense policy, remote work, etc.) |

## Key Concepts Demonstrated

### Multiple MCP servers from one client
`connect_to_server()` can be called once per server. Each call opens its own Streamable HTTP session and registers the server's tools into the shared `tool_to_session` dict and `openai_tools` list. OpenAI sees all tools from all servers in a single flat list; the client routes each tool call back to the right session.

### Connecting to a remote/external server
DeepWiki is added with one line — no local process, no `.env` key:
```python
await client.connect_to_server("deepwiki", "https://mcp.deepwiki.com/mcp")
```
This shows that any publicly accessible MCP server can be plugged in by URL.

### MCP Prompts
`weather_server.py` exposes a `compare_weather_prompt` as an MCP *prompt* (not a tool). Prompts are reusable instruction templates that the client/host can retrieve and inject into the conversation to guide model behavior — here, to force parallel tool calls when comparing two cities.

### Agent loop with `max_turns`
`process_query()` runs a loop: call the model → execute any tool calls → feed results back → repeat until the model returns a final answer or `max_turns` is reached. This handles multi-hop reasoning (e.g., "What's the weather at our HQ?" requires calling `get_office_location` first, then `get_weather`).

### Exposed to Claude Code via `.mcp.json`
The project root contains a `.mcp.json` that registers the two local servers:
```json
{
  "mcpServers": {
    "knowledge_base": { "type": "http", "url": "http://localhost:8050/mcp" },
    "weather":        { "type": "http", "url": "http://localhost:8051/mcp" }
  }
}
```
When the servers are running, Claude Code can call these tools directly in the chat session — the same servers serve both the Python client and the IDE assistant.

## Running the Example

**1. Start both servers** (in separate terminals):
```powershell
python kb_server.py
python weather_server.py
```

**2. Set environment variables** in `../.env`:
```
OPENAI_API_KEY=sk-...
OPENWEATHERMAP_API_KEY=...
```

**3. Run the client:**
```powershell
python client.py
```

Type any query at the prompt. Examples:
- `What is our vacation policy?` → routes to `get_knowledge_base`
- `What's the weather in Tokyo?` → routes to `get_weather`
- `What's the weather at our HQ?` → multi-hop: `get_office_location` then `get_weather`
- `Tell me about the anthropics/anthropic-sdk-python repo` → routes to DeepWiki

## Transport Comparison

| Transport | Used by | Notes |
|-----------|---------|-------|
| `streamable-http` | `client.py`, `kb_server.py`, `weather_server.py` | Recommended for network-accessible servers; supports multiple concurrent clients |
| `stdio` | `client-simple.py` | Client launches server as a subprocess; single-client only |
| `sse` | `client-sse-no-llm.py` | Older HTTP streaming approach; being superseded by streamable-http |
