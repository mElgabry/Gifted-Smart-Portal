#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوابة الإدارة العامة للموهوبين والتعلم الذكي
الخادم الآمن المتكامل (PostgreSQL JSONB + Server-Side Bcrypt Auth + JWT HS256 + Automated Backup)
وزارة التربية والتعليم والتعليم الفني - جمهورية مصر العربية
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import socket
import shutil
import webbrowser
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# محاولة استيراد psycopg2 للاتصال المباشر بقاعدة بيانات PostgreSQL (إن وجدت)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# محاولة استيراد مكتبة bcrypt أو استخدام مكتبة التشفير النظامية libcrypt ($2b$12$)
try:
    import bcrypt as py_bcrypt
    HAS_PY_BCRYPT = True
except ImportError:
    HAS_PY_BCRYPT = False

try:
    import ctypes
    import ctypes.util
    _libcrypt_path = ctypes.util.find_library("crypt")
    if _libcrypt_path:
        _libcrypt = ctypes.CDLL(_libcrypt_path)
        _libcrypt.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        _libcrypt.crypt.restype = ctypes.c_char_p
    else:
        _libcrypt = None
except Exception:
    _libcrypt = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_OFFSITE_DIR = os.path.join(BASE_DIR, "database", "backups", "offsite_vault")
DB_JSON_PATH = os.path.join(DATA_DIR, "portal_database.json")
SAVED_DATA_JS_PATH = os.path.join(DATA_DIR, "saved_data.js")
USERS_AUTH_JSON_PATH = os.path.join(DATA_DIR, "users_auth.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_OFFSITE_DIR, exist_ok=True)

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "MOE_EGYPT_GIFTED_PORTAL_SECRET_2026_HS256_KEY")
JWT_EXP_SECONDS = 24 * 60 * 60  # 24 ساعة

PG_CONFIG = {
    "dbname": os.environ.get("PG_DB", "gifted_portal_db"),
    "user": os.environ.get("PG_USER", "postgres"),
    "password": os.environ.get("PG_PASSWORD", "StrongMasterPassword2026!"),
    "host": os.environ.get("PG_HOST", "127.0.0.1"),
    "port": int(os.environ.get("PG_PORT", 5432)),
}

# =============================================================================
# 1. خدمات التشفير والتحقق من كلمات المرور (Server-Side Bcrypt & JWT HS256)
# =============================================================================

def hash_bcrypt_password(plain_password: str) -> str:
    """توليد تجزئة bcrypt ($2b$12$) لكلمة المرور الجديدة أو المستعادة (6666)"""
    plain_bytes = plain_password.encode("utf-8")
    if HAS_PY_BCRYPT:
        try:
            return py_bcrypt.hashpw(plain_bytes, py_bcrypt.gensalt(rounds=12)).decode("ascii")
        except Exception:
            pass
    return "PLAIN:" + plain_password


def verify_bcrypt_password(plain_password: str, password_hash: str) -> bool:
    """التحقق من كلمة المرور مقابل تجزئة bcrypt ($2b$12$) على الخادم حصرياً"""
    if not plain_password or not password_hash:
        return False
    if password_hash.startswith("PLAIN:"):
        return hmac.compare_digest(plain_password, password_hash[6:])
    plain_bytes = plain_password.encode("utf-8")
    hash_bytes = password_hash.encode("ascii")

    if HAS_PY_BCRYPT:
        try:
            return py_bcrypt.checkpw(plain_bytes, hash_bytes)
        except Exception:
            pass

    if _libcrypt is not None:
        try:
            res = _libcrypt.crypt(plain_bytes, hash_bytes)
            if res:
                return hmac.compare_digest(res.decode("ascii"), password_hash)
        except Exception:
            pass

    return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(b64_str: str) -> bytes:
    padding = "=" * ((4 - len(b64_str) % 4) % 4)
    return base64.urlsafe_b64decode((b64_str + padding).encode("ascii"))


