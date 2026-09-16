import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRAINING = ROOT / "training"
TEMPLATE = ROOT / "template.html"
ARTIFACT = ROOT / "ai_engineer_training.html"

QUIZ_FILES = ["quiz_core.json", "quiz_mid_senior.json", "quiz_senior_agents.json"]
FAQ_FILES = ["faq_core.json", "faq_mid_senior.json", "faq_senior_agents.json"]
ORDER = "ABCDEFGHIJKLMNOPQRSTUVWZ"


def load(name):
    path = TRAINING / name
    if not path.exists():
        raise SystemExit(f"нет источника: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def rank(item):
    return ORDER.index(item["id"]) if item["id"] in ORDER else len(ORDER)


def main():
    blocks, questions, sections = [], [], []
    for name in QUIZ_FILES:
        data = load(name)
        blocks += data.get("blocks", [])
        questions += data.get("questions", [])
    for name in FAQ_FILES:
        sections += load(name).get("sections", [])

    tracks = load("tracks.json")
    library = load("library.json")

    orphans = sorted({b["id"] for b in blocks} - set(tracks["assignment"]))
    if orphans:
        raise SystemExit(f"блокам не назначен трек в tracks.json: {orphans}")

    known = {b["id"] for b in blocks}
    stray = sorted({q["block"] for q in questions} - known)
    if stray:
        raise SystemExit(f"вопросы ссылаются на несуществующие блоки: {stray}")

    blocks.sort(key=rank)
    sections.sort(key=rank)
    tracks["tracks"].sort(key=lambda t: t["order"])

    if not TEMPLATE.exists():
        raise SystemExit(f"нет шаблона: {TEMPLATE}")

    payload = {
        "quiz": {"blocks": blocks, "questions": questions},
        "faq": {"sections": sections},
        "library": library,
        "tracks": tracks,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
    page = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", blob)

    previous = ARTIFACT.read_text(encoding="utf-8") if ARTIFACT.exists() else ""
    if page != previous:
        ARTIFACT.write_text(page, encoding="utf-8")

    terms = sum(len(s.get("terms", [])) for s in sections)
    materials = {r["u"] for s in sections for r in s.get("resources", [])}
    materials |= {i["u"] for stage in library.get("roadmap", []) for i in stage["items"]}
    materials |= {i["u"] for g in library.get("catalog", {}).get("groups", []) for i in g["items"]}

    print(f"блоков: {len(blocks)} · вопросов: {len(questions)} · разделов: {len(sections)} · терминов: {terms}")
    print(f"треков: {len(tracks['tracks'])} · материалов: {len(materials)}")
    print(f"страница: {'перезаписана' if page != previous else 'без изменений'}, {round(len(page.encode('utf-8')) / 1024, 1)} kb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
