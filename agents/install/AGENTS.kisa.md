# DSH kullanıcı bağlamı

- Kullanıcı Türkçe konuşur; yanıtları Türkçe bekler. Kod yorumları Türkçe, tanımlayıcılar İngilizce.
- Adım adım, doğrulanabilir talimat ister; her adımın test/çıktısı gösterilmeli.
- Sır değerini raporlama; yalnız yolunu ve 0600 olduğunu söyle.
- Tasarım kullanıcıya aittir; onay almadan görsel değerleri değiştirme.
- Eski işi silmek yerine arşivle; temiz klasörde başla.
- Hata sınıfları için makineyle doğrulanan kontrol noktası ister.

## Makineler

| Makine | Adres | Rol |
|---|---|---|
| aceri5 | 192.168.1.51 | geliştirici; DSH Web :3080 |
| i5 | 192.168.1.52 | inceleme |
| i3 | 192.168.1.50 | karar |

i5/i3: sudo yok; ağır Node komutları için bellek tavanlı koşucu kullan.

## DSH

- Checkout: /home/hakki/deepseek-harness (yerel).
- Headless: node apps/cli/lib/bin.js --profile <profil> -
- Proje kuralları: depodaki AGENTS.md.
- Ajan sistemi: depo içindeki agents/ (config, roller, skill index).

## Sırlar

~/.config/yourkiosk-secrets/ (0600). Depoya sır girmez.

## Hafıza

- ~/.agents/memory/USER.md (kullanıcı tercihleri)
- ~/.agents/memory/MEMORY.md (kalıcı dersler)
- Skill'ler: ~/.agents/skills/ + SKILL-INDEX.md; gövde yalnız ihtiyaçta çağrılır.
