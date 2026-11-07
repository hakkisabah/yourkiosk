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


# --- 28 Ekim i5 bulgusu: maliyet TABANI iki farklı sayıyla yazılıydı -------------------------
# Belge tabloları 1,3 istek/tur ile yeniden üretilmişti ama `config.py` yorumları, `durum.py`
# docstring'i ve TETIK-OLCEK.md tablosu hâlâ 1,0 tabanıyla ($59,62 / $14,90) konuşuyordu.
# Aynı sınıf hatanın tekrarı, sayı elle yazıldığı sürece mümkündür; bu test sayıları KODDAN
# türetip hem yorumlarda hem tabloda arar (ve eski 1,0 tabanlı değerleri yasaklar).
TETIK_OLCEK = KOK / "docs" / "TETIK-OLCEK.md"
CONFIG_PY = KIOSK / "config.py"
DURUM_PY = KIOSK / "core" / "durum.py"


def _maliyet_metinleri() -> dict[str, str]:
    """1,3 tabanını yazmak zorunda olan üç metin (yorum/docstring/tablo)."""
    return {
        "kiosk/config.py": CONFIG_PY.read_text(encoding="utf-8"),
        "kiosk/core/durum.py": DURUM_PY.read_text(encoding="utf-8"),
        "docs/TETIK-OLCEK.md": TETIK_OLCEK.read_text(encoding="utf-8"),
    }


def test_config_ve_durum_yorumlari_tur_basina_1_3_istek_yazar() -> None:
    """Yorumlar/docstring koddan türetilen tabanı ve aylık tutarları yazmalı."""
    carpan = _istek_turu()
    assert carpan == 1.3, f"tur başına istek sayısı koddan {carpan} türetildi"
    otuz = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"))
    yuz_yirmi = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH"))
    for ad, metin in _maliyet_metinleri().items():
        assert "1,3" in metin, f"{ad}: tur başına 1,3 istek tabanı yazılmıyor (1,0 tabanı kalmış)"
        assert otuz in metin, f"{ad}: bugünkü varsayılan (30 sn) için {otuz} istek/ay yazmıyor"
        assert yuz_yirmi in metin, f"{ad}: push bağlı (120 sn) için {yuz_yirmi} istek/ay yazmıyor"


def test_bayat_1_0_tabani_tutarlari_yasak() -> None:
    """Eski 1,0 istek/tur tabanıyla hesaplanmış tutarlar bu üç metinde kalamaz."""
    for ad, metin in _maliyet_metinleri().items():
        for bayat in ("59,62", "14,90", "51,8 M", "13,0 M"):
            assert bayat not in metin, (
                f"{ad}: eski 1,0 istek/tur tabanlı değer ({bayat}) duruyor — 13/10 = 1,3 ile "
                "yeniden üretilmeli")


def test_tetik_olcek_tablosu_koddan_turetilir() -> None:
    """TETIK-OLCEK.md tablosunun her satırı 1,3 çarpanıyla koddan türetilmeli."""
    satirlar = [s for s in TETIK_OLCEK.read_text(encoding="utf-8").splitlines()
                if s.startswith("|") and re.search(r"\d+\s*(?:sn|dk)\s*\|", s)]
    assert len(satirlar) >= 5, f"TETIK-OLCEK.md tablosunda beklenen 5 satır, bulunan {len(satirlar)}"
    for satir in satirlar:
        aralik_h, istek_h, cf_h, s3_h, top_h = _hucre(satir)
        m = re.search(r"(\d+)\s*(sn|dk)", aralik_h)
        assert m, f"aralık çözülemedi: {aralik_h!r}"
        sn = int(m.group(1)) * (60 if m.group(2) == "dk" else 1)
        beklenen_m = CIHAZ * 86400 * AY / sn * _istek_turu() / 1_000_000
        assert istek_h == _tr(beklenen_m) + " M", (
            f"{aralik_h}: istek {istek_h!r} ≠ koddan türetilen {_tr(beklenen_m) + ' M'!r}")
        assert cf_h == "$" + _tr(beklenen_m * CLOUDFRONT_M), f"{aralik_h}: CloudFront {cf_h!r}"
        assert s3_h == "$" + _tr(beklenen_m * S3_M), f"{aralik_h}: S3 {s3_h!r}"
        assert top_h.lstrip("~") == "$" + _tr(beklenen_m * (CLOUDFRONT_M + S3_M)), (
            f"{aralik_h}: toplam {top_h!r}")


