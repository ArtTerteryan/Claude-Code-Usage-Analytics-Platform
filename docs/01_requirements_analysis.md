# Requirements Analysis: Claude Code Telemetry Analytics Platform

## 1. Dataset Structure — Complete Field Inventory

### 1.1 Source File: `output/telemetry_logs.jsonl`

**Format:** JSONL — one JSON object per line. Each line is a CloudWatch-style log batch.

#### Batch-Level Fields (top-level per JSONL line)

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `messageType` | string | `"DATA_MESSAGE"` | Constant — always `DATA_MESSAGE` |
| `owner` | string | `"123456789012"` | Constant — fake AWS account ID |
| `logGroup` | string | `"/claude-code/telemetry"` | Constant |
| `logStream` | string | `"otel-collector"` | Constant |
| `subscriptionFilters` | array[string] | `["logs-to-s3"]` | Constant — single element |
| `logEvents` | array[object] | — | **Variable-length (1–10 events per batch)** |
| `year` | int | `2026` | Derived from first event timestamp |
| `month` | int | `1` | Derived from first event timestamp |
| `day` | int | `15` | Derived from first event timestamp |

#### logEvent-Level Fields (each element in `logEvents`)

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `id` | string | `"1234...5678"` | Random 56–58 digit integer as string. **Not a UUID.** |
| `timestamp` | int | `1737936000000` | Epoch milliseconds (UTC) |
| `message` | string (JSON) | `"{\"body\":...}"` | **JSON-encoded string** — must be parsed again |

#### Event Payload (parsed from `logEvent.message`)

Each parsed message contains exactly 4 top-level keys:

| Key | Type | Description |
|-----|------|-------------|
| `body` | string | Event type identifier (see §1.2) |
| `attributes` | object | All event-specific + common fields (flat key-value) |
| `scope` | object | Instrumentation metadata |
| `resource` | object | Host/user environment info |

#### Common Attributes (present in ALL event types)

| Attribute Key | Type | Cardinality | Notes |
|---------------|------|-------------|-------|
| `event.timestamp` | string | high | Format: `YYYY-MM-DDThh:mm:ss.mmmZ` (ISO 8601 variant, millisecond precision) |
| `event.name` | string | 5 | One of: `api_request`, `tool_decision`, `tool_result`, `user_prompt`, `api_error` |
| `organization.id` | string (UUID) | ~num_users | One org per user (1:1 mapping in generator) |
| `session.id` | string (UUID) | ~num_sessions | Unique per coding session |
| `terminal.type` | string | 9 | `vscode`(40), `pycharm`(20), `WarpTerminal`(10), `webstorm`(8), `iTerm2`(7), `Terminal`(5), `intellij`(5), `cursor`(3), `goland`(2) |
| `user.account_uuid` | string (UUID) | ~num_users | Unique per user |
| `user.email` | string | ~num_users | Format: `first.last@example.com` — **join key to employees.csv** |
| `user.id` | string (SHA-256 hex) | ~num_users | Deterministic hash of email |

#### Scope Object

| Field | Type | Cardinality | Notes |
|-------|------|-------------|-------|
| `scope.name` | string | 1 | Constant: `"com.anthropic.claude_code.events"` |
| `scope.version` | string | 20 | Claude Code CLI version. Weighted distribution, e.g. `"2.1.39"`, `"2.1.50"` |

#### Resource Object

| Field | Type | Cardinality | Notes |
|-------|------|-------------|-------|
| `host.arch` | string | 2 | `arm64`, `x86_64` |
| `host.name` | string | ~num_users | Machine hostname, user-specific |
| `os.type` | string | 3 | `darwin`, `linux`, `windows` |
| `os.version` | string | 7 combinations | Tied to os.type (see OS_CONFIGS) |
| `service.name` | string | 1 | Constant: `"claude-code-None"` |
| `service.version` | string | 20 | Same as scope.version (assigned per user, static for lifetime) |
| `user.email` | string | 1 | **Always empty string `""`** — do NOT use for joins |
| `user.practice` | string | 5 | Engineering practice — **duplicated from employees.csv** |
| `user.profile` | string | ~num_users | Username/profile slug |
| `user.serial` | string | ~num_users | 10-char alphanumeric device serial |

---

### 1.2 Event Types — Complete Field Reference

#### `claude_code.api_request` (body = `"claude_code.api_request"`)

Represents a successful API call to a Claude model.

