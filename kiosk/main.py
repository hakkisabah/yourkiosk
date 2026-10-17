"""Uygulama giriş noktası.

Referans davranış korunur (tam ekran, çerçevesiz, her zaman üstte). Ek olarak:
günlük dosyası, Qt eklentisi karantinası ve güvenlik öz kontrolü.

Güvenlik sırası (önemli):
  1. Qt yüklenmeden önce ortam sertleştirilir (eklenti dizini sabitlenir),
  2. riskli Qt eklentileri (svg/pdf/tiff/gif, vnc platformu) karantinaya alınır —
     bunlar `QApplication` kurulmadan önce yapılmalıdır,
  3. `--guvenlik-denetimi` verilmişse arayüz açılmaz, ölçüm raporu yazdırılır.
"""

import argparse
import logging
import sys

import config
import ayarlar
from logging_setup import gunluk_kur
from security.qt_sertlestirme import karantinaya_al, ortam_sertlestir


def main(argv=None):
    ayristirici = argparse.ArgumentParser(description="Eczane nöbet ekranı (kiosk)")
    ayristirici.add_argument("--pencere", action="store_true", help="tam ekran yerine pencere olarak aç")
    ayristirici.add_argument("--log-seviyesi", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    ayristirici.add_argument(
        "--guvenlik-denetimi",
        action="store_true",
        help="arayüzü açmadan güvenlik ayarlarını ölç ve raporla (hata varsa çıkış kodu 1)",
    )
    ayristirici.add_argument(
        "--karantina-yok",
        action="store_true",
        help="riskli Qt eklentilerini karantinaya alma (varsayılan: alınır)",
    )
    ayristirici.add_argument(
        "--ayarlari-yaz",
        action="store_true",
        help="etkin ayarları ayarlar.json dosyasına yaz (yönetim paneli/elle düzenleme için başlangıç)",
    )
    ayarlar_hazir = ayristirici.parse_args(argv)

    # --- 0) çalışma zamanı ayarları (ayarlar.json) ----------------------------
    ayar_ozeti = ayarlar.uygula()
    if ayar_ozeti.get("gecersiz"):
        for satir in ayar_ozeti["gecersiz"]:
            print(f"ayar uyarısı: {satir}")

    gunluk_kur(config.LOG_DOSYASI, getattr(logging, ayarlar_hazir.log_seviyesi))
    log = logging.getLogger("kiosk")

    if ayarlar_hazir.ayarlari_yaz:
        hedef = ayarlar.yaz()
        print(f"etkin ayarlar yazıldı: {hedef}")
        ozet = ayarlar.ozet()
        for ad, deger in ozet["ozellikler"].items():
            print(f"  özellik {ad}: {'açık' if deger else 'KAPALI'}")
        return 0

    # --- 1) gösterim modu: tarayıcı (Chromium kiosk) --------------------------
    #     Bu modda Qt HİÇ yüklenmez; sayfa aynı veriyi, aynı ayarları ve aynı
    #     kapsam kurallarını kendisi çeker. Cihaz kimliği URL'de gönderilir.
    if str(getattr(config, "CALISTIRMA_MODU", "qt")).lower() == "tarayici":
        from core.tarayici import calistir as tarayici_calistir

        log.info(
            "gösterim modu: tarayıcı (Chromium kiosk) · web klasörü: %s · veri modu: %s",
            config.WEB_KLASORU,
            config.WEB_VERI_MODU,
        )
        return tarayici_calistir(ayarlar_hazir)

    # --- 2) Qt yüklenmeden önce ortam + eklenti/kütüphane sertleştirmesi ---------
    ortam_sertlestir()
    if not ayarlar_hazir.karantina_yok:
        if config.QT_EKLENTI_KARANTINA:
            karantinaya_al(etkin=True, modul=bool(getattr(config, "QT_MODUL_KARANTINA", True)))
        else:
            karantinaya_al(etkin=False)

    # --- 3) yalnızca denetim isteniyorsa arayüz açılmaz ------------------------
    if ayarlar_hazir.guvenlik_denetimi:
        from security.denetim import denetim_kodu, rapor_metni

        print(rapor_metni())
        return denetim_kodu()

    from PyQt6.QtWidgets import QApplication

    from pharmacy_app import PharmacyApp

    log.info("kiosk başlatılıyor · veri kaynağı: %s", config.KAYNAK)
    log.info(
        "özellikler: nöbet listesi=%s, yayınlar=%s, kayan yazı=%s, saat/tarih=%s",
        ayarlar.ozellik("nobet_listesi"),
        ayarlar.ozellik("yayinlar"),
        ayarlar.ozellik("kayan_yazi"),
        ayarlar.ozellik("saat_tarih"),
    )
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    pencere = PharmacyApp(tam_ekran=not ayarlar_hazir.pencere)
    log.info("arayüz hazır (platform=%s)", app.platformName())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
