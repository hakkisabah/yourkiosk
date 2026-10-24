"""TARAYICI (Chromium) KIOSK MODU — PyQt6 arayüzüne alternatif gösterim.

Aynı veriyi, aynı kurallarla ve aynı görünümle gösteren HTML/JS arayüzü
(`WEB_KLASORU`, varsayılan `web/`) **yerel ve yalnızca-127.0.0.1** bir HTTP
sunucusundan sunulur ve Chromium kiosk modunda açılır.

Cihaza özgü tek bilgi URL'deki `clientID` parametresidir:

    http://127.0.0.1:8090/index.html?clientID=<cihaz>&veri=yerel

Sayfa geri kalan her şeyi kendi çeker (nöbet verisi, ayarlar, kapsam ayarları) ve
görselleri tarayıcının kalıcı profil önbelleğinde saklar (Qt tarafındaki
`onbellek/` klasörünün karşılığı).

Güvenlik (yerel sunucu):
  * yalnızca `WEB_SUNUCU_ADRESI` (varsayılan 127.0.0.1) üzerinde dinler,
  * `..`/sembolik bağ ile kök dışına çıkma reddedilir,
  * dizin listesi kapalı, yalnızca **beyaz listedeki** dosyalar sunulur,
  * `makinebilgileri.json` (cihaz kimliği) HİÇ sunulmaz — sayfa kimliği URL'den alır,
  * JSON yanıtları `no-store` (lastupdate her zaman taze okunsun), görseller
    tarayıcı önbelleğine bırakılır (`Cache-Control: max-age`).
"""

from __future__ import annotations

import http.server
import json
import logging
import re
import time
import os
import shlex
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlencode

import config
from core import tetik as tetik_modulu

log = logging.getLogger("kiosk.tarayici")

KOK = Path(__file__).resolve().parent.parent          # kiosk/ (çalışma zamanı dosyaları)
PROJE_KOK = KOK.parent                                 # proje kökü (web/ burada)

#: Yerel sunucudan sunulabilecek veri dosyaları (cihaz kimliği hariç — o URL'de gelir)
#: Cihaza özgü, depoya girmeyen veri dosyaları (temiz klonda BULUNMAZ)
CIHAZ_VERI_DOSYALARI = ("lastSystemData.json", "match.json", "lastupdate.json", "makinebilgileri.json")

SUNULAN_VERI_DOSYALARI = (
    "lastSystemData.json",
    "lastupdate.json",
    "match.json",
    "sablon.json",
    "ayarlar.json",
    "kapsam-ayarlari.json",
    "tetikle.json",
)

#: Proje kökünde OLUP arayüze ASLA verilmeyecek adlar (403 ile reddedilir)
YASAKLI_ADLAR = frozenset({"makinebilgileri.json", "kiosk.log", "ayarlar.json.ornek"})

#: Web arayüzünde sunulabilecek dosya uzantıları (beyaz liste)
IZINLI_UZANTILAR = {
    ".html", ".htm", ".js", ".mjs", ".css", ".map",
    ".json", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf", ".txt",
}


# ------------------------------------------------------------------ yollar
def web_kaynak_kok() -> Path:
    """Arayüzün KAYNAK klasörü (proje kökü altında, ör. <proje>/web)."""
    return PROJE_KOK / str(getattr(config, "WEB_KLASORU", "web"))


def derlenmis_kok() -> Path:
    """Derlenmiş arayüz kökü (`web/dist`)."""
    return web_kaynak_kok() / "dist"


def derlenmis_mi() -> bool:
    """Arayüz `npm run build` ile derlenmiş mi? (tarayıcı `.ts` çalıştıramaz!)"""
    return (derlenmis_kok() / "index.html").is_file()


def web_kok() -> Path:
    """SUNULACAK kök: derlenmiş sürüm varsa `web/dist`, yoksa kaynak klasör.

    Kaynak klasör doğrudan sunulamaz: `index.html` `/src/main.ts` ister ve tarayıcı
    TypeScript çalıştıramaz (bu, "beyaz ekran" olarak görünür). Derlenmemişse
    `baslat()` net bir hata verir.
    """
    return derlenmis_kok() if derlenmis_mi() else web_kaynak_kok()


def profil_kok() -> Path:
    return KOK / str(getattr(config, "TARAYICI_PROFIL_KLASORU", ".tarayici-profil"))


def sunucu_adresi() -> str:
    return str(getattr(config, "WEB_SUNUCU_ADRESI", "127.0.0.1"))


def sunucu_portu() -> int:
    return int(getattr(config, "WEB_SUNUCU_PORTU", 8090))


# ------------------------------------------------------------------ URL / komut
def url_olustur(client_id: str, veri_modu: str | None = None, port: int | None = None, adres: str | None = None) -> str:
    """Tarayıcıya verilecek adresi üretir (cihaz kimliği URL'de).

    `veri=yerel` → veri yerel sunucudan (dosya kaynağıyla aynı mantık),
    `veri=https` → veri `DOSYA_ADRESI`'nden (cihazın internet bağlantısı kullanılır).
    """
    mod = str(veri_modu or getattr(config, "WEB_VERI_MODU", "yerel")).lower()
    if mod not in ("yerel", "https"):
        mod = "yerel"
    parametreler = {"clientID": str(client_id or ""), "veri": mod}
    if mod == "https":
        # Sayfa `veri=https` gördüğünde veriyi `${taban}/${dosya}` adresinden çeker.
        # `taban` verilmezse sessizce YEREL dosyaya düşüyordu (https modu çalışmıyordu).
        taban = str(getattr(config, "DOSYA_ADRESI", "") or "").strip().rstrip("/")
        if taban:
            parametreler["taban"] = taban
    makine = adres or sunucu_adresi()
    kaport = sunucu_portu() if port is None else int(port)
    return f"http://{makine}:{kaport}/index.html?{urlencode(parametreler)}"


