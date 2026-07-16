#!/usr/bin/env bash
# shellcheck disable=SC2034

iso_name="workspace"
iso_label="WORKSPACE_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="LGA Project <https://github.com/rafaelsantos-cs>"
iso_application="WorkSpace - constrained learning environment for LGA"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"
install_dir="workspace"
buildmodes=('iso')
bootmodes=('bios.syslinux'
           'uefi.systemd-boot')
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/sudoers.d/10-workspace-operator"]="0:0:440"
  ["/root"]="0:0:750"
  ["/root/.automated_script.sh"]="0:0:755"
  ["/root/.gnupg"]="0:0:700"
  ["/root/customize_airootfs.sh"]="0:0:755"
  ["/usr/local/bin/choose-mirror"]="0:0:755"
  ["/usr/local/bin/Installation_guide"]="0:0:755"
  ["/usr/local/bin/livecd-sound"]="0:0:755"
  ["/usr/local/bin/nanolga"]="0:0:755"
  ["/usr/local/bin/nanolga-desktop-bridge"]="0:0:755"
  ["/usr/local/bin/uimp"]="0:0:755"
  ["/usr/local/bin/workspace-browser"]="0:0:755"
  ["/usr/local/bin/workspace-fetch"]="0:0:755"
  ["/usr/local/bin/workspace-first-session"]="0:0:755"
  ["/usr/local/bin/workspace-job"]="0:0:755"
  ["/usr/local/bin/workspace-status"]="0:0:755"
  ["/usr/local/lib/workspace/egressd.py"]="0:0:755"
  ["/usr/local/lib/workspace/job_runner.py"]="0:0:755"
  ["/usr/local/lib/workspace/uimp.py"]="0:0:755"
  ["/usr/local/libexec/workspace-operator-setup"]="0:0:755"
)
