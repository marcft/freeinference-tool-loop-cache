# Prompt-cache loss inside tool loops

Observations from the FreeInference agentic trace. Marc Frances, November 2026.

Every figure below is printed by `numbers.py`; the full output is in `expected.txt`, and the section numbers match its tables.

## Summary

- After a response that ends in a tool call, the same session sends its next request within one minute in 95.8% of cases, with a prompt that is almost unchanged. Reuse of the cached prefix is therefore close to certain, and the server can tell from its own output.
- Nevertheless, 1 in 295 tool-loop steps is served with less than half of the previous prompt from cache. These steps account for 10.7% of all uncached prompt tokens in the trace.
- In 88.4% of them, what remains cached is no larger than the system prompt and tool definitions, which is what a request would find on a machine that had not served the session before.

## 1. Data and definitions

The trace covers 16 weeks of coding-agent traffic through FreeInference: 1,222,199 requests. For each request it records the prompt size, the number of prompt tokens the provider reports as served from cache, timings, and what the step was waiting for.

- **Tool-loop step.** A request that waited on a tool, whose prompt only extends the previous prompt of the session, and that was sent to the same provider and model less than 60 seconds after the previous step ended. There are 1,021,835.
- **Losing half.** A tool-loop step whose previous prompt had at least 4,096 tokens and of which less than half was served from cache.
- **Uncached tokens.** Prompt tokens minus cached tokens, over all requests that report a cache number: 4.82 billion.

## 2. A tool call announces the next request

| Response ended with | Responses | Share of requests | Next request within 2 s | 10 s | 60 s | 5 min | Median wait | Median prompt growth | Median context |
|---|---|---|---|---|---|---|---|---|---|
| a tool call | 1,137,188 | 93.0% | 54.5% | 84.6% | 95.8% | 98.9% | 1.7 s | 0.4% | 119,892 tokens |
| a final answer | 84,800 | 6.9% | 6.1% | 14.1% | 34.4% | 66.7% | 93.6 s | 0.3% | 117,382 tokens |

A cache normally holds what might be requested again. After a tool call the next request is nearly certain, arrives within seconds, and carries about 120K tokens of context that the provider has just processed.

## 3. Steps that lose the cache

3,463 of the 1,021,835 tool-loop steps lose half (1 in 295).

- They hold 10.7% of all uncached tokens in the trace.
- The following step is served from cache again in 87.0% of cases.
- They occur for 141 users and 13 harnesses, in 1,558 sessions, of which 959 have exactly one.

**They are real misses.** Median time to first token before, at and after such a step:

| Provider | Tool-loop steps | Lose half | One in | Before | At | After |
|---|---|---|---|---|---|---|
| A | 515,240 | 625 | 824 | 1.0 s | 19.3 s | 1.0 s |
| B | 291,777 | 921 | 317 | 6.5 s | 10.1 s | 6.8 s |
| C | 89,028 | 1,177 | 76 | 3.9 s | 8.1 s | 3.9 s |
| D | 82,129 | 565 | 145 | 4.3 s | 10.3 s | 4.4 s |
| F | 11,103 | 154 | 72 | 6.0 s | 9.0 s | 4.3 s |

**What remains cached.** In 18.3% of these steps nothing is cached. In 88.4% the cached part is no larger than the system prompt plus tool definitions (92.6% if the estimate of their size is allowed to be 25% too low). The median step keeps 0.5% of the previous prompt, while the system prompt and tools make up 16.0% of a prompt at the median. The part that survives is the part every session shares.

**Timing.** The rate does not go to zero for short waits, and rises with longer ones:

| Time since the previous step ended | Tool-loop steps | Lose half | Rate |
|---|---|---|---|
| under 1 s | 373,317 | 1,022 | 0.27% |
| 1 to 3 s | 323,811 | 961 | 0.30% |
| 3 to 10 s | 209,978 | 722 | 0.34% |
| 10 to 30 s | 87,839 | 446 | 0.51% |
| 30 to 60 s | 26,890 | 312 | 1.16% |

A rate of 0.27% within one second is hard to attribute to a retention time expiring.

## 4. Robustness

**The two thresholds.** Neither the "half" nor the "one minute" drives the result:

| Cached share below | Steps | One in | Share of uncached tokens |
|---|---|---|---|
| 10% | 2,827 | 362 | 9.9% |
| 25% | 3,132 | 326 | 10.4% |
| 50% | 3,463 | 295 | 10.7% |
| 75% | 4,110 | 249 | 11.1% |

| Time limit | Tool-loop steps | Lose half | One in | Share of uncached tokens |
|---|---|---|---|---|
| 10 s | 907,106 | 2,705 | 335 | 7.7% |
| 60 s | 1,021,835 | 3,463 | 295 | 10.7% |
| 300 s | 1,049,718 | 4,063 | 258 | 13.1% |

**Harnesses.** All twelve harnesses with at least 5,000 tool-loop steps are affected:

| Harness | Tool-loop steps | Lose half | One in | Users affected |
|---|---|---|---|---|
| pi | 268,470 | 803 | 334 | 16 |
| hermes | 212,914 | 711 | 299 | 40 |
| opencode | 187,406 | 775 | 242 | 51 |
| oh-my-pi | 61,369 | 108 | 568 | 14 |
| kilo | 55,874 | 502 | 111 | 15 |
| codex | 52,280 | 181 | 289 | 12 |
| eval:swe-bench | 52,193 | 24 | 2,175 | 2 |
| claude-code | 52,002 | 115 | 452 | 13 |
| copilot | 31,207 | 51 | 612 | 4 |
| zcode | 24,949 | 98 | 255 | 6 |
| cline | 10,411 | 60 | 174 | 4 |
| openclaw | 7,996 | 25 | 320 | 2 |

**Time and users.** Such steps occur in every calendar week of the trace, from 1 in 25 in the most affected week to 1 in 703 in the least, with a median of 1 in 291. The user with the largest loss accounts for 11.0% of it.

**The prompts are true extensions.** For all 3,463 steps, the block ids of the prompt begin with the block ids of the previous prompt.

## 5. Limitations

- **Cause.** The trace has no machine or replica identifiers. A request that reached a different machine and a request whose cache was evicted look the same. The signature in section 3 suggests the former but does not establish it.
- **Provider-reported cache numbers.** The cached-token count is what each provider reports. Time to first token agrees with it (section 3), but it is not an independent measurement.
- **Requests without a cache number.** 32,738 otherwise qualifying steps report none and are excluded (counting the seven providers with at least 100 such steps). Their median time to first token lies between a hit and a miss on provider A (5.0 s, against 0.7 s and 19.3 s), matches a miss on provider C, and matches a hit on provider D. If some are misses, the figures above are lower bounds.
- **Estimated sizes.** The size of the system prompt and tool definitions is an estimate in the trace, so the 88.4% is approximate.
- **Heterogeneity.** The rate ranges from 1 in 72 to 1 in 824 across providers. More than one mechanism is likely.

## 6. Open question

The FreeInference gateway pins each caller to an endpoint and releases the pin once the endpoint is too busy. When the next step is almost certain and carries about 120K tokens, under what conditions is waiting for the machine that holds them cheaper than moving to a free one?

The trace cannot answer this. The gateway's logs could, since they record where each step was sent and how long it would have waited.

## Reproduction

See the README. `python numbers.py data` prints all tables in a few minutes.
