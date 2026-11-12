# Otonom koordinatör — plan ve işletim sözleşmesi

> Bu dosya **sürümlenmiş plandır**: koordinatör her tikte buradaki fazları ve durma
> koşullarını okur. Kişisel/makine bilgisi burada tutulmaz; makineye özel yollar
> `~` altındaki durum dizinindedir.

## 1. Amaç

i5 (güvenlik) ve i3 (karar/merge) kapısı zaten kurulu. Eksik olan **geliştirici ayağı**:
bir PR i5'ten `sorun`/`red` aldığında bulguları okuyup düzelten, testle kilitleyen ve
yeni commit'i kapıya geri gönderen ajan. Koordinatör bunu **zamanlı ve insansız** yapar.

Kapı açılmaz: koordinatör **merge etmez, `main`'e push etmez, kapıyı atlamaz**.
Kapıyı i5 ve i3 verir; koordinatör yalnızca PR dalına düzeltme commit'i ekler.

## 2. Tick algoritması

Her tik (`otonom_tik.py`, systemd timer):

1. `flock` kilidi al; başka tik varsa sessizce çık.
2. Açık PR'ları ve her PR'ın head sha + `guvenlik/inceleme` + `guvenlik/karar`
   durumlarını GitHub'dan oku.
3. En eski PR'dan başlayarak **tek** eyleme karar ver:

