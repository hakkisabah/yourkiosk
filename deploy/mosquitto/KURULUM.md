# Mosquitto (VPS) kurulumu — güvenli, tek komut

600 cihazda yoklama ≈ **$596/ay**; kendi broker'ınız **$5/ay sabit** ve ~100 ms gecikme verir.

---

## 1. Sizden gereken yetkilendirme (kısa liste)

| # | Gereken | Neden |
|---|---|---|
| 1 | **VPS'in IP'si + SSH kullanıcısı** (ör. `root@203.0.113.10`, Ubuntu 22.04/24.04) | Mosquitto'yu kurup sertifika alacağım |
| 2 | **SSH erişimi**: ya benim açık anahtarımı `~/.ssh/authorized_keys`'e ekleyin, ya da `kur.sh`'i kendiniz çalıştırın | Şifre asla istemem/almam |
| 3 | **TLS için alan adı** — domain almadıysanız ücretsiz çözüm: `broker.<IP>.nip.io` (ör. `broker.203.0.113.10.nip.io`) | Let's Encrypt sertifikası için (ücretsiz, gerçek CA) |
| 4 | **E-posta** (Let's Encrypt bildirimleri) | Sertifika kaydı |
| 5 | **Bulut güvenlik duvarı**: 22, 80, 8883, 8084 açık (Hetzner/DO/AWS Security Group) | 80 = sertifika, 8883 = MQTT/TLS, 8084 = panel WebSocket |
| 6 | VPS'te **root/sudo** | Paket kurulumu, sistem servisi |

**Açık anahtarım** (2. madde için, isterseniz):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM73puPcAfsmWFRSrL90cSL+X0wH2935d9BJ7mbvXceh hakkihelyanwe@gmail.com
```

> İsterseniz bu anahtarı **kurulumdan sonra** kaldırın (`authorized_keys`'ten silin) — kalıcı erişim
> gerekmiyor; bundan sonra broker yönetimi sizde.

## 2. İki yol

### A) Siz çalıştırın (1 komut)

```bash
# VPS'te:
sudo bash kur.sh --host broker.<IP>.nip.io --eposta siz@example.com
```

Sonunda ekrana **iki parola** basar ve `/root/yourkiosk-mqtt-credentials.txt` (0600) dosyasına yazar:
- `panel` → yalnız **yazar** (yayın)
- `cihaz` → yalnız **okur** (abone)

### B) Ben çalıştırayım

Anahtarı ekledikten sonra bana şunu yazın: `VPS <kullanıcı>@<IP> hazır` — kurulumu, doğrulamayı ve
panel yayınını ben yaparım; sonunda anahtarı kaldırmanızı hatırlatırım.

## 3. Kurulumun yaptıkları (güvenlik dahil)

- `mosquitto` + `certbot` + `ufw`; **yalnız TLS** dinleyiciler: `8883` (MQTT) ve `8084` (WebSocket/TLS)
- **Düz 1883 kapalı** (TLS'siz MQTT yok)
- `allow_anonymous false` + kullanıcı/parola (`/etc/mosquitto/auth/passwd`, 0640, mosquitto sahipli)
- **Konu ACL'i**: `panel` → yalnız `yourkiosk/yayin` **yazma**; `cihaz` → yalnız **okuma**
- `message_size_limit 1024` (yalnız "yenile" mesajı), `max_queued_messages 5`, `persistence false`
- Let's Encrypt + **yenileme kancası** (sertifika yenilenince kopyalanır ve mosquitto reload olur)
- `ufw`: 22/80/8883/8084 (diğer her şey kapalı)

## 4. Kurulumdan sonra (ben yaparım / siz yaparsınız)

1. **Panel** `panel/.env.local`:
   ```bash
   VITE_MQTT_URL=wss://broker.<IP>.nip.io:8084/mqtt
   VITE_MQTT_KONU=yourkiosk/yayin
   VITE_MQTT_KULLANICI=panel
   VITE_MQTT_PAROLA=<panel parolası>
   ```
   → `./panel/infra/yayinla.sh`
2. **Cihazlarda**: `pip install paho-mqtt`
3. **Panelden ayarlar** (Tetikleme grubu):
   `push_aktif=true` · `push_broker=broker.<IP>.nip.io` · `push_port=8883` ·
   `push_konu=yourkiosk/yayin` · `push_kullanici=cihaz` · `push_parola=<cihaz parolası>` ·
   `kontrol_ms=300000` (5 dk emniyet ağı)
4. **Doğrulama** (herhangi bir makineden):
   ```bash
   MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… bash dogrula.sh broker.<IP>.nip.io
   ```
   Beklenen: TLS ✓ · panel yayını ✓ · cihaz aboneliği ✓ · **cihaz yayını RED** ✓ · anonim RED ✓ · 1883 kapalı ✓

## 5. Maliyet ve kapasite

| Kalem | Değer |
|---|---|
| VPS (1 vCPU / 1 GB) | ~$4–6/ay |
| Mesaj | yayın başına 1 küçük mesaj (600 cihaza dağıtım broker tarafında) |
| Bağlantı | 600 kalıcı TLS bağlantısı — 1 GB RAM'li VPS'te rahat (mosquitto bağlantı başına ~10–20 KB) |
| Karşılaştırma | 3 sn yoklama ≈ $596/ay · 20 sn ≈ $89/ay |

## 6. Geri alma

```bash
systemctl disable --now mosquitto
apt-get remove --purge -y mosquitto mosquitto-clients
rm -rf /etc/mosquitto /var/lib/mosquitto /etc/letsencrypt/live/<host>
ufw delete allow 8883/tcp; ufw delete allow 8084/tcp
```

Cihazlar `tetik.push_aktif=false` yapılınca yoklama emniyet ağına döner (kesinti olmaz).

---

## 7. Nerede çalıştırmalı: ev bilgisayarı mı, VPS mi?

| | Ev bilgisayarı (Asrock FX-6100 / 4 GB) | En ucuz VPS |
|---|---|---|
| Donanım yeterli mi | **Fazlasıyla** (600 TLS bağlantısı ≈ 20 MB RAM) | 1 vCPU / 1 GB yeter |
| Elektrik | FX-6100 boşta ~90–110 W → ayda ~70 kWh ≈ **$6–8** | yok |
| Sabit IP | Genelde **yok**; CGNAT varsa dışarıdan erişilemez | var |
| Erişim | Router'da **80/8883/8084 port yönlendirme** gerekir | hazır |
| Kesinti | Elektrik/internet kesilince **tüm tetikler durur** (cihazlar yoklamaya düşer) | veri merkezi |
| Kurulum | aynı `kur.sh` (Ubuntu/Debian gerekir) | aynı `kur.sh` |

**Öneri:** 600 cihaz hedefiyle **VPS**. Ev bilgisayarı pilot/1–20 cihaz için mantıklı; 600 cihazda
elektrik + kesinti riski VPS fiyatını zaten geçiyor.

### CGNAT kontrolü (ev sunucusu için şart)

```bash
# Router arayüzündeki "WAN IP" ile karşılaştır:
curl -s https://ifconfig.me ; echo
```

Aynı değilse **CGNAT** var → port yönlendirme çalışmaz, ev sunucusu dışarıdan erişilemez.
Çözüm: VPS, ya da bir tünel (cloudflared/ngrok) — MQTT için tünel önerilmez.

### En ucuz VPS seçenekleri (2026, ~)

| Sağlayıcı | Paket | Fiyat | Not |
|---|---|---|---|
| **Hetzner** (Falkenstein/Nürnberg) | CX22 (2 vCPU, 4 GB) | **~€3,79/ay** | En iyi fiyat/performans, TR'ye ~50 ms |
| Contabo | VPS S | ~€4,50/ay | Daha yavaş disk, çok RAM |
| Netcup | VPS 1000 G11 | ~€4/ay | EU |
| Oracle Cloud | **Always Free** (ARM 4 çekirdek/24 GB) | **$0** | Kapasite/hesap onayı sorunlu olabilir |
| AWS Lightsail | 1 GB | ~$5/ay | AWS faturasına eklenir |
| TR sağlayıcı (Turhost/Natro/Vargonen) | 1 vCPU/1 GB | ~₺150–250/ay | TR'ye ~10–20 ms gecikme |

> 600 cihaz için hepsi yeterli; seçim gecikme (TR DC) ve fatura para birimi meselesi.

## 8. Alan adı ve sertifika (ACM hakkında)

- **AWS ACM sertifikası burada KULLANILAMAZ**: ACM sertifikaları **dışa aktarılamaz**, yalnız
  ALB / CloudFront / API Gateway gibi AWS kaynaklarına takılır. Kendi sunucunuzda çalışan Mosquitto
  için **Let's Encrypt** kullanılır (script otomatik alır ve yeniler).
- `yourkiosk.hakkisabah.com` kullanmak için DNS'te **A kaydı** yeterli:

```
Tip: A   Ad: yourkiosk   Değer: <VPS IP>   TTL: 300
```

- Kayıt yayıldıktan sonra (kontrol: `dig +short yourkiosk.hakkisabah.com`):

```bash
sudo bash kur.sh --host yourkiosk.hakkisabah.com --eposta siz@example.com
```

- Sonuç: `wss://yourkiosk.hakkisabah.com:8084/mqtt` (panel) ve `yourkiosk.hakkisabah.com:8883`
  (cihazlar) — ücretsiz ve otomatik yenilenen gerçek sertifika. `nip.io` yalnız domain yoksa pratiktir.

---

## 9. AWS Lightsail ile kurulum (seçilen yol · $5/ay)

### 9.1 Instance oluştur (konsol)

1. AWS Konsol → **Lightsail** → **Create instance**
2. **Region**: `Frankfurt, eu-central-1` (S3/CloudFront ile aynı bölge, TR'ye ~50 ms)
3. **Platform**: Linux/Unix · **Blueprint**: *OS Only* → **Ubuntu 24.04 LTS**
4. **Plan**: **$5/ay** (1 GB RAM · 2 vCPU · 40 GB SSD · **2 TB transfer**)
5. **Name**: `yourkiosk-mqtt` → Create

> 600 TLS bağlantısı için 1 GB RAM fazlasıyla yeter (mosquitto bağlantı başına ~10–20 KB).

### 9.2 Statik IP (ZORUNLU)

Lightsail'in IP'si **instance durdurulup başlatılınca değişir** → DNS ve sertifika kırılır.
**Networking → Static IPs → Create static IP** → instance'a bağla (bağlıyken ücretsiz).
Not al: `<STATIK_IP>`.

### 9.3 Güvenlik duvarı (Lightsail'in kendi paneli)

**Networking → IPv4 Firewall** → şu kuralları ekle:

| Uygulama | Protokol | Port |
|---|---|---|
| SSH | TCP | 22 |
| HTTP | TCP | **80** (Let's Encrypt) |
| Custom | TCP | **8883** (MQTT/TLS) |
| Custom | TCP | **8084** (WebSocket/TLS — panel) |

> Burada açılmayan port sunucuda `ufw`'de açık olsa bile **dışarıdan erişilemez**.

### 9.4 DNS

`hakkisabah.com` DNS panelinde (Route53 ya da registrar):

```
Tip: A   Ad: yourkiosk   Değer: <STATIK_IP>   TTL: 300
```

Kontrol: `dig +short yourkiosk.hakkisabah.com` → `<STATIK_IP>`

### 9.5 SSH + kurulum

```bash
# kendi makinenizden
chmod 600 ~/Downloads/LightsailDefaultKey-*.pem
ssh -i ~/Downloads/LightsailDefaultKey-*.pem ubuntu@<STATIK_IP>

# sunucuda
sudo apt-get update -qq && sudo apt-get install -y -qq git
git clone https://github.com/hakkisabah/yourkiosk.git
cd yourkiosk
sudo bash deploy/mosquitto/kur.sh --host yourkiosk.hakkisabah.com --eposta siz@example.com
```

Betik sonunda iki parolayı basar ve `/root/yourkiosk-mqtt-credentials.txt` (0600) dosyasına yazar.

### 9.6 Doğrulama (kendi makinenizden)

```bash
MQTT_PAROLA_PANEL=… MQTT_PAROLA_CIHAZ=… \
  bash deploy/mosquitto/dogrula.sh yourkiosk.hakkisabah.com
```

Beklenen: TLS ✓ · panel yayını ✓ · cihaz aboneliği ✓ · **cihaz yayını RED** ✓ · anonim RED ✓ · 1883 kapalı ✓

### 9.7 Devamı

1. Panel `.env.local`: `VITE_MQTT_URL=wss://yourkiosk.hakkisabah.com:8084/mqtt` (+ konu/kullanıcı/parola) → `./panel/infra/yayinla.sh`
2. Cihazlarda `pip install paho-mqtt`
3. Panel → Tetikleme: `push_aktif=true` · `push_broker=yourkiosk.hakkisabah.com` · `push_port=8883` · `push_kullanici=cihaz` · `push_parola=…` · `kontrol_ms=300000`
4. (Öneri) Lightsail → **Snapshots** → otomatik snapshot aç (yapılandırma yeniden üretilebilir, ama geri dönüş hızlı olur)

### 9.8 Maliyet

| Kalem | Aylık |
|---|---|
| Lightsail $5 planı | $5,00 |
| Statik IP (instance'a bağlı) | $0 |
| Trafik (2 TB dahil; broker trafiği ~MB) | $0 |
| **Toplam** | **~$5** (3 sn yoklama $596 · 20 sn $89 ile karşılaştır) |
