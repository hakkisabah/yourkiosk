"""Belgelerdeki yoklama süreleri KODDAN türetilmeli (i5 "ifade doğruluğu" sınıfı).

NEDEN: `DAMGA_KONTROL_MS` bir zamanlar 20 sn'ydi; 30/120 sn'ye çekildikten sonra README,
NODET-DEGISIKLIGI.md, KOMUTLAR.md ve iki araç docstring'i "20 sn" demeye devam etti. Kullanıcı
"bildirdim ama değişmedi" beklentisini bu yanlış metinden kuruyor.

Bu test SABİT KALIP ARAMAZ; iddiaları SINIFLANDIRIR (25 Ekim i3 bulguları sonrası yeniden yazıldı):

  · Kapsam: deponun TAMAMI (kiosk + web + panel + docs), `.md .py .ts .tsx .vue .sh .json …`.
    Eski sürüm yalnız `kiosk/` altını ve yalnız {.md,.py,.json,.sh} uzantılarını tarıyordu →
    `web/src`'teki bayat "20 sn" satırları hiç görülmüyordu (i3 bulgusu).
  · "20 sn"/"300 sn" her yerde yasak DEĞİL: maliyet karşılaştırması ve tarihsel ölçüm meşrudur.
    Yasak olan, bunları **bugünkü yoklama aralığı** gibi sunmak. Bu yüzden satır bağlamına bakılır
    (fiyat/≈/idi/eski…) ve istisnalar `MUAF` tablosunda GEREKÇESİYLE tutulur.
  · `push bağlı X sn / kopuk Y sn` ikilisi yapısal olarak denetlenir: 120/30 olmalı.
  · git yoksa (arşiv/tarball) tarama SESSİZCE tüm ağaca düşmez — açıkça `skip` eder. Eski sürüm
    düşüyordu ve gitignore'lu cihaz verisi (`ayarlar.json`) yüzünden yanlış kırmızı üretiyordu.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

import config

KIOSK = Path(__file__).resolve().parents[1]
KOK = KIOSK.parent  # depo kökü: kapsam kiosk ile sınırlı olamaz
ATLANAN = {".venv", ".qt-libs", "__pycache__", "_arsiv", ".karantina", "onbellek", "node_modules",
           "dist", ".pytest_cache", ".git", ".cache", "coverage"}
METIN_UZANTI = {".md", ".py", ".json", ".sh", ".ts", ".tsx", ".vue", ".yaml", ".yml",
                ".txt", ".css", ".html", ".conf", ".service", ".nft"}

#: Gerçek değerler (tek kaynak: kiosk/config.py). Metinler bunlarla çelişemez.
PUSH_SN = config.DAMGA_KONTROL_MS_PUSH // 1000
PUSH_YOK_SN = config.DAMGA_KONTROL_MS_PUSH_YOK // 1000

#: Bayat süre işaretleri. `120 sn` içindeki "20 sn" eşleşmesin diye önceki karakter rakam olamaz.
BAYAT_SN = re.compile(r"(?<!\d)20\s*sn\b", re.IGNORECASE)
BAYAT_MS = re.compile(r"(?<!\d)20000(?!\d)")
ESKI_SN = re.compile(r"(?<!\d)300\s*sn\b", re.IGNORECASE)
#: İkili iddia biçimi: "push bağlı 120 sn / kopuk 30 sn"
IKILI = re.compile(r"push\s*ba[ğg]l[ıi]\D{0,12}(\d+)\s*sn\D{0,20}kopuk\D{0,12}(\d+)\s*sn", re.IGNORECASE)
#: Tarihsel/ölçüm bağlamı: bunlar bayat iddia değil, karşılaştırmadır.
TARIH = re.compile(r"(\bidi\b|\bik[ie]n\b|önce|eski|tarihsel|karşılaştır|demekti|yerine|≈|\$|maliyet)",
                   re.IGNORECASE)

#: Kendi belgesi: eski değeri ANLATIR (20 sn), taranmaz.
KENDI = Path(__file__).resolve()

#: Gerekçeli istisnalar: (dosya, satır parçası) → neden bayat sayılmıyor.
MUAF: dict[tuple[str, str], str] = {
    ("README.md", "en çok 20 sn"): "tarayıcı uzun yoklamasının tetik gecikmesi (DAMGA değil)",
    ("kiosk/README.md", "**10 yoklama turunda bir**"): "komut çapraz kontrolü: 10 tur × 120 sn",
}


def _izlenen_dosyalar() -> set[Path]:
    """`git` varsa İZLENEN dosyalar; yoksa test SKIP edilir (sessiz tüm-ağaç taraması yok)."""
    cikti = None
    try:
        cikti = subprocess.run(
            ["git", "-C", str(KOK), "ls-files", "-z"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError) as hata:  # pragma: no cover - ortam arızası
        pytest.skip(f"git çalıştırılamadı ({hata}) → taranacak dosya kümesi bilinmiyor")
    if cikti is None:  # pragma: no cover - yukarıdaki skip zaten çıkardı
        pytest.skip("git çıktısı yok → tarama atlandı")
    if cikti.returncode != 0 or not cikti.stdout:
        pytest.skip("git deposu değil (arşiv/tarball) → izlenen dosya listesi yok; tarama atlandı")
    return {KOK / ad for ad in cikti.stdout.split("\0") if ad}


def _metinler() -> list[Path]:
    """Depodaki taranacak metin dosyaları (yalnız git'in izlediği, üretilen dizinler hariç)."""
    izlenen = _izlenen_dosyalar()
    dosyalar = [
        yol for yol in izlenen
        if yol.is_file() and yol.suffix in METIN_UZANTI
        and not any(parca in ATLANAN for parca in yol.parts)
    ]
    assert len(dosyalar) > 70, f"tarama beklenenden az dosya buldu ({len(dosyalar)}) — kapsam daralmış"
    return sorted(dosyalar)


def _kisa(satir: str, sinir: int = 160) -> str:
    """Assertion mesajını kısalt: taranan dosya cihaz verisi olsa bile gövde sızmasın."""
    temiz = " ".join(satir.split())
    return temiz if len(temiz) <= sinir else temiz[:sinir] + "…"


def _muaf(yol: Path, satir: str) -> bool:
    ad = str(yol.relative_to(KOK))
    return any(ad == dosya and parca in satir for dosya, parca in MUAF)


def _satir_iddiasi(satir: str) -> bool:
    """Satır BUGÜNKÜ yoklama aralığından söz ediyor mu? (tarihsel/ölçüm bağlamı hariç)"""
    if TARIH.search(satir):
        return False
    kucuk = satir.lower()
    return ("yoklama" in kucuk) or ("damga" in kucuk) or ("damga_kontrol_ms" in kucuk)


def test_damga_araligi_iki_degerli_kalir():
    """Sabitler: push bağlı 120 sn, kopuk 30 sn (etkin aralık bağlantıya göre seçilir)."""
    assert config.DAMGA_KONTROL_MS_PUSH == 120 * 1000
    assert config.DAMGA_KONTROL_MS_PUSH_YOK == 30 * 1000
    assert config.DAMGA_KONTROL_MS == 120 * 1000


def test_tarama_kapsami_web_ve_kok_belgelerini_gorur():
    """Kapsam kilidi: .ts/.tsx ve depo kökü belgeleri taranmalı (i3 bulgusu: hiç bakılmıyordu)."""
    adlar = {str(y.relative_to(KOK)) for y in _metinler()}
    assert any(a.endswith(".ts") for a in adlar), "hiç .ts dosyası taranmıyor (süzgeç daralmış)"
    assert any(a.endswith(".tsx") or a.endswith(".vue") for a in adlar)
    assert "docs/ONBELLEK-VE-MALIYET.md" in adlar, "depo kökü belgeleri taranmıyor"
    assert "web/src/kiosk.ts" in adlar


def test_hicbir_metinde_bayat_yoklama_iddiasi_yok():
    """Bugünkü aralık iddiası 120/30 olmalı; 20 sn/300 sn yalnız tarihsel bağlamda geçebilir."""
    kacak: list[str] = []
    kullanilan: set[tuple[str, str]] = set()
    for yol in _metinler():
        if yol == KENDI:
            continue
        icerik = yol.read_text(encoding="utf-8", errors="replace")
        # KOD dosyasında "her 20/300 sn" iddia değildir: zaman aşımı, bekleme, gecikme sabitleri
        # (ör. chromium `300 sn zaman aşımı`) meşrudur. Bu yüzden kod kuralı yalnız yoklama
        # zincirindeki dosyalara uygulanır: içinde `DAMGA_KONTROL_MS` geçenler.
        yoklama_zinciri = "DAMGA_KONTROL_MS" in icerik
        for no, satir in enumerate(icerik.splitlines(), 1):
            if _muaf(yol, satir):
                kullanilan.update(k for k in MUAF if k[0] == str(yol.relative_to(KOK)) and k[1] in satir)
                continue
            ikili = IKILI.search(satir)
            if ikili and (int(ikili.group(1)) != PUSH_SN or int(ikili.group(2)) != PUSH_YOK_SN):
                kacak.append(f"{yol.relative_to(KOK)}:{no}: ikili {ikili.group(0)!r} ≠ "
                             f"{PUSH_SN}/{PUSH_YOK_SN} — {_kisa(satir)}")
                continue
            kucuk = satir.lower()
            # 20 sn TARAYICI tetik yoklaması için DOĞRU (`config.TETIK_KONTROL_MS`), DAMGA için
            # değil. Eski sürüm satırda yalnız "tetik" geçmesini TAM MUAFİYET sayıyordu → 26 Ekim
            # i5 bulgusu: SIRADAKI-ISLER.md'deki üç bayat "20 sn" satırı bu kaçış yüzünden yeşil
            # kalıyordu. Artık muafiyet AÇIK kanıt ister: sabitin adı ya da uzun yoklama ucu.
            if "TETIK_KONTROL_MS" in satir or "/degisiklik" in kucuk:
                continue
            if yol.suffix not in {".md", ".txt"}:
                if not yoklama_zinciri:
                    continue
                # KOD/BETİK dosyalarında ("sn" yazıyorsa) iddia sayılır: i3 bulgusu, "# 20 sn yeterli
                # olurdu" gibi anahtar kelimesiz satır eski sürümde yeşil kalıyordu. Ham `20000`
                # sayısı bu kurala girmez (koltuk sınırları, bayt uzunlukları — iddia değil).
                if (BAYAT_SN.search(satir) or ESKI_SN.search(satir)) and not TARIH.search(satir):
                    kacak.append(f"{yol.relative_to(KOK)}:{no}: bayat süre (kod/belge) — {_kisa(satir)}")
                continue
            if not _satir_iddiasi(satir):
                continue
            if BAYAT_SN.search(satir) or BAYAT_MS.search(satir):
                kacak.append(f"{yol.relative_to(KOK)}:{no}: bayat 20 sn — {_kisa(satir)}")
            elif ESKI_SN.search(satir):
                kacak.append(f"{yol.relative_to(KOK)}:{no}: bayat 300 sn — {_kisa(satir)}")
    assert not kacak, "bayat yoklama süresi iddiası (120/30 bekleniyor):\n" + "\n".join(kacak)

    olu = set(MUAF) - kullanilan
    assert not olu, f"MUAF kayıtları artık eşleşmiyor (silinmeli): {sorted(olu)}"


def _getattr_varsayilanlari(satir: str) -> list[str]:
    """`getattr(config, "DAMGA_KONTROL_MS", <ifade>)` içindeki <ifade>'yi PARANTEZ DENGELEYEREK al.

    i3 bulgusu: eski `([^)]+?)` deseni iç içe ifadede (`int(ayar)`) yanlış pozitif üretiyor ve
    DOĞRU kodu kırmızıya düşürüyordu.
    """
    cikti: list[str] = []
    for bul in re.finditer(r'getattr\(\s*config\s*,\s*"DAMGA_KONTROL_MS"\s*,', satir):
        derinlik, basla, i = 1, bul.end(), bul.end()
        while i < len(satir):
            if satir[i] == "(":
                derinlik += 1
            elif satir[i] == ")":
                derinlik -= 1
                if derinlik == 0:
                    cikti.append(satir[basla:i].strip())
                    break
            i += 1
    return cikti


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
    yanlis: list[str] = []
    for yol in _metinler():
        if yol.suffix != ".py" or yol == KENDI:
            continue  # KENDİ dosyası atlanır: docstring'ler örnek biçim anlatır.
        for no, satir in enumerate(yol.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for ifade in _getattr_varsayilanlari(satir):
                deger = _ifade_degeri(ifade)
                if deger != 120_000:
                    yanlis.append(f"{yol.relative_to(KOK)}:{no}: {_kisa(ifade, 40)} → {deger}")
    assert not yanlis, "yanlış varsayılan (120000 bekleniyor): " + repr(yanlis)


def test_getattr_cozumleyici_ic_ice_ifadeyi_dogru_okur():
    """Yardımcı testi: sınır çözümü bozulursa üstteki kilit sessizce yanlış kırmızı üretir."""
    assert _getattr_varsayilanlari('x = getattr(config, "DAMGA_KONTROL_MS", 120_000)') == ["120_000"]
    assert _getattr_varsayilanlari('y = getattr(config, "DAMGA_KONTROL_MS", int(ayar))') == ["int(ayar)"]
    assert _getattr_varsayilanlari('getattr(config, "DAMGA_KONTROL_MS", 1800 * 1000)') == ["1800 * 1000"]


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
    yasak = ("VeriView →", "VeriView'de", "VeriView ekranında", "AyarlarView'de")
    kotu = []
    for md in list((KOK / "docs").glob("*.md")) + [KOK / "panel" / "README.md"]:
        if not md.exists():
            continue
        metin = md.read_text(encoding="utf-8")
        for kalip in yasak:
            if kalip in metin:
                kotu.append(f"{md.relative_to(KOK)}: {kalip}")
    assert not kotu, f"talimatta menüde görünmeyen dosya adı kullanılmış: {kotu}"

    # panel/README bu kuralı açıkça yazmalı (yeni talimat yazan buraya bakar).
    pano = (KOK / "panel" / "README.md").read_text(encoding="utf-8")
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