def komut_olustur(url: str, tarayici: str | None = None, tani: bool = False) -> list[str]:
    """Chromium kiosk komutunu üretir (test edilebilir: yalnızca liste döner).

    NOT: `--app=<url>` KULLANILMAZ; bazı Chromium sürümlerinde `--kiosk` ile birlikte
    siyah/boş pencereye yol açıyor. Kiosk modunda URL konumsal argümandır.

    `tani=True` → konsol hataları terminale düşer (`--enable-logging=stderr --v=1`).

    Varsayılan bayraklar kiosk cihazında **kararlılık** için seçildi: GPU hızlandırma ve
    GPU ile birleştirme kapalı (X11/EGL sorunlarında siyah ekranı önler), arka plan ağ
    trafiği (GCM/oturum açma/senkron) kapalı, `/dev/shm` küçük sistemlerde sorun çıkarmasın.

    ZAMANLAMA bayrakları (`--disable-background-timer-throttling`,
    `--disable-renderer-backgrounding`, `--disable-backgrounding-occluded-windows`):
    Chromium, pencere arka planda/örtülü sanılırsa `setInterval`i **1 sn'ye** yavaşlatır ve
    `requestAnimationFrame`i **duraklatır**. Kiosk arayüzü zamanlayıcılarla dönüyor
    (nöbet adımı, kuşak, saat, geçişler) — bu kısıtlama açık kalırsa adımlar gecikir,
    yayın atlanır, geçişler yarı yolda takılır. Kiosk cihazında kısıtlama hiç istenmez.

    İstenirse `ayarlar.json → calistirma.tarayici_ek_bayraklar` ile eklenip değiştirilebilir.
    """
    yol = str(tarayici or getattr(config, "TARAYICI_YOLU", "chromium"))
    ek = str(getattr(config, "TARAYICI_EK_BAYRAKLAR", "") or "")
    komut = [
        yol,
        "--kiosk",
        "--start-fullscreen",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--noerrdialogs",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-translate",
        "--disable-pinch",
        "--overscroll-history-navigation=0",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-features=Translate,MediaRouter,OptimizationHints",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--disable-domain-reliability",
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        # ZAMANLAMA: arka plan/örtülü pencerede zamanlayıcı kısıtlaması ve rAF duraklaması
        # kapatılır (yoksa adımlar gecikir, yayın atlanır, geçişler takılır)
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        f"--window-size={getattr(config, 'TARAYICI_PENCERE_BOYUTU', '1920,1080')}",
        "--window-position=0,0",
        f"--user-data-dir={profil_kok()}",
    ]
    if tani:
        # konsol iletileri ve ağ hataları stderr'e yazılır (kullanıcı terminalde görür)
        komut += ["--enable-logging=stderr", "--v=1"]
    if ek.strip():
        komut.extend(shlex.split(ek))
    komut.append(url)  # konumsal: --kiosk <adres>
    return komut


def tani_raporu(client_id: str, port: int | None = None) -> list[str]:
    """Ön kontrol raporu: arayüz dosyaları, veri, cihaz kimliği ve tarayıcı sürümü.

    Tarayıcı açılmadan önce "neyin eksik olduğunu" gösterir; `--tani` ile yazdırılır.
    """
    import json as _json
    import urllib.error
    import urllib.request

    satirlar: list[str] = []
    satirlar.append(f"arayüz kökü     : {web_kok()}")
    _pd = dist_durumu()
    if not _pd["var"]:
        satirlar.append("derlenmiş mi    : HAYIR → cd web && npm run build")
        satirlar.append("paket durumu    : ✗ YOK — tarayıcı modu eski/boş arayüzle çalışır")
    elif _pd["bayat"]:
        satirlar.append("derlenmiş mi    : EVET (ancak BAYAT)")
        satirlar.append(
            f"paket durumu    : ✗ BAYAT — web/{_pd['en_yeni_kaynak']} paketten yeni; "
            "ekran ESKİ kodu çalıştırır → ./kur.sh kiosk"
        )
    else:
        satirlar.append("derlenmiş mi    : EVET")
        satirlar.append("paket durumu    : ✓ GÜNCEL")
    # Hangi paketin çalıştığı görünsün: eski dist ile yeni kaynak karışmasın (beyaz ekran hataları)
    try:
        import json as _j

        paketler = sorted((web_kok() / "assets").glob("index-*.js"), key=lambda p: p.stat().st_mtime)
        if paketler:
            son = paketler[-1]
            satirlar.append(f"arayüz paketi   : {son.name} · {time.strftime('%Y-%m-%d %H:%M', time.localtime(son.stat().st_mtime))}")
        surum_yolu = web_kok() / "surum.json"
        if surum_yolu.is_file():
            s = _j.loads(surum_yolu.read_text(encoding="utf-8"))
            satirlar.append(f"paket sürümü    : git={s.get('git', '-')} · derleme={s.get('zaman', '-')}")
        # kaynak dist'ten yeni mi? (kur.sh artık kendisi derler; burada uyarı)
        kaynaklar = list((web_kok().parent / "src").rglob("*")) + [web_kok().parent / "index.html"]
        en_yeni = max((p.stat().st_mtime for p in kaynaklar if p.is_file()), default=0)
        if paketler and en_yeni > paketler[-1].stat().st_mtime + 1:
            satirlar.append("UYARI           : web/dist ESKİ (kaynak daha yeni) → ./kur.sh kiosk")
    except Exception:  # noqa: BLE001
        pass
    eksik_veri = [ad for ad in CIHAZ_VERI_DOSYALARI if not (KOK / ad).is_file()]
    if eksik_veri:
        satirlar.append(f"cihaz verisi    : EKSİK → {', '.join(eksik_veri)}")
        satirlar.append("                  bu dosyalar cihaza özgüdür (depoya girmez). Çözüm:")
        satirlar.append("                    python3 tools/fetch_nobet.py      # veriyi kaynaktan üret")
        satirlar.append("                    # ya da eski kurulumdan kopyala:")
        satirlar.append("                    cp /eski/kurulum/kiosk/{lastupdate,lastSystemData,match,makinebilgileri}.json kiosk/")
    else:
        satirlar.append("cihaz verisi    : TAM ✓")
    satirlar.append(f"cihaz kimliği   : {client_id or '(BOŞ — URL\'ye clientID yazılamaz!)'}")
    satirlar.append(f"profil klasörü  : {profil_kok()}")

    yol = tarayici_bul()
    if yol:
        try:
            surum = subprocess.run([yol, "--version"], capture_output=True, text=True, timeout=10)  # noqa: S603
            metin = (surum.stdout or surum.stderr).strip()
            satirlar.append(f"tarayıcı        : {metin} ({yol})")
            # Arayüz ES2020+ gerektirir; çok eski tarayıcı "boş ekran" verebilir
            eslesme = re.search(r"(\d+)\.\d+", metin)
            if eslesme and int(eslesme.group(1)) < 100:
                satirlar.append(
                    f"  !! tarayıcı sürümü eski ({eslesme.group(1)}) — arayüz için Chromium ≥ 100 önerilir"
                )
        except (OSError, subprocess.SubprocessError):
            satirlar.append(f"tarayıcı        : {yol} (sürüm okunamadı)")
    else:
        satirlar.append("tarayıcı        : BULUNAMADI (chromium kurun ya da calistirma.tarayici_yolu)")

    try:
        sunucu, gercek_port, _ = sunucu_baslat(sunucu_adresi(), 0 if port is None else int(port))
    except (FileNotFoundError, OSError) as hata:
        satirlar.append(f"sunucu          : BAŞLATILAMADI ({hata})")
        return satirlar

    def _cek(yol_: str) -> str:
        try:
            with urllib.request.urlopen(f"http://{sunucu_adresi()}:{gercek_port}{yol_}", timeout=5) as yanit:
                return f"{yanit.status} · {len(yanit.read())} bayt · {yanit.headers.get('Content-Type', '-')}"
        except urllib.error.HTTPError as hata:
            return f"{hata.code} (sunulmuyor)"
        except (urllib.error.URLError, OSError) as hata:
            return f"hata: {hata}"

    satirlar.append(f"geçici sunucu   : http://{sunucu_adresi()}:{gercek_port}")

    # MQTT push durumu (600+ cihaz ölçeğinde birincil tetikleme yolu)
    try:
        from core import push as push_modulu

        if push_modulu.acik():
            # Raporda GERÇEK durumu göster: kısa bir bağlantı denemesi yap (kiosk başlarken
            # nasıl davranacağını burada görürüz). İş parçacığı süreçle birlikte biter.
            push_modulu.baslat()
            for _ in range(12):
                if push_modulu.durum().get("bagli"):
                    break
                time.sleep(0.25)
        d = push_modulu.durum()
        if push_modulu.acik():
            durum = "bağlı ✓" if d.get("bagli") else f"BAĞLI DEĞİL ({d.get('hata') or 'bağlantı kurulamadı'})"
            satirlar.append(f"MQTT push       : açık · {push_modulu.broker()} · konu={push_modulu.konu()} · {durum}")
        else:
            satirlar.append("MQTT push       : kapalı (yoklama emniyet ağı kullanılıyor)")
    except Exception as hata:  # noqa: BLE001
        satirlar.append(f"MQTT push       : durum okunamadı ({hata})")
    for yol_ in ("/index.html", "/lastSystemData.json", "/lastupdate.json", "/match.json", "/bg_layout/box.png"):
        satirlar.append(f"  {yol_:<24}: {_cek(yol_)}")

    # cihaz kimliği match.json içinde var mı? (yoksa arayüz hata kartı gösterir)
    try:
        from core import veri_kaynagi

        match = veri_kaynagi.match_yukle()
        veri = veri_kaynagi.sistem_verisi_yukle()
        kimlik_var = bool(client_id) and client_id in _json.dumps(match or {})
        satirlar.append(f"match.json eşleşme: {'VAR ✓' if kimlik_var else 'YOK ✗ (clientID match.json içinde bulunamadı)'}")
        gun_sayisi = len((veri or {}).get("Nobetler", {})) if isinstance(veri, dict) else 0
        yayin_sayisi = len((veri or {}).get("Yayinlar", {})) if isinstance(veri, dict) else 0
        satirlar.append(f"veri içeriği    : {gun_sayisi} gün bloğu · {yayin_sayisi} yayın kaydı")
        # GÜNCELLEME ZİNCİRİ: panel → durum.json/lastupdate → cihaz. Uyuşmazlık burada görünür.
        try:
            from core import durum as _durum
            from core import onbellek as _onbellek

            belge = _durum.getir()
            durum_damga = _durum.damga(belge)
            ag_damga = veri_kaynagi.lastupdate_taze()
            kayitli = ""
            try:
                kayitli = str(_onbellek.veri_kayit("lastSystemData.json").get("lastupdate", "") or "")
            except Exception:  # noqa: BLE001
                kayitli = ""
            satirlar.append(f"damga (durum)   : {durum_damga or '(durum.json yok)'}")
            satirlar.append(f"damga (lastupd) : {ag_damga or '(okunamadı)'}")
            satirlar.append(f"damga (disk)    : {kayitli or '(yok)'}")
            if durum_damga and ag_damga and durum_damga != ag_damga:
                satirlar.append("UYARI           : durum.json ile lastupdate.json FARKLI → panel yarım yazmış olabilir")
            if ag_damga and kayitli and ag_damga != kayitli:
                satirlar.append("UYARI           : disk önbelleği eski → bir sonraki turda yenilenecek")
            tetik = _durum.tetik(belge) or {}
            if tetik:
                satirlar.append(f"tetikleyici     : {tetik.get('zaman','-')} · kapsam={tetik.get('ilceId') or 'tümü'}")
        except Exception as hata:  # noqa: BLE001
            satirlar.append(f"güncelleme     : okunamadı ({hata})")
    except Exception as hata:  # noqa: BLE001 - rapor her durumda yazılsın
        satirlar.append(f"veri kontrolü   : yapılamadı ({hata})")

    sunucu.shutdown()
    sunucu.server_close()
    return satirlar


