"""MQTT ile ANLIK tetikleme (600+ cihaz ölçeği).

NEDEN: cihaz başına yoklama, cihaz sayısıyla DOĞRUSAL maliyet demek. 600 cihazda 3 sn yoklama
≈ ayda 518 milyon istek (≈ $600). Kalıcı bir MQTT bağlantısı ise ayda ~26 milyon cihaz-dakika
(AWS IoT Core ≈ $2; kendi Mosquitto'nuz varsa sabit $5) ve mesaj başına ~100 ms gecikme verir.

TASARIM (mevcut kodu DEĞİŞTİRMEZ): mesaj geldiğinde cihaz yerel `tetikle.json` dosyasını yazar.
Yerel dosya değişince mevcut imza/uzun yoklama mekanizması arayüzü anında yeniler — Qt ve tarayıcı
aynı yolu kullanır. Böylece push, mevcut tetikleme zincirinin yerine geçmez, ONU besler.

GÜVENLİK: TLS (8883) + kullanıcı/parola. Parola ayar dosyasında tutulur (cihazın kendi dosyası,
kum havuzu dışında paylaşılmaz). Mesaj içeriği yalnız "yenile" işaretidir; veri MQTT'den GELMEZ.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import config

log = logging.getLogger("kiosk.push")

#: Aktif paho istemcisi (gerçek bağlantı durumu için). Thread başlatılınca doldurulur.
_istemci_ref: list = [None]

#: Arka plan iş parçacığı ve son durum (--tani çıktısı için)
_iş: threading.Thread | None = None
_durum: dict = {"aktif": False, "bagli": False, "son_mesaj": "", "hata": ""}


def acik() -> bool:
    return bool(getattr(config, "TETIK_PUSH_AKTIF", False))


def konu() -> str:
    return str(getattr(config, "TETIK_PUSH_KONU", "yourkiosk/yayin") or "").strip()


def broker() -> str:
    return str(getattr(config, "TETIK_PUSH_BROKER", "") or "").strip()


def durum() -> dict:
    """Push durumu. `bagli` alanı MÜMKÜNSE paho'nun GERÇEK durumundan okunur.

    NEDEN: `_durum["bagli"]` bayrağı on_connect/on_disconnect ile güncelleniyor ama kısa
    kopmalarda bayat kalabiliyordu (log: "MQTT bağlandı" → 2 sn sonra "KOPUK"). Yoklama aralığı
    bu bayrağa bağlı olduğu için aralık yanlış hesaplanıyordu.
    """
    anlik = dict(_durum)
    istemci = _istemci_ref[0]
    if istemci is not None:
        try:
            anlik["bagli"] = bool(istemci.is_connected())
        except Exception:  # noqa: BLE001
            pass
    return anlik


#: Kalp atışı aralığı (sn) — panel 600 cihazın çevrimiçi/çevrimdışı durumunu bundan okur.
#: 5 dk × 600 cihaz = ayda ~5,2 M küçük mesaj (MQTT'de önemsiz; yoklama maliyeti doğrusal büyür).
KALP_ATISI_S = 300


def cihaz_kimligi() -> str:
    """Bu cihazın kimliği (clientID) — kalp atışı konusunda kullanılır."""
    from core import veri_kaynagi

    try:
        return str(veri_kaynagi.client_id() or "").strip()
    except Exception:  # noqa: BLE001 - kimlik okunamazsa "bilinmeyen" ile devam
        return ""


def durum_konusu(cihaz: str | None = None) -> str:
    """Cihaz durum konusu: `<taban>/durum/<cihazId>` (`yourkiosk/yayin` → `yourkiosk/durum/<id>`).

    `+` ve `#` MQTT joker karakterleridir; kimlikte bulunurlarsa konu bozulur → temizlenir.
    """
    taban = konu().rsplit("/", 1)[0] if "/" in konu() else konu()
    kimlik = str(cihaz or cihaz_kimligi() or "bilinmeyen")
    kimlik = kimlik.replace("/", "-").replace("+", "-").replace("#", "-").strip() or "bilinmeyen"
    return f"{taban}/durum/{kimlik}"


def kalp_atisi_belgesi(cevrimici: bool = True, simdi: datetime | None = None) -> dict:
    """Kalp atışı gövdesi (retained): panel `cevrimici` + `zaman` alanlarını okur."""
    an = simdi or datetime.now(timezone.utc)
    return {
        "cevrimici": bool(cevrimici),
        "zaman": an.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mod": "tarayici" if str(getattr(config, "CALISTIRMA_MODU", "")).lower().startswith("tar") else "qt",
        "surum": str(getattr(config, "SURUM", "") or ""),
    }


def _tetik_yaz(kaynak: str = "mqtt") -> Path:
    """Yerel `tetikle.json`'u yazar → mevcut imza mekanizması arayüzü yeniler."""
    from core import tetik as tetik_modulu

    zaman = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    belge = {"zaman": zaman, "ilceId": "", "bolgeId": "", "aciklama": f"push:{kaynak}"[:120]}
    yol = tetik_modulu.dosya_yolu()
    # GÜVENLİK: sabit `.tmp` adı yerine mkstemp (sembolik bağ saldırısı — i5/i3 bulgusu).
    from core import uzak

    if not uzak.atomik_yaz(yol, json.dumps(belge, ensure_ascii=False).encode("utf-8")):
        log.warning("MQTT tetikleyicisi yazılamadı: %s", yol)
    log.info("MQTT tetikleyicisi yazıldı (%s)", kaynak)
    return yol


