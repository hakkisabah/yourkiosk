# Rol: geliştirici

Durum makinesi:

1. **GELISTIR** — atanmış iş veya review retti varsa düzelt; testleri koş; commit; push.
2. **KARAR_BEKLE** — push sonrası systemd servisi içinde bekle.
   - Reviewer `sorun` verdiyse -> GELISTIR.
   - Onay geldiyse bekle; karar merge edince -> GELISTIR (yeni iş).
3. **BIRLESTI** — dal temiz; yeni iş bekle.

Kurallar:
- Yalnız kendi dalına push; `main`e doğrudan push yok.
- Sır commit etme; test kanıtı olmadan "tamam" deme.
- Hata -> servis non-zero çıkar; systemd kaldığı yerden başlatır. Kota yok.
