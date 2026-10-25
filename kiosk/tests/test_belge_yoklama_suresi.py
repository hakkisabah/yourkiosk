"""Belgelerdeki yoklama süreleri KODDAN türetilmeli (i5 "ifade doğruluğu" sınıfı).

NEDEN: `DAMGA_KONTROL_MS` bir zamanlar 20 sn'ydi; 30/120 sn'ye çekildikten sonra README,
NODET-DEGISIKLIGI.md, KOMUTLAR.md ve iki araç docstring'i "20 sn" demeye devam etti. Kullanıcı
"bildirdim ama değişmedi" beklentisini bu yanlış metinden kuruyor.

Bu test SABİT KALIPLARI aramaz (eski sürüm öyleydi ve bayat metni kaçırdı — i5 bulgusu).
Bunun yerine tüm kiosk metinlerini TARAR:

  1. Bir satırda `DAMGA_KONTROL_MS` geçiyorsa "20 sn"/"20000" geçemez (bayat sabit).
  2. `getattr(config, "DAMGA_KONTROL_MS", <varsayılan>)` varsayılanı 120000 olmalı; sessiz
     `20000` varsayılanı belgeyle çelişir.
  3. Yoklama süresinden söz eden satır "20 sn" diyemez (tek moda özgü değer genellenemez).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import config

KIOSK = Path(__file__).resolve().parents[1]
ATLANAN = {".venv", ".qt-libs", "__pycache__", "_arsiv", ".karantina", "onbellek", "node_modules"}


def _izlenen_dosyalar() -> set[Path] | None:
    """`git` varsa İZLENEN dosyaların kümesi; yoksa None.

    i5 bulgusu: tarama `kiosk/` altındaki TÜM .json dosyalarını okuyordu — cihazda
    `ayarlar.json`, `lastSystemData.json` gibi gitignore'lu VERİ dosyaları da taranıyor ve
    içlerinde geçen bir sayı testi kırabiliyordu. Sadece depoya giren metinler taranmalı.
    """
    try:
        cikti = subprocess.run(
            ["git", "-C", str(KIOSK), "ls-files", "-z"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if cikti.returncode != 0 or not cikti.stdout:
        return None
    return {KIOSK / ad for ad in cikti.stdout.split("\0") if ad}


#: Bayat süre işaretleri. DİKKAT: `120 sn` içindeki "20 sn" eşleşmesin diye önceki karakter
#: rakam olamaz (`(?<!\d)`) — ilk sürüm bunu kaçırdı ve doğru metni de "bayat" saydı.
BAYAT_SN = re.compile(r"(?<!\d)20\s*sn\b", re.IGNORECASE)
BAYAT_MS = re.compile(r"(?<!\d)20000(?!\d)")
#: Kendi belgesi: eski değeri ANLATIR (20 sn), taranmaz.
KENDI = Path(__file__).resolve()


def _metinler() -> list[Path]:
    """kiosk altındaki taranacak metin dosyaları (üretilen/3. parti dizinler hariç)."""
    izlenen = _izlenen_dosyalar()
    dosyalar: list[Path] = []
    for yol in KIOSK.rglob("*"):
        if not yol.is_file() or yol.suffix not in {".md", ".py", ".json", ".sh"}:
            continue
        if any(parca in ATLANAN for parca in yol.parts):
            continue
        # git varsa yalnız depoya giren dosyalar (cihaz verisi/gitignore'lu json taranmaz)
        if izlenen is not None and yol not in izlenen:
            continue
        dosyalar.append(yol)
    assert len(dosyalar) > 30, "tarama beklenenden az dosya buldu (yol hatası?)"
    return sorted(dosyalar)


def _kisa(satir: str, sinir: int = 160) -> str:
    """Assertion mesajını kısalt: taranan dosya cihaz verisi olsa bile gövde sızmasın."""
    temiz = " ".join(satir.split())
    return temiz if len(temiz) <= sinir else temiz[:sinir] + "…"


def test_damga_araligi_iki_degerli_kalir():
    """Sabitler: push bağlı 120 sn, kopuk 30 sn (etkin aralık bağlantıya göre seçilir)."""
    assert config.DAMGA_KONTROL_MS_PUSH == 120 * 1000
    assert config.DAMGA_KONTROL_MS_PUSH_YOK == 30 * 1000
    assert config.DAMGA_KONTROL_MS == 120 * 1000


def test_hicbir_metinde_bayat_20_sn_iddiasi_yok():
    """Tarama: `DAMGA_KONTROL_MS` geçen satırda 20 sn/20000; yoklama geçen satırda 20 sn kalmamalı."""
    kacak: list[str] = []
    for yol in _metinler():
        if yol == KENDI:
            continue
        for no, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), 1):
            bayat_sn = bool(BAYAT_SN.search(satir))
            damga = "DAMGA_KONTROL_MS" in satir
            yoklama = "yoklama" in satir.lower()
            if damga and (bayat_sn or BAYAT_MS.search(satir)):
                kacak.append(f"{yol.relative_to(KIOSK)}:{no}: {_kisa(satir)}")
            elif yoklama and "TETIK_KONTROL_MS" not in satir and (bayat_sn or BAYAT_MS.search(satir)):
                # `TETIK_KONTROL_MS` kendi başına 20 sn/20000'dir (ayrı sabit, doğru) — hariç tutulur.
                kacak.append(f"{yol.relative_to(KIOSK)}:{no}: {_kisa(satir)}")
    assert not kacak, "bayat yoklama süresi (20 sn / 20000):\n" + "\n".join(kacak)


def _ifade_degeri(ifade: str) -> int | None:
    """`1800 * 1000`, `120_000`, `120*1000` gibi aritmetik ifadeyi güvenle hesapla."""
    try:
        agac = ast.parse(ifade, mode="eval")
    except SyntaxError:
        return None

    def _hesapla(dugum):  # noqa: ANN001, ANN202
        if isinstance(dugum, ast.Expression):
            return _hesapla(dugum.body)
        if isinstance(dugum, ast.Constant) and isinstance(dugum.value, int):
            return dugum.value
        if isinstance(dugum, ast.BinOp) and isinstance(dugum.op, ast.Mult):
            sol, sag = _hesapla(dugum.left), _hesapla(dugum.right)
            if sol is None or sag is None:
                raise ValueError
            return sol * sag
        raise ValueError

    try:
        return _hesapla(agac)
    except (ValueError, RecursionError):
        return None


def test_getattr_varsayilanlari_kodla_ayni():
    """`getattr(config, "DAMGA_KONTROL_MS", <ifade>)` varsayılanı 120000 olmalı.

    i5 bulgusu: eski desen yalnız ÇIPLAK sayıyı (`120000`) görüyordu; `1800 * 1000` gibi
    aritmetik ifade biçimini kaçırdığı için timer_manager'daki 30 dakikalık bayat varsayılan
    yeşil testle yaşıyordu. Artık ifade AST ile hesaplanıp karşılaştırılır.
    """
    desen = re.compile(r'getattr\(\s*config\s*,\s*"DAMGA_KONTROL_MS"\s*,\s*([^)]+?)\s*\)')
    yanlis: list[str] = []
    for yol in _metinler():
        if yol.suffix != ".py" or yol == KENDI:
            # KENDİ dosyası atlanır: docstring'ler örnek `getattr(...)` biçimi anlatır.
            continue
        for no, satir in enumerate(yol.read_text(encoding="utf-8").splitlines(), 1):
            for ifade in desen.findall(satir):
                deger = _ifade_degeri(ifade)
                if deger != 120_000:
                    yanlis.append(f"{yol.relative_to(KIOSK)}:{no}: {_kisa(ifade, 40)} → {deger}")
    assert not yanlis, "yanlış varsayılan (120000 bekleniyor): " + repr(yanlis)


def test_ifade_degeri_aritmetigi_cozer():
    """Yardımcı testi: ifade çözümü çalışmazsa üstteki kilit sessizce boşalır."""
    assert _ifade_degeri("1800 * 1000") == 1_800_000
    assert _ifade_degeri("120_000") == 120_000
    assert _ifade_degeri("120*1000") == 120_000
    assert _ifade_degeri("bilinmeyen") is None


def test_timer_manager_sabiti_dogrudan_kullanir():
    """Yoklama QTimer'ı `config.DAMGA_KONTROL_MS`i doğrudan kurmalı; sessiz varsayılan olmamalı."""
    metin = (KIOSK / "core" / "timer_manager.py").read_text(encoding="utf-8")
    assert "tetik_timer.start(config.DAMGA_KONTROL_MS)" in metin
    assert 'getattr(config, "DAMGA_KONTROL_MS"' not in metin


