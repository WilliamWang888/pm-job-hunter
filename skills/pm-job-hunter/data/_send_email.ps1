
param([string]$Recipient, [string]$Subject, [string]$BodyFile)
$body = Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.To = $Recipient
$mail.Subject = $Subject
$mail.BodyFormat = 2  # olFormatHTML
$mail.HTMLBody = $body
$mail.Send()
Write-Output "Sent to $Recipient"