# ------------------------------------------------------------------ görsel köprüsü
def _ag_ayarlari():
    """Görsel indirme politikası (Qt tarafındaki `network.AgAyarlari` ile aynı)."""
    from security.network import AgAyarlari

    return AgAyarlari(
        zaman_asimi_s=config.HTTP_TIMEOUT_S,
        en_buyuk_bayt=config.MAX_GORSEL_BAYT,
        izinli_hostlar=tuple(config.ALLOWED_HOSTS),
        kullanici_ajani="yourkiosk/1.0",
        izinli_portlar=tuple(getattr(config, "AG_IZINLI_PORTLAR", (443,))),
        yonlendirme_izinli=bool(getattr(config, "AG_YONLENDIRME_IZINLI", False)),
        en_buyuk_url=getattr(config, "MAX_URL_UZUNLUK", 2048),
    )


def _icerik_turu_tahmin(baytlar: bytes, icerik_turu: str = "") -> str:
    """Baytlardan içerik türü (önbellekten gelen görsellerde tür kayıtlı olmayabilir)."""
    from security.image_policy import bicim_tahmin

    tur = (icerik_turu or "").split(";")[0].strip().lower()
    if tur in ("image/png", "image/jpeg", "image/webp"):
        return tur
    esleme = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
    return esleme.get(bicim_tahmin(baytlar) or "", "application/octet-stream")


def tetik_oku() -> dict | None:
    """Panelin yazdığı tetikleyiciyi okur (tek kural: `core.tetik`)."""
    from core import tetik as tetik_modulu

    return tetik_modulu.oku()


def degisiklik_imzasi() -> str:
    """Nöbet değişikliği imzası: veri dosyalarının (mtime+boyut) + tetikleyicinin (mtime+zaman) özeti.

    Yalnızca KÜÇÜK üst veriler okunur; büyük veri dosyasının İÇERİĞİ okunmaz.

    NEDEN `lastSystemData.json` DA İMZADA: panel/araç veriyi değiştirdiğinde `lastupdate.json`
    damgası tazelenmezse (ya da damga aynı kalırsa) arayüz damgaya bağlı önbellekten **eski**
    gövdeyi servis etmeye devam ediyordu. Dosyanın mtime+boyutu imzaya girince her yerel
    değişiklik anında bildirilir; arayüz de bildirimde önbelleği atlayıp taze veriyi indirir.
    """
    parcalar: list[str] = []
    for ad in (
        str(getattr(config, "LASTUPDATE_DOSYASI", "lastupdate.json")),
        str(getattr(config, "TETIK_DOSYASI", "tetikle.json")),
        str(getattr(config, "SISTEM_VERISI_DOSYASI", "lastSystemData.json")),
    ):
        try:
            durum = (KOK / ad).stat()
            parcalar.append(f"{ad}:{durum.st_mtime_ns}:{durum.st_size}")
        except OSError:
            parcalar.append(f"{ad}:-")
    tetik = tetik_oku()
    if tetik:
        parcalar.append(f"tetik:{tetik.get('zaman', '')}:{tetik.get('ilceId', '')}")
    return "|".join(parcalar)


def uzak_yoklama_gerekli() -> bool:
    """Uzun yoklama sırasında tetikleyici UZAKTAN çekilsin mi?

    Hayır eğer MQTT push açıksa (mesaj getirir) ya da veri yerelden okunuyorsa (dosya değişimi
    yerel imzada görünür). Bu, cihaz başına yoklama maliyetini önler (600 cihaz ölçeği).
    """
    from core import push as push_modulu

    # DİKKAT: `acik()` yalnız AYARIN açık olduğunu söyler. Bağlantı DENENDİ ve KOPTUysa push
    # mesaj getirmez; uzun yoklama da hiçbir şey öğrenmez → değişiklik yeniden başlatmaya kalırdı.
    # (Başlangıçta henüz denenmemişse push'a güvenilir; gereksiz uzak istek yapılmaz.)
    if push_modulu.acik():
        durum = push_modulu.durum() or {}
        if bool(durum.get("bagli")) or not bool(durum.get("denendi")):
            return False
    return str(getattr(config, "WEB_VERI_MODU", "yerel")).lower() == "https" or str(
        getattr(config, "KAYNAK", "dosya")
    ).lower() == "https"


