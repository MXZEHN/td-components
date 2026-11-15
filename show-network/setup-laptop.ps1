<#
.SYNOPSIS
    Sets up one laptop for the direct-cable show network (no router).

.DESCRIPTION
    Role A = web interface laptop  -> 192.168.77.1
    Role B = TouchDesigner laptop  -> 192.168.77.2

    What it does (safe to run again at any time):
      1. Finds the wired adapter that has a cable link
      2. Sets the fixed IP (no gateway, no DNS)
      3. Marks the cable network as Private
      4. Adds one firewall rule: allow everything coming from 192.168.77.0/24
      5. Disables old firewall rules that BLOCK TouchDesigner
      6. Turns off Ethernet power saving (Energy Efficient Ethernet, device sleep)
      7. Optional (-SharePath): creates local user "show" and shares the folder as "ShowData"

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup-laptop.ps1 -Role A
    powershell -ExecutionPolicy Bypass -File .\setup-laptop.ps1 -Role B -SharePath D:\ShowData
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('A', 'B')][string]$Role,
    [string]$Adapter,          # adapter name, only needed if more than one cable is plugged in
    [string]$SharePath         # folder to share as \\<this laptop>\ShowData (optional)
)

$ErrorActionPreference = 'Stop'
$Subnet   = '192.168.77'
$MyIP     = if ($Role -eq 'A') { "$Subnet.1" } else { "$Subnet.2" }
$PeerIP   = if ($Role -eq 'A') { "$Subnet.2" } else { "$Subnet.1" }
$RuleName = 'Show cable LAN'
$ShareName = 'ShowData'
$ShareUser = 'show'

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "    OK   $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    WARN $text" -ForegroundColor Yellow }

# --- 0. Admin check ---------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Please run PowerShell as Administrator (right-click > Run as administrator)." -ForegroundColor Red
    exit 1
}

Write-Host "Show network setup - this laptop is ROLE $Role ($MyIP), peer is $PeerIP" -ForegroundColor White

# --- 1. Find wired adapter --------------------------------------------------
Step "1/7 Finding the wired adapter with a cable link"
if ($Adapter) {
    $nic = Get-NetAdapter -Name $Adapter
} else {
    $wired = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.MediaType -eq '802.3' })
    if ($wired.Count -eq 0) {
        Write-Host "    No wired adapter has a link. Check: cable plugged in on BOTH laptops, other laptop switched on," -ForegroundColor Red
        Write-Host "    link lights on, USB/dock adapter connected. Then run this script again." -ForegroundColor Red
        Get-NetAdapter | Format-Table Name, InterfaceDescription, Status, MediaType -AutoSize
        exit 1
    }
    if ($wired.Count -gt 1) {
        Write-Host "    More than one wired adapter is up. Run again with -Adapter ""<Name>"":" -ForegroundColor Red
        $wired | Format-Table Name, InterfaceDescription, LinkSpeed -AutoSize
        exit 1
    }
    $nic = $wired[0]
}
$ifIndex = $nic.ifIndex
Ok "Using '$($nic.Name)' ($($nic.InterfaceDescription)), link $($nic.LinkSpeed)"

# --- 2. Fixed IP ------------------------------------------------------------
Step "2/7 Setting fixed IP $MyIP/24 (no gateway, no DNS)"
# Make sure no OTHER adapter already uses the show subnet
$clash = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like "$Subnet.*" -and $_.InterfaceIndex -ne $ifIndex }
foreach ($c in $clash) {
    Warn "Removing $($c.IPAddress) from other adapter '$($c.InterfaceAlias)'"
    Remove-NetIPAddress -InterfaceIndex $c.InterfaceIndex -IPAddress $c.IPAddress -Confirm:$false
}
Set-NetIPInterface -InterfaceIndex $ifIndex -AddressFamily IPv4 -Dhcp Disabled
Remove-NetRoute -InterfaceIndex $ifIndex -DestinationPrefix '0.0.0.0/0' -Confirm:$false -ErrorAction SilentlyContinue
Remove-NetIPAddress -InterfaceIndex $ifIndex -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceIndex $ifIndex -IPAddress $MyIP -PrefixLength 24 | Out-Null
Set-DnsClientServerAddress -InterfaceIndex $ifIndex -ResetServerAddresses
Ok "IP set"

