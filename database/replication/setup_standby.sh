#!/bin/bash
# =============================================================================
# بوابة الإدارة العامة للموهوبين والتعلم الذكي
# سكريبت إعداد وتفعيل الخادم الاحتياطي (Standby Server) عبر Streaming Replication
# =============================================================================
set -euo pipefail

PRIMARY_HOST="${PRIMARY_HOST:-192.168.10.10}"
PRIMARY_PORT="${PRIMARY_PORT:-5432}"
REP_USER="${REP_USER:-repuser}"
REP_SLOT="${REP_SLOT:-standby_portal_slot}"
PGDATA="${PGDATA:-/var/lib/postgresql/16/main}"

echo "[1/4] إيقاف خدمة PostgreSQL على الخادم الاحتياطي..."
systemctl stop postgresql || true

echo "[2/4] تنظيف مجلد البيانات الحالي (${PGDATA})..."
rm -rf "${PGDATA:?}"/*

echo "[3/4] سحب البيانات الأولية من الخادم الرئيسي عبر pg_basebackup (-R -Xs)..."
sudo -u postgres pg_basebackup \
    -h "${PRIMARY_HOST}" \
    -p "${PRIMARY_PORT}" \
    -U "${REP_USER}" \
    -D "${PGDATA}" \
    -Fp -Xs -P -R \
    -S "${REP_SLOT}"

echo "[4/4] ضبط الصلاحيات وتشغيل الخادم الاحتياطي (Hot Standby)..."
chmod 0700 "${PGDATA}"
chown -R postgres:postgres "${PGDATA}"
systemctl start postgresql
echo "تم تشغيل الخادم الاحتياطي بنجاح!"
