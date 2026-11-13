# Self-hosted MQTT broker for a device fleet (push channel)

The push half of a device-refresh design: a fleet of kiosks keeps one TLS connection each, the panel
publishes one small message per publish, devices refresh in ~100 ms instead of polling.

## 1. Where it runs

| | Home box | Small VPS |
|---|---|---|
| CPU/RAM | irrelevant — 600 TLS connections cost tens of MB | 1 vCPU / 1 GB is plenty |
| Power | a desktop idles at 90–110 W ≈ 70 kWh/month (~$6–8) | none |
| Reachability | needs a **public, stable IP** — check CGNAT first | included |
| Firewall | router port-forward **and** host firewall | provider firewall **and** host firewall |

- **CGNAT check before promising home hosting:** compare the router's WAN address with
  `curl -s https://ifconfig.me`. Different ⇒ no inbound routing; use a VPS (a tunnel for MQTT adds
  latency and a failure mode for little gain).
- **Static IP first, DNS and certificates second.** On Lightsail-class clouds the instance IP changes
  when it is stopped/started, which silently breaks both the `A` record and the certificate. Attach
  the static IP before running certbot.
- Open the ports in **both** layers: `22`, `80` (ACME), `8883` (MQTT/TLS), `8084` (WebSocket/TLS for
  the browser panel). A port opened only in `ufw` is invisible from outside and looks like a broker
  crash.
- **Read a refused connect as information, not as a wall.** A TCP connect refused in tens of
  milliseconds (`curl` → `Could not connect … after 42 ms`) means the provider firewall is already
  passing traffic and nothing is bound yet; a multi-second hang/timeout means the firewall is still
  closed. Check this before rebuilding the broker config for a "crash".

## 2. Broker config that passes an audit

Mosquitto 2.x, TLS-only, per-listener auth:

```conf
per_listener_settings true

listener 8883                       # devices
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
tls_version tlsv1.2
allow_anonymous false
password_file /etc/mosquitto/auth/passwd
acl_file      /etc/mosquitto/auth/acl

listener 8084                       # browser panel publishes here
protocol websockets
certfile /etc/mosquitto/certs/fullchain.pem
keyfile  /etc/mosquitto/certs/privkey.pem
allow_anonymous false
password_file /etc/mosquitto/auth/passwd
acl_file      /etc/mosquitto/auth/acl

message_size_limit 1024             # the message is a "refresh" ping, nothing else
persistence false
max_queued_messages 5
```

- With `per_listener_settings true`, `allow_anonymous`, `password_file` and `acl_file` belong **inside
  each listener**; a global copy is ignored (and makes you believe auth is configured when it is not).
- Never leave a plain `1883` listener around "for testing". TLS-only, and prove the plain port is
  closed.
- `cafile` is for verifying **client** certificates; a server-side TLS listener needs only
  `certfile` + `keyfile`.
- **Never redeclare a global the distro package already sets.** Ubuntu's packaged
  `mosquitto.conf` ships `log_dest file /var/log/mosquitto/mosquitto.log`; a second `log_dest file`
  in a drop-in is a hard startup error (`Duplicate "log_dest file" value`, exit `3/NOTIMPLEMENTED`).
  Configure only what you own — to change verbosity use `log_type`, never `log_dest`.
- `message_size_limit` still works on 2.x but logs a deprecation note; on newer builds use
  `max_packet_size` with the same value.

## 3. Two accounts, opposite permissions

```conf
user panel
topic write <app>/publish

user device
topic read <app>/publish
```

Generate both passwords on the server (`openssl rand -base64 24`), write them once to a 0600 file, and
never echo them into chat or a repo. Give the panel a **write-only** identity and devices a
**read-only** identity: a compromised device cannot inject a fleet-wide refresh storm, and a leaked
panel password cannot read anything.

## 4. Certificates (Let's Encrypt, not ACM)

```bash
certbot certonly --standalone -d broker.example.com -m you@example.com --agree-tos -n
install -d -o mosquitto -g mosquitto -m 750 /etc/mosquitto/certs
install -o mosquitto -g mosquitto -m 640 /etc/letsencrypt/live/broker.example.com/fullchain.pem /etc/mosquitto/certs/
install -o mosquitto -g mosquitto -m 640 /etc/letsencrypt/live/broker.example.com/privkey.pem   /etc/mosquitto/certs/
```

`/etc/letsencrypt/live` is a root-only tree, so the broker user cannot read the key in place — copying
into a broker-owned directory is mandatory, not tidiness. Add a renewal **deploy hook** that repeats
the copy and reloads the service, otherwise the broker dies of an expired cert weeks later with no
change on your side.

