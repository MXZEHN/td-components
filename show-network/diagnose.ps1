<#
.SYNOPSIS
    Checks the direct-cable show network and says exactly what is wrong.

.DESCRIPTION
    Read-only: changes nothing. Run on BOTH laptops. Writes a report file next to
    this script (diagnose-<COMPUTER>-<time>.txt) that you can give to Claude or
    copy to the other laptop.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\diagnose.ps1 -Role A
    powershell -ExecutionPolicy Bypass -File .\diagnose.ps1 -Role B -WebPort 9980
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('A', 'B')][string]$Role,
    [int]$WebPort = 9980        # port of the Web Server DAT in TouchDesigner
)

$Subnet    = '192.168.77'
$MyIP      = if ($Role -eq 'A') { "$Subnet.1" } else { "$Subnet.2" }
$PeerIP    = if ($Role -eq 'A') { "$Subnet.2" } else { "$Subnet.1" }
$TdIP      = "$Subnet.2"
$RuleName  = 'Show cable LAN'
$ShareName = 'ShowData'

$script:report = New-Object System.Collections.Generic.List[string]
$script:fails = 0
function Log($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color; $script:report.Add($text) }
function Pass($id, $text) { Log "[PASS] $id $text" 'Green' }
function Fail($id, $text, $fix) { $script:fails++; Log "[FAIL] $id $text" 'Red'; Log "       FIX: $fix" 'Yellow' }
function Note($id, $text) { Log "[INFO] $id $text" 'Gray' }
function WarnL($id, $text) { Log "[WARN] $id $text" 'Yellow' }

function Test-Tcp($ip, $port) {
    $c = New-Object System.Net.Sockets.TcpClient
    try { return ($c.ConnectAsync($ip, $port).Wait(2000) -and $c.Connected) } catch { return $false } finally { $c.Close() }
}

Log "Show network diagnose  |  computer $env:COMPUTERNAME  |  role $Role  |  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" 'White'
Log "Expected: this laptop $MyIP, peer $PeerIP, TD web server on ${TdIP}:$WebPort" 'White'
Log ""

# D1 wired link --------------------------------------------------------------
$wired = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object { $_.MediaType -eq '802.3' })
$up = @($wired | Where-Object Status -eq 'Up')
if ($up.Count -eq 0) {
    Fail 'D1' 'No wired adapter has a cable link.' ('Plug cable firmly into both laptops, check other laptop is on, check link lights, try other port/adapter. Wired adapters seen: ' + (($wired | ForEach-Object { "$($_.Name)=$($_.Status)" }) -join ', '))
} else {
    foreach ($n in $up) { Pass 'D1' "Cable link on '$($n.Name)' at $($n.LinkSpeed)" }
    if ($up[0].LinkSpeed -match 'Mbps' -and $up[0].LinkSpeed -notmatch '^1000') { WarnL 'D1' 'Link is slower than 1 Gbps - cable or port may be damaged.' }
}

# D2 IP on the right adapter -------------------------------------------------
$mine = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -eq $MyIP)
$apipa = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like '169.254.*' -and ($up.ifIndex -contains $_.InterfaceIndex) })
if ($mine.Count -eq 0) {
    $hint = if ($apipa.Count) { "Cable adapter has $($apipa[0].IPAddress) (automatic address)." } else { '' }
    Fail 'D2' "This laptop does not have $MyIP. $hint" "Run setup-laptop.ps1 -Role $Role as Administrator."
} elseif ($up.ifIndex -notcontains $mine[0].InterfaceIndex) {
    Fail 'D2' "$MyIP is on '$($mine[0].InterfaceAlias)', which has no cable link." "Run setup-laptop.ps1 -Role $Role again (it picks the adapter with the link)."
} else {
    Pass 'D2' "$MyIP on '$($mine[0].InterfaceAlias)'"
    $gw = Get-NetRoute -InterfaceIndex $mine[0].InterfaceIndex -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue
    if ($gw) { Fail 'D2' 'Cable adapter has a default gateway.' "Run setup-laptop.ps1 -Role $Role again (removes it)." }
}
$dupe = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -like "$Subnet.*" -and $_.IPAddress -ne $MyIP })
foreach ($d in $dupe) { Fail 'D2' "Unexpected $($d.IPAddress) on '$($d.InterfaceAlias)'." "Run setup-laptop.ps1 -Role $Role again." }

# D3 network profile ---------------------------------------------------------
if ($mine.Count) {
    $prof = Get-NetConnectionProfile -InterfaceIndex $mine[0].InterfaceIndex -ErrorAction SilentlyContinue
    if ($prof -and $prof.NetworkCategory -eq 'Private') { Pass 'D3' 'Cable network is Private' }
    elseif ($prof) { WarnL 'D3' "Cable network is $($prof.NetworkCategory) (OK as long as D4 passes)." }
}

