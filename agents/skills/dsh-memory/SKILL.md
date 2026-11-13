---
name: dsh-memory
description: "Kalıcı DSH hafızasını oku, ara ve güncelle (MEMORY.md / USER.md)."
whenToUse: "Uzun proje işine başlarken, kullanıcı tercihi öğrenince veya kalıcı bir ortam/karar notu gerektiğinde."
---

# DSH hafızası

DSH'de Hermes'teki otomatik `memory` aracı yok; bu skill dosya tabanlı hafızayı kullanır.
Hafıza **makineye özeldir**, repoya girmez; proje kuralları repo `AGENTS.md`'de kalır.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `~/.agents/memory/MEMORY.md` | Ajan notları: ortam, kararlar, tuzaklar, doğrulanmış komutlar |
| `~/.agents/memory/USER.md` | Kullanıcı profili: dil, çalışma biçimi, beklentiler |

İkisi de 0600'dür. **Sır yazma** (token, parola, API anahtarı); yalnız yolunu/adını yaz.

## Akış

1. Uzun işe başlarken oku:
   ```bash
   ~/.agents/bin/dsh-memory list
   ~/.agents/bin/dsh-memory list --user
   ```
2. İlgili geçmişi ara:
   ```bash
   ~/.agents/bin/dsh-memory search "aws"
   ```
3. Kalıcı bir gerçek öğrendiğinde ekle (kısa, tek cümle, en fazla 500 karakter):
   ```bash
   ~/.agents/bin/dsh-memory add "AWS eu-central-1; kova yourkiosk-veri"
   ~/.agents/bin/dsh-memory add "Türkçe, adım adım, sayılı trade-off ister" --user
   ```
4. Geçici durum (PID, bugünkü log, yarım iş) hafızaya değil `/tmp/ILERLEME.md`'ye yazılır.

## Sınırlar

- Aynı not ikinci kez eklenmez (birebir satır kontrolü).
- `MEMORY.md` 12 KB, `USER.md` 8 KB sınırı; dolunca eski notları birleştir/kırp.
- Not, doğrulanmamış tahmin değil **kanıtlanmış gerçek** olmalı; tarih otomatik eklenir.
- Kullanıcı tercihi değiştiyse eski notu silmek yerine yeni not ekle; çelişkiyi belirt.
