$body = @{
  name = "Test RGB"
  qr_code = "matter://20159913864"
} | ConvertTo-Json

$start = Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/matter/pair" -Method Post -ContentType "application/json" -Body $body
Write-Output "JOB_START"
$start | ConvertTo-Json -Depth 10
Start-Sleep -Seconds 10
$status = Invoke-RestMethod -Uri ("http://127.0.0.1:5000/api/matter/pair/" + $start.job_id) -Method Get
Write-Output "JOB_STATUS"
$status | ConvertTo-Json -Depth 10
