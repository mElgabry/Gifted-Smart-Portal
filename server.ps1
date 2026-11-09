# server.ps1 - خادم محلي لبوابة الموهوبين والتعلم الذكي عبر PowerShell (ويندوز)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$baseDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir = Join-Path $baseDir "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
}
$dbPath = Join-Path $dataDir "portal_database.json"
$jsPath = Join-Path $dataDir "saved_data.js"

$port = 8000
$started = $false
$listener = $null

while (-not $started -and $port -lt 8050) {
    try {
        $listener = New-Object System.Net.HttpListener
        $listener.Prefixes.Add("http://localhost:$port/")
        $listener.Start()
        $started = $true
    } catch {
        if ($listener -ne $null) { $listener.Close() }
        $port++
    }
}

if (-not $started) {
    Write-Host "تعذر تشغيل الخادم على المنافذ من 8000 إلى 8050." -ForegroundColor Red
    Start-Process (Join-Path $baseDir "index.html")
    exit
}

$url = "http://localhost:$port/index.html"
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  بوابة الإدارة العامة للموهوبين والتعلم الذكي | الخادم المحلي" -ForegroundColor Yellow
Write-Host "  جمهورية مصر العربية - وزارة التربية والتعليم والتعليم الفني" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  * رابط البوابة: $url" -ForegroundColor White
Write-Host "  * الحفظ التلقائي: مفعّل مباشرة داخل المجلد (data/portal_database.json)" -ForegroundColor Green
Write-Host "  * عند نقل هذا المجلد لأي جهاز آخر ستظل البيانات والتعديلات محفوظة." -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  جاري فتح المتصفح تلقائياً... (اضغط Ctrl+C لإيقاف الخادم)" -ForegroundColor Gray

Start-Process $url

$mimeMap = @{
    ".html" = "text/html; charset=utf-8"
    ".htm"  = "text/html; charset=utf-8"
    ".js"   = "application/javascript; charset=utf-8"
    ".json" = "application/json; charset=utf-8"
    ".css"  = "text/css; charset=utf-8"
    ".png"  = "image/png"
    ".jpg"  = "image/jpeg"
    ".jpeg" = "image/jpeg"
    ".gif"  = "image/gif"
    ".svg"  = "image/svg+xml"
    ".ico"  = "image/x-icon"
    ".pdf"  = "application/pdf"
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        $response.Headers.Add("Access-Control-Allow-Origin", "*")
        $response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.Headers.Add("Access-Control-Allow-Headers", "Content-Type")
        $response.Headers.Add("Cache-Control", "no-cache, no-store, must-revalidate")

        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 200
            $response.Close()
            continue
        }

        $rawUrl = $request.Url.LocalPath.TrimEnd('/')

        if ($rawUrl -eq "/api/status" -and $request.HttpMethod -eq "GET") {
            $response.ContentType = "application/json; charset=utf-8"
            $statusObj = @{
                status = "ok"
                persistence = "server_ps1"
                dbPath = "data/portal_database.json"
                exists = (Test-Path $dbPath)
            }
            $jsonStr = $statusObj | ConvertTo-Json
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)
            $response.ContentLength64 = $bytes.Length
            $response.OutputStream.Write($bytes, 0, $bytes.Length)
            $response.Close()
            continue
        }

        if ($rawUrl -eq "/api/data" -and $request.HttpMethod -eq "GET") {
            if (Test-Path $dbPath) {
                $response.ContentType = "application/json; charset=utf-8"
                $bytes = [System.IO.File]::ReadAllBytes($dbPath)
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } else {
                $response.StatusCode = 404
            }
            $response.Close()
            continue
        }

        if (($rawUrl -eq "/api/save" -or $rawUrl -eq "/api/data") -and $request.HttpMethod -eq "POST") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $body = $reader.ReadToEnd()
                $reader.Close()

                [System.IO.File]::WriteAllText($dbPath, $body, [System.Text.Encoding]::UTF8)

                $jsContent = "// ملف البيانات المحفوظة لبوابة الإدارة العامة للموهوبين والتعلم الذكي`nwindow.PORTAL_SAVED_DATA = $body;`n"
                [System.IO.File]::WriteAllText($jsPath, $jsContent, [System.Text.Encoding]::UTF8)

                Write-Host "[حفظ تلقائي] تم حفظ التعديلات بنجاح في مجلد data." -ForegroundColor Green

                $response.ContentType = "application/json; charset=utf-8"
                $respObj = @{ status = "ok"; message = "Saved to folder successfully" } | ConvertTo-Json
                $respBytes = [System.Text.Encoding]::UTF8.GetBytes($respObj)
                $response.ContentLength64 = $respBytes.Length
                $response.OutputStream.Write($respBytes, 0, $respBytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        $relPath = $request.Url.LocalPath.TrimStart('/')
        if ([string]::IsNullOrEmpty($relPath)) {
            $relPath = "index.html"
        }
        $filePath = Join-Path $baseDir ($relPath.Replace('/', [System.IO.Path]::DirectorySeparatorChar))

        if (Test-Path $filePath -PathType Leaf) {
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            $mime = "application/octet-stream"
            if ($mimeMap.ContainsKey($ext)) {
                $mime = $mimeMap[$ext]
            }
            $response.ContentType = $mime
            $fileBytes = [System.IO.File]::ReadAllBytes($filePath)
            $response.ContentLength64 = $fileBytes.Length
            $response.OutputStream.Write($fileBytes, 0, $fileBytes.Length)
        } else {
            $response.StatusCode = 404
        }
        $response.Close()
    }
} finally {
    if ($listener -ne $null) {
        $listener.Stop()
        $listener.Close()
    }
}
