# Grader brief

You are one of several blind graders. Read the sheet file you are given: one JSON object per
line, each a question with `id`, `question`, `reference`, `key_points` and several `answers`
labeled A, B, C and so on. Grade every answer of every question with the rubric below. A question with many
answers is split over several lines whose `id` ends in `~1`, `~2`, ...: grade each line on its own, with
the same standard, and keep the `id` exactly as given. Do not
open any other file and do not search the web: grade only against the reference and key points.

Write your grades to the output file you are given, one JSON line per question, in sheet order:

{"id": "fb-01", "grades": [{"label": "A", "covered": [true, false], "contradiction": false}, ...]}

Every label of every question, and "covered" has one boolean per key point, in order. When done,
reply with only the number of questions graded.

## Rubric

The questions are about companies' annual reports on Form 10-K. Judge each answer only against
the reference and the key points. The question explicitly asks for every item the key points
require.

Covering each key point
- Go through the key points in order and decide for each whether the answer states it.
- Numbers may differ only by rounding, and equivalent wording counts. Where the question says
  "approximately", accept figures within about 2% of the key point. For a calculated figure,
  accept a result within one unit of the last digit the question asks for.
- A key point is NOT covered if the answer only hints at it, hedges between alternatives, or
  gives a materially different number.
- Every part of a key point outside parentheses must be stated. Parenthetical extras are
  required only if the question explicitly asks for them.
- A key point joining two facts with "and" needs both.
- When a key point is a list ("all of ..."), it is covered only if every item is named.

Contradictions
- Decide whether the answer makes a claim that contradicts the reference: a wrong figure or
  reason presented as the answer.
- When the question names a company, a fiscal year or a filing, an answer that gives another
  company's figure, another fiscal year's figure, or the same year's figure as restated in a
  different filing, is a contradiction, even if that figure appears in some filing.
- When the question asks for a complete list or for the items that meet a condition, naming an
  item that does not belong is a contradiction.
- When the question asks for everything the filing gives of some kind about a topic (rather than
  for the items that meet a condition), extra items beyond the key points are not contradictions,
  unless they conflict with the reference (a different value for the same item).
- Omissions, "not available" statements and extra correct detail are not contradictions.

General
- Do not reward length, confidence or formatting.
- An answer saying the information is not available covers nothing.
- An answer that is "(no answer)" covers nothing.
- Grade each answer on its own, with the same standard for all of them.
