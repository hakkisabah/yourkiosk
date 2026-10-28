# GitHub'a güvenli yükleme rehberi (yourkiosk)

Bu dosya, depoyu **sızıntı ve karışıklık olmadan** GitHub'a yüklemek için izlenecek sırayı verir.
Her adımın bir **doğrulama** komutu vardır; doğrulama geçmeden sonraki adıma geçmeyin.

> **Şu anki durum (bu dosya yazıldığında):** depo yerel olarak `git init -b main` ile hazırlandı,
> henüz **commit yok**. Yüklenecek dosya sayısı **169**; cihaz verisi, önbellek, günlük, sanal ortam ve
> `node_modules` **dışarıda**. Gerçek sır (AWS anahtarı, parola, token) **yok** — panelde yalnızca
> `.env.ornek` şablonu var, `.env.local` hiç oluşturulmadı.

---

## 0) Neden bu adımlar? (kısa)

* **Cihaz verisi depoya girmez.** `lastSystemData.json`, `match.json`, `lastupdate.json`,
  `makinebilgileri.json` cihaza özeldir (cihaz kimliği + yerel veri). `.gitignore` bunları dışlar;
  her kurulum kendi verisini `tools/fetch_nobet.py` ile üretir.
* **Üretilen/yerel şeyler depoya girmez:** `node_modules/`, `.venv/`, `dist/`, `onbellek/`,
  `.tarayici-profil/`, `*.log`, `__pycache__/`.
* **Sırlar asla girmez:** AWS anahtarları `.env.local`de tutulur (`.gitignore` dışlar), depoda
  yalnız `.env.ornek` bulunur.

---

## 1) Ön kontrol (commit'ten ÖNCE, 4 komut)

```bash
cd /home/hakki/evrim_otonom/yourkiosk

# 1.a) Neler yüklenecek? (169 civarı olmalı; node_modules/venv/dist GÖRÜNMEMELİ)
git add -A -n | wc -l
git add -A -n | grep -iE "node_modules|\.venv|/dist/|\.env$|credential|\.pem|makinebilgileri|lastSystemData" ; echo "(yukarısı boş olmalı)"

# 1.b) En büyük dosyalar (binlerce MB'lık dosya olmamalı; en büyüğü ~250 KB olan font)
git add -A -n | sed "s/^add '//;s/'$//" | xargs -r du -h | sort -h | tail -10

# 1.c) Sır taraması (kod içinde anahtar/parola kalıbı)
grep -rInE "AKIA[0-9A-Z]{16}|aws_secret_access_key\s*=\s*['\"]|BEGIN [A-Z ]*PRIVATE KEY|client_secret\s*=" \
  --include="*.py" --include="*.ts" --include="*.vue" --include="*.json" --include="*.md" . \
  | grep -v node_modules | grep -v "\.venv" ; echo "(boş olmalı)"
```

**İsteğe bağlı temizlik** (küçük dosya artıkları; depoyu etkilemez ama düzeni korur — bu komutu
aracın dışında, kendi terminalinizde çalıştırın):

```bash
find . -type d -name "__pycache__" -not -path "*/node_modules/*" -not -path "*/.venv/*" -prune -exec rm -rf {} +
find . -type d -name ".pytest_cache" -not -path "*/node_modules/*" -prune -exec rm -rf {} +
rm -f kiosk/kiosk.log kiosk/kiosk.log.*
```

---

## 2) Git kimliği ve GitHub erişimi (bir kez)

```bash
git config --global user.name  "Ad Soyad"
git config --global user.email "eposta@ornek.com"     # GitHub hesabındaki e-posta
git config --global init.defaultBranch main

# Erişim yolu A (önerilen): SSH anahtarı
ssh-keygen -t ed25519 -C "eposta@ornek.com"           # Enter, Enter, (parola önerilir)
cat ~/.ssh/id_ed25519.pub                             # çıktıyı GitHub → Settings → SSH keys'e ekle
ssh -T git@github.com                                 # "Hi <kullanıcı>!" görülmeli

# Erişim yolu B: HTTPS + Personal Access Token
# GitHub → Settings → Developer settings → Fine-grained token (Contents: Read/Write)
git config --global credential.helper store           # token'ı bir kez girin, sonra saklanır
```

