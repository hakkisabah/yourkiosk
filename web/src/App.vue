<script setup lang="ts">
/**
 * KIOSK KÖK BİLEŞENİ — Qt `pharmacy_app.py` karşılığı.
 *
 * · Sahne 1920×1080 sabittir; ekran yüksekliğine göre ölçeklenir (Qt: `scale = screen_h/1080`).
 * · Veri, ayarlar, zamanlayıcılar ve döngü `src/kiosk.ts` içindedir (Qt `manage_loop`).
 * · Cihaz kimliği URL'den gelir: `index.html?clientID=<cihaz>&veri=yerel|https&taban=<adres>`
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import Kusak from '@/bilesenler/Kusak.vue'
import OrtaPanel from '@/bilesenler/OrtaPanel.vue'
import SolPanel from '@/bilesenler/SolPanel.vue'
import YayinGoruntusu from '@/bilesenler/YayinGoruntusu.vue'
import { createKiosk } from '@/kiosk'
import { Onbellek } from '@/veri/onbellek'
import { parametreleriOku, VeriKaynagi } from '@/veri/kaynak'
import { elle, sahneOlcegi, sabit } from '@/stiller/olcu'

const secenekler = parametreleriOku(window.location.search)
const onbellek = new Onbellek(sabit('ONBELLEK_GORSEL_SAKLAMA_GUN', 2))
const kaynak = new VeriKaynagi({ secenekler, onbellek, yerelTaban: '' })
const kiosk = createKiosk({ kaynak, onbellek })
const { durum } = kiosk

const olcek = ref(1)
const gorselBlob = ref('')
const logoVar = ref(false)
/** Ekran üstü teşhis (kiosk modunda konsol görünmez → `d` tuşu) */
const taniAcik = ref(false)
const taniSatirlari = computed(() => {
  const kayit = durum.kayitlar[durum.index]
  return [
    `sayfa        : ${window.location.href}`,
    `ölçü         : --ekran-y=${window.getComputedStyle(document.documentElement).getPropertyValue('--ekran-y').trim()} --ekran-g=${window.getComputedStyle(document.documentElement).getPropertyValue('--ekran-g').trim()} ölçek=${olcek.value}`,
    `hazır        : ${durum.hazir}   hata: ${durum.hata || '—'}`,
    `cihaz kimliği: ${secenekler.clientID || '(yok)'}   veri modu: ${secenekler.veri}`,
    `konum        : ilçe=${durum.konum.ilceId ?? '?'} bölge=${durum.konum.bolgeId ?? '?'} bulundu=${durum.konum.bulundu}`,
    `gün bloğu    : ${durum.gunAnahtari || '—'}`,
    `kayıt        : ${durum.kayitlar.length} (gösterilen ${durum.index + 1}.) → ${kayit ? kayit.eczane : '—'}`,
    `sol panel    : kaydırma=${durum.kaydirma}px · satır yüksekliği ${window.getComputedStyle(document.documentElement).getPropertyValue('--satir-yuksekligi').trim()} · 5'ten fazlaysa kayar`,
    `yayın modu   : ${durum.yayinModu} · havuz=${durum.yayinlar.length} · görsel=${durum.gorselUrl || '—'}`,
    `önbellek     : ${onbellek.etkin ? 'açık' : 'kapalı'} · damga=${durum.damga || '—'}`,
    `özellikler   : ${JSON.stringify(durum.ozellikler)}`,
    `kuşak        : ${durum.kusak.gorunur ? 'görünür' : 'kapalı'} · "${String(durum.kusak.metin).slice(0, 60)}"`,
    `saat         : ${JSON.stringify(durum.saat)}`,
    '— son günlük —',
    ...durum.gunluk.slice(-6).map((s) => `  ${s}`),
  ]
})

function tusaBasildi(olay: KeyboardEvent): void {
  if (olay.key === 'd' || olay.key === 'D' || olay.key === 'F8') taniAcik.value = !taniAcik.value
}

