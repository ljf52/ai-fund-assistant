$Ports = 8010, 4173
foreach ($Port in $Ports) {
  $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($Listener in $Listeners) {
    Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
  }
}
Write-Host 'AI Fund Assistant stopped.'
