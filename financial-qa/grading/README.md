# Graders

Every grade in `data/grading/` comes from Claude Opus 5.5 (`claude-opus-5-5`): one fresh session per sheet, sharing
no context with any other.

## What a grader sees

- `grading/brief.md`, the rubric exactly as the graders received it, and one sheet from `grade.py sheets` or
  `grade.py adjudicate`.
- A sheet holds questions, reference answers, key points and answers labeled A, B, C, …: no configuration named,
  answers in seeded random order. The label-to-answer map stays in `data/grading/<round>_map.json`.
- The instruction to follow the brief exactly and return one JSON line per sheet line, in sheet order, keeping each
  "id" exactly as given and grading every label, without opening any other file or searching the web.

## Checks

- `grade.py` checks every grade file against its map before use: every line of the map graded (by the first and
  the third grader), every label of each line, one boolean per key point.
- A second grader re-grades a seeded fifth of each round's sheet lines (`<round>_check_grades_<n>.jsonl`).
- A third grader re-grades blind the answers `grade.py adjudicate` picks, those whose two grades differ, seeing
  neither verdict; its verdict stands (`<round>_adjudicate_map.json`, `<round>_adjudicate_grades_<n>.jsonl`).

## To grade new runs

1. `python3 grade.py sheets <round> <config,...>` writes the sheets to `sheets/` and the map to `data/grading/`.
2. Give each sheet and the brief to a grader with the instruction above; its grades go to
   `data/grading/<round>_grades_<n>.jsonl` for `sheets/<round>_<n>.jsonl` and to `<round>_check_grades_<n>.jsonl`
   for `sheets/<round>_check_<n>.jsonl`.
3. `python3 grade.py adjudicate <round>`, and grade its sheets the same way into `<round>_adjudicate_grades_<n>.jsonl`.
4. `python3 grade.py report <round>` shows the round's accuracy per run, the check grader's agreement and the
   anchors; add the round to `ROUNDS` in `grade.py` to put it in the results.

Any model can grade; results graded by another one are not directly comparable with these.
