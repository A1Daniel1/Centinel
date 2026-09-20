$ErrorActionPreference = "Continue"
$log = "C:\Users\User\Dev\DigitalTransformationProject\docs\deliverable-2\build\miktex-install.log"
"START $(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8
$mpm = "C:\Users\User\AppData\Local\Programs\MiKTeX\miktex\bin\x64\mpm.exe"
foreach ($p in @("babel-spanish", "newunicodechar", "listingsutf8", "pmboxdraw", "seqsplit", "ragged2e")) {
    "--- install $p ---" | Out-File -FilePath $log -Append -Encoding utf8
    & $mpm --install=$p *>> $log
    "EXIT=$LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8
}
"DONE $(Get-Date -Format o)" | Out-File -FilePath $log -Append -Encoding utf8
