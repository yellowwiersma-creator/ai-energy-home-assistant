"""Audit only the distributable tree; report locations, never matched secrets."""
from pathlib import Path
import ipaddress
import re
import sys

REPO = Path(__file__).resolve().parents[1]
TOP_FILES = {"README.md", "README.en.md", "LICENSE", "NOTICE.md", "CONTRIBUTING.md",
             "SECURITY.md", "CHANGELOG.md", "requirements-dev.txt", ".gitignore", ".gitattributes"}
TOP_FILES.add("RELEASE_FILES.txt")
DIRECTORIES = {"home_assistant", "planner", "tools", "tests", "examples", "docs", ".github"}
EXTENSIONS = {".py", ".md", ".json", ".yaml", ".yml", ".svg", ".txt"}
PATTERNS = {
    "home path": re.compile(r"(?:[A-Za-z]:[\\/]Users[\\/]|[/]home[/][^/\s]+[/])", re.I),
    "email address": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "JWT token": re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"),
    "device identifier": re.compile(r"\b[a-f0-9]{32}\b", re.I),
    "integration identifier": re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b"),
    "MAC address": re.compile(r"\b(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\b", re.I),
}
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


def release_files(root=REPO):
    """Only individually reviewed paths from the committed release manifest."""
    root = Path(root).resolve()
    manifest = root / "RELEASE_FILES.txt"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Missing reviewed RELEASE_FILES.txt; refusing directory-wide discovery")
    seen = set()
    for name in manifest.read_text(encoding="utf-8").splitlines():
        if not name or name.startswith("#"):
            continue
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or name in seen:
            raise ValueError("Invalid or duplicate release manifest entry")
        seen.add(name)
        path = root / relative
        if not path.is_file() or any(p.is_symlink() for p in [path, *path.parents] if p != root):
            raise ValueError("Missing or symbolic release source: " + name)
        if root not in path.resolve().parents:
            raise ValueError("Release source escapes repository")
        if len(relative.parts) == 1:
            allowed = relative.name in TOP_FILES
        else:
            allowed = relative.parts[0] in DIRECTORIES and path.suffix in EXTENSIONS
        if not allowed or any(p in {"data", "local", ".storage", "__pycache__"} for p in relative.parts):
            raise ValueError("Unapproved release source category: " + name)
        if ".local." in path.name or path.name in {"settings.json", "ev-settings.json", "secrets.yaml"}:
            raise ValueError("Private local settings cannot join a release")
        if path.suffix == ".json" and name not in {
            "examples/settings.example.json", "examples/ev-settings.example.json",
            "examples/planning.example.json", "home_assistant/optional/ev_roles.json",
        }:
            raise ValueError("Unapproved JSON source: " + name)
        yield path


def audit(root=REPO):
    root = Path(root).resolve()
    findings = []
    files = list(release_files(root))
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeError:
            findings.append({"file": relative, "line": 0, "kind": "non-text file"})
            continue
        for number, line in enumerate(lines, 1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append({"file": relative, "line": number, "kind": name})
            for match in IPV4.finditer(line):
                try:
                    address = ipaddress.ip_address(match.group())
                except ValueError:
                    continue
                if address.is_private and not address.is_loopback and not str(address).startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
                    findings.append({"file": relative, "line": number, "kind": "private IPv4 address"})
    return files, findings


def main():
    try:
        files, findings = audit()
    except (ValueError, OSError) as exc:
        print("Release manifest rejected: " + str(exc))
        return 1
    for item in findings:
        print(f"{item['file']}:{item['line']}: {item['kind']}")
    print(f"Audited {len(files)} selected release files; {len(findings)} findings.")
    print("Pattern checking complements manual review; it cannot certify arbitrary future contributions.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
