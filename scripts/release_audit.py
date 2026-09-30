from __future__ import annotations

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    ".env.example",
    ".github/workflows/ci.yml",
    "DEMO_NOTICE.md",
    "PORTABLE_README.md",
    "README.md",
    "docs/DEMO_WALKTHROUGH.md",
    "requirements.lock",
}
FORBIDDEN_NAMES = {".env", ".env.pending", ".DS_Store"}
FORBIDDEN_PARTS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "dist",
    "htmlcov",
    "vendor",
}
TEXT_PATTERNS = {
    "personal macOS path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "personal Windows path": re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\s]+"),
    "known internal cluster reference": re.compile("validation" + "stages", re.I),
    "known internal gateway reference": re.compile("grove" + "-gateway", re.I),
    "credential-like API key": re.compile(
        r"\b(?:pa|sk)-(?!your-key\b)(?!secret-value-for-testing\b)"
        r"(?!saved-key-value-for-testing\b)[A-Za-z0-9_-]{20,}\b"
    ),
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [Path(value) for value in result.stdout.decode().split("\0") if value]


def main() -> None:
    files = tracked_files()
    paths = {path.as_posix() for path in files}
    problems = [f"required release file is missing: {path}" for path in sorted(REQUIRED_FILES - paths)]

    for relative in files:
        value = relative.as_posix()
        if relative.name in FORBIDDEN_NAMES or FORBIDDEN_PARTS.intersection(relative.parts):
            problems.append(f"generated or private path is tracked: {value}")
        if relative.suffix.lower() in {".pdf", ".zip", ".pyc", ".log"}:
            problems.append(f"generated content is tracked: {value}")
        if "uploads" in relative.parts and value != "uploads/.gitkeep":
            problems.append(f"uploaded content is tracked: {value}")

        if value == "scripts/release_audit.py":
            continue
        try:
            contents = (ROOT / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        for label, pattern in TEXT_PATTERNS.items():
            if pattern.search(contents):
                problems.append(f"{label} found in {value}")

    if problems:
        print("Release audit failed:")
        for problem in sorted(set(problems)):
            print(f"- {problem}")
        raise SystemExit(1)

    print(f"Release audit passed for {len(files)} tracked files.")


if __name__ == "__main__":
    main()
