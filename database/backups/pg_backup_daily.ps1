# ==============================================================================
# بوابة الإدارة العامة للموهوبين والتعلم الذكي
# سكريبت النسخ الاحتياطي اليومي الآلي والنقل لموقع منفصل (PowerShell - Windows)
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DbName = if ($env:PG_DB) { $env:PG_DB } else { "gifted_portal_db" }
$DbUser = if ($env:PG_USER) { $env:PG_USER } else { "postgres" }
$DbHost = if ($env:PG_HOST) { $env:PG_HOST } else { "127.0.0.1" }
$DbPort = if ($env:PG_PORT) { $env:PG_PORT } else { "5432" }

$LocalBackupDir = "C:\PostgresBackups\GiftedPortal"
$OffsiteNetworkDir = "\\10.20.30.100\OffsiteVault\GiftedPortalBackups"
$S3Bucket = "s3://moe-gifted-offsite-backups/postgresql/daily"

if (-not (Test-Path $LocalBackupDir)) {
    New-Item -ItemType Directory -Path $LocalBackupDir -Force | Out-Null
}

$DumpFile = Join-Path $LocalBackupDir "${DbName}_${Timestamp}.dump"
$HashFile = "${DumpFile}.sha256"
$LogFile = Join-Path $LocalBackupDir "backup_log.txt"

function Write-BackupLog($Message) {
    $Line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
    Write-Host $Line -ForegroundColor Cyan
}

Write-BackupLog "بدء النسخ الاحتياطي اليومي لقاعدة البيانات ($DbName)..."
& pg_dump -h $DbHost -p $DbPort -U $DbUser -d $DbName -F c -b -v -f $DumpFile 2>> $LogFile

$FileHash = (Get-FileHash -Path $DumpFile -Algorithm SHA256).Hash
Set-Content -Path $HashFile -Value "$FileHash  $(Split-Path $DumpFile -Leaf)" -Encoding UTF8
Write-BackupLog "تم إنشاء النسخة الاحتياطية وحساب البصمة الرقمية SHA-256: $FileHash"

if (Test-Path $OffsiteNetworkDir) {
    Copy-Item -Path $DumpFile -Destination $OffsiteNetworkDir -Force
    Copy-Item -Path $HashFile -Destination $OffsiteNetworkDir -Force
    Write-BackupLog "تم نقل النسخة الاحتياطية إلى الخادم المنفصل عبر الشبكة ($OffsiteNetworkDir)."
}

Get-ChildItem -Path $LocalBackupDir -Filter "*.dump*" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force
Write-BackupLog "تم تطبيق سياسة الاستبقاء وحذف النسخ المحلية القديمة بنجاح."