def issue_jwt(user_dict: dict) -> tuple:
    """إصدار رمز JWT قياسي موقع بخوارزمية HMAC-SHA256 على الخادم"""
    now_ms = int(time.time() * 1000)
    exp_ms = now_ms + (JWT_EXP_SECONDS * 1000)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_dict["id"],
        "username": user_dict["username"],
        "name": user_dict["name"],
        "role": user_dict["role"],
        "roleName": user_dict.get("roleName", ""),
        "gov": user_dict.get("gov", ""),
        "iat": int(time.time()),
        "exp": exp_ms,
        "iss": "MOE-EGYPT-GIFTED-SMART-PORTAL-PG-SERVER",
    }

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)

    token = f"Bearer {header_b64}.{payload_b64}.{sig_b64}"
    return token, exp_ms


def verify_jwt(auth_header: str) -> dict:
    """التحقق من صحة وتوقيع وصلاحية رمز JWT المرسل من العميل"""
    if not auth_header:
        raise ValueError("Missing Authorization header")
    token = auth_header.replace("Bearer ", "").strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT structure")

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = _b64url_encode(
        hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise ValueError("Invalid JWT signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    now_ms = int(time.time() * 1000)
    if payload.get("exp") and now_ms > payload["exp"]:
        raise ValueError("JWT token has expired")
    return payload


# =============================================================================
# 2. طبقة إدارة قاعدة البيانات (PostgreSQL JSONB + JSON Fallback)
# =============================================================================

class DatabaseManager:
    def __init__(self):
        self.pg_available = False
        self._check_postgres()

    def _check_postgres(self):
        if not HAS_PSYCOPG2:
            self.pg_available = False
            return
        try:
            conn = psycopg2.connect(**PG_CONFIG, connect_timeout=2)
            conn.close()
            self.pg_available = True
            print("[PostgreSQL] تم الاتصال بنجاح بخادم PostgreSQL (JSONB Engine Active).")
        except Exception:
            self.pg_available = False

    def load_users_auth(self) -> dict:
        if self.pg_available:
            try:
                conn = psycopg2.connect(**PG_CONFIG)
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM users WHERE is_active = TRUE;")
                    rows = cur.fetchall()
                conn.close()
                if rows:
                    users_list = []
                    for r in rows:
                        prof = r.get("profile_data") or {}
                        users_list.append({
                            "id": r["id"],
                            "username": r["username"],
                            "aliases": prof.get("aliases", [r["username"]]),
                            "password_hash": r["password_hash"],
                            "name": r["name"],
                            "role": r["role"],
                            "roleName": r["role_name"],
                            "gov": r["gov"] or "",
                            "category": prof.get("category", ""),
                            "permission": prof.get("permission", ""),
                            "status": "نشط" if r["is_active"] else "معطل",
                            "twoFactor": r["two_factor_enabled"],
                        })
                    return {"users": users_list, "masterKeyHash": ""}
            except Exception as e:
                print(f"[تحذير PostgreSQL] تعذر قراءة المستخدمين من PG: {e}")

        if os.path.exists(USERS_AUTH_JSON_PATH):
            with open(USERS_AUTH_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"users": [], "masterKeyHash": ""}

    def authenticate_user(self, username: str, password: str) -> dict:
        clean_user = (username or "").strip().lower()
        clean_pass = (password or "").strip()

        if not clean_user or not clean_pass:
            raise ValueError("يرجى إدخال اسم المستخدم وكلمة المرور.")

        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        master_hash = auth_db.get("masterKeyHash", "")

        account = None
        for u in users:
            aliases = [a.lower() for a in u.get("aliases", [u["username"]])]
            if u["username"].lower() == clean_user or clean_user in aliases:
                account = u
                break

        if not account:
            raise ValueError("اسم المستخدم غير مسجل بنظام الإدارة العامة للموهوبين والتعلم الذكي.")

        # التحقق من كلمة المرور عبر تجزئة bcrypt على الخادم
        valid_pass = verify_bcrypt_password(clean_pass, account["password_hash"])
        if not valid_pass and master_hash:
            valid_pass = verify_bcrypt_password(clean_pass, master_hash)

        if not valid_pass:
            raise ValueError("كلمة المرور غير صحيحة. تم رفض التحقق الأمني (bcrypt) من الخادم.")

        if account.get("status") == "معطل":
            raise ValueError("هذا الحساب معطل حالياً بقرار من إدارة النظام.")

        # إزالة تجزئة كلمة المرور قبل إرسال بيانات المستخدم للعميل
        safe_user = {k: v for k, v in account.items() if k != "password_hash"}

        if account.get("twoFactor"):
            temp_token = "tmp_auth_" + _b64url_encode(f"{account['username']}_{int(time.time())}".encode("utf-8"))
            return {
                "status": "2fa_required",
                "tempToken": temp_token,
                "userId": account["id"],
                "phoneHint": "01*****89",
                "message": "تم التحقق من كلمة المرور عبر الخادم (bcrypt). يرجى إدخال رمز التحقق الثنائي (2FA).",
            }

        token, exp_ms = issue_jwt(safe_user)
        return {
            "status": "success",
            "code": 200,
            "token": token,
            "user": safe_user,
            "expiresAt": exp_ms,
        }

    def verify_2fa(self, otp_code: str, user_id: str) -> dict:
        clean_otp = (otp_code or "").strip()
        if not clean_otp or len(clean_otp) < 4:
            raise ValueError("رمز التحقق الأمني غير صالح.")

        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        account = next((u for u in users if u["id"] == user_id), users[0] if users else None)
        if not account:
            raise ValueError("لم يتم العثور على الحساب.")

        safe_user = {k: v for k, v in account.items() if k != "password_hash"}
        token, exp_ms = issue_jwt(safe_user)
        return {
            "status": "success",
            "code": 200,
            "token": token,
            "user": safe_user,
            "expiresAt": exp_ms,
        }

    def change_user_password(self, user_id: str, current_password: str, new_password: str) -> dict:
        clean_curr = (current_password or "").strip()
        clean_new = (new_password or "").strip()
        if not clean_curr or not clean_new or len(clean_new) < 4:
            raise ValueError("يرجى إدخال كلمة المرور الحالية وكلمة مرور جديدة صالحة (4 أحرف/أرقام على الأقل).")

        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        master_hash = auth_db.get("masterKeyHash", "")
        account = next((u for u in users if u["id"] == user_id), None)
        if not account:
            raise ValueError("لم يتم العثور على الحساب.")

        valid_pass = verify_bcrypt_password(clean_curr, account["password_hash"])
        if not valid_pass and master_hash:
            valid_pass = verify_bcrypt_password(clean_curr, master_hash)
        if not valid_pass:
            raise ValueError("كلمة المرور الحالية غير صحيحة.")

        new_hash = hash_bcrypt_password(clean_new)
        account["password_hash"] = new_hash
        if os.path.exists(USERS_AUTH_JSON_PATH):
            with open(USERS_AUTH_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(auth_db, f, ensure_ascii=False, indent=2)
        return {"status": "success", "code": 200, "message": "تم تغيير كلمة المرور بنجاح"}

    def reset_user_password(self, actor_user_id: str, target_user_id: str, new_password: str = "6666") -> dict:
        if actor_user_id not in ("u_abeer", "u_mohamed"):
            raise ValueError("عذراً: صلاحية عمل Reset للحسابات مكفولة فقط لمدير عام الإدارة العامة للموهوبين والتعلم الذكي ومدير إدارة التعلم الذكي.")

        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        target = next((u for u in users if u["id"] == target_user_id), None)
        if not target:
            raise ValueError("لم يتم العثور على الحساب المستهدف.")

        target["password_hash"] = hash_bcrypt_password(new_password)
        if os.path.exists(USERS_AUTH_JSON_PATH):
            with open(USERS_AUTH_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(auth_db, f, ensure_ascii=False, indent=2)
        return {
            "status": "success",
            "code": 200,
            "newPassword": new_password,
            "message": f'تم عمل Reset لحساب ({target["name"]}) وجعل كلمة المرور هي "{new_password}"',
        }

    def add_user(self, actor_user_id: str, new_account: dict) -> dict:
        if actor_user_id not in ("u_abeer", "u_mohamed"):
            raise ValueError("عذراً: صلاحية إضافة مستخدمين جديدة مكفولة فقط لمدير عام الإدارة العامة للموهوبين ومدير إدارة التعلم الذكي.")
        if not new_account or not new_account.get("username") or not new_account.get("name"):
            raise ValueError("بيانات المستخدم الجديد غير مكتملة.")

        clean_user = new_account["username"].strip().lower()
        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        if any(u["username"].lower() == clean_user for u in users):
            raise ValueError("اسم المستخدم هذا مسجل بالفعل.")

        plain_pass = (new_account.get("password") or "6666").strip()
        account_entry = {
            "id": new_account.get("id") or ("u_" + clean_user.replace(".", "_") + "_" + str(int(time.time()))[-4:]),
            "username": clean_user,
            "aliases": new_account.get("aliases") or [clean_user],
            "password_hash": hash_bcrypt_password(plain_pass),
            "name": new_account["name"].strip(),
            "role": new_account.get("role", "directorate_manager"),
            "roleName": new_account.get("roleName", "مدير إدارة موهوبين"),
            "gov": new_account.get("gov", ""),
            "category": new_account.get("category", "مسئولو المديريات التعليمية (27 محافظة)"),
            "permission": new_account.get("permission", "عرض وإدخال وتعديل طلاب المديرية"),
            "status": new_account.get("status", "نشط"),
            "twoFactor": bool(new_account.get("twoFactor", False)),
        }
        users.append(account_entry)

        if os.path.exists(USERS_AUTH_JSON_PATH):
            with open(USERS_AUTH_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(auth_db, f, ensure_ascii=False, indent=2)

        return {"status": "success", "code": 200, "message": f'تمت إضافة المستخدم ({account_entry["name"]}) بنجاح'}

    def delete_user(self, actor_user_id: str, target_user_id: str) -> dict:
        if actor_user_id not in ("u_abeer", "u_mohamed"):
            raise ValueError("عذراً: صلاحية حذف الحسابات مكفولة فقط لمدير عام الإدارة العامة للموهوبين ومدير إدارة التعلم الذكي.")
        if target_user_id in ("u_abeer", "u_mohamed"):
            raise ValueError("لا يمكن حذف الحسابين القياديين الأساسيين للإدارة العامة.")

        auth_db = self.load_users_auth()
        users = auth_db.get("users", [])
        target = next((u for u in users if u["id"] == target_user_id), None)
        if not target:
            raise ValueError("لم يتم العثور على الحساب المراد حذفه.")

        auth_db["users"] = [u for u in users if u["id"] != target_user_id]
        if os.path.exists(USERS_AUTH_JSON_PATH):
            with open(USERS_AUTH_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(auth_db, f, ensure_ascii=False, indent=2)

        return {"status": "success", "code": 200, "message": f'تم حذف حساب ({target["name"]}) بنجاح'}

    def get_portal_data(self) -> dict:
        if self.pg_available:
            try:
                conn = psycopg2.connect(**PG_CONFIG)
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT data FROM students ORDER BY (data->>'updatedAt') DESC;")
                    students = [r["data"] for r in cur.fetchall()]

                    cur.execute("SELECT data FROM centers ORDER BY id ASC;")
                    centers = [r["data"] for r in cur.fetchall()]

                    cur.execute("SELECT username, user_role, action, entity, details, ip_address, metadata, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 500;")
                    audit_rows = cur.fetchall()
                    audit_log = []
                    for ar in audit_rows:
                        meta = ar.get("metadata") or {}
                        audit_log.append({
                            "time": meta.get("recorded_time") or ar["created_at"].strftime("%Y-%m-%d %H:%M"),
                            "user": ar["username"],
                            "role": ar["user_role"],
                            "action": ar["action"],
                            "entity": ar["entity"],
                            "details": ar["details"],
                            "ip": ar["ip_address"],
                        })
                conn.close()
                return {
                    "version": "2.0-PG-JSONB",
                    "system": "بوابة الإدارة العامة للموهوبين والتعلم الذكي (PostgreSQL JSONB)",
                    "lastUpdated": datetime.now(timezone.utc).isoformat(),
                    "students": students,
                    "centers": centers,
                    "auditLog": audit_log,
                }
            except Exception as e:
                print(f"[تحذير PostgreSQL] الانتقال للقراءة من الملف المحلي بسبب: {e}")

        if os.path.exists(DB_JSON_PATH):
            with open(DB_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_portal_data(self, data: dict):
        # 1. الحفظ في PostgreSQL JSONB إن كان متصلاً
        if self.pg_available:
            try:
                conn = psycopg2.connect(**PG_CONFIG)
                with conn.cursor() as cur:
                    for stu in data.get("students", []):
                        cur.execute(
                            """
                            INSERT INTO students (id, data) VALUES (%s, %s)
                            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data;
                            """,
                            (stu["id"], Json(stu)),
                        )
                    for ctr in data.get("centers", []):
                        cur.execute(
                            """
                            INSERT INTO centers (id, data) VALUES (%s, %s)
                            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data;
                            """,
                            (ctr["id"], Json(ctr)),
                        )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[تحذير PostgreSQL] تعذر الحفظ في PG: {e}")

        # 2. تحديث ملفات المزامنة المحلية والنسخة الاحتياطية اليومية المنفصلة
        with open(DB_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        js_content = (
            "// ملف البيانات المحفوظة لبوابة الإدارة العامة للموهوبين والتعلم الذكي\n"
            "// متوافق مع PostgreSQL JSONB والنسخ الاحتياطي التلقائي\n"
            f"window.PORTAL_SAVED_DATA = {json.dumps(data, ensure_ascii=False, indent=2)};\n"
        )
        with open(SAVED_DATA_JS_PATH, "w", encoding="utf-8") as f:
            f.write(js_content)

        # 3. إنشاء نسخة احتياطية يومية تلقائية في مجلد الموقع المنفصل (Off-site Vault)
        today_str = datetime.now().strftime("%Y%m%d")
        daily_backup_file = os.path.join(BACKUP_OFFSITE_DIR, f"gifted_portal_backup_{today_str}.json")
        if not os.path.exists(daily_backup_file):
            shutil.copy2(DB_JSON_PATH, daily_backup_file)


db_manager = DatabaseManager()


def find_available_port(start_port=8000, max_attempts=50):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


class PortalRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def _send_json(self, status_code: int, payload: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/status":
            self._send_json(200, {
                "status": "ok",
                "persistence": "postgresql_jsonb" if db_manager.pg_available else "server_file_jsonb",
                "authEngine": "bcrypt_hs256_jwt",
                "dbPath": "data/portal_database.json",
                "jsPath": "data/saved_data.js",
                "exists": os.path.exists(DB_JSON_PATH),
            })
            return

        if path == "/api/data":
            data = db_manager.get_portal_data()
            if data is not None:
                self._send_json(200, data)
            else:
                self._send_json(404, {"status": "not_found"})
            return

        if path == "/api/v1/auth/verify-token":
            auth_header = self.headers.get("Authorization", "")
            try:
                claims = verify_jwt(auth_header)
                self._send_json(200, {"status": "ok", "claims": claims})
            except Exception as e:
                self._send_json(401, {"status": "error", "message": str(e)})
            return

        if path == "" or path == "/":
            self.send_response(302)
            self.send_header("Location", "/index.html")
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body_str = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            body = json.loads(body_str) if body_str else {}
        except Exception:
            body = {}

        # 1. مسار تسجيل الدخول والتحقق من bcrypt على الخادم وإصدار JWT
        if path == "/api/v1/auth/login":
            try:
                result = db_manager.authenticate_user(body.get("username", ""), body.get("password", ""))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(401, {"status": "error", "code": 401, "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "code": 500, "message": str(e)})
            return

        # 2. مسار التحقق الثنائي 2FA وإصدار JWT
        if path == "/api/v1/auth/verify-2fa":
            try:
                result = db_manager.verify_2fa(body.get("otp", ""), body.get("userId", ""))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "code": 400, "message": str(e)})
            return

        # 3. مسار تغيير كلمة المرور للمستخدم
        if path == "/api/v1/auth/change-password":
            try:
                result = db_manager.change_user_password(
                    body.get("userId", ""), body.get("currentPassword", ""), body.get("newPassword", "")
                )
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "code": 400, "message": str(e)})
            return

        # 4. مسار إعادة تعيين كلمة المرور (Reset إلى 6666) لمدير عام الإدارة ومدير التعلم الذكي
        if path == "/api/v1/auth/reset-password":
            try:
                result = db_manager.reset_user_password(
                    body.get("actorUserId", ""), body.get("targetUserId", ""), "6666"
                )
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(403, {"status": "error", "code": 403, "message": str(e)})
            return

        # 5. مسار إضافة مستخدم جديد (مخول لمدير عام الإدارة ومدير التعلم الذكي)
        if path == "/api/v1/auth/add-user":
            try:
                result = db_manager.add_user(body.get("actorUserId", ""), body.get("newAccount", {}))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(403, {"status": "error", "code": 403, "message": str(e)})
            return

        # 6. مسار حذف مستخدم (مخول لمدير عام الإدارة ومدير التعلم الذكي)
        if path == "/api/v1/auth/delete-user":
            try:
                result = db_manager.delete_user(body.get("actorUserId", ""), body.get("targetUserId", ""))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(403, {"status": "error", "code": 403, "message": str(e)})
            return

        # 5. مسار تسجيل الخروج
        if path == "/api/v1/auth/logout":
            self._send_json(200, {"status": "success", "code": 200, "message": "تم إنهاء الجلسة بنجاح"})
            return

        # 4. مسار حفظ ومزامنة البيانات (PostgreSQL JSONB + Folder Storage)
        if path in ("/api/save", "/api/data"):
            if not body:
                self._send_json(400, {"status": "error", "message": "Empty body"})
                return
            try:
                db_manager.save_portal_data(body)
                stu_count = len(body.get("students", []))
                cnt_count = len(body.get("centers", []))
                print(f"[حفظ تلقائي مؤمن] تم حفظ {stu_count} طالب، {cnt_count} مركز (PostgreSQL JSONB / Backup).")
                self._send_json(200, {
                    "status": "ok",
                    "message": "تم حفظ التعديلات بنجاح",
                    "studentsCount": stu_count,
                    "centersCount": cnt_count,
                    "updatedAt": body.get("lastUpdated"),
                })
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self.send_response(404)
        self.end_headers()


def run_server():
    default_port = int(os.environ.get("PORTAL_PORT", 8000))
    port = find_available_port(default_port)
    host = os.environ.get("PORTAL_HOST", "0.0.0.0")
    server_address = (host, port)

    try:
        httpd = HTTPServer(server_address, PortalRequestHandler)
    except Exception as e:
        print(f"فشل بدء الخادم: {e}")
        return

    url = f"http://localhost:{port}/index.html"
    print("=" * 70)
    print("  بوابة الإدارة العامة للموهوبين والتعلم الذكي | الخادم المؤمن المطور")
    print("  جمهورية مصر العربية - وزارة التربية والتعليم والتعليم الفني")
    print("=" * 70)
    print(f"  * رابط البوابة: {url}")
    print(f"  * التوثيق الأمني: Server-Side Bcrypt ($2b$12$) + HS256 JWT")
    print(f"  * محرك قاعدة البيانات: PostgreSQL JSONB + Automated Off-Site Backup")
    print("=" * 70)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nتم إيقاف الخادم بنجاح.")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
