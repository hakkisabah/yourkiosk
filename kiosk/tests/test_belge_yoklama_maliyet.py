"""Yoklama süresi/maliyet belgeleri KODLA aynı olmalı (i5 "ifade doğruluğu" sınıfı).

NEDEN: `docs/GORSEL-MIMARISI.md` §8.3 uzun süre yoklama sürelerini koddan kopuk yazıyordu
(MQTT bağlıyken kodun katları mertebesinde büyük, kopukken onlarca kat büyük değerler); kod ise
`DAMGA_KONTROL_MS_PUSH`=120 sn ve `DAMGA_KONTROL_MS_PUSH_YOK`=30 sn.
Belge 600 cihaz maliyetini ~$1/ay gösterirken gerçek tablo ~$15-60/ay'dı. Bu sınıf hata
(elle yazılmış süre/maliyet tablosu koddan kopuyor) yalnız metin düzeltmeyle kapanmaz:
aşağıdaki test değerleri KODDAN okur, belgedeki tabloyla karşılaştırır.

27 Ekim i5 bulgusu (maliyet tabanı): tablolar "1 istek/cihaz/tur" ile kurulmuştu; Qt yolunda her
10 turda bir 3 ek istek var (`durum.json` her turda + `lastupdate.json` + `tetikle.json` +
`komut.json`) → 10 tur = 13 istek, yani tur başına 1,3. Tablolar bu çarpanla yeniden üretildi ve
`test_tablo_istek_sayilari_koddan_turetilir` ile kilitlendi. Ayrıca tarayıcı turu `durum.json`u
HİÇ istemez; dipnot bunu yanlış yazıyordu.

Kural: bir süre/maliyet tablosu belgeye elle yazılıyorsa, testi koddan türetilir.
"""

from __future__ import annotations

import re
from pathlib import Path

KIOSK = Path(__file__).resolve().parents[1]
KOK = KIOSK.parent
BELGE = KOK / "docs" / "GORSEL-MIMARISI.md"
MALIYET_BELGESI = KOK / "docs" / "ONBELLEK-VE-MALIYET.md"
AY = 30.44          # ortalama ay (gün)
CIHAZ = 600
CLOUDFRONT_M = 0.75  # $/milyon istek ($0,0075/10k)
S3_M = 0.40          # $/milyon istek ($0,0004/1k)


def _config_sabit(ad: str) -> int:
    """`kiosk/config.py` içinden sabit değeri oku (import etmeden: Qt bağımlılığı yok)."""
    kaynak = (KIOSK / "config.py").read_text(encoding="utf-8")
    m = re.search(rf"^{ad}\s*=\s*(\d+)\s*\*\s*1000\s*$", kaynak, re.MULTILINE)
    assert m, f"{ad} config.py içinde '<sayı> * 1000' biçiminde bulunamadı"
    return int(m.group(1))


def _blok(kaynak: str, baslik: str) -> str:
    """`if <baslik>:` satırından sonraki, girintisi düşene kadar olan blok."""
    satirlar = kaynak.splitlines()
    basla = next(i for i, s in enumerate(satirlar) if baslik in s)
    girinti = len(satirlar[basla]) - len(satirlar[basla].lstrip())
    cikti = []
    for satir in satirlar[basla + 1:]:
        if satir.strip() and (len(satir) - len(satir.lstrip())) <= girinti:
            break
        cikti.append(satir)
    return "\n".join(cikti)


def _istek_turu() -> float:
    """Qt yolunda tur başına istek sayısı — `pharmacy_app.py`ten TÜRETİLİR.

    10 tur boyunca: her turda 1 `durum.json` (taban) + son turda `_durum_tur % 10` bloğunun
    indirmeleri (`lastupdate.json`, `tetikle.json`) + `_komut_tur % 10` bloğunun indirmesi
    (`komut.json`) → (10 + 3) / 10 = 1,3.
    """
    kaynak = (KIOSK / "pharmacy_app.py").read_text(encoding="utf-8")
    assert "belge = durum_modulu.getir()" in kaynak, "tur başına durum.json indirmesi kalkmış"
    durum_blok = _blok(kaynak, "if self._durum_tur % 10 == 1:")
    ekler = durum_blok.count("veri_kaynagi.lastupdate_taze()") + durum_blok.count("tetik_modulu.getir()")
    komut_blok = _blok(kaynak, "if self._komut_tur % 10 == 1:")
    assert "self._komut_capraz_kontrol()" in komut_blok
    komut_govde = _blok(kaynak, "def _komut_capraz_kontrol(self):")
    ekler += komut_govde.count("komut_modulu.getir()")
    assert ekler == 3, f"10 turluk döngüde beklenen 3 ek indirme, kaynakta {ekler} bulundu"
    return (10 + ekler) / 10


