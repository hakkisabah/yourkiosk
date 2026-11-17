# AGENTS.md — yourkiosk

Bu dosya depo bağlamıdır; her makinede aynı okunur. Kişisel/makine bilgisi buraya girmez.

## 1. Proje nedir

Eczane nöbet ekranı: **600+ kiosk** (Qt masaüstü + Chromium tarayıcı modu), yayın verisi
S3 + CloudFront, yönetim paneli Vue 3 + Vuetify 3 + TS + Cognito, MQTT ile "şimdi güncelle".

| Dizin | İçerik |
|---|---|
| `kiosk/` | PyQt6 kiosk uygulaması + `tools/` + `tests/` |
| `web/` | tarayıcı (Chromium kiosk) modu — TS, vitest |
| `panel/` | yönetim paneli + `infra/` |
| `deploy/` | mosquitto, systemd, docker, cihaz betikleri |
| `docs/` | AWS, maliyet, mimari, güvenlik |

## 2. Komutlar

```bash
kiosk/tools/test.sh            # Qt testleri (offscreen)
cd panel && npm test           # vitest
cd web   && npm test
```

`NODE_ENV=production` dışa aktarılmışsa `npm ci --include=dev` kullan.

## 3. Değişmez kurallar

1. **Sır depoya girmez.** Token/parola `~/.config/yourkiosk-secrets/` altında, 0600.
   `VITE_*` pakete gömülür → sır olamaz.
2. **`main` korumalı:** doğrudan push yok; her değişiklik dal + PR.
3. **Davranış değiştiyse test de gelir.**
4. Yanıtlar ve commit mesajları **Türkçe**; kod yorumları Türkçe, tanımlayıcılar İngilizce.
5. Tasarım/iskelet kullanıcıya aittir; onay almadan görsel değerleri değiştirme.
6. Doküman sayıları koddan türetilir; süre/sınır değişince aynı PR'da güncelle.

## 4. Bağlam nerede

| Bilgi | Yeri |
|---|---|
| Proje kuralları, komutlar | bu dosya |
| Tehdit modeli, kabul edilmiş riskler | `docs/GUVENLIK-BAGLAM.md` |
| AWS kurulumu/kimlikler | `docs/AWS-KURULUM.md` |
| Maliyet/kota | `docs/ONBELLEK-VE-MALIYET.md` |
| Cihaz sertleştirme | `kiosk/GUVENLIK.md` |
