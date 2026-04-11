#!/bin/bash
# NARA container entrypoint — starts XFCE desktop + VNC server, then idles.

# Clean up stale lock files from previous runs
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# Start VNC server on display :1 (port 5901)
vncserver :1 \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes None \
    --I-KNOW-THIS-IS-INSECURE \
    2>/dev/null

echo "[NARA] VNC server running on :5901"
echo "[NARA] Container ready — waiting for commands."

# Keep the container alive
tail -f /dev/null
