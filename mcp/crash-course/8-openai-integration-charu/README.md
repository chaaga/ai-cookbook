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

## Design Decisions

### MCP Tool vs Agent — when to use which

An **MCP tool** is stateless: input in, output out. The model decides when to call it, how many times, and in what order. An **agent** owns a loop — it decides which tools to call and sequences them to reach a goal.

Rule of thumb:
- **Capability** (do X to Y) → MCP tool
- **Workflow** (decide how to apply X, Y, Z to achieve a goal) → agent

**Real example:** a company has REST APIs like `make_sentence_compliant` and `get_customer`. These should be wrapped as MCP tools, not agents. Clients building agentic systems connect to your MCP server and the model decides when to call each tool. If you wrapped them in an agent, you'd be forcing your orchestration logic on every client.

REST APIs are designed for developers writing code. MCP tools are designed for models doing reasoning. If your clients are building agentic systems, expose MCP tools.

### Agent vs Subagent

There is no technical distinction — it's about role in a given system. The same code can be both.

- **Agent** = runs autonomously, has a loop, decides which tools to call
- **Subagent** = an agent being orchestrated by another agent

`MCPOpenAIClient` in this repo is an agent when run standalone. Wrap it in `agent_server.py` and have an orchestrator call it, and that same instance becomes a subagent. The label describes the relationship, not the code.

### Tools vs MCP Tools

A **tool** (in the LLM sense) is a function the model can call — you define it as a JSON schema, the model decides when to invoke it, you execute it and return the result. This is what `patterns/workflows/3-tools.py` does with the raw OpenAI SDK.

An **MCP tool** is the same concept but served over a standardized protocol (MCP). The difference is operational:

| | Plain tool | MCP tool |
|---|---|---|
| Definition | JSON schema hardcoded in your client | Defined once in the server, auto-discovered by any client |
| Execution | Your client runs the function | The MCP server runs the function |
| Reuse | Copy-paste into every project | Any MCP-compatible client connects and uses it |
| Hosting | In-process with the client | Separate process, can be remote |

Plain tools are fine for one-off scripts. MCP tools are the right choice when you want capabilities reused across projects, teams, or clients.

### Benefits of MCP Tools

1. **Discoverability** — the model discovers available tools at runtime by calling `list_tools()`. No human needs to read docs and hardcode schemas. The tool description *is* the documentation for the model.

2. **Reusability** — define the tool once in the server, use it from any MCP-compatible client (Claude Code, your Python client, PydanticAI, LangChain). No copy-pasting JSON schemas across projects.

3. **Separation of concerns** — the server owns the implementation; the client owns the orchestration. You can update the tool's logic without touching any client code.

4. **Model-friendly output** — you shape the return value for LLM consumption (concise text, no irrelevant fields) rather than for a frontend or another service.

5. **Composability** — clients can connect to multiple MCP servers and the model sees all tools in a flat list. Mix your own servers with external ones (like DeepWiki) with no extra glue code.

### MCP vs A2A (Agent-to-Agent protocol)

- **MCP** = how an agent connects to tools and data (stateless capabilities)
- **A2A** = how agents coordinate with each other (stateful, long-running tasks)

Companies publish MCP servers today because tools are stateless and composable — any client can use them. Agents are opinionated (your prompt, your model, your loop). A2A is the emerging protocol for sharing agents the same way MCP shares tools. As A2A matures, expect "agent marketplaces" the same way MCP server directories exist today.

## Transport Comparison

| Transport | Used by | Notes |
|-----------|---------|-------|
| `streamable-http` | `client.py`, `kb_server.py`, `weather_server.py` | Recommended for network-accessible servers; supports multiple concurrent clients |
| `stdio` | `client-simple.py` | Client launches server as a subprocess; single-client only |
| `sse` | `client-sse-no-llm.py` | Older HTTP streaming approach; being superseded by streamable-http |
