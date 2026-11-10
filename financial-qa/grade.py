"""Blind grading: sheets for the graders, and the grades they return.

    python3 grade.py sheets ROUND CONFIGS   # every run of these configurations not graded yet, with the anchors
    python3 grade.py regrade ROUND          # every answer in the results to the question REGRADES gives the round
    python3 grade.py adjudicate ROUND       # the answers the first and the check grader disagree on, for a third
    python3 grade.py report ROUND           # accuracy per run, the check grader's agreement, the anchors

Graders follow grading/brief.md; grading/README.md says who they are and how each is run. Sheets go to sheets/
(answers labeled A, B, C, ...; no configuration names), the label-to-answer map to data/grading/<round>_map.json,
and graders write data/grading/<round>_grades_<n>.jsonl and <round>_check_grades_<n>.jsonl (and
<round>_adjudicate_grades_<n>.jsonl for the adjudication sheets).
"""
import json
import math
import pathlib
import random
import sys

from models import CONFIGS

HERE = pathlib.Path(__file__).resolve().parent
DATA, GRADES, SHEETS = HERE / "data", HERE / "data" / "grading", HERE / "sheets"
# the rounds behind the results, in the order graded (METHOD.md, "Grading"): round1 18 models at one level each,
# round2 ten of those at a second level, round3-5 GPT-6.1 Sol (low) and MiniMax M3.1 Flash at five levels, round6
# Kimi K3.1 Pro, round7 GPT-6.1 Terra (medium), round8-9 GPT-6.1 Terra (max), round10-11 Hy4,
# round12-13 Muse Ember
ROUNDS = ("round1", "round2", "round3", "round4", "round5", "round6", "round7", "round8", "round9", "round10",
          "round11", "round12", "round13")
# the answers of round1 and round2 that ran out of turns, asked again (run.py); their grades replace the earlier ones
REASK = "reask"
# questions whose every answer in the results was graded again in one round (`regrade`), because graders of
# different rounds judged its extra causes differently; these grades replace the earlier ones
REGRADES = {"fh32": "fh-32"}
# settled readings of key points graders split on (ruled 2026-10-29, when these questions were first graded),
# applied to every round so that every round reads them alike: key points whose wording carries a description the
# filing gives in passing; leaving it out names nothing else in the filing: question -> [(key point index, text of
# that key point, the answers that cover it: any of these lists, each of whose texts the answer gives, in lower
# case)]. fh-21: the notes' coupons and the yen note's principal (an amount with its maturity date identifies the
# note), as graders read it from round4.
KEY_POINT_RULINGS = {
    "fh-21": [(2, "3.300% notes", [["1,500", "april 22"], ["1.5 billion", "april 22"]]),
              (3, "2.850% notes", [["990", "july 8"]]), (4, "0.298% notes", [["253", "july 18"]]),
              (5, "2.650% notes", [["630", "december 15"]])],
}
# two runs round1 graded, graded again blind in every later round to show it grades on the same scale
ANCHORS = ("deepseek-v4.1-flash-high r1", "claude-haiku-5.5-medium r1")
CHECK_SHARE = 1.0  # a second grader re-grades this share of each round's sheet lines: all from round10, a fifth before
ANSWERS_PER_GROUP, ANSWERS_PER_SHEET = 20, 100


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def questions():
    return json.loads((HERE / "questions" / "questions.json").read_text())


def runs_of(config):
    return sorted(int(p.stem.rsplit("_run", 1)[1]) for p in (DATA / "answers").glob(f"{config}_run*.jsonl"))


def answer_rows(config, run):
    """question id -> the row that stands: the last one, except that a model fault is final (METHOD.md)."""
    out = {}
    for row in read(DATA / "answers" / f"{config}_run{run}.jsonl"):
        if not (row["id"] in out and "model_error" in out[row["id"]]):
            out[row["id"]] = row
    return out


def rows_of(systems):
    """(question id, system) -> standing row, for systems '<config> r<run>' or 'anchor <config> r<run>'."""
    out = {}
    for s in systems:
        config, run = s.removeprefix("anchor ").rsplit(" r", 1)
        out |= {(qid, s): row for qid, row in answer_rows(config, int(run)).items()}
    return out


def blind_map(rnd, kind=""):
    return json.loads((GRADES / f"{rnd}{kind}_map.json").read_text())


