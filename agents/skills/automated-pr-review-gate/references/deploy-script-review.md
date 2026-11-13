# Deploy / systemd / broker betiklerinde inceleme kontrol listesi

Kurulum ve bakım betikleri (`deploy/**`, `*.sh`, systemd birimleri, broker ACL, S3 yaşam döngüsü)
incelenirken bakılan sınıflar. Her madde, sahada gerçek bir arıza/risk ürettiği için listede.

## Kök olarak çalışan betikler

- **Kirli-ağaç kapısı `git status --porcelain` kullanmalı**, `git diff --quiet` DEĞİL: `diff` yalnız
  çalışma ağacı ↔ index farkına bakar, `git add` edilmiş değişiklik "temiz" görünür ve ayrıcalıklı
  kullanıcının yazabildiği içerik root olarak kurulur (yerel yetki yükseltmesi).
- **Öngörülebilir geçici yol yasak.** `> "$DOSYA.yeni"` + `install` yerine `mktemp` ile rastgele ad +
  atomik `mv`. Betiğin yazdığı dizin başka bir sürece aitse (broker, servis kullanıcısı) o süreç
  sembolik bağ koyup root'a keyfî dosya yazdırabilir.
- **Depoda mod 0755 olmalı**: belge `./betik.sh` diyorsa dosya yürütülebilir olmalı; `git ls-files -s`
  ile doğrula, `git update-index --chmod=+x` ile sabitle.
- **/tmp sabit yolu yok** (sembolik bağ yarışı), `mktemp`; birimde `PrivateTmp=` düşünülür.
- **Ajan süreci içinden gateway/servis yeniden başlatma çalışmaz** — betik komutu YAZDIRIR, çalıştırmaz.

## systemd birimleri

- Ayrıcalıklı adım ayrı birim olsun; depo işlemleri `runuser -u <kiosk>` ile ayrıcalıksız koşsun.
- `ProtectSystem`/`ProtectHome` ile yazma izni çelişmesin (`ReadWritePaths=` gerçekten gereken dizini
  açsın) — çelişki sessiz EROFS olarak görünür.
- Sağlık kapısı bağımlılık kapalıyken “atlandı” desin, sessizce “geçti” demesin.

## MQTT broker (mosquitto)

- `allow_anonymous false`, düz 1883 kapalı, TLS dinleyicilerde `password_file` + `acl_file`.
- **`max_connections -1` yazma**: kimlik doğrulaması bağlantı kabulünden SONRA yapılır; tek kaynak
  binlerce TLS el sıkışması açıp broker'ın FD'lerini tüketebilir. Filo büyüklüğü + pay kadar sayı ver.
- **Cihaz başına kimlik**: paylaşılan cihaz hesabı `durum/+` yazabildiği an cihaz taklidi mümkün.
  Her cihaz `cihaz-<id>` → yalnız `durum/<id>` yazar; izleme hesabı yalnız okur.
- **ACL testi kendi kendini çürütmesin**: retained test mesajını bırakırsan sonraki abone onu alıp
  çıkar ve gerçek sızıntı testi hiçbir şey ölçmez. Retained temizliği + konu ayrımı şart.
- Doğrulama betiği, ACL'in izin VERMEDİĞİ bir konuya yazmayı deniyorsa kontrol her koşuda ✗ verir —
  yanlış kırmızı, operatörü “güvenlik bozuk” sanısına sokar. Kimlik verilmediyse kontrol ATLANIR.

## S3 / bulut

- **Yaşam döngüsü kuralları etiketsiz silmez.** Önek + gün kuralı, adı içerik hash'i olan ve panel
  kaydında kalıcı duran nesneleri sessizce siler → sahada kırık görsel. Silme yalnız `silinebilir=true`
  ETİKETLİ nesnelere; etiket “hiçbir kayıt göstermiyor” kanıtından sonra konur.
- IAM politikalarında `Resource: "*"` yerine ARN; sayfa boyutu (`--max-items`/`--no-paginate`) ayarlı.
- Sır/ARN çalışma ağacına yazılmaz (`~/.local/state` ya da ortam).

