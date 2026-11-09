-- =============================================================================
-- بوابة الإدارة العامة للموهوبين والتعلم الذكي
-- وزارة التربية والتعليم والتعليم الفني - جمهورية مصر العربية
-- مخطط قاعدة البيانات المؤسسية (PostgreSQL + JSONB Hybrid Schema)
-- =============================================================================

-- تفعيل الامتدادات الضرورية للبحث النصي العربي والتشفير والمعرفات
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. جدول المستخدمين والحسابات الرسمية (Users & Authentication)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL, -- تجزئة bcrypt ($2b$12$...)
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,           -- general_admin, general_viewer, directorate_manager
    role_name VARCHAR(255) NOT NULL,
    gov VARCHAR(100) DEFAULT '',         -- نطاق المديرية التعليمية (فارغ للإدارة العامة)
    is_active BOOLEAN DEFAULT TRUE,
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    profile_data JSONB DEFAULT '{}'::jsonb, -- بيانات الحساب الإضافية (aliases, category, permission)
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. جدول الطلاب الموهوبين والمبتكرين والفائقين وذوي الهمم (Students JSONB)
-- =============================================================================
CREATE TABLE IF NOT EXISTS students (
    id VARCHAR(64) PRIMARY KEY,          -- مثل STU-2026-001
    data JSONB NOT NULL,                 -- وثيقة JSONB شاملة لبيانات الطالب والملف التراكمي
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 3. جدول مراكز رعاية الموهوبين والتعلم الذكي الـ 164 (Centers JSONB)
-- =============================================================================
CREATE TABLE IF NOT EXISTS centers (
    id VARCHAR(64) PRIMARY KEY,          -- مثل CTR-001
    data JSONB NOT NULL,                 -- وثيقة JSONB لبيانات المركز والتجهيزات والجاهزية
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 4. جدول سجل التدقيق الأمني والعمليات (Audit Log JSONB)
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(150) NOT NULL,
    user_role VARCHAR(150),
    action VARCHAR(150) NOT NULL,
    entity VARCHAR(255),
    details TEXT,
    ip_address VARCHAR(64),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 5. جدول البرامج الإثرائية، ورش العمل، والمسابقات (Workshops & Competitions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS portal_configs (
    config_key VARCHAR(100) PRIMARY KEY, -- مثل workshops_sem1, workshops_sem2, competitions, rubrics
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 6. دالة وتريجر التحديث التلقائي للطابع الزمني (updated_at)
-- =============================================================================
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS trg_students_updated_at ON students;
CREATE TRIGGER trg_students_updated_at
BEFORE UPDATE ON students
FOR EACH ROW EXECUTE FUNCTION update_modified_column();

DROP TRIGGER IF EXISTS trg_centers_updated_at ON centers;
CREATE TRIGGER trg_centers_updated_at
BEFORE UPDATE ON centers
FOR EACH ROW EXECUTE FUNCTION update_modified_column();
