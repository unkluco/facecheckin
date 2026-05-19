param(
  [string]$DistDir = "$PSScriptRoot\dist\FaceCheckin",
  [string]$OutputDir = "$PSScriptRoot\installer",
  [string]$ProductName = "FaceCheckin",
  [string]$Manufacturer = "FaceCheckin",
  [string]$Version = "0.1.0",
  [string]$IconPath = "$PSScriptRoot\assets\FaceCheckin.ico"
)

$ErrorActionPreference = "Stop"

function Find-Tool($name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $commonDirs = @(
    "${env:ProgramFiles(x86)}\WiX Toolset v3.14\bin",
    "${env:ProgramFiles(x86)}\WiX Toolset v3.11\bin",
    "$env:ProgramFiles\WiX Toolset v3.14\bin",
    "$env:ProgramFiles\WiX Toolset v3.11\bin"
  )
  foreach ($dir in $commonDirs) {
    if (-not [string]::IsNullOrWhiteSpace($dir)) {
      $candidate = Join-Path $dir $name
      if (Test-Path $candidate) { return $candidate }
    }
  }
  return $null
}

$candle = Find-Tool "candle.exe"
$light = Find-Tool "light.exe"

if (-not $candle -or -not $light) {
  Write-Host "[ERROR] Không tìm thấy WiX Toolset v3 (candle.exe/light.exe)." -ForegroundColor Red
  Write-Host "Cài WiX Toolset rồi chạy lại script này." -ForegroundColor Yellow
  Write-Host "Gợi ý: winget install WiXToolset.WiXToolset"
  exit 1
}

if (-not (Test-Path "$DistDir\FaceCheckin.exe")) {
  throw "Không tìm thấy FaceCheckin.exe trong $DistDir. Hãy build PyInstaller trước."
}

