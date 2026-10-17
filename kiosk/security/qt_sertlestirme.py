"""Qt kütüphane ve eklenti sertleştirmesi (geri alınabilir karantina).

NEDEN
-----
PyQt6 tekerleği Qt'nin **tamamını** getirir: 96 Qt kütüphanesi, ~30 eklenti dizini,
19 MB QML modülü. Uygulama bunun çok küçük bir parçasını kullanır
(QtCore/QtGui/QtWidgets + xcb platform eklentisi + PNG/JPEG/WEBP çözücüleri).
Geri kalan her şey **saldırı yüzeyidir** ve 2026'da açıklanan yüksek önemli Qt
açıkları tam da kullanılmayan bu parçalarda:

  * CVE-2026-6210  Qt SVG marker type-confusion (6.11.1+)
  * CVE-2026-78253 QXmlStreamReader özyineleme (6.11.2)
  * CVE-2026-79616 Qt Quick SVG yolu (6.11.2)
  * CVE-2026-79680 Qt **VNC** platform eklentisi parola atlatma (6.11.3)
    → PyPI tekerleği 6.11.2'de duruyor ve PyPI'da 6.11.3 **yok**; bu yüzden
      düzeltme sürümüne geçilemediği sürece eklenti **kaldırılır**.

YÖNTEM (kanıta dayalı, geri alınabilir)
---------------------------------------
1. Tutulacaklar açıkça listelenir (platform eklentileri, görsel çözücüler,
   PyQt6 Python modülleri).
2. Tutulan dosyaların **ldd ile gerçek bağımlılık kapanışı** hesaplanır: yalnızca
   gerçekten bağlı Qt kütüphaneleri kalır.
3. Geri kalan her şey silinmez; `kiosk/.karantina/` altına taşınır
   (qt-eklentileri/, qt-kutuphaneleri/, pyqt6-modulleri/, qt-qml/).
4. Aynı işlem tekrar çalıştırılabilir (idempotent); izin hatası uygulamayı durdurmaz.

Geri alma: `.karantina/<dizin>/*` dosyalarını geldiği yere kopyala.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("kiosk.qt_guvenlik")

# ---------------------------------------------------------------- tutulanlar
#: Kullanılan platform eklentileri (xcb = X11, offscreen = test, wayland = Wayland cihazları,
#: minimal = son çare). Kaldırılanlar: vnc (CVE-2026-79680), eglfs/linuxfb/vkkhrdisplay/minimalegl
#: (gömülü/kiosk çerçeve arabelleği yolları — bu uygulama pencere sistemi kullanıyor).
KORUNAN_PLATFORMLAR = {"libqxcb.so", "libqoffscreen.so", "libqminimal.so", "libqwayland.so"}
#: Kullanılan görsel çözücüler (politikanın beyaz listesi: PNG çekirdekte, JPEG/WEBP/ICO eklenti)
KORUNAN_GORSEL_EKLENTILERI = {"libqjpeg.so", "libqwebp.so", "libqico.so"}
#: Wayland platformunun ihtiyaç duyduğu alt eklenti dizinleri
#: (wayland-decoration-client **alınmaz**: çerçevesiz/tam ekran kiosk'ta pencere dekorasyonu
#:  gereksizdir ve `libadwaita.so` üzerinden `libQt6Svg`'yi de çekiyordu)
KORUNAN_EKLENTI_DIZINLERI = {
    "wayland-graphics-integration-client",
    "wayland-shell-integration",
}
#: PyQt6 Python modülleri: yalnızca kullanılanlar kalır
#: (QtTest: pytest-qt test altyapısı — üretimde kullanılmaz ama testlerde gerekir)
KORUNAN_PYQT_MODULLERI = {"QtCore", "QtGui", "QtWidgets", "QtDBus", "QtTest", "sip"}
#: Açıkça korunacak Qt kütüphaneleri (ldd kapanışına ek olarak; platform/çekirdek)
KORUNAN_QT_KUTUPHANELERI = {
    "libQt6Core.so.6",
    "libQt6Gui.so.6",
    "libQt6Widgets.so.6",
    "libQt6DBus.so.6",
    "libQt6XcbQpa.so.6",  # xcb platform arka ucu
    "libQt6Test.so.6",  # pytest-qt test altyapısı (üretimde kullanılmaz)
    "libQt6WaylandClient.so.6",
    "libQt6WlShellIntegration.so.6",
}

#: Karantinaya alınacak eklenti dizinleri (kullanılmıyor)
KARANTINA_EKLENTI_DIZINLERI = {
    "assetimporters",
    "egldeviceintegrations",
    "generic",
    "geometryloaders",
    "help",
    "multimedia",
    "networkinformation",
    "platforminputcontexts",
    "platformthemes",
    "position",
    "printsupport",
    "qmllint",
    "qmlls",
    "renderers",
    "renderplugins",
    "sceneparsers",
    "scxmldatamodel",
    "sensors",
    "sqldrivers",
    "texttospeech",
    "tls",
    "wayland-decoration-client",
    "webview",
    "xcbglintegrations",
}
#: Karantinaya alınacak görsel biçim eklentileri (riskli/kompleks çözücüler)
KARANTINA_GORSEL = {
    "libqsvg.so",
    "libqpdf.so",
    "libqtiff.so",
    "libqgif.so",
    "libqicns.so",
    "libqtga.so",
    "libqwbmp.so",
}
#: Karantinaya alınacak ikon motoru (SVG ikon çözücü)
KARANTINA_IKON = {"libqsvgicon.so"}

KARANTINA_EKLENTI = "qt-eklentileri"
KARANTINA_KUTUPHANE = "qt-kutuphaneleri"
KARANTINA_MODUL = "pyqt6-modulleri"
KARANTINA_QML = "qt-qml"


# ------------------------------------------------------------------- yardımcı
def _kok(kok: Path | None) -> Path:
    return Path(kok) if kok else Path(__file__).resolve().parent.parent


def pyqt_dizini(kok: Path | None = None) -> Path | None:
    """venv içindeki PyQt6 kurulum dizini."""
    kok = _kok(kok)
    for aday in sorted(kok.glob(".venv/lib/python*/site-packages/PyQt6")):
        if aday.is_dir():
            return aday
    return None


def eklenti_dizinleri(kok: Path | None = None) -> list[Path]:
    """Qt eklenti dizinleri (venv + proje içi aşamalama)."""
    kok = _kok(kok)
    bulunan: list[Path] = []
    pyqt = pyqt_dizini(kok)
    if pyqt and (pyqt / "Qt6/plugins").is_dir():
        bulunan.append(pyqt / "Qt6/plugins")
    if (kok / ".qt-libs/plugins").is_dir():
        bulunan.append(kok / ".qt-libs/plugins")
    return bulunan


def karantina_dizini(ad: str, kok: Path | None = None) -> Path:
    hedef = _kok(kok) / ".karantina" / ad
    hedef.mkdir(parents=True, exist_ok=True)
    return hedef


def _tasi(kaynak: Path, hedef_dizin: Path, *, tasinan: list[str],
          etiket: str | None = None, kok: Path | None = None) -> bool:
    """Dosya/dizini karantinaya taşır (idempotent, hataya dayanıklı)."""
    if not kaynak.exists():
        return False
    hedef = hedef_dizin / (etiket or kaynak.name)
    if hedef.exists():  # daha önce taşınmış
        return False
    hedef.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(kaynak), str(hedef))
    except OSError as hata:
        log.warning("karantinaya alınamadı (%s): %s", kaynak, hata)
        return False
    try:
        tasinan.append(str(hedef.relative_to(_kok(kok)).as_posix()))
    except ValueError:  # kök dışı (test amaçlı geçici dizin)
        tasinan.append(str(hedef))
    return True


# ----------------------------------------------------------- kütüphane kapanışı
def _basvurulan_dosyalar(kok: Path | None = None) -> set[str]:
    """Tutulan dosyaların (ldd) başvurduğu TÜM dosya adları (Qt dışı dâhil)."""
    kok = _kok(kok)
    pyqt = pyqt_dizini(kok)
    if pyqt is None:
        return set(KORUNAN_QT_KUTUPHANELERI)
    qt_lib = pyqt / "Qt6/lib"

    hedefler: list[Path] = []
    for ad in ("QtCore", "QtGui", "QtWidgets", "QtDBus"):
        hedefler.extend(pyqt.glob(f"{ad}*.so"))
    for dizin in eklenti_dizinleri(kok):
        for alt, izinli in (
            ("platforms", KORUNAN_PLATFORMLAR),
            ("imageformats", KORUNAN_GORSEL_EKLENTILERI),
        ):
            alt_dizin = dizin / alt
            if alt_dizin.is_dir():
                hedefler.extend(d for d in alt_dizin.glob("*.so") if d.name in izinli)
        for alt in KORUNAN_EKLENTI_DIZINLERI:
            hedefler.extend((dizin / alt).glob("*.so"))

    import os

    ortam = dict(os.environ, LD_LIBRARY_PATH=str(qt_lib))
    basvurulan: set[str] = set()
    kuyruk = [str(h) for h in hedefler if h.exists()]
    gorulen: set[str] = set()
    while kuyruk:
        dosya = kuyruk.pop()
        if dosya in gorulen:
            continue
        gorulen.add(dosya)
        try:
            cikti = subprocess.run(
                ["ldd", dosya], capture_output=True, text=True, timeout=30, env=ortam
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for satir in cikti.splitlines():
            parca = satir.split("=>")[-1].strip().split(" ")[0]
            if not parca.startswith("/"):
                continue
            basvurulan.add(Path(parca).name)
            if parca not in gorulen:
                kuyruk.append(parca)
    return basvurulan


def gerekli_kutuphaneler(kok: Path | None = None) -> set[str]:
    """Tutulan dosyaların ihtiyaç duyduğu Qt kütüphaneleri (kanıta dayalı kapanış)."""
    return {ad for ad in _basvurulan_dosyalar(kok) if ad.startswith("libQt6")} | set(
        KORUNAN_QT_KUTUPHANELERI
    )


# ------------------------------------------------------------------- karantina
def eklentileri_karantinaya_al(kok: Path | None = None, *, etkin: bool = True) -> list[str]:
    """Kullanılmayan/riskli Qt eklentilerini karantinaya taşır."""
    if not etkin:
        return []
    hedef_dizin = karantina_dizini(KARANTINA_EKLENTI, kok)
    tasinan: list[str] = []
    for dizin in eklenti_dizinleri(kok):
        # 1) tamamen kaldırılacak eklenti dizinleri
        for alt in sorted(KARANTINA_EKLENTI_DIZINLERI):
            _tasi(dizin / alt, hedef_dizin, tasinan=tasinan, kok=kok)
        # 2) seçili dosyalar (görsel çözücüler, ikon motoru, platformlar)
        for alt, hedefler in (
            ("imageformats", KARANTINA_GORSEL),
            ("iconengines", KARANTINA_IKON),
        ):
            for ad in sorted(hedefler):
                _tasi(dizin / alt / ad, hedef_dizin, tasinan=tasinan, etiket=f"{alt}/{ad}", kok=kok)
        # 3) korunmayan platform eklentileri
        plat = dizin / "platforms"
        if plat.is_dir():
            for dosya in sorted(plat.glob("*.so")):
                if dosya.name not in KORUNAN_PLATFORMLAR:
                    _tasi(dosya, hedef_dizin, tasinan=tasinan, etiket=f"platforms/{dosya.name}", kok=kok)
    if tasinan:
        log.warning("Qt eklentileri karantinaya alındı (%d): %s", len(tasinan), ", ".join(tasinan))
    return tasinan


def modulleri_karantinaya_al(kok: Path | None = None, *, etkin: bool = True) -> list[str]:
    """Kullanılmayan Qt kütüphanelerini, PyQt6 modüllerini ve QML dizinini karantinaya taşır."""
    if not etkin:
        return []
    kok = _kok(kok)
    pyqt = pyqt_dizini(kok)
    if pyqt is None:
        return []
    tasinan: list[str] = []

    gerekli = gerekli_kutuphaneler(kok)
    lib_dizin = pyqt / "Qt6/lib"
    kitap_hedef = karantina_dizini(KARANTINA_KUTUPHANE, kok)
    for dosya in sorted(lib_dizin.glob("libQt6*.so.6")):
        if dosya.name not in gerekli:
            _tasi(dosya, kitap_hedef, tasinan=tasinan, kok=kok)

    # eski sürüm kalıntıları (libQt6*.so.6.11.2 gibi) — Qt6 dışı kütüphanelere dokunulmaz
    for desen in ("libQt6*.so.6.*", "libQt6*.so"):
        for dosya in sorted(lib_dizin.glob(desen)):
            if dosya.name.split(".so")[0] + ".so.6" not in gerekli:
                _tasi(dosya, kitap_hedef, tasinan=tasinan, kok=kok)

    # yetim kütüphaneler: korunan dosyalardan HİÇBİRİ bağvurmuyorsa (ör. QtMultimedia'nın
    # getirdiği libav*/libicu*/FFmpegStub) karantinaya alınır
    basvurulan = _basvurulan_dosyalar(kok)
    for dosya in sorted(lib_dizin.glob("*.so*")):
        if dosya.name in basvurulan or dosya.name.split(".so")[0] + ".so.6" in gerekli:
            continue
        if dosya.name.startswith("libQt6") and dosya.name.endswith(".so.6"):
            continue  # yukarıdaki Qt döngüsünde işlendi
        _tasi(dosya, kitap_hedef, tasinan=tasinan, kok=kok)

    modul_hedef = karantina_dizini(KARANTINA_MODUL, kok)
    for dosya in sorted(pyqt.glob("*.so")):
        ad = dosya.name.split(".")[0]
        if ad not in KORUNAN_PYQT_MODULLERI:
            _tasi(dosya, modul_hedef, tasinan=tasinan, kok=kok)

    if (pyqt / "Qt6/qml").is_dir():
        _tasi(pyqt / "Qt6/qml", karantina_dizini(KARANTINA_QML, kok), tasinan=tasinan, kok=kok)

    if tasinan:
        log.warning("Qt modülleri karantinaya alındı (%d): %s", len(tasinan), ", ".join(tasinan))
    return tasinan


def karantinaya_al(kok: Path | None = None, *, etkin: bool = True, modul: bool = True) -> list[str]:
    """Eklenti (+ istenirse modül) karantinasını uygular."""
    if not etkin:
        return []
    tasinan = eklentileri_karantinaya_al(kok, etkin=True)
    if modul:
        tasinan += modulleri_karantinaya_al(kok, etkin=True)
    return tasinan


# ----------------------------------------------------------------------- durum
def durum(kok: Path | None = None) -> dict:
    """Karantina durumu: riskli eklenti/kütüphane/modül kaldı mı?"""
    kok = _kok(kok)
    pyqt = pyqt_dizini(kok)
    riskli_eklenti: list[str] = []
    for dizin in eklenti_dizinleri(kok):
        for alt, hedefler in (
            ("imageformats", KARANTINA_GORSEL),
            ("iconengines", KARANTINA_IKON),
        ):
            riskli_eklenti.extend(f"{alt}/{a}" for a in sorted(hedefler) if (dizin / alt / a).exists())
        plat = dizin / "platforms"
        if plat.is_dir():
            riskli_eklenti.extend(
                f"platforms/{p.name}" for p in sorted(plat.glob("*.so")) if p.name not in KORUNAN_PLATFORMLAR
            )
        riskli_eklenti.extend(
            alt for alt in sorted(KARANTINA_EKLENTI_DIZINLERI) if (dizin / alt).is_dir()
        )

    riskli_modul: list[str] = []
    if pyqt is not None:
        gerekli = gerekli_kutuphaneler(kok)
        basvurulan = _basvurulan_dosyalar(kok)
        lib_dizin = pyqt / "Qt6/lib"
        riskli_modul = [p.name for p in sorted(lib_dizin.glob("libQt6*.so.6")) if p.name not in gerekli]
        riskli_modul += [
            p.name
            for p in sorted(lib_dizin.glob("*.so*"))
            if p.name not in basvurulan
            and not (p.name.startswith("libQt6") and p.name.endswith(".so.6"))
        ]
        riskli_modul += [
            p.name for p in sorted(pyqt.glob("*.so")) if p.name.split(".")[0] not in KORUNAN_PYQT_MODULLERI
        ]
        if (pyqt / "Qt6/qml").is_dir():
            riskli_modul.append("Qt6/qml")

    return {
        "eklenti_dizini": [str(d) for d in eklenti_dizinleri(kok)],
        "riskli_eklenti": riskli_eklenti,
        "riskli_modul": riskli_modul,
        # geriye uyum (denetim raporu)
        "riskli": riskli_eklenti,
    }


def ortam_sertlestir(ortam: dict | None = None) -> dict:
    """Qt yüklenmeden ÖNCE güvenli ortam varsayılanları (verilmişse üzerine yazmaz)."""
    import os

    ortam = ortam if ortam is not None else os.environ
    ayarlanan: dict[str, str] = {}
    # Eklenti dizini sabitlenir: CWD ya da kullanıcı dizininden eklenti yüklenmesin
    if not ortam.get("QT_PLUGIN_PATH"):
        eklenti = [str(d) for d in eklenti_dizinleri()]
        if eklenti:
            ortam["QT_PLUGIN_PATH"] = ":".join(eklenti)
            ayarlanan["QT_PLUGIN_PATH"] = ortam["QT_PLUGIN_PATH"]
    ortam.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
    return ayarlanan
