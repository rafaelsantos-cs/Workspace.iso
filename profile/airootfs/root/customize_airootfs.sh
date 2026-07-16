#!/usr/bin/env bash
set -euo pipefail

if ! getent group lga-ipc >/dev/null; then
    groupadd --system lga-ipc
fi

if ! id lga-runner >/dev/null 2>&1; then
    useradd --system --gid lga-ipc --home-dir /var/lib/lga \
        --shell /usr/bin/nologin lga-runner
fi
if ! id lga-egress >/dev/null 2>&1; then
    useradd --system --gid lga-ipc --home-dir /var/lib/lga \
        --shell /usr/bin/nologin lga-egress
fi
if ! id workspace >/dev/null 2>&1; then
    useradd --create-home --user-group --shell /bin/bash \
        --groups audio,video,input,render,storage,optical,lga-ipc,systemd-journal \
        workspace
fi
if ! id operator >/dev/null 2>&1; then
    useradd --create-home --user-group --shell /bin/bash operator
fi

# The fixed password exists only in the ephemeral live session. An installed
# system is created separately by archinstall and must use operator-selected
# credentials. Root stays locked in the live image.
echo 'workspace:workspace' | chpasswd
passwd --lock operator
passwd --lock root

systemd-tmpfiles --create /etc/tmpfiles.d/lga.conf
chown -R lga-runner:lga-ipc /var/lib/lga/memory /var/lib/lga/uimp-spool
chown -R lga-egress:lga-ipc /var/lib/lga/quarantine /var/lib/lga/audit

install -d -m 0755 /etc/skel/Desktop /home/workspace/Desktop
cp -a /etc/skel/. /home/workspace/
chown -R workspace:workspace /home/workspace

systemctl disable systemd-networkd.service systemd-networkd-wait-online.service 2>/dev/null || true
systemctl enable NetworkManager.service
systemctl enable systemd-resolved.service
systemctl enable sddm.service
systemctl enable bluetooth.service
systemctl enable firewalld.service
systemctl enable lga-egressd.service
systemctl enable lga-artifact-guard.path
systemctl enable workspace-operator-setup.service
systemctl enable getty@tty3.service

git lfs install --system --skip-repo || true
firewall-offline-cmd --set-default-zone=workspace
firewall-offline-cmd --set-log-denied=unicast

# Keep the reference runtime immutable; all state lives under /var/lib/lga.
find /opt/lga/nanolga -type d -exec chmod 0755 {} +
find /opt/lga/nanolga -type f -exec chmod 0644 {} +
