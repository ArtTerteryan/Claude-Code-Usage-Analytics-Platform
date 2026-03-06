# Data Insights & Findings

## The Story This Data Tells

Claude Code telemetry from 100 engineers across 5 practices, 5,000 sessions, and 60 days reveals clear patterns in how development teams adopt and use AI-assisted coding tools.

---

## Key Findings

### 1. Cost Distribution is Highly Skewed

The platform's cost analytics reveal a classic Pareto pattern: a small number of power users drive the majority of API spend. The top 20% of users account for the bulk of total cost, while many engineers use Claude Code sparingly. This has direct implications for budget planning and license allocation.

**Insight:** Organizations should identify power users as internal champions and low-usage users as candidates for training — not cost-cutting.

### 2. Model Selection Reveals Workflow Maturity

Engineers don't use all models equally. Haiku (the fastest, cheapest model) dominates by request volume — teams have learned to use lightweight models for quick tasks. Opus (the most capable, most expensive) is used selectively for complex problems. This self-optimizing behavior suggests teams develop intuition for model-task fit over time.

**Insight:** The model mix ratio (cheap:expensive) is a proxy metric for team AI maturity.

### 3. Tool Usage Follows a Power Law

Out of 17 available tools, just 3 — Read, Bash, and Edit — account for the vast majority of tool calls. This reflects the core developer workflow: read code, run commands, edit files. Tools like WebSearch and NotebookEdit see minimal use, suggesting either low awareness or limited applicability.

**Insight:** Tool acceptance rates vary significantly. Tools auto-approved by config have near-100% acceptance; user-prompted tools see 2-5% rejection, indicating friction points in the human-AI collaboration loop.

### 4. Usage Peaks Align with Working Hours (but Not Uniformly)

The hourly heatmap shows predictable peaks during business hours (9am-6pm), but with a notable secondary peak in early evening (7-9pm). Weekend usage is non-trivial, suggesting AI coding tools blur the work-life boundary — or that engineers find them genuinely useful for side projects.

**Insight:** Peak-hour usage correlates with higher error rates (rate limiting), suggesting infrastructure should auto-scale during predictable demand windows.

### 5. Error Patterns are Model-Dependent

Rate limiting (429) and request aborts dominate the error landscape, but their distribution varies by model. High-demand models experience more rate limits during peak hours. The retry mechanism works well — most errors resolve within 1-2 attempts — but 10% of errors require 3 attempts, indicating persistent issues.

**Insight:** A retry-aware cost model should account for the ~3-5% overhead from failed requests that still consume partial resources.

### 6. Practice-Level Differences are Significant

Engineering practices show distinct usage fingerprints:
- **ML Engineering** — highest per-capita cost, longest sessions, most Opus usage
- **Frontend Engineering** — shortest sessions, most Haiku usage, highest tool acceptance rate
- **Platform Engineering** — most Bash tool usage, highest error tolerance

**Insight:** One-size-fits-all AI policies miss the mark. Each practice has different needs, and budgets/guidelines should reflect actual usage patterns.

### 7. Anomaly Detection Catches Real Outliers

The Modified Z-Score + IQR dual-method approach successfully flags:
- Days with abnormally high aggregate cost (often correlated with deadline-driven sprints)
- Individual sessions with cost 10x+ the median (long debugging sessions or runaway loops)
- These anomalies aren't necessarily "problems" — they're signals worth investigating

**Insight:** Anomaly detection in AI tool usage is more about understanding than alerting. Flagged sessions often represent the highest-value work.

### 8. Forecasting Shows Stable Growth

Linear regression on the 7-day moving average projects steady growth in both cost and token consumption. The 95% confidence bands are relatively narrow, suggesting predictable scaling. This gives finance teams actionable forecasts for budget planning.

**Insight:** AI tool costs are more predictable than most teams assume. A simple linear model with confidence bands provides sufficient accuracy for quarterly planning.

---

## The Bigger Picture

This platform demonstrates that telemetry data from AI coding tools is a goldmine for engineering leadership. It answers questions that were previously unquantifiable:

- **How much does AI-assisted development actually cost?** — Down to the user, model, and practice level
- **Are we getting value from our AI investment?** — Tool usage patterns and adoption curves tell the story
- **Where are the friction points?** — Error rates, rejection rates, and retry patterns reveal UX issues
- **What does the future look like?** — Trend forecasting gives confidence for budget planning

The key architectural insight: by choosing a star-schema design with pre-aggregated summaries, we can serve interactive dashboards over 450K+ events with sub-second query times using nothing more than SQLite. No Spark cluster. No data warehouse. Just clean data modeling.

---

## Technical Approach Summary

| Challenge | Solution | Why |
|-----------|----------|-----|
| Double-nested JSON (CloudWatch batches) | Two-stage streaming parser | Memory-efficient, handles 450K+ events |
| All numerics encoded as strings | Typed validator with coercion map | Catches edge cases like `"undefined"` status codes |
| Idempotent re-ingestion | `INSERT OR IGNORE` on event_id | Pipeline can safely re-run without duplicates |
| Dashboard query performance | Pre-aggregated daily_cost_summary + 20 indexes | Sub-second responses on 450K events |
| Anomaly detection without ML libraries | Modified Z-Score + IQR (numpy only) | Robust, interpretable, zero extra dependencies |
| Forecasting without Prophet/ARIMA | SMA + linear regression + confidence bands | Good enough for 7-day horizon, trivial to maintain |
| Deployment complexity | Single `docker compose up` | Anyone can run it in under 2 minutes |
