"""Sınırlandırılmış ağ erişimi (Qt bağımlılığı YOK).

Referans sürümde `urllib.request.urlopen(url)` vardı: zaman aşımı, boyut sınırı, şema ve
ana makine denetimi yoktu; hata durumunda ekran sessizce boş kalıyordu. Bu modüldeki kapı:

  * **https zorunlu**, ana makine **izin listesine** bağlı (büyük/küçük harf ve son nokta
    normalleştirilir), **yalnızca 443** portu, adreste kullanıcı bilgisi/denetim karakteri yok,
    uzunluk sınırlı (SSRF ve URL enjeksiyonu denemeleri),
  * **yönlendirme denetimi**: `urllib` varsayılanı yönlendirmeleri körü körüne izler; bu, izin
    listesini atlatmanın en kolay yoludur. Burada her yönlendirme yeniden doğrulanır ve
    varsayılan olarak yalnızca **aynı ana makineye** izin verilir,
  * **ortam vekil sunucuları yok sayılır** (`ProxyHandler({})`): cihazdaki `http_proxy`
    değişkeni trafiği araya sokamaz,
  * **TLS**: sertifika + ana makine doğrulaması açık, en az TLS 1.2, sıkıştırma kapalı,
  * **boyut sınırı**: `Content-Length` önden denetlenir, gövde sınırın bir fazlası kadar okunur,
  * `Accept-Encoding: identity` (sıkıştırılmış gövdeyle boyut sınırı atlatılamasın).
"""

from __future__ import annotations

import logging
import ipaddress
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import SplitResult, urlparse

log = logging.getLogger("kiosk.ag")

IZINLI_SEMALAR = ("https",)
VARSAYILAN_PORT = 443
EN_BUYUK_URL_UZUNLUK = 2048
#: Görsel indirmede kabul edilen içerik türleri (gövde imzası ayrıca denetlenir)
IZINLI_ICERIK_TURLERI = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


class AgHatasi(RuntimeError):
    """Ağ erişimi politikaya uymadı veya başarısız oldu."""


def _tls_baglami() -> ssl.SSLContext:
    """Sertifika/ana makine doğrulaması açık, TLS 1.2+, sıkıştırma kapalı bağlam."""
    baglam = ssl.create_default_context()
    try:
        baglam.minimum_version = ssl.TLSVersion.TLSv1_2
    except (AttributeError, ValueError):  # çok eski OpenSSL
        log.debug("minimum_version ayarlanamadı")
    baglam.options |= ssl.OP_NO_COMPRESSION
    baglam.verify_mode = ssl.CERT_REQUIRED
    baglam.check_hostname = True
    return baglam


@dataclass(frozen=True, slots=True)
class AgAyarlari:
    zaman_asimi_s: float = 10.0
    en_buyuk_bayt: int = 8 * 1024 * 1024
    izinli_hostlar: tuple[str, ...] = ()
    kullanici_ajani: str = "yourkiosk/1.0"
    izinli_portlar: tuple[int, ...] = (VARSAYILAN_PORT,)
    yonlendirme_izinli: bool = False
    en_buyuk_url: int = EN_BUYUK_URL_UZUNLUK

    # ------------------------------------------------------------------ #
    @property
    def _izinli_host_kumesi(self) -> set[str]:
        return {h.strip().rstrip(".").lower() for h in self.izinli_hostlar if h and h.strip()}

    def dogrula_url(self, url: str) -> SplitResult:
        """Adresi politikaya göre doğrular; uymuyorsa `AgHatasi` yükseltir."""
        if not isinstance(url, str) or not url.strip():
            raise AgHatasi("boş adres")
        if len(url) > self.en_buyuk_url:
            raise AgHatasi(f"adres çok uzun ({len(url)} > {self.en_buyuk_url})")
        if any(k in url for k in ("\r", "\n", "\x00")) or any(k.isspace() for k in url):
            raise AgHatasi("adreste denetim/boşluk karakteri var")
        try:
            parcali = urlparse(url)
        except ValueError as hata:  # bozuk port vb.
            raise AgHatasi(f"adres ayrıştırılamadı: {hata}") from hata

        if parcali.scheme not in IZINLI_SEMALAR:
            raise AgHatasi(f"yalnızca https kabul edilir (gelen: {parcali.scheme or 'yok'})")
        if parcali.username or parcali.password:
            raise AgHatasi("adreste kullanıcı bilgisi var")
        host = (parcali.hostname or "").rstrip(".").lower()
        if not host:
            raise AgHatasi("adreste ana makine yok")
        if host not in self._izinli_host_kumesi:
            raise AgHatasi(f"adres izin listesinde değil: {host}")
        try:
            port = parcali.port or VARSAYILAN_PORT
        except ValueError as hata:
            raise AgHatasi(f"geçersiz port: {hata}") from hata
        if port not in self.izinli_portlar:
            raise AgHatasi(f"izin verilmeyen port: {port} (izinli: {self.izinli_portlar})")
        return parcali

    def host_izinli(self, url: str) -> bool:
        """Geriye uyum: adres politikaya uyuyorsa True."""
        try:
            self.dogrula_url(url)
        except AgHatasi:
            return False
        return True


