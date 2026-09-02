# win-ocr.ps1
# Extract all text from an image (or PDF first page) using the OCR engine that
# ships with Windows 10/11 -- no API key, fully local, runs offline.
#
# Why this exists: the arena upload channel that would hand an attached
# screenshot to the agent keeps failing to deliver the file, and the agent has
# no vision path. This lets the user read any screenshot themselves and paste
# the text back.
#
# Usage (Windows PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\win-ocr.ps1 -Path "C:\Users\45120\Pictures\screenshot.png"
#   (drag & drop the image onto the window also works if you edit -Path below)
#
# Notes:
#   - Works with png / jpg / bmp / gif. For a PDF, convert the page to png first
#     (e.g. open in an image viewer and "save as png"), or use a screenshot.
#   - The recognized text is printed to the console; copy it and paste it back.
param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = "Stop"
$null = [System.Reflection.Assembly]::Load("System.Runtime.WindowsRuntime")
$null = [Windows.Storage.StorageFile,   Windows.Storage,     ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,   Windows.Foundation,  ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]

# Await a WinRT IAsyncOperation<T> and return its .Result (async -> sync bridge).
function Await($WinRtTask, $ResultType) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
               Where-Object { $_.Name -eq "AsTask" -and
                              $_.GetParameters().Count -eq 1 -and
                              $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation`1" })[0]
    $netTask = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait() | Out-Null
    return $netTask.Result
}

$abs = (Resolve-Path $Path).Path
$file   = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($abs)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap  = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine  = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { Write-Error "No OCR language pack available. Install one in Settings > Time & Language > Language, or set a Chinese/English language." }
$result  = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

Write-Output "----- OCR text from: $abs -----"
Write-Output $result.Text
Write-Output "----- end -----"
