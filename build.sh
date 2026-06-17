#!/usr/bin/env bash
# Render build script — собирает фронтенд и готовит Django
set -e
echo "=== BUILD START ==="
echo "Current dir: $(pwd)"
ls -la

# ── 1. Билдим фронтенд ──
echo ""
echo "=== Building frontend ==="
cd frontend
npm install
npm run build
ls -la dist/

# ── 2. Копируем билд в Django static ──
echo ""
echo "=== Copying frontend build to Django static ==="
cd ..
mkdir -p backend/staticfiles
cp -r frontend/dist/* backend/staticfiles/
ls -la backend/staticfiles/

# ── 3. Устанавливаем Python-зависимости ──
echo ""
echo "=== Installing Python dependencies ==="
cd backend
pip install -r requirements.txt

# ── 4. Собираем статику Django ──
echo ""
echo "=== Collecting Django static files ==="
python manage.py collectstatic --noinput

echo ""
echo "=== BUILD END ==="