def split_answers(rnd, qid, systems):
    """A question's answers in groups of at most ANSWERS_PER_GROUP, graded one group at a time (long lists of
    answers invite drift). A configuration's runs go to different groups as far as the number of groups allows, so
    that a group graded more leniently cannot hold all of one configuration's runs unless it is the only group."""
    n = math.ceil(len(systems) / ANSWERS_PER_GROUP)
    by_config = {}
    for s in systems:
        by_config.setdefault(s.rsplit(" r", 1)[0], []).append(s)
    groups, dealt = [[] for _ in range(n)], 0
    for config in random.Random(f"split-{rnd}-{qid}").sample(sorted(by_config), len(by_config)):
        for s in sorted(by_config[config]):
            groups[dealt % n].append(s)
            dealt += 1
    return groups


def pack(lines):
    """Whole sheet lines into sheets of about ANSWERS_PER_SHEET answers."""
    parts = [[]]
    for line in lines:
        if parts[-1] and sum(len(x["answers"]) for x in parts[-1]) + len(line["answers"]) > ANSWERS_PER_SHEET:
            parts.append([])
        parts[-1].append(line)
    return parts if lines else []


def sheet_line(item, q, labels, rows):
    return {"id": item, "question": q["question"], "reference": q["answer"], "key_points": q["key_points"],
            "answers": [{"label": lab, "answer": rows[(q["id"], s)].get("answer") or "(no answer)"}
                        for lab, s in labels.items()]}