## IAM: en-az-yetki politikası betikten TÜRETİLİR

- **Politika elle yazılmaz; `aws <servis> <komut>` çiftlerinden türetilir.** Bir harita tut
  (`sns create-topic → sns:CreateTopic`, `s3api copy-object → GetObject|GetObjectVersion|PutObject`,
  `cloudwatch put-metric-alarm → PutMetricAlarm`, …). Test betiklerin metnini bu çiftler için tarar ve
  politikanın karşılığı vermediğini KIRMIZI yapar — eksik izin sahada sessiz `AccessDenied` olur
  (alarm kurulmaz, yedek alınmaz, kimse fark etmez).
- **Ters yön de test edilir: politikadaki her eylem ya bir betikte çağrılıyor ya da GEREKÇELİ
  allow-list'te.** "Belki gerekir" gerekçe değildir; kullanılmayan izin yalnız saldırı yüzeyidir.
  Örnek sınıf: konu niteliklerini değiştiren bir izin sızarsa bildirim aboneleri saldırganın adresine
  çevrilir — betik o çağrıyı hiç yapmıyorsa izin de durmamalı. Aynı sınıftan `*Tagging` ve `ListBucket`
  gibi "bir ara lazım olur" izinlerini de aynı turda at.
- **Nesne kaynağı betiğin gerçekten yazdığı anahtarlarla sınırlanır.** Geri dönme/yedek anahtarı
  `…/kiosk/*` yazabiliyorsa panel paketini, yayın görsellerini ve ayar dosyalarını ezer; betik iki
  nesne yazıyorsa politika iki ARN taşır. `/*` wildcard'ının geri gelmesini testle yasakla.
