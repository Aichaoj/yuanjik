# 安装 Android SDK + Gradle 并构建数显壳 APK（后台执行，日志写入 build.log）
$ErrorActionPreference = 'Continue'
$log = 'D:\Deepseek智能体\AI元健康\shuzi\_app\build.log'
function Log($m) { $t = Get-Date -Format 'HH:mm:ss'; "$t $m" | Tee-Object -FilePath $log -Append }

$sdk = 'C:\android-sdk'
$tools = "$sdk\cmdline-tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

if (-not (Test-Path "$tools\latest\bin\sdkmanager.bat")) {
    Log 'downloading commandline-tools'
    $zip = "$env:TEMP\cmdline-tools.zip"
    Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip' -OutFile $zip -TimeoutSec 600
    Log ("downloaded " + (Get-Item $zip).Length)
    Expand-Archive -Path $zip -DestinationPath "$env:TEMP\cmdline-tools" -Force
    Move-Item "$env:TEMP\cmdline-tools\cmdline-tools" "$tools\latest" -Force
}
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:JAVA_HOME = 'C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot'

$sdkm = "$tools\latest\bin\sdkmanager.bat"
Log 'accepting licenses'
' y' * 30 | & $sdkm --sdk_root=$sdk --licenses 2>&1 | Out-Null
Log 'installing platform-tools / platform 34 / build-tools 34'
& $sdkm --sdk_root=$sdk 'platform-tools' 'platforms;android-34' 'build-tools;34.0.0' 2>&1 | ForEach-Object { Log $_ }
Log ('sdk done, exists build-tools: ' + (Test-Path "$sdk\build-tools\34.0.0"))

$gradleDir = 'C:\gradle'
if (-not (Test-Path "$gradleDir\gradle-8.7\bin\gradle.bat")) {
    Log 'downloading gradle 8.7'
    $gz = "$env:TEMP\gradle.zip"
    Invoke-WebRequest -Uri 'https://services.gradle.org/distributions/gradle-8.7-bin.zip' -OutFile $gz -TimeoutSec 600
    Expand-Archive -Path $gz -DestinationPath $gradleDir -Force
}
$gradle = "$gradleDir\gradle-8.7\bin\gradle.bat"
Log ('gradle exists: ' + (Test-Path $gradle))

$proj = 'D:\Deepseek智能体\AI元健康\shuzi\_app\shell'
Set-Content -LiteralPath "$proj\local.properties" -Encoding ASCII -Value "sdk.dir=C\:\\android-sdk"

Log 'building debug apk'
& $gradle -p $proj assembleDebug --no-daemon 2>&1 | ForEach-Object { Log $_ }

$apk = Get-ChildItem -Path "$proj\app\build\outputs\apk" -Recurse -Include *.apk -ErrorAction SilentlyContinue | Select-Object -First 1
if ($apk) { Log ("APK OK: " + $apk.FullName + " size=" + $apk.Length) } else { Log 'APK FAILED' }
Log 'DONE'