def _host_herkese_acik(host: str) -> tuple[bool, str]:
    """Host yalnız GENEL (özel olmayan) IP'lere çözümleniyorsa True.

    SSRF koruması: 127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7,
    multicast/ayrılmış adresler reddedilir. DNS rebinding'e karşı tam koruma sağlamaz
    (bağlantı anında yeniden çözümleme olur) — içerik panel tarafından yetkilendirilir.
    """
    try:
        kayitlar = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as hata:
        return False, f"çözümlenemedi: {hata}"
    if not kayitlar:
        return False, "adres kaydı yok"
    for kayit in kayitlar:
        try:
            ip = ipaddress.ip_address(str(kayit[4][0]).split("%")[0])
        except ValueError:
            return False, "geçersiz IP"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False, f"özel/ayrılmış adres: {ip}"
    return True, ""


def gorsel_icin_ayarlar(ayarlar: AgAyarlari, url: str) -> AgAyarlari:
    """Görsel indirme için ayarları genişletir: izin listesinde olmayan **herkese açık** https host kabul.

    NEDEN: yayın görselleri panelde serbestçe adreslenir (ör. https://hakkisabah.com/api/x.png).
    Cihazın veri izin listesine her görsel alan adını eklemek 600 cihazda sürdürülemez.
    """
    import dataclasses

    parcali = urlparse(url)
    if parcali.scheme not in IZINLI_SEMALAR:
        raise AgHatasi(f"görsel: yalnızca https kabul edilir (gelen: {parcali.scheme or 'yok'})")
    if parcali.username or parcali.password:
        raise AgHatasi("görsel adresinde kullanıcı bilgisi var")
    try:
        port = parcali.port or VARSAYILAN_PORT
    except ValueError as hata:
        raise AgHatasi(f"görsel: geçersiz port: {hata}") from hata
    if port not in ayarlar.izinli_portlar:
        raise AgHatasi(f"görsel: izin verilmeyen port: {port}")
    host = (parcali.hostname or "").rstrip(".").lower()
    if not host:
        raise AgHatasi("adreste ana makine yok")
    uygun, neden = _host_herkese_acik(host)
    if not uygun:
        raise AgHatasi(f"görsel adresi reddedildi ({host}): {neden}")
    izinli = tuple(dict.fromkeys((*ayarlar.izinli_hostlar, host)))
    return dataclasses.replace(ayarlar, izinli_hostlar=izinli)


class _YonlendirmeDenetimi(urllib.request.HTTPRedirectHandler):
    """Her yönlendirmeyi yeniden doğrular (izin listesi atlatılamasın)."""

    def __init__(self, ayarlar: AgAyarlari) -> None:
        super().__init__()
        self._ayarlar = ayarlar

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 (urllib imzası)
        self._ayarlar.dogrula_url(newurl)  # şema/izin listesi/port dışıysa AgHatasi
        if not self._ayarlar.yonlendirme_izinli:
            kaynak_host = (urlparse(req.full_url).hostname or "").rstrip(".").lower()
            hedef_host = (urlparse(newurl).hostname or "").rstrip(".").lower()
            if kaynak_host != hedef_host:
                raise AgHatasi(f"farklı ana makineye yönlendirme reddedildi: {hedef_host}")
        log.warning("yönlendirme izlendi (%s): %s", code, newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(ayarlar: AgAyarlari):
    """Vekil sunucuları yok sayan, yönlendirmeyi denetleyen opener."""
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),  # ortam vekilleri devre dışı
        _YonlendirmeDenetimi(ayarlar),
        urllib.request.HTTPSHandler(context=_tls_baglami()),
    )


def indir(url: str, ayarlar: AgAyarlari, *, icerik_turu_denetle: bool = True) -> tuple[bytes, str]:
    """HTTPS GET; (bayt, content-type) döner. Politika ihlali -> AgHatasi."""
    ayarlar.dogrula_url(url)
    istek = urllib.request.Request(
        url,
        headers={
            "User-Agent": ayarlar.kullanici_ajani,
            "Accept": "image/png,image/jpeg,image/webp,application/json;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity",  # sıkıştırılmış gövde boyut sınırını atlatmasın
            "Connection": "close",
        },
        method="GET",
    )
    try:
        with _opener(ayarlar).open(istek, timeout=ayarlar.zaman_asimi_s) as yanit:  # noqa: S310
            if yanit.status != 200:
                raise AgHatasi(f"HTTP {yanit.status}")
            tur = (yanit.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if icerik_turu_denetle and tur not in IZINLI_ICERIK_TURLERI:
                raise AgHatasi(f"içerik türü kabul edilmiyor: {tur or 'yok'}")
            ilan = yanit.headers.get("Content-Length")
            if ilan is not None and ilan.isdigit() and int(ilan) > ayarlar.en_buyuk_bayt:
                raise AgHatasi(f"yanıt çok büyük: {ilan} bayt")
            veri = yanit.read(ayarlar.en_buyuk_bayt + 1)
            if len(veri) > ayarlar.en_buyuk_bayt:
                raise AgHatasi(f"yanıt üst sınırı aştı (> {ayarlar.en_buyuk_bayt} bayt)")
            return veri, tur
    except AgHatasi:
        raise
    except urllib.error.HTTPError as hata:
        raise AgHatasi(f"HTTP {hata.code}") from hata
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as hata:
        raise AgHatasi(f"{type(hata).__name__}: {hata}") from hata


def json_indir(url: str, ayarlar: AgAyarlari) -> object:
    """JSON gövdesi çeker (boyut + derinlik + düğüm denetimiyle)."""
    from security.veri_dogrulama import json_yukle

    veri, _tur = indir(url, ayarlar, icerik_turu_denetle=False)
    return json_yukle(veri, etiket=url, en_buyuk_bayt=ayarlar.en_buyuk_bayt)
