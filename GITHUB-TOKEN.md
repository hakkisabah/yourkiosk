# GitHub token'ı: bana nasıl verirsiniz (veya kendiniz nasıl yaparsınız)

> ## ✅ DURUM (uygulandı — 21 Ekim 2026)
>
> Token `~/.config/hermes-secrets/github-yourkiosk.token` ile kurulum yapıldı:
>
> | Ayar | Sonuç |
> |---|---|
> | Depo görünürlüğü | **public** (aşağıdaki nota bakın) |
> | Branch protection (`main`) | ✅ PR zorunlu, force-push ❌, silme ❌, doğrusal geçmiş ✅, `enforce_admins` ✅ |
> | Zorunlu durum kontrolü | ⏳ **henüz eklenmedi** — i5 ilk kez çalıştıktan sonra eklenecek |
> | Secret scanning + push protection | ✅ açık (public depoda ücretsiz) |
> | Dependabot alerts + security updates | ✅ açık |
> | Etiketler | ✅ `guvenlik/onay`, `guvenlik/sorun`, `karar/verildi`, `duzeltme/gerekli` |
> | Yazma yolu | ✅ `yaz.py` gerçek durum yazdı (`guvenlik/inceleme=success`, HTTP 201, API'den doğrulandı) |
>
> **Neden public?** GitHub, **private** depolarda branch protection ve ruleset'leri ücretsiz hesapta
> **kapalı** tutuyor (`403: Upgrade to GitHub Pro or make this repository public`). Secret scanning +
> push protection de private depoda ücretli. Public yapınca üçü de ücretsiz açıldı. Proje zaten
> GPL-3.0 açık kaynak hedefiyle yazıldı ve depoda sır/cihaz verisi yok (tarandı: yalnız belge
> örnekleri). **Geri almak isterseniz:** Settings → General → Danger Zone → *Change visibility* →
> Private (o anda protection ve secret scanning kapanır).
>
> **Bilinmesi gereken:** commit yazarı e-postanız (`hakkihelyanwe@gmail.com`) public geçmişte görünür.
> İsterseniz geçmiş yeniden yazılabilir (`git filter-repo` + force-push) — bu tüm SHA'ları değiştirir,
> bilinçli karar gerektirir.


Branch protection ve iş akışı etiketleri **API** ister; deploy key yalnız git taşımasına yarar.
İki yol var — ikisi de geçerli, birincisi daha az tıklama.

---

## Yol A — Bana token verin (önerilen: 5 dakika)

### 1. Fine-grained token oluşturun

1. GitHub → sağ üst profil → **Settings**
2. Sol menü en altta → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. Doldurun:
   - **Token name:** `hermes-yourkiosk`
   - **Expiration:** 30 gün (iş bitince iptal edin; uzun süre gerekirse 90)
   - **Resource owner:** `hakkisabah`
   - **Repository access:** *Only select repositories* → **`hakkisabah/yourkiosk`**
   - **Repository permissions** (yalnız şunlar):
     | İzin | Seviye | Neden |
     |---|---|---|
     | **Administration** | Read and write | branch protection kuralları |
     | **Metadata** | Read (otomatik) | zorunlu temel izin |
     | **Contents** | Read and write | commit/PR karşılaştırma, etiket dosyaları |
     | **Pull requests** | Read and write | inceleme yorumu, onay/red |
     | **Issues** | Read and write | etiketler (PR'lar da issue'dur) |
     | **Commit statuses** | Read and write | `guvenlik/inceleme` kontrolü |
5. **Generate token** → `github_pat_...` ile başlayan değeri **kopyalayın** (bir daha gösterilmez).

> Not: *Actions* izni gerekmiyor. *Workflows* izni de gerekmiyor (depoda workflow yok).

### 2. Token'ı dosyaya koyun (sohbete YAZMAYIN)

Terminalde:

```bash
mkdir -p ~/.config/hermes-secrets && chmod 700 ~/.config/hermes-secrets
# panoya kopyaladığınız token'ı yapıştırın (ekranda görünmez):
read -rsp "token: " T && printf '%s\n' "$T" > ~/.config/hermes-secrets/github-yourkiosk.token && unset T
chmod 600 ~/.config/hermes-secrets/github-yourkiosk.token
ls -l ~/.config/hermes-secrets/github-yourkiosk.token   # -rw------- olmalı
```

### 3. Bana sadece yolu söyleyin

> "token hazır: `~/.config/hermes-secrets/github-yourkiosk.token`"

Ben şunu yaparım: token'ı **hiç ekrana basmadan** `curl -H "Authorization: Bearer $(cat …)"` ile
kullanır, önce `GET /repos/hakkisabah/yourkiosk` ile izni doğrular, sonra hazır betiği çalıştırırım:

```bash
python3 otomasyon/betik/koruma-kur.py --uygula
```

Betik şunları yapar (tek komut): `main` için branch protection (PR zorunlu, **zorunlu durum kontrolü
`guvenlik/inceleme`**, force-push ve silme kapalı, doğrusal geçmiş, `enforce_admins` açık),
4 etiket (`guvenlik/onay`, `guvenlik/sorun`, `karar/verildi`, `duzeltme/gerekli`), Dependabot
uyarıları ve sonunda **doğrulama** (`GET .../protection`).

> **Neden onay sayısı 0?** GitHub kendi PR'ını onaylamana izin vermez; tek kişilik depoda
> "1 onay zorunlu" kuralı PR'ları **hiçbir zaman** birleştirilemez yapar. Bu yüzden güvenlik kapısı
> **zorunlu durum kontrolü** ile kurulur: i5 `guvenlik/inceleme = success` yazmadan birleştirme
> yapılamaz. İkinci bir GitHub hesabını ortak yaparsanız `--onay 1` ile gerçek onay da eklenir.

Token'ı **depoya, commit'e, günlüğe yazmam**; iş bitince `shred -u` ile silmenizi öneririm.

> Güvenlik notu: bu token yalnız bu depoya erişir, süresi 30 gün. Bir sorun görürseniz GitHub →
> Settings → Developer settings → token → **Revoke** (anında etkisiz).

---

## Yol B — Kendiniz yapın (arayüzden, tıklama tıklama)

### Branch protection

> Not: **private** depoda bu ekran "Upgrade to GitHub Pro" der; public depoda açıktır.

1. `https://github.com/hakkisabah/yourkiosk` → **Settings** (depo sekmesi, profil değil)
2. Sol menü → **Branches** → *Branch protection rules* → **Add branch protection rule**
   (yeni arayüzde: **Add branch ruleset** → *New branch ruleset*; ikisi de olur)
3. **Branch name pattern:** `main`
4. İşaretleyin:
   - ☑ **Require a pull request before merging** → *Required approvals:* **0** (tek kişilik depo;
     GitHub kendi PR'ını onaylatmaz — kapıyı durum kontrolü kurar)
   - ☑ **Require status checks to pass before merging** → **`guvenlik/inceleme`** (i5 kurulduktan sonra)
   - ☑ **Require linear history** (merge commit'siz geçmiş — isteğe bağlı ama önerilir)
   - ☑ **Require conversation resolution before merging**
   - ☑ **Do not allow bypassing the above settings** (yönetici de kurala uysun)
   - ☐ Allow force pushes → **kapalı**
   - ☐ Allow deletions → **kapalı**
5. **Create** / **Save changes**

### Güvenlik özellikleri

1. **Settings** → **Code security** (eski adı *Security & analysis*)
2. ☑ **Dependabot alerts** — ücretsiz, bağımlılık açıkları için
3. ☑ **Dependabot security updates** — otomatik düzeltme PR'ı açar
4. **Secret scanning** / **Push protection**: **özel** depolarda GitHub'ın *Secret Protection* (ücretli)
   planını gerektirir. Ücretsiz alternatif: depodaki `.gitignore` + i5 makinesinin `gitleaks`/regex
   taraması (iş akışında var). Public yaparsanız bu iki özellik ücretsiz açılır.

---

## Sık karşılaşılan iki hata

| Hata | Neden |
|---|---|
| `403 Resource not accessible by personal access token` | Token'da **Administration: Read and write** yok ya da depo seçilmemiş |
| `404 Not Found` (depo var olduğu hâlde) | Token başka *resource owner* için üretilmiş ya da depo erişimi *Only select* listesinde değil |
