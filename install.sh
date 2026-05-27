#!/usr/bin/env bash
# TL IDE — установщик для Linux и macOS
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/Ameight/mvp_inspector/master/install.sh | bash
#
# Что делает:
#   1. Определяет ОС
#   2. Скачивает последний бинарный релиз (PyInstaller onedir) с GitHub
#   3. Устанавливает в ~/.local/share/tl-ide/
#   4. Создаёт ярлык ~/.local/bin/tl-ide
#   5. Подсказывает добавить ~/.local/bin в PATH

set -euo pipefail

REPO="Ameight/mvp_inspector"
APP_NAME="tl-ide"
INSTALL_DIR="${HOME}/.local/share/${APP_NAME}"
BIN_DIR="${HOME}/.local/bin"

# ── Цвета ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "  $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

# ── Зависимости ────────────────────────────────────────────────────────────────
need() { command -v "$1" &>/dev/null || die "Требуется $1. Установи его и повтори."; }
need curl
need unzip

# ── Определение ОС ─────────────────────────────────────────────────────────────
OS=$(uname -s)
case "$OS" in
  Linux*)  LABEL="Linux"  ;;
  Darwin*) LABEL="macOS"  ;;
  *)       die "Неподдерживаемая ОС: $OS. Используй ручную установку." ;;
esac

echo ""
echo "  TL IDE — установка"
echo "  ─────────────────────"

# ── Последняя версия ───────────────────────────────────────────────────────────
info "Получаем последнюю версию..."
LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
  | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": "\(.*\)".*/\1/')
[ -z "$LATEST" ] && die "Не удалось получить версию с GitHub. Проверь подключение."
info "Версия: ${LATEST}"

# ── Скачивание ────────────────────────────────────────────────────────────────
ZIP_NAME="${APP_NAME}-${LATEST}-${LABEL}.zip"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${LATEST}/${ZIP_NAME}"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

info "Скачиваем ${ZIP_NAME}..."
curl -fsSL --progress-bar "$DOWNLOAD_URL" -o "${TMP_DIR}/${ZIP_NAME}" \
  || die "Ошибка скачивания. Проверь: ${DOWNLOAD_URL}"

# ── Установка ─────────────────────────────────────────────────────────────────
info "Устанавливаем в ${INSTALL_DIR}..."
unzip -q "${TMP_DIR}/${ZIP_NAME}" -d "${TMP_DIR}/"

# Удаляем старую версию если есть
rm -rf "$INSTALL_DIR"
mkdir -p "$(dirname "$INSTALL_DIR")"

# Внутри ZIP — папка tl-ide/
mv "${TMP_DIR}/${APP_NAME}" "$INSTALL_DIR"
chmod +x "${INSTALL_DIR}/${APP_NAME}"

# ── Создание ярлыка ───────────────────────────────────────────────────────────
mkdir -p "$BIN_DIR"
cat > "${BIN_DIR}/${APP_NAME}" << WRAPPER
#!/usr/bin/env bash
exec "${INSTALL_DIR}/${APP_NAME}" "\$@"
WRAPPER
chmod +x "${BIN_DIR}/${APP_NAME}"

ok "TL IDE ${LATEST} установлен!"

# ── Проверка PATH ─────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
  echo ""
  warn "${BIN_DIR} не в PATH."
  info "Добавь в ~/.bashrc / ~/.zshrc:"
  info ""
  info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  info ""
  info "Затем перезапусти терминал или выполни:"
  info "  source ~/.bashrc   # или source ~/.zshrc"
  echo ""
fi

echo ""
info "Запуск:"
info "  tl-ide"
info ""
info "Приложение откроется в браузере: http://localhost:8080"
echo ""