def degisiklik_bekle(imza: str, sure_s: float, izinli: bool = True, uzak_kaynak: bool = False) -> dict:
    """`imza` değişene kadar (en fazla `sure_s`) bekler; değişiklik bilgisini döner.

    Tarayıcıya SSE yerine **tek istek** (uzun yoklama) sunulur: kurulum gerektirmez,
    kopan bağlantıda arayüz kendi kendine yeniden kurar. Süre dolduğunda `degisti: false`
    döner (nabız) ve arayüz yeni bir istek açar.
    """
    if not izinli:
        # `tetik.aktif = false` ya da bu mod `tetik.modlar` içinde değil: arayüz ANINDA
        # yenilenmesin. İstek hemen dönmesin (sıcak döngü olur) — kısa bir nabız kadar beklenir.
        time.sleep(min(max(float(sure_s or 0), 1.0), 10.0))
        return {"degisti": False, "imza": degisiklik_imzasi(), "tetik": None, "damga": lastupdate_damgasi()}
    ilk = degisiklik_imzasi()
    if not imza or imza != ilk:
        return {"degisti": True, "imza": ilk, "tetik": tetik_oku(), "damga": lastupdate_damgasi()}
    bitis = time.monotonic() + max(0.0, sure_s)
    # https modunda veri UZAKTA: yerel `tetikle.json` ancak indirilince imza değişir. Uzun yoklama
    # sırasında tetikleyiciyi KENDİMİZ çekiyoruz; aksi hâlde yenileme arka plan turunu (20 sn)
    # bekliyordu — "anlık" beklentisini karşılamıyordu.
    # ÜST SINIR: `ayarlar.json` içinde `tetik.kontrol_ms` 300000 (5 dk) yazılı olabiliyor.
    # Uzun yoklamada tetikleyici çekimi bu değere uyarsa "anlık" beklentisi 5 dakikaya düşer.
    # En fazla `DAMGA_KONTROL_MS` (120 sn) kullanılır.
    _kontrol = float(getattr(config, "TETIK_KONTROL_MS", 3000)) / 1000.0
    _tavan = float(getattr(config, "DAMGA_KONTROL_MS", 120_000)) / 1000.0
    kontrol_s = max(1.0, min(_kontrol, _tavan))
    sonraki_cekim = time.monotonic() + kontrol_s
    while time.monotonic() < bitis:
        time.sleep(0.4)
        if uzak_kaynak and time.monotonic() >= sonraki_cekim:
            sonraki_cekim = time.monotonic() + kontrol_s
            try:
                tetik_modulu.getir()
            except Exception:  # noqa: BLE001 - ağ hatası yoklamayı durdurmamalı
                log.debug("tetikleyici çekilemedi", exc_info=True)
        simdi = degisiklik_imzasi()
        if simdi != ilk:
            return {"degisti": True, "imza": simdi, "tetik": tetik_oku(), "damga": lastupdate_damgasi()}
    return {"degisti": False, "imza": ilk, "tetik": tetik_oku(), "damga": lastupdate_damgasi()}


def lastupdate_damgasi() -> str:
    """`lastupdate.json` içindeki damga (arayüz `durum.damga` ile karşılaştırır)."""
    yol = KOK / str(getattr(config, "LASTUPDATE_DOSYASI", "lastupdate.json"))
    try:
        veri = json.loads(yol.read_bytes()[-8192:].decode("utf-8-sig"))
    except (OSError, ValueError):
        return ""
    if not isinstance(veri, dict):
        return ""
    for anahtar in ("lastupdate", "lastUpdate", "tarih", "zaman"):
        if veri.get(anahtar):
            return str(veri[anahtar])
    return ""


class GorselReddedildi(RuntimeError):
    """Görsel güvenlik denetiminden geçemedi (403 ile yanıtlanır)."""


def gorsel_getir(url: str) -> tuple[bytes, str]:
    """Görseli CİHAZ ÖNBELLEĞİNDEN ya da ağdan alır (doğrulayıp önbelleğe yazar).

    NEDEN SUNUCU ÜZERİNDEN: tarayıcı, farklı alan adındaki görselleri `fetch` ile alamaz
    (CORS başlığı yoksa "Failed to fetch"). Qt'de bu kısıt yoktur. Sunucu görseli
    indirdiğinde hem bu sınır kalkar hem de CİHAZ ÖNBELLEĞİ (Qt ile aynı `onbellek/`
    klasörü) ve güvenlik denetimleri (izin listesi, bayt/piksel bütçesi, biçim beyaz
    listesi) aynen kullanılır. Ayrıca aynı görsel ikinci kez internetten çekilmez.
    """
    from core import onbellek
    from security.image_policy import dogrula
    from security.network import indir

    from security.network import AgHatasi as _AgHatasi
    from security.network import gorsel_icin_ayarlar

    ayarlar = _ag_ayarlari()
    try:
        ayarlar.dogrula_url(url)
    except _AgHatasi as hata:
        # Veri izin listesi görseller için çok dar: yayın görselleri panelde serbest adreslenir.
        # Herkese açık https host ise (özel/loopback IP değilse) izin ver.
        ayarlar = gorsel_icin_ayarlar(ayarlar, url)
        log.info("görsel: izin listesi dışı herkese açık host kabul edildi (%s) — %s", url, hata)

    baytlar = onbellek.gorsel_oku(url)
    if baytlar is not None:
        onbellek.gorsel_gosterildi(url)
        return baytlar, _icerik_turu_tahmin(baytlar)

    ham, icerik_turu = indir(url, ayarlar)
    karar = dogrula(
        ham,
        en_buyuk_bayt=config.MAX_GORSEL_BAYT,
        en_buyuk_piksel=config.MAX_GORSEL_PIKSEL,
        icerik_turu=icerik_turu,
    )
    if not karar.kabul:
        raise GorselReddedildi(f"görsel reddedildi: {karar.sebep}")
    onbellek.gorsel_yaz(url, ham, icerik_turu)
    return ham, _icerik_turu_tahmin(ham, icerik_turu)


def ayar_varsayilani(ad: str) -> bytes | None:
    """Cihazda bulunmayan ayar dosyaları için varsayılan içerik (404 yerine 200).

    `ayarlar.json` ve `kapsam-ayarlari.json` İSTEĞE BAĞLIDIR: yoksa varsayılanlar
    geçerlidir (Qt tarafı da böyle davranır). Arayüze 404 döndürüp konsolu kirletmek
    yerine varsayılanlar sunulur. `tetikle.json` da öyledir: tetikleyici YOK demektir.
    """
    try:
        import ayarlar as ayar_modulu

        if ad == getattr(config, "TETIK_DOSYASI", "tetikle.json"):
            return json.dumps(
                {"zaman": "", "ilceId": "", "bolgeId": "", "aciklama": ""}, ensure_ascii=False
            ).encode("utf-8")
        if ad == getattr(config, "AYARLAR_DOSYASI", "ayarlar.json"):
            belge = ayar_modulu.varsayilan_belge()
            temiz = {
                grup: {k: v for k, v in (degerler or {}).items() if not k.startswith("_")}
                for grup, degerler in belge.items()
            }
            return json.dumps(temiz, ensure_ascii=False, indent=1).encode("utf-8")
        if ad == getattr(config, "KAPSAM_AYARLARI_DOSYASI", "kapsam-ayarlari.json"):
            return json.dumps(
                {"varsayilan": {}, "ilceler": {}, "bolgeler": {}, "cihazlar": {}}, ensure_ascii=False, indent=1
            ).encode("utf-8")
    except Exception:  # noqa: BLE001 - varsayılan üretilemezse 404'e düşülür
        return None
    return None


