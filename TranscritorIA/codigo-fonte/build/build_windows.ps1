<#
  Compila o Transcritor IA Local para Windows 10/11 (x64).

  Uso (PowerShell, na pasta do projeto):
    powershell -ExecutionPolicy Bypass -File build\build_windows.ps1            # tudo
    powershell -ExecutionPolicy Bypass -File build\build_windows.ps1 -SemWhisperCpp

  Requisitos para compilar (NÃO para usar o programa):
    - Python 3.12 x64
    - Para o motor Vulkan (AMD/Intel): Visual Studio 2022 Build Tools (C++), CMake, Git e Vulkan SDK
    - Para o instalador: Inno Setup 6 (opcional)
  Resultado:
    dist\TranscritorIA\                      programa (TranscritorIA.exe)
    dist-instalador\TranscritorIA_Portatil_<versão>.zip
    dist-instalador\TranscritorIA_Setup_<versão>.exe  (se o Inno Setup existir)
#>
param(
  [switch]$SemWhisperCpp,
  [switch]$SemTestes,
  [string]$WhisperCppTag = "v1.9.5",
  [string]$VulkanVersion = "1.4.313.2"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Version = (python -c "import transcritor; print(transcritor.__version__)").Trim()
Write-Host "== Transcritor IA $Version =="

function Step($t) { Write-Host "`n== $t ==" -ForegroundColor Cyan }

Step "Dependências Python"
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

if (-not $SemTestes) {
  Step "Testes automatizados"
  $env:QT_QPA_PLATFORM = "offscreen"
  python -m pytest tests -q
  if ($LASTEXITCODE -ne 0) { throw "Testes falharam" }
  Remove-Item Env:QT_QPA_PLATFORM
}

$Engines = Join-Path $Root "engines"
if (-not $SemWhisperCpp) {
  Step "whisper.cpp $WhisperCppTag (Vulkan + CPU)"
  if (-not $env:VULKAN_SDK) {
    $sdkRoot = "C:\VulkanSDK"
    if (-not (Test-Path $sdkRoot) -or -not (Get-ChildItem $sdkRoot -Directory -ErrorAction SilentlyContinue)) {
      Write-Host "Instalando Vulkan SDK $VulkanVersion…"
      $inst = Join-Path $env:TEMP "vulkansdk.exe"
      try {
        Invoke-WebRequest "https://sdk.lunarg.com/sdk/download/$VulkanVersion/windows/vulkansdk-windows-X64-$VulkanVersion.exe" -OutFile $inst
      } catch {
        Write-Host "Versão fixa indisponível; usando a mais recente."
        Invoke-WebRequest "https://sdk.lunarg.com/sdk/download/latest/windows/vulkan-sdk.exe" -OutFile $inst
      }
      & $inst --root "$sdkRoot\$VulkanVersion" --accept-licenses --default-answer --confirm-command install | Out-Host
    }
    $env:VULKAN_SDK = (Get-ChildItem $sdkRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
    $env:PATH = "$env:VULKAN_SDK\Bin;$env:PATH"
  }
  Write-Host "VULKAN_SDK = $env:VULKAN_SDK"
  $src = Join-Path $env:TEMP "whisper.cpp-$WhisperCppTag"
  if (-not (Test-Path $src)) { git clone --depth 1 --branch $WhisperCppTag https://github.com/ggml-org/whisper.cpp $src }
  # Instruções portáveis (AVX2/FMA): rodam em i7-10700, Ryzen e Core Ultra; nunca AVX-512 do compilador
  $common = @("-DGGML_NATIVE=OFF", "-DGGML_AVX=ON", "-DGGML_AVX2=ON", "-DGGML_FMA=ON", "-DGGML_F16C=ON",
              "-DBUILD_SHARED_LIBS=OFF", "-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF",
              "-DWHISPER_SDL2=OFF", "-DCMAKE_BUILD_TYPE=Release")
  foreach ($v in @(@{name="whispercpp-vulkan"; flags=@("-DGGML_VULKAN=ON")},
                   @{name="whispercpp-cpu"; flags=@("-DGGML_VULKAN=OFF")})) {
    $b = Join-Path $env:TEMP "wbuild-$($v.name)"
    cmake -S $src -B $b @common @($v.flags)
    if ($LASTEXITCODE -ne 0) { throw "cmake falhou ($($v.name))" }
    cmake --build $b --config Release -j 4 --target whisper-cli
    if ($LASTEXITCODE -ne 0) { throw "compilação falhou ($($v.name))" }
    $dst = Join-Path $Engines $v.name
    New-Item -ItemType Directory -Force $dst | Out-Null
    $exe = Get-ChildItem $b -Recurse -Filter whisper-cli.exe | Select-Object -First 1
    Copy-Item $exe.FullName $dst -Force
    Get-ChildItem $exe.DirectoryName -Filter *.dll -ErrorAction SilentlyContinue | Copy-Item -Destination $dst -Force
    Copy-Item (Join-Path $src "LICENSE") (Join-Path $dst "LICENSE-whisper.cpp.txt") -Force
    & (Join-Path $dst "whisper-cli.exe") --help 2>&1 | Select-Object -First 3 | Out-Host
  }
}

Step "PyInstaller"
pyinstaller --noconfirm --clean --distpath dist --workpath build\pyi-work build\TranscritorIA.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }
$App = Join-Path $Root "dist\TranscritorIA"
if (Test-Path $Engines) { Copy-Item $Engines (Join-Path $App "engines") -Recurse -Force }
Copy-Item README.md, LICENSE.txt -Destination $App -ErrorAction SilentlyContinue

Step "Teste rápido do executável"
& (Join-Path $App "TranscritorIA-cli.exe") --diagnostico
if ($LASTEXITCODE -ne 0) { throw "Executável não iniciou" }

Step "Pacotes"
$Out = Join-Path $Root "dist-instalador"
New-Item -ItemType Directory -Force $Out | Out-Null
$Port = Join-Path $env:TEMP "TranscritorIA_portatil"
if (Test-Path $Port) { Remove-Item $Port -Recurse -Force }
Copy-Item $App $Port -Recurse
Set-Content (Join-Path $Port "portable.txt") "Modo portátil: modelos e configurações ficam na pasta 'dados' ao lado do programa."
$zip = Join-Path $Out "TranscritorIA_Portatil_$Version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$Port\*" -DestinationPath $zip -CompressionLevel Optimal
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) { & $iscc "/DAppVersion=$Version" build\installer.iss } else { Write-Host "Inno Setup não encontrado: instalador não gerado (o .zip portátil foi)." }
Get-ChildItem $Out | Format-Table Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}}
