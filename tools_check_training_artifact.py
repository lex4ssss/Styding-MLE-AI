import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRAINING = ROOT / "training"
ARTIFACT = ROOT / "ai_engineer_training.html"
MAX_KB = 16 * 1024


def fail(problems):
    for p in problems:
        print("FAIL:", p)
    return 1


def load_sources():
    blocks, questions, sections = [], [], []
    for path in sorted(TRAINING.glob("quiz_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        blocks += data.get("blocks", [])
        questions += data.get("questions", [])
    for path in sorted(TRAINING.glob("faq_*.json")):
        sections += json.loads(path.read_text(encoding="utf-8")).get("sections", [])
    tracks = json.loads((TRAINING / "tracks.json").read_text(encoding="utf-8"))
    return blocks, questions, sections, tracks


def load_page():
    page = ARTIFACT.read_text(encoding="utf-8")
    head = "const DATA = "
    start = page.find(head)
    if start < 0:
        raise SystemExit("в странице не найден литерал DATA")
    start += len(head)
    end = page.find(";\n</script>", start)
    return page, json.loads(page[start:end])


def main():
    problems = []
    blocks, questions, sections, tracks = load_sources()
    page, data = load_page()

    if len(data["quiz"]["blocks"]) != len(blocks):
        problems.append(f"блоков в странице {len(data['quiz']['blocks'])}, в источниках {len(blocks)}")
    if len(data["quiz"]["questions"]) != len(questions):
        problems.append(f"вопросов в странице {len(data['quiz']['questions'])}, в источниках {len(questions)}")
    if len(data["faq"]["sections"]) != len(sections):
        problems.append(f"разделов в странице {len(data['faq']['sections'])}, в источниках {len(sections)}")

    seen = {}
    for q in data["quiz"]["questions"]:
        if len(q["options"]) != 4:
            problems.append(f"не четыре варианта: {q['q'][:60]}")
        if not 0 <= q["correct"] < len(q["options"]):
            problems.append(f"неверный индекс ответа: {q['q'][:60]}")
        if not q.get("why"):
            problems.append(f"нет разбора: {q['q'][:60]}")
        if q["q"] in seen:
            problems.append(f"дубль вопроса: {q['q'][:60]}")
        seen[q["q"]] = True

    ids = {b["id"] for b in data["quiz"]["blocks"]}
    for block_id in sorted(ids):
        if block_id not in tracks["assignment"]:
            problems.append(f"блоку не назначен трек: {block_id}")
        if not any(q["block"] == block_id for q in data["quiz"]["questions"]):
            problems.append(f"блок без вопросов: {block_id}")

    for s in data["faq"]["sections"]:
        for key in ("lead", "terms", "pitfalls", "drill"):
            if not s.get(key):
                problems.append(f"раздел {s['id']}: пустое поле {key}")
        for t in s.get("terms", []):
            if not t.get("d") or not t.get("m"):
                problems.append(f"раздел {s['id']}: термин без описания — {t['t']}")
        for r in s.get("resources", []):
            if not re.match(r"^https://", r["u"]):
                problems.append(f"раздел {s['id']}: ссылка не по https — {r['u']}")

    if "__DATA__" in page:
        problems.append("страница не собрана: остался placeholder __DATA__")
    for token in ('id="app"', 'id="counters"', "prefers-color-scheme: dark", "prefers-reduced-motion"):
        if token not in page:
            problems.append(f"в странице нет обязательного фрагмента: {token}")

    size_kb = len(page.encode("utf-8")) / 1024
    if size_kb > MAX_KB:
        problems.append(f"страница больше лимита: {round(size_kb, 1)} kb")

    if problems:
        return fail(problems)

    terms = sum(len(s.get("terms", [])) for s in data["faq"]["sections"])
    print(f"OK · блоков {len(ids)} · вопросов {len(data['quiz']['questions'])} · разделов {len(data['faq']['sections'])} · терминов {terms}")
    print(f"OK · треков {len(tracks['tracks'])} · размер {round(size_kb, 1)} kb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
