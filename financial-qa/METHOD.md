# Method

How the questions were made, how each configuration was run, graded and priced. Every number in the results comes
from the files in `data/` through `results.py` and `grade.py`.

## Task

A question about one or more companies' annual reports goes to PageIndex's chat agent, which finds the answer in a
library of 40 Form 10-K filings with its tools (`browse_documents`, `get_document`, `get_document_structure`,
`get_page_content`) and writes an answer. Only the model behind the agent changes from one configuration to the
next; the library, the questions, the agent and its settings stay the same.

## Corpus and library

- **Corpus**: the five most recent annual reports on Form 10-K of eight companies (Apple, Berkshire Hathaway,
  Boeing, ExxonMobil, JPMorgan Chase, NVIDIA, Pfizer, Walmart), 40 PDFs with 7,318 pages, as each company's
  investor-relations site serves them, exhibits included. `corpus/manifest.json` gives each file's source URL,
  EDGAR accession number, page count and SHA-256; `corpus/fetch.py` downloads and checks them.
- **Library**: `library-w70/`, built once with PageIndex 0.4.4 (`index.py`): a tree per filing, indexed by GPT-6
  Luna, node summaries capped at 70 words, the SDK's other settings at their defaults. Every configuration answers
  from this same library, and every run records its SHA-256. Indexing cost is not part of any result.

## Questions

100 questions in three types, each naming the company and fiscal year but never a section, note, table or page:

| Type | Questions | Asks for |
|---|---:|---|
| SET, open set | 52 | Every item of one kind (each amount, term, condition, party, example or consequence) the filing gives about one clearly scoped matter; 4–6 items, on at least two non-adjacent pages or sections |
| WHY, open causes | 28 | Every cause the filing gives for one change; 2–5 causes, in at least two non-adjacent sections |
| XCO, cross-company open set | 20 | Which of six or eight named companies' filings for one fiscal year meet a precise condition, with a detail for each; 2–5 meet it, at least 2 do not |

The question neither lists the items nor says how many there are, so the agent has to judge for itself when it has
found them all. Each question in `questions/questions.json` holds a reference answer, 2–6 key points and the
evidence: quotes from the filings, with PDF pages, that support the key points.

Questions were written by Claude Opus agents from the filings. Every candidate was answered blind by a second
agent and checked against the filings by a third, who rejected or fixed any whose reference missed an item, included
a doubtful one, or allowed a second reasonable reading. The 100 were drawn per type with a fixed seed from the
verified candidates.

## Configurations

A configuration is a model at one reasoning level (`models.py`): 34 configurations of 19 models, 11 of them at two
or more levels.

- **Route**: OpenRouter, each model pinned to one provider with fallbacks off, at its standard tier (no flex, fast or
  priority endpoints): the model's maker, or a provider at the maker's list price (Together for Muse Spark Open and
  DeepSeek V4.1 Flash). `run.py preflight` checks the route, that calls are billed at the provider's standard-tier
  price, and the reasoning setting (`data/preflight/`).
- **Reasoning levels**: a level other than the default is sent as `reasoning.effort`. At the default level no
  reasoning setting is sent, and the level named is the vendor's default, confirmed by runs with that level set
  explicitly. MiniMax M3.1 Flash runs at max, its default, with max sent. MiMo models have no levels; Muse Wonder's
  default is a level the model picks for itself, labeled "adaptive".

## Runs

- Each configuration answers the 100 questions three times; MiniMax M3.1 Flash at max and xhigh, six times. Every
  question is a fresh conversation.
- Each run's own reference line (`Request reference: r1-…`) is part of every request's system prompt, so runs do
  not share cached conversations.
- Up to 20 agent turns per question. An answer that runs out of turns is asked again from the start with up to 100,
  and that answer stands: the limit belongs to the harness, not the model.
- A transient provider or account error (rate limit, 5xx, dropped connection, OpenRouter's in-flight credit check)
  repeats the call; a question whose attempt still fails is asked again, as is an empty response the provider cut
  off or never processed.
- Graded wrong, not asked again: a model fault (a call to a tool that does not exist, malformed tool input or tool
  call), a conversation that outgrows the context window, and an empty response a provider kept returning.
- `data/runs.jsonl` records each run's environment: PageIndex and LiteLLM versions, turn limit, reference format,
  and the SHA-256 of `questions/questions.json` and of the library, the same for every run.

## Grading

Graders are Claude Opus 5.5 agents, one fresh agent per sheet with no other context (`grading/README.md`), grading
by the rubric in `grading/brief.md`:

- An answer is correct when it covers every key point and makes no claim that contradicts the reference.
- Missing any key point makes it wrong. Extra items are fine on questions that ask for everything of one kind
  (SET, WHY), unless they conflict with the reference; on questions that ask for the items meeting a condition
  (XCO), an item that does not belong is a contradiction.

Sheets are blind: answers labeled A, B, C, … in seeded random order, with no configuration named. A question's
answers go to graders in groups of at most 20, each configuration's runs in different groups. A second grader
re-grades a seeded fifth of every round, and a third grader decides blind on disputed answers; that verdict stands.

Configurations were graded in rounds as they were run (`data/grading/`). Every round after round1 also grades two
of round1's runs blind among the others, DeepSeek V4.1 Flash (high) and Claude Haiku 5.5 (medium), run 1, as
anchors that show it grades on the same scale.

| Round | Answers | Check grader agreed | Adjudicated | Anchors as in the results |
|---|---|---:|---:|---:|
| round1 | 18 models at one level each, 54 runs | 1,076 / 1,080 | 65 | – |
| round2 | ten of those models at a second level, 30 runs | 638 / 640 | 2 | 199 / 200 |
| reask | the 170 answers of round1 and round2 asked again after running out of turns | 52 / 52 | 0 | 77 / 78 |
| round3 | GPT-6.1 Sol (low) and MiniMax M3.1 Flash at five levels, run 1 | 160 / 160 | 0 | 197 / 200 |
| round4 | the same, runs 2–3 | 277 / 280 | 3 | 200 / 200 |
| round5 | MiniMax M3.1 Flash (max) and (xhigh), runs 4–6 | 159 / 160 | 1 | 196 / 200 |

## Cost

- Cost is what OpenRouter billed: each call's `usage.cost`, logged per call in `data/calls/` and checked against
  OpenRouter's own record of the call in `data/generations/`. It includes long-context surcharges and cache
  discounts as billed.
- A run's cost is the sum over its questions of the attempt whose answer stands; attempts retried after an error or
  replaced by an answer asked again are not counted (`results/runs.csv` also gives each run's full bill,
  `billed_usd`). The cost per run in the results is the mean over runs.
- Prices are those of the pinned providers on 2026-10-22 and 2026-10-23, when the runs were made.

## Statistics

Accuracy is the mean over runs of the share of questions answered correctly. A configuration's runs can differ by
several points (Gemini 3.8 Flash (medium): 89, 80, 64), so treat gaps of one or two points as ties:
`python3 results.py compare A B` runs a sign test over the questions where one configuration's share of correct
runs is higher.
