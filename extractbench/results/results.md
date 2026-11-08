# Page Extract on ExtractBench

Value F1 (%), averaged over documents, each the same; a failed document counts zero.

| Tier | Overall | Short | Medium | Long | % perfect | ¢ / page | Failed | Documents |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard | 96.37 | 96.98 | 94.99 | 95.46 | 31.1 | 3.00 | 0 | 370 of 370 |
| Pro | 96.80 | 97.46 | 95.48 | 94.86 | 32.7 | 5.00 | 0 | 370 of 370 |

Precision, recall and seconds per document, by split:

| Tier | Split | Documents | Value F1 | Precision | Recall | Seconds / document |
|---|---|---:|---:|---:|---:|---:|
| Standard | short | 252 of 252 | 96.98 | 97.51 | 96.72 | 42 |
| Standard | medium | 98 of 98 | 94.99 | 95.33 | 94.81 | 140 |
| Standard | long | 20 of 20 | 95.46 | 95.24 | 95.69 | 376 |
| Pro | short | 252 of 252 | 97.46 | 97.46 | 97.50 | 34 |
| Pro | medium | 98 of 98 | 95.48 | 95.68 | 95.42 | 120 |
| Pro | long | 20 of 20 | 94.86 | 94.70 | 95.03 | 349 |

Beside ExtractBench's leaderboard (commit 4064262), by Overall value F1:

| # | System | Overall | ¢ / page |
|---:|---|---:|---:|
| 1 | **PageIndex Page Extract (Pro)** | 96.80 | 5.00 |
| 2 | **PageIndex Page Extract (Standard)** | 96.37 | 3.00 |
| 3 | LlamaExtract Agentic Plus | 96.17 | 7.50 |
| 4 | LlamaExtract Agentic Plus (Max Effort) | 96.17 | 19.11 |
| 5 | Reducto Deep Extract | 96.08 | 6.35 |
| 6 | Pulse (Effort) | 96.07 | 10.50 |
| 7 | LlamaExtract Agentic | 95.65 | 3.12 |
| 8 | Codex (GPT-6.1 Sol) | 95.31 | 7.13 |
| 9 | Claude Code (Sonnet 5.5) | 94.68 | 5.69 |
| 10 | Codex (GPT-6 Sol) | 94.57 | 9.80 |
| 11 | Pulse (Non-effort) | 94.51 | 3.00 |
| 12 | Codex (GPT-6.1 Terra) | 94.28 | 4.68 |
| 13 | LlamaExtract Cost-Effective | 94.21 | 1.00 |
| 14 | Codex (GPT-5.6 Sol) | 93.77 | 21.65 |
| 15 | Codex (GPT-5.5) | 93.35 | 33.63 |
