"""What happens to the prompt cache while an agent waits on a tool.

Prints the numbers in NOTE.md from the FreeInference agentic trace.
Usage: python numbers.py [folder holding the trace]    (default: data)
"""
import sys

import duckdb

data = sys.argv[1] if len(sys.argv) > 1 else "data"
requests = f"read_parquet('{data}/**/requests.parquet')"
sessions = f"read_parquet('{data}/**/sessions.parquet')"
db = duckdb.connect()


def show(title, query):
    print(f"\n{title}")
    db.sql(query).show(max_width=200)


# One row per request, next to the previous and the next request of its session.
# "head" is the system prompt plus the tool definitions. The trace estimates token
# counts per role, so the estimate is rescaled to the provider's own prompt count.
db.sql(f"""
create table steps as
with r as (
    select session_id, step, start_ms, end_ms, ttft_ms, provider, model,
           finish_reason, transition, waited_for,
           prompt_tokens as prompt,
           coalesce(completion_tokens, 0) as output,
           cache_read_tokens as cached,
           coalesce(role_tokens['system'], 0) + coalesce(role_tokens['tool_definitions'], 0) as head_estimate,
           coalesce(role_tokens['system'], 0) + coalesce(role_tokens['user'], 0)
             + coalesce(role_tokens['assistant'], 0) + coalesce(role_tokens['tool'], 0)
             + coalesce(role_tokens['tool_definitions'], 0) as all_roles
    from {requests}
),
s as (select distinct session_id, user_id, harness from {sessions})
select r.*, s.user_id, s.harness,
       head_estimate * prompt / nullif(all_roles, 0) as head,
       lag(step)     over w as prev_step,
       lag(prompt)   over w as prev_prompt,
       lag(end_ms)   over w as prev_end,
       lag(provider) over w as prev_provider,
       lag(model)    over w as prev_model,
       lag(ttft_ms)  over w as prev_ttft,
       lead(start_ms)   over w as next_start,
       lead(prompt)     over w as next_prompt,
       lead(cached)     over w as next_cached,
       lead(transition) over w as next_transition,
       lead(ttft_ms)    over w as next_ttft
from r left join s using (session_id)
window w as (partition by session_id order by step)
""")

show("1. After the model asks for a tool, does the session come back?", """
select count(*) as tool_call_responses,
       round(100.0 * count(*) / (select count(*) from steps), 1) as pct_of_all_requests,
       round(100 * avg(coalesce(next_start - end_ms < 60000, false)::int), 1) as pct_back_within_60s,
       round(100 * avg(coalesce(next_start - end_ms < 2000, false)::int), 1) as pct_back_within_2s,
       round(median(next_start - end_ms) / 1000, 1) as median_wait_s,
       round(100 * median((next_prompt - prompt) / prompt), 1) as median_prompt_growth_pct,
       round(median(prompt + output)) as median_context_tokens
from steps
where finish_reason = 'tool_calls'
""")
