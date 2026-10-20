# Kurulum — i5 ve i3 makineleri (adım adım)

Her iki makinede de aynı adımlar; yalnız **prompt** ve **zamanlama** farklı. Komutlar Linux içindir
(Hermes kurulu olduğu için `python3` zaten var).

---

## 0. Ön koşullar (tek sefer)

```bash
python3 --version && git --version && curl --version | head -1
# eksikse:  sudo apt install -y python3 git curl
```

---

## 1. Token dosyası

Token'ı **o makinede** oluşturduğunuz fine-grained PAT ile doldurun (sohbete yazmayın):

```bash
mkdir -p ~/.config/hermes-secrets && chmod 700 ~/.config/hermes-secrets
read -rsp "token: " T && printf '%s\n' "$T" > ~/.config/hermes-secrets/github-yourkiosk.token && unset T
chmod 600 ~/.config/hermes-secrets/github-yourkiosk.token
```

Doğrulama (yalnız depo adı görünmeli, hata yoksa tamam):

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $(cat ~/.config/hermes-secrets/github-yourkiosk.token)" \
  https://api.github.com/repos/hakkisabah/yourkiosk
# 200 beklenir (404 → token depoya erişemiyor, 401 → token geçersiz)
```

---

## 2. Depo klonu

```bash
# HTTPS + token (deploy key yoksa en kolayı):
git clone https://x-access-token:$(cat ~/.config/hermes-secrets/github-yourkiosk.token)@github.com/hakkisabah/yourkiosk.git ~/yourkiosk
```

> Bu komut token'ı `.git/config` içine yazar (`origin` URL'i). İstemiyorsanız klondan sonra temizleyin:
> ```bash
> cd ~/yourkiosk && git remote set-url origin https://github.com/hakkisabah/yourkiosk.git
> git config --global credential.helper store   # ilk push'ta token'ı bir kez girer
> ```
> i5/i3 yalnız **okur** (fetch + API), bu yüzden token'sız `https` uzak adres de yeterlidir.

---

## 3. Betikleri dene (hiçbir şey yayınlamadan)

```bash
cd ~/yourkiosk
python3 otomasyon/betik/topla.py --cikti /tmp/paket.json        # bağlam paketi
python3 -c "import json;p=json.load(open('/tmp/paket.json'));print('değişiklik:',p['degisiklik'],'commit:',len(p['commitler']),'sır:',len(p['taramalar']['sirlar']))"

# karar dosyası örneği (elle) ve KURU yayın:
cat > /tmp/karar.json <<'JSON'
{"makine":"i5","sha":"'"$(git rev-parse HEAD)"'","pr":null,"karar":"onay","onem":"dusuk",
 "ozet":"Deneme kararı (kurulum testi).","bulgular":[],"not":"kurulum doğrulaması"}
JSON
python3 otomasyon/betik/yaz.py /tmp/karar.json --kuru
```

Son komut yalnız **gösterir** (istek atmaz). Çıktıda yorum metni + `guvenlik/inceleme=success`
görünüyorsa betikler hazır.

---

## 4. Hermes cron görevi

### Yol A — Dashboard (önerilen)

1. O makinede `hermes dashboard` açın.
2. **Cron** (ya da "Zamanlanmış görevler") → **Yeni görev**.
3. Ayarlar:

   | Alan | i5 | i3 |
   |---|---|---|
   | Zamanlama | `*/15 * * * *` (07:00–23:00) | `*/30 * * * *` |
   | İstem (prompt) | `otomasyon/prompt/i5-guvenlik.md` içeriği | `otomasyon/prompt/i3-karar.md` içeriği |
   | Çalışma dizini | `~/yourkiosk` | `~/yourkiosk` |

   İstem metninin **başına** şunu ekleyin:
   > "Çalışma dizini ~/yourkiosk. Önce `python3 otomasyon/betik/topla.py --cikti /tmp/paket.json`
   > çalıştır. `/tmp/paket.json` içinde `degisiklik: false` ise HİÇBİR ŞEY yapma, sessizce çık."

4. Kaydedip bir kez **"Şimdi çalıştır"** ile deneyin.

### Yol B — sistem cron + tek seferlik Hermes

```bash
# i5 için (crontab -e):
*/15 * * * * cd /home/USER/yourkiosk && hermes chat -q "$(cat otomasyon/prompt/i5-guvenlik.md)" >> /home/USER/.local/state/i5.log 2>&1
```
`USER` yerine o makinenin kullanıcı adı. i3 için `*/30` ve `i3-karar.md`.

---

## 5. Durum ve günlükler

```bash
~/.local/state/yourkiosk-otomasyon/son-sha   # en son incelenen commit
~/.local/state/i5.log                        # (Yol B kullanılıyorsa)
git -C ~/yourkiosk log --oneline -3          # ne çekilmiş
```

Yeniden incelemek için (son noktayı sıfırla):

```bash
rm ~/.local/state/yourkiosk-otomasyon/son-sha
python3 ~/yourkiosk/otomasyon/betik/topla.py --ilk --cikti /tmp/paket.json
```

---

## 6. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `token yok` | Dosya yolu/izni: `ls -l ~/.config/hermes-secrets/…` (`-rw-------`), ya da `GH_TOKEN` ortam değişkeni |
| `HTTP 404` (depo var) | Token'da depo seçili değil (*Only select repositories*) |
| `HTTP 403` + `Resource not accessible` | İzin eksik: *Commit statuses: RW* / *Pull requests: RW* |
| `degisiklik: false` hep | `git fetch` çalışmıyor olabilir: `git -C ~/yourkiosk fetch origin` çıktısına bakın |
| `git fetch: could not read Username` | Uzak adres HTTPS ve token yok → deploy key kurun ya da 2. adımdaki URL'i kullanın |
| Yorum iki kez | Aynı commit'e iki kez karar yazılmış; sorun değil, son yazan geçerli |
| Cron hiç koşmuyor | Dashboard'da görev "aktif" mi? Makine uyumuyor mu (`systemctl status`)? |

---

## 7. İlk gerçek koşu

1. Bu makinede (bende) bir düzeltme commit'i push edilir.
2. i5 ≤ 15 dk içinde PR yorumu + `guvenlik/inceleme` durumu yazar. PR yoksa yalnız commit durumu.
3. Görüldüğü an: branch protection'a `guvenlik/inceleme` **zorunlu kontrol** olarak eklenir.
4. i5 "sorun" derse i3 ≤ 30 dk içinde karar + plan yazar; ben düzeltirim.
