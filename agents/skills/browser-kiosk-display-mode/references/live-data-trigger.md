# Canlı veri değişikliğini anında yansıtma (yoklama + tetikleyici)

Tarayıcı kiosk modunda "panelde veriyi değiştirdim, ekran ne zaman görür?" sorusunun tam sözleşmesi.
Tek başına saatlik yenileme yetmez; kullanıcı bunu ilk turda ister. Üç katman birlikte çalışır.

## 1. Küçük dosya yoklaması (her iki modda)

Saatlik tam yenilemeden ayrı, `DAMGA_KONTROL_MS` (10–30 sn) aralıkla YALNIZCA üst veri oku:
`lastupdate.json` (~40 bayt) + tetikleyici dosyası. Büyük veri dosyası damga değişmedikçe
**indirilmez** (kota/önbellek korunur). Yoklama önbelleğine takılmayın: tur içi damga memo'sunu
sıfırlayan ayrı bir "taze oku" yolu yaz.

## 2. Anlık bildirim (yerel sunucu varsa)

Sunucuya uzun yoklama ucu ekle: `GET /degisiklik?imza=<imza>&sure=<sn>` → imza değişene kadar
isteği açık tutar, değiştiği AN yanıt verir (tipik <1 sn); süre dolunca `degisti:false` nabzı
döner ve istemci yeniden bağlanır. SSE/WebSocket'ten basittir, kopan bağlantıda kendini toparlar.
Sunucu **threaded** olmalı (bekleyen istek diğerlerini bloklamasın). Uç yoksa (statik sunum)
sessizce yoklamaya düş.

Hızlı dönme koruması: uzun yoklama imza değişmediği hâlde anında yanıt verirse sıkı döngü oluşur —
imza değişmediyse kısa bir nefes (ör. 800 ms), imza boşsa daha uzun (5 sn). Test yazarken bu nefesi
hesaba kat (yoksa "anında" bekleyip kırmızı alırsın).

## 3. İmza: damga ≠ gerçek

İmzayı yalnız damga dosyasına (`lastupdate` mtime+boyut) ve tetikleyiciye bağlamak, damgayı
tazelemeyen her yazımı **görünmez** kılar: elle düzenleme, kopyalama, senkron aracı. Doğrusu:
imzaya **veri dosyasının** (ör. `lastSystemData.json`) `mtime+boyut`unu da kat (istenirse kısa
içerik özeti).

Aynı tuzağın istemci tarafı: veri önbelleği damgaya bağlıdır → damga eşitse **eski gövdeyi** servis
eder; bu yüzden bildirim yolunda önbelleği atlayan bir "zorla yenile" adımı şart.

Sözleşme: **damga = hızlı eleme, imza/mtime = gerçeğin kendisi, zorla yol = önbellek bypass'ı.**

## 4. Tetikleyici dosyası (panel → cihaz)

Yönetici paneli veriyi değiştirince `tetikle.json` yazar: `{zaman, ilceId, bolgeId, aciklama}`.

Kapsam kuralı: ilçe boş/`"*"` → tüm cihazlar; doluysa yalnız o ilçenin/bölgenin cihazları hemen
yenilenir; aynı `zaman` iki kez uygulanmaz. Böylece "değişikliğin olduğu ilçe" hedeflenir, diğer
cihazlar boşa yüklenmez.

Kuralı TEK yerde tut (ör. `core/tetik.py`) ve sunucu/uygulama/CLI hepsi onu kullansın; tarayıcı
tarafında da aynı kuralın saf fonksiyonunu yazıp test et (iki dil, tek sözleşme).

## 5. Zorla yenileme ve gösterim sürekliliği

- Tetikleyici, damga değişmeden gelebilir: "damga aynıysa yenileme" kapısını `zorla=True` ile aç
  ve varsa veri önbelleğini de temizle, yoksa tetikleyici görünürde hiçbir şey yapmaz.
- Yenileme gösterimi bozmasın: indeksi sıfırlama, orta panelde o an gösterilen kayıt korunmalı
  (yerel sürümdeki "yenile → geçerli indeksi göster" davranışı).

## 6. Cihazda elle doğrulama

Bir CLI yaz (`tools/nobet_tetikle.py --ilce …` / `--durum` / `--sil`): kullanıcı paneli beklemeden
uçtan uca doğrular, arıza ayıklaması saniyeler sürer.

## 7. Test listesi

- İmza, veri dosyası yazılınca değişiyor (damga aynı kalsa bile) ve `/degisiklik` bunu bildiriyor.
- Aynı tetikleyici iki kez uygulanmıyor; başka ilçenin tetikleyicisi bu cihazı yenilemiyor.
- Bildirim geldiğinde önbellek atlanıp taze gövde gösteriliyor (damga eşit olsa da).
- Yenileme sırasında gösterilen kayıt/indeks korunuyor.
