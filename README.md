# Feast Agent

An LLM-powered Data Agent that manages [Feast](https://feast.dev/) feature stores through natural language — locally or against a **remote** Feast deployment with **RBAC**.

<img width="1908" height="901" alt="feast-agent" src="https://github.com/user-attachments/assets/7bf7fbfc-9302-4466-8ad3-807e18a4ca1f" />


## What It Does

The Data Agent wraps the Feast Python SDK as LangChain tools and orchestrates them via a LangGraph ReAct agent. You describe what you want in plain English, and the agent handles the Feast API calls:

- **Register data sources** — file, BigQuery, push sources
- **Create feature views** — batch, stream, on-demand
- **Define transformations** — pandas, python, SQL modes
- **Handle backfills** — full and incremental materialization
- **Sync offline to online store** — automated materialization workflows
- **Ensure correctness** — schema validation, freshness checks, offline/online consistency
- **Optimize pipelines** — TTL analysis, freshness monitoring, unused feature detection
- **Manage RBAC** — list/create permissions, check auth status, verify connectivity

## Installation

Requires [uv](https://docs.astral.sh/uv/) (recommended) or pip.

```bash
# Install with all LLM providers
uv pip install -e ".[all]"

# Or lock and sync for reproducible environments
uv sync --extra all
```

For a specific LLM provider only:

```bash
uv pip install -e ".[openai]"    # OpenAI only
uv pip install -e ".[anthropic]" # Anthropic only
uv pip install -e ".[ollama]"    # Ollama (local, no API key needed)
```

Development install:

```bash
uv sync --extra all --extra dev
```

## Configuration

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FEAST_AGENT_REPO_PATH` | `.` | Path to your Feast feature repository |
| `FEAST_AGENT_FEATURE_STORE_YAML` | — | Explicit path to `feature_store.yaml` |
| `FEAST_AGENT_LLM_PROVIDER` | `openai` | LLM provider: `openai`, `anthropic`, or `ollama` |
| `FEAST_AGENT_LLM_MODEL` | `gpt-4o` | Model name |
| `FEAST_AGENT_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OPENAI_API_KEY` | — | Required when using OpenAI |
| `ANTHROPIC_API_KEY` | — | Required when using Anthropic |

### Remote Connectivity

| Variable | Default | Description |
|----------|---------|-------------|
| `FEAST_AGENT_REMOTE_REGISTRY_URL` | — | Remote registry gRPC endpoint (e.g. `feast-registry:6570`) |
| `FEAST_AGENT_REMOTE_REGISTRY_TLS` | `false` | Enable TLS for the gRPC connection |
| `FEAST_AGENT_REMOTE_REGISTRY_CERT` | — | Path to TLS certificate file |
| `FEAST_AGENT_PROJECT` | `default` | Feast project name (used with remote registry) |

### Authentication / RBAC

| Variable | Default | Description |
|----------|---------|-------------|
| `FEAST_AGENT_AUTH_TYPE` | `no_auth` | Auth type: `no_auth`, `oidc`, or `kubernetes` |
| `FEAST_AGENT_AUTH_DISCOVERY_URL` | — | OIDC discovery URL |
| `FEAST_AGENT_AUTH_CLIENT_ID` | — | OIDC client ID |
| `FEAST_AGENT_AUTH_CLIENT_SECRET` | — | OIDC client secret (for client-credentials flow) |
| `FEAST_AGENT_AUTH_TOKEN` | — | Pre-fetched auth token (also reads `FEAST_OIDC_TOKEN`) |

## Usage

### Local Mode with Ollama (no API key needed)

The fastest way to test locally. Make sure [Ollama](https://ollama.com/) is running and you have a model pulled:

```bash
# Pull a model with good tool-calling support
ollama pull llama3.1
# or for better results:
ollama pull qwen2.5

# Install the agent with Ollama support
uv pip install -e ".[ollama]"

# Run with Ollama
feast-agent --provider ollama --model llama3.1 --repo-path ./feature_repo chat
```

Or via environment variables:

```bash
export FEAST_AGENT_LLM_PROVIDER=ollama
export FEAST_AGENT_LLM_MODEL=qwen2.5
# If Ollama is on another host:
# export FEAST_AGENT_OLLAMA_BASE_URL=http://my-gpu-server:11434

feast-agent chat
```

### Local Mode (default)

```bash
# Point at a local Feast repo and chat
feast-agent --repo-path ./feature_repo chat
```

### Remote Mode with OIDC Auth

Connect to a remote Feast registry server with OIDC authentication:

```bash
export FEAST_AGENT_REMOTE_REGISTRY_URL=feast-registry.example.com:6570
export FEAST_AGENT_AUTH_TYPE=oidc
export FEAST_OIDC_TOKEN=$(get-my-token)
export OPENAI_API_KEY=sk-...

feast-agent chat
```

Or pass options directly:

```bash
feast-agent \
  --remote-registry feast-registry.example.com:6570 \
  --auth-type oidc \
  chat
```

### Remote Mode with Kubernetes Auth

When running inside a Kubernetes cluster (e.g. in a pod alongside Feast):

```bash
export FEAST_AGENT_REMOTE_REGISTRY_URL=feast-registry.feast-system.svc:6570
export FEAST_AGENT_AUTH_TYPE=kubernetes

feast-agent chat
```

The agent automatically uses the pod's service account token.

### Using an Existing `feature_store.yaml`

If you already have a `feature_store.yaml` with auth and registry configured:

```bash
feast-agent --yaml /path/to/feature_store.yaml chat
```

The agent reads the `auth:` and `registry:` blocks from the YAML directly.

### Interactive Chat

```
You: Check the connectivity and auth status

Agent: Connected to remote registry at feast-registry.example.com:6570.
       Auth type: oidc. RBAC is active with 3 permissions registered.

You: List all permissions

Agent: Found 3 permissions:
       1. "admin_full_access" — all actions, RoleBasedPolicy(roles=["admin"])
       2. "ml_eng_read" — READ_ONLINE, READ_OFFLINE, RoleBasedPolicy(roles=["ml-engineer"])
       3. "data_eng_write" — CREATE, UPDATE, WRITE_OFFLINE, RoleBasedPolicy(roles=["data-engineer"])

You: Create a permission allowing the "analyst" role to read online features

Agent: Created Permission 'analyst_online_read': actions=[READ_ONLINE, DESCRIBE],
       policy=RoleBasedPolicy(roles=['analyst']).

You: Register a file source called driver_stats from data/driver_stats.parquet
      with timestamp field event_timestamp

Agent: Registered FileSource 'driver_stats' pointing to data/driver_stats.parquet.

You: Now create an entity, feature view, and materialize the last 7 days

Agent: Created Entity 'driver' with join key 'driver_id'.
       Created FeatureView 'driver_hourly_stats' with 2 features.
       Materialized driver_hourly_stats from 2026-04-06 to 2026-04-13.
```

### Single-Shot Execution

```bash
feast-agent run "List all feature views and check their data freshness"
```

### Quick Status (no LLM required)

```bash
feast-agent status
```

### Programmatic Usage

```python
from feast_agent import create_agent, AgentConfig

# Local with Ollama (no API key needed)
config = AgentConfig(
    repo_path="path/to/feature_repo",
    llm_provider="ollama",
    llm_model="llama3.1",
)
agent = create_agent(config=config)
response = agent.invoke("List all feature views")
print(response)

# Remote with OIDC + cloud LLM
config = AgentConfig(
    remote_registry_url="feast-registry.example.com:6570",
    auth_type="oidc",
    auth_token="eyJhbG...",
    llm_provider="openai",
    llm_model="gpt-4o",
)
agent = create_agent(config=config)
response = agent.invoke("Show me all feature views and their freshness status")
print(response)
```

## Architecture

```
User (natural language)
    │
    ▼
LangGraph ReAct Agent
    │
    ├── Auth Tools ──────── check_connectivity, get_auth_status,
    │                       list_permissions, create_permission
    ├── Inspect Tools ───── list_all_objects, describe_*, sample data
    ├── Registry Tools ──── register sources, entities, feature services
    ├── Feature View Tools ─ create standard/batch/stream views
    ├── Transform Tools ─── create on-demand feature views
    ├── Materialize Tools ── backfill, incremental sync, status
    ├── Validate Tools ──── schema, freshness, offline/online parity
    └── Optimize Tools ──── TTL analysis, freshness, suggestions
          │
          ▼
    Feast FeatureStore
      (local or remote gRPC + auth)
          │
    ┌─────┼──────┐
    ▼     ▼      ▼
 Offline Online Registry
 Store   Store
```

## How RBAC Works

Feast implements RBAC through **Permission** objects stored in the registry:

1. **No permissions registered** = all access **denied** (deny-by-default)
2. Each permission specifies **resource types**, **allowed actions**, and a **policy** (who)
3. Policies can be role-based, group-based, or namespace-based
4. Auth is handled via OIDC JWT tokens or Kubernetes TokenReview
5. The MCP server (if enabled) inherits the same RBAC via FastAPI route middleware

The agent can inspect and manage these permissions through the `get_auth_status`,
`list_permissions`, and `create_permission` tools.
