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

# A tool-loop step: it waited on a tool, its prompt only extends the previous one,
# and it went to the same provider and model less than a minute after the previous step ended.
# It "loses half" when under half of the previous prompt is served from cache.
db.sql("""
create view loop_steps as
select *,
       greatest(prev_prompt - cached, 0) as lost,
       prev_prompt >= 4096 and cached < 0.5 * prev_prompt as lost_half
from steps
where waited_for = 'tool' and transition = 'append'
  and cached is not null and prev_prompt is not null
  and provider = prev_provider and model = prev_model
  and start_ms - prev_end >= 0 and start_ms - prev_end < 60000
""")

show("2. Tool-loop steps that lose more than half of the previous prompt from cache", """
select count(*) as loop_steps,
       sum(lost_half::int) as lost_half,
       round(count(*) / sum(lost_half::int), 1) as one_in,
       round(100 * sum(lost) filter (where lost_half)
             / (select sum(prompt - cached) from steps where cached is not null), 1) as pct_of_all_uncached_tokens,
       round(100 * avg((next_cached >= 0.9 * prompt)::int)
             filter (where lost_half and next_transition = 'append' and next_cached is not null), 1) as pct_cached_again_next_step,
       round(100 * avg(coalesce(cached <= head, false)::int) filter (where lost_half), 1) as pct_at_most_system_and_tools,
       count(distinct user_id) filter (where lost_half) as users,
       count(distinct harness) filter (where lost_half) as harnesses
from loop_steps
""")
