# Bulgu kapatma turu — geliştirici tarafı

Kapı (i5/i3) "sorun/düzeltme" yazdıktan sonra bulguları kapatma işi. Amaç: her bulgu **kodu
değişmiş + testi kilitlenmiş + aynı sınıf geri gelirse kırmızıya dönen** bir commit'le kapanır;
belge sayıları koddan yeniden türetilir.

## 1. Envanter (tek tur, ağ üzerinden)

`gh` her makinede kurulu olmayabilir — REST yeterli ve token zaten sır dizininde:

```bash
T=$(cat ~/.config/hermes-secrets/github-yourkiosk.token)
curl -s -H "Authorization: Bearer $T" \
  "https://api.github.com/repos/<sahip>/<depo>/pulls?state=open&per_page=50" \
  | python3 -c "import json,sys;[print(p['number'],p['head']['sha'][:8],p['head']['ref'],p['mergeable_state'],'|',p['title'][:60]) for p in json.load(sys.stdin)]"
```

Her PR için **son** inceleme yorumu geçerlidir (aynı head'e birkaç tur yazılmış olabilir):

```bash
curl -s -H "Authorization: Bearer $T" \
  "https://api.github.com/repos/<sahip>/<depo>/issues/<no>/comments?per_page=100" \
  | python3 -c "import json,sys;c=json.load(sys.stdin);print(c[-1]['created_at']);print(c[-1]['body'])"
```

Yorum gövdesi tablo hâlinde bulgu listesi + `dosya:satır` + `kabul` (kapanış ölçütü) taşır;
tablo kesilmişse (200 karakter sınırı) satır numarasını kaynak dosyada doğrula, yoruma güvenme.

### Bulgu bayat mı? (düzeltmeye başlamadan önce)

İnceleyen makine, üzerine konuştuğu ağacı yanlış hatırlayabilir ya da yorum eski head'e yazılmış
olabilir: bulgu "dosya satırında X yazıyor" der, güncel head'de X zaten düzeltilmiştir. Her bulgu
için iki komut — maliyeti bir çağrı, kazancı bir tur:

```bash
git -C /tmp/wtNN rev-parse --short HEAD        # incelenen sha ile aynı mı (yorumdaki machine-readable blok)
sed -n '<satır-8>,<satır+8>p' <dosya>          # iddia edilen satırın ÇEVRESİNİ oku
git grep -n '<bulgunun andığı sembol/metin>' -- <dizin>   # ağacın geri kalanında da var mı
```

Üç sonuç ve üç davranış:

- **İddia doğru** → normal düzeltme (§3–§5).
- **Zaten düzeltilmiş** → "düzeltme" yazma. Kapalı olduğunu commit mesajında ve kısa bir cevap
yorumunda **kanıtla** belirt (grep çıktısı: sembol bu head'de yok); sessizce atlarsan inceleyen makine
kapanışı görmez ve aynı madde döner.
- **Kısmen doğru** (ör. belgede bir yerde düzeltilmiş, başka yerde duruyor) → yalnız kalan yeri düzelt
ve tüm depoyu `git grep`le tara; aynı sınıf metin ikinci bir dosyada yaşıyor olabilir.

Bir turda aynı yorumun maddelerini birlikte kapat, ama **her madde kendi kanıtını** taşısın: tek
testin yeşil olması altı maddenin kapandığını göstermez.

## 2. Dal başına bir worktree

```bash
git worktree list                      # dal zaten bir worktree'de açık mı?
git worktree add /tmp/wt84 <dal>       # PR numarasıyla adlandır: /tmp/wtNN
cd /tmp/wt84 && git log --oneline -3
git log --oneline origin/<dal>..HEAD   # push EDİLMEMİŞ iş (önceki oturumdan kalmış olabilir)
git log --oneline HEAD..origin/<dal>   # uzakta yeni commit var mı
```

Ayrışmış (`diverged`) dalda tüm dalı rebase etmek yabancı commit'leri geri getirir. Yalnız kendi
commit'ini taşı:

```bash
git diff --stat <eski-taban> origin/<dal>       # uzak taraf neyi değiştirmiş
git rebase --onto origin/<dal> <eski-taban> <commit>
git branch -f <dal> HEAD && git checkout -q <dal> && git push origin <dal>
```

Ana klonu kirli bırakma: temiz ağaç denetimi yapan betikler (`git status --porcelain`) ve aynı
depoda koşan başka işler buna bağlı.

İki tuzak burada bekler:

- **Dal ana klonda checkout'sa `git worktree add /tmp/wtNN <dal>` "already checked out" ile düşer.**
  Ana klonun HEAD'i o dalsa worktree'ye aynı dalı veremezsin. İki çıkış: `git worktree add --detach
  /tmp/wtNN origin/<dal>` (push `git push origin HEAD:<dal>`) ya da geçici dal
  (`git worktree add -b gecici/wtNN origin/<dal>`, push `git push origin gecici/wtNN:<dal>`) — geçici
  dal adı commit'in `git log`unda kalır, rapora yaz.
- **Worktree'de `.git` bir DİZİN değil, dosyadır.** `>/tmp/wtNN/.git/COMMIT_MSG` yazma girişimi
  "File exists"/"Is a directory" ile düşer. Commit mesajını `/tmp/commit-msg-<pr>.txt` gibi ağaç
  dışı bir yola yaz, `git commit -F` ile ver. Aynı sebeple yerel dışlama dosyası da
  `>> .git/info/exclude` ile yazılamaz (`Not a directory`); yolu git'ten sor:
  `EX=$(git rev-parse --git-path info/exclude); mkdir -p "$(dirname "$EX")"; printf '%s\n' kiosk/.venv
  kiosk/.qt-libs web/dist >> "$EX"`. Fixture sembolik bağlarını (`ln -sfn /ana/klon/…`) oraya yaz ki
  `git status --porcelain` temiz kalsın; bağı COMMIT ETME (dizin kuralını sonda `/` olmadan yaz, bkz.
  ana belgedeki ignore tuzağı).

## 2b. Kopya taşıyan (yığılmış) dal — kök neden ve onarım

Belirti: iki PR da `mergeable_state = behind`/`dirty` kalır, kapı her turda "dal güncellenmeli"
yazar, rebase denemeleri modify/delete ve içerik çakışmaları üretir. Neden: üst PR'ın dalı alt PR'ın
dalından açılmış → aynı dosyalar iki PR'da, iki farklı sürümle duruyor.

**Teşhis (iki komut):**

```bash
git diff --name-only origin/main...<dalA> | sort > /tmp/a.txt
git diff --name-only origin/main...<dalB> | sort > /tmp/b.txt
comm -12 /tmp/a.txt /tmp/b.txt          # yüksek kesişim (özellikle yeni dosyalar) = kopya şüphesi

# içerik gerçekten kopya mı? aynı yama = aynı patch-id
git patch-id --stable < <(git show <commitA>)
git patch-id --stable < <(git show <commitB>)
```

Patch-id'ler eşitse o commit'ler **aynı iştir**; üst dalda tekrar durmamalıdır.

**Onarım — katmanlı bırak, kopyayı at:**

```bash
git branch yedek/<dal>-$(date +%H%M)          # force push öncesi geri dönüş noktası
git diff --name-only origin/main...<dalB> | grep -v -F -f <(sort /tmp/a.txt) > /tmp/yalniz-b.txt

# taban = ALT PR'ın uzak head'i; üst dalın yalnız kendi dosyaları
cd /tmp/wtNN && git checkout -B <dalB> origin/<dalA>
git checkout <yedek> -- $(tr '\n' ' ' < /tmp/yalniz-b.txt)
git commit -F /tmp/commit-msg-<prB>.txt
git push --force-with-lease origin <dalB>
```

Base'i API'den çevir (aksi hâlde PR hâlâ main'e karşı hesaplanır ve kopya diff'te görünür):

```bash
curl -s -X PATCH -H "Authorization: Bearer $T" -H "Accept: application/vnd.github+json" \
  -d '{"base": "<dalA>"}' \
  https://api.github.com/repos/<sahip>/<depo>/pulls/<noB>
```

Doğrula: `mergeable_state` `clean`/`blocked` olmalı ve `changed_files` yalnız üst PR'ın kendi işine
düşmeli. Sıra artık **alt PR önce** birleşir; üst PR alt birleşince kendiliğinden main'e yaklaşır.

`git rebase --onto origin/<dalA> origin/main` denemesi cazip ama çoğu zaman çakışır: kopya
commit'leri `git rebase --skip` ile atlayabilirsin (patch-id eşitliği kanıt), fakat SONRAKİ commit'ler
kopyanın soktuğu kodu yamaladığı için çakışır. Dosya kümesinden yeniden kurmak deterministiktir —
çakışma çözümüyle uğraşmak yerine bu yolu seç.

Bu onarımı yaptığın turda testleri **taban = alt PR'ın head'i** iken koş; üst PR'ın testleri alt PR'ın
dosyalarına bağlıysa yalnız o tabanda yeşil olur.

## 2c. Yeni tabana oturtma — dosya KÜMESİ sessizce küçülebilir

Uzun ömürlü bir dalı yeni bir tabana (`origin/main`, ya da katmanlı düzende `origin/<alt-dal>`) oturtmak
`git rebase`/`git rebase --onto` ile "başarılı" biterken içerik kaybı üretebilir: **eski tabanda
 eklenmiş ama yeni tabanda hiç bulunmayan bir dosya**, onu ekleyen commit yeniden oynatılan aralıkta
olmadığı için ağaçtan düşer. Belirti yoktur — çıkış 0, çakışma yok, `git log` makul; yalnız push
edilen PR birim dosyalarını, araçları, belgeleri taşımıyordur. Testler de yeşil kalır, çünkü o
dosyalara bakan testler ağaçta yoktur: kaybı **yeşil takım** gizler.

**Kural: rebase bir araçtır, kanıt değildir. Dosya kümesini ölç.**

```bash
# 1) taşımadan önce eski ucun künyesini al
git ls-tree -r --name-only <eski-head> | sort > /tmp/eski.txt
# 2) rebase/--onto + çakışma çözümü
# 3) sonuç kümesini karşılaştır
git ls-tree -r --name-only HEAD | sort > /tmp/yeni.txt
comm -23 /tmp/eski.txt /tmp/yeni.txt     # yalnız ESKİDE olanlar = kayıp adayları
comm -12 /tmp/eski.txt /tmp/yeni.txt > /tmp/kesisen.txt   # iki tabanın da dokunduğu dosyalar
```

- **`comm -23` listesi boş değilse taşı, ama tek tek karar ver:** `git checkout <eski-head> -- <yol>`.
  **Yol listesini önce süz** — listedeki TEK bir geçersiz yol bütün checkout'u düşürür (`pathspec … did
  not match any file(s) known to git`, çıkış 1, hiçbir dosya taşınmaz); var olmayanları ayıkla, sonra
  taşı ve `git status --short` ile gerçekten taşındığını gör.
- **Kesişim (`comm -12`) dosyalarını körlemesine taşıma.** İki dal da aynı dosyaya dokunduysa (tipik:
  üretilmiş artefaktlar — `yerlesim.json`, `*.generated.json`, birim metni) hangi sürümün geçerli
  olduğunu **anlam** belirler, "eskisi daha çok şey içeriyor" belirlemez. Ölçüt: dosyayı üreten kodun
  kaynağı hangi tabanda güncelse o tabanın sürümü kalır; kalanı için farkı oku (`git diff <a> <b> -- <yol>`)
  ve raporda tek satır gerekçe yaz.
- **Yeni tabanda bilerek SİLİNMİŞ bir şeyi geri getirme.** Taşıdığın eski sürüm, yeni tabanda kapatılmış
  bir açığı geri açabilir: derleme zamanı sır değişkenini (paketlenen `VITE_*` parolası gibi) geri
  getiren ya da "parola derlemeye gömülmez" kuralını eski cümlesiyle ezen bir belge satırı tam olarak
  bu sınıftır. Karar kuralı: **güvenlik/davranış düzeltmesi taşınan sürümde değil, YENİ tabanda kalır**;
  taşıma yalnız o dosyanın yeni tabanda hiç ele almadığı kısımlarla sınırlanır.
- **Taşımanın sonunda iki ölçüm yap:** (a) `git diff --stat <eski-head> HEAD` — fark yalnız "kasten
  düşürülen" dosyalardan oluşmalı, listesini rapora yaz; (b) tam test takımı (worktree fixture'larıyla,
  §3) — collect sayısı tabanla karşılaştırıldığında kayıp test dosyası varsa hemen görünür.
- **Force-push sonrası hedef dalın PR head'ini API'den yeniden oku** (`head.sha`, `changed_files`,
  `mergeable_state`): `changed_files` beklediğinden küçükse dosya kümesi hâlâ eksiktir.

## 3. Worktree'de test koşumu

Worktree'ye **gitignore'lu** çalışma zamanı gelmez: sanal ortam, `node_modules`, derlenmiş `dist/`,
cihaz verisi. Ana klondakini ödünç ver, commit'e sokma:

```bash
# Qt/kiosk (pytest): venv ana klonda
KIOSK_PYTHON=/ana/klon/kiosk/.venv/bin/python ./tools/test.sh tests/<dosya> -q

# panel (vitest): node_modules ana klondan bağla, iş bitince SİL (git status'u kirletmesin)
cd panel && ln -s /ana/klon/panel/node_modules node_modules && npx vitest run && rm node_modules
npx vue-tsc --noEmit                 # çıkış kodu 0 mı, "npm notice" satırlarına aldanma

# otomasyon (unittest)
python3 -m unittest discover -s otomasyon/betik/testler -p "test_*.py"
```

`NODE_ENV=production` dışa aktarılmış kabuklarda `npm ci --include=dev` (yoksa vite/vitest kurulmaz).

**Eksik fixture'lar dalga dalga çıkar — ilk yeşil olmayan koşuda durma.** Suite bir dosya kümesi
yüzünden düşerken ilk düzelttiğin küme arkasındakini maskeler: önce onlarca `FileNotFoundError`
(`match.json`, `lastSystemData.json`, `makinebilgileri.json`, `ayarlar.json`), o küme tamamlanınca
kalan iki `FAILED` (`lastupdate.json`, testin kendi `FileNotFoundError` yolunu söylediği hâlde ikinci
dalgada çıkar). Döngü: koş → hatanın adını verdiği dosyayı ana klondan ödünç ver → tekrar koş →
kırmızı 0 olana kadar. "Fixture'ları koydum" demeden önce tam paketi bir kez daha koş; dalganın
ikincisini atlamak rapora yanlış "dal kendi işinden kırmızı" yazar.

**Ortam kırmızısını regresyondan ayır.** Worktree'de bir dosya grubu (derlenmiş arayüz, tasarım
varlıkları, cihaz verisi) eksikse o dosyaya bakan testler `FileNotFoundError`/`AssertionError` ile
düşer ve sayı gerçek regresyonu gömer. İki adım: (1) eksik olanı ana klondan **symlink/kopya** ile
ödünç ver (ör. `ln -sfn /ana/klon/web/dist web/dist`), (2) kalan kırmızıları kendi düzeltmeyi
stash'leyip tekrar koşarak **taban commit sayısıyla** karşılaştır. Sayı tabanda da aynıysa ortam
gürültüsüdür; rapora "tabanda N, düzeltmeyle N — regresyon yok" yaz, "testler kırmızı" diye
bırakma. Aynı karşılaştırmayı incelediğin PR'ın ilk turunda da yap: kaç hatanın o dalın kendi işi
olduğunu ancak böyle bilirsin.

### Tam küme farkı — sayı eşitliği regresyonu gizler

Düzeltmesiz aynayı ayrı dizine çıkar, iki ağaca AYNI fixture'ları koy, kırmızı listelerini sırala,
KÜME olarak karşılaştır:

```bash
mkdir -p /tmp/wtNN-temel && git -C /tmp/wtNN archive HEAD | tar -x -C /tmp/wtNN-temel
# her iki ağaca da venv/dist/test verisi fixture'larını koy (ana klondan ödünç)
for d in temel duzelti; do
  ( cd /tmp/wtNN-$d && <test komutu> 2>&1 | grep -E "^(FAILED|ERROR)" | sort > /tmp/$d.txt )
done
diff /tmp/temel.txt /tmp/duzelti.txt && echo "regresyon yok — kırmızı kümeleri aynı"
```

- **Sayı eşitliği yetmez:** tabanda kırmızı olan bir test düzelmeyle yeşile dönerken başka biri
  kırmızıya dönebilir, toplam aynı kalır ve rapor "tabanda N, düzeltmeyle N" diyerek regresyonu
  gizler. Karşılaştırma satır satır küme üzerinden yapılır; fark varsa hangi testin eklendiğini yaz.
- **Fixture'ı "çalışan makinenin canlı ayarı"ndan değil, suite'in istediği en az kümeden kopyala.**
  Kullanıcının canlı ayar dosyasını (`ayarlar.json` gibi) kopyalamak testin ölçtüğü VARSAYILANLARI
  değiştirir: kırmızıların bir kısmı ortam değil anlam kaymasıdır ve senin düzeltmenle ilgisi yoktur.
  Önce dosya olmadan koş; gerekiyorsa depodaki örneği (`.ornek.json`) kullan. Veri/üretim
  fixture'larını kopyalarken alt dizinde iç içe kopya (`dist/dist`) oluşmadığını `ls` ile doğrula.

## 4. Mutasyon kanıtı (test gerçekten yakalıyor mu)

Düzeltmeyi geçici olarak geri al, ilgili testi koş, KIRMIZI olduğunu gör, geri koy, YEŞİL olduğunu gör:

```python
import pathlib, subprocess
yol = pathlib.Path("deploy/mosquitto/kur.sh"); orj = yol.read_text(encoding="utf-8")
yol.write_text(orj.replace("<düzeltilmiş satır>", "<eski hatalı satır>"), encoding="utf-8")
r = subprocess.run(["<python>", "-m", "pytest", "tests/test_x.py", "-q"], capture_output=True, text=True)
print("MUTASYON:", r.stdout.strip().splitlines()[-1])       # FAILED beklenir
yol.write_text(orj, encoding="utf-8")                        # HER ZAMAN geri yaz
print("GERİ ALINDI:", subprocess.run([...], capture_output=True, text=True).stdout.strip().splitlines()[-1])
```

Bunu commit mesajına yaz ("mutasyon: X geri alınınca test kırmızı, geri alınınca yeşil") — inceleyen
makine kanıt ister, "testler geçti" tek başına yetmez.

**Mutasyon yedeğini dosya ADIYLA değil tam yoluyla sakla.** Aynı ada sahip iki dosya (ör.
`deploy/cloudwatch/iam-politikasi.json` ve `deploy/yedek/iam-politikasi.json`)
`cp "$f" /tmp/mut-$(basename "$f").bak` ile TEK yedeğe çakışır; geri yükleme sırasında biri
ötekinin içeriğiyle ezilir ve mutasyon testleri yeşil olsa bile "düzelttim" dediğin dosya sessizce
yanlış içerik taşır. Yedek adına tam yolu (eğik çizgileri `_` yap) ya da sıra numarası koy, geri
yüklemeden sonra `git diff --stat` + `git diff` ile YALNIZ amaçlanan değişikliklerin kaldığını gör;
şüphe varsa dosyayı `git checkout -- <yol>` ile tabandan geri alıp düzeltmeyi yeniden uygula ve
testi bir kez daha koş.

### Hızlı yol: düzeltmeyi stash'le (yeni test dosyası henüz commit edilmemişken)

Dosyayı elle eski hâline yazıp geri koymak yerine düzeltmeyi geçici kaldır — aynı kanıt, daha az
yazma hatası riski:

```bash
cd /tmp/wtNN
git stash push -- docs/BELGE.md kiosk/config.py     # YALNIZ izlenen dosyaları AÇIKÇA listele
(cd kiosk && KIOSK_PYTHON=/ana/klon/kiosk/.venv/bin/python ./tools/test.sh tests/test_yeni.py -q)
# beklenen: FAILED → test iddiayı gerçekten yakalıyor
git stash pop && git status --short                  # pop gerçekten döndü mü
git diff --stat                                      # düzeltme geri geldi mi
```

- Yeni test dosyası **untracked**sa yol verilmiş `git stash push` onu kapsamaz — istenen budur: test
ağaçta kalır, düzeltme kalkar. `-u` verirsen test de kaybolur ve "kırmızı" boş bir koşuya dönüşür.
- Yol listesi vermeden `git stash push` tüm çalışma ağacını alır; aynı worktree'de başka PR'ın işi
varsa onu da kaldırır → dosyaları tek tek yaz.
- `stash pop` çakışabilir: çakışırsa temizle, düzeltmeyi yeniden uygula, testi tekrar koş (yeşil).
- Yeni testi yazarken ilk koşuyu **taban commit'te** yap (düzeltme yokken kırmızı). Testi önce yeşil
görmek, kanıtı tersine çevirir: "yakalıyor mu" sorusu cevapsız kalır.

## 5. Commit ve push

- Commit mesajı: numaralı bulgu listesi + her biri için **mekanizma** (neden böyle bozuluyordu) +
  doğrulama sayıları (kaç test yeşil, hangi mutasyon kırmızı).
- Dal `origin/main` üzerine rebase edilmiş olsun; `git push --force-with-lease origin <dal>`.
- Push sonrası head sha değişir → kapı kuralı gereği PR kendiliğinden yeniden kuyruğa girer; elle
tetikleme yok. `/tmp/ILERLEME.md`'ye "PR, yeni head, ne yapıldı" satırını yaz.

## 6. Belge sayıları koddan türetilir

Bulgu "belge bayat sayı yazıyor" ise doğru sayıyı **koddan/ölçümden** yeniden hesapla (istek/tur,
varsayılan süre, ayar adı → hangi sabiti yazıyor). Kopyala-yapıştır düzeltme (eski sayıyı yeni
sayıyla değiştirmek) ikinci turda yine bayatlar: önce etkin davranışı oku, sonra tabloyu yeniden
kur, sonra metin tarama testinin kapsamını (hangi dizinler, hangi uzantılar) gerçekten genişlet.

**Sayıyı testte KODDAN hesapla, belgeden kopyalama.** Elle yazılmış bir süre/maliyet tablosu, değer
bir daha değiştiğinde yine yalan söyler; tabloyu kilitleyen test "belgede `120 sn` yazıyor mu" diye
dize aramak yerine sabiti kaynaktan okuyup beklenen metni üretsin:

```python
# modülü IMPORT ETME (Qt/ağ yan etkisi olabilir): sabiti dosyadan oku
kaynak = (KIOSK / "config.py").read_text(encoding="utf-8")
m = re.search(r"^DAMGA_KONTROL_MS_PUSH\s*=\s*(\d+)\s*\*\s*1000\s*$", kaynak, re.MULTILINE)
sn = int(m.group(1))
assert f"**{sn} sn**" in belge
assert f"{600 * 86400 * 30.44 / sn / 1e6:.2f}".replace(".", ",") + " M" in belge   # istek/ay satırı
```

Yanına kötü-fikir kilidi ekle: "eski değer `X` yalnız 'elle ayarlanırsa' bağlamında geçebilir, 'bağlı
varsayılan' diyemez" gibi bir kuralı ayrı test et. Böylece belge düzeltmesi de testle korunur, sadece
cümle değişmez. Ayar ADI iddiasını da aynı yolla kilitle: belgedeki `ayarlar.json → ANAHTAR` ve
`grup.anahtar` metinleri `config.py`deki tanımlar ve ayar tablosuyla karşılaştırılsın — olmayan bir
anahtar adı (kaldırılmış bir ayar) okuyucuyu sahada boş yere uğraştırır.

### Sabit test SAYISI belgeye hiç yazılmaz

"319 test", "kiosk 370+ / web 111 test", "(21 test)" gibi ifadeler ilk test eklendiğinde yalan olur ve
inceleyen makine her turda aynı bulguyu yeniden yazar ("bildirdim ama değişmedi" algısının kaynağı).
Belgeye **komutu** yaz, sayıyı çıktıdan oku: `cd kiosk && bash tools/test.sh`. Kuralı makineye bağla —
izlenen `.md` dosyalarında kalıbı reddet ve kalıbın kendisini de ayrı testle doğrula (kör kural, kural
değildir):

```python
KALIP = re.compile(r"\b\d{2,4}\+?\s*test\b", re.IGNORECASE)   # yakalamalı: "319 test", "111 test", "(21 test)"
```

Tarama kümesini `rglob("*")` ile değil `git ls-files` ile kur: `.gitignore` kendiliğinden uygulanır,
cihaz verisi/derleme çıktısı/karantina dizinleri taranmaz ve "belge ↔ kod" iddiasının konusu olan
kümeyle birebir örtüşür. Boş `git` çıktısında (arşiv/tarball) testi SKIP et, sessizce tüm ağacı tarama.

## 7. Tur bitmez: her yeni head yeni bir inceleme açar

Push'tan sonra iş "geliştiricide" biter, kapıda bitmez. Yeni head, inceleyen makinede yeni bir tur
başlatır ve o tur ÇOĞU ZAMAN yeni bulgu yazar — önceki bulguların kapanmış olması bunu engellemez.
Bu bir başarısızlık değil, normal seyir; ama "kapattım" demeden önce son kararı TEKRAR oku.

- Push'tan sonra `commits/<sha>/status` + `issues/<no>/comments` son kaydını yeniden çek. Yeni head'de
  status yoksa iş kuyruktadır; "bitti" diye raporlama, "inceleme bekliyor" yaz.
- **Önem düzeyi düşüyorsa (orta → düşük → bilgi) tur yaklaşıyor demektir.** Karar metni yine `sorun`
  olabilir; bunu düzeltmenin başarısızlığı sayıp aynı yeri yeniden yazma. Kalan maddeler çoğunlukla
  belge doğruluğu / ifade hassasiyeti olur — düzelt, yeni bir mimari arayışına girme.
- Önceki turun bulgularını kapattığını **yorumla değil testle** göster: her düzeltmenin kendi
  mutasyon kanıtı (§4) olsun. İnceleyen makine "testler geçti" ifadesini kanıt saymaz.

## 8. Paralel dağıtım — ve çocuk raporunu doğrula

Birden çok PR'ın bulguları birbirinden bağımsızsa (farklı worktree, farklı dosya kümeleri), her PR'ı
ayrı bir alt ajana vermek tek oturumda sırayla uğraşmaktan hızlıdır. Görev metnine şunlar MUTLAKA
girer, yoksa çocuk yanlış ağaçta çalışır:

- worktree yolu + dal adı, ve "ana çalışma ağacında commit YAPMA";
- o repoda testin nasıl koşulduğu (hangi python/venv, hangi dizin, ortam yüzünden kırmızı kalan
  bilinen test sınıfı) — çocuk bunu tahmin etmeye çalışırsa turu test kurulumuyla harcar;
- bulgu listesinin dosyaya yazılmış hâli (`/tmp/yargi/prNN.md`), çünkü çocuk senin bağlamını görmez;
- "her düzeltmenin testi kırmızıya döndüğünü göster" + commit/push komutu.

**Çocuk raporu kanıt değildir.** "Push ettim, 97 test OK" bir iddiadır. Ana ajan olarak doğrula:

```bash
git -C /tmp/wtNN log --oneline -1 && git rev-parse HEAD          # yerel head
git ls-remote origin refs/heads/<dal>                             # uzak head AYNI mı
python3 -m unittest discover -s otomasyon/betik/testler 2>&1 | tail -3   # sayıyı kendin gör
git -C /tmp/wtNN diff --name-only HEAD~1 HEAD                     # dokunduğu dosyalar beklenen mi
```

Sonra raporun en riskli tek iddiasını dosyada da doğrula (`git grep <sembol>` → beklenen sonuç BOŞ
olmalı, ör. kaldırıldığı söylenen derleme-zamanı sır değişkeni; `grep -n verify-tag` → kapı gerçekten
var mı). Çocuk "düzelttim" derken dosya gerçekten değişmemiş olabilir; bu kontrol bir çağrı sürer.

## 9. Üretici–tüketici sözleşmesi: tek örnek tablosu, iki dil

Sınıf: **aynı kimliği/anahtarı bir taraf ÜRETİYOR, başka bir taraf ARIYOR** ve iki taraf farklı
normalleştiriyor. Tipik: yayıncı konuyu üretirken ASCII dışı karakterleri `-` yapıp kırpıyor, panel
ise veri dosyasındaki HAM değerle haritaya bakıyor. Belirti yoktur — veri akar, istisna çıkmaz, testler
yeşildir; yalnız öğe arayüzde sonsuza kadar "bilinmiyor"/boş görünür.

**Teşhis — iki tarafı yan yana koy:**

```bash
git grep -n "def .*kimligi\|def .*_anahtar" -- '*push*' '*konu*'      # üretici
rg -n "get\(|find\(" <tüketici-kaynağı>                            # arama yerleri
rg -n 'replace\(/\[\^' <tüketici-kaynağı>                           # tüketicide kural VAR MI
```

Tüketicide kural hiç yoksa (ya da karakter kümesi/sınır farklıysa) bulgu gerçektir. Aynı sınıf
"gösterim adı" ile "kimlik" karıştığında da çıkar: görünen etiket normalleştirilmiş, eşleştirme ham.

**Onarım — kuralı kopyalama, tek VERİ dosyasından doğrula:**

```jsonc
// panel/src/domain/<alan>.ornekler.json — TEK sözleşme
{ "kural": "ASCII dışı/joker → '-', baş/son '-' kırpılır, en çok 40",
  "ornekler": [ {"ham": "İZMİR 01", "beklenen": "ZM-R-01"},
                {"ham": "kiosk.local 1", "beklenen": "kiosk-local-1"},   // '.' farkını yakalar
                {"ham": "<40 karakter>", "beklenen": "<40 karakter>"},   // tam sınır
                {"ham": "<41 karakter>", "beklenen": "<40 karakter>"} ] }  // sınır+1
```

```python
# kiosk/tests/test_<alan>_parite.py — ÜRETİCİ tarafı
ORNEKLER = KOK / "panel" / "src" / "domain" / "<alan>.ornekler.json"

def _ornekler():
    if not ORNEKLER.exists():          # yalnız kiosk ağacı kopyalanmış ortam
        pytest.skip(f"ortak tablo yok: {ORNEKLER}")
    return json.loads(ORNEKLER.read_text(encoding="utf-8"))["ornekler"]

def test_yayinci_ortak_tabloyla_ayni_sonucu_uretir():
    hatalar = [f"{o['ham']!r}: {push.durum_kimligi(o['ham'])!r} ≠ {o['beklenen']!r}"
               for o in _ornekler()
               if o["beklenen"] and push.durum_kimligi(o["ham"]) != o["beklenen"]]
    assert not hatalar, "normalizasyon sözleşmesi kaydı:\n" + "\n".join(hatalar)
```

Tüketici tarafında aynı dosya `import ... from './<alan>.ornekler.json'` ile okunur ve
`expect(hatalar).toEqual([])` yazılır — kural iki yerde yaşar ama ORTAK VERİ tek yerde durur, böylece
bir tarafı değiştiren diğerini de değiştirmek zorunda kalır.

**Kural üç yerde daha gerekir:**

1. **Arama yapan her yer.** Özet sayacı, satır etiketi, liste tekilleştirme ayrı ayrı ham değerle
   arıyorsa düzeltmeyi birine uygulamak arızayı yarı yarıya yaşatır. Kaynak taramasıyla yasakla:
   `assertNotIn("harita.get(cihaz)", metin)` + `assertIn("harita.get(norm(cihaz))", metin)`.
2. **Kaynak nöbeti.** Tüketici işlevi silinirse ya da kural/limit değişirse parite testi kırmızı olsun:
   `assertIn("export function <ad>", kaynak)`, `assertIn("[^A-Za-z0-9_-]", kaynak)`,
   `assertIn("AZAMI = 40", kaynak)`. Yoksa "iki test var" iddiası dosya silinince sessizce boşa düşer.
3. **Boş değer davranışı ayrı karardır.** Üretici boş kimlikte `"bilinmeyen"`e düşerken (konu boş
   kalmasın) tüketici `""` dönebilir (farklı cihazlar tek ad altında toplanmasın). Tabloda boş girdiyi
   İKİ tarafın kendi sözleşmesiyle ayrı assert et, "birebir aynı" diye zorlamayın.

**Mutasyon kanıtı — ve tablonun ayırt ediciliği:** dört mutasyon ayrı ayrı kırmızı olmalı:
(a) tüketici ham değerle arıyor, (b) üreticinin sınırı 40→64, (c) tüketicide karakter kümesi genişledi
(`.` serbest), (d) belge/sayı iddiası bozuldu. (c) yeşil kalıyorsa tablo eksiktir: kural farkını
gösteren bir girdi (nokta içeren ad, tam sınır uzunluğu) ekleyip tekrar koş. Beklenen değerleri elle
hesaplama — bir kez kuralın kendisinden üret, dosyaya yaz.

## 10. Test yalıtımı — üretim kökü, import yan etkisi, sıraya bağlı kırmızı

Bu sınıfın ortak özelliği: hata **yeşil takımın altında** saklanır ve sahada veri kaybı ya da
"düzeltmem mi bozuk?" belirsizliği üretir. İkisi de kabaca aynı turda ortaya çıkar.

### 10a. Test üretim köküne yazmaz

Belirti: bir test sahte fixture'ı uygulamanın GERÇEK çalışma-ânı yoluna yazar (cihaz kimliği, ayar,
veri dosyası) ve sonunda siler. Temiz klonda o dosya hiç yoktur → test "dosya yok" durumunu ölçer ve
yeşil kalır; gerçek cihazda cihazın kimliği ezilir ve silinir (geri dönüşü yok). İnceleyen makine
bunu "veri kaybı, A bölgesi, orta/yüksek" diye yazar.

```python
def test_yasak_ad_sunulmaz(sunucu, monkeypatch, tmp_path):
    sahte_kok = tmp_path / "kok"; sahte_kok.mkdir()
    sahte = sahte_kok / "makinebilgileri.json"
    sahte.write_text('{"clientID": "SIZAN"}', encoding="utf-8")
    monkeypatch.setattr(modul, "KOK", sahte_kok)      # üretim kökü SALT-OKUR kalır
    ...
```

İki katmanlı kilit (biri diğerinin kaçağını kapatır):

```python
# (a) kaynak taraması — üretim kökünden türetilen değişkene yazma yasak
kok_bag = re.compile(r"(\w+)\s*=\s*[^\n#]*modul\.KOK\b[^\n]*(?:makinebilgileri\.json|MAKINE_DOSYASI)")
# (b) conftest.py — oturum kapsamlı bekçi
@pytest.fixture(scope="session", autouse=True)
def uretim_dosyasi_dokunulmaz():
    yol = SALT_OKUR_YOL
    def durum(): return (yol.is_file(), hashlib.sha256(yol.read_bytes()).hexdigest() if yol.is_file() else "")
    once = durum(); yield
    assert once == durum(), f"test turu üretim dosyasını değiştirdi: {yol}"
```

Tarama desenini **yalnız o dosya adına** daralt: tüm test ağacında "kök altına yazma" diye genel bir
yasak, meşru geçici dosyaları (günlük, sayaç) da yakalar ve yanlış kırmızı üretir. Mutasyon kanıtı:
eski satırı geri koy → tarama testi kırmızı; bekçiyi tek başına dene (dosya varsa sha256 değişimi).

### 10b. Import yan etkisi → sıraya bağlı kırmızı

Belirti: test dosyası tek başına yeşil, tam pakette kırmızı; kırmızılar hep "varsayılan config"
bekleyen testler; hata kendi düzeltmenle ilgisiz dosyalarda. Neden: `tools/*.py` modül düzeyinde
`ayarlar.uygula()` (ya da `config.X = …`) çağırıyor; o aracı import eden test modülü, süitin geri
kalanı için global config'i kalıcı değiştiriyor.

```bash
# teşhis: kirlenen global'i her testten sonra yazdır (700 testi elle bölmek gerekmez)
cat > /tmp/bekci.py <<'EOF'
import config
def pytest_runtest_teardown(item, nextitem):
    if config.KAYNAK != "dosya":
        print(f"KIRLENME: {item.nodeid} sonrası KAYNAK={config.KAYNAK}", flush=True)
EOF
PYTHONPATH=/tmp <python> -m pytest -q -p bekci 2>&1 | grep -m5 KIRLENME
```

Onarım: yapan çağrıyı `main()` içine al (`def ayarlari_uygula(): ayarlar.uygula()`), modül düzeyinde
yan etki bırakma. Kilidi alt süreçle kur — aynı süreçte import etmek kirliliği ölçmez:

```python
betik = ("import sys, json; sys.path.insert(0,'.')\nimport config\nonce=[config.KAYNAK, config.DOSYA_ADRESI]\n"
         "import importlib.util\nspec=importlib.util.spec_from_file_location('t','tools/arac.py')\n"
         "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
         "print(json.dumps([once,[config.KAYNAK, config.DOSYA_ADRESI]]))")
cikti = subprocess.run([sys.executable, "-c", betik], cwd=KOK, capture_output=True, text=True)
once, sonra = json.loads(cikti.stdout.strip().splitlines()[-1])
assert once == sonra, f"araç import'u config'i değiştirdi: {once} → {sonra}"
```

Ayrıca kaynak nöbeti: modül düzeyinde çıplak `ayarlar.uygula()` kalırsa test kırmızı olsun (kaynak
taraması), yoksa bir sonraki düzenleme yan etkiyi geri getirir. Aynı sınıfın kardeşi: ağaçta cihazın
kendi `ayarlar.json`u dururken varsayılan bekleyen testler de kırmızıdır — ölçümü dosyayı geçici
kaldırarak tekrarla ve sonucu **temiz ağaçtan** raporla.
