$ErrorActionPreference='Stop'
$base='http://localhost:8000'

$tokenOutput = docker compose exec -T backend python manage.py shell -c "from infrastructure.orm.models import User; from rest_framework_simplejwt.tokens import AccessToken; u=User.objects.get(email='test@example.com'); print(str(AccessToken.for_user(u)))"
$token = ($tokenOutput | Where-Object { $_ -and $_.Trim() -and $_ -notmatch 'objects imported automatically' } | Select-Object -Last 1).Trim()
$headers=@{Authorization="Bearer $token"}
$templates=(Invoke-RestMethod -Method Get -Uri "$base/api/templates/" -Headers $headers).data
$template=$templates | Where-Object { $_.name -match 'Personal Life Manager|Personal Assistant' } | Select-Object -First 1
$creds=(Invoke-RestMethod -Method Get -Uri "$base/api/credentials/" -Headers $headers).data
$openai=$creds | Where-Object { $_.provider -eq 'openai' -and $_.health_status -ne 'revoked' } | Sort-Object created_at -Descending | Select-Object -First 1
$cloneBody=@{name="QA Refresh Check - $($template.name)";provider='openai';model='gpt-4';credential_id=$openai.id}|ConvertTo-Json
$clone=Invoke-RestMethod -Method Post -Uri "$base/api/templates/$($template.id)/clone" -Headers $headers -ContentType 'application/json' -Body $cloneBody
$input = if($template.sample_input){$template.sample_input} else {@{}}
$runBody=@{graph_version_id=$clone.data.graph_version_id;input_json=$input}|ConvertTo-Json -Depth 20
$run=(Invoke-RestMethod -Method Post -Uri "$base/api/runs/start" -Headers $headers -ContentType 'application/json' -Body $runBody).data
$runId=$run.id
$deadline=(Get-Date).AddMinutes(5)
do { Start-Sleep -Seconds 2; $detail=(Invoke-RestMethod -Method Get -Uri "$base/api/runs/$runId" -Headers $headers).data } while((Get-Date)-lt $deadline -and $detail.status -notin @('succeeded','failed','canceled','paused'))
[ordered]@{run_id=$runId;status=$detail.status;error=$detail.error_message;duration_ms=$detail.duration_ms}|ConvertTo-Json -Depth 10
