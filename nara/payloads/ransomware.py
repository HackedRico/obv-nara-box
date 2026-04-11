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
_ICON_DIR = "/tmp/nara_icons"
_ICON_WARN = os.path.join(_ICON_DIR, "rocket_warn.png")
_ICON_FOLDER = os.path.join(_ICON_DIR, "rocket_folder.png")
_ICON_BROWSER = os.path.join(_ICON_DIR, "rocket_browser.png")
_ICON_MAIL = os.path.join(_ICON_DIR, "rocket_mail.png")

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
WALLPAPER_PATH = "/tmp/nara_ransom_wallpaper.jpg"
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
    Replace ALL existing desktop shortcuts with Team Rocket R-branded locked versions,
    then drop ransom-themed shortcuts so the XFCE desktop visibly reflects the takeover.
    """
    os.makedirs(DESKTOP, exist_ok=True)
    readme = os.path.join(DESKTOP, "README_RANSOM.txt")
    rocket_icon = _ICON_FOLDER  # Red R on dark — used for all hijacked icons

    # Replace ALL existing .desktop files with "LOCKED" versions using the R icon
    for name in list(os.listdir(DESKTOP)):
        path = os.path.join(DESKTOP, name)
        if not name.endswith(".desktop") or "NARA_" in name or not os.path.isfile(path):
            continue

        # Extract the original app name from the .desktop file
        original_name = name.replace(".desktop", "")
        try:
            with open(path, "r") as f:
                for line in f:
                    if line.startswith("Name="):
                        original_name = line.strip().split("=", 1)[1]
                        break
        except Exception:
            pass

        # Overwrite the shortcut with a locked version using the R icon
        locked_lines = [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={original_name} — LOCKED",
            "Comment=NARA ransomware simulation",
            f"Icon={rocket_icon}",
            "Terminal=false",
            f"Exec=xfce4-terminal --hold -e \"bash -c 'head -60 {readme}; echo; echo ---; sleep 600'\"",
            "",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(locked_lines))
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass
        print(f"[RANSOMWARE] Hijacked: {name} → {original_name} — LOCKED")

    # Drop ransom shortcuts
    templates = [
        ("NARA__READ_ME.desktop", "!!! READ ME — RANSOM !!!", _ICON_WARN),
        ("NARA__FILES_LOCKED.desktop", "Documents — ENCRYPTED", _ICON_FOLDER),
        ("NARA__BROWSER_LOCKED.desktop", "Browser — ENCRYPTED", _ICON_BROWSER),
        ("NARA__MAIL_LOCKED.desktop", "Mail — ENCRYPTED", _ICON_MAIL),
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


# ── Team Rocket "R" bitmap (16x20 grid, 1 = red, 0 = background) ────
_ROCKET_R = [
    "0011111111111100",
    "0011111111111110",
    "0011100000011111",
    "0011100000001111",
    "0011100000001111",
    "0011100000001111",
    "0011100000011111",
    "0011111111111110",
    "0011111111111100",
    "0011111111110000",
    "0011100011110000",
    "0011100001111000",
    "0011100000111100",
    "0011100000011110",
    "0011100000001111",
    "0011100000000111",
]


def _make_png(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    """Build a raw PNG from a 2D list of (R, G, B) tuples. Stdlib only."""
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    rows = bytearray()
    for row in pixels:
        rows += b"\x00"  # filter type None
        for r, g, b in row:
            rows += bytes([r, g, b])

    png += chunk(b"IDAT", zlib.compress(bytes(rows), level=1))
    png += chunk(b"IEND", b"")
    return png


def _draw_rocket_r(width: int, height: int, bg: tuple, fg: tuple) -> list:
    """Render the Team Rocket R bitmap scaled to fill the given dimensions."""
    bmp_h = len(_ROCKET_R)
    bmp_w = len(_ROCKET_R[0])

    # Scale factor — R fills ~60% of the smaller dimension
    scale = int(min(width, height) * 0.6 / max(bmp_w, bmp_h))
    if scale < 1:
        scale = 1

    r_w = bmp_w * scale
    r_h = bmp_h * scale
    ox = (width - r_w) // 2
    oy = (height - r_h) // 2

    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            bx = (x - ox) // scale
            by = (y - oy) // scale
            if 0 <= bx < bmp_w and 0 <= by < bmp_h and _ROCKET_R[by][bx] == "1":
                row.append(fg)
            else:
                row.append(bg)
        pixels.append(row)
    return pixels


def _create_ransom_wallpaper():
    """
    Use the Team Rocket wallpaper (Jessie & James silhouette) if the exploiter
    copied it into the container. Falls back to a generated red R on black.
    Returns the path to the created file.
    """
    # The exploiter copies the real Team Rocket wallpaper here before running us
    if os.path.exists(WALLPAPER_PATH) and os.path.getsize(WALLPAPER_PATH) > 1000:
        print(f"[RANSOMWARE] Using Team Rocket wallpaper → {WALLPAPER_PATH}")
        return WALLPAPER_PATH

    # Fallback: generate a red R on black
    width, height = 1920, 1080
    bg = (10, 10, 10)       # near-black
    fg = (200, 0, 0)        # Team Rocket red

    pixels = _draw_rocket_r(width, height, bg, fg)
    png_path = WALLPAPER_PATH.replace(".jpg", ".png")
    png = _make_png(width, height, pixels)

    with open(png_path, "wb") as f:
        f.write(png)

    return png_path


def generate_rocket_icons():
    """Generate Team Rocket 'R' icon PNGs for desktop shortcuts."""
    os.makedirs(_ICON_DIR, exist_ok=True)

    icon_configs = [
        (_ICON_WARN,    (200, 0, 0),   (255, 255, 255)),  # red bg, white R
        (_ICON_FOLDER,  (40, 40, 40),  (200, 0, 0)),      # dark bg, red R
        (_ICON_BROWSER, (40, 40, 40),  (200, 0, 0)),      # dark bg, red R
        (_ICON_MAIL,    (40, 40, 40),  (200, 0, 0)),      # dark bg, red R
    ]

    for path, bg, fg in icon_configs:
        pixels = _draw_rocket_r(48, 48, bg, fg)
        png = _make_png(48, 48, pixels)
        with open(path, "wb") as f:
            f.write(png)

    print(f"[RANSOMWARE] Team Rocket icons generated → {_ICON_DIR}")


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
    generate_rocket_icons()
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
