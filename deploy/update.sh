#!/usr/bin/env bash
# ENT Prep — обновление продакшена на сервере (109.235.116.114, /opt/entprep)
# Использование:
#   bash deploy/update.sh                # git pull с GitHub
#   bash deploy/update.sh file.bundle    # обновление из git-bundle (если GitHub требует auth)
set -e
cd /opt/entprep

BUNDLE="${1:-}"

echo "=== 1/6 git update ==="
if [ -n "$BUNDLE" ] && [ -f "$BUNDLE" ]; then
  echo "Updating from bundle: $BUNDLE"
  git fetch -q "$BUNDLE" main
  git reset --hard -q FETCH_HEAD
else
  git pull --ff-only origin main
fi
git log --oneline -1

echo "=== 2/6 python deps ==="
./venv/bin/pip install -r requirements.txt --quiet

echo "=== 3/6 frontend build ==="
cd frontend
npm install --no-audit --no-fund --silent
npm run build --silent
cd ..
mkdir -p backend/staticfiles
cp -r frontend/dist/* backend/staticfiles/

echo "=== 4/6 collectstatic ==="
cd backend
../venv/bin/python manage.py collectstatic --noinput | tail -1

echo "=== 5/6 migrate ==="
../venv/bin/python manage.py migrate --noinput 2>&1 | tail -3

echo "=== 6/6 restart ==="
sudo systemctl restart ent-web.service
sleep 2
systemctl is-active ent-web.service && echo "DEPLOY OK"