# --- 3. Private network profile ---------------------------------------------
Step "3/7 Marking the cable network as Private"
$done = $false
for ($i = 0; $i -lt 10 -and -not $done; $i++) {
    try {
        Set-NetConnectionProfile -InterfaceIndex $ifIndex -NetworkCategory Private
        $done = $true
    } catch { Start-Sleep -Seconds 2 }
}
if ($done) { Ok "Profile is Private" } else { Warn "Could not set Private (not critical - the firewall rule in step 4 works on all profiles)" }

# --- 4. Firewall rule -------------------------------------------------------
Step "4/7 Firewall: allow all incoming traffic from $Subnet.0/24"
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Profile Any `
    -RemoteAddress "$Subnet.0/24" -Description 'Direct cable show network (TD web server, file sharing, ping)' | Out-Null
Ok "Rule '$RuleName' created"

# --- 5. Disable old BLOCK rules for TouchDesigner ---------------------------
Step "5/7 Looking for firewall rules that BLOCK TouchDesigner"
$blockRules = @(Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True -ErrorAction SilentlyContinue |
    Where-Object {
        $_.DisplayName -match 'TouchDesigner' -or
        (($_ | Get-NetFirewallApplicationFilter).Program -match 'TouchDesigner')
    })
if ($blockRules.Count -eq 0) {
    Ok "None found"
} else {
    foreach ($r in $blockRules) {
        Disable-NetFirewallRule -Name $r.Name
        Warn "Disabled block rule: $($r.DisplayName)"
    }
}

# --- 6. Ethernet power saving -----------------------------------------------
Step "6/7 Turning off Ethernet power saving"
$eee = Get-NetAdapterAdvancedProperty -Name $nic.Name -RegistryKeyword '*EEE' -ErrorAction SilentlyContinue
if ($eee) {
    Set-NetAdapterAdvancedProperty -Name $nic.Name -RegistryKeyword '*EEE' -RegistryValue 0 -NoRestart
    Ok "Energy Efficient Ethernet off (takes effect after the next reconnect or reboot)"
} else {
    Ok "Adapter has no Energy Efficient Ethernet setting"
}
try {
    Disable-NetAdapterPowerManagement -Name $nic.Name -NoRestart -ErrorAction Stop
    Ok "Adapter power management off"
} catch { Warn "Could not change adapter power management (not critical)" }

# --- 7. Optional: file share ------------------------------------------------
Step "7/7 File share"
if (-not $SharePath) {
    Ok "Skipped (no -SharePath given)"
} else {
    if (-not (Test-Path $SharePath)) { New-Item -ItemType Directory -Path $SharePath | Out-Null }
    # Always ask, so the password is guaranteed to match the other laptop
    $pw = Read-Host -AsSecureString "Password for local user '$ShareUser' (type the SAME password on both laptops)"
    if (-not (Get-LocalUser -Name $ShareUser -ErrorAction SilentlyContinue)) {
        New-LocalUser -Name $ShareUser -Password $pw -PasswordNeverExpires -AccountNeverExpires `
            -Description 'Show network file sharing' | Out-Null
        Ok "Local user '$ShareUser' created"
    } else {
        Set-LocalUser -Name $ShareUser -Password $pw -PasswordNeverExpires $true
        Enable-LocalUser -Name $ShareUser
        Ok "Local user '$ShareUser' already existed - password updated"
    }
    if (-not (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue)) {
        New-SmbShare -Name $ShareName -Path $SharePath -FullAccess $ShareUser | Out-Null
    }
    & icacls $SharePath /grant "${ShareUser}:(OI)(CI)M" | Out-Null
    Ok "Folder $SharePath shared as \\$MyIP\$ShareName (user '$ShareUser')"
}

Write-Host ""
if (-not $SharePath) { Write-Host "NOTE: no file share was set up and no password asked. To share a folder, run again with -SharePath D:\ShowData" -ForegroundColor Yellow }
Write-Host "Done. Next: run setup on the other laptop, then diagnose.ps1 on both (-Role A on laptop A, -Role B on laptop B)." -ForegroundColor White