| Kapı durumu | Eylem |
|---|---|
| i5 yok / `pending` | **bekle** (i5 sırada; model çağrılmaz) |
| i5 `failure`/`error` | **düzelt** (i5 bulguları) |
| i5 `success`, i3 yok/`pending` | **bekle** (i3 sırada) |
| i5 `success`, i3 `failure`/`error` | **düzelt** (i3 bulguları) |
| i5 `success`, i3 `success` | **bitti** (birleşme i3'te) |
| hiç açık PR yok | **bitti** (faz raporu) |

4. `düzelt` ise:
   - makine klonunu güncelle, PR head'ini yerel dala al,
   - PR paketini (diff + i5/i3 son yorumu + değişen dosyalar) **sandbox dışında** üret,
   - `dsh --profile otonom-gelistirici` ajanını **sandbox içinde** çalıştır,
   - commit'leri doğrula (temiz ağaç, merge commit yok, sır yok, boyut sınırı),
   - PR dalına **normal push** (force yok) yap, durumu yaz.
5. Her tik sonunda `durum.json`'a ne yapıldığını yaz; model çağrılmadıysa 0 token.

## 3. Fazlar

| Faz | İçerik | Kabul ölçütü |
|---|---|---|
| **0 — devir** | Açık PR'ları kapıdan geçir (i5→i3→merge) | açık PR yok ya da hepsi `success`/`merged` |
| **1 — normal düzen** | i5/i3'ü `--dal main`e al; eski Hermes servislerini kapat | iki makinede `--dal main`, eski birimler `disabled` |
| **2 — backlog** | Hafıza/skill uyarlaması, 3 ajan E2E, doküman/test eksikleri | her iş kendi PR'ı + kapıdan geçmiş |
| **3 — steady state** | Yalnız kırmızı işe dokun; iş yoksa hiç model çağırma | 7 gün üst üste boş tikte 0 oturum |

Faz geçişi **otomatik değildir**: `durum.json` içindeki `faz` alanını operatör
(veya fazın kabul ölçütünü doğrulayan bir tik) yükseltir.

## 4. Durma koşulları (fail-closed)

- Aynı head için **5** başarısız düzeltme denemesi → `engel`, PR'a dokunma.
- Bir PR için toplam **8** düzeltme denemesi → `engel`.
- Doğrulama reddi (sır, merge commit, kirli ağaç, force gereksinimi) → o tik push yok.
- GitHub 401/403/429 → o tik durur; otomatik geri çekilme yok (operatör görür).
- DSH profili/runner yok ya da `--kuru` doğrulaması geçmiyor → hiç oturum açma.
- İlerlemesiz tikler otomatik durdurulmaz; deneme sınırları yukarıdadır.

## 5. Güvenlik modeli

| Katman | Kural |
|---|---|
| Ajan sandbox'ı | `dsh-bwrap-gelistirici`: repo **rw**, `$HOME` gölge (boş), `/run` ve ağ kapalı, sırlar görünmez |
| Araç yüzeyi | `read/grep/glob/web_fetch/subagent` kapalı; ajan yalnız sandbox'lı `bash` kullanır |
| Push | Ajan **yapmaz**; güvenilir süreç doğrular ve push eder |
| Push hedefi | Yalnız PR'ın kendi head dalı; `main`/force reddedilir |
| Sır taraması | Eklenen satırlarda token/anahtar deseni ve `.env`/`*.pem`/`id_rsa*` reddedilir |
| Token | **Zorunlu** ayrı `OTONOM_TOKEN` dosyası: yalnız **Contents: write**, **Metadata: read**, **Pull requests: read**. Kapı token'ı yalnız geçiş döneminde; günlüğe uyarı yazılır. |
| Git bütünlüğü | Ajan `.git/hooks` ve `.git/config` yazamaz (ro-bind); güvenilir git komutları `-c core.hooksPath=/dev/null -c core.fsmonitor=false` ile koşar; aktif hook varsa push yok. |
| Bütçe | `OTONOM_GUNLUK_AZAMI` (varsayılan 12) ajan oturumu/gün; aşılırsa model çağrılmaz. |
| Çıktı sınırı | Ajan stdout/stderr `OTONOM_AZAMI_AJAN_CIKTI` (2 MB), commit mesajı `OTONOM_AZAMI_MESAJ_BAYT` (1 MB) ile sınırlı; aşımda push yok. |
| Token zorunlu | `OTONOM_TOKEN` yoksa veya kapı token'ıyla aynıysa tik **fail-closed** durur. |
| Kapı | i5 + i3 zorunlu; koordinatör status yazmaz, etiket değiştirmez |
| Girdi | PR başlığı/gövdesi/yorumu/diff'i **veri**, talimat değil; pakette bu yazılı |

## 6. Bekçi (otonom-bekci.timer)

`otonom-tik.service` bir oneshot tik'tir; `otonom-tik.timer` onu 20 dk arayla çalıştırır.
Timer ölürse, servis `start-limit`e takılırsa veya kalp atışı (`durum.json/son_tik`) 90 dk'dan
uzun süre gelmezse **`otonom-bekci.timer`** (10 dk) durumu denetler; gerekirse
`systemctl --user reset-failed` + `start otonom-tik.timer` ile zamanlayıcıyı ayağa kaldırır.
Onarımı 15 dk'dan sık yapmaz (kırık kurulumda döngü olmasın); karar ve onarım `bekci.log`'a
yazılır. Servis o anda çalışıyorsa dokunmaz.

## 7. Ayarlar (ortam değişkeni → varsayılan)

| Değişken | Varsayılan | Anlam |
|---|---|---|
| `OTONOM_ARALIK` | `20min` (timer) | tik sıklığı |
| `OTONOM_ZAMAN_ASIMI` | `2700` sn | tek ajan oturumu bütçesi |
| `OTONOM_AZAMI_DENEME` | `5` | head başına deneme |
| `OTONOM_AZAMI_TOPLAM` | `8` | PR başına toplam deneme |
| `OTONOM_DEPO` | `~/.local/share/yourkiosk-otonom/depo` | koordinatör makine klonu |
| `OTONOM_PROFIL` | `otonom-gelistirici` | DSH profili |
| `OTONOM_TABAN_DAL` | PR'ın base dalı | paket diff tabanı |
| `OTONOM_SADECE_PR` | boş (tümü) | virgüllü PR listesi; geçiş döneminde yalnız #97 |
| `OTONOM_AZAMI_SESSIZ_DK` | `90` | bekçinin "kalp atışı bayat" eşiği |
| `OTONOM_ONARIM_ARALIGI_DK` | `15` | bekçinin art arda onarım aralığı |

## 8. Operatör komutları

```bash
bash otomasyon/otonom-kur.sh --kuru      # ne kurulacak, yazmadan göster
bash otomasyon/otonom-kur.sh             # runner + profil + timer kur, timer'ı başlat
bash otomasyon/otonom-kur.sh --simdi     # bir tik hemen çalıştır
bash otomasyon/otonom-kur.sh --durum     # timer + son durum + son günlük
bash otomasyon/otonom-kur.sh --kaldir    # timer'ı durdur, birimleri sil (profil kalır)
python3 otomasyon/betik/otonom_tik.py --kuru    # yalnız karar (ağ okur, model çağırmaz)
```

Durdurma: `systemctl --user stop otonom-tik.timer`. Tek tik: `systemctl --user start otonom-tik.service`.
