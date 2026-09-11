import re
from pathlib import Path

ROOTS = [
    Path("g4f"),
    Path(".venv/Lib/site-packages/g4f"),
]

PATTERNS = [
    re.compile(r'os\.getenv\(\s*["\']([^"\']+)'),
    re.compile(r'os\.environ\.get\(\s*["\']([^"\']+)'),
    re.compile(r'os\.environ\[\s*["\']([^"\']+)'),
    re.compile(r'os\.environ\.setdefault\(\s*["\']([^"\']+)'),
]

found = {}

for root in ROOTS:
    if not root.exists():
        continue

    for path in root.rglob("*.py"):
        try:
            lines = path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()
        except OSError:
            continue

        for line_no, line in enumerate(lines, 1):
            for pattern in PATTERNS:
                for match in pattern.finditer(line):
                    name = match.group(1)

                    found.setdefault(name, []).append(
                        (
                            str(path),
                            line_no,
                            line.strip(),
                        )
                    )

print()
print("=" * 80)
print("G4F ENVIRONMENT VARIABLES")
print("=" * 80)
print()

for name in sorted(found):
    print(name)

print()
print("=" * 80)
print(f"TOTAL UNIQUE VARIABLES: {len(found)}")
print("=" * 80)
print()

print("DETAILS")
print("-" * 80)

for name in sorted(found):
    print()
    print(f"[{name}]")

    # Remove duplicate locations.
    seen = set()

    for path, line_no, line in found[name]:
        key = (path, line_no)

        if key in seen:
            continue

        seen.add(key)

        print(f"  {path}:{line_no}")
        print(f"    {line}")