# ------------------------------------------------------------------ statik sunucu
class _IstekIsleyici(http.server.BaseHTTPRequestHandler):
    """Beyaz listeli statik sunucu (web/ + izinli veri dosyaları)."""

    sunucu_surumu = "yourkiosk-web/1.0"
    #: test/teşhis için son isteklerin kaydı
    gunluk: list[tuple[str, int]] = []

    def log_message(self, bicim, *args):  # noqa: A003 - üst sınıf arayüzü
        log.debug("web sunucu: %s", bicim % args)

    # -- yardımcılar ------------------------------------------------------
    def _yol(self) -> str:
        ham = self.path.split("?", 1)[0]
        try:
            from urllib.parse import unquote

            return unquote(ham)
        except Exception:  # pragma: no cover - unquote nadiren hata verir
            return ham

    def _hedef(self, tam_yol: str) -> Path | None:
        """İstenen yolu güvenli biçimde dosya sistemine çevirir (yoksa None)."""
        temiz = tam_yol.replace("\\", "/")
        if "\x00" in temiz or ".." in temiz.split("/"):
            return None
        if tam_yol in ("/", "/index.html"):
            return web_kok() / "index.html"

        ad = Path(temiz).name
        # veri dosyaları proje kökünden, geri kalanı web klasöründen
        if ad in SUNULAN_VERI_DOSYALARI and tam_yol == f"/{ad}":
            return KOK / ad
        # tasarım görselleri (Qt ile AYNI dosyalar; kopyalanmaz, tek kaynaktan sunulur)
        if tam_yol.startswith("/bg_layout/") and tam_yol.count("/") == 2:
            return KOK / "bg_layout" / ad
        if tam_yol in ("/logo.png",):
            return KOK / "logo.png"
        # yasaklı adlar kök yoluyla eşlenir: _gonder bunları 403 ile reddeder
        if ad in YASAKLI_ADLAR:
            return KOK / ad
        return web_kok() / temiz.lstrip("/")

    def _govde_gonder(self, govde: bytes, tur: str, onbellek_kontrolu: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", onbellek_kontrolu)
        self.end_headers()
        self.wfile.write(govde)
        self.gunluk.append((self.path, 200))

    def _gorsel(self) -> None:
        """`/gorsel?u=<url>`: görseli cihaz önbelleğinden/ağdan alıp sunar (CORS engeli yok).

        Tarayıcı farklı alan adındaki görseli `fetch` edemez; bu uç, indirmeyi sunucu
        tarafında yapar. Önbellek ve güvenlik denetimleri Qt moduyla aynıdır.
        """
        from urllib.parse import parse_qs

        from security.network import AgHatasi

        sorgu = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        url = (sorgu.get("u") or [""])[0].strip()
        if not url:
            self._hata(400, "u parametresi yok")
            return
        try:
            baytlar, tur = gorsel_getir(url)
        except GorselReddedildi as hata:
            log.warning("görsel reddedildi (%s): %s", url, hata)
            self._hata(403, str(hata))
            return
        except AgHatasi as hata:
            # adres politikası ihlali (izin listesi/scheme/port) → 403, ağ hatası → 502
            metin = str(hata)
            politika = any(k in metin for k in ("izin", "politika", "kabul edilir", "adres ", "reddedildi", "çözümlenemedi"))
            log.warning("görsel alınamadı (%s): %s", url, hata)
            self._hata(403 if politika else 502, metin)
            return
        except Exception as hata:  # noqa: BLE001 - sunucu çökmemeli
            log.warning("görsel hatası (%s): %s", url, hata)
            self._hata(502, "görsel alınamadı")
            return
        self._govde_gonder(baytlar, tur, "public, max-age=86400")

    def _degisiklik(self) -> None:
        """`/degisiklik?imza=<imza>&sure=<sn>` — nöbet değişikliğini ANINDA bildirir.

        Uzun yoklama (long poll): imza değişmediyse istek `sure` saniye (en çok
        `DEGISIKLIK_BEKLEME_S`) açık kalır, değiştiği an yanıt döner. Arayüz böylece
        20 sn'lik yoklamayı beklemeden (tipik olarak <1 sn) nöbet değişikliğini gösterir.
        Yalnızca 127.0.0.1'e açıktır ve yalnızca imza/tetikleyici bilgisi döner.
        """
        from urllib.parse import parse_qs

        sorgu = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        imza = (sorgu.get("imza") or [""])[0]
        ham_sure = (sorgu.get("sure") or [""])[0]
        try:
            sure = float(ham_sure) if ham_sure else float(getattr(config, "DEGISIKLIK_BEKLEME_S", 30))
        except ValueError:
            sure = float(getattr(config, "DEGISIKLIK_BEKLEME_S", 30))
        sure = max(0.0, min(sure, float(getattr(config, "DEGISIKLIK_BEKLEME_S", 30))))
        uzak = uzak_yoklama_gerekli()
        veri = degisiklik_bekle(imza, sure, tetik_modulu.otomatik_acik("tarayici"), uzak)
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self._govde_gonder(govde, "application/json; charset=utf-8", "no-store")

    def _onbellek_bakimi(self, govde: bytes) -> None:
        """Yayın verisi sunulurken önbellek bakımı (Qt `_onbellek_bakimi` karşılığı)."""
        try:
            from core import onbellek

            veri = json.loads(govde.decode("utf-8-sig"))
            yayinlar = veri.get("Yayinlar") or {}
            gecerli = {
                str(y.get("contentUrl") or y.get("contentURL") or "")
                for y in yayinlar.values()
                if isinstance(y, dict)
            }
            gecerli.discard("")
            ozet = onbellek.bakim(gecerli_url_kumesi=gecerli or None)
            if ozet.get("silinen") or ozet.get("oksuz_dosya"):
                log.info(
                    "önbellek bakımı: %s görsel silindi, kalan %.1f MB",
                    ozet.get("silinen", 0),
                    ozet.get("kalan_bayt", 0) / 1024 / 1024,
                )
        except Exception:  # noqa: BLE001 - bakım veri sunmayı engellememeli
            log.warning("önbellek bakımı yapılamadı", exc_info=True)

    def _gonder(self, yol: Path) -> None:
        try:
            gercek = yol.resolve(strict=True)
        except (OSError, RuntimeError):
            self._hata(404, "bulunamadı")
            return
        # kök dışına çıkma / sembolik bağ denetimi
        izinli_kokler = (web_kok().resolve(), KOK.resolve())
        if not any(gercek == k or k in gercek.parents for k in izinli_kokler):
            self._hata(403, "izin yok")
            return
        # makinebilgileri (cihaz kimliği) ve gizli klasörler asla sunulmaz
        if gercek.name == "makinebilgileri.json" or any(p.startswith(".") for p in gercek.parts):
            self._hata(403, "izin yok")
            return
        if gercek.suffix.lower() not in IZINLI_UZANTILAR:
            self._hata(403, "izin yok")
            return
        if not gercek.is_file():
            self._hata(404, "bulunamadı")
            return

        govde = gercek.read_bytes()
        tur = _icerik_turu(gercek)
        # yayın verisi sunulurken süresi geçen görselleri temizle (Qt ile aynı kural)
        if gercek.name == getattr(config, "SISTEM_VERISI_DOSYASI", "lastSystemData.json"):
            self._onbellek_bakimi(govde)
        onbellek_kontrolu = (
            "no-store" if (tur.startswith("text/html") or tur.startswith("application/json")) else "public, max-age=86400"
        )
        self._govde_gonder(govde, tur, onbellek_kontrolu)

    def _hata(self, kod: int, mesaj: str) -> None:
        govde = mesaj.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)
        self.gunluk.append((self.path, kod))

    def do_GET(self):  # noqa: N802 - üst sınıf arayüzü
        # 0) görsel köprüsü: /gorsel?u=<url> (CORS engeli olmadan, cihaz önbelleğiyle)
        if self.path.startswith("/gorsel"):
            self._gorsel()
            return
        # 0.1) değişiklik bildirimi: /degisiklik?imza=... (uzun yoklama; nöbet değişikliği anında)
        if self.path.startswith("/degisiklik"):
            self._degisiklik()
            return
        hedef = self._hedef(self._yol())
        if hedef is None:
            self._hata(403, "izin yok")
            return
        # cihazda olmayan İSTEĞE BAĞLI ayar dosyaları → varsayılan içerik (404 konsolu kirletmesin)
        if not hedef.is_file():
            varsayilan = ayar_varsayilani(hedef.name)
            if varsayilan is not None:
                self._govde_gonder(varsayilan, "application/json; charset=utf-8", "no-store")
                return
        self._gonder(hedef)

    def do_HEAD(self):  # noqa: N802
        hedef = self._hedef(self._yol())
        if hedef is None or not hedef.is_file():
            self._hata(404, "bulunamadı")
            return
        self.send_response(200)
        self.send_header("Content-Type", _icerik_turu(hedef))
        self.send_header("Content-Length", str(hedef.stat().st_size))
        self.end_headers()