> **Not:** Bu depoda `git config user.email` ayarlanmadan commit atılırsa GitHub katkı saymaz ve
> commit'ler "yer tutucu" kimlikle görünür. Önce 2. adımı tamamlayın.

---

## 3) İlk commit

```bash
cd /home/hakki/evrim_otonom/yourkiosk
git add -A
git status --short | wc -l          # 169 civarı: hepsi "A" (added) olmalı, "??" kalmamalı

git commit -m "yourkiosk: Qt kiosk ekranı, tarayıcı (Chromium) modu, S3 paneli ve tetikleyici altyapısı

- kiosk/: veri akışı, cihaz önbelleği, güvenlik denetimleri, tarayıcı başlatıcı + testler
- web/: Qt görünümünün birebir web portu (Vue 3 + Vite) + testler
- panel/: S3 tabanlı yönetim paneli (Cognito ya da Lambda modu) + testler
- Nöbet değişikliğini anında yansıtan tetikleyici (tetikle.json + /degisiklik uzun yoklama)"
```

Kontrol: `git log --stat --oneline -1 | tail -5` (dosya sayısı makul olmalı).

---

## 4) GitHub'da depoyu oluştur

**Yol A — Web (önerilen):** GitHub → **New repository**
* **Repository name:** `yourkiosk`
* **Description:** `Eczane nöbet ekranı: Qt kiosk + Chromium web arayüzü + S3 yönetim paneli`
* **Public/Private:** siz karar verin (önce **Private** ile başlayıp canlıya geçerken Public yapmak
  en güvenli yol).
* **Initialize this repository with:** ❗ **hiçbirini işaretlemeyin** (README/gitignore/license
  EKLEMEYİN — yerelde zaten hazır; aksi hâlde ilk push çakışır ve `--force` gerekir.)
* **Add license:** seçmeyin (depoda `LICENSE` = GPL-3.0 hazır).

**Yol B — `gh` CLI:**

```bash
gh auth login
gh repo create yourkiosk --private --source=. --remote=origin --push \
  --description "Eczane nöbet ekranı: Qt kiosk + Chromium web arayüzü + S3 yönetim paneli"
```

---

## 5) Push

```bash
git remote add origin git@github.com:<kullanıcı>/yourkiosk.git   # HTTPS için: https://github.com/...
git remote -v                                    # origin doğru mu?
git push -u origin main
git ls-remote --heads origin                     # main görünmeli (uzak gerçekten yazdı mı?)
```

---

## 6) Push sonrası doğrulama (GitHub arayüzünde)

* Depo ana sayfasında **169 dosya** ve README görünüyor mu?
* `LICENSE` → **GPL-3.0** olarak tanındı mı (sağ üstte "GPL-3.0 license" etiketi)?
* **Cihaz verisi yok mu?** `kiosk/lastSystemData.json`, `kiosk/makinebilgileri.json`
  **görünmemeli**. Görünüyorsa hemen 8. adıma (geçmişten temizleme) bakın.
* `.env.local` / `node_modules` / `dist` görünmemeli.

---

## 7) Depoyu koruma altına al (önerilen, 5 dakika)

| Ayar | Nerede | Neden |
|---|---|---|
| **Branch protection** (`main`: doğrudan push yasak, PR şart) | Settings → Branches | Yanlışlıkla bozuk kod canlıya gitmesin |
| **Secret scanning + Push protection** | Settings → Code security | Sır içeren push'u GitHub engeller |
| **Dependabot alerts** | Settings → Code security | Bağımlılık açıkları bildirilir |
| **Issues** açık, **Discussions** kapalı | Settings → General | Hata/istek takibi |
| **Konular (topics):** `kiosk`, `pyqt6`, `vue3`, `digital-signage`, `pharmacy` | Depo ana sayfası | Bulunabilirlik |

---

## 8) Yanlışlıkla sır/veri yüklendiyse

