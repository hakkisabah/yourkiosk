---
name: browser-kiosk-display-mode
description: Use when building or debugging a Chromium kiosk web display.
version: 1.0.0
author: agents
license: MIT
metadata:
  agents:
    tags: [chromium, kiosk, vue, vite, cache-storage, remote-diagnosis, parity]
    related_skills: [pyqt6-kiosk-hardening, ts-monorepo-build-gotchas, systematic-debugging]
---

# Tarayıcı (Chromium kiosk) gösterim modu

Yerel bir uygulamanın (PyQt/Gtk/Electron) **ikinci gösterim modu**: aynı görünüm, aynı davranış,
aynı veri kuralları — Chromium kiosk olarak. Yerel taraf için `pyqt6-kiosk-hardening` şemsiyesine bak.

## When to Use

* Kiosk/ekran uygulamasının **tarayıcı alternatifi** isteniyorsa (yerel sürümle birebir eşleşerek),
* tarayıcı modunda **boş/siyah/beyaz ekran**, "veri yüklenemedi" ya da "kiosk modunda açılmıyor"
  şikâyeti geldiğinde,
* 127.0.0.1'de statik sunucu + URL parametresinde cihaz kimliği taşıyan arayüz kurarken,
* tarayıcı erişimi olmayan makinede bu arayüzü **test ederek** doğrulamak gerektiğinde.

## 0. Ayar grubu: mod anahtarı (her zaman)

Gösterim modunu **ayar dosyasından** seçilir yap (`mod = qt | tarayici`) ki yönetim paneli
çevirebilsin. Giriş noktası modu okuduktan sonra **yerel araç setini hiç import etmeden** dispatch
etsin (`import PyQt6` satırına hiç gelinmemeli). Cihaz kimliği, adres ve veri modu sunucu tarafında
kurulur; web arayüzü ayar dosyasını **kendi yerel kaynağından** okur.

## 1. Sunucu + URL sözleşmesi

* Arayüzü **127.0.0.1** üzerinde küçük bir statik sunucudan sun (stdlib HTTP + thread yeter). Kiosk
  için kimlik doğrulaması gerekmez; **yerel bağlanma** asıl savunmadır.
* Cihaza özgü tek bilgi **URL parametresidir**: `index.html?clientID=<cihaz>&veri=yerel|https[&taban=<adres>]`.
  Sayfa ilçe/bölgeyi kendisi bulur; sunucuda şablon/SSR yok.
* **`veri=https` tek başına yetmez: `taban` da yazılmalı.** Sayfa adresi `${taban}/${dosya}` diye
  kurar; `taban` boşsa **sessizce yerel kaynağa düşer** — https modu "çalışıyor" görünür ama veri
  hâlâ yerelden gelir (loglarda hata yok). URL'i üreten TEK fonksiyon, mod `https` iken yapılandırılmış
  veri kökünü `taban` olarak eklesin; sondaki `/` atılsın (`//` 404 üretir), tanınmayan mod `yerel`e
  düşsün. Birim testi: https+adres → `taban=` kodlanmış ve sonda `/` yok · https+boş adres → parametre
  yok · bilinmeyen mod → `veri=yerel`.
* **Sondaki `/` yalnız URL üreticisinde değil, VERİ OKUYUCUSUNDA da temizlenmeli.** Okuyucu
  `${taban}/${dosya}` diye birleştiriyorsa `https://…/` tabanı `https://…//match.json` üretir →
  S3/CloudFront **403** → dosya okunamaz ("match.json bulunamadı" gibi yanıltıcı hata). İki çalışma
  zamanı (yerel + tarayıcı) varsa **ikisi de** `rstrip('/')` yapmalı: biri yapıp diğeri yapmıyorsa
  arıza yalnız tek modda görünür. Regresyon testi üç durumu kilitler: tek `/`, çoklu `///`, slash yok.
* **Ayar dosyaları da moda uysun.** `veri=https` iken `ayarlar.json`/`kapsam-ayarlari.json` de `taban`dan
  okunmalı; aksi hâlde panelden yapılan ayar değişikliği cihaza **hiç** ulaşmaz (yalnız veri dosyaları
  uzaktan gelir). Okuma sırası: uzak → son iyi kopya (bellek + `localStorage`) → yerel dosya →
  varsayılan. Cihaza/ağa özgü anahtarlar (veri kaynağı, taban adresi, izin listesi) yayınla
  ezilmemeli. Şemsiye kurallar: `edge-device-remote-config`.
* Beyaz liste: yalnızca arayüz varlıkları + **adı bilinen** veri dosyaları + tasarım görselleri (yerel
  klasörden, kopyalamadan). **Cihaz kimliği dosyasını ve günlükleri ASLA sunma** (403) — kimlik URL'de
  gelir. `..`/sembolik bağ reddi, dizin listesi kapalı, uzantı beyaz listesi.
* JSON yanıtlarına `no-store` (damga/tazelik her turda okunur), görsellere `max-age`.
* **İsteğe bağlı ayar dosyaları eksikse 404 DEĞİL varsayılan içerik döndür** (200 + JSON): panelin
  yazacağı `ayarlar.json`/`kapsam-ayarlari.json` cihazda çoğu zaman yoktur; 404 konsolu kirletir ve
  "sunucu bozuk" izlenimi verir. Yerel uygulama da yoksa varsayılanı kullanır — aynı anlamı HTTP'de kur.
