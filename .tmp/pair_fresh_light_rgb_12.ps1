$ErrorActionPreference = 'Stop'
$body = @{
  name = 'Zarowka RGB'
  vendor = 'matter-sim'
  endpoint = '1'
  pairing_code = '20054912334'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:5000/api/matter/pair' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
