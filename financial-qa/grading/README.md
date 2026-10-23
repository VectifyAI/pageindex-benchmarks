# Graders

Every grade in `data/grading/` comes from a Claude Opus 5.5 (`claude-opus-5-5`) agent run from Claude Code: one
fresh agent per sheet, sharing no context with any other.

## What a grader sees

- `grading/brief.md`, the rubric exactly as the graders received it, and one sheet from `grade.py sheets` or
  `grade.py adjudicate`.
- A sheet holds questions, reference answers, key points and answers labeled A, B, C, …: no configuration named,
  answers in seeded random order. The label-to-answer map stays in `data/grading/<round>_map.json`.
- This prompt, with the paths filled in:

  > You are one of several blind graders for a benchmark of answers about companies' annual reports. Read the
  > grading instructions at `<brief>` and follow them exactly. The sheet to grade is `<sheet>`. Write your grades
  > with the Write tool to `<grades>`: one JSON line per sheet line, in sheet order, keeping each "id" exactly as
  > given (they end in ~1, ~2 or ~3) and grading every label. Do not open any other file and do not search the
  > web. Reply with only the number of lines graded.

  The note on `~1, ~2 or ~3` follows the round's sheets, and is left out where questions are not split.

## Checks

- `grade.py` checks every grade file against its map before use: every line of the map graded (by the first and
  the third grader), every label of each line, one boolean per key point.
- A second grader re-grades a seeded fifth of each round's sheet lines (`<round>_check_grades_<n>.jsonl`).
- A third grader re-grades blind the answers `grade.py adjudicate` picks, those whose two grades differ, seeing
  neither verdict; its verdict stands (`<round>_adjudicate_map.json`, `<round>_adjudicate_grades_<n>.jsonl`).

## To grade new runs

1. `python3 grade.py sheets <round> <config,...>` writes the sheets to `sheets/` and the map to `data/grading/`.
2. Give each sheet, the brief and the prompt above to a grader, which writes `data/grading/<round>_grades_<n>.jsonl`
   for `sheets/<round>_<n>.jsonl` and `<round>_check_grades_<n>.jsonl` for `sheets/<round>_check_<n>.jsonl`.
3. `python3 grade.py adjudicate <round>`, and grade its sheets the same way into `<round>_adjudicate_grades_<n>.jsonl`.
4. `python3 grade.py report <round>` shows the round's accuracy per run, the check grader's agreement and the
   anchors; add the round to `ROUNDS` in `grade.py` to put it in the results.

Any model can grade; results graded by another one are not directly comparable with these.
