#!/usr/bin/env python3
"""
NARA Ransomware Simulation
==========================
Runs INSIDE the Docker container via: python3 /tmp/ransomware.py

Self-contained — stdlib only. No pip installs needed.

This is a VISUAL DEMONSTRATION for a security research hackathon.
- No actual encryption of real files
- No network exfiltration
- Effects are contained to the Docker container
- Container is disposable and resettable via 'nara > reset'
"""

import os
import shlex
import subprocess
import struct
import sys
import zlib

# Absolute paths — XFCE resolves themed names inconsistently in minimal images
_ICON_WARN = "/usr/share/icons/Humanity/status/48/dialog-warning.svg"
_ICON_FOLDER = "/usr/share/icons/Humanity/places/48/folder.svg"
_ICON_BROWSER = "/usr/share/icons/Humanity/apps/48/web-browser.svg"
_ICON_MAIL = "/usr/share/icons/Humanity/categories/48/applications-mail.svg"

# ------------------------------------------------------------------ #
# Ransom note — customizable via CLI argument or env var              #
# ------------------------------------------------------------------ #

DEFAULT_NOTE = """
╔══════════════════════════════════════════════════════════════════╗
║                  YOUR SYSTEM HAS BEEN COMPROMISED                ║
║                                                                  ║
║  NARA has autonomously discovered and exploited vulnerabilities  ║
║  in this system. In a real attack, your data would be gone.      ║
║                                                                  ║
║  VULNERABILITIES EXPLOITED:                                      ║
║  → Command Injection via /api/pokemon endpoint                   ║
║    (user input passed directly to os.system() — no sanitization) ║
║  → Unrestricted file upload                                      ║
║  → Remote code execution                                         ║
║                                                                  ║
║  WHAT HAPPENED:                                                  ║
║  1. NARA scanned your codebase with Semgrep + Bandit             ║
║  2. AI planner designed this kill chain autonomously             ║
║  3. Exploiter gained shell access via command injection          ║
║  4. This payload was uploaded and executed                       ║
║                                                                  ║
║  This is a SECURITY RESEARCH DEMONSTRATION.                      ║
║  No real files were harmed. Reset with: nara > reset             ║
║                                                                  ║
║  ──────────────────────────────────────────────────────────────  ║
║  NARA — Autonomous Red Team Platform  |  Bitcamp 2026            ║
╚══════════════════════════════════════════════════════════════════╝
"""

DESKTOP = os.path.expanduser("~/Desktop")
WALLPAPER_PATH = "/tmp/nara_ransom_wallpaper.png"
DUMMY_FILES_DIR = "/tmp/nara_demo_files"


def drop_ransom_note(custom_message: str = ""):
    """Drop README_RANSOM.txt on the desktop."""
    os.makedirs(DESKTOP, exist_ok=True)
    note_path = os.path.join(DESKTOP, "README_RANSOM.txt")
    content = custom_message if custom_message else DEFAULT_NOTE
    with open(note_path, "w") as f:
        f.write(content)
    print(f"[RANSOMWARE] Ransom note → {note_path}")

    # Also drop one in /tmp for visibility in non-desktop environments
    with open("/tmp/README_RANSOM.txt", "w") as f:
        f.write(content)
    print("[RANSOMWARE] Ransom note → /tmp/README_RANSOM.txt")