1. **Önce anahtarı/parolayı iptal edip yenileyin** (AWS: IAM kullanıcısı → yeni anahtar üret, eskisini sil).
   GitHub'a yazılmış bir sır, silinse bile **yayınlanmış** sayılır; döndürmek şart.
2. Geçmişten temizlemek için (geçmişi KALICI olarak değiştirir, dikkat):

```bash
pip install git-filter-repo
git filter-repo --path kiosk/lastSystemData.json --path kiosk/makinebilgileri.json --invert-paths
git push --force --all && git push --force --tags
# Ekip varsa: herkes yeniden klonlamalı (geçmiş kimlikleri değişti)
```

3. Bundan sonra `.gitignore` kuralını ekleyip (zaten ekli) tekrar sızdırmayın; GitHub'da
   **Push protection** açık kalsın.

---

## 9) Başka bir makinede klonlayıp çalıştırma

```bash
git clone git@github.com:<kullanıcı>/yourkiosk.git && cd yourkiosk

# Cihaz verisi depoda YOK → ilk çalıştırmada üretilir
cd kiosk
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python3 tools/fetch_nobet.py            # lastupdate + match + lastSystemData (+ makinebilgileri)
python3 main.py                         # Qt modu

# Tarayıcı modu
cd ../web && npm install --include=dev && npm run build
cd ../kiosk && python3 tools/tarayici_kiosk.py --tani

# Panel
cd ../panel && cp .env.ornek .env.local   # AWS değerleri; npm install --include=dev && npm run dev
```

> `npm install` bu ortamda `NODE_ENV=production` ise devDependencies'i atlar → **`--include=dev`** şart.

---

## 10) Canlıya geçiş yol haritası (git'ten sonraki aşama)

1. **S3 kova + yaşam döngüsü:** kiosk dosyaları (`kiosk/` ön eki), süresi geçen görseller için
   yaşam döngüsü kuralı, sürümleme (yanlış kayda geri dönüş).
2. **Panel `.env.local`:** `VITE_AWS_REGION`, `VITE_USER_POOL_ID`, `VITE_USER_POOL_CLIENT_ID`,
   `VITE_IDENTITY_POOL_ID`, `VITE_BUCKET` doldurulur (bkz. `panel/README.md`).
3. **Kimlik doğrulama kararı:** Cognito (yönetilen, ücretli) ya da Lambda + S3 imzalı cookie
   (Cognito'suz; `panel/lambda/`). Maliyet karşılaştırması: `panel/MAALIYET.md`.
4. **Cihazda servis:** `systemd` unit'i (`kiosk.service`) → açılışta otomatik başlatma, çökme
   durumunda yeniden başlatma; günlükler `journalctl`'e.
5. **Güncelleme akışı:** cihazda `git pull` + `cd web && npm run build` + servisi yeniden başlat
   (ileride imzalı komut kurgusuna bağlanacak — `SIRADAKI-ISLER.md` İş 3).
6. **Durum izleme:** cihazın son `lastupdate` damgası + son görsel gösterimi panelde görünsün.

---

## 11) Sık yapılan hatalar

| Hata | Sonucu | Doğrusu |
|---|---|---|
| GitHub'da repo oluştururken README/gitignore eklemek | ilk push reddedilir, `--force` gerekir | **Boş** repo oluştur (4. adım) |
| `.env.local` ya da `makinebilgileri.json` commit'lemek | cihaz kimliği/AWS bilgisi sızar | `.gitignore` dışlar; kontrol: 1.a ve 6. adım |
| `git add -f` ile ignore'u ezmek | yukarıdaki sızıntı | Gerekmiyorsa asla `-f` kullanmayın |
| `web/dist` veya `node_modules` commit'lemek | depo şişer, gürültü | `.gitignore` dışlar; klonlayan kendisi derler |
| Uzun ömürlü PAT'ı depoya/CI dosyasına yazmak | sızıntı | GitHub → **Secrets** (Actions) kullanın |
| `git commit` öncesi sır taramasını atlamak | geri dönüşü zor | 1.c komutunu her commit öncesi çalıştırın |