def _tr(sayi: float, basamak: int = 2) -> str:
    """Türkçe ondalık biçim: 13.15 → '13,15'."""
    return f"{sayi:.{basamak}f}".replace(".", ",")


def _milyon(aralik_sn: int, cihaz: int = CIHAZ, carpan: float | None = None) -> str:
    """Aylık istek sayısı (M), belgedeki Türkçe ondalık biçimiyle: '13,15 M'."""
    carpan = _istek_turu() if carpan is None else carpan
    return _tr(cihaz * 86400 * AY / aralik_sn * carpan / 1_000_000) + " M"


def _hucre(satir: str) -> list[str]:
    return [h.strip().strip("*").strip() for h in satir.strip().strip("|").split("|")]


def _tablo(metin: str, ipucu: str) -> list[list[str]]:
    """`ipucu` başlığından sonraki markdown tablosunun veri satırları (hücre listesi)."""
    basliklar = metin.splitlines()
    basla = next(i for i, s in enumerate(basliklar) if ipucu in s)
    satirlar: list[list[str]] = []
    for satir in basliklar[basla:]:
        if satir.startswith("|") and "·" in satir and "sn" in satir:
            satirlar.append(_hucre(satir))
        elif satirlar and not satir.startswith("|"):
            break
    assert satirlar, f"{ipucu} tablosu bulunamadı"
    return satirlar


def _kontrol_tablosu(metin: str, ipucu: str) -> None:
    """Tablodaki her satırın istek/CF/S3/toplam değerlerini koddan türetilenle karşılaştır.

    İki tablo biçimi desteklenir: 6 hücreli (cihaz · etiket | aralık | istek | CF | S3 | toplam)
    ve 5 hücreli (senaryo — cihaz ve aralık aynı hücrede | istek | CF | S3 | toplam).
    """
    for hucre in _tablo(metin, ipucu):
        if len(hucre) == 6:
            cihaz = int(re.match(r"(\d+)", hucre[0]).group(1))
            sn = int(re.search(r"(\d+)", hucre[1]).group(1))
            etiket, istek, cf_h, s3_h, top_h = hucre[0], hucre[2], hucre[3], hucre[4], hucre[5]
        else:
            assert len(hucre) == 5, f"beklenmeyen tablo biçimi: {hucre}"
            etiket = hucre[0]
            cihaz = int(re.match(r"(\d+)", etiket).group(1)) if re.match(r"(\d+)", etiket) else CIHAZ
            sn = int(re.search(r"(\d+)\s*sn", etiket).group(1))
            istek, cf_h, s3_h, top_h = hucre[1], hucre[2], hucre[3], hucre[4]
        # "Eski: 3 dosya" satırı ESKİ 3 istek/tur tabanını anlatır (tarihsel karşılaştırma).
        carpan = 3.0 if "3 dosya" in etiket else _istek_turu()
        top_h = top_h.lstrip("~")  # "~$78,64" yaklaşık işareti sayıyı değiştirmez
        beklenen_m = cihaz * 86400 * AY / sn * carpan / 1_000_000
        cf = beklenen_m * CLOUDFRONT_M
        s3 = beklenen_m * S3_M
        assert istek == _tr(beklenen_m) + " M", (
            f"{etiket} · {sn} sn: istek {istek!r} ≠ koddan türetilen "
            f"{_tr(beklenen_m) + ' M'!r} (çarpan {carpan})")
        assert cf_h == "$" + _tr(cf), f"{etiket} · {sn} sn: CloudFront {cf_h!r} ≠ ${_tr(cf)}"
        assert s3_h == "$" + _tr(s3), f"{etiket} · {sn} sn: S3 {s3_h!r} ≠ ${_tr(s3)}"
        assert top_h == "$" + _tr(cf + s3), f"{etiket} · {sn} sn: toplam {top_h!r} ≠ ${_tr(cf + s3)}"


