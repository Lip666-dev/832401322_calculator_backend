#!/bin/sh
# ---------------------------------------------------------------------------
# One-command deployment of the 832401322 calculator (back end + front end)
# on a Linux server.
#
#   curl -fsSL https://raw.githubusercontent.com/Lip666-dev/832401322_calculator_backend/main/deploy/deploy.sh | sudo sh
#
# Optional environment variables:
#   PUBLIC_IP       public address printed in the summary (auto-detected otherwise)
#   BACKEND_PORT    API port                (default 8000)
#   FRONTEND_PORT   static front-end port   (default 8080)
#   INSTALL_DIR     where the sources go    (default /opt/832401322_calculator)
#   REPO_OWNER      GitHub account          (default Lip666-dev)
#   STUDENT_ID      repository prefix       (default 832401322)
#
# Example:
#   curl -fsSL .../deploy.sh | sudo PUBLIC_IP=203.0.113.10 FRONTEND_PORT=8080 sh
#
# The script is plain POSIX sh, installs git + python3 through the distribution
# package manager, clones both repositories, registers two systemd services
# (falling back to nohup when systemd is unavailable), opens the local firewall
# and finally prints the public URLs.
# ---------------------------------------------------------------------------
set -eu

REPO_OWNER="${REPO_OWNER:-Lip666-dev}"
STUDENT_ID="${STUDENT_ID:-832401322}"
INSTALL_DIR="${INSTALL_DIR:-/opt/832401322_calculator}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
PUBLIC_IP="${PUBLIC_IP:-}"
# Clone source.  Inside mainland China github.com is sometimes slow or blocked;
# point REPO_BASE at a mirror in that case, for example:
#   REPO_BASE=https://gitclone.com/github.com/Lip666-dev
#   REPO_BASE=https://ghproxy.net/https://github.com/Lip666-dev
REPO_BASE="${REPO_BASE:-https://github.com/$REPO_OWNER}"

log() { printf '\n==> %s\n' "$*"; }
warn() { printf '    ! %s\n' "$*"; }
fail() { printf '\n!! %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run this script as root, for example:  curl -fsSL <url> | sudo sh"

# --- 1. packages -----------------------------------------------------------
log "installing git, python3 and curl"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq git python3 curl ca-certificates
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q git python3 curl
elif command -v yum >/dev/null 2>&1; then
    yum install -y -q git python3 curl
elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache git python3 curl
else
    fail "no supported package manager found (tried apt-get, dnf, yum, apk)"
fi

# --- 2. pick an interpreter >= 3.8 ----------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
            PY="$candidate"
            break
        fi
    fi
done
[ -n "$PY" ] || fail "Python 3.8+ not found. Install a newer python3 and run this script again."
PY_PATH="$(command -v "$PY")"
log "using $("$PY" --version 2>&1) at $PY_PATH"

# --- 3. sources ------------------------------------------------------------
mkdir -p "$INSTALL_DIR"
for part in backend frontend; do
    url="$REPO_BASE/${STUDENT_ID}_calculator_$part.git"
    dir="$INSTALL_DIR/$part"
    if [ -d "$dir/.git" ]; then
        log "updating the $part checkout"
        git -C "$dir" pull --ff-only || warn "could not fast-forward $part, keeping the local copy"
    else
        log "cloning $part from $url"
        if ! git clone --depth 1 "$url" "$dir"; then
            fail "could not clone $url
    Inside mainland China github.com is sometimes unreachable from a server.
    Re-run with a mirror, for example:
        curl -fsSL <script-url> | sudo REPO_BASE=https://gitclone.com/github.com/$REPO_OWNER sh"
        fi
    fi
done

# --- 4. stop previous nohup instances (harmless when systemd is used) ------
for pidfile in "$INSTALL_DIR/backend.pid" "$INSTALL_DIR/frontend.pid"; do
    if [ -f "$pidfile" ]; then
        kill "$(cat "$pidfile")" 2>/dev/null || true
        rm -f "$pidfile"
    fi
done

# --- 5. services -----------------------------------------------------------
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    log "registering systemd services"
    cat > /etc/systemd/system/calculator-backend.service <<UNIT
[Unit]
Description=Calculator API (assignment ${STUDENT_ID})
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}/backend
Environment=CALC_DB_PATH=${INSTALL_DIR}/backend/data/calculator.db
ExecStart=${PY_PATH} run.py --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

    cat > /etc/systemd/system/calculator-frontend.service <<UNIT