def _icerik_turu(yol: Path) -> str:
    import mimetypes

    tur = mimetypes.guess_type(str(yol))[0]
    if not tur:
        return "application/octet-stream"
    if tur.startswith("text/") or tur in {"application/javascript", "application/json"}:
        return f"{tur}; charset=utf-8"
    return tur


class Sunucu(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def sunucu_baslat(adres: str | None = None, port: int | None = None) -> tuple[Sunucu, int, threading.Thread]:
    """Yerel statik sunucuyu ayrı bir iş parçacığında başlatır (port 0 = boş port)."""
    adres = adres or sunucu_adresi()
    port = sunucu_portu() if port is None else int(port)
    if not web_kok().is_dir() or not (web_kok() / "index.html").is_file():
        raise FileNotFoundError(f"arayüz bulunamadı: {web_kok()} (bkz. web/README.md)")
    if not derlenmis_mi():
        raise FileNotFoundError(
            "arayüz DERLENMEMİŞ: tarayıcı TypeScript çalıştıramaz (bu yüzden beyaz ekran görünür). "
            f"Şunu çalıştırın:  cd {web_kaynak_kok()} && npm install --include=dev && npm run build"
        )
    sunucu = Sunucu((adres, port), _IstekIsleyici)
    gercek_port = sunucu.server_address[1]
    is_parcacigi = threading.Thread(target=sunucu.serve_forever, name="web-sunucu", daemon=True)
    is_parcacigi.start()
    log.info("web sunucu hazır: http://%s:%s (kök: %s)", adres, gercek_port, web_kok())
    return sunucu, gercek_port, is_parcacigi


# ------------------------------------------------------------------ tarayıcı
def tarayici_bul(yol: str | None = None) -> str | None:
    """Tarayıcı çalıştırılabilir dosyasını bulur (PATH ya da açık yol)."""
    aday = str(yol or getattr(config, "TARAYICI_YOLU", "chromium"))
    if os.path.isabs(aday) or "/" in aday:
        return aday if Path(aday).is_file() else None
    bulunan = shutil.which(aday)
    if bulunan:
        return bulunan
    for yedek in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "chrome"):
        if shutil.which(yedek):
            log.warning("'%s' bulunamadı; '%s' kullanılacak", aday, yedek)
            return shutil.which(yedek)
    return None