def write_sheets(name, lines):
    SHEETS.mkdir(exist_ok=True)
    for n, part in enumerate(pack(lines), 1):
        (SHEETS / f"{name}_{n}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in part))
    return len(pack(lines))


def sheets(rnd, configs):
    """Blind sheets of every run of these configurations that no round has graded yet, the anchors mixed in: per
    question, groups of at most ANSWERS_PER_GROUP answers in seeded random order, one sheet line per group; and a
    seeded CHECK_SHARE of the lines for a check grader."""
    graded = {s for p in GRADES.glob("*_map.json") if "_adjudicate_" not in p.name
              for labels in json.loads(p.read_text()).values() for s in labels.values()}
    systems = sorted({f"{c} r{r}" for c in configs for r in runs_of(c)} - graded) + [f"anchor {a}" for a in ANCHORS]
    write_round(rnd, systems, questions(), CHECK_SHARE)


def regrade(rnd, qid):
    """Blind sheets of every answer to one question in the results, every line for the check grader too; grades()
    puts the round's grades in place of the earlier ones (REGRADES)."""
    systems = sorted({s for q, s in grades() if q == qid})
    write_round(rnd, systems, [q for q in questions() if q["id"] == qid], 1.0)


def write_round(rnd, systems, qs, check_share):
    """A round's sheets and map: per question, groups of at most ANSWERS_PER_GROUP answers in seeded random order,
    one sheet line per group; and a seeded share of the lines for a check grader."""
    assert not (GRADES / f"{rnd}_map.json").exists(), f"round {rnd} exists"
    rows, blind, lines = rows_of(systems), {}, []
    for q in qs:
        groups = split_answers(rnd, q["id"], systems)
        for g, members in enumerate(groups, 1):
            item = q["id"] if len(groups) == 1 else f"{q['id']}~{g}"
            order = random.Random(f"blind-{rnd}-{item}").sample(members, len(members))
            blind[item] = {chr(65 + i): s for i, s in enumerate(order)}
            lines.append(sheet_line(item, q, blind[item], rows))
    check = random.Random(f"check-{rnd}").sample(lines, round(check_share * len(lines)))
    n, m = write_sheets(rnd, lines), write_sheets(f"{rnd}_check", check)
    (GRADES / f"{rnd}_map.json").write_text(json.dumps(blind, indent=1))
    print(f"{len(systems)} runs, {len(lines)} sheet lines: {n} sheets, {m} check sheets")


def correct(q, x, answer):
    """Every key point covered and no contradiction, as the grader marked them with KEY_POINT_RULINGS applied, and
    an answer given."""
    covered, text = list(x["covered"]), answer.lower()
    for k, point, readings in KEY_POINT_RULINGS.get(q["id"], ()):
        assert point in q["key_points"][k], f"{q['id']}: KEY_POINT_RULINGS text"
        covered[k] = covered[k] or any(all(t in text for t in r) for r in readings)
    return all(covered) and not x["contradiction"] and bool(answer.strip())


def load(rnd, kind=""):
    """(question id, system) -> correct, from a round's grades: "" the first grader's, "_check" the check
    grader's, "_adjudicate" the third grader's."""
    blind, questions_by_id = blind_map(rnd, "_adjudicate" if kind == "_adjudicate" else ""), {q["id"]: q for q in questions()}
    files = sorted(GRADES.glob(f"{rnd}{kind}_grades_*.jsonl"))
    rows, out, seen = rows_of({s for labels in blind.values() for s in labels.values()}), {}, set()
    for path in files:
        for g in read(path):
            seen.add(g["id"])
            qid = g["id"].split("~")[0]  # a question split into groups has lines <id>~1, <id>~2, ...
            assert {x["label"] for x in g["grades"]} == set(blind[g["id"]]), f"{path.name} {g['id']}: labels"
            for x in g["grades"]:
                assert len(x["covered"]) == len(questions_by_id[qid]["key_points"]), f"{path.name} {g['id']} {x['label']}"
                key = (qid, blind[g["id"]][x["label"]])
                out[key] = correct(questions_by_id[qid], x, rows[key].get("answer") or "")
    # the first and the third grader grade every line of their map; the check grader a sample of it
    assert kind == "_check" or not files or seen == set(blind), f"{rnd}{kind}: lines not graded {sorted(set(blind) - seen)[:5]}"
    return out


def round_grades(rnd):
    """A round's grades after adjudication: the third grader's verdict stands where it was asked."""
    out = load(rnd)
    if list(GRADES.glob(f"{rnd}_adjudicate_grades_*.jsonl")):
        out |= load(rnd, "_adjudicate")
    return out


def grades():
    """(question id, '<config> r<run>') -> correct, for every run behind the results."""
    out = {}
    for rnd in ROUNDS:
        out |= {k: v for k, v in round_grades(rnd).items() if not k[1].startswith("anchor ")}
    for rnd in (REASK, *(r for r in REGRADES if (GRADES / f"{r}_map.json").exists())):
        out |= {k: v for k, v in round_grades(rnd).items() if k in out}
    return out


def adjudication_sheets(rnd):
    """Sheets of the answers whose check grade differs from the first grade, for a third grader who sees neither."""
    assert not list(GRADES.glob(f"{rnd}_adjudicate_grades_*.jsonl")), f"round {rnd} is adjudicated"
    first, check = load(rnd), load(rnd, "_check")
    by_q = {}
    for qid, s in sorted(k for k in check if check[k] != first[k]):
        by_q.setdefault(qid, []).append(s)
    qs, rows, blind = {q["id"]: q for q in questions()}, rows_of({s for v in by_q.values() for s in v}), {}
    for qid, v in by_q.items():  # more than ANSWERS_PER_GROUP disputes split into groups as in sheets()
        groups = split_answers(f"{rnd}_adjudicate", qid, v) if len(v) > ANSWERS_PER_GROUP else [v]
        for g, members in enumerate(groups, 1):
            item = qid if len(groups) == 1 else f"{qid}~{g}"
            order = random.Random(f"adjudicate-{rnd}-{item}").sample(members, len(members))
            blind[item] = {chr(65 + i): s for i, s in enumerate(order)}
    n = write_sheets(f"{rnd}_adjudicate", [sheet_line(i, qs[i.split("~")[0]], blind[i], rows) for i in blind])
    (GRADES / f"{rnd}_adjudicate_map.json").write_text(json.dumps(blind, indent=1))
    print(f"{sum(map(len, blind.values()))} disputed answers in {len(by_q)} questions, {n} sheets")


def report(rnd):
    first, final = load(rnd), round_grades(rnd)
    for s in sorted({s for _, s in final}):
        mine = [v for (_, system), v in final.items() if system == s]
        print(f"{s:36}{sum(mine):>4} / {len(mine)}")
    if list(GRADES.glob(f"{rnd}_check_grades_*.jsonl")):
        check = load(rnd, "_check")
        print(f"check grader agrees with the first grader on {sum(check[k] == first[k] for k in check)}/{len(check)} answers")
    if list(GRADES.glob(f"{rnd}_adjudicate_grades_*.jsonl")):
        adjudicated = load(rnd, "_adjudicate")
        print(f"third grader: {len(adjudicated)} disputed answers, {sum(adjudicated.values())} correct")
    anchors = [k for k in final if k[1].startswith("anchor ")]
    if anchors:
        published = grades()
        print(f"anchors: {sum(final[k] == published[(k[0], k[1][len('anchor '):])] for k in anchors)}/{len(anchors)} "
              f"answers graded as in the results")


if __name__ == "__main__":
    stage, rnd, *configs = sys.argv[1:]
    {"sheets": lambda: sheets(rnd, configs[0].split(",")), "regrade": lambda: regrade(rnd, REGRADES[rnd]),
     "adjudicate": lambda: adjudication_sheets(rnd), "report": lambda: report(rnd)}[stage]()
