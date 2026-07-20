from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_old_brand_is_absent_from_project_text() -> None:
    forbidden = ("JA" + "NUS", "Sanjiv" + "GPT", "Sanjiv" + " AI")
    included = [ROOT / "AGENTS.md", ROOT / ".env.example"]
    included.extend((ROOT / "docs").glob("*.md"))
    included.extend((ROOT / "services").rglob("*.py"))
    included.extend((ROOT / "apps").rglob("*.tsx"))
    for path in included:
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in text, f"forbidden brand remains in {path}"
