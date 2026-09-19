# ─────────────────────────────────────────────────────────────────────────────
# Thai SET IR Universe — consolidate every local copy onto one drive (Windows)
#
# Keeps exactly ONE working copy, at D:\thai-set-ir, and removes copies sitting
# on any other drive (C:, OneDrive, USB sticks, …).
#
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\consolidate-repo.ps1
#       → dry run, shows the plan and deletes nothing
#   powershell -ExecutionPolicy Bypass -File scripts\consolidate-repo.ps1 -Apply
#       → actually moves and deletes
#   ... -Apply -Force        also deletes copies with uncommitted / unpushed work
#   ... -Dest 'E:\thai-set-ir'   use a different destination
#
# A copy with uncommitted changes or commits that are not on origin is REFUSED
# unless you pass -Force, so local work is never thrown away silently.
# ─────────────────────────────────────────────────────────────────────────────
[CmdletBinding()]
param(
    [string]$Dest = 'D:\thai-set-ir',
    [switch]$Apply,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$RemoteUrl = 'https://github.com/chatpongt/thai-set-ir'

function Test-IsRepoCopy([string]$dir) {
    if (-not (Test-Path (Join-Path $dir 'index.html'))) { return $false }
    if (-not (Test-Path (Join-Path $dir 'data\companies.js'))) { return $false }
    if (-not (Test-Path (Join-Path $dir '.git'))) { return $false }
    $url = & git -C $dir remote get-url origin 2>$null
    return ($LASTEXITCODE -eq 0 -and $url -match 'chatpongt/thai-set-ir')
}

# Normalise the destination so path comparisons below are reliable.
$DestParent = Split-Path -Parent $Dest
if (-not (Test-Path $DestParent)) {
    Write-Host "X ไม่พบไดรฟ์/โฟลเดอร์ปลายทาง $DestParent — เสียบไดรฟ์ D: แล้วลองใหม่" -ForegroundColor Red
    exit 1
}
$Dest = Join-Path (Resolve-Path $DestParent).Path (Split-Path -Leaf $Dest)

Write-Host "ปลายทางที่จะเก็บงานไว้: $Dest" -ForegroundColor Cyan
if (-not $Apply) {
    Write-Host "โหมด dry-run — ยังไม่ลบ/ย้ายอะไรทั้งนั้น (ใส่ -Apply เพื่อทำจริง)" -ForegroundColor Yellow
}
Write-Host ''

# ── Find every copy on every local (non-network) drive ───────────────────────
Write-Host 'กำลังค้นหา copy ทั้งหมด (อาจใช้เวลาสักครู่)...'
$found = [System.Collections.Generic.List[string]]::new()
$roots = Get-PSDrive -PSProvider FileSystem |
         Where-Object { $_.Root -match '^[A-Za-z]:\\$' } |
         Select-Object -ExpandProperty Root

foreach ($root in $roots) {
    # Match on data\companies.js rather than the folder name, so a renamed or
    # copied folder is still recognised. -Depth bounds the sweep; a repo buried
    # deeper than that needs -Dest.
    Get-ChildItem -LiteralPath $root -File -Recurse -Depth 6 `
                  -Filter 'companies.js' -ErrorAction SilentlyContinue |
    ForEach-Object {
        $dir = Split-Path -Parent (Split-Path -Parent $_.FullName)
        if ((Test-IsRepoCopy $dir) -and -not $found.Contains($dir)) { $found.Add($dir) }
    }
}

if ($found.Count -eq 0) {
    Write-Host 'ไม่พบ copy ในเครื่องเลย'
} else {
    Write-Host "พบ $($found.Count) copy:"
    $found | ForEach-Object { Write-Host "   - $_" }
}
Write-Host ''

# ── Make sure the canonical copy exists ──────────────────────────────────────
$keeper = $found | Where-Object { $_ -ieq $Dest } | Select-Object -First 1
$movedSrc = $null

if ($keeper) {
    Write-Host "มี copy อยู่ที่ปลายทางแล้ว: $keeper" -ForegroundColor Green
} elseif ($found.Count -gt 0) {
    $src = $found[0]
    $movedSrc = $src
    Write-Host "จะย้าย $src -> $Dest"
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
        Move-Item -LiteralPath $src -Destination $Dest
        $keeper = $Dest
        [void]$found.Remove($src)
        Write-Host '   ย้ายเรียบร้อย'
    }
} else {
    Write-Host "จะ clone ใหม่จาก $RemoteUrl -> $Dest"
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
        & git clone $RemoteUrl $Dest
        $keeper = $Dest
    }
}
Write-Host ''

# ── Remove the copies on other drives ────────────────────────────────────────
$deleted = 0
$skipped = 0
foreach ($dir in @($found)) {
    if ($dir -ieq $Dest) { continue }
    # In a dry run the move source is still in $found; listing it for deletion
    # too would contradict the move printed above.
    if ($movedSrc -and $dir -ieq $movedSrc) { continue }

    # Refuse to delete work that exists nowhere else.
    $reasons = @()
    if (& git -C $dir status --porcelain) { $reasons += 'มีไฟล์ที่ยังไม่ commit' }
    $unpushed = & git -C $dir log --branches --not --remotes --oneline 2>$null
    if ($unpushed) { $reasons += 'มี commit ที่ยังไม่ push' }

    if ($reasons.Count -gt 0 -and -not $Force) {
        Write-Host "ข้าม $dir — $($reasons -join ' + ')" -ForegroundColor Yellow
        if ($unpushed) { $unpushed | Select-Object -First 5 | ForEach-Object { Write-Host "        $_" } }
        Write-Host '        push งานก่อน แล้วรันซ้ำ (หรือใช้ -Force ถ้าจะทิ้งจริง ๆ)'
        $skipped++
        continue
    }

    $note = if ($reasons.Count -gt 0) { "  (-Force: ทิ้ง $($reasons -join ' + '))" } else { '' }
    Write-Host "ลบ $dir$note" -ForegroundColor Red
    if ($Apply) {
        Remove-Item -LiteralPath $dir -Recurse -Force
        $deleted++
    }
}

Write-Host ''
Write-Host '-----------------------------------------'
if ($Apply) {
    $kept = if ($keeper) { $keeper } else { $Dest }
    Write-Host "เสร็จแล้ว — เก็บไว้ที่ $kept, ลบไป $deleted copy, ข้าม $skipped copy"
} else {
    Write-Host 'dry-run จบ — รันซ้ำพร้อม -Apply เพื่อทำจริง'
}
