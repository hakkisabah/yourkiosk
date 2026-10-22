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