# --- 6 Kasım i5 bulgusu: tarayıcı turu 2 istek, maliyet 1 istek/tur ile yazılmıştı ------------
KIOSK_TS = KOK / "web" / "src" / "kiosk.ts"


def test_tarayici_maliyet_notu_iki_istek_tabanini_kullanir() -> None:
    """`web/src/kiosk.ts` maliyet yorumu tarayıcı turunun GERÇEK istek sayısıyla hesaplanmalı.

    NEDEN: aynı yorum bloğu 486. satırda "tur başına en çok İKİ küçük istek" diyor
    (`lastupdate.json` + `tetikle.json`), 491. satırda ise 600 cihaz maliyetini TEK istek/tur
    ile yazıyordu. Okuyan operatör yarı yarıya düşük maliyet görür; 600 cihazda fark
    $10 → $20 ve $60 → $79 mertebesinde.
    """
    metin = KIOSK_TS.read_text(encoding="utf-8")
    assert "en çok İKİ küçük istek" in metin, "tarayıcı turunun 2 istek olduğu iddiası kaldırılmış"

    # Değerler koddan türetilir: 2 istek/tur (lastupdate + tetikle), depo maliyet tabanıyla.
    yuz_yirmi = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH"), carpan=2.0)
    otuz = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), carpan=2.0)
    assert yuz_yirmi in metin, f"kiosk.ts: 120 sn için {yuz_yirmi} istek/ay yazmıyor"
    assert otuz in metin, f"kiosk.ts: 30 sn için {otuz} istek/ay yazmıyor"


def test_tarayici_maliyet_notunda_tek_istek_tabani_yasak() -> None:
    """1 istek/tur (ve Qt'nin 1,3 tabanı) ile hesaplanmış değerler kiosk.ts'te kalamaz."""
    metin = KIOSK_TS.read_text(encoding="utf-8")
    for carpan, etiket in ((1.0, "tek istek/tur"), (1.3, "Qt'nin 1,3 tabanı")):
        for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH"), _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")):
            bayat = _milyon(aralik, carpan=carpan)
            assert bayat not in metin, (
                f"kiosk.ts: {aralik} sn için {bayat} ({etiket}) yazıyor — tarayıcı turu 2 istek"
            )
    # 30 gün tabanıyla yazılmış eski elle değerler de yasak (13,0 M / 51,8 M)
    for elle in ("13,0 M", "51,8 M"):
        assert elle not in metin, f"kiosk.ts: elle yazılmış eski değer ({elle}) duruyor"


# --- 6 Kasım i5 bulguları: aynı sınıf, dört ayrı belgede elle yazılmış çelişkili sayılar --------
SIRADAKI_ISLER = KOK / "SIRADAKI-ISLER.md"
AWS_KURULUM = KOK / "docs" / "AWS-KURULUM.md"


def test_siradaki_isler_maliyet_sayilari_koddan_turetilir() -> None:
    """`SIRADAKI-ISLER.md`: "tabloyla aynı sayılar" diyen satır gerçekten aynı olmalı.

    6 Kasım i5 bulgusu: satır 13,0 M / $14,90 / $59,62 (1,0 istek/tur) diyordu, aynı PR'ın
    tablosu ise 17,10 M / $19,66 ve 68,38 M / $78,64 (1,3 istek/tur) üretiyordu.
    """
    metin = SIRADAKI_ISLER.read_text(encoding="utf-8")
    for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), _config_sabit("DAMGA_KONTROL_MS_PUSH")):
        istek = _milyon(aralik)
        tutar = "$" + _tr(cihaz_tutari(aralik))
        assert istek in metin, f"SIRADAKI-ISLER.md: {aralik} sn için {istek} istek/ay yazmıyor"
        assert tutar in metin, f"SIRADAKI-ISLER.md: {aralik} sn için {tutar} yazmıyor"
    for bayat in ("13,0 M", "$14,90", "$59,62", "1 istek"):
        assert bayat not in metin, f"SIRADAKI-ISLER.md: eski 1,0 tabanlı değer ({bayat}) duruyor"


