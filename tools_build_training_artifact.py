import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRAINING = ROOT / "training"
ARTIFACT = ROOT / "ai_engineer_training.html"
TRACKS_FILE = TRAINING / "tracks.json"

FILE_ORDER = ["quiz_core.json", "quiz_mid_senior.json", "faq_core.json", "faq_mid_senior.json"]


def ordered_sources():
    known = [TRAINING / name for name in FILE_ORDER if (TRAINING / name).exists()]
    rest = sorted(
        p for p in TRAINING.glob("*.json")
        if p.name not in FILE_ORDER and p.name != TRACKS_FILE.name
    )
    return known + rest


def load_tracks():
    if not TRACKS_FILE.exists():
        raise SystemExit(f"нет файла треков: {TRACKS_FILE}")
    data = json.loads(TRACKS_FILE.read_text(encoding="utf-8"))
    tracks = sorted(data["tracks"], key=lambda t: t["order"])
    return tracks, data["assignment"]


def collect(sources, assignment):
    blocks, questions, sections = [], [], []
    for path in sources:
        data = json.loads(path.read_text(encoding="utf-8"))
        blocks += data.get("blocks", [])
        questions += data.get("questions", [])
        sections += data.get("sections", [])
    missing = sorted({b["id"] for b in blocks} - set(assignment))
    if missing:
        raise SystemExit(f"блокам не назначен трек в tracks.json: {missing}")
    for b in blocks:
        b["track"] = assignment[b["id"]]
    for s in sections:
        if s["id"] in assignment:
            s["track"] = assignment[s["id"]]
    return blocks, questions, sections


def replace_literal(text, varname, obj):
    lines = text.split("\n")
    head = f"const {varname} = {{"
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(head))
    except StopIteration:
        return text, False
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "};")
    literal = f"const {varname} = " + json.dumps(obj, ensure_ascii=False, indent=2) + ";"
    return "\n".join(lines[:start] + literal.split("\n") + lines[end + 1:]), True


def main():
    sources = ordered_sources()
    if not sources:
        raise SystemExit(f"нет источников содержания в {TRAINING}")
    tracks, assignment = load_tracks()
    blocks, questions, sections = collect(sources, assignment)

    if not ARTIFACT.exists():
        raise SystemExit(f"нет артефакта: {ARTIFACT}")
    page = ARTIFACT.read_text(encoding="utf-8")
    original = page

    page, ok_quiz = replace_literal(page, "QUIZ_DATA", {"blocks": blocks, "questions": questions})
    if not ok_quiz:
        raise SystemExit("в артефакте не найден литерал QUIZ_DATA")
    page, ok_faq = replace_literal(page, "FAQ_DATA", {"sections": sections})
    if not ok_faq:
        raise SystemExit("в артефакте не найден литерал FAQ_DATA")
    page, ok_tracks = replace_literal(page, "TRACKS", {"tracks": tracks})

    terms = sum(len(s.get("terms", [])) for s in sections)
    kicker = f"ПЕРСОНАЛЬНАЯ ПРОГРАММА · {len(questions)} ВОПРОСОВ · {len(sections)} РАЗДЕЛОВ · {terms} ТЕРМИНОВ"
    page = re.sub(
        r'(<div class="brand-kicker">)[^<]*(</div>)',
        lambda m: m.group(1) + kicker + m.group(2),
        page,
        count=1,
    )
    page = re.sub(r'"найдено \d+ терминов"', f'"найдено {terms} терминов"', page)

    changed = page != original
    if changed:
        ARTIFACT.write_text(page, encoding="utf-8")

    print(f"источников: {len(sources)} ({', '.join(p.name for p in sources)})")
    print(f"блоков: {len(blocks)} · вопросов: {len(questions)} · разделов: {len(sections)} · терминов: {terms}")
    print(f"треков: {len(tracks)} · литерал TRACKS в HTML: {'обновлён' if ok_tracks else 'отсутствует, пропущен'}")
    print(f"артефакт: {'перезаписан' if changed else 'без изменений'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
