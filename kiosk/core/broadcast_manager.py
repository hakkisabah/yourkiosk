"""Yayın yöneticisi: zaman aralığında olan yayınları seçer.

Referans mantık korunur (start <= şimdi <= end), ancak:
  * çıplak `except: continue` yerine tür bazlı yakalama + günlük,
  * ISO biçimi (mikrosaniyeli) ve boşluklu ISO birlikte desteklenir.
"""

import logging
from datetime import datetime

import config
from core.yayin_kapsam import kapsam_uygun
from security.veri_dogrulama import liste_sinirla

log = logging.getLogger("kiosk.yayin")


class BroadcastManager:
    def __init__(self, app_instance):
        self.app_instance = app_instance
        self.active_yayin_list = []
        self.current_yayin_idx = 0

    @staticmethod
    def _zaman(metin):
        if not isinstance(metin, str) or not metin.strip():
            return None
        try:
            return datetime.fromisoformat(metin.strip().replace("Z", "+00:00"))
        except ValueError:
            for bicim in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
                try:
                    return datetime.strptime(metin.strip(), bicim)
                except ValueError:
                    continue
        return None

    def get_active_yayinlar(self, yayinlar, simdi=None, ilce_id="", bolge_id="", cihaz_id=""):
        """Aktif yayınlar — KAPSAM süzgeciyle (ilçe/bölge/cihaz).

        Kapsam alanları boşsa (bugünkü veri) davranış değişmez: tüm cihazlar görür.
        Eşleşmeyen yayın hiç indirilmez → cihaz bant genişliği ve CDN maliyeti düşer.
        """
        an = simdi or datetime.now()
        aktif = []
        for yayin in yayinlar or []:
            if not isinstance(yayin, dict):
                continue
            if not kapsam_uygun(yayin, ilce_id, bolge_id, cihaz_id):
                continue
            baslangic = self._zaman(yayin.get("start"))
            bitis = self._zaman(yayin.get("end"))
            if baslangic is None or bitis is None:
                log.debug("yayın zamanı okunamadı, atlanıyor: %r", yayin.get("start"))
                continue
            try:
                if baslangic <= an <= bitis:
                    aktif.append(yayin)
            except TypeError:  # saat dilimi uyuşmazlığı: çökme yerine atla
                log.warning("yayın zaman dilimi uyuşmuyor, atlanıyor: %r", yayin.get("start"))
        # Aynı anda işlenecek yayın sayısı sınırlanır (bozuk veri ekranı kilitlemesin)
        return liste_sinirla(aktif, en_buyuk=getattr(config, "MAX_AKTIF_YAYIN", 20), etiket="aktif yayın")
