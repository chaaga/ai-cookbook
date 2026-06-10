# AI Engineering Learnings

Personal knowledge base — concepts, decisions, and insights accumulated while building projects in this repo.

---

## MCP (Model Context Protocol)

### Plain Tool vs MCP Tool

A **tool** (in the LLM sense) is a function the model can call — defined as a JSON schema, the model decides when to invoke it, you execute it and return the result. This is the raw pattern used in `patterns/workflows/3-tools.py`.

An **MCP tool** is the same concept but served over a standardized protocol:

| | Plain tool | MCP tool |
|---|---|---|
| Definition | JSON schema hardcoded in the client | Defined once in the server, auto-discovered by any client |
| Execution | Your client runs the function | The MCP server runs the function |
| Reuse | Copy-paste into every project | Any MCP-compatible client connects and uses it |
| Hosting | In-process with the client | Separate process, can be remote |

Plain tools are fine for one-off scripts. MCP tools are the right choice when you want capabilities reused across projects, teams, or clients.

### Benefits of MCP Tools

1. **Discoverability** — the model discovers available tools at runtime via `list_tools()`. The tool description *is* the documentation for the model; no human needs to read docs and hardcode schemas.
2. **Reusability** — define once in the server, use from any MCP-compatible client (Claude Code, Python client, PydanticAI, LangChain). No copy-pasting JSON schemas.
3. **Separation of concerns** — the server owns the implementation; the client owns the orchestration. Update tool logic without touching client code.
4. **Model-friendly output** — shape return values for LLM consumption (concise, no irrelevant fields) rather than for a frontend.
5. **Composability** — connect to multiple MCP servers and the model sees all tools in a flat list. Mix your own servers with external ones (e.g. DeepWiki) with no glue code.

### Why Companies Publish MCP Servers, Not Agents

Tools are **stateless** — call them, get a result, done. An agent has a loop, memory, and decision-making built in. Sharing a stateful agent is harder to host and forces your orchestration logic on the consumer.

When you expose `get_weather` as an MCP tool, any client can use it however they want — once, in a loop, in parallel, conditionally. If you wrapped it in an agent, you'd be dictating the prompt design, model choice, and loop logic to every client. Companies want to own that layer.

**A2A (Agent-to-Agent protocol)** is the emerging standard for sharing agents the way MCP shares tools. As it matures, expect agent marketplaces the same way MCP server directories exist today.

### When to Wrap Company APIs as MCP Tools

REST APIs are designed for **developers writing code**. MCP tools are designed for **models doing reasoning**. If your clients are building agentic systems, expose MCP tools — the model can discover and call them without any human writing glue code.

A company with APIs like `make_sentence_compliant` and `get_customer` should wrap them as MCP tools, not agents. The client's model decides when to call each tool. Group related tools into logical servers:

```
compliance_server  →  make_sentence_compliant, check_policy, flag_content
data_server        →  get_customer, get_contract, search_documents
```

### MCP vs A2A

| | MCP | A2A |
|---|---|---|
| **Purpose** | Connect agents to tools and data | Connect agents to other agents |
| **State** | Stateless (tools) | Stateful (tasks with lifecycle) |
| **Task lifecycle** | Fire and forget | submitted → working → completed / failed |
| **Streaming** | Not built in | Native SSE |
| **Maturity** | Production-ready | Emerging (2025) |

Use MCP for capabilities. Use A2A for orchestrating agents across teams or vendors.

---

## Agent Patterns

### Agent vs Subagent

There is no technical distinction — it is purely about role in the system. The same code can be both.

- **Agent** = runs a loop, has autonomy, decides which tools to call
- **Subagent** = an agent being orchestrated by another agent

`MCPOpenAIClient` in this repo is an agent when run standalone. Wrap it in `agent_server.py` and have an orchestrator call it, and that same instance becomes a subagent. The label describes the relationship, not the code.

### MCP Tool vs Agent — When to Use Which

- **Capability** (do X to Y) → MCP tool
- **Workflow** (decide how to apply X, Y, Z to achieve a goal) → agent