def fake_encrypt_files():
    """
    'Encrypt' dummy files by renaming them with .NARA_ENCRYPTED extension.
    Only touches files in /tmp/nara_demo_files — never touches real files.
    """
    os.makedirs(DUMMY_FILES_DIR, exist_ok=True)

    # Create dummy sensitive-looking files
    dummy_files = [
        ("financial_report_Q4.xlsx", "ACME Corp Q4 Revenue: $4.2M"),
        ("employee_records.csv", "id,name,salary\n1,John Smith,95000"),
        ("database_backup.sql", "CREATE TABLE users (id INT, password VARCHAR(255));"),
        ("api_keys.txt", "AWS_KEY=AKIAIOSFODNN7EXAMPLE\nGITHUB_TOKEN=ghp_example"),
        ("source_code_backup.tar", "Binary archive placeholder"),
    ]

    for fname, content in dummy_files:
        fpath = os.path.join(DUMMY_FILES_DIR, fname)
        with open(fpath, "w") as f:
            f.write(content)

    # "Encrypt" by renaming
    encrypted_count = 0
    for fname in os.listdir(DUMMY_FILES_DIR):
        if fname.endswith(".NARA_ENCRYPTED"):
            continue
        src = os.path.join(DUMMY_FILES_DIR, fname)
        dst = src + ".NARA_ENCRYPTED"
        os.rename(src, dst)
        print(f"[RANSOMWARE] Encrypted: {fname} → {fname}.NARA_ENCRYPTED")
        encrypted_count += 1

    print(f"[RANSOMWARE] {encrypted_count} file(s) encrypted in {DUMMY_FILES_DIR}")


