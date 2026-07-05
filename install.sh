#!/usr/bin/env bash
#
# Hata — install script for WSL2 (Ubuntu / Debian).
# Sets up the whole environment on a bare system: system deps, PostgreSQL,
# Python venv, app dependencies, Playwright browsers, DB schema, and systemd
# service (if systemd is available in WSL2; otherwise a run helper).
#
# Usage:  bash install.sh
#
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$PROJECT_DIR"
VENV="$APP_DIR/.venv"
DATA_DIR="$APP_DIR/data"
PHOTO_DIR="$DATA_DIR/photos"
LOG_DIR="$APP_DIR/logs"
DB_NAME="hata"
DB_USER="hata"
DB_PASS="hata"

log()  { printf "\033[1;34m[install]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[error]\033[0m %s\n" "$*" >&2; }
ok()   { printf "\033[1;32m[ok]\033[0m %s\n" "$*"; }
die()  { err "$*"; exit 1; }

require_root_or_sudo() {
  if [[ $EUID -eq 0 ]]; then return; fi
  if command -v sudo >/dev/null 2>&1; then return; fi
  die "Запустите скрипт с правами root или установите sudo."
}

detect_distro() {
  if [[ -f /etc/debian_version ]]; then echo "debian"; return; fi
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian|linuxmint|pop) echo "debian"; return ;;
      *) echo "unknown: $ID"; return ;;
    esac
  fi
  die "Не удалось определить дистрибутив. Поддерживаются Ubuntu / Debian (WSL2)."
}

install_system_deps_debian() {
  log "Установка системных пакетов (Debian/Ubuntu)..."
  sudo apt-get update -y
  sudo apt-get install -y \
    ca-certificates curl gnupg lsb-release build-essential \
    postgresql postgresql-contrib libpq-dev \
    python3 python3-venv python3-pip python3-dev \
    libffi-dev libssl-dev libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 2>/dev/null \
    || sudo apt-get install -y \
    ca-certificates curl gnupg lsb-release build-essential \
    postgresql postgresql-contrib libpq-dev \
    python3 python3-venv python3-pip python3-dev \
    libffi-dev libssl-dev libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2
  ok "Системные пакеты установлены."
}

ensure_postgres_running() {
  log "Запуск PostgreSQL..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    sudo systemctl enable --now postgresql || true
  else
    # WSL2 without systemd: start the cluster directly
    local ver
    ver="$(ls /etc/postgresql 2>/dev/null | sort -V | tail -1 || true)"
    if [[ -n "$ver" ]]; then
      sudo pg_ctlcluster "$ver" main start 2>/dev/null || true
    else
      sudo service postgresql start 2>/dev/null || true
    fi
  fi
  sleep 2
  ok "PostgreSQL запущен."
}

create_db_user() {
  log "Создание пользователя и базы данных '$DB_NAME'..."
  local sql="DO \$\$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
      CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS';
    END IF;
  END \$\$;
  SELECT 'CREATE DATABASE $DB_NAME OWNER $DB_USER'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
  ALTER DATABASE $DB_NAME OWNER TO $DB_USER;
  GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<<"$sql" || die "Не удалось создать БД"
  ok "БД '$DB_NAME' и пользователь '$DB_USER' готовы."
}

setup_venv() {
  log "Создание Python venv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip wheel setuptools
  "$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"
  ok "Зависимости Python установлены."
}

install_playwright_browsers() {
  log "Установка браузеров Playwright (Chromium)..."
  "$VENV/bin/playwright" install chromium
  "$VENV/bin/playwright" install-deps chromium 2>/dev/null || true
  ok "Браузеры Playwright готовы."
}

prepare_dirs() {
  mkdir -p "$DATA_DIR" "$PHOTO_DIR" "$LOG_DIR"
}

apply_schema() {
  log "Применение схемы БД..."
  HATA_ENV=development "$VENV/bin/python" -c "
import sys; sys.path.insert(0, '$APP_DIR')
from app import config, db
import os
os.chdir('$APP_DIR')
db.migrate()
print('schema OK')
" || die "Не удалось применить схему БД"
  ok "Схема БД применена."
}

write_run_scripts() {
  local run="$APP_DIR/run_hata.sh"
  cat >"$run" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR"
exec "$VENV/bin/python" run.py
EOF
  chmod +x "$run"
  ok "Скрипт запуска: $run"

  # systemd unit if systemd is available
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    local unit="/etc/systemd/system/hata.service"
    log "Установка systemd-юнита..."
    sudo tee "$unit" >/dev/null <<EOF
[Unit]
Description=Hata real-estate parser & map
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$VENV/bin/python run.py
Restart=on-failure
User=$USER
Environment=HATA_ENV=production

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable hata
    ok "systemd-юнит установлен: sudo systemctl start hata"
  fi
}

print_banner() {
  cat <<'BANNER'

   ╔═══════════════════════════════════════════╗
   ║              Hata установлен               ║
   ╚═══════════════════════════════════════════╝

  Запуск:        ./run_hata.sh
  Сервис:        sudo systemctl start hata  (если есть systemd)
  Веб-интерфейс: http://localhost:5000

  БД:            PostgreSQL  база=$DB_NAME  пользователь=$DB_USER
  Фото:          $PHOTO_DIR
  Логи:          $LOG_DIR/parser.log
  Настройки:     $APP_DIR/config.json (создаётся через веб-интерфейс)

  Первый запуск: откройте «Парсинг» → отметьте «Тестовый режим»
                 → «Начать парсинг» чтобы заполнить БД мок-данными.
BANNER
}

main() {
  require_root_or_sudo
  local distro; distro="$(detect_distro)"
  [[ "$distro" == "debian" ]] || die "Дистрибутив не поддерживается: $distro"
  install_system_deps_debian
  ensure_postgres_running
  create_db_user
  setup_venv
  install_playwright_browsers
  prepare_dirs
  apply_schema
  write_run_scripts
  print_banner
}

main "$@"