| Attribute | Type in JSON | Actual Type | Distribution / Notes |
|-----------|-------------|-------------|---------------------|
| `model` | string | string | 5 values: `claude-haiku-4-5-20251001` (wt 362), `claude-opus-4-6` (203), `claude-opus-4-5-20251101` (185), `claude-sonnet-4-5-20250929` (155), `claude-sonnet-4-6` (21) |
| `cost_usd` | **string** | float | Normal dist, model-specific. Range ~0 to ~0.3+. **Must parse to float.** |
| `duration_ms` | **string** | int | Normal dist, model-specific. Min 100. **Must parse to int.** |
| `input_tokens` | **string** | int | Normal dist. Min 0. **Must parse to int.** |
| `output_tokens` | **string** | int | Normal dist. Min 1. **Must parse to int.** |
| `cache_read_tokens` | **string** | int | Normal dist. Min 0. Often large (70k+ for opus/sonnet). **Must parse to int.** |
| `cache_creation_tokens` | **string** | int | Normal dist. Min 0. **Must parse to int.** |

#### `claude_code.tool_decision` (body = `"claude_code.tool_decision"`)

Represents Claude's decision to use a tool (or user's rejection).

| Attribute | Type | Distribution / Notes |
|-----------|------|---------------------|
| `tool_name` | string | 17 values: `Read`(190), `Bash`(176), `Edit`(79), `Grep`(47), `Glob`(29), `mcp_tool`(26), `Write`(18), `TodoWrite`(16), `TaskUpdate`(12), `Task`(11), `TaskCreate`(6), `AskUserQuestion`(4), `WebFetch`(2), `ToolSearch`(2), `WebSearch`(2), `NotebookEdit`(1), `ExitPlanMode`(1) |
| `decision` | string | 2 values: `accept`, `reject`. Reject only when source=`user_reject` |
| `source` | string | 4 values: `config`(80), `user_temporary`(15), `user_permanent`(3), `user_reject`(2) |

#### `claude_code.tool_result` (body = `"claude_code.tool_result"`)

Represents the outcome of a tool execution. **Only generated for accepted tool decisions.**

| Attribute | Type in JSON | Actual Type | Distribution / Notes |
|-----------|-------------|-------------|---------------------|
| `tool_name` | string | string | Same 17 tools as tool_decision |
| `success` | **string** | boolean | `"true"` or `"false"`. **Must parse to bool.** Per-tool success rates (Bash lowest at 93.3%) |
| `duration_ms` | **string** | int | Tool-specific. Huge variance: `Task` avg 476,282ms vs `TaskUpdate` avg 1ms. **Must parse to int.** |
| `decision_source` | string | string | Echoes the decision source: `config` or `user_reject` |
| `decision_type` | string | string | Echoes: `accept` or `reject` |
| `tool_result_size_bytes` | **string (optional)** | int | **Present only ~30% of the time.** Range 10–50,000. **Must check existence before parsing.** |

#### `claude_code.user_prompt` (body = `"claude_code.user_prompt"`)

Represents a user's prompt submission. Content is redacted.

| Attribute | Type in JSON | Actual Type | Notes |
|-----------|-------------|-------------|-------|
| `prompt` | string | string | Constant: `"<REDACTED>"` — no analytical value |
| `prompt_length` | **string** | int | Lognormal distribution (µ=4.85, σ=1.8). p50 ≈ 128, p90 ≈ 2,969. **Must parse to int.** |

#### `claude_code.api_error` (body = `"claude_code.api_error"`)

Represents a failed API call.

| Attribute | Type in JSON | Actual Type | Notes |
|-----------|-------------|-------------|---------------------|
| `error` | string | string | 8 distinct messages. Top: `"Request was aborted."` (wt 44), `"...rate limit..."` (19) |
| `status_code` | string | string/int | **Mixed type:** can be `"429"`, `"400"`, `"500"`, `"401"`, or `"undefined"`. Not always numeric! |
| `model` | string | string | Same 5 models |
| `duration_ms` | **string** | int | Normal dist, mean 500ms. **Must parse to int.** |
| `attempt` | **string** | int | Values: 1 (70%), 2 (20%), 3 (10%). **Must parse to int.** |

---

### 1.3 Source File: `output/employees.csv`

**Format:** CSV with header row, no quoting (names have no commas).

| Column | Type | Cardinality | Notes |
|--------|------|-------------|-------|
| `email` | string | ~num_users | **Primary key. Join key to `attributes.user.email`.** Format: `first.last@example.com` |
| `full_name` | string | ~num_users | `"First Last"` format, title-cased |
| `practice` | string | 5 | `Platform Engineering`, `Data Engineering`, `ML Engineering`, `Backend Engineering`, `Frontend Engineering` |
| `level` | string | 10 | `L1` through `L10`. Bell-curve distribution peaking at L5 |
| `location` | string | 5 | `United States`, `Germany`, `United Kingdom`, `Poland`, `Canada` |