/** Sahne ölçeği + logo denetimi (logo.png yoksa alan boş kalır — Qt ile aynı). */
function olcekle(): void {
  olcek.value = sahneOlcegi(window.innerHeight)
}
function logoTespit(): void {
  const gorsel = new Image()
  gorsel.onload = () => (logoVar.value = true)
  gorsel.onerror = () => (logoVar.value = false)
  gorsel.src = '/logo.png'
}

/** Yayın görselini cihaz önbelleğinden (blob) hazırlar. */
async function gorseliHazirla(url: string): Promise<void> {
  if (gorselBlob.value) URL.revokeObjectURL(gorselBlob.value)
  gorselBlob.value = ''
  if (!url) return
  const govde = await kaynak.gorsel(url, durum.damga)
  if (govde) gorselBlob.value = URL.createObjectURL(new Blob([govde]))
}

watch(
  () => durum.gorselUrl,
  (url) => void gorseliHazirla(url),
)

onMounted(async () => {
  olcekle()
  window.addEventListener('resize', olcekle)
  window.addEventListener('keydown', tusaBasildi)
  logoTespit()
  await onbellek.bagla()
  kiosk.baslat()
})

onBeforeUnmount(() => {
  kiosk.durdur()
  window.removeEventListener('resize', olcekle)
  window.removeEventListener('keydown', tusaBasildi)
  if (gorselBlob.value) URL.revokeObjectURL(gorselBlob.value)
})

const animasyonMs = elle('animasyon.sure_ms', 1800) as number
</script>

<template>
  <div id="sahne-kap">
    <!-- Hata kartı: beyaz ekran yerine okunabilir mesaj (Qt log + panel davranışıyla aynı ruh) -->
    <div v-if="durum.hata && !durum.hazir" class="hata-kart">
      <div><strong>yourkiosk</strong> — veri yüklenemedi</div>
      <div>{{ durum.hata }}</div>
      <div>
        Cihaz kimliği: <code>{{ secenekler.clientID || '(URL\'de clientID yok)' }}</code>
      </div>
      <div>
        Başlatma biçimi:
        <code>index.html?clientID=&lt;cihaz&gt;&amp;veri={{ secenekler.veri }}</code>
      </div>
    </div>

    <div v-else id="sahne" :style="{ transform: `scale(${olcek})` }">
      <!-- NÖBET EKRANI (Qt: nobet_widget) -->
      <template v-if="!durum.yayinModu">
        <SolPanel
          v-if="durum.ozellikler.nobet_listesi"
          :kayitlar="durum.kayitlar"
          :index="durum.index"
          :kaydirma="durum.kaydirma"
          :animasyon-ms="animasyonMs"
        />
        <div v-if="durum.ozellikler.nobet_listesi" class="dikey-cizgi" />
        <OrtaPanel
          :bloklar="durum.bloklar"
          :konumlar="durum.konumlar"
          :aktif-blok="durum.aktifBlok"
          :animasyonlu="durum.animasyonlu"
          :saat="durum.saat"
          :logo-var="logoVar"
        />
      </template>

      <!-- YAYIN EKRANI (Qt: yayin_widget) — nöbet listesi kapalıysa da bu görünüm kalır -->
      <template v-else>
        <YayinGoruntusu :src="gorselBlob" />
      </template>

      <!-- EKRAN ÜSTÜ TEŞHİS: kiosk modunda konsol görünmez → `d` tuşu ile aç/kapa -->
      <pre v-if="taniAcik" class="tani-kart">{{ taniSatirlari.join('\n') }}</pre>

      <!-- KAYAN YAZI KUŞAĞI: yalnızca yayın görünümünde, görselin ÜSTÜNDE -->
      <Kusak
        v-if="durum.yayinModu && durum.kusak.gorunur"
        :metin="durum.kusak.metin"
        :x="durum.kusak.x"
        @genislik="kiosk.yaziGenisligiAyarla"
      />
    </div>
  </div>
</template>
