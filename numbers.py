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
    db.sql(query).show(max_width=300)


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

show("1. After a response, does the session come back? (tool call against a normal final answer)", """
select finish_reason,
       count(*) as responses,
       round(100.0 * count(*) / (select count(*) from steps), 1) as pct_of_all_requests,
       round(100 * avg(coalesce(next_start - end_ms < 2000, false)::int), 1) as pct_back_within_2s,
       round(100 * avg(coalesce(next_start - end_ms < 10000, false)::int), 1) as pct_back_within_10s,
       round(100 * avg(coalesce(next_start - end_ms < 60000, false)::int), 1) as pct_back_within_60s,
       round(100 * avg(coalesce(next_start - end_ms < 300000, false)::int), 1) as pct_back_within_5min,
       round(median(next_start - end_ms) / 1000, 1) as median_wait_s,
       round(100 * median((next_prompt - prompt) / prompt), 1) as median_prompt_growth_pct,
       round(median(prompt + output)) as median_context_tokens
from steps
where finish_reason in ('tool_calls', 'stop')
group by finish_reason
order by responses desc
""")

# A tool-loop step: it waited on a tool, its prompt only extends the previous one,
# and it went to the same provider and model less than a minute after the previous step ended.
# It "loses half" when under half of the previous prompt is served from cache.
db.sql("""
create view tool_steps as
select *,
       (start_ms - prev_end) / 1000.0 as gap_s,
       greatest(prev_prompt - cached, 0) as lost,
       prev_prompt >= 4096 and cached < 0.5 * prev_prompt as lost_half
from steps
where waited_for = 'tool' and transition = 'append'
  and cached is not null and prev_prompt is not null
  and provider = prev_provider and model = prev_model
  and start_ms >= prev_end
""")
db.sql("create view loop_steps as select * from tool_steps where gap_s < 60")
uncached = db.sql("select sum(prompt - cached) from steps where cached is not null").fetchone()[0]

show("2. Tool-loop steps that lose more than half of the previous prompt from cache", f"""
select count(*) as loop_steps,
       sum(lost_half::int) as lost_half,
       round(count(*) / sum(lost_half::int), 1) as one_in,
       round(100 * sum(lost) filter (where lost_half)
             / {uncached}, 1) as pct_of_all_uncached_tokens,
       round(100 * avg((next_cached >= 0.9 * prompt)::int)
             filter (where lost_half and next_transition = 'append' and next_cached is not null), 1) as pct_cached_again_next_step,
       round(100 * avg(coalesce(cached <= head, false)::int) filter (where lost_half), 1) as pct_at_most_system_and_tools,
       count(distinct user_id) filter (where lost_half) as users,
       count(distinct harness) filter (where lost_half) as harnesses
from loop_steps
""")

show("3. The same, by provider, with the median time to first token before, at and after such a step (ms)", """
select provider,
       count(*) as loop_steps,
       sum(lost_half::int) as lost_half,
       round(count(*) / sum(lost_half::int)) as one_in,
       round(median(prev_ttft) filter (where lost_half)) as ttft_before,
       round(median(ttft_ms)   filter (where lost_half)) as ttft_at,
       round(median(next_ttft) filter (where lost_half)) as ttft_after
from loop_steps
group by provider
having sum(lost_half::int) >= 100
order by loop_steps desc
""")

show("4. What is still cached at such a step", """
select round(100 * avg((cached = 0)::int), 1) as pct_nothing_cached,
       round(100 * avg(coalesce(cached <= head, false)::int), 1) as pct_at_most_system_and_tools,
       round(100 * avg(coalesce(cached <= 1.25 * head, false)::int), 1) as pct_same_with_25pct_slack,
       round(100 * median(cached / prev_prompt), 1) as median_pct_of_previous_prompt_cached,
       round(100 * median(head / prompt), 1) as median_pct_of_prompt_that_is_system_and_tools
from loop_steps
where lost_half
""")

show("5. How often it happens, by time since the previous step ended", """
select case when gap_s < 1 then '1. under 1 s' when gap_s < 3 then '2. 1 to 3 s'
            when gap_s < 10 then '3. 3 to 10 s' when gap_s < 30 then '4. 10 to 30 s'
            else '5. 30 to 60 s' end as time_since_previous_step,
       count(*) as loop_steps,
       sum(lost_half::int) as lost_half,
       round(100.0 * sum(lost_half::int) / count(*), 2) as pct
from loop_steps
group by 1
order by 1
""")