def _port_bos_mu(adres: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((adres, port)) != 0


def _bizim_sunucu_mu(adres: str, port: int, zaman_asimi: float = 1.0) -> bool:
    """Portta bizim web arayüzümüz mü var? (index.html içinde 'yourkiosk' işareti)"""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{adres}:{port}/index.html", timeout=zaman_asimi) as yanit:
            return b"yourkiosk" in yanit.read(4096).lower()
    except (urllib.error.URLError, OSError, ValueError):
        return False


def baslat(
    client_id: str,
    *,
    tarayici: str | None = None,
    port: int | None = None,
    veri_modu: str | None = None,
    kuru: bool = False,
    yeniden_baslat_s: int | None = None,
    deneme_siniri: int = 5,
    tani: bool = False,
) -> int:
    """Sunucuyu başlatır ve tarayıcıyı kiosk modunda açar.

    `kuru=True` hiçbir şey başlatmaz: yalnızca adresi ve komutu döndürür (test/teşhis).
    Tarayıcı kapanırsa `TARAYICI_YENIDEN_BASLAT_S` saniye sonra yeniden açılır; kısa
    sürede `deneme_siniri` kez üst üste çökerse vazgeçilir (sonsuz döngü olmasın).
    """
    yol = tarayici_bul(tarayici)
    if kuru:
        adres = url_olustur(client_id, veri_modu, port=port)
        komut = komut_olustur(adres, yol or str(getattr(config, "TARAYICI_YOLU", "chromium")), tani=tani)
        print(f"adres : {adres}")
        print(f"komut : {' '.join(shlex.quote(p) for p in komut)}")
        return 0

    if tani:
        # tarayıcı bulunamasa/derleme eksik olsa bile rapor yazılır
        print("=== TANI RAPORU (--tani) ===")
        for satir in tani_raporu(client_id, 0):
            print(f"  {satir}")
        print()

    eksik_veri = [ad for ad in CIHAZ_VERI_DOSYALARI if not (KOK / ad).is_file()]
    if eksik_veri:
        mesaj = (
            "CİHAZ VERİSİ EKSİK: " + ", ".join(eksik_veri) + "\n"
            "  Bu dosyalar cihaza özgüdür ve depoya girmez (temiz klonda yoktur).\n"
            "  Çözüm:  python3 tools/fetch_nobet.py        (veriyi kaynaktan üret)\n"
            "          ya da eski kurulumdan kopyalayın:\n"
            "          cp /eski/kurulum/kiosk/{lastupdate,lastSystemData,match,makinebilgileri}.json kiosk/"
        )
        log.error("%s", mesaj.replace("\n", " | "))
        print(mesaj)
        print("  (arayüz açılacak ama veri kartında aynı mesaj görünecek)\n")

    if not yol:
        log.error("tarayıcı bulunamadı: %s (ayar: calistirma.tarayici_yolu)", getattr(config, "TARAYICI_YOLU", "chromium"))
        return 2

    if not derlenmis_mi():
        # Kaynak arayüzü tarayıcıda ÇALIŞMAZ (TypeScript) → beyaz ekran yerine net hata.
        mesaj = (
            "arayüz derlenmemiş (web/dist/index.html yok). Tarayıcı .ts dosyalarını çalıştıramaz;\n"
            f"  çözüm:  cd {web_kaynak_kok()}\n"
            "          npm install --include=dev\n"
            "          npm run build\n"
            "  (derleme yoksa arayüz açılmaz; Qt moduna dönmek için calistirma.mod = \"qt\")"
        )
        log.error("%s", mesaj)
        print(mesaj)
        return 4

    # PAKET TAZELİĞİ: `web/dist` git'te YOK (.gitignore) → `git pull` eski arayüzü bırakır.
    # Bayatsa otomatik derlenir; derlenemezse YÜKSEK SESLE uyarılır (sessiz eski arayüz yasak).
    if bool(getattr(config, "TARAYICI_OTOMATIK_DERLE", True)):
        _oldu, _mesaj = web_derle()
        if _oldu and _mesaj == "derlendi":
            log.info("tarayıcı paketi derlendi (web/dist güncellendi)")
        elif not _oldu:
            log.warning("%s (%s)", paket_uyarisi() or "tarayıcı paketi güncellenemedi", _mesaj)
    else:
        _uyari = paket_uyarisi()
        if _uyari:
            log.warning("%s", _uyari)

    profil_kok().mkdir(parents=True, exist_ok=True)
    #: tarayıcı profili yalnızca sahibi okuyabilsin (kimlik/çerez içerebilir)
    try:
        profil_kok().chmod(0o700)
    except OSError:
        pass

    # --- yerel sunucu: istenen port boşsa oraya, doluysa (ve bizim sunucumuz değilse)
    #     işletim sisteminin vereceği boş bir porta kurulur.
    istenen_port = sunucu_portu() if port is None else int(port)
    sunucu = None
    yerel_port = istenen_port
    if _port_bos_mu(sunucu_adresi(), istenen_port):
        sunucu, yerel_port, _ = sunucu_baslat(sunucu_adresi(), istenen_port)
    elif _bizim_sunucu_mu(sunucu_adresi(), istenen_port):
        log.info("port %s üzerinde çalışan web sunucumuz bulundu; o kullanılacak", istenen_port)
    else:
        log.warning("port %s başka bir servis tarafından kullanılıyor; boş port seçiliyor", istenen_port)
        sunucu, yerel_port, _ = sunucu_baslat(sunucu_adresi(), 0)

    adres = url_olustur(client_id, veri_modu, port=yerel_port)
    komut = komut_olustur(adres, yol, tani=tani)

    if tani:
        print("=== tarayıcı çıktısı (konsol hataları dâhil) aşağıda ===")
        print()

    bekleme = int(getattr(config, "TARAYICI_YENIDEN_BASLAT_S", 5) if yeniden_baslat_s is None else yeniden_baslat_s)
    denemeler: list[float] = []
    kod = 0
    durdur = {"istek": False}
    surec_kutusu: dict = {"surec": None}

    def _sinyal(_isaret, _cerceve):  # pragma: no cover - sinyal yolu
        durdur["istek"] = True

    for isaret in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(isaret, _sinyal)
        except (ValueError, OSError):  # ana iş parçacığı değilse
            pass

    # NÖBET DEĞİŞİKLİĞİ + UZAKTAN KOMUT: arka planda küçük dosyaları tazeler, komutu uygular.
    # (Süpervizör döngüsü tarayıcıyı beklediği için ayrı bir iş parçacığı gerekir.)
    from core import push as push_modulu

    push_modulu.baslat()

    izleyici = threading.Thread(
        target=_uzak_kontrol_dongusu,
        args=(durdur, surec_kutusu, str(client_id), float(getattr(config, "DAMGA_KONTROL_MS", 20000)) / 1000.0),
        name="uzak-kontrol",
        daemon=True,
    )
    izleyici.start()

    try:
        while not durdur["istek"]:
            log.info("tarayıcı başlatılıyor (kiosk): %s", adres)
            try:
                surec = subprocess.Popen(komut, cwd=str(KOK), start_new_session=True)  # noqa: S603
                surec_kutusu["surec"] = surec
                kod = surec.wait()
            except FileNotFoundError:
                log.error("tarayıcı çalıştırılamadı: %s", yol)
                return 2
            except KeyboardInterrupt:  # pragma: no cover
                durdur["istek"] = True
                break
            log.info("tarayıcı kapandı (çıkış kodu %s)", kod)
            if bekleme <= 0 or durdur["istek"]:
                break
            simdi = time.time()
            denemeler = [t for t in denemeler if simdi - t < 60]
            denemeler.append(simdi)
            if len(denemeler) > deneme_siniri:
                log.error("tarayıcı 60 saniyede %d kez kapandı; yeniden başlatma durduruldu", len(denemeler))
                return 1
            log.info("%s saniye sonra yeniden başlatılacak", bekleme)
            for _ in range(int(bekleme * 10)):
                if durdur["istek"]:
                    break
                time.sleep(0.1)
    finally:
        if sunucu is not None:
            sunucu.shutdown()
            sunucu.server_close()
    return kod


def uzak_kontrol_bir_tur(cihaz_id: str, surec_kutusu: dict | None = None) -> str:
    """Küçük kontrol dosyalarını tazeler (`tetikle.json`, `komut.json`) ve komutu uygular.

    Tek tur, yan etkileri sınırlı: dönen metin boşsa "yapılacak bir şey yok" demektir.
    `ekrani-yenile` komutunda tarayıcı süreci kapatılır (süpervizör onu yeniden başlatır →
    kiosk'ta sayfa tazelemenin en güvenilir yolu). `argv`'li komutlar (`systemctl ...`) kendileri
    gerekli işi yapar.

    Test edilebilirlik için ayrı tutuldu: zamanlayıcı/thread mantığı bu fonksiyonun dışında.
    """
    from core import komut as komut_modulu
    from core import tetik as tetik_modulu

    try:
        tetik_modulu.getir()
        komut_modulu.getir()
    except Exception:  # noqa: BLE001 - ağ/indirme hatası gösterimi etkilemesin
        log.warning("uzak kontrol dosyaları alınamadı", exc_info=True)

    try:
        karar, sonuc = komut_modulu.kontrol(cihaz_id=cihaz_id)
    except Exception:  # noqa: BLE001
        log.warning("uzaktan komut denetimi yapılamadı", exc_info=True)
        return ""

    if sonuc is None:
        return ""
    satir = komut_modulu.sonuc_metni(sonuc)
    log.warning("UZAKTAN KOMUT: %s", satir)
    if sonuc.uygulama_ici and surec_kutusu is not None:
        surec = surec_kutusu.get("surec")
        if surec is not None and surec.poll() is None:
            log.info("ekrani-yenile: tarayıcı yeniden başlatılıyor (sayfa tazelenecek)")
            surec.terminate()
    return satir


def _uzak_kontrol_dongusu(durdur: dict, surec_kutusu: dict, cihaz_id: str, aralik_s: float) -> None:
    """Arka planda `DAMGA_KONTROL_MS` aralığıyla `uzak_kontrol_bir_tur` çağırır (daemon thread)."""
    while not durdur.get("istek"):
        for _ in range(int(max(1.0, float(aralik_s)) * 10)):
            if durdur.get("istek"):
                return
            time.sleep(0.1)
        if durdur.get("istek"):
            return
        try:
            uzak_kontrol_bir_tur(cihaz_id, surec_kutusu)
        except Exception:  # noqa: BLE001 - thread ölmesin
            log.warning("uzak kontrol turu hata verdi", exc_info=True)


def calistir(_ayarlar_hazir=None) -> int:
    """`main.py` tarafından çağrılan giriş noktası (mod=tariyaci)."""
    from core import veri_kaynagi

    client_id = str(veri_kaynagi.client_id() or "").strip()
    if not client_id:
        log.error("cihaz kimliği okunamadı (%s); URL'ye clientID yazılamaz", config.MAKINE_DOSYASI)
        return 3
    return baslat(client_id)


def main(argv=None) -> int:
    import argparse

    ayristirici = argparse.ArgumentParser(description="yourkiosk tarayıcı (Chromium kiosk) gösterim modu")
    ayristirici.add_argument("--client-id", default="", help="cihaz kimliği (boşsa makinebilgileri.json'dan)")
    ayristirici.add_argument("--port", type=int, default=None, help="yerel sunucu portu")
    ayristirici.add_argument("--tarayici", default=None, help="tarayıcı çalıştırılabilir dosyası")
    ayristirici.add_argument("--veri-modu", choices=["yerel", "https"], default=None)
    ayristirici.add_argument("--kuru", action="store_true", help="başlatma; yalnızca adres ve komutu yazdır")
    ayristirici.add_argument(
        "--tani", action="store_true", help="ön kontrol raporu yazdır + tarayıcı konsolunu terminale dök"
    )
    ayristirici.add_argument("--yeniden-baslat-s", type=int, default=None)
    secenek = ayristirici.parse_args(argv)

    from core import veri_kaynagi

    kimlik = secenek.client_id or str(veri_kaynagi.client_id() or "")
    return baslat(
        kimlik,
        tarayici=secenek.tarayici,
        port=secenek.port,
        veri_modu=secenek.veri_modu,
        kuru=secenek.kuru,
        yeniden_baslat_s=secenek.yeniden_baslat_s,
        tani=secenek.tani,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


#: Bayatlık toleransı (sn): dosya sistemi mtime çözünürlüğü/vardiya farkı.
_BAYAT_TOLERANS_S = 1.0

#: `web/dist` içine derlenen kaynaklar (bunlardan biri yeniyse paket BAYAT).
_DERLEME_GIRDISI = ("src", "index.html", "package.json", "vite.config.ts", "tsconfig.json")


def _web_proje_koku() -> Path:
    """Web projesinin kökü: `kiosk/` komşusu (`<proje>/web`). Testler `KOK`u taşır."""
    for aday in (KOK.parent / "web", KOK / "web"):
        if (aday / "package.json").is_file() or (aday / "src").is_dir():
            return aday
    return KOK.parent / "web"


def dist_durumu() -> dict:
    """Tarayıcının yüklediği derlenmiş paket (`web/dist`) GÜNCEL mi?

    NEDEN: `web/dist/` .gitignore'da → `git pull` derlenmiş paketi GETİRMEZ. Sunucu tarafı
    düzeltilse bile cihaz **eski JavaScript**'i çalıştırır ve ekranda hiçbir şey değişmez.
    Gerçek olay: Qt güncelleniyordu, tarayıcı güncellenmiyordu; `web/dist` 8 saat eskiydi.

    Dönüş: `{"var": bool, "bayat": bool, "en_yeni_kaynak": str, "dist_mtime": float}`.
    """
    kok = _web_proje_koku()
    dist = kok / "dist"
    index = dist / "index.html"
    if not index.is_file():
        return {"var": False, "bayat": True, "en_yeni_kaynak": "", "dist_mtime": 0.0}
    try:
        damga = index.stat().st_mtime
    except OSError:
        return {"var": False, "bayat": True, "en_yeni_kaynak": "", "dist_mtime": 0.0}

    en_yeni_zaman, en_yeni_yol = 0.0, ""
    for parca in _DERLEME_GIRDISI:
        yol = kok / parca
        if not yol.exists():
            continue
        adaylar = [yol] if yol.is_file() else [x for x in yol.rglob("*") if x.is_file()]
        for aday in adaylar:
            try:
                zaman = aday.stat().st_mtime
            except OSError:
                continue
            if zaman > en_yeni_zaman:
                en_yeni_zaman, en_yeni_yol = zaman, aday

    bayat = en_yeni_zaman > damga + _BAYAT_TOLERANS_S
    return {
        "var": True,
        "bayat": bayat,
        "en_yeni_kaynak": str(en_yeni_yol.relative_to(kok)) if en_yeni_yol else "",
        "dist_mtime": damga,
    }


def web_derle(zorla: bool = False) -> tuple[bool, str]:
    """`web/dist` bayatsa derler (`npm run build`). Dönüş: (başarılı, mesaj).

    Cihazda node/npm yoksa derleme YAPILAMAZ → çağıran taraf yüksek sesle uyarır; sessizce
    eski paketle devam etmek "değişiklik gelmiyor" şikâyetini üretir.
    """
    import shutil as _shutil
    import subprocess as _subprocess

    durum = dist_durumu()
    if not zorla and not durum["bayat"]:
        return True, "paket güncel"
    npm = _shutil.which("npm")
    if not npm:
        return False, "npm bulunamadı — cihazda derleme yapılamaz (paket elle kopyalanmalı)"
    web = _web_proje_koku()
    try:
        sonuc = _subprocess.run(
            [npm, "run", "build"], cwd=web, capture_output=True, text=True, timeout=600,
        )
    except (_subprocess.SubprocessError, OSError) as hata:
        return False, f"derleme çalıştırılamadı: {hata}"
    if sonuc.returncode != 0:
        kuyruk = (sonuc.stderr or sonuc.stdout or "")[-300:]
        return False, f"derleme başarısız (çıkış {sonuc.returncode}): {kuyruk}"
    if dist_durumu()["bayat"]:
        return False, "derleme bitti ama paket hâlâ bayat görünüyor"
    return True, "derlendi"


def paket_uyarisi() -> str:
    """Bayat/eksik paket için TEK satırlık, eyleme dönük uyarı (boş = sorun yok)."""
    durum = dist_durumu()
    if not durum["var"]:
        return "TARAYICI PAKETİ YOK: cd web && npm run build (tarayıcı modu açılamaz)"
    if durum["bayat"]:
        return (
            f"TARAYICI PAKETİ BAYAT: web/{durum['en_yeni_kaynak']} paketten yeni → "
            "ekrandaki arayüz ESKİ koddur. Düzelt: ./kur.sh kiosk"
        )
    return ""
