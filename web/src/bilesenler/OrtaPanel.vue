<script setup lang="ts">
/**
 * ORTA PANEL — nöbet detayı (Qt `components/right_content_block.py`).
 *
 * Sıra ve ölçüler Qt ile aynıdır: üst şerit (125) → viewport (955) içinde
 * tarih aralığı (45) → detay kutusu (480) → kırmızı çizgi (3) → alt şerit (640:
 * logo 1192 + saat kutusu 226). İki içerik bloğu dikey kayarak yer değiştirir:
 * çıkan **aşağı**, giren **yukarıdan** (1800 ms InOutCubic).
 */
import { computed } from 'vue'

import { ortaMetinler } from '@/kiosk'
import type { EkranKaydi } from '@/veri/ekran'

const props = defineProps<{
  bloklar: Array<EkranKaydi | null>
  konumlar: number[]
  aktifBlok: number
  animasyonlu: boolean
  saat: { saat: string; tarih: string; gun: string }
  logoVar: boolean
}>()

const blokMetinleri = computed(() => props.bloklar.map((b) => (b ? ortaMetinler(b) : null)))
</script>

<template>
  <div class="orta-panel">
    <div class="serit-bandi" />
    <div class="viewport">
      <div
        v-for="(metin, i) in blokMetinleri"
        :key="i"
        class="blok"
        :class="{ kayan: animasyonlu }"
        :style="{ transform: `translateY(${konumlar[i] ?? 0}px)`, zIndex: i === aktifBlok ? 2 : 1 }"
      >
        <template v-if="metin">
          <div class="tarih-aralik">{{ metin.aralik }}</div>
          <div class="detay">
            <div class="ad">{{ metin.ad }}</div>
            <div class="adres">{{ metin.adres }}</div>
            <div class="telefon">{{ metin.telefon }}</div>
            <div class="esnek" />
          </div>
          <div class="yatay-cizgi" />
          <div class="alt-serit">
            <div class="logo-kap">
              <img v-if="logoVar" :src="'/logo.png'" alt="" />
            </div>
            <div class="saat-kutu">
              <div class="saat">{{ saat.saat }}</div>
              <div class="tarih">{{ saat.tarih }}</div>
              <div class="gun">{{ saat.gun }}</div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
