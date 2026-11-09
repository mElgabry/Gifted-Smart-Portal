-- =============================================================================
-- بوابة الإدارة العامة للموهوبين والتعلم الذكي
-- استراتيجية الفهرسة المتقدمة (B-Tree Expression, GIN JSONB, pg_trgm)
-- =============================================================================

-- =============================================================================
-- 1. فهارس جدول المستخدمين (Users Indexes)
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);
CREATE INDEX IF NOT EXISTS idx_users_gov ON users (gov);
CREATE INDEX IF NOT EXISTS idx_users_aliases_gin ON users USING GIN ((profile_data->'aliases'));

-- =============================================================================
-- 2. فهارس جدول الطلاب (Students JSONB Indexes)
-- =============================================================================

-- أ. فهرس فريد للرقم القومي لمنع تكرار قيد الطالب على مستوى الجمهورية
CREATE UNIQUE INDEX IF NOT EXISTS idx_students_nid_unique 
ON students (((data->>'nid')));

-- ب. فهرس مركب للمحافظة والإدارة التعليمية (لتسريع التصفية حسب الصلاحيات الجغرافية)
CREATE INDEX IF NOT EXISTS idx_students_gov_dept 
ON students (((data->>'gov')), ((data->>'dept')));

-- ج. فهرس حالة الاعتماد (معتمد، مرسل للاعتماد، مسودة، مرفوض)
CREATE INDEX IF NOT EXISTS idx_students_status 
ON students (((data->>'status')));

-- د. فهرس مركب للمرحلة الدراسية والصف الدراسي
CREATE INDEX IF NOT EXISTS idx_students_stage_grade 
ON students (((data->>'stage')), ((data->>'grade')));

-- هـ. فهرس لمجال الموهبة ومستوى الموهبة
CREATE INDEX IF NOT EXISTS idx_students_talent 
ON students (((data->>'talent')), ((data->>'giftLevel')));

-- و. فهرس لفرز الطلاب حسب النسبة المئوية للتحصيل الدراسي تنازلياً
CREATE INDEX IF NOT EXISTS idx_students_percentage_desc 
ON students ((((data->>'percentage')::numeric)) DESC NULLS LAST);

-- ز. فهرس لفرز الطلاب حسب تاريخ آخر تحديث تنازلياً
CREATE INDEX IF NOT EXISTS idx_students_updated_at_desc 
ON students (((data->>'updatedAt')) DESC);

-- ح. فهرس GIN شامل لوثيقة JSONB باستخدام jsonb_path_ops لاستعلامات الاحتواء السريعة (@>)
CREATE INDEX IF NOT EXISTS idx_students_data_gin_path 
ON students USING GIN (data jsonb_path_ops);

-- ط. فهرس GIN لمصفوفة التصنيفات (موهوبين، مبتكرين، فائقين، ذوي همم)
CREATE INDEX IF NOT EXISTS idx_students_categories_gin 
ON students USING GIN ((data->'categories'));

-- ي. فهارس البحث النصي العربي السريع والضبابي (Trigram Indexes) لاسم الطالب والمدرسة
CREATE INDEX IF NOT EXISTS idx_students_name_trgm 
ON students USING GIN (((data->>'name')) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_students_school_trgm 
ON students USING GIN (((data->>'school')) gin_trgm_ops);

-- =============================================================================
-- 3. فهارس جدول مراكز الموهوبين الـ 164 (Centers JSONB Indexes)
-- =============================================================================

-- أ. فهرس مركب للمحافظة والإدارة التعليمية للمراكز
CREATE INDEX IF NOT EXISTS idx_centers_gov_dept 
ON centers (((data->>'gov')), ((data->>'dept')));

-- ب. فهرس حالة المركز (مفعل ومجهز بالكامل، مفعل جزئياً، يحتاج دعم)
CREATE INDEX IF NOT EXISTS idx_centers_status 
ON centers (((data->>'status')));

-- ج. فهرس رقمي لنسبة الجاهزية للفرز التنازلي والتصاعدي
CREATE INDEX IF NOT EXISTS idx_centers_readiness_desc 
ON centers ((((data->>'readiness')::int)) DESC);

-- د. فهرس GIN لكائن التجهيزات (equipment) للبحث عن المراكز المجهزة بالروبوت أو الإنترنت
CREATE INDEX IF NOT EXISTS idx_centers_equipment_gin 
ON centers USING GIN ((data->'equipment'));

-- هـ. فهرس البحث النصي العربي (Trigram) لاسم المركز والمدرسة المضيفة
CREATE INDEX IF NOT EXISTS idx_centers_name_trgm 
ON centers USING GIN (((data->>'name')) gin_trgm_ops);

-- =============================================================================
-- 4. فهارس سجل التدقيق الأمني (Audit Logs Indexes)
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at_desc ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs (username);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_metadata_gin ON audit_logs USING GIN (metadata);
