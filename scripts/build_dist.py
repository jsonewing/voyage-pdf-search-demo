from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = ROOT / "dist"
VERSION_FILE = ROOT / "VERSION"


def copy_tree(source: str, package_dir: Path) -> None:
    shutil.copytree(
        ROOT / source,
        package_dir / source,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".DS_Store",
            ".pytest_cache",
        ),
    )


def validate_archive(archive: Path, package_name: str) -> None:
    forbidden_parts = {
        ".env",
        ".env.pending",
        ".venv",
        ".runtime",
        ".pytest_cache",
        "__pycache__",
        "dist",
        "vendor",
    }
    with zipfile.ZipFile(archive) as package_zip:
        bad_member = package_zip.testzip()
        if bad_member:
            raise RuntimeError(f"ZIP verification failed at {bad_member}")
        names = package_zip.namelist()
        if not names or not all(name.startswith(f"{package_name}/") for name in names):
            raise RuntimeError("ZIP does not contain exactly one versioned package root")
        for name in names:
            path = Path(name)
            if forbidden_parts.intersection(path.parts):
                raise RuntimeError(f"Forbidden runtime or secret path included: {name}")
            if path.suffix.lower() in {".pdf", ".zip"}:
                raise RuntimeError(f"Uploaded or generated artifact included: {name}")
            if "uploads" in path.parts and path.name not in {"uploads", ".gitkeep"}:
                raise RuntimeError(f"Uploaded content included: {name}")

        required = {
            f"{package_name}/DEMO_NOTICE.md",
            f"{package_name}/run.sh",
            f"{package_name}/start.command",
            f"{package_name}/README.md",
            f"{package_name}/docs/DEMO_WALKTHROUGH.md",
            f"{package_name}/requirements.lock",
            f"{package_name}/VERSION",
            f"{package_name}/app/main.py",
            f"{package_name}/static/index.html",
            f"{package_name}/uploads/.gitkeep",
        }
        missing = required.difference(names)
        if missing:
            raise RuntimeError(f"ZIP is missing required files: {sorted(missing)}")

        env_path = ROOT / ".env"
        if env_path.exists():
            secret_keys = {"ATLAS_URI", "VOYAGE_API_KEY", "OPENAI_API_KEY"}
            secret_values = []
            for line in env_path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() in secret_keys:
                    secret = value.strip().strip("'\"")
                    if secret:
                        secret_values.append(secret.encode())
            for name in names:
                if name.endswith("/"):
                    continue
                contents = package_zip.read(name)
                if any(secret in contents for secret in secret_values):
                    raise RuntimeError(f"A configured credential was found in {name}")


def build() -> tuple[Path, Path]:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"VERSION must use MAJOR.MINOR.PATCH; found {version!r}")

    package_name = f"voyage-pdf-search-portable-v{version}"
    archive = DIST_ROOT / f"{package_name}.zip"
    checksum = DIST_ROOT / f"{archive.name}.sha256"
    DIST_ROOT.mkdir(exist_ok=True)

    for stale in DIST_ROOT.glob("voyage-pdf-search-portable*"):
        if stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()

    with tempfile.TemporaryDirectory(prefix="voyage-pdf-release-") as staging:
        package_dir = Path(staging) / package_name
        package_dir.mkdir()

        copy_tree("app", package_dir)
        copy_tree("docs", package_dir)
        copy_tree("static", package_dir)
        (package_dir / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "setup-python.sh", package_dir / "scripts")

        release_files = (
            "requirements.txt",
            "requirements.lock",
            ".env.example",
            ".gitignore",
            "DEMO_NOTICE.md",
            "VERSION",
            "run.sh",
            "start.sh",
            "start.command",
        )
        for name in release_files:
            shutil.copy2(ROOT / name, package_dir / name)
        shutil.copy2(ROOT / "PORTABLE_README.md", package_dir / "README.md")
        (package_dir / "uploads").mkdir()
        (package_dir / "uploads" / ".gitkeep").touch()

        for name in ("run.sh", "start.sh", "start.command", "scripts/setup-python.sh"):
            path = package_dir / name
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        shutil.make_archive(str(archive.with_suffix("")), "zip", staging, package_name)

    validate_archive(archive, package_name)

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, checksum


if __name__ == "__main__":
    output, digest_file = build()
    print(f"Built {output}")
    print(f"Checksum: {digest_file.read_text(encoding='ascii').strip()}")