def test_damga_yoklamasi_anlatilan_belgeler_iki_degeri_de_yazar():
    """Süre yazılan belgeler iki aralığı (120/30) birlikte anlatmalı — tek sayı yanıltıcı."""
    for ad in ("README.md", "NODET-DEGISIKLIGI.md", "KOMUTLAR.md"):
        metin = (KIOSK / ad).read_text(encoding="utf-8")
        if "DAMGA_KONTROL_MS" not in metin:
            continue
        assert "120 sn" in metin, ad
        assert "30 sn" in metin, ad


def test_komut_gecikmesi_dogru_anlatilir():
    """Komut yolu 10 turda bir çalışır: en çok 20 dk (push bağlı) / 5 dk (kopuk).

    i5 bulgusu: KOMUTLAR.md komut gecikmesini ~10 kat küçük gösteriyordu ("DAMGA_KONTROL_MS
    içinde") — panel `durum.json`a komut işareti YAZMIYOR, bu yüzden çapraz kontrol gerekir.
    """
    metin = (KIOSK / "KOMUTLAR.md").read_text(encoding="utf-8")
    assert "10 tur" in metin or "10 yoklama turunda" in metin
    assert "20 dakika" in metin
    assert "5 dakika" in metin


# --- menü adı / dosya adı ayrımı (kullanıcı geri bildirimi) ---------------------