* Derlenmiş HTML'e işaret koy (`<meta name="application-name" content="...">`): başlatıcı "portta bizim
  sunucu mu" denetimini bununla yapar ve yabancı servisi boş porta atmaz.
* `--kuru`/`--dry-run` kipi: URL + tarayıcı komutunu yazdır, hiçbir şey başlatma.

## 2. Derlenmiş çıktıyı sun, kaynağı DEĞİL (en sık kök neden)

* Tarayıcı **TypeScript çalıştıramaz**: kaynak `index.html` (`/src/main.ts`) sunulursa modül yüklenmez.
  CSS ayrı dosya olduğu için arka plan yine boyanır → "beyaz" değil **siyah** ekran görünür.
* Sunucu kökü: **derlenmiş klasör varsa o** (`web/dist`), yoksa *açma*: anlaşılır hata + özel çıkış
  kodu + `npm install --include=dev && npm run build` komutunu yazdır. Boş ekran bırakmak, hata
  vermekten kötüdür.
* `npm ci`/`npm install`, `NODE_ENV=production` ortamında devDependencies'i atlar → `--include=dev`.
* **Kurulum betiği derlemeyi "çıktı yoksa" koşuluna bağlamasın.** `if [ ! -f web/dist/index.html ]`
  yazan bir betik, dist bir kez oluştuktan sonra kaynak değişse bile **hiç derlemez**; kullanıcı
  "düzelttim, hâlâ aynı hata" der ve sen kodda olmayan bir hatayı kovalarsın. Kural: kaynak
  (`src/`, `index.html`, `package.json`, `vite/tsconfig`) çıktıdan **yeniyse** derle; derleme hatasını
  `>/dev/null 2>&1` ile **yutma** (çıktıyı göster, sıfırdan farklı kodla dön) ve başarılı derlemede
  çıktı klasörüne **damga** yaz (`dist/surum.json`: git sha + zaman).
* **Teşhis, çalışan paketi kanıtlasın.** `--tani` raporu paket adını + mtime'ını ve damgayı (git sha)
  bassın; kaynak damgadan yeniyse "dist ESKİ → yeniden derle" uyarısı versin. Kullanıcının gördüğü
  hata metni depodaki kodla uyuşmuyorsa ilk şüpheli **eski pakettir**, kod değil: yeni metin pakette
  var mı diye `grep -c "<yeni mesaj>" dist/assets/index-*.js` ile doğrula ve bu komutu kullanıcıya ver.

## 3. Chromium kiosk başlatma

* `--kiosk <url>` (URL **konumsal**). `--app=<url>` ile `--kiosk`'u BİRLİKTE kullanma: bazı Chromium
  sürümlerinde boş/siyah pencere verir.
* `--user-data-dir=<kalıcı profil>` (incognito **değil**) → disk/HTTP/Cache Storage önbelleği yeniden
  başlatmada korunur; trafik/maliyet kazancının yarısı budur.
* Siyah ekrana karşı varsayılan: `--disable-gpu --disable-gpu-compositing --disable-dev-shm-usage`.
* Gürültüyü kes: `--disable-background-networking --disable-component-update --disable-sync
  --noerrdialogs --disable-breakpad`. Google servis hataları (`PHONE_REGISTRATION_ERROR`,
  `DEPRECATED_ENDPOINT`) **zararsızdır** — açılmamayla ilgisi yok; kullanıcıyı yanlış yola sürüklemeyin.
