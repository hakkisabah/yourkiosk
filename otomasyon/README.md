# otomasyon/ — kısa başvuru

İnsanı döngüden çıkaran üç makine: **geliştirici (bu repo)** · **i5 (güvenlik incelemesi)** ·
**i3 (ikinci onay + birleştirme)**. Hepsi yalnız **GitHub** üzerinden konuşur (açık port yok).

## Komutlar (kısa yol — `.py` yazmaya gerek yok)

| Komut | Ne yapar |
|---|---|
| `./otomasyon/durum` | i5/i3 haberleşmesi: son commit'ler, açık PR'lar, kararlar |
| `./otomasyon/kontrol --rol i3 --yazma-dene` | ortam + izin denetimi (Contents yazma dâhil) |
| `./otomasyon/koruma --durum` | branch protection'ın mevcut hâli (salt okuma) |
| `./otomasyon/koruma --uygula --kontrol "guvenlik/inceleme,guvenlik/karar"` | korumayı uygula (yönetici token) |
| `./otomasyon/topla --cikti /tmp/paket.json` | bağlam paketi (diff + sır/riskli kod taraması + PR'lar) |
| `./otomasyon/yaz /tmp/karar.json [--birlestir] [--cift-onay]` | kararı GitHub'a yaz; koşullar tamamsa birleştir |
| `bash otomasyon/kur.sh i5 --cron` | makine kurulumu (denetim + sarmalayıcılar + cron) |

## Akış (D modu)

```
ben: dal + commit + PR
  ├─► i5 (30 dk): topla → incele → guvenlik/inceleme = success|failure + PR yorumu + etiket
  ├─► i3 (30 dk): i5 onayı varsa ikinci inceleme → guvenlik/karar + (koşullar tamamsa) SQUASH MERGE
  └─► ben: birleşen commit'i çeker, sonraki işe geçer
```

Zorunlu kontroller: `guvenlik/inceleme` **ve** `guvenlik/karar` → ikisi `success` olmadan birleşme yok.
Durdurma: PR'a `birlestirme/durdur` etiketi · `hermes cron pause <job_id>`.

## Dosya düzeni

```
otomasyon/
├── durum, koruma, topla, yaz, kontrol   # /bin/sh sarmalayıcıları (doğru yorumlayıcıyı seçer)
├── kur.sh                               # makine kurulumu
├── betik/                               # Python araçları
├── prompt/i5-guvenlik.md, i3-karar.md   # makinelerdeki ajanın görev tanımı
├── IS-AKISI.md                          # roller, durum makinesi, maliyet, sınırlar
└── KURULUM.md                           # adım adım kurulum + sorun giderme
```