def test_belgelerde_menude_gorunmeyen_dosya_adi_talimat_olarak_kullanilmaz():
    """Panelde menü adı 'Nöbet ve Yayınlar'; `VeriView` yalnız DOSYA adıdır.

    Kullanıcı geri bildirimi: talimatta "panelde VeriView'de" denince ekranda öyle bir şey
    bulunamıyor. Belgeler görünen menü adını kullanmalı; dosya adı geçecekse 'dosya:' demeli.
    """
    kok = Path(__file__).resolve().parents[2]
    yasak = ("VeriView →", "VeriView'de", "VeriView ekranında", "AyarlarView'de")
    kotu = []
    for md in list((kok / "docs").glob("*.md")) + [kok / "panel" / "README.md"]:
        if not md.exists():
            continue
        metin = md.read_text(encoding="utf-8")
        for kalip in yasak:
            if kalip in metin:
                kotu.append(f"{md.relative_to(kok)}: {kalip}")
    assert not kotu, f"talimatta menüde görünmeyen dosya adı kullanılmış: {kotu}"

    # panel/README bu kuralı açıkça yazmalı (yeni talimat yazan buraya bakar).
    pano = (kok / "panel" / "README.md").read_text(encoding="utf-8")
    assert "Nöbet ve Yayınlar" in pano and "dosya adları menüde görünmez" in pano


# --- komut çapraz kontrolü tetikleyici kapısından BAĞIMSIZ olmalı (i5 bulgusu) ----

def test_komut_capraz_kontrolu_tetik_kapisindan_once():
    """`tetik.aktif=false` olan cihazda da uzaktan komut çalışmalı.

    i5 bulgusu: `_komut_capraz_kontrol()` çağrısı `otomatik_acik("qt")` kapısının ARKASINDA
    olduğu için otomatik tetikleme kapalıysa uzaktan komut sessizce ölüyordu. Komut ayrı
    özellik: çağrı kapıdan ÖNCE olmalı.
    """
    yol = KIOSK / "pharmacy_app.py"
    kaynak = yol.read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    hedef = None
    for dugum in ast.walk(agac):
        if isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)) and dugum.name == "_durum_uygula":
            hedef = dugum
    assert hedef is not None, "_durum_uygula bulunamadı (yeniden adlandırıldı mı?)"

    satirlar = kaynak.splitlines()
    govde = "\n".join(satirlar[hedef.body[0].lineno - 1: hedef.end_lineno])
    cagri = govde.find("self._komut_capraz_kontrol()")
    kapi = govde.find('if not tetik_modulu.otomatik_acik("qt"):')
    assert cagri != -1, "_komut_capraz_kontrol çağrısı yok — uzaktan komut sessizce ölür"
    assert kapi != -1, "tetikleyici kapısı bulunamadı (kaynak değişti, testi güncelle)"
    assert cagri < kapi, "komut çapraz kontrolü yine tetikleyici kapısının arkasında (i5 bulgusu)"
