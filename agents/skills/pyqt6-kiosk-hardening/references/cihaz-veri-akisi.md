# Cihaz odaklı kiosk veri akışı (filo / çok şubeli ekranlar)

Bir kiosk filosunda ekranın ne göstereceğini cihaz kendi kimliğinden öğrenir. Bu dosya o
akışın somut şekli, dosya rolleri ve kurallarıdır; kod yazmadan önce modele uyduğunu doğrula,
sonra testle kilitle.

## Dosya rolleri

| Dosya | Rol |
|---|---|
| `makinebilgileri.json` | Bu cihazın kimliği: `{"clientID": "<17 hane>"}` |
| `match.json` | İlçe/bölge → **makine id'leri**: `{ "<ilceId>": [ { "<bolgeId>": ["<makine id>", …] } ], "lastUpdate": … }` |
| `lastupdate.json` | Nöbet verisi en son ne zaman işlendi: `{"lastupdate": "<ts>"}` |
| `sablon.json` | Şablon (boş iskelet): kayıt alanları + `Yayinlar` + `lastUpdate` |
| `lastSystemData.json` | Şablonun doldurulmuş hâli = asıl veri: `Nobetler -> "T<YYYYMMDD>" -> { <ilceId>: [ { <bolgeId>: [kayıt] } ] }` |

Kayıt alanları: `ilce, ilceId, bolge, bolgeId, eczane, adres, tel, adres_tarifi, enlem, boylam,
start, end`. Tarihler şablonda **`gg/aa/yyyy ss:dd`** biçimindedir (ISO değil) — biçimi koru.

## Akış (uygulama tarafı)

1. **Saatte bir** `lastupdate.json` oku. Zaman damgası cihazdakiyle **aynıysa hiçbir şey yapma**
   (veriyi yeniden yükleme, ekranı yeniden kurma). Aynıysa-dönüşü loglayıp erken çık.
2. Değiştiyse `lastSystemData.json` + `match.json` oku (ağ hatasında son başarılı okumayı kullan).
3. `match.json` içinde kendi `clientID`'ni ara → `ilceId` + `bolgeId`. `lastUpdate` gibi alanları
   ilçe anahtarı sanma (atla).
4. **Nöbet günü:** `T<YYYYMMDD>` anahtarını 08:30 kuralıyla seç — 08:30'dan önce *dünün* anahtarı.
   İstenen anahtar yoksa sırayla: kaydın kendi penceresi (`start <= şimdi <= end`) → en yakın
   gelecek anahtar → en son anahtar; her düşüşü logla.
5. Kayıtları `ilceId` (ve `KAPSAM`'a göre `bolgeId`) ile filtrele ve ekran alanlarına çevir.

**Kapsam kararı kullanıcıya aittir:** `ilce` = cihazın ilçesindeki tüm bölgeler (aynı ilçe, farklı
bölge listesi genelde bunu gösterir), `bolge` = yalnızca kendi bölgesi. Seçimi config'de bayrak
yap, varsayılanı belirt, onay al.

## Veri üretme (kaynak siteden)

Kaynak adres tarih **yol parçaları** taşır: `<temel>/<baslangic>/<bitis>/`.

* İlk tarih = aralığın **başlangıcı** ve çekim günü olmalı (yarın çekersen yarının tarihi), aksi
  hâlde kaynak hata/boş döner.
* İkinci tarih = bitiş; aralık **en fazla 30 gün** (`EN_FAZLA_GUN`). Aşarsan araç hata ver, sessizce kırpma.
* Kaynak gövdesi düz bir sözlük olabilir (anahtar `""`, `"1"`, …); şablona çevirirken gün
  anahtarını `baslangic` alanından türet, alan adlarını (`baslangic/bitis` → `start/end`) eşle ve
  tarih biçimini şablona çevir.
* `ilceId` / `bolgeId` üretilecekse **kararlı** üret: isimden sha1 → `f"{int(ozet,16) % 10**17:017d}"`.
  Böylece her tazelemede aynı bölge aynı id'yi alır; okunabilir eşlemeyi (`ilce/bölge adı → id`)
  ayrı bir dosyaya yaz.
* `match.json` üretirken cihazın `clientID`'sini hedef bölgeye **ilk sıradan** yaz; diğer makineleri
  deterministik üret. Cihazın yerini `--cihaz-bolge` gibi bir parametreyle değiştirilebilir yap.
* `Yayinlar` blokları önümüzdeki 30 güne çoğaltılırken saat/süre korunur, ISO milisaniye hanesi
  (`timespec="milliseconds"`) korunur ve anahtarlar artan sayı olarak yeniden numaralanır.
* **Yayın penceresi ekranın açılıp açılmayacağını belirler.** Şablondaki dar pencereyi (ör. 17 dk)
  olduğu gibi çoğaltırsan ekran gün içinde neredeyse hiç yayın moduna girmez ve o görünüme ait
  öğeler (alt kuşak, kayan yazı) "kaybolmuş" sanılır. Üreteçte pencereyi parametre yap
  (`--yayin-araligi "HH:MM-HH:MM"`, `sablon` değeri şablon saatlerini korur), her gün için
  `start`/`end` = gün + pencere saatleri; yayın süresi (`duration`) ayrı kalır.

## Doğrulama listesi

* `lastupdate` aynı → `load_data()` veriyi **yeniden yüklemez** (mock'la sayaç tut, çağrı 0 olmalı).
* `lastupdate` farklı → bir kez yeniden yükler.
* Cihaz `match.json`'da yoksa veri yüklenmez/boş gösterilir ve log'a yazılır.
* Sınır saatleri: 08:29 → dünün anahtarı, 08:30 → bugün, 00:00 → değişmez.
* Başka ilçenin kayıtları listeye girmez; kapsam `bolge` iken tek kayıt döner.
* Kaynak gövdesinden şablona çevirme testi: gün/ilçe/bölge anahtarları, `start/end` biçimi,
  `ilceId`/`bolgeId` alanlarının kayıtta da bulunması.
* URL kuralı testleri: gün=1, gün=30 geçerli; gün=31 hata verir.
* Aktif yayın penceresi: veri içinde "şu an aktif kayıt var mı" testi bulunsun; pencere gün dışına
  yazıldığında yayın görünümü (ve ona bağlı öğeler) hiç açılmaz.
