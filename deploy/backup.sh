#!/usr/bin/env bash
set -e
# ENT Prep — ежедневный бекап базы данных и медиафайлов
# Запускать по cron: 0 3 * * * /path/to/deploy/backup.sh

BACKUP_DIR="${BACKUP_DIR:-/var/backups/ent-prep}"
DB_NAME="${DB_NAME:-entprep}"
DB_USER="${DB_USER:-entprep}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)

mkdir -p "$BACKUP_DIR"

echo "=== Backup started: $TIMESTAMP ==="

# 1. Бекап БД (PostgreSQL)
if [ -n "$DATABASE_URL" ]; then
    echo "Backing up PostgreSQL..."
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/db_$TIMESTAMP.sql.gz"
else
    echo "DATABASE_URL not set, skipping DB backup"
fi

# 2. Бекап медиа-файлов (картинки вопросов)
MEDIA_DIR="${MEDIA_DIR:-/var/www/ent-prep/backend/media}"
if [ -d "$MEDIA_DIR" ]; then
    echo "Backing up media files..."
    tar czf "$BACKUP_DIR/media_$TIMESTAMP.tar.gz" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"
fi

# 3. Удаляем старые бекапы
echo "Cleaning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name 'media_*.tar.gz' -mtime "+$RETENTION_DAYS" -delete

echo "=== Backup complete: $(date +%Y-%m-%d_%H-%M-%S) ==="