def mesaj_isle(govde: bytes | str) -> bool:
    """Gelen MQTT mesajı → yerel tetikleyici.

    `tetik.aktif` kapalıysa ya da cihazın modu `tetik.modlar` içinde değilse yok sayılır.
    Mesaj gövdesi JSON olabilir (`{"zaman": ...}`) ya da düz metin; içerik doğrulanmaz,
    yalnız "yenile" anlamı taşır.
    """
    from core import tetik as tetik_modulu

    mod = "tarayici" if str(getattr(config, "CALISTIRMA_MODU", "")).lower().startswith("tar") else "qt"
    if not tetik_modulu.otomatik_acik(mod):
        log.info("MQTT tetiği yok sayıldı (oto tetikleme kapalı ya da mod listede değil)")
        return False
    try:
        metin = govde.decode("utf-8", "ignore") if isinstance(govde, bytes) else str(govde)
        belge = json.loads(metin) if metin.strip().startswith("{") else {}
    except ValueError:
        belge = {}
    _tetik_yaz(str(belge.get("kaynak") or "mqtt"))
    _durum["son_mesaj"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return True


def _dongu(durdur: threading.Event) -> None:
    try:
        import paho.mqtt.client as mqtt  # type: ignore
    except ImportError:
        _durum["hata"] = "paho-mqtt kurulu değil (pip install paho-mqtt)"
        log.warning("MQTT push etkin ama 'paho-mqtt' yok → yoklama modu kullanılacak")
        return

    adres, port = broker(), int(getattr(config, "TETIK_PUSH_PORT", 8883))
    # paho-mqtt 2.x CallbackAPIVersion'ı ZORUNLU tutar; 1.x'te yoktur → ikisini de destekle
    istemci_id = f"yourkiosk-{int(time.time()) % 100000}"
    if hasattr(mqtt, "CallbackAPIVersion"):
        istemci = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=istemci_id)
    else:  # pragma: no cover - eski paho
        istemci = mqtt.Client(client_id=istemci_id)

    if getattr(config, "TETIK_PUSH_KULLANICI", ""):
        istemci.username_pw_set(str(config.TETIK_PUSH_KULLANICI), str(getattr(config, "TETIK_PUSH_PAROLA", "")))
    if port == 8883:
        ca = str(getattr(config, "TETIK_PUSH_CA", "") or "").strip()
        sertifika = str(getattr(config, "TETIK_PUSH_SERTIFIKA", "") or "").strip()
        anahtar = str(getattr(config, "TETIK_PUSH_ANAHTAR", "") or "").strip()
        try:
            if sertifika and anahtar:
                # AWS IoT Core: istemci sertifikası ile kimlik doğrulama
                istemci.tls_set(ca_certs=ca or None, certfile=sertifika, keyfile=anahtar)
            else:
                istemci.tls_set(ca_certs=ca or None)  # sistem CA'sı / verilen CA
        except Exception as hata:  # noqa: BLE001 - sertifika hatası push'u kapatır, cihaz çalışır
            _durum["hata"] = f"TLS/sertifika hatası: {hata}"[:200]
            log.error("MQTT TLS kurulamadı (%s) — push devre dışı, yoklama sürüyor", hata)
            return

    def _baglandi(_c, _u, _f, rc, _p=None):  # paho 2.x 5 argüman geçer (properties)
        _durum["bagli"] = rc == 0
        _durum["denendi"] = True
        if rc == 0:
            istemci.subscribe(konu(), qos=1)
            # ÇEVRİMİÇİ BİLDİRİMİ (retained): panel 600 cihazın durumunu buradan görür.
            try:
                istemci.publish(
                    durum_konusu(),
                    json.dumps(kalp_atisi_belgesi(True), ensure_ascii=False),
                    qos=1,
                    retain=True,
                )
            except Exception:  # noqa: BLE001 - kalp atışı push'u engellememeli
                log.debug("kalp atışı yayınlanamadı", exc_info=True)
            log.info("MQTT bağlandı (%s:%s) · konu=%s · durum=%s", adres, port, konu(), durum_konusu())
        else:
            log.warning("MQTT bağlanamadı (rc=%s)", rc)

    def _mesaj(_c, _u, mesaj):
        try:
            mesaj_isle(mesaj.payload)
        except Exception:  # noqa: BLE001 - thread ölmesin
            log.warning("MQTT mesajı işlenemedi", exc_info=True)

    _istemci_ref[0] = istemci
    istemci.on_connect = _baglandi
    istemci.on_disconnect = lambda *_: _durum.update(bagli=False)
    istemci.on_message = _mesaj

    # paho'nun kendi yeniden bağlanması (loop_start + reconnect_delay) kullanılır; dış döngüde
    # tekrar `connect()` çağırmak çift bağlantı/çift abonelik üretiyordu.
    try:
        istemci.reconnect_delay_set(min_delay=2, max_delay=60)
    except Exception:  # noqa: BLE001
        pass
    # SON İRADE (LWT): bağlantı koparsa broker cihazın durumunu "çevrimdışı" olarak yayınlar.
    # `will_set` BAĞLANMADAN ÖNCE kurulmalıdır.
    try:
        istemci.will_set(
            durum_konusu(),
            json.dumps(kalp_atisi_belgesi(False), ensure_ascii=False),
            qos=1,
            retain=True,
        )
    except Exception:  # noqa: BLE001
        log.debug("LWT kurulamadı", exc_info=True)
    son_kalp = 0.0
    while not durdur.is_set():
        try:
            istemci.connect(adres, port, keepalive=60)
            istemci.loop_start()
            while not durdur.is_set():
                if not istemci.is_connected():
                    _durum["bagli"] = False
                # KALP ATIŞI: bağlıyken her KALP_ATISI_S saniyede bir retained durum mesajı.
                elif time.monotonic() - son_kalp >= KALP_ATISI_S:
                    son_kalp = time.monotonic()
                    try:
                        istemci.publish(
                            durum_konusu(),
                            json.dumps(kalp_atisi_belgesi(True), ensure_ascii=False),
                            qos=1,
                            retain=True,
                        )
                    except Exception:  # noqa: BLE001
                        log.debug("kalp atışı yayınlanamadı", exc_info=True)
                time.sleep(1.0)
        except Exception as hata:  # noqa: BLE001 - ağ hatasında yeniden dene
            _durum.update(bagli=False, denendi=True, hata=str(hata)[:200])
            log.warning("MQTT bağlantı hatası: %s — 10 sn sonra yeniden", hata)
            time.sleep(10)


def baslat() -> bool:
    """Push'u arka planda başlatır (etkin değilse sessizce False)."""
    global _iş
    if not acik():
        return False
    if not broker() or not konu():
        _durum["hata"] = "broker/konu tanımlı değil"
        log.warning("MQTT push etkin ama broker/konu boş")
        return False
    if _iş and _iş.is_alive():
        return True
    _durum.update(aktif=True, hata="", denendi=False)
    durdur = threading.Event()
    _iş = threading.Thread(target=_dongu, args=(durdur,), name="mqtt-push", daemon=True)
    _iş.start()
    return True
