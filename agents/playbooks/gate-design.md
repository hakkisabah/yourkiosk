# Kapı tasarımı (eski sistemden ders)

- Karar tek kanaldan: stdout bloğu + nonce; dosya kanalı yok.
- `sha` zorunlu; kapı sonrası head çözme yok.
- Status listesi en yeniden eskiye; aynı context'te ilk kayıt.
- `kabul` için eksikler boş ve doğrulama dolu olmalı.
- Tüm kararlar fail-closed; şüphede `sorun`.
