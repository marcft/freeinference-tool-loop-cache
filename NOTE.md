# The next step is already known

Marc Frances, November 2026. Everything here comes from `numbers.py`; the output is in `expected.txt`.

## The trace

16 weeks of coding agents going through FreeInference, 1.22M requests. For each request it gives the prompt size, how much of it the provider says it served from cache, and what the step was waiting on.

## 1. After a tool call, the session comes back

93% of responses end with the model asking for a tool. After those:

- the next request starts within a minute 95.8% of the time, and within two seconds 54.5% of the time (median 1.7 s)
- its prompt is the old one plus a little: 0.4% longer at the median
- the context it carries is about 120K tokens at the median

A cache is normally a bet on what might come back. Here it is hardly a bet. The server itself asked for the next step.

## 2. Some steps lose the cache anyway

I call a step a tool-loop step when it waited on a tool, its prompt only extends the previous one, and it went to the same provider and model less than a minute after the previous step ended. There are 1,021,835 of them.

In 3,463 of them (1 in 295) less than half of the previous prompt came from cache.

- They are 10.7% of all uncached tokens in the trace.
- 87% of the time the next step is cached again.
- In 88.4% of them, what is still cached is no bigger than the system prompt plus the tool definitions. It looks like the request went somewhere that had never seen the session.
- They come from 141 users and 13 harnesses.
- They are real misses. Time to first token jumps at that step and comes back down on the next one.
- The prompt really does start with the previous one, in all 3,463.

| Provider | Tool-loop steps | Lose half | One in | First token before | At that step | After |
|---|---|---|---|---|---|---|
| A | 515,240 | 625 | 824 | 1.0 s | 19.3 s | 1.0 s |
| B | 291,777 | 921 | 317 | 6.5 s | 10.1 s | 6.8 s |
| C | 89,028 | 1,177 | 76 | 3.9 s | 8.1 s | 3.9 s |
| D | 82,129 | 565 | 145 | 4.3 s | 10.3 s | 4.4 s |
| F | 11,103 | 154 | 72 | 6.0 s | 9.0 s | 4.3 s |

## What I can't tell

- **Why it happens.** The trace has no machine ids, so I can't tell a request that landed on another machine from one whose cache was evicted.
- **Whether the cache numbers are exact.** They are what each provider reports. Requests with no cache number are left out.
- **The 88.4%.** The size of the system prompt and tools is an estimate in the trace, so that figure is approximate.
- **Whether it is one thing.** The rate goes from 1 in 72 to 1 in 824 depending on the provider, so probably not.

## The question

The FreeInference gateway pins each caller to an endpoint and releases them once it gets too busy. When the next step is almost certain and carries 120K tokens, when is waiting for the machine that has them cheaper than moving to a free one?

The trace can't answer that. The gateway's logs could: where each step went, and how long it would have waited.