# D4 firewall ----------------------------------------------------------------
$rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($rule -and $rule.Enabled -eq 'True' -and $rule.Action -eq 'Allow') { Pass 'D4' "Firewall rule '$RuleName' present" }
else { Fail 'D4' "Firewall rule '$RuleName' missing or disabled." "Run setup-laptop.ps1 -Role $Role as Administrator." }
$blocks = @(Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match 'TouchDesigner' -or (($_ | Get-NetFirewallApplicationFilter).Program -match 'TouchDesigner') })
if ($blocks.Count) { Fail 'D4' "Active BLOCK rule(s) for TouchDesigner: $(($blocks.DisplayName) -join ', ')" "Run setup-laptop.ps1 -Role $Role (disables them)." }
else { Pass 'D4' 'No firewall rule blocks TouchDesigner' }
$fwProducts = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct -ErrorAction SilentlyContinue)
foreach ($p in $fwProducts) { WarnL 'D4' "Third-party firewall installed: $($p.displayName). It must also allow $Subnet.0/24 (add as trusted network)." }

# D5 other adapters ----------------------------------------------------------
$wifiUp = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' -and $_.MediaType -match '802.11' })
if ($wifiUp.Count) { Note 'D5' 'Wi-Fi is on. Fine for setup (Claude needs internet); switch it off for the show.' }
$vpn = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'VPN|TAP|WireGuard|Tailscale|ZeroTier|Fortinet|Cisco|Pulse|GlobalProtect' })
foreach ($v in $vpn) { WarnL 'D5' "VPN adapter active: $($v.InterfaceDescription). Disconnect it if anything below fails." }

# D6 reach the peer ----------------------------------------------------------
$ping = Test-Connection -ComputerName $PeerIP -Count 2 -Quiet -ErrorAction SilentlyContinue
if ($ping) {
    Pass 'D6' "Ping $PeerIP answers"
} else {
    $nb = Get-NetNeighbor -IPAddress $PeerIP -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($nb -and $nb.LinkLayerAddress -and $nb.LinkLayerAddress -notmatch '^(00-){5}00$' -and $nb.State -notin @('Unreachable','Incomplete')) {
        Fail 'D6' "Peer $PeerIP exists on the cable (MAC $($nb.LinkLayerAddress)) but does not answer ping." "Cable and IPs are fine - the OTHER laptop's firewall blocks. Run setup-laptop.ps1 on the other laptop; check its third-party firewall."
    } else {
        Fail 'D6' "Peer $PeerIP not found on the cable." "On the other laptop: is it on, is the cable plugged in, did setup-laptop.ps1 run with the other role? Run diagnose.ps1 there too."
    }
}

# D7 TouchDesigner web server ------------------------------------------------
if ($Role -eq 'B') {
    $listen = @(Get-NetTCPConnection -State Listen -LocalPort $WebPort -ErrorAction SilentlyContinue)
    if ($listen.Count -eq 0) {
        Fail 'D7' "Nothing listens on port $WebPort." "Start TouchDesigner, open the project, check the Web Server DAT: Active = On, Port = $WebPort (or run diagnose with -WebPort <port>)."
    } else {
        $owner = (Get-Process -Id $listen[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
        $addrs = ($listen.LocalAddress | Sort-Object -Unique) -join ', '
        if ($listen.LocalAddress | Where-Object { $_ -in @('0.0.0.0', '::', $MyIP) }) {
            Pass 'D7' "Port $WebPort open by '$owner' on $addrs"
        } else {
            Fail 'D7' "Port $WebPort only listens on $addrs (this laptop only)." "Server must listen on all addresses (0.0.0.0) or on $MyIP."
        }
    }
} else {
    if (Test-Tcp $TdIP $WebPort) { Pass 'D7' "TD web server reachable at http://${TdIP}:$WebPort" }
    else { Fail 'D7' "Cannot reach ${TdIP}:$WebPort." "If D6 passed: TD not running, Web Server DAT not active, wrong port, or a block rule on the TD laptop. Run diagnose.ps1 -Role B on the TD laptop." }
}

# D8 file sharing ------------------------------------------------------------
if (Test-Tcp $PeerIP 445) { Pass 'D8' "File sharing port 445 on peer is reachable" }
else { Fail 'D8' "File sharing port 445 on peer $PeerIP not reachable." "On the other laptop: setup-laptop.ps1 ran? 'Server' service running (services.msc)?" }
$share = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($share) { Pass 'D8' "This laptop shares '$ShareName' -> $($share.Path)" }
else { Note 'D8' "This laptop has no '$ShareName' share (run setup with -SharePath if it should)." }
$maps = @(Get-SmbMapping -ErrorAction SilentlyContinue | Where-Object RemotePath -like "\\$PeerIP\*")
foreach ($m in $maps) {
    if ($m.Status -eq 'OK') { Pass 'D8' "Drive $($m.LocalPath) -> $($m.RemotePath) connected" }
    else { Fail 'D8' "Drive $($m.LocalPath) -> $($m.RemotePath) status $($m.Status)" "Re-map: see guide step 6. Check user 'show' and password." }
}
if ($maps.Count -eq 0) { Note 'D8' "No drive mapped to \\$PeerIP (see guide step 6)." }

# Summary --------------------------------------------------------------------
Log ""
if ($script:fails -eq 0) { Log "RESULT: ALL CHECKS PASSED on role $Role." 'Green' }
else { Log "RESULT: $($script:fails) problem(s). Fix the FIRST [FAIL] first, then run this again." 'Red' }

$file = Join-Path $PSScriptRoot ("diagnose-{0}-{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { $script:report | Out-File -FilePath $file -Encoding UTF8; Log "Report saved: $file" 'White' } catch { }