def cihaz_tutari(aralik_sn: int, cihaz: int = CIHAZ) -> float:
    """Aylık TOPLAM tutar (CloudFront + S3 GET), koddan türetilen istek sayısıyla."""
    istek_m = cihaz * 86400 * AY / aralik_sn * _istek_turu() / 1_000_000
    return istek_m * (CLOUDFRONT_M + S3_M)


def test_aws_kurulum_uc_cihaz_tablosu_koddan_turetilir() -> None:
    """`docs/AWS-KURULUM.md` 3 cihaz tablosu da 1,3 istek/tur ve 30,44 gün tabanını kullanmalı.

    6 Kasım i5 bulgusu: GET satırı "259 bin" (1 istek/tur, 30 gün) diyordu; PR'ın kendi tabanı
    1,3 olduğu için gerçek değer 342 bin, tutar $0,14.
    """
    metin = AWS_KURULUM.read_text(encoding="utf-8")
    taban = 0.01 + 0.003 + 0.02  # depolama + PUT + dışa aktarım (tablodaki diğer kalemler)
    for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), _config_sabit("DAMGA_KONTROL_MS_PUSH")):
        istek_bin = f"{3 * 86400 * AY / aralik * _istek_turu() / 1000:,.0f}"
        assert f"{istek_bin} bin istek" in metin, (
            f"AWS-KURULUM.md: {aralik} sn için '{istek_bin} bin istek' yazmıyor "
            "(1,0 istek/tur tabanı kalmış olabilir)")
        toplam = taban + 3 * 86400 * AY / aralik * _istek_turu() / 1_000_000 * S3_M
        assert "$" + _tr(toplam) in metin, (
            f"AWS-KURULUM.md: {aralik} sn için toplam ${_tr(toplam)} yazmıyor")
    for bayat in ("259 bin", "$0,13/ay", "$0,06/ay"):
        assert bayat not in metin, f"AWS-KURULUM.md: eski 1,0 tabanlı değer ({bayat}) duruyor"


def test_ay_uzunlugu_tabloyla_ayni_yazilir() -> None:
    """`docs/ONBELLEK-VE-MALIYET.md` ay uzunluğu tablonun üretildiği değer olmalı.

    6 Kasım i5 bulgusu: "tur = 2.592.000 sn/ay" (30 gün) yazıyordu, tablo ise 30,44 gün
    (2.630.016 sn) ile üretilmiş — okuyan iki sayıyı uzlaştıramıyordu.
    """
    saniye = round(AY * 86400)
    metin = MALIYET_BELGESI.read_text(encoding="utf-8")
    assert f"{saniye:,}".replace(",", ".") + " sn/ay" in metin, (
        f"ONBELLEK-VE-MALIYET.md: ay uzunluğu {saniye} sn olarak yazılmıyor")
    assert "2.592.000 sn/ay" not in metin, "30 günlük eski ay uzunluğu (2.592.000) duruyor"


def test_kiosk_ts_maliyet_notu_cloudfront_ve_toplami_ayirir() -> None:
    """`web/src/kiosk.ts` maliyet yorumu yalnız CloudFront kalemini "maliyet" diye sunmamalı.

    6 Kasım i5 bulgusu: $19,73 / $78,90 toplam gibi okunuyordu; oysa onlar yalnız CloudFront
    kalemidir (S3 GET hariç). Toplamlar $30,25 / $120,98.
    """
    metin = KIOSK_TS.read_text(encoding="utf-8")
    for aralik in (_config_sabit("DAMGA_KONTROL_MS_PUSH"), _config_sabit("DAMGA_KONTROL_MS_PUSH_YOK")):
        istek_m = CIHAZ * 86400 * AY / aralik * 2.0 / 1_000_000
        cf = "$" + _tr(istek_m * CLOUDFRONT_M)
        s3 = "$" + _tr(istek_m * S3_M)
        toplam = "$" + _tr(istek_m * (CLOUDFRONT_M + S3_M))
        assert cf in metin and s3 in metin, f"kiosk.ts: {aralik} sn için CloudFront/S3 kalemleri yazılmıyor"
        assert toplam in metin, f"kiosk.ts: {aralik} sn için TOPLAM {toplam} yazılmıyor"
    assert "CloudFront" in metin and "S3 GET" in metin, "kiosk.ts: kalem adları yazılmıyor"


