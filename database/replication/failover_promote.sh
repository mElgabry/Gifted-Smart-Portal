#!/bin/bash
# =============================================================================
# بوابة الإدارة العامة للموهوبين والتعلم الذكي
# سكريبت مراقبة التزامن وترقية الخادم الاحتياطي عند الطوارئ (Failover & Monitoring)
# =============================================================================
set -euo pipefail

ACTION="${1:-status}"

case "${ACTION}" in
    status)
        echo "=== حالة النسخ المتماثل على الخادم الرئيسي (Primary) ==="
        sudo -u postgres psql -c "
            SELECT client_addr AS standby_ip, state, sync_state,
                   pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) AS sent_lag_bytes,
                   pg_wal_lsn_diff(flush_lsn, replay_lsn) AS replay_lag_bytes
            FROM pg_stat_replication;
        " || true

        echo "=== حالة الاستقبال على الخادم الاحتياطي (Standby) ==="
        sudo -u postgres psql -c "
            SELECT pg_is_in_recovery() AS is_standby_mode;
            SELECT status, sender_host, last_msg_receipt_time, latest_end_lsn
            FROM pg_stat_wal_receiver;
        " || true
        ;;
    promote)
        echo "تحذير: جاري ترقية الخادم الاحتياطي ليصبح الخادم الرئيسي (Primary Read/Write)..."
        sudo -u postgres psql -c "SELECT pg_promote();"
        echo "تمت الترقية بنجاح!"
        ;;
    *)
        echo "الاستخدام: $0 {status|promote}"
        exit 1
        ;;
esac
