"""Cihaza özgü ayarların yayınla EZİLMEMESİ (i5 bulgusu, PR #81).

Ölçülen risk: panel "tam belge" kuralıyla `tetik.push_parola: ""` / `push_anahtar: ""` gibi
varsayılanları yayınlıyordu; kiosk birleştirmesinde bu boş değerler YEREL MQTT kimliğini eziyor,
yani panelde kaydetmek cihazın bağlantısını sessizce koparıyordu. Aynı sınıf: uzaktan
`calistirma.komut_imza_zorunlu=False` yazılabilmesi imza denetimini tüm cihazlarda kaldırıyordu.
"""

from __future__ import annotations

import ayarlar


def test_yayin_mqtt_kimligini_ve_komut_dizelerini_ezemez() -> None:
    yerel = {
        "tetik": {
            "push_aktif": True,
            "push_broker": "mqtt.cihaz.local",
            "push_port": 8883,
            "push_konu": "kiosk/cihaz-1",
            "push_kullanici": "cihaz-1",
            "push_parola": "yerel-parola",
            "push_ca": "/etc/ssl/ca.pem",
            "push_sertifika": "/etc/ssl/cihaz.crt",
            "push_anahtar": "/etc/ssl/cihaz.key",
        },
        "calistirma": {
            "komut_imza_zorunlu": True,
            "komut_kuru_calistirma": False,
            "komut_zaman_asimi_s": 60,
            "komut_yeniden_baslat": "systemctl reboot",
            "komut_uygulama_yeniden_baslat": "systemctl restart yourkiosk-kiosk",
            "komut_ekrani_yenile": "",
        },
    }
    uzak = {
        "tetik": {
            "push_aktif": False,
            "push_broker": "",
            "push_port": 1883,
            "push_konu": "",
            "push_kullanici": "",
            "push_parola": "",
            "push_ca": "",
            "push_sertifika": "",
            "push_anahtar": "",
        },
        "calistirma": {
            "komut_imza_zorunlu": False,
            "komut_kuru_calistirma": True,
            "komut_zaman_asimi_s": 5,
            "komut_yeniden_baslat": "systemctl poweroff",
            "komut_uygulama_yeniden_baslat": "systemctl stop yourkiosk-kiosk",
            "komut_ekrani_yenile": "echo ele-gecirildi",
        },
    }
    sonuc = ayarlar.birlestir(yerel, uzak)
    for anahtar, deger in yerel["tetik"].items():
        assert sonuc["tetik"][anahtar] == deger, f"yayın tetik.{anahtar} değerini ezdi"
    for anahtar, deger in yerel["calistirma"].items():
        assert sonuc["calistirma"][anahtar] == deger, f"yayın calistirma.{anahtar} değerini ezdi"


def test_yerel_oncelikli_listesi_sema_anahtarlariyla_tutarli() -> None:
    """Koruma listesi bayatlamasın: her anahtar gerçekten bir ayar anahtarı olmalı."""
    sema_anahtarlari = {f"{grup}.{anahtar}" for grup, anahtar in ayarlar.KURALLAR}
    bilinmeyen = sorted(ayarlar.YEREL_ONCELIKLI - sema_anahtarlari)
    assert bilinmeyen == [], f"YEREL_ONCELIKLI'de şemada olmayan anahtar(lar): {bilinmeyen}"

    beklenen_sirlar = {
        f"tetik.push_{ad}"
        for ad in ("aktif", "broker", "port", "konu", "kullanici", "parola", "ca", "sertifika", "anahtar")
    }
    beklenen_komutlar = {
        f"calistirma.komut_{ad}"
        for ad in (
            "imza_zorunlu",
            "kuru_calistirma",
            "zaman_asimi_s",
            "yeniden_baslat",
            "uygulama_yeniden_baslat",
            "ekrani_yenile",
        )
    }
    eksik = (beklenen_sirlar | beklenen_komutlar) - set(ayarlar.YEREL_ONCELIKLI)
    assert eksik == set(), f"korunmayan cihaza özgü anahtar(lar): {sorted(eksik)}"
