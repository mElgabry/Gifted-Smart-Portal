#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوابة الإدارة العامة للموهوبين والتعلم الذكي
أداة ترحيل البيانات وتشفير كلمات المرور بـ bcrypt إلى PostgreSQL (JSONB)
وزارة التربية والتعليم والتعليم الفني - جمهورية مصر العربية
"""

import os
import sys
import json
import psycopg2
from psycopg2.extras import Json
import bcrypt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "schema.sql")
INDEXES_SQL = os.path.join(os.path.dirname(__file__), "indexes.sql")
USERS_AUTH_JSON = os.path.join(DATA_DIR, "users_auth.json")
PORTAL_DB_JSON = os.path.join(DATA_DIR, "portal_database.json")

DB_CONFIG = {
    "dbname": os.environ.get("PG_DB", "gifted_portal_db"),
    "user": os.environ.get("PG_USER", "postgres"),
    "password": os.environ.get("PG_PASSWORD", "StrongMasterPassword2026!"),
    "host": os.environ.get("PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("PG_PORT", 5432)),
}

def hash_password_bcrypt(plain_password: str, rounds: int = 12) -> str:
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")

def run_migration():
    print("=" * 70)
    print("  بدء ترحيل وتأمين قاعدة البيانات (PostgreSQL + JSONB + bcrypt)")
    print("=" * 70)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("[1/4] جاري إنشاء الجداول وتفعيل الامتدادات (schema.sql)...")
    with open(SCHEMA_SQL, "r", encoding="utf-8") as f:
        cur.execute(f.read())

    print("[2/4] جاري بناء الفهارس (GIN, B-Tree, pg_trgm)...")
    with open(INDEXES_SQL, "r", encoding="utf-8") as f:
        cur.execute(f.read())

    print("[3/4] جاري ترحيل الحسابات الرسمية الـ 40 بتجزئة bcrypt...")
    with open(USERS_AUTH_JSON, "r", encoding="utf-8") as f:
        users_payload = json.load(f)

    for u in users_payload.get("users", []):
        profile = {
            "aliases": u.get("aliases", []),
            "category": u.get("category", ""),
            "permission": u.get("permission", ""),
            "status": u.get("status", "نشط"),
        }
        cur.execute(
            """
            INSERT INTO users (id, username, password_hash, name, role, role_name, gov, is_active, two_factor_enabled, profile_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                name = EXCLUDED.name,
                role = EXCLUDED.role,
                role_name = EXCLUDED.role_name,
                gov = EXCLUDED.gov,
                two_factor_enabled = EXCLUDED.two_factor_enabled,
                profile_data = EXCLUDED.profile_data;
            """,
            (
                u["id"],
                u["username"],
                u["password_hash"],
                u["name"],
                u["role"],
                u["roleName"],
                u.get("gov", ""),
                u.get("status", "نشط") == "نشط",
                bool(u.get("twoFactor", False)),
                Json(profile),
            ),
        )

    print("[4/4] جاري ترحيل سجلات الطلاب والمراكز وسجل التدقيق (JSONB)...")
    with open(PORTAL_DB_JSON, "r", encoding="utf-8") as f:
        portal_data = json.load(f)

    for stu in portal_data.get("students", []):
        cur.execute(
            """
            INSERT INTO students (id, data) VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data;
            """,
            (stu["id"], Json(stu)),
        )

    for ctr in portal_data.get("centers", []):
        cur.execute(
            """
            INSERT INTO centers (id, data) VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data;
            """,
            (ctr["id"], Json(ctr)),
        )

    for log in portal_data.get("auditLog", []):
        cur.execute(
            """
            INSERT INTO audit_logs (username, user_role, action, entity, details, ip_address, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """,
            (
                log.get("user", ""),
                log.get("role", ""),
                log.get("action", ""),
                log.get("entity", ""),
                log.get("details", ""),
                log.get("ip", ""),
                Json({"recorded_time": log.get("time", "")}),
            ),
        )

    conn.commit()
    cur.close()
    conn.close()
    print("=" * 70)
    print("  تم الانتهاء من ترحيل كافة البيانات وتفعيل التشفير والفهارس بنجاح!")
    print("=" * 70)

if __name__ == "__main__":
    run_migration()
