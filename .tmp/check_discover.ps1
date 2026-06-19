Write-Output 'HEALTH'
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health' | ConvertTo-Json -Depth 10
Write-Output 'DISCOVER'
try {
  Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/matter/discover' -TimeoutSec 30 | ConvertTo-Json -Depth 10
} catch {
  if ($_.ErrorDetails.Message) {
    Write-Output $_.ErrorDetails.Message
  } else {
    Write-Output $_.Exception.Message
  }
  exit 1
}
