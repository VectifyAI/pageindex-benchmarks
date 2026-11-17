# Method

As [Financial QA's](../financial-qa/METHOD.md): the same questions, configurations, routes, rubric and graders.
What differs:

## Index

The 40 PDFs (`../financial-qa/corpus/pdfs/`) in one PageIndex Cloud collection, uploaded with PageIndex's default
settings (`upload.py`): 7,318 pages. `data/collection.json` records each document as the cloud reports it.

## Agent

`PageIndexClient(api_key=..., chat_model="openrouter/<model>")` of PageIndex 0.7.0, asked with `chat()` on the
collection. The model is called over Chat Completions through LiteLLM and OpenRouter, as in Financial QA. The tools
are those PageIndex Cloud serves the agent; each run records them and a hash of the agent's system prompt
(`env.cloud` in `data/runs.jsonl`). Up to 100 turns per question from the start.

## Cost

- **Model calls**: what OpenRouter billed, counted as in Financial QA (each question's standing attempt).
- **PageIndex search**: the SDK reports no PageIndex charge, so it is computed at PageIndex's list prices from what
  each search reports it read: per 1,000 pages a `search_pages` call reads, $0.10 for its first question and $0.02
  for each extra one; per 1,000 documents a `search_documents` call reads, $0.30 and $0.10.
- **Indexing**: $1 per 1,000 pages, $7.32 for the 40 filings, once; not included in the cost per run.

## Index time

The chart's index time, for a 100-page document, is the figure pageindex.ai/agent gives; it was not measured in
these runs.

## Grading

One round, `data/grading/round1_*`, graded as Financial QA's rounds are, with a check grader on every answer (297 of
300 agreed) and a third grader on the 3 disagreements. Legacy PageIndex's results are Financial QA's own.