def hijack_desktop_shortcuts():
    """
    Rename existing .desktop launchers and drop ransom-themed shortcuts so the
    XFCE desktop visibly reflects the 'takeover' in VNC.
    """
    os.makedirs(DESKTOP, exist_ok=True)
    readme = os.path.join(DESKTOP, "README_RANSOM.txt")

    for name in list(os.listdir(DESKTOP)):
        path = os.path.join(DESKTOP, name)
        if (
            name.endswith(".desktop")
            and "NARA_" not in name
            and os.path.isfile(path)
        ):
            try:
                locked = path + ".NARA_LOCKED"
                os.rename(path, locked)
                print(f"[RANSOMWARE] Locked launcher: {name} → {name}.NARA_LOCKED")
            except OSError as e:
                print(f"[RANSOMWARE] Could not lock {name}: {e}")

    # Ransom shortcuts (open ransom note in a terminal so it always works in the container)
    templates = [
        ("NARA__READ_ME.desktop", "!!! READ ME — RANSOM !!!", _ICON_WARN),
        ("NARA__FILES_LOCKED.desktop", "Documents — LOCKED", _ICON_FOLDER),
        ("NARA__BROWSER_LOCKED.desktop", "Browser — LOCKED", _ICON_BROWSER),
        ("NARA__MAIL_LOCKED.desktop", "Mail — LOCKED", _ICON_MAIL),
    ]
    for fname, title, icon in templates:
        path = os.path.join(DESKTOP, fname)
        lines = [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={title}",
            "Comment=NARA ransomware simulation",
            f"Icon={icon}",
            "Terminal=false",
            # Hold terminal open so the user can read the note in VNC
            f"Exec=xfce4-terminal --hold -e \"bash -c 'head -60 {readme}; echo; echo ---; sleep 600'\"",
            "",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass
        print(f"[RANSOMWARE] Desktop shortcut → {path}")


def _create_ransom_wallpaper():
    """
    Create a solid dark-red PNG using only stdlib (struct + zlib).
    Returns the path to the created file.
    """
    width, height = 1920, 1080

    def make_chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # PNG signature
    png = b"\x89PNG\r\n\x1a\n"

    # IHDR: width, height, bit depth=8, color type=2 (RGB), compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png += make_chunk(b"IHDR", ihdr_data)

    # IDAT: raw image data (dark red #1a0000 background with a centered message in white)
    # Build rows: filter_byte + RGB pixels per row
    # To keep it fast, use a simple scanline approach with a pattern
    bg_r, bg_g, bg_b = 26, 0, 0  # #1a0000 dark red

    rows = bytearray()
    for y in range(height):
        rows += b"\x00"  # filter type None
        for x in range(width):
            rows += bytes([bg_r, bg_g, bg_b])

    png += make_chunk(b"IDAT", zlib.compress(bytes(rows), level=1))
    png += make_chunk(b"IEND", b"")

    with open(WALLPAPER_PATH, "wb") as f:
        f.write(png)

    return WALLPAPER_PATH


def change_wallpaper():
    """
    Set the XFCE desktop wallpaper. Requires DBus (xfconf) — docker exec without a session
    often fails; when run as DISPLAY=:1 python3 ... from the exploiter, this script runs
    with dbus-launch below so all monitor/workspace backdrops update.
    """
    wallpaper = _create_ransom_wallpaper()
    print(f"[RANSOMWARE] Wallpaper image created → {wallpaper}")
    wp = shlex.quote(wallpaper)

    # Must use the SAME dbus session as the running XFCE desktop, otherwise
    # xfconf-query writes to a new session that xfdesktop never reads.
    # Then kill+restart xfdesktop to force the wallpaper refresh.
    script = f"""
set -e
export DISPLAY="${{DISPLAY:-:1}}"

# Inherit the dbus session from the running xfce4-session process
XFCE_PID=$(pgrep -o xfce4-session 2>/dev/null || true)
if [ -n "$XFCE_PID" ] && [ -r /proc/$XFCE_PID/environ ]; then
  eval $(cat /proc/$XFCE_PID/environ 2>/dev/null | tr '\\0' '\\n' | grep DBUS_SESSION_BUS_ADDRESS)
  export DBUS_SESSION_BUS_ADDRESS
fi

# If we still don't have a dbus address, fall back to feh only
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
  feh --bg-fill {wp} 2>/dev/null || true
  exit 0
fi

# Set wallpaper for all monitors/workspaces
for key in $(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep last-image || true); do
  xfconf-query -c xfce4-desktop -p "$key" -s {wp} 2>/dev/null || true
done

# Kill and restart xfdesktop so it picks up the new wallpaper
pkill xfdesktop 2>/dev/null || true
sleep 1
xfdesktop &
sleep 1

# Also use feh on root window as belt-and-suspenders
feh --bg-fill {wp} 2>/dev/null || true
"""
    try:
        r = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if r.returncode != 0 and r.stderr:
            print(f"[RANSOMWARE] Wallpaper script stderr: {r.stderr[:500]}")
        print("[RANSOMWARE] Wallpaper applied (xfconf + xfdesktop + feh)")
    except subprocess.TimeoutExpired:
        print("[RANSOMWARE] Wallpaper command timed out")
    except Exception as e:
        print(f"[RANSOMWARE] Wallpaper change failed: {e}")


def print_ascii_skull():
    """Print an ASCII skull for dramatic terminal effect."""
    skull = r"""
    ░░░░░░░░░░░░░░░░░░░░░░░░░░
    ░░░░░▄████▄░░▄████▄░░░░░░░
    ░░░░██▀▀▀▀█░█▀▀▀▀██░░░░░░░
    ░░░░██░░░░█░█░░░░██░░░░░░░
    ░░░░░██████░░██████░░░░░░░
    ░░░░░░████░░░░████░░░░░░░░
    ░░░░░███░░░░░░░███░░░░░░░░
    ░░░░░███░░▄▄▄░░███░░░░░░░░
    ░░░░░░▀███████████░░░░░░░░
    ░░░░░░░░▀███████▀░░░░░░░░░
    ░░░░░░░░░░░░░░░░░░░░░░░░░░
    """
    print("\033[91m" + skull + "\033[0m")


def main(custom_message: str = ""):
    print("\n" + "═" * 60)
    print("[RANSOMWARE] Deploying NARA ransomware simulation...")
    print("═" * 60 + "\n")

    print_ascii_skull()

    drop_ransom_note(custom_message)
    hijack_desktop_shortcuts()
    fake_encrypt_files()
    change_wallpaper()

    print("\n" + "═" * 60)
    print("[RANSOMWARE] Payload complete.")
    print("[RANSOMWARE] Check VNC :5901 to see the desktop effects.")
    print("═" * 60)
    print(DEFAULT_NOTE)


if __name__ == "__main__":
    custom_msg = ""
    if len(sys.argv) > 1:
        custom_msg = " ".join(sys.argv[1:])
    main(custom_msg)
