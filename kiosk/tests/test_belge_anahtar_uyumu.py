"""Belgelerdeki AYAR ANAHTARI ve dosya adı iddiaları kodla uyuşmalı (26 Ekim i5 bulgusu).

NEDEN: `docs/AWS-KURULUM.md` "Yoklama sıklığı `kiosk/ayarlar.json` → `TETIK_ARALIK_SN` ile
düşürülebilir" diyordu; kodda `TETIK_ARALIK_SN` diye bir anahtar YOK (`grep` yalnız o belgeyi
buluyordu). Aynı sınıf: `web/src/kiosk.ts` yorumu tarayıcı modunun `durum.json` okuduğunu
söylüyordu — tarayıcı `durum.json`u hiç istemez (`web/src/veri/kaynak.ts` yalnız
`lastupdate.json` + `tetikle.json` çeker), o tek isteklik yol Qt moduna aittir.

İki kilit:
  1. `ayarlar.json` → `<ANAHTAR>` iddiasındaki anahtar `kiosk/config.py`de tanımlı olmalı;
     `grup.anahtar` biçimi `kiosk/ayarlar.py` ayar tablosunda bulunmalı.
  2. `web/src` altında `durum.json` KOD olarak (tırnak içinde) hiç geçmemeli — yalnız yorum
     olarak geçebilir.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

KIOSK = Path(__file__).resolve().parents[1]
KOK = KIOSK.parent
KENDI = Path(__file__).resolve()

#: "ayarlar.json" → `ANAHTAR`  (markdown kalınlığı ve ara sözcükler serbest)
ANAHTAR_IDDIASI = re.compile(r"ayarlar\.json`?[^\n]{0,60}?`([A-Z][A-Z0-9_]{2,})`")
#: "ayarlar.json" → `grup.anahtar`
GRUP_IDDIASI = re.compile(r"ayarlar\.json`?[^\n]{0,60}?`([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)`")

TARANAN = {".md", ".py", ".ts", ".tsx", ".vue", ".sh"}
ATLA = {"node_modules", ".venv", "dist", ".git", "__pycache__", "_arsiv", ".qt-libs"}


def _config_adlari() -> set[str]:
    """`config.py`de modül düzeyinde tanımlı adlar."""
    agac = ast.parse((KIOSK / "config.py").read_text(encoding="utf-8"))
    adlar: set[str] = set()
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign):
            for hedef in dugum.targets:
                if isinstance(hedef, ast.Name):
                    adlar.add(hedef.id)
        elif isinstance(dugum, ast.AnnAssign) and isinstance(dugum.target, ast.Name):
            adlar.add(dugum.target.id)
    return adlar


def _ayar_tablosu() -> set[tuple[str, str]]:
    """`ayarlar.py` AYARLAR tablosundaki (grup, anahtar) çiftleri."""
    metin = (KIOSK / "ayarlar.py").read_text(encoding="utf-8")
    return set(re.findall(r"\(\s*\"([a-z_]+)\"\s*,\s*\"([a-z_0-9]+)\"\s*\)", metin))


def _dosyalar() -> list[Path]:
    """Taranacak dosyalar = **depoya izlenen** dosyalar (`git ls-files`).

    26 Ekim i5 bulgusu: `KOK.rglob("*")` tüm çalışma ağacını geziyordu → cihaz verisi
    (`lastSystemData.json`, `onbellek/`), `.karantina/`, `.cache/` gibi makineye özgü klasörler de
    taranıyor; bu test cihazda anlamsız kırılmalar üretebiliyor ve tarama yavaştı. Depoya izlenen
    dosya listesi hem `.gitignore`'u kendiliğinden uygular hem de "belge ↔ kod" iddiasının konusu
    olan kümeyle birebir örtüşür.
    """
    sonuc = subprocess.run(["git", "-C", str(KOK), "ls-files", "-z"],
                           capture_output=True, check=True, timeout=120)
    cikti = []
    for ad in sonuc.stdout.decode("utf-8", errors="replace").split("\0"):
        if not ad:
            continue
        yol = KOK / ad
        if yol.suffix not in TARANAN or yol == KENDI:
            continue
        if any(parca in ATLA for parca in Path(ad).parts):
            continue
        cikti.append(yol)
    return cikti


def test_ayarlar_json_anahtarlari_kodda_var() -> None:
    config_adlari = _config_adlari()
    tablo = _ayar_tablosu()
    assert config_adlari and tablo, "kaynak tabloları okunamadı — test körleşti"
    gruplar = {grup for grup, _ in tablo}

    kacak: list[str] = []
    for yol in _dosyalar():
        metin = yol.read_text(encoding="utf-8", errors="replace")
        if "ayarlar.json" not in metin:
            continue
        goreli = yol.relative_to(KOK)
        for no, satir in enumerate(metin.splitlines(), 1):
            if "ayarlar.json" not in satir:
                continue
            for ad in ANAHTAR_IDDIASI.findall(satir):
                if ad not in config_adlari:
                    kacak.append(f"{goreli}:{no}: `{ad}` config.py'de YOK — {satir.strip()[:110]}")
            for grup, anahtar in GRUP_IDDIASI.findall(satir):
                if grup not in gruplar:
                    continue  # `sablon.json`, `logo.png` gibi DOSYA adları ayar anahtarı değil
                if (grup, anahtar) not in tablo:
                    kacak.append(f"{goreli}:{no}: `{grup}.{anahtar}` ayarlar.py tablosunda YOK — "
                                 f"{satir.strip()[:110]}")
    assert not kacak, "belgede olmayan ayar anahtarı:\n" + "\n".join(kacak)


def test_anahtar_iddiasi_kapisi_kendini_denetler() -> None:
    """Kapı gerçekten yakalıyor mu? (i5'in bulduğu satır kırmızı, doğrusu yeşil)"""
    config_adlari = _config_adlari()
    eski = "Yoklama sıklığı `kiosk/ayarlar.json` → `TETIK_ARALIK_SN` ile düşürülebilir."
    yeni = "Yoklama sıklığı `kiosk/ayarlar.json` → `calistirma.degisiklik_kontrol_ms` ile ayarlanır"
    assert [a for a in ANAHTAR_IDDIASI.findall(eski) if a not in config_adlari] == ["TETIK_ARALIK_SN"]
    assert [a for a in ANAHTAR_IDDIASI.findall(yeni) if a not in config_adlari] == []
    assert ("calistirma", "degisiklik_kontrol_ms") in _ayar_tablosu()


def test_tarayici_modu_durum_json_okumaz() -> None:
    """`durum.json` tek isteklik Qt yoludur; tarayıcı modunda KOD olarak geçemez.

    Yorumda adı geçebilir (bu PR'da tam olarak bunu açıklıyor); yasak olan bir istek/yol
    olarak kullanılması: tırnak içinde `durum.json`.
    """
    kotu: list[str] = []
    for yol in (KOK / "web" / "src").rglob("*"):
        if not yol.is_file() or yol.suffix not in {".ts", ".tsx", ".js"}:
            continue
        for no, satir in enumerate(yol.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"['\"]durum\.json['\"]", satir) or re.search(r"[/$]\{?[^`\n]{0,20}durum\.json", satir):
                kotu.append(f"{yol.relative_to(KOK)}:{no}: {satir.strip()[:110]}")
    assert not kotu, ("tarayıcı modu `durum.json` istiyor görünüyor (Qt yolu ile karışmış):\n"
                      + "\n".join(kotu))