show("6a. If 'loses half' is replaced by another share of the previous prompt", f"""
select t as cached_below_this_share,
       sum((prev_prompt >= 4096 and cached < t * prev_prompt)::int) as steps,
       round(count(*) / sum((prev_prompt >= 4096 and cached < t * prev_prompt)::int), 1) as one_in,
       round(100 * sum(lost) filter (where prev_prompt >= 4096 and cached < t * prev_prompt) / {uncached}, 1)
           as pct_of_all_uncached_tokens
from loop_steps, (select unnest([0.1, 0.25, 0.5, 0.75]) as t)
group by t
order by t
""")

show("6b. If 'less than a minute after the previous step' is replaced by another limit", f"""
select c as limit_s,
       count(*) filter (where gap_s < c) as loop_steps,
       sum(lost_half::int) filter (where gap_s < c) as lost_half,
       round(count(*) filter (where gap_s < c) / sum(lost_half::int) filter (where gap_s < c), 1) as one_in,
       round(100 * sum(lost) filter (where lost_half and gap_s < c) / {uncached}, 1) as pct_of_all_uncached_tokens
from tool_steps, (select unnest([10, 60, 300]) as c)
group by c
order by c
""")

show("7a. By harness", """
select harness,
       count(*) as loop_steps,
       sum(lost_half::int) as lost_half,
       round(count(*) / nullif(sum(lost_half::int), 0)) as one_in,
       count(distinct user_id) filter (where lost_half) as users_affected
from loop_steps
group by harness
having count(*) >= 5000
order by loop_steps desc
""")

show("7b. By week and by user", """
with weekly as (
    select date_trunc('week', to_timestamp(start_ms / 1000)) as wk,
           count(*) as n, sum(lost_half::int) as k
    from loop_steps group by 1),
by_user as (
    select user_id, sum(lost) as lost from loop_steps where lost_half group by 1),
by_session as (
    select session_id, count(*) as k from loop_steps where lost_half group by 1)
select (select count(*) from weekly) as weeks,
       (select count(*) from weekly where k > 0) as weeks_with_such_steps,
       (select round(min(n / k)) from weekly where k > 0) as most_frequent_week_one_in,
       (select round(median(n / k)) from weekly where k > 0) as median_week_one_in,
       (select round(max(n / k)) from weekly where k > 0) as rarest_week_one_in,
       (select round(100 * max(lost) / sum(lost), 1) from by_user) as pct_of_loss_from_top_user,
       (select count(*) from by_session) as sessions_affected,
       (select count(*) from by_session where k = 1) as sessions_with_exactly_one
""")

show("8. Steps left out because the provider reported no cache number, with median time to first token (ms)", """
select provider,
       count(*) filter (where cached is null) as steps_without_cache_number,
       round(median(ttft_ms) filter (where cached is null)) as ttft_no_number,
       round(median(ttft_ms) filter (where cached >= 0.9 * prev_prompt)) as ttft_cached,
       round(median(ttft_ms) filter (where prev_prompt >= 4096 and cached < 0.5 * prev_prompt)) as ttft_lost_half
from steps
where waited_for = 'tool' and transition = 'append' and prev_prompt is not null
  and provider = prev_provider and model = prev_model
  and start_ms >= prev_end and start_ms - prev_end < 60000
group by provider
having count(*) filter (where cached is null) >= 100
order by steps_without_cache_number desc
""")

# The prompt of such a step should really start with the whole previous prompt.
# The last block of the previous prompt can be partial, so it is left out.
show("9. Does the prompt of such a step really start with the previous prompt?", f"""
with hit as (select session_id, step, prev_step from loop_steps where lost_half),
     blocks as (
         select session_id, step, block_ids from {requests}
         where (session_id, step) in (select session_id, step from hit)
            or (session_id, step) in (select session_id, prev_step from hit))
select count(*) as checked,
       sum((list_slice(cur.block_ids, 1, len(prev.block_ids) - 1)
            = list_slice(prev.block_ids, 1, len(prev.block_ids) - 1))::int) as starts_with_previous_prompt
from hit
join blocks cur  on cur.session_id = hit.session_id and cur.step = hit.step
join blocks prev on prev.session_id = hit.session_id and prev.step = hit.prev_step
""")