If the decision-making and sequencing should belong to the *caller*, expose a tool. If you want to encapsulate the reasoning loop, expose an agent.

### Multi-Agent Pattern with MCP

An orchestrator can treat a sub-agent as just another MCP server:

```
orchestrator (MCPOpenAIClient)
    └── agent_server.py  (port 8052)  ← exposes ask_agent() tool
            └── MCPOpenAIClient internally
                    ├── kb_server   (port 8050)
                    └── weather_server (port 8051)
```

The orchestrator only knows `ask_agent` exists — it has no visibility into what tools the sub-agent uses. The `MCPOpenAIClient` class is the same at both levels; only the servers it connects to differ.

### Agent Loop Pattern

The standard agent loop (used in `MCPOpenAIClient.process_query`):

1. Call model with tools available
2. If model returns tool calls → execute them, append results to messages, go to 1
3. If model returns a final answer → return it
4. Safety cap: `max_turns` prevents infinite loops

---

## APIs and SDKs

### Chat Completions vs OpenAI Responses API

| | Chat Completions | Responses API |
|---|---|---|
| **Availability** | OpenAI, Anthropic, Google, Mistral (standard) | OpenAI only |
| **State** | You manage the messages list | OpenAI stores history server-side |
| **Built-in tools** | Not available | `web_search`, `file_search`, `code_interpreter` |
| **MCP compatibility** | Yes — MCP tool format maps directly | No |
| **Portability** | Works across all providers | OpenAI-specific |

Use Chat Completions when building MCP-based or multi-provider systems. Use Responses API when you need OpenAI's built-in tools.

### Built-in Tools vs Custom Function Tools (Responses API)

- **Built-in tools** (`web_search`, etc.) — OpenAI executes them internally. You just declare them; no execution code needed. You only check `output_item.type == "web_search_call"` if you want to log it.
- **Custom function tools** — same as Chat Completions: model decides to call them, you execute and return the result.

### PydanticAI and LangChain Under the Hood

Both abstract over Chat Completions (or equivalent). PydanticAI auto-generates JSON tool schemas from function signatures and runs the agent loop for you — exactly what `MCPOpenAIClient` does manually. The difference is operational convenience, not capability. Understanding the raw pattern first (as in this repo) makes frameworks trivial to pick up.

### `async with` and Why It's Needed

```python
async with MCPOpenAIClient() as client:
    ...
```

This calls `__aenter__` on enter and `__aexit__` on exit (even if an exception is raised). In `MCPOpenAIClient`, `__aexit__` awaits `self.exit_stack.aclose()` to tear down all HTTP sessions — that requires `await`, which only works in an async context. A regular `with` can't do this.

`__aenter__` here just returns `self` (nothing async happens on entry). The `async with` is needed purely because of `__aexit__`. Some classes use `__aenter__` meaningfully — e.g. awaiting until a background task is ready — but that's not the case here.

---

## Frameworks

### Raw API vs Framework vs MCP

| | Raw API (`3-tools.py`) | Framework (`PydanticAI`) | MCP (`MCPOpenAIClient`) |
|---|---|---|---|
| Schema definition | Hand-written JSON | Auto-generated from function signature | Defined in server, auto-discovered |
| Agent loop | Manual | Framework handles it | Manual (you built it) |
| Tool execution | Manual dispatch | Framework handles it | Manual dispatch |
| Portability | Provider-specific | Multi-provider | Multi-provider + multi-server |
| Best for | Learning, one-off scripts | Production agents | MCP-integrated systems |

---

## Next Steps (Learning Path)

Based on the AI Engineer 2026 roadmap:

- [x] LLM APIs (OpenAI, Anthropic)
- [x] Tool calling — raw and via MCP
- [x] Agent loop pattern
- [x] Multi-server MCP client
- [x] External MCP servers
- [ ] **RAG** — ingestion pipeline, embeddings, vector DB, hybrid search, re-ranking
- [ ] Observability — Langfuse tracing, LLM-as-a-judge evals, cost tracking
- [ ] Deployment — Docker, cloud, CI/CD
- [ ] Multi-agent with A2A protocol (emerging)
