#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 24.04 VM for EventHub (docs/DEPLOY.md).
#
#   sudo EventHub/scripts/server-bootstrap.sh [--user eventhub] [--repo /home/eventhub/EventHub]
#
# Idempotent: safe to run again; every step checks before it changes anything
# and the summary at the end lists what this run changed.
#   - apt upgrade; Docker Engine + compose plugin from Docker's apt repository
#   - ufw: only 22/tcp, 80/tcp, 443/tcp, 443/udp
#   - 2 GB swapfile, timezone UTC, unattended security upgrades
#   - sshd: no password logins, no root login (only after checking that the
#     deploy user has an authorized key, so key-based logins keep working)
#   - fail2ban for sshd
#   - nightly database backup timer (scripts/prod-backup.sh) when the repo exists
set -euo pipefail

DEPLOY_USER=eventhub
REPO_DIR=''
while [ $# -gt 0 ]; do
  case "$1" in
    --user) DEPLOY_USER="${2:?}"; shift 2 ;;
    --repo) REPO_DIR="${2:?}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release
[ "${ID:-}" = ubuntu ] || { echo "Ubuntu only (found ${ID:-unknown})." >&2; exit 1; }
id "$DEPLOY_USER" >/dev/null 2>&1 || { echo "User $DEPLOY_USER does not exist." >&2; exit 1; }
USER_HOME=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
[ -n "$REPO_DIR" ] || REPO_DIR="$USER_HOME/EventHub"

CHANGES=()
changed() { CHANGES+=("$1"); echo "  changed: $1"; }
step() { echo "==> $1"; }
export DEBIAN_FRONTEND=noninteractive

step "System packages"
apt-get update -q
upgradable=$(apt list --upgradable 2>/dev/null | grep -c upgradable || true)
apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
[ "$upgradable" -gt 0 ] && changed "upgraded $upgradable packages"
need=()
for pkg in ca-certificates curl gnupg ufw fail2ban unattended-upgrades git openssl; do
  dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