* Ek bayraklar ayar dosyasından verilebilsin (boşlukla ayrılmış tek anahtar).
* Tarayıcı bulunamazsa yedek adları dene (`chromium-browser`, `google-chrome`); yoksa net hata + kod.
* Kapanınca kaç saniye sonra açılacağı ve **çökme döngüsü sınırı** (ör. 60 sn'de 5) ayarda olsun.
* Tüm bayraklar + gerekçeleri: `references/chromium-kiosk-flags.md`.

## 4. Teşhis: boş ekranı "tahmin"le kovalamayın

Sırayla kur; sonra kullanıcıdan **hata metnini** isteyin — iki turda kök neden bulunur.

1. **Uygulama kabuğuna hata yüzeyi koy (ilk iş).** `index.html` içinde paketten bağımsız satır içi
   betik: `window.onerror` + `unhandledrejection` → okunabilir **kart** (hata + yığın + adres); 6 sn
   sonra kök eleman hâlâ boşsa "arayüz başlatılamadı" kartı + doğrulama komutu. Böylece her boş/siyah
   ekran eyleme dönüşür.
2. **`--tani` (teşhis) kipi:** tarayıcıyı `--enable-logging=stderr --v=1` ile başlat → **tarayıcı
   konsolu terminale düşer**. Ayrıca tarayıcı açılmadan önce rapor bas: derlenmiş mi, tarayıcı
   yolu+sürümü (min sürüm altındaysa uyar), cihaz kimliği dosyada var mı, hangi yol hangi HTTP
   kodu/boyut/içerik türüyle sunuluyor, veri kaç gün/yayın içeriyor.
3. Kullanıcıdan istenecekler: `--tani` raporu **ve** konsol satırları. "Konsolu aç" demek yetmez;
   kiosk modunda konsol görünmez.
4. Uygulama-içi hata kartı da olsun: veri yüklenemezse sebep + başlatma biçimi yazılsın.
5. **Ekran üstü teşhis katmanı (kiosk'ta konsol yok):** bir tuşla (`d`/`F8`) açılan kaplama —
   sayfa adresi, `hazır/hata`, cihaz kimliği + veri modu, eşleşen kapsam, kayıt sayısı + gösterilen
   kayıt, yayın modu + görsel adresi, önbellek durumu + damga, özellik anahtarları, **son N günlük
   satırı**. Kullanıcı fotoğraflar; "hangi durumda kaldı" sorusu tahmine dönüşmez. Durumu ve
   günlüğü arayüz durumuyla aynı yerden oku (ikinci bir kayıt tutma).
6. **Hata mesajları sebebi AYIRSIN: "okunamadı" ≠ "kayıtta yok" ≠ "kimlik boş".** Üç ayrı arızayı
   tek `if (!bulundu)` dalına yazmak her turda yanlış katmanı arattırır. Ayrı mesaj + ayrı log satırı:
   (a) belge hiç okunamadı (403/404/CORS/ağ → istenen tam adresi yaz), (b) belge okundu ama cihaz
   kimliği eşleşmiyor, (c) kimlik kaynağı okunamadı → clientID boş. Üçünü kapsayan birim testi yaz.

## 4.1 İlk kurulum: cihaz verisi DEPODA YOKTUR

Temiz bir klonda tarayıcı modu açılır ama veri yoktur: `lastSystemData.json`,
`match.json`, `lastupdate.json` ve cihaz kimliği dosyası `.gitignore`'da olduğu için klonda hiç
bulunmaz. Kullanıcı bunu "kaynak json bulunamadı / veri yüklenemedi" olarak görür ve uygulamada
olmayan bir hata arar.

* Eksik veriyi **genel veri hatasıyla karıştırma**: kartta dosya adını, "bu dosyalar cihaza
  özgüdür, depoya girmez" açıklamasını ve **çalıştırılacak komutu** yaz
  (`python3 tools/fetch_nobet.py` ya da eski kurulumdan `cp … kiosk/`). Sadece "veri okunamadı"
  demek, kullanıcıyı kod tarafında saatlerce arattırır.
* `--tani` raporu "cihaz verisi : EKSİK → <dosyalar>" satırını ve çözümü yazsın; **başlatıcı da
  tarayıcıyı açmadan önce** terminale aynı uyarıyı bassın (kart görünse bile kullanıcı terminalde
  de görsün).
* Bu yolu **test et**: `fetch` her isteğe 404 dönerken kartın dosya adını ve komutu içerdiğini
  doğrulayan bir render testi + `tani_raporu`'nun eksik dosyaları listelediğini doğrulayan bir
  birim testi. Aksi hâlde düzeltme ilk temiz klonda sessizce geri gelir.
* Testte **boş `caches` taklidi** kullan: önceki testler gerçek veriyi Cache Storage'a yazmışsa
  404'e rağmen gövde önbellekten gelir ve yanlış hata mesajını (ör. `match.json` bulunamadı)
  doğrulayıp yanlış yeri düzeltirsin.

### Veri üreten aracın kendisi de "profesyonel" davranmalı

Cihaz verisini üreten araç (`fetch_nobet.py` benzeri) temiz klonda **çalışmaz** — kimlik dosyası
yoktur. Kullanıcı burada takılır, çünkü hata bir Python traceback'idir:

* Beklenen her durum için **çıkış kodu + çözüm satırı**: kimlik yok (nereden bulunur: panel/S3/eski
  kurulum + oluşturma komutu), ağ yok (`--yerel` ile eldeki dosya), izin yok (`--cikti-dizin`),
  biçim bozuk. `main()`i sarmalayıp `FileNotFoundError`/`PermissionError`/`URLError`/`ValueError`
  için tek satır mesaj ver; traceback yalnız gerçek programlama hatasında kalsın.
* **`--kontrol` (yalnız denetim) ve `--cihaz-id <id>` (kimliği oluştur)** bayrakları koy: kullanıcı
  uzaktan tek komutla "neyim eksik" sorusunu yanıtlar; temiz klonda uçtan uca çalışabilsin.
* **Varsayılan değer sessizce kimlik/konum değiştirmesin.** `--cihaz-bolge` gibi bir varsayılan,
  cihazın `match.json` kaydını başka bölgeye taşırsa kiosk **yanlış eczaneleri** gösterir ve bunu
  kimse fark etmez. Yazmadan ÖNCE eski eşlemeyi oku, bölge/ilçe adı değişiyorsa **dur**
  (eski↔yeni değerleri + `--zorla` ipucu + çıkış kodu). Karşılaştırmada büyük/küçük harf ve fazla
  boşluğu normalize et.
* `--cikti-dizin` ile verilen klasör (ve `data/` alt klasörü) yoksa **oluştur**; "dosya bulunamadı"
  hatasını yanlış yere (kimlik/ağ) yorma.
* Bu davranışları birim testiyle kilitle (kimlik yok → SystemExit(3)+metin, `--cihaz-id` → dosya
  oluşur, bölge değişimi → uyarı, aynı bölge → uyarı yok).
* **Temiz klonda doğrula**: `git clone` (venv yok, cihaz verisi yok) + araç → uçtan uca. "Benim
  dizinimde çalışıyor" bir doğrulama değildir; kullanıcı tam olarak bu yüzden ikinci makinede takılır.

## 5. Tarayıcı yokken doğrulama

* **Kurulu bir chromium varsa ÖNCE gerçek başsız (headless) doğrulama yap.** jsdom mantığı sınar;
  gerçek paket, gerçek CORS ve gerçek konsol yalnız tarayıcıda görünür. Bayrak tuzakları ve asgari
  çağrı: `references/chromium-kiosk-flags.md` §Headless doğrulama (`--headless=new` ve boşluklu
  `--screenshot` → "Multiple targets", `--user-data-dir` → asılma). Tarayıcı yoksa aşağıdaki jsdom
  yolu geçerli.

* **jsdom render testi**: arayüzü **gerçek veri dosyalarıyla** mount et, `fetch` + `caches` taklidi
  ver, DOM'da bekle (satır sayısı, ana metinler, saat biçimi, **hata kartı YOK**). `server.fs.allow:
  ['..']` kök dışına bakmak için gerekli. jsdom ortamında `node:fs`/`node:path` **çalışmaz**
  (`fileURLToPath is not a function`), ama cihaz verisini **statik `import` da etme** — dosya depoda
  olmadığı için temiz klonda `npm run build` `TS2307` ile patlar. Doğrusu `import.meta.glob` +
  `describe.skipIf`; tam tarif ve vitest major'ında `defineConfig` tuzağı:
  `ts-monorepo-build-gotchas` §11–12.
  `new URL(..., import.meta.url)` varlık çözümlemesine takılır; kullanma.
* **Durum makinesini saf mantık olarak test et** (sahte zamanlayıcı + sahte veri kaynağı): mod döngüsü,
  yayın sırası/süresi, kaydırma hedefi, özellik bayrakları. Zamanlayıcı/rAF çağrılarını ince
  sarmalayıcılardan geçir ki node ortamında da koşsun.
* Yerel uygulamanın **belgelenmiş** sayılarını (kaydırma hedefleri, süreler, ölçüler) porta test
  olarak koy: "birebir aynı" iddiası böyle sayıyla kanıtlanır.
* **Üretilen sınama verisi (fixture) uygulamanın GÖSTERECEĞİ pencereye yazmalı.** Zaman penceresine
  göre veri seçen bir uygulamada, "ilk N bloğu doldur" diyen bir üretici aracı, veri seti çok günlü
  hâle geldiğinde **yanlış blokları** doldurur (uygulama "şimdi"yi içeren bloğu gösterir) → ekranda
  hiçbir şey değişmez ve sen kodda olmayan bir hatayı kovalarsın. Kural: (1) hedef blok = şimdiyi
  içeren blok (±1), (2) geçersizleşme damgasını da tazele, (3) araç **ekranda gösterilecek bloğu ve
  kayıt sayısını** yazsın ("ilk günde 8 kayıt" yanıltıcıdır), (4) kayıtların kendi `start/end`
  penceresi yoksa pencerenin blok tarihinden türetildiğini hesaba kat.
* **Cihazın canlı verisine bağlı test yazma.** Yayın penceresi daralan bir günde liste tek kayda
  düşer ve test `IndexError`/eksik ayırıcı ile kırılır (kod değişmediği hâlde). Test verisini
  **kaynağa** enjekte et (ör. `pharmacies` özelliğini `monkeypatch` ile değiştirip hazırlama
  fonksiyonunu çağır); türetilmiş listeyi (`ticker_items`) elle doldurmak işe yaramaz. Ayrıntı +
  diğer varyantlar: `ts-monorepo-build-gotchas` §13.
* **Bir doğrulama prosedürünü kullanıcıya vermeden önce bağlı olduğu ARACI doğrula.** "Şu komutu
  çalıştır" dedikten sonra "işe yaramadı" gelirse şüpheli sırası: önce araç/fixture, sonra önbellek,
  en son uygulama kodu. Bozuk bir yardımcı araç, uygulamada olmayan bir hatayı rapor ettirir ve
  bir tur kaybettirir.

### Operatör tarifi: "N kayıtlı, kaydırmalı" görünümü canlı doğrulama

Kullanıcı bu adımları unutur; her seferinde dört satır hâlinde ver (tahmin etme, aracın kendi
çıktısına dayan):

```bash
cd <proje>/kiosk
python3 tools/<fixture-araci>.py --adet 8 --kuru   # planı göster: hangi blok, kaç kayıt
python3 tools/<fixture-araci>.py --adet 8          # yaz + damgayı tazele
python3 tools/tarayici_kiosk.py                    # ya da yerel mod: python3 main.py
# ekranda: sol panelde 8 satır; 6. kayda gelince liste kayar; `d` kaplaması kaydırma değerini yazar
python3 tools/<fixture-araci>.py --geri-al         # veri + damga birlikte geri
```

- "Kuru" çıktısındaki **gösterilecek blok** ile ekranda gördüğünüz blok aynı olmalı; farklıysa
  araç yanlış bloğu dolduruyordur (bkz. yukarıdaki fixture kuralı).
- Beklenen sayıları (satır sayısı, satır yüksekliği, kaydırma hedefi) **önceki oturumda ölçülmüş
  değerlerden** ver; "kaydırma oluyor mu" gibi öznel bir ölçüt bırakma.
- Test bitince `--geri-al` çalıştırılmazsa cihaz sahte kayıtlarla kalır — bunu adımın parçası yap.

## 6. Tasarım eşliği: token'ları ÜRET, elle yazma

* Yerel koddan (config + satır içi ölçüler) bir JSON üreten araç yaz; web arayüzü bu dosyayı **CSS
  değişkeni** olarak `<html>`e uygular (punto/renk/ölçü tek yerde).
* Yerel kodda **satır içi** duran değerler için üreticiye değer + (dosya, o dosyada bulunması gereken
  ifade) üçlüsü koy; test **ifadenin hâlâ dosyada olduğunu** denetlesin → yerel taraf sessizce
  değişirse test kırmızı olur.
* Üretici dosyasının **güncel** olduğunu ayrı test kilitler (üret → karşılaştır; fark varsa "yeniden
  üret" mesajı).
* **Ölçüleri CSS'e yazarken BİRİM ekle.** Yerel toolkit değerleri **sayıdır** (1080, 208, 3);
  `height: var(--ekran-y)` içine birimsiz sayı yazılırsa CSS değeri geçersiz sayar ("invalid at
  computed-value time") ve özellik ilk değerine düşer → `height: auto`. Sahnenin çocukları
  `position: absolute` ise sahne yüksekliği **0** olur ve arkadaki gövde rengi (siyah) görünür:
  konsolda **hiç hata yok**, ekran siyah. Kural: sayısal değeri daima `px` ile (süreleri `ms`)
  yaz; sayısal metin ('3') dahil. Yanlış/eksik anahtar (ör. `viewport_yukseklik` ↔
  `viewport_yuksekligi`) aynı sonucu verir → eksik değerde **gürültülü hata fırlat**, sessizce
  `undefined` yazma.
* Bu sınıf için iki test şart: (1) üretilen hiçbir değişken **birimsiz sayı** değil ve uzunluk
  değişkenleri `px` ile bitiyor; (2) **CSS'teki her `var(--x)` üretiliyor** (tanımsız değişken de
  `height:auto` yapar). Ayrıca değişkenleri **gerçek `<html>`e** uygulayan bir render testi olsun:
  jsdom yerleşim hesaplamadığı için "0 yükseklik" doğrudan görünmez; test değişkenin `1080px`
  olduğunu doğrulasın.
* Testteki **gerçek saat bağımlılığını** kaldır: gün bloğu/nöbet penceresi kuralı zamana bağlıdır,
  veri setinin dışına çıkıldığında ya da 08:30 sınırı geçildiğinde "satır sayısı 2 → 1" gibi
  yalancı kırmızılar çıkar. `vi.useFakeTimers({ toFake: ['Date'] })` + `vi.setSystemTime(...)`
  ile veri aralığına sabitle (yalnızca `Date` taklit edilsin; zamanlayıcılar gerçek kalsın ki
  `waitFor` çalışsın). Kanıt: kilitlenmiş saatle beklenen sayı **tam** yazılabilir.
* Tasarım görsellerini kopyalama; aynı dosyalardan sun (tek kaynak).
* Portlanan kurallar **yapıya** göre olsun: yerel taraf ilçe/bölge süzmeyi ağaç anahtarlarıyla
  yapıyorsa port da öyle yapsın. Kayıt içindeki alanlara göre süzmek, alanlar dolu olan gerçek veride
  farkı gizler — testte yapı ile alanları **bilerek çeliştir**.

## 7. Önbellek (maliyet): Cache Storage sözleşmeleri

Ayrıntı + katı taklit tarifi: `references/cache-storage-contracts.md`. Özü:

* Anahtar **geçerli http(s) URL** olmalı (aynı kaynak altında sentetik yol: `/__onbellek/veri/<ad>`);
  `meta:`/`gorsel:` gibi şemalar `put`ta fırlatır.
* **`cache.keys()` `Request` döndürür**, string değil → karşılaştırmadan önce metne çevir.
* Yazma hataları gösterimi DÜŞÜRMESİN: yazımları sarmala, hata olursa önbelleği kapat; `open` sonrası
  yaz-oku-sil ile gerçekten çalışıyor mu diye denetle.
* Veri önbelleğini `lastupdate` damgasına bağla; görsellerde son gösterim + saklama süresi, artık
  geçmeyenler ve kota temizliği yerel sürümle aynı kuralları izlesin.

## 7.1 CORS: veri ve görsel isteklerini SUNUCUDAN geçir

Tarayıcı **farklı kaynaktaki her isteği** CORS'a tabi tutar — yalnız görselleri değil `match.json`,
`lastupdate.json`, ayar belgeleri gibi **veri dosyalarını da**. Kiosk sayfası `127.0.0.1:<port>`'tan
CDN'e gider; bucket CORS'unda bu origin yoksa `fetch` reddedilir ve ekran "dosya okunamadı" der —
Python tarafı aynı dosyayı sorunsuz okuduğu için "sunucu bozuk" sanılır. Teşhis:
`curl -D - -H "Origin: http://127.0.0.1:<port>" <veri-adresi>` çıktısında
`access-control-allow-origin` başlığının **olmaması**.

* **Tek noktadan aynı-kaynak yedeği (asıl çözüm).** Uzak okumanın yapıldığı TEK fonksiyonda hata
  olursa aynı yolu yerel sunucu tabanıyla tekrar dene; yerel süreç veriyi zaten TLS + izin listesiyle
  çekip diske yazıyor, tarayıcı aynı kaynaktan okur. Böylece tarayıcı CORS'a hiç bağımlı kalmaz.
  Yedeği tek tek çağrılara değil ortak okuyucuya koy, yoksa bir sonraki dosya türü yine kırılır.
* **CORS'u yine de düzgün yapılandır:** iki kural — cihazlar için `GET/HEAD` **her origin (`*`)**, panel
  için `PUT` yalnız panel origin'leri. Kuralı yayın betiğine göm (`s3api put-bucket-cors` her yayında);
  yalnız dokümana yazmak yetmez. Doğrulama: aynı `curl -H Origin` → `access-control-allow-origin: *`.

* Tarayıcı **farklı alan adındaki görseli `fetch` EDEMEZ** (karşı taraf `Access-Control-Allow-Origin`
  göndermiyorsa "Failed to fetch"). Yerel sürümde bu kısıt yoktur → port **sessizce görsiz** kalır ve
  "siyah ekran" şikâyeti gelir (yayın görünümünde görsel yoksa arka plan siyahtır). Teşhis üçlüsü:
  konsolda CORS satırı + siyah ekran + yerel sürümün sorunsuz çalışması.
* **İzin listesi veri içindir, içerik görselleri için değildir.** Yayın görselleri panelde serbestçe
  adreslenir (başka bir alan adı, müşterinin kendi sunucusu); cihazın `host_allowlist`'i ise veri
  kaynağı için dar tutulur. Köprü sıkı politikayı görsellere de uygularsa görsel 403 alır, yayın
  görünümü **siyah** kalır ve (parite kuralı gereği görselsiz yayın atlanıyorsa) moddan çıkar —
  "yayın ekranı açılmıyor" şikâyeti budur. Kural: **veri dosyaları sıkı listede kalsın; görseller
  için ayrı politika** — yalnız `https`, port denetimi, kullanıcı bilgisi reddi ve **herkese açık**
  host şartı; loopback/özel/link-local/ayrılmış/multicast IP'ler ile çözümlenemeyen adlar reddedilir
  (SSRF). İzin listesine host eklemek 600 cihazda sürdürülemez; istisnayı koda yaz, kullanıcıya
  "şu alan adını da ekle" dedirtme. Test: gerçek görsel indirme (bayt sayısı + içerik türü) **ve**
  `127.0.0.1`/`10.x`/`169.254.169.254` reddi.
* Çözüm: yerel sunucuya **görsel köprüsü** ucu ekle — `GET /gorsel?u=<yüzde-kodlu adres>`:
  önbellek → ağ → **güvenlik denetimi** (izin listesi, yalnız HTTPS, bayt/piksel bütçesi, SVG/HTML
  reddi) → yerele önbelleğe yaz → gövdeyi ver. Tarayıcı yalnız aynı kaynaktan ister; CORS hiç devreye girmez.
* Kazanç zinciri: köprü **yerel sürümün önbelleğini** kullanır (aynı klasör), güvenlik kapıları aynen
  geçerli kalır, "ikinci gösterimde ağa çıkmama" garantisi korunur; koruma tarayıcıya taşınmadığı için
  **açık proxy'ye dönüşme riski yoktur**.
* Ayrımı **hata türüyle** yap, mesaj metniyle değil: içerik reddi için ayrı istisna sınıfı (403),
  adres politikası ihlali -şema/host/port/çözümlenemeyen ad- (403), ağ hatası (502). Mesajda anahtar
  kelime aramak yeni politika metinlerinde sessizce yanlış kod döndürür: "izin listesinde değil ama
  DNS'te yok" bir politika reddidir, ağ hatası değil — 502 dönerse kullanıcı sunucuyu açık proxy
  sanır, mevcut test de kırılır. Politika reddini fırlatan yerde kodu belirle, çağıranda tahmin etme.
* Tarayıcı önbelleği yolunu **yedek** olarak bırak (sunucusuz/statik deneme için): köprü başarısızsa
  tarayıcı önbelleği → doğrudan indirme sırasına düş.

## 9. Zamanlama ve geçişler: tarayıcı, yerel zamanlayıcıdan farklı davranır

Yerel sürümden "birebir" port edilen zamanlama, tarayıcıda **iki bağımsız sebepten** bozulur;
ikisi de "adım gecikiyor / yayın atlanıyor / geçiş yarı yolda takılıyor" olarak görünür.

* **Tek zamanlayıcı kuralı (en sık hata).** Yerel taraf genelde TEK bir döngü zamanlayıcısını her
  fazda yeniden kurar (nöbet adımı → `start(CYCLE)`, yayın adımı → `start(duration)`, çıkış →
  `start(CYCLE)`). Port ederken buna karşılık `setInterval(CYCLE)` + her yayın için ayrı
  `setTimeout(duration)` yazmak çift ilerleme üretir: yayın süresi dolmadan atlanır, iki zincir
  üst üste biner, mod değişiminde eski zincir yeni moda adım atlatır. Doğrusu: **tek, yeniden
  planlanabilir zamanlayıcı** (`donguPlanla(ms)`: önce `clearTimeout`, sonra `setTimeout`) ve her
  adımın SONUNDA bir sonraki adımı planlaması. Yayın modunda aktif liste de **mod boyunca
  sabitlenmeli** (Qt'in `active_yayinlar` parametresi gibi); her adımda yeniden hesaplamak
  süresi dolan yayını listeden düşürüp indeksleri kaydırır.
* **Chromium zamanlayıcı kısıtlaması.** Pencere arka planda/örtülü (occluded) sanılırsa tarayıcı
  arka plan zamanlayıcılarını **1 sn'ye** yavaşlatır ve `requestAnimationFrame`i **duraklatır**.
  Kiosk'ta bunlar hiç istenmez: `--disable-background-timer-throttling`,
  `--disable-renderer-backgrounding`, `--disable-backgrounding-occluded-windows` varsayılan olsun.
  Yine de tek savunma bu olmasın — rAF duraklatılsa bile durum hedefe ulaşmalı.
* **Geçiş tetikleyicisini rAF'a bağımlı kurmayın.** CSS geçişini başlatmak için "önce başlangıç
  değerleri, sonra bir sonraki karede hedef değerler" deseni standarttır; ama tek kare beklerseniz
  rAF duraklatıldığında hedef değerler HİÇ yazılmaz → panel kalıcı olarak yarı yolda takılır.
  Deseni iki kare + bir **yedek `setTimeout` (≈80 ms)** ile kurun; "uygulandı" bayrağıyla tek
  seferlik olsun. Animasyon kaybolabilir, ama ekran asla eski/yarım durumda kalmaz.
* **Periyodik yenileme MEVCUT öğeyi korusun.** Veri yeniden yüklendiğinde (saatlik tur) görünümü
  listenin başına çekmek, seçili öğe ile paneli desenkron eder (sol panelde 5. kayıt, ortada 1.).
  Yerel sürüm genelde "yenile → geçerli indeksi göster" yapar; port da öyle yapmalı.
* **Sabit adımlı animasyonu geçen süreye çevir.** Yerelde `QTimer` düzenlidir; tarayıcıda zamanlayıcı
  kayar. "Her tikte sabit px" yazıyı sıçratır → kaymayı `geçen süre / nominal adım` ile hesapla,
  tek adımda üst sınır koy (ör. 250 ms) ki uzun duraklamadan sonra yazı ekrandan atlamasın.
  Nominal hız (`px/adım`) korunur, yani davranış aynı kalır ama jitter gider.
* **Her tikte metin KURMA.** Kaydırılan liste metnini her tikte yeniden birleştirmek (60 kayıt ×
  30 ms) tarayıcıda gözle görülür takılmadır; metni moda girerken bir kez kur.
* Bu sınıf için test: sahte zamanlayıcılarla (`vi.useFakeTimers` + `advanceTimersByTimeAsync`)
  (1) uzun bir yayın, süresi dolmadan **atlanmamalı** (eski kurguda sabit döngü intervali atlatırdı),
  (2) nöbet adımı tam `CYCLE` ile dönmeli, (3) çıkışta durum temizlenmeli ve kadans nöbete dönmeli,
  (4) rAF hiç çağrılmasa bile geçiş hedefe ulaşmalı, (5) yenileme geçerli indeksi koruyor olmalı.

## 10. Canlı veri değişikliği: yoklama + anlık bildirim (tetikleyici)

Üç katman: (1) 10–30 sn'de bir YALNIZ üst veri yoklaması, (2) yerel sunucuda uzun yoklama ucu
`GET /degisiklik?imza=&sure=` (<1 sn), (3) panelin yazdığı `tetikle.json` ile kapsam hedefleme.
İki değişmez: **imza, damga dosyasının yanında veri dosyasının mtime+boyutunu da kapsar** (yoksa
damgayı tazelemeyen yazımlar görünmez) ve **bildirim yolunda önbellek atlanır** (damga eşit olsa da
taze gövde gösterilir).

Yazan tarafın ayağı ayrı bir kuraldır: **veri belgesini yazan her kayıt damgayı da tazelemeli**, yoksa
push ulaşmayan her cihaz önbellekten eski gövdeyi gösterir (belge yazıldı, tetik yazıldı, ekran
değişmedi). Kural ve mağaza düzeyi testi: `edge-device-remote-config` §5.2.

Tam sözleşme — uç biçimi, hızlı dönme koruması, zorla yenileme, CLI ve test listesi:
`references/live-data-trigger.md`.

## 8. Çalışma biçimi (bu kullanıcı)

* Teknik ayrıntı **sayıyla** istenir: test sayıları, HTTP kodları/boyutları, kazanç yüzdeleri.
* Uzun envanterleri (yerel UI ölçüleri, davranış tabloları, veri kuralları) **alt-ajanlara** okutup
  özet al; ama **iddia edilen dosya/satır/değeri kaynakta doğrula** — alt-ajan var olmayan dosya adı
  verebilir ve üzerine yüzlerce satır kod yazılır.
* Kullanıcı kendi makinesinde çalıştırır: hatayı **metin olarak** iste (rapor + konsol); tahmin
  turlarını bu kısa keser.
* **Erişimin olmayan uzak taraf için TAHMİN yürütme.** Bulut konsolu/anahtarı sende değilse
  (`sts get-caller-identity` → `NoCredentials`) nedeni söylemek yerine **salt-okuma bir teşhis aracı**
  yaz ve çıktısını iste: politika ifadeleri, origin yapılandırması, isteğin S3'te mi yoksa edge'de mi
  reddedildiği. Üst üste iki yanlış tahmin, bir tur beklemekten daha pahalıdır; kullanıcı bunu
  "araştırmanı doğru yapmıyor musun" diye geri söyler. Tahminini "deneyelim" diye değil, açıkça
  "doğrulanmadı" diye etiketle.
* Çok parçalı bir işin sonunda **ikinci bir kontrol turu** ister: her iddiayı taze bir
  komut/API okumasıyla yeniden doğrula (test sayısı, HTTP kodu, temiz klonda derleme, koruma
  ayarının API'den okunması) ve sonucu tablo hâlinde ver. "Yaptım" demek yetmez; kanıt
  komutun kendi çıktısıdır — özellikle doğrudan push/PR gibi dış sistemlere yazdıktan sonra
  geri okuyup doğrula.
* **Toplu düzenlemeleri "başarılı" sayma.** `python3 - <<'PY'` ile çok sayıda `str.replace`
  yaptığın oturumlarda: (1) her değişiklikten önce `assert eski in metin`, (2) yazdıktan sonra
  `search_files` ile yeni kalıbın dosyada gerçekten durduğunu doğrula. Eşleşmeyen bir replace
  sessizce hiçbir şey yapmaz, betik yine "ok" basar ve sen olmayan bir düzeltmeyi test etmiş olursun.
* **Kendi kabuğunu vuran komutlardan kaçın.** `pkill -f <desen>` desen kendi komut satırınla
  eşleşirse çalışan kabuğu öldürür (`exit -15`) ve "düzeltme uygulanmadı" sanıp aynı işi ikinci kez
  yaparsın — PID ile öldür ya da deseni `[c]hrome` yaz. Çok satırlı commit mesajını `-m "…"` içinde
  verme: ters tırnak/`$` kabuk tarafından yorumlanır, mesaj **sessizce kırpılır** ve `error:
  unexpected end of file` uyarısına rağmen commit yine geçer. Mesajı dosyaya yaz, `git commit -F <dosya>`.
* **Dal değiştirmek çalışma ağacındaki düzeltmeleri geri alır.** Düzeltmeler bir dalda commit'li
  değilse `git checkout main` onları siler; sonra "yama tutmadı" sanıp aynı işi ikinci kez yaparsın.
  Dal değiştirdikten sonra düzenlediğin dosyada `search_files` ile kalıbın durduğunu doğrula; iş
  bitince `git status` boş olsun.
* **Kurulum adımlarını TEK giriş betiğine topla — dağınık `pip install`/`apt`/panel adımları
  birikir ve kullanıcı "artık bunları da sen yaz" der.** Depo kökünde bir yürütücü betik
  (`./kur.sh kontrol|kiosk|panel|broker|hepsi`) olsun; betik her bileşenin bağımlılığını kendisi
  kursun (cihaz venv'i + `requirements.txt`, panelde `npm ci --include=dev`, sunucu tarafı ayrı),
  `kontrol` alt komutu **neyin eksik olduğunu tek ekranda** yazsın (python/venv/PyQt/paho, node,
  chromium, `web/dist`, `.env.local`) ve eksik olan `hepsi`de **atlanıp gerekçesiyle** raporlansın
  (sessizce devam etmesin). Yeni bir bağımlılık eklerken sor: "bunu betik mi kuruyor, yoksa
  kullanıcı elle mi?" — elle olan her adım geri gelir.
* **Cihazı kapsayıcıda çalıştırmak isteyen için iki mod, ikisi de betikte:** (1) ana makinenin X11
  soketini bağla (`/tmp/.X11-unix` + `DISPLAY`, gerçek ekran), (2) başsız sunucuda `Xvfb :99`
  (ekran yok, yalnız test/uzaktan). Kalıcı **önbellek dizinini birime (volume) bağla** — kapsayıcı
  silinince cihazın çevrimdışı önbelleği ve tarayıcı profili de silinirse "çevrimdışı çalışıyor"
  iddiası ölür. Yerel broker'ı yalnız **geliştirme profili** olarak koy (TLS/ACL yok), üretim
  broker'ını taklit ettiğini sanma.
* **Tekrarlanan insan adımını görünce otomasyon SEÇENEKLERİNİ sun, tek taraflı en gevşek olanı açma.**
  Kullanıcı "ben bu işi elle yapmak istemiyorum" dediğinde istenen şey otomatikleştirmek, ama hangi
  güvenlik kapısının kalkacağı onun kararı. Küçük bir tablo ver: seçenek · kalan insan işi · risk ·
  **gereken izin/ayar** (ör. merge için `Contents: RW`, ikinci onay için ikinci zorunlu kontrol) ve
  önerini işaretle. Seçimi aldıktan sonra kur, kill-switch'i (etiket / `cron pause` / geri dönüş
  komutu) birlikte ver. İzin genişleten ya da geri alınması zor (depo görünürlüğü gibi) adımları
  seçim gelmeden uygulama.
