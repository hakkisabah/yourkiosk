#!/usr/bin/env python3
"""ORTAM DENETİMİ — i5 / i3 ajan makineleri (ve kiosk cihazı) için ön kontrol.

Amaç: "kurulumun neresinde takıldım?" sorusunu tek komutla yanıtlamak. Her satır ✓/✗ ve
**çözüm** içerir; hiçbir şeyi değiştirmez, yalnız okur (token'ı ekrana basmaz).

    python3 otomasyon/betik/ortam-kontrol.py --rol i5
    python3 otomasyon/betik/ortam-kontrol.py --rol i3 --depo ~/calisma_konumun/yourkiosk
    python3 otomasyon/betik/ortam-kontrol.py --rol kiosk      # cihaz tarafı (veri + tarayıcı)

Çıkış kodları: 0 hepsi tam · 2 eksik var (çözümler yazdırıldı) · 3 token yok/geçersiz
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

VARSAYILAN_TOKEN = Path.home() / ".config" / "hermes-secrets" / "github-yourkiosk.token"
VARSAYILAN_DEPO_ADI = "hakkisabah/yourkiosk"
DENETIM = {"satir": [], "sorun": 0}
#: `yaz.py` modülü (tembel yüklenir; testler bu özniteliği enjekte eder).
YAZ_MODUL = None


def satir(durum: bool, ad: str, ayrinti: str = "", cozum: str = "") -> None:
    isaret = "✓" if durum else "✗"
    DENETIM["satir"].append(f"{isaret} {ad:<22}: {ayrinti}" + (f"\n    → {cozum}" if (cozum and not durum) else ""))
    if not durum:
        DENETIM["sorun"] += 1


def bilgi(mesaj: str) -> None:
    DENETIM["satir"].append(f"  {mesaj}")


def _calistir(komut: list[str], zaman: int = 25) -> tuple[int, str]:
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=zaman, check=False)
        return sonuc.returncode, (sonuc.stdout or sonuc.stderr).strip()
    except (OSError, subprocess.SubprocessError) as hata:
        return 127, str(hata)


def yaz_modulu(depo: Path | None = None):
    """`yaz.py`'yi yol üzerinden yükler — kimlik kuralı TEK yerde kalsın diye.

    Neden: makine kimliği kuralı (root sahipli dosya, `i5`/`i3`, sanal FS yasağı) `yaz.py` içinde
    uygulanıyor. Denetim betiği kendi kopyasını yazsaydı iki kural zamanla ayrışır ve "denetim ✓
    dedi ama yazım reddedildi" durumu doğardı. Bu yüzden burada da AYNI fonksiyon çağrılır.
    """
    global YAZ_MODUL
    if YAZ_MODUL is not None:
        return YAZ_MODUL
    import importlib.util

    adaylar = []
    if depo:
        adaylar.append(depo / "otomasyon" / "betik" / "yaz.py")
    adaylar.append(Path(__file__).resolve().parent / "yaz.py")
    for aday in adaylar:
        if aday.is_file():
            spec = importlib.util.spec_from_file_location("yourkiosk_yaz", aday)
            if spec is None or spec.loader is None:
                continue
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)
            YAZ_MODUL = modul
            return modul
    return None


def makine_kimligi_kontrolu(rol: str, depo: Path | None) -> None:
    """Bu makinenin kimliği operatörün kurduğu dosyayla uyuşuyor mu? (yaz.py ile AYNI kural)"""
    modul = yaz_modulu(depo)
    if modul is None:
        satir(False, "makine kimliği", "yaz.py bulunamadı — kural denetlenemedi",
              "depo eksik/bozuk: git -C <depo> fetch origin && git -C <depo> reset --hard origin/main")
        return
    kimlik, neden = modul.makine_kimligi_denetle()
    mod = getattr(modul, "kimlik_modu", lambda: "?")()
    if not kimlik:
        satir(False, "makine kimliği", f"{neden} (kaynak: {mod})",
              f"SUDO GEREKMEYEN yol: bash otomasyon/betik/makine-kimligi-kur.sh --kaydet {rol} --yaz "
              f"→ commit + PR (eşleme git'te temiz olmalı). Alternatif: "
              f"sudo sh -c 'printf {rol} > {modul.KIMLIK_VARSAYILAN}' && "
              f"sudo chmod 0644 {modul.KIMLIK_VARSAYILAN}")
        return
    satir(kimlik == rol, "makine kimliği", f"{kimlik} (kaynak: {mod})",
          f"bu makine {kimlik!r} olarak kurulu ama --rol {rol!r} istendi; doğru makinede çalıştırın "
          f"ya da kimliği operatör değiştirsin")


def depo_bul(verilen: str) -> Path | None:
    adaylar = []
    if verilen:
        adaylar.append(Path(verilen).expanduser())
    if os.environ.get("KIOSK_YOLU"):
        adaylar.append(Path(os.environ["KIOSK_YOLU"]).expanduser())
    adaylar += [Path.home() / "calisma_konumun" / "yourkiosk", Path.home() / "projeler" / "yourkiosk", Path.home() / "yourkiosk", Path.cwd()]
    for aday in adaylar:
        if (aday / ".git").exists() or (aday / ".git").is_file():
            return aday
    return None


def api(yol: str, token: str) -> tuple[int, object]:
    istek = urllib.request.Request(
        f"https://api.github.com{yol}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "yourkiosk-ortam-kontrol",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(istek, timeout=20) as yanit:
            return yanit.status, json.loads(yanit.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as hata:
        return hata.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError) as hata:
        return 0, {"hata": str(hata)[:120]}


def main() -> int:
    ap = argparse.ArgumentParser(description="i5/i3/kiosk ortam denetimi")
    ap.add_argument("--rol", choices=["i5", "i3", "kiosk", "dev"], default="i5")
    ap.add_argument("--depo", default="", help="depo yolu (boşsa otomatik)")
    ap.add_argument("--depo-adresi", default=VARSAYILAN_DEPO_ADI)
    ap.add_argument("--token-dosya", default=str(VARSAYILAN_TOKEN))
    ap.add_argument("--yazma-dene", action="store_true",
                    help="Contents yazma iznini zararsız bir blob ile dene (merge için gerekir)")
    a = ap.parse_args()

    print(f"=== yourkiosk ortam denetimi · rol: {a.rol} ===")

    # 1) python / araçlar
    surum = sys.version_info
    satir(surum >= (3, 8), "python", f"{sys.version.split()[0]} ({sys.executable})",
          "Python 3.8+ gerekli: sudo apt install -y python3")
    satir(True, "  not", "3.10+ önerilir" if surum < (3, 10) else "sürüm yeterli")
    for arac in ("git", "curl"):
        yol = shutil.which(arac)
        satir(bool(yol), arac, yol or "bulunamadı", f"sudo apt install -y {arac}")

    # 2) depo
    depo = depo_bul(a.depo)
    satir(depo is not None, "depo", str(depo or "bulunamadı"),
          "git clone https://github.com/" + a.depo_adresi + ".git ~/calisma_konumun/yourkiosk")
    if depo:
        kod, uzak = _calistir(["git", "-C", str(depo), "remote", "get-url", "origin"])
        uzak_metin = uzak.splitlines()[0] if uzak else "yok"
        # GÜVENLİK: uzak adreste kimlik bilgisi varsa ASLA yazdırma (token terminale/sohbete sızmasın)
        gizli_var = bool(re.search(r"://[^/@]+@", uzak_metin))
        satir(kod == 0, "  uzak (origin)", re.sub(r"://[^/@]+@", "://***@", uzak_metin),
              f"git -C {depo} remote add origin https://github.com/{a.depo_adresi}.git")
        if gizli_var:
            satir(False, "  uzakta kimlik", "token URL içinde (git config'te düz metin!)",
                  f"git -C {depo} remote set-url origin https://github.com/{a.depo_adresi}.git  "
                  "(depo public → token'sız klon/fetch yeterli)")
        kod, _ = _calistir(["git", "-C", str(depo), "fetch", "origin", "--prune", "--quiet"], zaman=60)
        satir(kod == 0, "  git fetch", "başarılı" if kod == 0 else f"başarısız (kod {kod})",
              "ağ/HTTPS erişimi ya da uzak adresi kontrol edin")

    # 3) token
    token_yolu = Path(a.token_dosya).expanduser()
    if token_yolu.is_file():
        izin = oct(token_yolu.stat().st_mode & 0o777)
        satir(izin == "0o600", "token dosyası", f"{token_yolu} (izin {izin})", "chmod 600 " + str(token_yolu))
        token = token_yolu.read_text(encoding="utf-8").strip()
        kod, depo_veri = api(f"/repos/{a.depo_adresi}", token)
        satir(kod == 200, "token → depo", f"HTTP {kod}", "token'da depo seçili mi? (Only select repositories)")
        kod2, _ = api(f"/repos/{a.depo_adresi}/pulls?state=open&per_page=1", token)
        satir(kod2 == 200, "  PR okuma izni", f"HTTP {kod2}",
              "Fine-grained token → Pull requests: Read and write")
        kod3, _ = api(f"/repos/{a.depo_adresi}/labels", token)
        satir(kod3 == 200, "  etiket izni (Issues)", f"HTTP {kod3}",
              "Fine-grained token → Issues: Read and write")
        if a.yazma_dene:
            # Zararsız deneme: sahipsiz bir blob oluşturur (commit/tree YOK → depoda iz bırakmaz)
            govde = json.dumps({"content": "yourkiosk izin denemesi", "encoding": "utf-8"}).encode()
            istek = urllib.request.Request(
                f"https://api.github.com/repos/{a.depo_adresi}/git/blobs",
                data=govde,
                method="POST",
                headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                         "Content-Type": "application/json", "User-Agent": "yourkiosk-ortam-kontrol"},
            )
            try:
                with urllib.request.urlopen(istek, timeout=20) as yanit:
                    kod = yanit.status
            except urllib.error.HTTPError as hata:
                kod = hata.code
            except (urllib.error.URLError, TimeoutError):
                kod = 0
            satir(kod in (200, 201), "  yazma izni (Contents)", f"HTTP {kod}",
                  "Fine-grained token → Contents: Read and write (merge/otomatik birleştirme için ŞART)")
        else:
            bilgi("yazma izni: --yazma-dene ile sınanabilir (i3 için Contents: RW gerekir)")
    else:
        satir(False, "token dosyası", f"{token_yolu} yok",
              "KURULUM.md §1 (read -rsp ile dosyaya yazın; sohbete yazmayın)")

    # 4) sarmalayıcı betikler (yalnız ajan rolleri)
    if a.rol in ("i5", "i3"):
        klasor = Path.home() / ".hermes" / "scripts"
        gerekli = ["i5-imza.sh", "i3-durum.sh", "otomasyon-topla.sh"]
        for ad in gerekli:
            yol = klasor / ad
            var = yol.is_file() and os.access(yol, os.X_OK)
            satir(var, f"betik {ad}", str(yol) if yol.is_file() else "yok",
                  "bash otomasyon/kur.sh " + a.rol + "   (sarmalayıcıları kurar)")
            if var:
                # içindeki .py yolu gerçekten var mı? (bozuk/çiftlenmiş yol hatasını yakalar:
                # ör. /home/kullanici/home/kullanici/... → python3: can't open file)
                icerik = yol.read_text(encoding="utf-8", errors="ignore")
                bulunan = re.findall(r"([/][\w./-]+\.py)", icerik)
                if bulunan:
                    hedef = bulunan[0]
                    satir(os.path.exists(hedef), f"  {ad} yolu", hedef,
                          "yol YOK → sarmalayıcı bozuk: bash otomasyon/kur.sh " + a.rol)
        hermes = shutil.which("hermes")
        satir(bool(hermes), "hermes CLI", hermes or "PATH'te yok",
              "Hermes kurulumunu/PATH'i kontrol edin (cron görevi bununla kurulur)")
        # 26 Ekim i5 bulgusu: makine kimliği karar dosyasının kendi beyanıydı; i5 oturumu "i3"
        # yazıp iki kapıyı da geçirebiliyordu. Kimlik artık operatörün kurduğu ROOT sahipli
        # dosyadan okunur → kurulumda bu dosyanın varlığı da denetlenir (kural yaz.py'de).
        makine_kimligi_kontrolu(a.rol, depo)

    # 5) durum klasörü
    durum = Path.home() / ".local" / "state" / "yourkiosk-otomasyon"
    try:
        durum.mkdir(parents=True, exist_ok=True)
        yazilabilir = os.access(durum, os.W_OK)
    except OSError:
        yazilabilir = False
    satir(yazilabilir, "durum klasörü", str(durum), "chmod u+w " + str(durum))

    # 6) kiosk rolünde veri dosyaları
    if a.rol == "kiosk" and depo:
        kiosk = depo / "kiosk"
        eksik = [ad for ad in ("lastSystemData.json", "match.json", "lastupdate.json", "makinebilgileri.json")
                 if not (kiosk / ad).is_file()]
        satir(not eksik, "cihaz verisi", "tam" if not eksik else "eksik: " + ", ".join(eksik),
              "python3 tools/fetch_nobet.py --cihaz-id <clientID>   (kiosk/ içinden)")
        satir((kiosk / "web" / "dist" / "index.html").is_file() or (depo / "web" / "dist" / "index.html").is_file(),
              "web derlemesi", "var" if (depo / "web" / "dist" / "index.html").is_file() else "yok",
              "cd web && npm install --include=dev && npm run build")

    print("\n".join(DENETIM["satir"]))
    print()
    if DENETIM["sorun"] == 0:
        print("SONUÇ: hazır ✓ — sıradaki adım: KURULUM.md §4 (cron görevi)")
        return 0
    print(f"SONUÇ: {DENETIM['sorun']} eksik → yukarıdaki '→' satırlarını uygulayın.")
    if DENETIM["sorun"] and not token_yolu.is_file():
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