## 5. Publisher side (browser panel)

- Point it at the WebSocket listener: `wss://broker.example.com:8084/mqtt` with the write-only user.
  A browser panel can only carry that password in its own bundle (`VITE_…` is public), so the single-topic
  ACL is the mitigation, not secrecy. When the panel has an authenticated backend, mint a short-lived
  token instead — see `spa-api-auth-wiring`, "Anything in `VITE_*` ships to the browser".
- Load the MQTT client with a **dynamic import** and skip publishing entirely when the env var is
  unset, so the base bundle does not grow and an unconfigured deployment keeps working on polling.
- Publish fire-and-forget after a successful save (`void publish(...)`) — a slow broker must never
  delay or fail a save; the device's polling fallback covers a dropped message.
- The renewal/TLS listener must allow WebSocket upgrade through any CDN in front of the panel; mixed
  content is not an issue (wss), but a proxy that strips `Upgrade` will silently break publishing.

## 6. Installer shape

One idempotent script that a non-expert can run (`sudo bash install.sh --host … --email …`):

1. packages (`mosquitto`, `mosquitto-clients`, `certbot`, `ufw`), stop the service so ACME can bind 80;
2. firewall rules, then certificate, then copy + renewal hook;
3. users + ACL, then fix **directory and file separately**: `/etc/mosquitto/auth` must be
   **traversable by the broker user** (`0750 mosquitto:mosquitto`), and `passwd` must be
   `root:mosquitto 0640` — mosquitto 2.x warns, and newer builds refuse to start, when the password
   file is not root-owned. A `0700 root:root` auth directory yields
   `Error: Unable to open pwfile "/etc/mosquitto/auth/passwd"` and systemd `status=13` while the
   file's own mode looks perfectly correct;
4. config, `systemctl enable --now`, then a **self test** (publish over TLS as the panel user);
5. write the credentials file to `/root/<app>-mqtt-credentials.txt` (0600) **before** the final
   health gate, then print both passwords once. A first start that fails after the passwords were
   generated is the common case, and a file written afterwards is a lost password (the users still
   exist, so you must reset both with `mosquitto_passwd -b` and reload).

Do not put passwords in the script or in the repo; generate them on the host.

## 7. Verification — negative tests are the point

```bash
# TLS chain valid
openssl s_client -connect broker:8883 -servername broker -brief </dev/null 2>&1 | grep 'Verification: OK'
# panel can publish, device receives
mosquitto_pub -h broker -p 8883 -u panel  -P "$PANEL"  -t <app>/publish -m '{"k":"t"}'
mosquitto_sub -h broker -p 8883 -u device -P "$DEVICE" -t <app>/publish -C 1
# anonymous must fail, plain port must be closed (auth failure DOES change the exit code)
mosquitto_pub -h broker -p 8883 -t <app>/publish -m x                            # expect DENIED
bash -c 'echo >/dev/tcp/broker/1883'                                             # expect refused
# device publish is NOT checkable here — a denied PUBLISH exits 0; use the subscriber form below
```

A green "message received" alone proves nothing about blast radius; the denials are the test.

**Do not judge a publish denial by exit code.** In MQTT 3.1.1 a denied PUBLISH is dropped silently
and `mosquitto_pub` still exits `0`, so an exit-code check reports a security hole that is not there
(and, inverted, would hide a real one). Assert with a subscriber:

```bash
# device must NOT publish: subscribe as the device, publish as the device, buffer must stay EMPTY
( timeout 8 mosquitto_sub -h broker -p 8883 -u device -P "$DEVICE" -t <app>/publish -C 1 > out & )
sleep 2
mosquitto_pub -h broker -p 8883 -u device -P "$DEVICE" -t <app>/publish -m '{"probe":1}'
sleep 5; [ -s out ] && echo 'ACL MISSING' || echo 'ACL ok'
```

For a direct reason code use MQTT v5 (`mosquitto_pub -V 5 -d`), where the broker returns
`not authorized` instead of silence.

## 8. Device side, in order

1. `pip install paho-mqtt` (missing library ⇒ silent fallback to polling, which is the desired
   fail-safe, but say so in the docs instead of letting it look broken).
2. Settings: enabled, host, port, topic, user, password (or CA/cert/key for IoT Core-style X.509),
   plus a **long** safety-net poll interval (minutes).
3. On message: write the local trigger document and let the existing signature/long-poll chain refresh
   the UI — do not add a second refresh path.