- **Belgedeki "İçerik özeti" paragrafı politikayla BİREBİR aynı olmalı.** Test iki eylem kümesini
  karşılaştırsın (önek bazında), böylece belge ↔ politika kayması imkânsız olur. Bilerek VERİLMEYEN
  izin belgede gerekçesiyle anılabilir (`sns:Publish` — alarmlar SNS'e AWS servisi olarak yazar);
  istisna listesi hem eylemi hem gerekçe cümlesinin belgede durduğunu doğrulasın.
- **Anahtarın izni olmadığı için çalışmayan bir doğrulama komutu belgeye yazılır.** Abone listesi
  (`ListSubscriptionsByTopic`) kişisel e-postaları açar (PII) ve alarm kurma işi bunu gerektirmez;
  "bu tek kontrolü konsoldan yapın" satırı yoksa operatör izni bozuk sanıp anahtarı genişletir.
- Kova düzeyi izinleri de kullanımla eşle: `get-bucket-versioning` çağrılıyorsa `GetBucketVersioning`
  gerekir; `ListBucket` çağrılmıyorsa gereksizdir.

## Kuru koşu (`--kuru`) sözü TÜM yan etkileri kapsar

- **Kapı görünen komutun değil, yıkıcı bloğun tamamının etrafına konur.** Bir betikte
  `find <günlük-dizini> -mtime +14 -delete` bayrağın dışında kalırsa `--kuru` "hiçbir şey değişmez"
  derken geri alınamaz silme yapar; "her koşuda çalışan bir satır" kolayca gözden kaçar çünkü
  komutun kendisi zararsız görünür. `fetch`/tag güncellemesi, `chown`/`chmod`, geçici dizin açma da
  kapsam içindedir.
- **Test iki yönlü olmalı:** kuru koşu eski dosyayı SİLMEMELİ, gerçek koşu SİLMELİ. Yalnız ilkini
  yazarsan kapı işlevi tamamen kapatabilir ve kimse fark etmez.
- **Toplu işte yarım doğrulama = yalan mesaj.** Bazı öğeler doğrulamadan geçmiyor, geçenler
  yazılıyorsa "dosya DEĞİŞTİRİLMEDİ" cümlesi yalandır ve cihazlar yarım veri setiyle kalır. Tek karar
  ver: tek geçersiz öğe varsa HİÇBİRİ yazılmaz (atomik), çıkış ≠ 0, mesaj gerçeği söyler.
- **Mesaj bayrağı yansıtsın.** `--yaz` verildiği hâlde "KURU çalışma … (yazmak için --yaz)" basmak
  operatörü kendi komutundan şüpheye düşürür; yazılmadıysa NEDENİ yazılır ("geçersiz öğe var" /
  "değişecek öğe yok"). Ayrıca veri dosyası yazılmadığı hâlde çıktı ürünleri (dönüştürülmüş
  dosyalar) yazıldıysa "bunları yüklemeyin" uyarısı da basılır — yoksa operatör yarım kümeyi yayına alır.

## Derleme çıktısı ve sağlık kapısı (beyaz ekran sınıfı)

Gecede kendi kendine güncellenen cihazda en pahalı arıza, güncellemenin "başarılı" bitip cihazın
BOŞ EKRANLA açılmasıdır. İki ayrı kusur birlikte gelir:

- **Derleme doğrudan yayın dizinine yazılmaz.** `vite build` (ve `emptyOutDir: true` olan her
  üretici) hedef dizini önce boşaltır; tip hatası/bellek/kesinti derlemeyi yarıda bırakırsa `dist`
  yarımdır. Sıra: ayrı dizine derle (`npm run build -- --outDir dist.yeni`) → çıktı kapısı
  (`dist.yeni/index.html` var mı, yoksa `false` ile düş) → eski `dist`i `dist.eski`ye al → yeni
  dizini atomik `mv` ile yerleştir. Atomik takas artıklarını `.gitignore`a ekle (`web/dist.yeni/`,
  `web/dist.eski/`).
- **Geri dönüş, arızalı olabilecek derlemeye BAĞLI kalamaz.** `git reset --hard <önceki>` yalnız
  kaynağı döndürür — derleme çıktısı `.gitignore`'da olduğu için `dist` yerinde (yarım) kalır.
  `geri_don` bu yüzden yeniden derleme DENEMEZ; `dist.eski` > `dist` bayt bayt geri koyar, sonra
  servisi yeniden başlatır. Başarılı güncellemenin sonunda `dist.eski` silinir (disk şişmesin).
- **Sağlık kapısı "süreç ayakta" değil "PAKET SUNULUYOR" ölçer.** Halka: yerel sunucudan
  `/index.html` → 200 + `text/html` + uygulama işareti (ör. `yourkiosk`), `index.html`in işaret
  ettiği **ana JS varlığı** → 200 + `javascript` içerik tipi + makul boyut. Böylece "index var ama
  hash'li dosya yazılmamış", "varlık SPA fallback'iyle HTML dönüyor", "boş dosya" durumları da
  yakalanır; üçü de beyaz ekran üretir ama süreç ayaktadır.
- **Testi gerçek HTTP sunucusuna karşı yaz**, metin aramasına değil: geçici dizin + gerçek
  `ThreadingHTTPServer` (sınıf fabrikasıyla `directory=` ver; `functools.partial`ı sınıf tabanı
  olarak kullanmak `TypeError: the first argument must be callable` verir). Kapsanacak yollar:
  sağlam paket ✓, `index.html` yok, JS'e işaret yok, JS varlığı 404, boş varlık, yanlış içerik tipi
  (`guess_type` ezilerek), sunucu kapalı, yabancı uygulamanın `index.html`i. Her biri için çıkış
  kodunu da kilitle: sağlık kapısı bozuk pakette ≠ 0 dönmeli, yoksa güncelleme "başarılı" sayılır
  ve geri dönüş hiç tetiklenmez.

## Kanıt

- Her betik için `bash -n`; incelenen her davranış için **davranış testi** (metinde alt-dize aramak
  yeterli değil: `assert "diff --quiet" in metin` hatalı biçimi kilitler). Davranış testi geçici
  depoda gerçek `git` komutunu koşup çıktısını karşılaştırmalı.
