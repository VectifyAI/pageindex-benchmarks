# Data

Everything the results are computed from, one file per run where it applies: `<config>_run<n>.jsonl`, with
`<config>` a key of `models.py`. JSON Lines, appended in the order things happened.

| Path | One line per | Written by |
|---|---|---|
| `answers/` | answer: question `id`, `answer`, `started`, `seconds`, tokens; or how it ended without one | `run.py answer` |
| `calls/` | model call: question `id`, run `ref`, `turn`, tokens, `cost`, `gen_id`, tool calls, text | `run.py answer` |
| `generations/` | OpenRouter's record of a call (`/api/v1/generation`), matched by `gen_id` | `run.py generations` |
| `runs.jsonl` | pass of a run: calls, USD billed, route, provider, reasoning sent, environment | `run.py answer` |
| `preflight/` | configuration (one JSON file): route, provider, prices, reasoning levels, probe calls | `run.py preflight` |
| `grading/` | round: map and grades (below) | `grade.py`, graders |

## answers

- A question can have several rows: an attempt that ended in an error (`error`) is retried, and an answer that ran
  out of 20 turns (`max_turns: true`) is followed by one asked again with up to 100 (`max_turns_limit: 100`). The
  last row stands, except that a model fault (`model_error`) is final. Other endings: `context_limit` (the
  conversation outgrew the model's context window).
- `ref` is the run's reference line; `input_tokens`, `cached_tokens`, `output_tokens` and `usage` are the token
  counts the SDK reported for the attempt.

## calls and generations

- A call belongs to the attempt whose time window (from `started` to 5 s after `started + seconds` of its answer
  row) holds its `start`; `costs()` in `results.py` sums the calls of the attempts that stand.
- `cost` is OpenRouter's `usage.cost` for the call; the generation record's `total_cost` matches it for every call
  that has one. The account's `workspace_id` and `app_id` are removed from the records.

## runs.jsonl

- One line per pass of `run.py answer`: the run itself (`max_turns` 20 in `env`) and the pass asking again the
  questions that ran out of turns (`reask` lists them, `max_turns` 100). A resumed run adds a line; `errors_left`
  counts the questions still failing when a pass ended, which the next pass retried.
- `usd` sums every call of the pass, retried attempts included, so it can exceed the cost in the results.
- `reasoning` is the `reasoning.effort` sent; `null` means none was sent and the model ran at its default level,
  which the configuration's name gives (`models.py`).
- `env.questions_sha256` is the SHA-256 of `questions/questions.json`; `env.library_sha256` hashes the library's
  files (`run.py environment`).

## questions

`questions/questions.json`, one object per question: `id`, `type` and `type_name`, `companies`, `files`, `question`,
the reference `answer`, `key_points`, `evidence` (file, PDF page, quote), `calculation` (how a figure was checked,
where one was) and `candidate_id` (the question's id among the candidates it was drawn from).

## grading

Per round (`grade.py ROUNDS`, METHOD.md "Grading"):

- `<round>_map.json`: sheet line id (`fh-07`, or `fh-07~2` for a question split into groups) -> label -> answer,
  `<config> r<n>` or `anchor <config> r<n>`.
- `<round>_grades_<n>.jsonl`: per sheet line, per label, `covered` (one boolean per key point) and
  `contradiction`. `<round>_check_grades_<n>.jsonl`: the check grader's, same map.
- `<round>_adjudicate_map.json` and `<round>_adjudicate_grades_<n>.jsonl`: the third grader's, on the answers the
  first two disagreed on.

The grade files hold the configurations in the results, so a line's labels can skip letters.
