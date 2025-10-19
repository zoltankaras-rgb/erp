# scripts/install_csrf_patch.py — idempotent installer
import io, os, sys, re, pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"

def main():
    if not APP_PATH.exists():
        print(f"[!] app.py not found at {APP_PATH}")
        sys.exit(1)
    src = APP_PATH.read_text(encoding="utf-8")
    changed = False

    if "from csrf import csrf_protect" not in src:
        # Insert import near other imports
        src = re.sub(r"(\nimport data_handler[^\n]*\n)", r"\1from csrf import csrf_protect, inject_csrf, ensure_csrf_token\n", src, count=1)
        changed = True

    if "app.before_request(ensure_csrf_token)" not in src:
        # Add hooks after app = Flask(...) initialization
        src = re.sub(r"(app\s*=\s*Flask\([^\)]*\)[^\n]*\n)", r"\1# --- CSRF hooks (installed by patch) ---\napp.before_request(ensure_csrf_token)\napp.before_request(csrf_protect)\napp.after_request(inject_csrf)\n", src, count=1)
        changed = True

    if changed:
        APP_PATH.write_text(src, encoding="utf-8")
        print("[+] CSRF hooks added to app.py")
    else:
        print("[=] CSRF already installed, no changes")

if __name__ == "__main__":
    main()