if (-not (Test-Path $IconPath)) {
  throw "Không tìm thấy icon installer tại $IconPath."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$wxsPath = Join-Path $OutputDir "FaceCheckin.wxs"
$wixObj = Join-Path $OutputDir "FaceCheckin.wixobj"
$msiPath = Join-Path $OutputDir "FaceCheckin-$Version.msi"

$productGuid = "*"
$upgradeGuid = "9F32C5E0-7945-4F5A-A86F-2CB8D7DD8F80"

$dirChildren = @{}
$dirNames = @{}
$components = New-Object System.Collections.Generic.List[string]
$componentRefs = New-Object System.Collections.Generic.List[string]
$dirIds = @{}
$componentIndex = 0
$dirIndex = 0

function XmlEscape([string]$value) {
  return [System.Security.SecurityElement]::Escape($value)
}

$iconSource = XmlEscape ([System.IO.Path]::GetFullPath($IconPath))

function IdSafe([string]$value) {
  $safe = $value -replace '[^A-Za-z0-9_]', '_'
  if ($safe -match '^[0-9]') { $safe = "X_$safe" }
  return $safe
}

function Get-RelativePathCompat([string]$basePath, [string]$targetPath) {
  $baseFull = [System.IO.Path]::GetFullPath($basePath).TrimEnd('\') + '\'
  $targetFull = [System.IO.Path]::GetFullPath($targetPath)
  $baseUri = New-Object System.Uri($baseFull)
  $targetUri = New-Object System.Uri($targetFull)
  $relativeUri = $baseUri.MakeRelativeUri($targetUri)
  return [System.Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', '\')
}

function Get-DirId([string]$relativeDir) {
  if ([string]::IsNullOrWhiteSpace($relativeDir) -or $relativeDir -eq ".") { return "INSTALLFOLDER" }
  if ($dirIds.ContainsKey($relativeDir)) { return $dirIds[$relativeDir] }
  $script:dirIndex += 1
  $id = "DIR_$script:dirIndex"
  $dirIds[$relativeDir] = $id
  return $id
}

Get-ChildItem -Path $DistDir -Directory -Recurse | Sort-Object FullName | ForEach-Object {
  $relative = Get-RelativePathCompat $DistDir $_.FullName
  $parentRelative = Split-Path $relative -Parent
  [void](Get-DirId $relative)
  $dirNames[$relative] = $_.Name
  if ([string]::IsNullOrWhiteSpace($parentRelative)) { $parentRelative = "." }
  if (-not $dirChildren.ContainsKey($parentRelative)) {
    $dirChildren[$parentRelative] = New-Object System.Collections.Generic.List[string]
  }
  $dirChildren[$parentRelative].Add($relative)
}

function Render-DirectoryTree([string]$relativeDir, [int]$indent) {
  if (-not $dirChildren.ContainsKey($relativeDir)) { return "" }
  $pad = " " * $indent
  $parts = New-Object System.Collections.Generic.List[string]
  foreach ($child in ($dirChildren[$relativeDir] | Sort-Object)) {
    $id = Get-DirId $child
    $name = XmlEscape $dirNames[$child]
    $nested = Render-DirectoryTree $child ($indent + 2)
    if ($nested) {
      $parts.Add("$pad<Directory Id=`"$id`" Name=`"$name`">`r`n$nested`r`n$pad</Directory>")
    } else {
      $parts.Add("$pad<Directory Id=`"$id`" Name=`"$name`" />")
    }
  }
  return ($parts -join "`r`n")
}

$installSubdirs = Render-DirectoryTree "." 8

Get-ChildItem -Path $DistDir -File -Recurse | Sort-Object FullName | ForEach-Object {
  $componentIndex += 1
  $relative = Get-RelativePathCompat $DistDir $_.FullName
  $relativeDir = Split-Path $relative -Parent
  $dirId = Get-DirId $relativeDir
  $componentId = "cmp_$componentIndex"
  $fileId = "fil_$componentIndex"
  $source = XmlEscape $_.FullName
  $name = XmlEscape $_.Name
  $components.Add(@"
    <DirectoryRef Id="$dirId">
      <Component Id="$componentId" Guid="*" Win64="yes">
        <File Id="$fileId" Source="$source" Name="$name" KeyPath="yes" />
      </Component>
    </DirectoryRef>
"@)
  $componentRefs.Add("      <ComponentRef Id=`"$componentId`" />")
}

$wxs = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="$productGuid" Name="$ProductName" Language="1033" Version="$Version" Manufacturer="$Manufacturer" UpgradeCode="$upgradeGuid">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perUser" Platform="x64" />
    <MajorUpgrade DowngradeErrorMessage="A newer version of $ProductName is already installed." />
    <MediaTemplate EmbedCab="yes" />
    <Icon Id="FaceCheckinIcon" SourceFile="$iconSource" />
    <Property Id="ARPPRODUCTICON" Value="FaceCheckinIcon" />

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="LocalAppDataFolder">
        <Directory Id="INSTALLFOLDER" Name="$ProductName">
$installSubdirs
        </Directory>
      </Directory>
      <Directory Id="DesktopFolder" />
      <Directory Id="ProgramMenuFolder">
        <Directory Id="ApplicationProgramsFolder" Name="$ProductName" />
      </Directory>
    </Directory>

    <DirectoryRef Id="ApplicationProgramsFolder">
      <Component Id="cmp_StartMenuShortcut" Guid="*" Win64="yes">
        <Shortcut Id="StartMenuShortcut" Name="$ProductName" Description="Open $ProductName" Target="[INSTALLFOLDER]FaceCheckin.exe" WorkingDirectory="INSTALLFOLDER" Icon="FaceCheckinIcon" />
        <RemoveFolder Id="ApplicationProgramsFolder" On="uninstall" />
        <RegistryValue Root="HKCU" Key="Software\$ProductName" Name="installed" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </DirectoryRef>

    <DirectoryRef Id="DesktopFolder">
      <Component Id="cmp_DesktopShortcut" Guid="*" Win64="yes">
        <Shortcut Id="DesktopShortcut" Name="$ProductName" Description="Open $ProductName" Target="[INSTALLFOLDER]FaceCheckin.exe" WorkingDirectory="INSTALLFOLDER" Icon="FaceCheckinIcon" />
        <RegistryValue Root="HKCU" Key="Software\$ProductName" Name="desktopShortcut" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </DirectoryRef>

$($components -join "`r`n")

    <Feature Id="DefaultFeature" Title="$ProductName" Level="1">
$($componentRefs -join "`r`n")
      <ComponentRef Id="cmp_StartMenuShortcut" />
      <ComponentRef Id="cmp_DesktopShortcut" />
    </Feature>
  </Product>
</Wix>
"@

Set-Content -Path $wxsPath -Value $wxs -Encoding UTF8
& $candle -arch x64 -out $wixObj $wxsPath
if ($LASTEXITCODE -ne 0) { throw "WiX candle failed with exit code $LASTEXITCODE" }
& $light -sice:ICE38 -sice:ICE64 -sice:ICE91 -out $msiPath $wixObj
if ($LASTEXITCODE -ne 0) { throw "WiX light failed with exit code $LASTEXITCODE" }

Write-Host "[OK] MSI created: $msiPath" -ForegroundColor Green