def test_83_tablosu_koddaki_sureleri_yazar() -> None:
    itme = _config_sabit("DAMGA_KONTROL_MS_PUSH")
    kopuk = _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")
    belge = BELGE.read_text(encoding="utf-8")

    assert f"**{itme} sn**" in belge, f"§8.3 MQTT bağlı süresi {itme} sn yazmıyor"
    assert f"**{kopuk} sn**" in belge, f"§8.3 push kapalı/kopuk süresi {kopuk} sn yazmıyor"
    assert "`DAMGA_KONTROL_MS_PUSH`" in belge and "`DAMGA_KONTROL_MS_PUSH_YOK`" in belge, (
        "§8.3 tablosu sürenin hangi sabitten geldiğini yazmıyor"
    )


def test_maliyet_tablosu_koddan_turetilen_istek_sayilarini_yazar() -> None:
    belge = BELGE.read_text(encoding="utf-8")
    for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), _config_sabit("DAMGA_KONTROL_MS_PUSH"),
                   300, 1800):
        assert _milyon(aralik) in belge, (
            f"§9 maliyet tablosunda {aralik} sn için {_milyon(aralik)} yok — "
            "tablo koddan türetilmiş istek sayısıyla uyuşmuyor"
        )


def test_tablo_istek_sayilari_koddan_turetilir() -> None:
    """Her iki maliyet tablosunun HER satırı (istek/CF/S3/toplam) koddan türetilir.

    27 Ekim i5 bulgusu: tablo "1 istek/tur" tabanıyla kurulmuştu ve 10 turluk çapraz kontroller
    (13 istek) maliyete eklenmemişti.
    """
    _kontrol_tablosu(MALIYET_BELGESI.read_text(encoding="utf-8"), "## Yoklama aralığı")
    _kontrol_tablosu(BELGE.read_text(encoding="utf-8"), "## 9) MALİYET")


def test_10_turda_13_istek_belgede_yazar() -> None:
    """Koddan türetilen 13 istek/10 tur ve 1,3 çarpanı belgede AÇIKÇA yazmalı."""
    oran = _istek_turu()
    assert oran == 1.3, f"beklenen 1,3 istek/tur, kaynaktan {oran} türetildi"
    for belge in (MALIYET_BELGESI, BELGE):
        metin = belge.read_text(encoding="utf-8")
        assert "10 tur = 13 istek" in metin or "10 turda 13 istek" in metin, (
            f"{belge.name}: 10 turdaki çapraz kontroller (13 istek) sayıyla yazılmıyor")
        assert "1,3" in metin, f"{belge.name}: tur başına 1,3 istek çarpanı yazılmıyor"


def test_1800_sn_varsayilan_gibi_sunulmaz() -> None:
    """1800 sn yalnız 'elle ayarlanırsa' bağlamında geçebilir; 'bağlı/varsayılan' diyemez."""
    for satir in BELGE.read_text(encoding="utf-8").splitlines():
        if "1800" not in satir:
            continue
        kucuk = satir.lower()
        assert "varsayılan" not in kucuk or "eski" in kucuk, (
            f"1800 sn varsayılan gibi sunuluyor: {satir.strip()[:120]}"
        )
        if kucuk.lstrip().startswith("|"):
            assert "elle" in kucuk, f"1800 sn tablo satırı 'elle' ile nitelenmemiş: {satir.strip()[:120]}"
            assert "bağlı" not in kucuk, (
                f"1800 sn hâlâ 'MQTT bağlı' aralığı olarak yazılı: {satir.strip()[:120]}"
            )