# --- 7 Kasım i5 bulgusu: durum.py üç-dosya maliyeti 30 GÜN tabanıyla yazılıydı ---------------
# Tablolar 30,44 gün ile üretiliyor (AY) ama docstring 30 gün varsayıp 155,5 M / 38,9 M diyordu;
# yani aynı dosyada iki farklı ay uzunluğu. Sayı KODDAN türetilir, elle yazılmaz.
def test_durum_py_uc_dosya_maliyeti_30_44_gun_tabaniyla() -> None:
    """`durum.py` üç-dosya (çarpan 3) değerleri 30,44 gün tabanıyla yazılmalı."""
    metin = DURUM_PY.read_text(encoding="utf-8")
    otuz = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), carpan=3.0)
    yuz_yirmi = _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH"), carpan=3.0)
    assert otuz in metin, f"durum.py: 30 sn üç-dosya değeri {otuz} istek/ay yazmıyor"
    assert yuz_yirmi in metin, f"durum.py: 120 sn üç-dosya değeri {yuz_yirmi} istek/ay yazmıyor"
    # Tutarlar da koddan: CloudFront + S3 kalemleri ayrı ayrı ve toplam.
    for milyon in (_milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH_YOK"), carpan=3.0),
                   _milyon(_config_sabit("DAMGA_KONTROL_MS_PUSH"), carpan=3.0)):
        sayi = float(milyon.replace(" M", "").replace(".", "").replace(",", "."))
        assert "$" + _tr(sayi * CLOUDFRONT_M) in metin, f"durum.py: {milyon} CloudFront kalemi yok"
        assert "$" + _tr(sayi * (CLOUDFRONT_M + S3_M)) in metin, f"durum.py: {milyon} toplam yok"
    # 30 gün tabanıyla yazılmış eski elle değerler yasak.
    for bayat in ("155,5", "38,9", "178,9", "44,71", "116,6", "62,2"):
        assert bayat not in metin, f"durum.py: 30 gün tabanlı eski değer ({bayat}) duruyor"


def test_tarayici_yorumlari_baglantiya_gore_secim_iddia_etmez() -> None:
    """Tarayıcı modu sabit `DAMGA_KONTROL_MS` kullanır; 'kopuk 30 sn' yalnız Qt cümlesinde geçer.

    NEDEN: 686/744 ve kaynak.ts:277 tarayıcı için "push bağlı 120 sn / kopuk 30 sn" diyordu; oysa
    seçim `yoklama_araligi()` ile YALNIZ Qt tarafında yapılır (`pharmacy_app.py`), tarayıcı
    zamanlayıcısı sabittir. Operatöre yanlış davranış anlatan yorum = yanlış bulgu üretir.
    """
    kiosk_ts = KIOSK_TS.read_text(encoding="utf-8")
    kaynak_ts = (KOK / "web" / "src" / "veri" / "kaynak.ts").read_text(encoding="utf-8")
    assert kiosk_ts.count("kopuk 30 sn") == 1, (
        "kiosk.ts'te 'kopuk 30 sn' yalnız Qt cümlesinde geçmeli; tarayıcı yorumları sabit 120 sn demeli")
    yer = kiosk_ts.index("kopuk 30 sn")
    baglam = kiosk_ts[max(0, yer - 160):yer + 40]   # cümle iki satıra sarılmış olabilir
    assert "Qt modu" in baglam and "yoklama_araligi" in baglam, (
        f"'kopuk 30 sn' Qt bağlamı dışında: {baglam!r}")
    assert "kopuk 30 sn" not in kaynak_ts, "kaynak.ts tarayıcı yoludur: 'kopuk 30 sn' yazamaz"
    assert "bağlantıya göre seçim" in kiosk_ts.lower(), "kiosk.ts tarayıcı için seçim olmadığını yazmıyor"
    assert "bağlantıya göre seçim" in kaynak_ts.lower(), "kaynak.ts sabit 120 sn olduğunu yazmıyor"