4. While the broker connection is up, skip the fast remote poll entirely; otherwise the fleet pays for
   both mechanisms.
5. **Restart the app after enabling push.** Native runtimes read settings once at start; a panel that
   now publishes push settings changes nothing until the process is restarted, and the report reads
   "I enabled push and nothing happened".
6. **Install the client library into the interpreter that runs the service**, not whichever one is on
   your shell PATH. A subscriber test run with a different python proves nothing about the daemon that
   is failing - check the service unit's ExecStart interpreter and install there.
7. **A device that reads its data from local files never fetches the published settings document**, so
   push keys put only in the panel are invisible to it (symptom: the diagnostics line says push is
   `off` while the panel shows it `true`). Write those keys into the device's OWN settings file and
   ship a command that does it: merge (never overwrite the whole document), keep the file `0600`
   because it holds the broker password, support `--show` (mask the password), `--remove`, and a
   `--test` that opens the real TLS connection and reports ok/failure. Handing the user a JSON
   snippet to paste is how a fleet ends up half-configured.
8. **The diagnostics command must attempt the connection, not describe it.** "enabled, connected:
   false, error: not attempted yet" reads as a broken broker even when everything is correct; start
   the subscriber for a couple of seconds inside the diagnostic and report `connected ✓` (or the
   actual error text). One line the user can paste back is worth more than a packet capture.

## 9. Client library (paho-mqtt 2.x) and the three-signal triage

paho-mqtt 2.x changed the client API in two ways that fail silently or in a background thread:

- `mqtt.Client(...)` now requires a callback API version: `mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
  client_id=...)`. Without it you get `ValueError: Unsupported callback API version`.
- `on_connect` is called with **five** arguments - `(client, userdata, connect_flags, reason_code,
  properties)`; `on_disconnect` likewise. A four-argument callback raises TypeError *inside paho's
  network thread*: TCP/TLS connects fine, the process keeps running, and the app simply never records
  "connected" - a status line that says connected=false with an empty error.
- Stay version-agnostic with `hasattr(mqtt, "CallbackAPIVersion")` when constructing the client, and
  accept `(..., reason_code, properties=None)` in the callbacks. Compare `reason_code` to 0; never
  use identity comparison.
- Expose enabled / broker / topic / connected / last error in the app's own diagnostics command
  (a --tani / --diagnose flag). Handing the user one line to paste beats a packet capture.

"I published from the panel and the device did not react" - answer with three independent signals,
cheapest first, before touching any code:

| Signal | How | What it eliminates |
|---|---|---|
| Did the writer write? | `curl -sI <cdn>/<file>` then read Last-Modified | panel auth, save path, bucket prefix |
| Is anyone subscribed? | on the broker: `ss -tn state established '( sport = :8883 )' | wc -l` | if 0, the whole panel side is irrelevant - no consumer exists |
| What does the device think? | its diagnostics flag (--tani) | missing library, wrong interpreter, TLS/auth error, settings not reloaded |

A zero connection count is the most common finding, and it is not a broker or ACL problem: no
subscriber means the process is not running, was not restarted after the settings landed, or has no
client library. Never "fix" the broker before that count is 1.

### Ship the triage as ONE script the user runs while the app is live

Interpreting a table over a chat round-trip costs hours. Put the ladder in a `--tani`-style script
(`tools/live_check.py`) that walks the chain **in order**, prints one ✓/✗ line per link with the
actual values, and exits non-zero on the first broken link:

| # | Link | Check |
|---|---|---|
| 1 | publisher | fetch the freshness stamp + the aggregate status document through the **device's** URL; flag when the two disagree (a half-written publish) |
| 2 | device disk | the stamp in the local cache index vs the remote stamp |
| 3 | broker | subscribe as a device for ~15 s and count messages; distinguish "could not connect" (auth/TLS) from "connected, silent" (publisher side) |
| 4 | local trigger | the trigger document's mtime |

Three rules make it usable in the field:

- **Load the app's settings before reading config.** A probe that imports the config module directly
  reports "broker empty" because the settings file was never applied — a false failure that sends the
  user to the broker. Apply the settings loader first, exactly like `main` does.
- **Subscribe, do not publish.** The device side is the failing side in most reports; a probe that only
  publishes proves your credentials work and tells you nothing about delivery.
- **Say what to do next in the output**, not in the chat: "chain OK — press Notify in the panel, then
  run this again; link 3 must print `message received`". That turns a 10-hour thread into two runs.
