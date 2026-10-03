"""Create .env from .env.example with freshly generated secrets.

    python scripts/make_env.py

Fills JWT_SECRET and ADMIN_PASSWORD with random values so that no default
credential ever exists in the repository. Refuses to overwrite an existing
.env. The generated admin password is written to .env only (never printed):
open the file to read it.
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists; not overwriting it.")
        return 1
    generated = {
        "JWT_SECRET": secrets.token_urlsafe(48),
        # token_urlsafe gives letters/digits/-/_ ; the suffix guarantees the
        # password policy (a letter and a digit) is met.
        "ADMIN_PASSWORD": secrets.token_urlsafe(18) + "a1",
    }
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={generated[key]}" if key in generated else line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("Created .env with a random JWT_SECRET and ADMIN_PASSWORD.")
    print("The admin username is 'admin'; the password is in .env (ADMIN_PASSWORD).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
