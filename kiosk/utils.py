"""Yardımcılar: telefon biçimlendirme + tarih ayrıştırma.

`format_phone` referans sürümle **birebir aynıdır** (davranış değişmedi).

Veri okuma işi artık `core/veri_kaynagi.py` içindedir (lastupdate/match/
lastSystemData/makinebilgileri dosyaları); burada yalnızca biçimlendirme ve
tarih yardımcıları kalır.
"""

from datetime import datetime

import config

TARIH_BICIMLERI = ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y")


def format_phone(phone_str):
    if not phone_str: return "-"
    nums = "".join(filter(str.isdigit, str(phone_str)))
    if len(nums) == 10 and not nums.startswith("0"):
        nums = "0" + nums
    if len(nums) == 11:
        return f"{nums[0:4]} {nums[4:7]} {nums[7:9]} {nums[9:11]}"
    return phone_str


def parse_tarih(metin):
    """Bilinen biçimlerden birini datetime'a çevirir; olmazsa None."""
    if not isinstance(metin, str) or not metin.strip():
        return None
    metin = metin.strip()
    try:
        return datetime.fromisoformat(metin.replace("Z", "+00:00"))
    except ValueError:
        pass
    for bicim in TARIH_BICIMLERI:
        try:
            return datetime.strptime(metin, bicim)
        except ValueError:
            continue
    return None


def nobet_degisim_saati():
    """Nöbet değişim saati (config): (saat, dakika)."""
    return tuple(config.NOBET_DEGISIM_SAATI)