done
if [ ${#need[@]} -gt 0 ]; then
  apt-get install -y -q "${need[@]}"
  changed "installed ${need[*]}"
fi

step "Docker Engine + compose plugin (download.docker.com)"
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  changed "added Docker's apt key"
fi
DOCKER_LIST=/etc/apt/sources.list.d/docker.list
DOCKER_REPO="deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable"
if [ "$(cat "$DOCKER_LIST" 2>/dev/null)" != "$DOCKER_REPO" ]; then
  echo "$DOCKER_REPO" > "$DOCKER_LIST"
  apt-get update -q
  changed "added Docker's apt repository"
fi
if ! dpkg -s docker-ce docker-compose-plugin >/dev/null 2>&1; then
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  changed "installed Docker Engine and the compose plugin"
fi
systemctl enable --now docker >/dev/null
if ! id -nG "$DEPLOY_USER" | grep -qw docker; then
  usermod -aG docker "$DEPLOY_USER"
  changed "added $DEPLOY_USER to the docker group (log in again to use it)"
fi
# Default log rotation for containers started without their own options.
DAEMON_JSON=/etc/docker/daemon.json
if [ ! -f "$DAEMON_JSON" ]; then
  cat > "$DAEMON_JSON" <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "live-restore": true
}
EOF
  systemctl restart docker
  changed "wrote $DAEMON_JSON (log rotation, live-restore)"
fi

step "Firewall (ufw): 22, 80, 443"
# Docker publishes ports through its own iptables chains, which ufw does not
# filter; in production only Caddy publishes ports (docker-compose.prod.yml).
for rule in 22/tcp 80/tcp 443/tcp 443/udp; do
  if ! ufw status | grep -qE "^${rule}[[:space:]]+ALLOW"; then
    ufw allow "$rule" >/dev/null
    changed "ufw allow $rule"
  fi
done
if ! ufw status | grep -q "Status: active"; then
  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw --force enable >/dev/null
  changed "enabled ufw (default deny incoming)"
fi

step "Swap (2 GB)"
if ! swapon --show=NAME --noheadings | grep -q '^/swapfile$'; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  changed "enabled /swapfile (2 GB)"
fi
grep -q '^/swapfile ' /etc/fstab || { echo '/swapfile none swap sw 0 0' >> /etc/fstab; changed "added /swapfile to /etc/fstab"; }
SYSCTL=/etc/sysctl.d/99-eventhub.conf
if [ ! -f "$SYSCTL" ]; then
  printf 'vm.swappiness=10\n' > "$SYSCTL"
  sysctl -q -p "$SYSCTL"
  changed "vm.swappiness=10"
fi

step "Timezone UTC"
if [ "$(timedatectl show -p Timezone --value)" != UTC ]; then
  timedatectl set-timezone UTC
  changed "timezone set to UTC"
fi

step "Unattended security upgrades"
AUTO=/etc/apt/apt.conf.d/20auto-upgrades
WANT_AUTO='APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";'
if [ "$(cat "$AUTO" 2>/dev/null)" != "$WANT_AUTO" ]; then
  printf '%s\n' "$WANT_AUTO" > "$AUTO"
  changed "enabled unattended-upgrades (security origin, Ubuntu default)"
fi
systemctl enable --now unattended-upgrades >/dev/null

step "sshd hardening"
AUTH_KEYS="$USER_HOME/.ssh/authorized_keys"
# sshd keeps the first value it reads, and cloud-init writes 50-cloud-init.conf
# (PasswordAuthentication yes on some images): sort before it.
SSHD_DROPIN=/etc/ssh/sshd_config.d/10-eventhub-hardening.conf
if [ ! -s "$AUTH_KEYS" ] || ! grep -qE '^(ssh-|ecdsa-|sk-)' "$AUTH_KEYS"; then
  echo "  SKIPPED: $AUTH_KEYS has no key; disabling password logins now could lock you out."
  echo "  Add a key for $DEPLOY_USER and run this script again."
else
  WANT_SSHD='# Managed by EventHub/scripts/server-bootstrap.sh
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 4
X11Forwarding no'
  if [ "$(cat "$SSHD_DROPIN" 2>/dev/null)" != "$WANT_SSHD" ]; then
    printf '%s\n' "$WANT_SSHD" > "$SSHD_DROPIN"
    # Validate before reloading: a broken config would stop new logins.
    if sshd -t; then
      systemctl reload ssh
      changed "sshd: key-only logins, no root login"
    else
      rm -f "$SSHD_DROPIN"
      echo "  sshd -t failed; hardening reverted." >&2
    fi
  fi
fi

step "fail2ban (sshd)"
JAIL=/etc/fail2ban/jail.d/eventhub-sshd.local
WANT_JAIL='[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h'
if [ "$(cat "$JAIL" 2>/dev/null)" != "$WANT_JAIL" ]; then
  printf '%s\n' "$WANT_JAIL" > "$JAIL"
  systemctl enable fail2ban >/dev/null
  systemctl restart fail2ban
  changed "fail2ban jail for sshd"
fi

step "Backup directory and nightly timer"
if [ ! -d /var/backups/eventhub ]; then
  install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /var/backups/eventhub
  changed "created /var/backups/eventhub"
fi
if [ -x "$REPO_DIR/EventHub/scripts/install-backup-timer.sh" ]; then
  "$REPO_DIR/EventHub/scripts/install-backup-timer.sh" --user "$DEPLOY_USER" --repo "$REPO_DIR" \
    | sed 's/^/  /'
else
  echo "  repo not at $REPO_DIR yet: after cloning run sudo EventHub/scripts/install-backup-timer.sh"
fi

echo
if [ ${#CHANGES[@]} -eq 0 ]; then
  echo "Nothing to change: the server was already prepared."
else
  echo "Changed in this run:"
  printf '  - %s\n' "${CHANGES[@]}"
fi
[ -f /var/run/reboot-required ] && echo "A reboot is required (kernel update): sudo reboot"
exit 0
