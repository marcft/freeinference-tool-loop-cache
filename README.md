# Tool loops and the prompt cache

I went through the [FreeInference agentic trace](https://huggingface.co/datasets/harvardMadsys/freeinference_agentic_trace) to see what happens to the prompt cache while an agent waits on a tool.

Two things came out of it:

- After the model asks for a tool, the next request is back within a minute 95.8% of the time, with almost the same prompt.
- Even so, 1 in 295 of those steps loses more than half of its cached prompt and usually has it back one step later. Together they are 10.7% of all uncached tokens in the trace.

[NOTE.md](NOTE.md) has the details and what I can't tell from the trace alone.

## Run it

```
pip install duckdb huggingface_hub
huggingface-cli download harvardMadsys/freeinference_agentic_trace --repo-type dataset \
  --include "release/*/processed/requests.parquet" "release/*/processed/sessions.parquet" --local-dir data
python numbers.py data
```

It takes a few minutes and should print what is in [expected.txt](expected.txt).

Marc Frances