[Unit]
Description=Calculator front end (assignment ${STUDENT_ID})
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}/frontend
ExecStart=${PY_PATH} -m http.server ${FRONTEND_PORT} --bind 0.0.0.0 --directory ${INSTALL_DIR}/frontend
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable calculator-backend.service calculator-frontend.service >/dev/null 2>&1 || true
    systemctl restart calculator-backend.service calculator-frontend.service
else
    log "systemd not available, starting both parts with nohup"
    cd "$INSTALL_DIR/backend"
    CALC_DB_PATH="$INSTALL_DIR/backend/data/calculator.db" \
        nohup "$PY" run.py --host 0.0.0.0 --port "$BACKEND_PORT" >"$INSTALL_DIR/backend.log" 2>&1 &
    echo $! > "$INSTALL_DIR/backend.pid"

    nohup "$PY" -m http.server "$FRONTEND_PORT" --bind 0.0.0.0 --directory "$INSTALL_DIR/frontend" \
        >"$INSTALL_DIR/frontend.log" 2>&1 &
    echo $! > "$INSTALL_DIR/frontend.pid"
fi

# --- 6. local firewall -----------------------------------------------------
log "checking the local firewall"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$BACKEND_PORT"/tcp >/dev/null 2>&1 || true
    ufw allow "$FRONTEND_PORT"/tcp >/dev/null 2>&1 || true
    warn "ufw: allowed tcp/$BACKEND_PORT and tcp/$FRONTEND_PORT"
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    firewall-cmd --permanent --add-port="$BACKEND_PORT"/tcp >/dev/null 2>&1 || true
    firewall-cmd --permanent --add-port="$FRONTEND_PORT"/tcp >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
    warn "firewalld: allowed tcp/$BACKEND_PORT and tcp/$FRONTEND_PORT"
else
    warn "no active ufw/firewalld detected, nothing to open locally"
fi

# --- 7. self test ----------------------------------------------------------
log "self test"
sleep 2
if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 10 "http://127.0.0.1:$BACKEND_PORT/api/health"; then
        printf '\n    API answered correctly\n'
    else
        warn "the API did not answer on port $BACKEND_PORT yet; check: journalctl -u calculator-backend -n 50"
    fi
    code="$(curl -fsS --max-time 10 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$FRONTEND_PORT/" || true)"
    if [ "$code" = "200" ]; then
        printf '    front end answered with HTTP 200\n'
    else
        warn "the front end did not answer on port $FRONTEND_PORT (got '$code')"
    fi
fi

if [ -z "$PUBLIC_IP" ]; then
    PUBLIC_IP="$(curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)"
fi
[ -n "$PUBLIC_IP" ] || PUBLIC_IP="<your-server-ip>"

cat <<EOF

----------------------------------------------------------------------
Deployment finished.

  Front end : http://${PUBLIC_IP}:${FRONTEND_PORT}/
  Back end  : http://${PUBLIC_IP}:${BACKEND_PORT}/api/health
  Sources   : ${INSTALL_DIR}
  Database  : ${INSTALL_DIR}/backend/data/calculator.db

Still to do yourself:
  * open TCP ${FRONTEND_PORT} and TCP ${BACKEND_PORT} in the cloud console's
    security group (安全组), otherwise the two addresses stay unreachable;
  * verify from your own machine:
        curl http://${PUBLIC_IP}:${BACKEND_PORT}/api/health

Service control (systemd):
  systemctl status calculator-backend calculator-frontend
  systemctl restart calculator-backend
  journalctl -u calculator-backend -n 50 --no-pager
----------------------------------------------------------------------
EOF
