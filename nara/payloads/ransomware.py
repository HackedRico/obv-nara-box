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
import sys
import shutil
import subprocess
import struct
import zlib

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
    """Set the XFCE desktop wallpaper to the ransom image."""
    try:
        wallpaper = _create_ransom_wallpaper()
        print(f"[RANSOMWARE] Wallpaper image created → {wallpaper}")

        # Try xfconf-query (XFCE4)
        result = subprocess.run(
            [
                "xfconf-query", "-c", "xfce4-desktop",
                "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                "-s", wallpaper,
            ],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("[RANSOMWARE] Wallpaper changed via xfconf-query")
            return

        # Try feh as fallback
        result = subprocess.run(
            ["feh", "--bg-fill", wallpaper],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("[RANSOMWARE] Wallpaper changed via feh")
            return

        print("[RANSOMWARE] Wallpaper file ready — VNC may need to refresh to show change")

    except FileNotFoundError:
        print("[RANSOMWARE] xfconf-query/feh not available — wallpaper change skipped")
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
