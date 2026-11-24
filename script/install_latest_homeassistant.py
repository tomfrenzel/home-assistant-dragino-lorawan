"""Install the latest stable Home Assistant release and its matching test helpers.

CI uses this for the ``latest`` lane. To reproduce it locally::

    uv sync --group dev
    uv run --no-sync python script/install_latest_homeassistant.py
    uv run --no-sync pytest

Run ``uv sync --group dev`` again to return to the pinned environment.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.request import urlopen


def fetch_package(package: str, version: str = "") -> dict[str, Any]:
    """Fetch PyPI metadata; a missing release raises instead of falling back."""
    suffix = f"/{version}" if version else ""
    url = f"https://pypi.org/pypi/{package}{suffix}/json"
    with urlopen(url, timeout=30) as response:
        metadata: dict[str, Any] = json.load(response)
    return metadata


def run(*args: str) -> str:
    """Run a command and return its output."""
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main() -> None:
    """Replace the pinned Core with the latest stable release."""
    version = str(fetch_package("homeassistant")["info"]["version"])
    if not re.fullmatch(r"\d{4}\.\d+\.\d+", version):
        raise ValueError(f"Expected a stable Home Assistant release, got {version!r}")
    fetch_package("pytest-homeassistant", version)
    install = ["uv", "pip", "install", "--python", sys.executable]
    subprocess.run(
        ["uv", "pip", "uninstall", "--python", sys.executable, "pytest-home-assistant"],
        check=True,
    )
    subprocess.run(
        [*install, f"homeassistant=={version}", f"pytest-homeassistant=={version}"],
        check=True,
    )
    manifest = json.loads(
        run(
            sys.executable,
            "-c",
            "import homeassistant.components.lorawan as c, pathlib; "
            "print((pathlib.Path(c.__file__).parent / 'manifest.json').read_text())",
        )
    )
    subprocess.run([*install, *manifest["requirements"]], check=True)
    versions = run(
        sys.executable,
        "-c",
        "import importlib.metadata as m, platform; "
        "print('Python ' + platform.python_version()); "
        "print('\\n'.join(p + '==' + m.version(p) for p in "
        "('homeassistant', 'pytest-homeassistant', 'lorawan-connection')))",
    )
    print(versions, end="")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write(f"### Home Assistant: latest\n\n```text\n{versions}```\n")


if __name__ == "__main__":
    main()
