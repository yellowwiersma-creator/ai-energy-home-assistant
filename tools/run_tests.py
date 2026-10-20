"""Run tests with an isolated data root, never against Home Assistant data."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="ai-energy-tests-") as temp:
        env = os.environ.copy()
        env["AI_ENERGY_ROOT"] = temp
        paths = [str(repo), str(repo / "home_assistant/pyscript_modules")]
        if env.get("PYTHONPATH"):
            paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(paths)
        return subprocess.call(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=repo, env=env,
        )


if __name__ == "__main__":
    raise SystemExit(main())
