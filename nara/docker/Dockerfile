FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Core packages + XFCE desktop + VNC
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        xfce4 xfce4-terminal dbus-x11 \
        tigervnc-standalone-server tigervnc-common \
        python3 python3-pip git curl wget netcat-openbsd \
        feh xdg-utils sudo \
        firefox \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# XFCE as the VNC window manager
# Generate VNC password file ("nara") using tigervncpasswd at runtime in start_vnc.sh
RUN mkdir -p /root/.vnc && \
    echo '#!/bin/sh' > /root/.vnc/xstartup && \
    echo 'startxfce4 &' >> /root/.vnc/xstartup && \
    chmod +x /root/.vnc/xstartup

# noVNC — browser-based VNC client (no install needed on host)
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --depth 1 https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify

COPY start_vnc.sh /start_vnc.sh
RUN chmod +x /start_vnc.sh

EXPOSE 5901 6080 8080

ENTRYPOINT ["/start_vnc.sh"]
