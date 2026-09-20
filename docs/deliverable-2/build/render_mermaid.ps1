$ErrorActionPreference = "Continue"
$base = "C:\Users\User\Dev\DigitalTransformationProject\docs\deliverable-2"
$log = "$base\build\mermaid-render.log"
"START $(Get-Date -Format o)" | Out-File -FilePath $log -Encoding utf8
$pkg = "@mermaid-js/mermaid-cli@11"
foreach ($n in @("c4-level1-context", "c4-level2-containers", "c4-level3-components")) {
    "--- $n ---" | Out-File -FilePath $log -Append -Encoding utf8
    $in = "$base\build\$n.mmd"
    $out = "$base\figures\$n.png"
    # -p pins a large virtual window: mermaid-cli caps C4 rows by screen.availWidth (mermaid-cli#440),
    # so without it UpdateLayoutConfig($c4ShapeInRow=...) is silently throttled on headless machines.
    & npx.cmd --yes $pkg -i $in -o $out -b white -s 3 -w 1600 -p "$base\build\puppeteer.json" *>> $log
    "EXIT=$LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8
}
"DONE $(Get-Date -Format o)" | Out-File -FilePath $log -Append -Encoding utf8