def test_bugunku_varsayilan_30_sn_olarak_isaretli() -> None:
    """`TETIK_PUSH_AKTIF` varsayılanı false → sahada etkin aralık PUSH_YOK sabitidir."""
    kaynak = (KIOSK / "config.py").read_text(encoding="utf-8")
    m = re.search(r"^TETIK_PUSH_AKTIF\s*=\s*(True|False)", kaynak, re.MULTILINE)
    assert m, "TETIK_PUSH_AKTIF config.py içinde bulunamadı"
    if m.group(1) == "True":
        return  # push varsayılan açıksa 'bugünkü varsayılan' satırı gerekmez
    kopuk = _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")
    belge = BELGE.read_text(encoding="utf-8")
    assert "BUGÜNKÜ VARSAYILAN" in belge, (
        "push varsayılan kapalı ama belge 'bugünkü varsayılan' maliyet satırını işaretlemiyor"
    )
    assert f"**{kopuk} sn — BUGÜNKÜ VARSAYILAN**" in belge, (
        f"'bugünkü varsayılan' satırı {kopuk} sn değil"
    )


# --- tarayıcı turu: hangi dosyalar istenir? (27 Ekim i5 bulgusu: dipnot durum.json diyordu) -----
def _tarayici_veri_dosyalari() -> list[str]:
    """Tarayıcının veri turunda okuduğu dosyalar — `web/src/veri/kaynak.ts`ten."""
    kaynak = (KOK / "web" / "src" / "veri" / "kaynak.ts").read_text(encoding="utf-8")
    m = re.search(r"VERI_DOSYALARI\s*=\s*\[(.*?)\]", kaynak, re.S)
    assert m, "kaynak.ts içinde VERI_DOSYALARI bulunamadı"
    return re.findall(r"'([^']+\.json)'", m.group(1))


def _tarayici_tetik_dosyasi() -> str:
    kaynak = (KOK / "web" / "src" / "veri" / "kaynak.ts").read_text(encoding="utf-8")
    m = re.search(r"sabit\('TETIK_DOSYASI',\s*'([^']+\.json)'\)", kaynak)
    assert m, "kaynak.ts içinde tetik dosyası varsayılanı bulunamadı"
    return m.group(1)


def test_tarayici_turu_durum_json_istemez_ve_dipnot_kodla_ayni() -> None:
    """Tarayıcı turu = `lastupdate.json` + `tetikle.json`; `durum.json` HİÇ istenmez.

    27 Ekim i5 bulgusu: `docs/ONBELLEK-VE-MALIYET.md` dipnotu tarayıcı turunu
    "lastupdate.json (+ değiştiyse durum.json) ve tetikle.json" diye sayıyordu — Qt'ye ait
    `durum.json` tarayıcıda hiç okunmaz (`VERI_DOSYALARI` içinde yok).
    """
    veri = _tarayici_veri_dosyalari()
    assert "durum.json" not in veri, f"tarayıcı VERI_DOSYALARI artık durum.json içeriyor: {veri}"
    assert "lastupdate.json" in veri

    metin = MALIYET_BELGESI.read_text(encoding="utf-8")
    # Tarayıcı modunu anlatan paragraf (dipnot) — satırlar "Tarayıcı modu"dan sonra.
    satirlar = metin.splitlines()
    basla = next(i for i, s in enumerate(satirlar) if "Tarayıcı modu" in s)
    paragraf = "\n".join(satirlar[basla:basla + 6])
    assert "tarayıcı" in paragraf.lower()
    for dosya in ("lastupdate.json", _tarayici_tetik_dosyasi()):
        assert dosya in paragraf, f"dipnot tarayıcı turunda {dosya} olduğunu yazmıyor"
    for dosya in veri:
        assert dosya in paragraf, f"dipnot tarayıcının okuduğu {dosya} dosyasını saymıyor"
    # durum.json'dan söz ediliyorsa MUTLAKA olumsuzlanmalı (istemez / Qt'ye ait) ve asla
    # "+ durum.json" / "ve durum.json" biçiminde istenen dosya gibi sayılmamalı.
    assert not re.search(r"(?:\+|ve)\s*`?durum\.json", paragraf), (
        "dipnot tarayıcı turunda durum.json isteniyormuş gibi yazıyor")
    if "durum.json" in paragraf:
        assert "istemez" in paragraf.lower() or "aittir" in paragraf.lower(), (
            "dipnot tarayıcının durum.json istemediğini AÇIKÇA yazmıyor")