---

## 2. Data Quality Issues and Edge Cases

### 2.1 String-Encoded Numerics (CRITICAL)
All numeric metrics in `attributes` are **serialized as strings**, not native JSON numbers:
- `cost_usd`, `duration_ms`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `prompt_length`, `attempt`, `tool_result_size_bytes`
- **Impact:** Every numeric attribute requires explicit type casting during ingestion. A blanket `float()` or `int()` conversion strategy is needed.

### 2.2 Boolean-as-String
- `tool_result.success` is `"true"` or `"false"` (lowercase strings), not JSON booleans.
- **Impact:** Must map `"true" → 1/True`, `"false" → 0/False`.

### 2.3 The `status_code` Problem
- `api_error.status_code` can be `"undefined"` (a string literal, not a number).
- Occurs for client-side errors like "Request was aborted" and credential issues.
- **Impact:** Cannot blindly cast to int. Must treat as nullable integer or keep as string category.

### 2.4 Double-Nested JSON
- Each JSONL line → batch object → `logEvents[].message` is a **JSON string within JSON**.
- **Impact:** Two-stage parsing required: `json.loads(line)` then `json.loads(event["message"])` for each event.

### 2.5 Optional Fields
- `tool_result_size_bytes` is present in only ~30% of `tool_result` events.
- **Impact:** Must handle `KeyError` / use `.get()` with default. Database column should be nullable.

### 2.6 Empty `resource.user.email`
- `resource.user.email` is always `""` (empty string). The actual email is in `attributes.user.email`.
- **Impact:** Must use `attributes.user.email` for all joins. Could mislead if someone grabs the resource field instead.

### 2.7 Static User Properties
- In the generator, each user gets a fixed `terminal`, `version`, `os_config` assigned at creation time. These don't change across sessions.
- In real data these could vary, but in this synthetic dataset they're per-user constants.
- **Impact:** Aggregating "terminal usage" will really show "how many users use each terminal", not session-level variation.

### 2.8 Timestamp Redundancy
- Three timestamps per event: batch-level `year/month/day`, `logEvent.timestamp` (epoch ms), and `attributes.event.timestamp` (ISO string).
- **Impact:** Use `attributes.event.timestamp` as the canonical source. The epoch ms and date partition fields are derivatives.

### 2.9 Cost Precision
- `cost_usd` is generated via `positive_normal()` — can produce very small negatives clamped to 0, or high outliers.
- Stored as float-to-string, so precision up to ~15 decimal digits.
- **Impact:** Round to reasonable precision (e.g., 6 decimal places) for storage and display.

### 2.10 Session Structure Assumptions
- A session always starts with a `user_prompt` and alternates prompts → API calls → tool cycles.
- `tool_result` events only exist for accepted `tool_decision` events.
- API errors trigger an immediate retry (so error events are always followed by another `api_request`).
- **Impact:** Session reconstruction is deterministic if events are ordered by timestamp within session.

### 2.11 No Explicit Session Metadata
- There is no "session_start" or "session_end" event. Session boundaries must be inferred from the first/last event timestamps per `session.id`.

---

## 3. Key Analytics Questions This Data Can Answer

### 3.1 Cost & Token Consumption
1. **What is the total and average cost per day/week/month?** (trend over time)
2. **Which models consume the most budget?** (cost breakdown by model)
3. **Who are the top cost-generating users?** And by practice/level/location?
4. **What is the token efficiency?** (output tokens per input token, cache hit ratios)
5. **How does cost correlate with seniority level?** (L1–L10)
6. **Which practice has the highest per-capita spend?**

### 3.2 Usage Patterns
7. **What are the peak usage hours/days?** (heatmap of events by hour-of-day × day-of-week)
8. **How long are typical sessions?** (distribution of session durations and turns per session)
9. **How many sessions per user per day?** (engagement/adoption metrics)
10. **What is the prompt length distribution?** Do senior engineers write longer prompts?
11. **Which terminal/IDE is most popular?** Breakdown by practice.
12. **What OS and architecture distribution do we see?**

### 3.3 Tool Usage
13. **What are the most frequently used tools?** (ranking with proportions)
14. **What is the accept/reject rate per tool?** Which tools get rejected most?
15. **What is the success/failure rate per tool?** (Bash likely has the highest failure rate)
16. **Which tools take the longest?** (duration distribution by tool)
17. **How does tool mix vary by practice or level?** Do ML engineers use different tools?

### 3.4 Error Analysis
18. **What is the overall error rate?** (api_error events / api_request events)
19. **Which error types are most common?** Distribution by error message and status code.
20. **Which models have the highest error rate?**
21. **Are errors correlated with time of day?** (e.g., rate limits during peak hours)
22. **How many retries do errors typically require?** (attempt distribution)

