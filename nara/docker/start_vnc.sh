#!/bin/bash
# NARA container entrypoint — starts XFCE desktop + VNC + noVNC, then idles.

# Clean up stale lock files from previous runs
rm -f /tmp/.X*-lock /tmp/.X11-unix/X*

# Start dbus (required by XFCE)
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || true
export $(dbus-launch)

# Start VNC server on display :1 (port 5901), no password
Xvnc :1 \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes None \
    -rfbport 5901 \
    -AlwaysShared \
    &

sleep 2

export DISPLAY=:1

# Start XFCE desktop
startxfce4 &

# Start noVNC web client on port 6080 → proxies to VNC :5901
/opt/noVNC/utils/novnc_proxy --vnc localhost:5901 --listen 6080 &

echo "[NARA] VNC server running on :5901"
echo "[NARA] noVNC web client: http://localhost:6080/vnc.html"
echo "[NARA] Container ready — waiting for commands."

# Keep the container alive
tail -f /dev/null
