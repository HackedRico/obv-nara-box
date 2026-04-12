FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Core packages + XFCE desktop + VNC
# Note: Ubuntu's `firefox` .deb is a snap stub and does not run inside Docker.
# Real Firefox is installed from Mozilla in the next RUN.
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        xfce4 xfce4-terminal dbus-x11 \
        tigervnc-standalone-server tigervnc-common \
        python3 python3-pip git curl wget netcat-openbsd \
        feh xdg-utils sudo zenity psmisc libglib2.0-bin \
        xz-utils ca-certificates \
        humanity-icon-theme \
        libgtk-3-0 libdbus-glib-1-2 libxt6 libasound2 libnss3 libatk-bridge2.0-0 \
        libdrm2 libgbm1 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libx11-xcb1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Mozilla Firefox (real binary — works without snap; supports amd64 + arm64)
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) FF_OS=linux64 ;; \
        arm64) FF_OS=linux64-aarch64 ;; \
        *) echo "Unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    wget -q -O /tmp/firefox.tar.xz "https://download.mozilla.org/?product=firefox-latest-ssl&os=${FF_OS}&lang=en-US"; \
    tar -xJf /tmp/firefox.tar.xz -C /opt; \
    ln -sf /opt/firefox/firefox /usr/local/bin/firefox; \
    rm /tmp/firefox.tar.xz

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
