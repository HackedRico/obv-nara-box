#!/bin/bash
# NARA container entrypoint — starts XFCE desktop + VNC server, then idles.

# Clean up stale lock files from previous runs
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*

# Generate VNC password file (password: nara)
mkdir -p /root/.vnc
tigervncpasswd -f <<< $'nara\nnara\n' > /root/.vnc/passwd 2>/dev/null || \
    python3 -c "
import subprocess
p = subprocess.run(['vncpasswd','-f'], input=b'nara\n', capture_output=True)
open('/root/.vnc/passwd','wb').write(p.stdout)
" 2>/dev/null
chmod 600 /root/.vnc/passwd

# Start dbus (required by XFCE)
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || true
export $(dbus-launch)

# Start VNC server on display :1 (port 5901)
# Password: nara
Xvnc :1 \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes VncAuth \
    -PasswordFile /root/.vnc/passwd \
    -rfbport 5901 \
    -AlwaysShared \
    &

sleep 2

export DISPLAY=:1

# Start XFCE desktop
startxfce4 &

echo "[NARA] VNC server running on :5901 (password: nara)"
echo "[NARA] XFCE desktop started"
echo "[NARA] Container ready — waiting for commands."

# Keep the container alive
tail -f /dev/null