### 3.5 Organizational Insights
23. **Adoption curve:** How does usage grow over the 30/60-day window?
24. **Practice benchmarking:** Which practice is most/least productive per dollar?
25. **Geographic patterns:** Usage differences by location (timezone effects).
26. **Version adoption:** Are users upgrading Claude Code versions?

### 3.6 Predictive / Advanced (Bonus Features)
27. **Forecast next week's token consumption** using time-series analysis (ARIMA, Prophet, or simple exponential smoothing).
28. **Anomaly detection:** Flag sessions with abnormally high cost, error rates, or duration.
29. **User clustering:** Group users by behavior (tool preferences, cost profiles).

---

## 4. Technical Challenges for the Ingestion Pipeline

### 4.1 Two-Stage JSON Parsing
Every event requires parsing the JSONL line into a batch, then parsing each `logEvent.message` string into the actual event payload. For large datasets (5,000+ sessions → potentially 500k+ events), this double-deserialization is the main I/O bottleneck.

**Approach:** Stream-parse the JSONL file line by line, flatten events in a single pass, avoid loading the entire file into memory.

### 4.2 Schema Heterogeneity
Each event type has a different set of attributes. A single flat `attributes` dict contains both common fields and event-specific fields. There is no discriminator except `body` (or `attributes.event.name`).

**Approach:** Parse into a normalized schema — one base `events` table with common columns, plus event-type-specific tables (star schema) OR a single wide table with nullable columns for type-specific fields.

### 4.3 Type Coercion at Scale
All numeric attributes are strings. The ingestion layer must:
- Know which fields are numeric vs. categorical
- Handle `"undefined"` in `status_code` gracefully
- Convert `"true"/"false"` to boolean
- Handle missing optional fields (`tool_result_size_bytes`)

**Approach:** Define an explicit schema mapping (field name → target type → coercion function) applied during ingestion.

### 4.4 Denormalization vs. Normalization Trade-off
The `resource` and `scope` objects repeat identical data across all events in a session (and even across sessions for the same user). Storing them denormalized in every row wastes space; normalizing into dimension tables (users, sessions) saves space but requires joins.

**Approach:** Star schema — dimension tables for `users` (from employees.csv + resource fields), `sessions` (session_id → user, start/end time), `models`. Fact tables for each event type referencing dimensions by foreign key.

### 4.5 Timestamp Handling
Three timestamp representations must be reconciled. The canonical ISO string in `attributes.event.timestamp` uses the format `YYYY-MM-DDThh:mm:ss.mmmZ` (note: milliseconds, not microseconds, in the fractional part). SQLite doesn't have a native timestamp type, so store as ISO string or Unix epoch integer.

**Approach:** Parse to Python `datetime`, store as ISO 8601 text in SQLite (sortable, human-readable), create indexed columns for `date` and `hour` to enable fast time-based queries.

### 4.6 Employee Data Linkage
The join between telemetry and employees is on `email`. The generator guarantees all telemetry emails exist in the employee CSV, but a real pipeline should handle:
- Telemetry from unknown users (LEFT JOIN)
- Employees with no telemetry data

**Approach:** Use LEFT JOINs from events to employees. Validate referential integrity post-ingestion and surface warnings.

### 4.7 Batch-Level Metadata
The batch-level fields (`year`, `month`, `day`, `owner`, etc.) are mostly constants or derivatives. Only `logEvents` carries analytical value.

**Approach:** Discard batch-level metadata after extraction. Optionally log batch count for data-completeness auditing.

### 4.8 Idempotent Ingestion
If the pipeline is re-run, it should not create duplicate records. The `logEvent.id` field (a large random integer string) could serve as a dedup key, though in practice with synthetic data this is less critical.

**Approach:** Use `INSERT OR IGNORE` with a unique constraint on event ID, or truncate-and-reload for simplicity in a batch pipeline.

---

## 5. Data Scale Estimates

With default parameters (`--num-users 30 --num-sessions 500 --days 30`):
- Estimated events: ~30,000–80,000 (depends on session length distribution)
- Estimated JSONL file: ~20–60 MB
- SQLite database: ~10–30 MB (with indexes)

With recommended parameters (`--num-users 100 --num-sessions 5000 --days 60`):
- Estimated events: ~300,000–800,000
- Estimated JSONL file: ~200–600 MB
- SQLite database: ~100–300 MB

Both are well within SQLite's capabilities (single-file, no server needed).

> **Note:** The actual database schema (star schema with separate fact tables per event type) is documented in [02_architecture.md](02_architecture.md).
