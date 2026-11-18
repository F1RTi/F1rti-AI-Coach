"""Build the offline Windows setup using the official CPython embeddable distribution."""

import hashlib
import importlib.metadata
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".work"
OUT = ROOT / "release"
EMBED = "python-3.12.10-embed-amd64.zip"
SHA = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
RUNTIME = [
    "charset-normalizer",
    "reportlab",
    "annotated-doc",
    "annotated-types",
    "anyio",
    "certifi",
    "click",
    "colorama",
    "demoparser2",
    "fastapi",
    "h11",
    "httpcore",
    "httpx",
    "idna",
    "numpy",
    "opentelemetry-api",
    "packaging",
    "pandas",
    "pillow",
    "polars",
    "polars-runtime-32",
    "pyarrow",
    "pydantic",
    "pydantic-core",
    "pystray",
    "python-dateutil",
    "six",
    "starlette",
    "tqdm",
    "typing-extensions",
    "typing-inspection",
    "tzdata",
    "uvicorn",
]


def package():
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    archive = WORK / EMBED
    if not archive.exists():
        urllib.request.urlretrieve(
            "https://www.python.org/ftp/python/3.12.10/" + EMBED, archive
        )
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA:
        raise ValueError("CPython archive checksum mismatch")
    payload = WORK / "payload.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as dest:
        with zipfile.ZipFile(archive) as source:
            for item in source.namelist():
                if item.endswith("._pth"):
                    dest.writestr(item, "python312.zip\n.\npackages\n")
                else:
                    dest.writestr(item, source.read(item))
        for name in RUNTIME:
            dist = importlib.metadata.distribution(name)
            for item in dist.files or []:
                if (
                    ".." in item.parts
                    or "__pycache__" in item.parts
                    or item.suffix == ".pyc"
                ):
                    continue
                path = Path(dist.locate_file(item))
                if path.is_file():
                    dest.write(path, "packages/" + item.as_posix())
        for path in [
            ROOT / "desktop.py",
            ROOT / "README.md",
            *sorted((ROOT / "backend").glob("*.py")),
            *sorted((ROOT / "frontend/dist").rglob("*")),
        ]:
            if path.is_file() and not path.name.startswith("test_"):
                dest.write(path, path.relative_to(ROOT).as_posix())
    compiler = (
        Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    target = OUT / "F1rti-AI-Coach-Setup.exe"
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:winexe",
            "/platform:x64",
            "/optimize+",
            "/reference:System.IO.Compression.dll",
            "/reference:System.IO.Compression.FileSystem.dll",
            "/reference:System.Windows.Forms.dll",
            "/resource:" + str(payload) + ",coach.payload",
            "/out:" + str(target),
            str(ROOT / "scripts/Setup.cs"),
        ],
        check=True,
    )
    print(
        target, target.stat().st_size, hashlib.sha256(target.read_bytes()).hexdigest()
    )


if __name__ == "__main__":
    package()
