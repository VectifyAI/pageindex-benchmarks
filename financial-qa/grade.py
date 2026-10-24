"""Blind grading: sheets for the graders, and the grades they return.

    python3 grade.py sheets ROUND CONFIGS   # every run of these configurations not graded yet, with the anchors
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
# Kimi K3.1 Pro
ROUNDS = ("round1", "round2", "round3", "round4", "round5", "round6")
# the answers of round1 and round2 that ran out of turns, asked again (run.py); their grades replace the earlier ones
REASK = "reask"
# two runs round1 graded, graded again blind in every later round to show it grades on the same scale
ANCHORS = ("deepseek-v4.1-flash-high r1", "claude-haiku-5.5-medium r1")
CHECK_SHARE = 0.2  # a second grader re-grades this share of each round's sheet lines
ANSWERS_PER_GROUP, ANSWERS_PER_SHEET = 20, 100
# fh-32 asks for every cause the filing gives, so causes beyond the reference are not contradictions
# (grading/brief.md); its contradiction flags are not counted
CONTRADICTIONS_SET_ASIDE = {"fh-32"}


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
    answers invite drift). A configuration's runs go to different groups, so that a group graded more leniently
    cannot hold all of one configuration's runs."""
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
    assert not (GRADES / f"{rnd}_map.json").exists(), f"round {rnd} exists"
    graded = {s for p in GRADES.glob("*_map.json") if "_adjudicate_" not in p.name
              for labels in json.loads(p.read_text()).values() for s in labels.values()}
    systems = sorted({f"{c} r{r}" for c in configs for r in runs_of(c)} - graded) + [f"anchor {a}" for a in ANCHORS]
    rows, blind, lines = rows_of(systems), {}, []
    for q in questions():
        groups = split_answers(rnd, q["id"], systems)
        for g, members in enumerate(groups, 1):
            item = q["id"] if len(groups) == 1 else f"{q['id']}~{g}"
            order = random.Random(f"blind-{rnd}-{item}").sample(members, len(members))
            blind[item] = {chr(65 + i): s for i, s in enumerate(order)}
            lines.append(sheet_line(item, q, blind[item], rows))
    check = random.Random(f"check-{rnd}").sample(lines, round(CHECK_SHARE * len(lines)))
    n, m = write_sheets(rnd, lines), write_sheets(f"{rnd}_check", check)
    (GRADES / f"{rnd}_map.json").write_text(json.dumps(blind, indent=1))
    print(f"{len(systems)} runs ({len(ANCHORS)} anchors), {len(lines)} sheet lines: {n} sheets, {m} check sheets")


def load(rnd, kind=""):
    """(question id, system) -> correct, from a round's grades: "" the first grader's, "_check" the check
    grader's, "_adjudicate" the third grader's. Correct = every key point covered, no contradiction, an answer
    given."""
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
                out[key] = (all(x["covered"]) and (not x["contradiction"] or qid in CONTRADICTIONS_SET_ASIDE)
                            and bool((rows[key].get("answer") or "").strip()))
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
    return out | {k: v for k, v in round_grades(REASK).items() if k in out}


def adjudication_sheets(rnd):
    """Sheets of the answers whose check grade differs from the first grade, for a third grader who sees neither."""
    assert not list(GRADES.glob(f"{rnd}_adjudicate_grades_*.jsonl")), f"round {rnd} is adjudicated"
    first, check = load(rnd), load(rnd, "_check")
    by_q = {}
    for qid, s in sorted(k for k in check if check[k] != first[k]):
        by_q.setdefault(qid, []).append(s)
    qs, rows = {q["id"]: q for q in questions()}, rows_of({s for v in by_q.values() for s in v})
    blind = {qid: {chr(65 + i): s for i, s in enumerate(random.Random(f"adjudicate-{rnd}-{qid}").sample(v, len(v)))}
             for qid, v in by_q.items()}
    n = write_sheets(f"{rnd}_adjudicate", [sheet_line(qid, qs[qid], blind[qid], rows) for qid in blind])
    (GRADES / f"{rnd}_adjudicate_map.json").write_text(json.dumps(blind, indent=1))
    print(f"{sum(map(len, blind.values()))} disputed answers in {len(blind)} questions, {n} sheets")


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
    {"sheets": lambda: sheets(rnd, configs[0].split(",")), "adjudicate": lambda: adjudication_sheets(rnd),
     "report": lambda: report(rnd)}[stage]()
