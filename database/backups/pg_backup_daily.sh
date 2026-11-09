#!/bin/bash
# ==============================================================================
# بوابة الإدارة العامة للموهوبين والتعلم الذكي
# سكريبت النسخ الاحتياطي اليومي الآلي والنقل لموقع منفصل (Off-Site Backup)
# وزارة التربية والتعليم والتعليم الفني - جمهورية مصر العربية
# ==============================================================================
set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres/gifted_portal}"
DB_NAME="${PG_DB:-gifted_portal_db}"
DB_USER="${PG_USER:-postgres}"
DB_HOST="${PG_HOST:-127.0.0.1}"
DB_PORT="${PG_PORT:-5432}"

RAW_DUMP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
ENCRYPTED_FILE="${RAW_DUMP_FILE}.enc"
CHECKSUM_FILE="${RAW_DUMP_FILE}.sha256"
LOG_FILE="${BACKUP_DIR}/backup_execution.log"

OFFSITE_S3_BUCKET="${OFFSITE_S3_BUCKET:-s3://moe-gifted-offsite-backups/postgresql}"
OFFSITE_SSH_TARGET="${OFFSITE_SSH_TARGET:-backup_transfer@10.20.30.100:/mnt/offsite_vault/gifted_portal}"
ENCRYPTION_KEY_FILE="${ENCRYPTION_KEY_FILE:-/etc/postgresql/backup_aes256.key}"

mkdir -p "${BACKUP_DIR}"

log_msg() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

log_msg "بدء النسخ الاحتياطي اليومي لقاعدة البيانات (${DB_NAME})..."

pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        -F c -b -v -f "${RAW_DUMP_FILE}" 2>> "${LOG_FILE}"

sha256sum "${RAW_DUMP_FILE}" > "${CHECKSUM_FILE}"

if [ -f "${ENCRYPTION_KEY_FILE}" ]; then
    openssl enc -aes-256-cbc -salt -pbkdf2 \
        -in "${RAW_DUMP_FILE}" \
        -out "${ENCRYPTED_FILE}" \
        -pass file:"${ENCRYPTION_KEY_FILE}"
    rm -f "${RAW_DUMP_FILE}"
    TARGET_UPLOAD_FILE="${ENCRYPTED_FILE}"
    log_msg "تم تشفير النسخة الاحتياطية بنجاح (AES-256)."
else
    TARGET_UPLOAD_FILE="${RAW_DUMP_FILE}"
    log_msg "تنبيه: ملف مفتاح التشفير غير موجود، سيتم رفع النسخة المضغوطة مباشرة."
fi

if command -v aws &> /dev/null; then
    log_msg "جاري رفع النسخة الاحتياطية إلى التخزين السحابي المنفصل (${OFFSITE_S3_BUCKET})..."
    aws s3 cp "${TARGET_UPLOAD_FILE}" "${OFFSITE_S3_BUCKET}/daily/" --storage-class STANDARD_IA >> "${LOG_FILE}" 2>&1
    aws s3 cp "${CHECKSUM_FILE}" "${OFFSITE_S3_BUCKET}/daily/" >> "${LOG_FILE}" 2>&1
    log_msg "تم رفع النسخة إلى التخزين السحابي بنجاح."
fi

if command -v rsync &> /dev/null && [ "${ENABLE_RSYNC_OFFSITE:-false}" = "true" ]; then
    log_msg "جاري إرسال النسخة الاحتياطية إلى خادم الطوارئ المنفصل عبر SSH/Rsync..."
    rsync -avz --checksum "${TARGET_UPLOAD_FILE}" "${CHECKSUM_FILE}" "${OFFSITE_SSH_TARGET}/" >> "${LOG_FILE}" 2>&1
    log_msg "تم النقل إلى الخادم المنفصل عبر Rsync بنجاح."
fi

find "${BACKUP_DIR}" -type f \( -name "*.dump" -o -name "*.enc" -o -name "*.sha256" \) -mtime +7 -delete
log_msg "تم تنظيف النسخ المحلية الأقدم من 7 أيام. اكتملت المهمة بنجاح."
