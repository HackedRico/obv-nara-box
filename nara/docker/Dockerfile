FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Core packages + XFCE desktop + VNC
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        xfce4 xfce4-terminal dbus-x11 \
        tigervnc-standalone-server tigervnc-common \
        python3 python3-pip git curl wget netcat-openbsd \
        feh xdg-utils sudo \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# VNC config — no password for lab use
RUN mkdir -p /root/.vnc && \
    echo "" | vncpasswd -f > /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# XFCE as the VNC window manager
RUN echo '#!/bin/sh\nstartxfce4 &' > /root/.vnc/xstartup && \
    chmod +x /root/.vnc/xstartup

COPY start_vnc.sh /start_vnc.sh
RUN chmod +x /start_vnc.sh

EXPOSE 5901 8080

ENTRYPOINT ["/start_vnc.sh"]
