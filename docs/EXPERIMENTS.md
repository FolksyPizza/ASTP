# Experiments

This is the experiment record for ASTP. It reports the current large-scale evaluation. Earlier
work used a small set of hand-authored scenarios run on hosted models; that setup has been
retired in favor of the standard public suites below, which are larger, model-agnostic, and
scored objectively.

## Method

The evaluation compares four ways of delivering prior context to a receiver model on the same
task:

- `transcript`: the full accumulated context.
- `summary`: a same-model summarization of that context.
- `rag`: TF-IDF retrieval over that context.
- `mctp`: a believed-state packet selected to a token budget.

Each task is run once per condition. Task success is an objective check: code suites execute the
produced function against unit tests, and the math and long-context suites use exact-match answer
checks. The delivered-context size is measured with the tiktoken `o200k_base` encoding. The
harness, adapters, and scorers live in the ASTP-Bench repository.

## Results (interim)

One capable model so far: a 27B-parameter open-weights model (Qwen3 series, 4-bit quantized)
served with a 128K context window. Each cell reports pass rate and average delivered-context
size in tokens.

| Suite | transcript | summary | rag | mctp |
| --- | --- | --- | --- | --- |
| gsm8k | 97% / 0 | 97% / 0 | 97% / 0 | 97% / 63 |
| humaneval | 96% / 0 | 96% / 0 | 96% / 0 | 96% / 136 |
| mbpp | 82% / 0 | 82% / 0 | 82% / 0 | 81% / 52 |
| multifile | 100% / 80 | 91% / 279 | 100% / 75 | 100% / 157 |
| longbench | 61% / 12,360 | 46% / 836 | 46% / 354 | 59% / 180 |

Cells are pass rate / average context tokens. (longbench uses robust QA answer matching that
tolerates markdown, punctuation, and rewording.)

## Interpretation

The low-context suites (gsm8k, humaneval, mbpp) tie across all four conditions. These tasks carry
little prunable prior context, so the delivery method does not change the outcome. This is the
expected baseline and confirms ASTP does not cost accuracy where there is nothing to select.

The long-context suite is where the conditions separate. On longbench, ASTP nearly matches the
accuracy of the full transcript (59% against 61%) while delivering about one sixty-ninth of the
context (180 tokens against 12,360), and it scores about thirteen points above both same-model
summarization and TF-IDF retrieval. On the smaller models, whose 8192-token window forces the
transcript to truncate, ASTP wins outright. This is the mechanism working as intended: it holds
the accuracy of sending everything at a fraction of the token cost.

## Pending

- repobench is held back pending a correction to how the completion prompt is framed (the target
  file's cursor position must sit at the end of the prompt).
- swebench is held back pending the native scoring pass.
- The multi-agent (swarm) suite, where believed-state should hold across handoffs that a summary
  cannot, is still running.
- Additional models and trials.

Per-suite tables and the full methodology are maintained in the ASTP-Bench
[results doc](https://github.com/FolksyPizza/ASTP-Bench/blob/main/docs/RESULTS.md).
