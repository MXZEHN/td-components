# Show network: two laptops, one cable, no router

Laptop **A** runs the web interface (a browser). Laptop **B** runs the TouchDesigner show, which hosts the web interface with a Web Server DAT. Both laptops also share a folder with each other. They are connected by one Ethernet cable: no router, no Wi-Fi during the show.

This guide has three parts:

1. [**Setup**](#part-1--setup-step-by-step): do it once, then again only if something changes.
2. [**Troubleshooting**](#part-2--troubleshooting): when something doesn't work.
3. [**For Claude**](#part-3--for-claude-the-ai-assistant-on-each-laptop): instructions for the AI assistant on each laptop.

## The fixed facts

| | Laptop A — web interface | Laptop B — TouchDesigner |
|---|---|---|
| Role (for the scripts) | `A` | `B` |
| IP address | `192.168.77.1` | `192.168.77.2` |
| Subnet mask | `255.255.255.0` (`/24`) | `255.255.255.0` (`/24`) |
| Gateway / DNS | **none** | **none** |
| Shares its folder as | `\\192.168.77.1\ShowData` | `\\192.168.77.2\ShowData` |
| Maps the other laptop's folder as | `S:` | `T:` |
| Web interface | opens `http://192.168.77.2:9980` | TD Web Server DAT on port `9980` |
| Share user / password | `show` / *same password on both* | `show` / *same password on both* |

> If your Web Server DAT uses a port other than 9980, replace 9980 everywhere with your port.

**Files in this folder**

| File | What it does |
|---|---|
| `setup-laptop.ps1` | Configures one laptop. Safe to run again at any time. Needs Administrator. |
| `diagnose.ps1` | Checks everything and prints PASS/FAIL with the fix for each failure. Changes nothing. Saves a report file. |

---

## Part 1 — Setup, step by step

Do every step on **both** laptops unless the step says otherwise. Do the steps in order.

### Step 0 — Before you start

- [ ] Copy this whole `show-network` folder onto both laptops, for example to `C:\show-network`.
- [ ] Decide which folder each laptop shares, for example `D:\ShowData`. The script creates it if it doesn't exist.
- [ ] Choose **one password** for the share user `show` and write it down. Use the same password on both laptops.
- [ ] You need an Administrator account on both laptops.
- [ ] **Wi-Fi:** you can leave it on during setup and troubleshooting (Claude needs internet). Switch it off before the show.
- [ ] Disconnect any VPN.

### Step 1 — Plug in the cable

1. Connect the cable directly between the two laptops. A normal cable works; you don't need a crossover cable.
2. Both laptops must be switched on.
3. **Check:** the small lights at the network port light up or blink on **both** laptops.
   *No lights?* Go to [Troubleshooting, problem 1](#1-no-cable-link-no-lights-adapter-shows-disconnected) and don't continue until they light up.

> If you use a USB or dock network adapter, always use **the same adapter in the same USB port**. Windows treats a different port as a new adapter and the settings are gone.

### Step 2 — Open PowerShell as Administrator

1. Press the Windows key and type `powershell`.
2. Right-click **Windows PowerShell** and choose **Run as administrator**, then click **Yes**.
3. Go to the folder:
   ```powershell
   cd C:\show-network
   ```

### Step 3 — Run the setup script

**On laptop A (web interface):**
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-laptop.ps1 -Role A -SharePath D:\ShowData
```

**On laptop B (TouchDesigner):**
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-laptop.ps1 -Role B -SharePath D:\ShowData
```

- It **always** asks for the password of user `show`. Type the shared password from step 0 on **both** laptops. It isn't a fixed password; you choose it, and it must be identical on A and B.
- No password question? You forgot `-SharePath ...`, so the share step was skipped. Run the command again with it.
- Every line should be green `OK` or yellow `WARN`. A red message stops the script and tells you what to do.
- If it says *"More than one wired adapter is up"*, add `-Adapter "<Name>"` using the name it lists.

What the script does:
- sets the fixed IP without a gateway
- marks the cable network as Private
- adds one firewall rule that allows everything coming from `192.168.77.x`
- disables old firewall rules that block TouchDesigner
- turns off Ethernet power saving
- creates the user `show` and shares the folder

### Step 4 — Check the cable connection

On **both** laptops:
```powershell
powershell -ExecutionPolicy Bypass -File .\diagnose.ps1 -Role A     # on laptop A
powershell -ExecutionPolicy Bypass -File .\diagnose.ps1 -Role B     # on laptop B
```

At this point **D1–D6 must be PASS on both laptops**. D7 and D8 may still fail; that's fine, they're the next steps.
If D1–D6 aren't all PASS, follow the `FIX:` line under the **first** `[FAIL]`, then run diagnose again.

### Step 5 — TouchDesigner web interface

**On laptop B:**
1. Start TouchDesigner and open the show project.
2. Find the **Web Server DAT**. Check that **Active = On** and note the **Port** (we assume `9980`).
3. If Windows shows a firewall pop-up, click **Allow access** (tick *Private* and *Public*). **Never click Cancel**: Cancel creates a block rule.
4. Open a browser on B and go to `http://localhost:9980`. The page must load.

**On laptop A:**
5. Open a browser and go to **`http://192.168.77.2:9980`**. The page must load.
6. Press a control on the page. TouchDesigner must react.
   *Page loads but nothing reacts?* See [problem 7](#7-the-page-loads-on-laptop-a-but-touchdesigner-doesnt-react).

7. Bookmark `http://192.168.77.2:9980` on laptop A.

### Step 6 — Connect the shared folders

**On laptop A**, connect B's folder as drive `S:` (normal PowerShell; it doesn't need to be Administrator):
```powershell
cmdkey /add:192.168.77.2 /user:show /pass
net use S: \\192.168.77.2\ShowData /persistent:yes
```

**On laptop B**, connect A's folder as drive `T:`:
```powershell
cmdkey /add:192.168.77.1 /user:show /pass
net use T: \\192.168.77.1\ShowData /persistent:yes
```

`cmdkey ... /pass` asks for the password: type the `show` password. Windows remembers it, so the drive reconnects after a reboot.

**Check:** open File Explorer. `S:` (on A) and `T:` (on B) open and show the other laptop's files. Create a test file on one laptop and confirm it appears on the other.

### Step 7 — Final check

Run diagnose again on **both** laptops. The goal is:

```
RESULT: ALL CHECKS PASSED on role A.
RESULT: ALL CHECKS PASSED on role B.
```

### Step 8 — Make the laptops ready for the show

On **both** laptops:
- [ ] **Wi-Fi off** (click the Wi-Fi icon in the taskbar and switch Wi-Fi off). The cable keeps working.
- [ ] **Power:** plugged in, power mode *Best performance*, sleep *Never* while plugged in, screen off *Never*.
- [ ] **Windows Update:** pause updates for the show period (Settings → Windows Update → Pause).
- [ ] **Notifications:** turn on *Do not disturb*.
- [ ] **Rehearsal:** reboot both laptops, plug in, run diagnose on both and expect ALL PASSED. Then run the show for at least 30 minutes.

### Rules for show day

- Don't let TouchDesigner play media **directly from the shared drive**. Copy files to B's local disk first, because a network hiccup would freeze the output.
- Don't run big file copies while the show is running.
- Before doors open, run `diagnose.ps1` on both laptops once. It takes 10 seconds.

---

## Part 2 — Troubleshooting

**Always start the same way:** run `diagnose.ps1` on **both** laptops and fix the **first** `[FAIL]` first. Most later failures are caused by the first one.

### Quick map from diagnose result to problem

| First FAIL | Go to |
|---|---|
| D1 no cable link | [1](#1-no-cable-link-no-lights-adapter-shows-disconnected) |
| D2 wrong / missing IP, gateway | [2](#2-wrong-ip-169254xx-or-ip-on-the-wrong-adapter) |
| D4 firewall rule / block rule | [3](#3-firewall-problems) |
| D6 *"peer exists … but does not answer ping"* | [3](#3-firewall-problems) on the **other** laptop |
| D6 *"peer not found on the cable"* | [4](#4-peer-not-found-on-the-cable) |
| D7 nothing listens / cannot reach port | [5](#5-the-web-interface-doesnt-load-on-laptop-a) |
| D7 *"only listens on 127.0.0.1"* | [6](#6-web-server-only-listens-on-itself) |
| D8 port 445 / drive problems | [8](#8-shared-drive-problems) |

### 1. No cable link (no lights, adapter shows "Disconnected")

1. Unplug and replug the cable firmly on both ends until it clicks.
2. Make sure the other laptop is switched on and not asleep.
3. USB/dock adapter: unplug it, plug it back into the **same** port and wait 10 seconds. Check Device Manager → Network adapters for a yellow warning sign, which means the driver is missing.
4. Try another cable to rule out the cable.
5. If it links at 100 Mbps instead of 1 Gbps, the cable or plug is damaged. Replace it.
6. After any adapter change, run `setup-laptop.ps1` again.

### 2. Wrong IP (169.254.x.x) or IP on the wrong adapter

- `169.254.x.x` means the fixed IP isn't set on the cable adapter.
- **Fix:** run `setup-laptop.ps1 -Role <A|B>` again as Administrator. It always picks the adapter that has the cable link.
- Check with `ipconfig`: the adapter with the cable must show `192.168.77.1` (A) or `.2` (B) and **no** default gateway.
- Typical cause: a USB adapter plugged into a different port, or a dock was used.

### 3. Firewall problems

- Run `setup-laptop.ps1` again as Administrator. It re-creates the rule and disables TouchDesigner block rules.
- **Antivirus with its own firewall** (Norton, McAfee, Kaspersky, ESET, Bitdefender, Avast, and so on): diagnose shows `Third-party firewall installed`. In that program, add `192.168.77.0/24` as a *trusted network* or *home network*, or allow TouchDesigner and file sharing there.
- **Company-managed laptop:** IT policies can override local rules. Ask IT, or use a different laptop.
- To check by hand, run `wf.msc` → *Inbound Rules*. Look for `Show cable LAN` (green, enabled) and make sure there are **no** red entries for TouchDesigner.

### 4. Peer not found on the cable

The other laptop isn't on the cable with the right IP.
1. Run `diagnose.ps1` on the **other** laptop and fix its first FAIL.
2. Check both laptops didn't get the **same** role, which happens if setup ran with `-Role A` twice.
3. Check the cable (problem 1).

### 5. The web interface doesn't load on laptop A

Work through these in order:
1. Does `ping 192.168.77.2` work from A? If not, fix the network first (problems 1–4).
2. Is TouchDesigner running with the project open on B?
3. Web Server DAT: **Active = On**? Is the port the one you think?
4. On B, does `http://localhost:9980` load? If not, the problem is inside TD, not the network.
5. Run `diagnose.ps1 -Role B -WebPort <port>` on B and check D4 (block rule) and D7.
6. On A, check you typed `http://` and **not** `https://`.

### 6. Web server only listens on itself

Diagnose D7 says *"only listens on 127.0.0.1"*: the server only accepts connections from its own laptop. TouchDesigner's Web Server DAT normally listens on all addresses. If you see this, the web interface is probably served by something else, such as a Python or Node server, that is configured for `localhost`. Change its host or bind address to `0.0.0.0`.

### 7. The page loads on laptop A but TouchDesigner doesn't react

Almost always the page's JavaScript connects to `localhost` instead of the TD laptop.
- Search the HTML/JS (in TD: the Text DAT or file that holds the page) for `localhost` and `127.0.0.1`.
- Replace a fixed WebSocket address with the page's own address:
  ```js
  // wrong: only works on the TD laptop itself
  const ws = new WebSocket('ws://localhost:9980');
  // right: works from any laptop
  const ws = new WebSocket('ws://' + location.host);
  ```
- On laptop A, press **F12** → *Console* in the browser. Red WebSocket errors confirm this.

### 8. Shared drive problems

Error messages from `net use` and Explorer, and what they mean:

| Message | Meaning | Fix |
|---|---|---|
| *System error 53* / *network path not found* | Can't reach port 445 | Fix ping first. Run setup on the **other** laptop. Check that the *Server* service is running there (`services.msc`). |
| *...security policies block unauthenticated guest access* | Windows 11 refuses passwordless access | Always use the user `show` with a password (step 6). Never use guest. |
| *System error 86* / wrong password | Password mismatch | `cmdkey /delete:192.168.77.x`, then repeat step 6 with the correct password. |
| *System error 5* / access denied | User `show` has no rights on the folder | Run setup again with `-SharePath` on the laptop that shares the folder. |
| *System error 1219* / multiple connections | Old connection with other credentials | `net use * /delete /y`, then repeat step 6. |
| *System error 67* / network name not found | Share name wrong or not created | On the other laptop, `Get-SmbShare` must list `ShowData`. Run setup with `-SharePath` there. |
| Drive shows a red X after reboot | Reconnected before the cable was up | Double-click the drive, or run `net use` from step 6 again. |

Always connect with the **IP address** (`\\192.168.77.2\...`), not the computer name. Without a router, name lookup is unreliable.

### 9. It worked, then stopped (after a reboot, sleep or replug)

1. Run diagnose on both laptops.
2. The usual cause is a USB adapter in a different port (problem 2) or Windows Update. Run `setup-laptop.ps1` again.

### 10. Connection drops during the show

- Ethernet power saving: run setup again (it turns it off), then reboot.
- Sleep or power saving: see step 8.
- A worn cable or loose plug: replace it, and tape the cable down at both laptops.

### Undo everything (go back to normal networking)

As Administrator, on the laptop you want to reset:
```powershell
$nic = (Get-NetIPAddress -IPAddress 192.168.77.* -AddressFamily IPv4).InterfaceAlias
Remove-NetIPAddress -InterfaceAlias $nic -AddressFamily IPv4 -Confirm:$false
Set-NetIPInterface -InterfaceAlias $nic -Dhcp Enabled
Remove-NetFirewallRule -DisplayName "Show cable LAN"
net use * /delete /y
Remove-SmbShare -Name ShowData -Force          # keeps the files, removes only the share
Remove-LocalUser -Name show                    # optional
```

---

## Part 3 — For Claude (the AI assistant on each laptop)

This section is written for you, Claude. A person will ask you to help set up or fix this network on **one** of the two laptops. Another Claude may be helping on the other laptop. You can't talk to each other: the person (and the diagnose report files) carry information between laptops.

### Context you need

- Two Windows laptops (one Windows 10, one Windows 11) connected by **one Ethernet cable, no router, no DHCP**.
- Fixed facts: see the [table at the top](#the-fixed-facts). Role A = `192.168.77.1` (web interface, browser). Role B = `192.168.77.2` (TouchDesigner, Web Server DAT, port 9980 unless told otherwise).
- Traffic that must work: ping, HTTP and WebSocket from A to B on the web port, and SMB (TCP 445) in both directions to the `ShowData` shares, authenticated as local user `show`.
- The team **doesn't trust Wi-Fi for the show**. Wi-Fi may be on during setup so you have internet; it's switched off for the show.

### How to work

1. **First ask which laptop you're on** (A or B), unless it's obvious. Check with `ipconfig` and `Get-NetAdapter`.
2. **Run the read-only check first**, before changing anything:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\diagnose.ps1 -Role <A|B> [-WebPort <port>]
   ```
   Read the output. Work on the **first** `[FAIL]` only, then re-run diagnose. Repeat.
3. **Fix with `setup-laptop.ps1` when possible** instead of hand-made commands. It's idempotent and keeps both laptops consistent. It needs an Administrator PowerShell; if your shell isn't elevated, ask the person to run the command in one.
4. **Use Part 2 of this guide** as your playbook. The check IDs D1–D8 map to the problems there.
5. **When the cause may be on the other laptop**, for example D6 says *"peer exists … but does not answer ping"*, or D7/D8 fail while D6 passes: say so plainly, and ask the person to run diagnose on the other laptop and show you its report (the `diagnose-<COMPUTER>-<time>.txt` file, pasted or copied over).
6. **Explain each step in plain language** before you run it. The person may not be a network expert, and it's show preparation, so be calm and precise.

### Guardrails (don't break these)

- **Never add a default gateway or DNS server** to the cable adapter. It would hijack internet traffic and break Wi-Fi.
- **Never enable guest or anonymous SMB access** and never lower SMB security (signing, `AllowInsecureGuestAuth`). Use the `show` account.
- **Never turn off Windows Firewall completely** as a "fix". Use the scoped rule `Show cable LAN` (`RemoteAddress 192.168.77.0/24`). You may *briefly* disable the firewall to **test** whether it's the cause, but you must re-enable it right away and tell the person.
- **Don't change other adapters** (Wi-Fi, VPN) except to advise switching them off for the show.
- **Don't change the IP plan** (`192.168.77.1` / `.2`) on one laptop only. If it must change, change both and update this guide.
- **Don't delete firewall rules you didn't create.** Disable them, and only if they block TouchDesigner or the show traffic.
- Ask before anything that changes the TouchDesigner project, deletes files, or restarts the laptop.
- Report results honestly: if a check still fails, say which one and what you tried.

### Useful commands (read-only unless marked)

```powershell
Get-NetAdapter | ft Name, InterfaceDescription, Status, MediaType, LinkSpeed
Get-NetIPConfiguration                                   # IPs, gateways per adapter
Get-NetConnectionProfile                                 # Private / Public
Get-NetFirewallRule -DisplayName "Show cable LAN"
Get-NetFirewallRule -Direction Inbound -Action Block -Enabled True | ft DisplayName
Get-NetNeighbor -IPAddress 192.168.77.2                  # MAC seen on cable? (peer is there)
Test-NetConnection 192.168.77.2 -Port 9980               # TD web server from A
Test-NetConnection 192.168.77.1 -Port 445                # SMB from B to A
Get-NetTCPConnection -State Listen -LocalPort 9980       # on B: is TD listening?
Get-SmbShare; Get-SmbMapping; cmdkey /list
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct   # third-party firewalls
```

### Reading the most important diagnose results

| Result | What it really means |
|---|---|
| D6 PASS | Cable, IPs and both firewalls for ICMP are fine. Remaining problems are app-level (TD, ports, shares). |
| D6 FAIL, MAC seen | Layer 2 works. The **other** laptop's firewall (Windows or third-party) drops traffic. |
| D6 FAIL, no MAC | Cable, link, wrong adapter, or wrong or duplicate IP on one side. |
| D7 FAIL on A, D7 PASS on B | TD listens, but something on B blocks it: a TD block rule or a third-party firewall. |
| D7 PASS, page loads, no reaction | The page's JavaScript uses `localhost` for the WebSocket (Part 2, problem 7). |
| D8 port 445 FAIL, D6 PASS | Server service stopped, or a third-party firewall blocks SMB on the peer. |
