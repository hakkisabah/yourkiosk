<script setup lang="ts">
/**
 * SOL PANEL — nöbetçi listesi (Qt `ui/nobet_widget.py` + `pharmacy_app.setup_left_panel`).
 *
 * · Satır yüksekliği `MAKS_GORUNUR_SATIR` (5) tabanına göre SABİTTİR: az kayıtta büyümez,
 *   çok kayıtta küçülmez.
 * · Kayıt sayısı tabanı aşarsa liste kaydırılır ve **vurgulanan satırı takip eder**;
 *   kaydırma, orta geçişle AYNI ANDA ve AYNI sürede (1800 ms, InOutCubic) yapılır.
 */
import { onMounted, ref, watch } from 'vue'

import { inOutCubic } from '@/veri/kusak'
import { elle } from '@/stiller/olcu'

const props = defineProps<{
  kayitlar: Array<{ eczane: string; ikincil: string }>
  index: number
  kaydirma: number
  animasyonMs: number
}>()

const liste = ref<HTMLElement | null>(null)
let rafKimlik = 0

/** Kaydırmayı Qt gibi yumuşatır (hedefe InOutCubic ile, verilen sürede). */
function yumusakKaydir(hedef: number, sure: number): void {
  const el = liste.value
  if (!el) return
  cancelAnimationFrame(rafKimlik)
  const baslangic = el.scrollTop
  const fark = hedef - baslangic
  if (Math.abs(fark) < 1) {
    el.scrollTop = hedef
    return
  }
  const t0 = performance.now()
  const adim = (t: number): void => {
    const oran = Math.min(1, (t - t0) / sure)
    el.scrollTop = baslangic + fark * inOutCubic(oran)
    if (oran < 1) rafKimlik = requestAnimationFrame(adim)
  }
  rafKimlik = requestAnimationFrame(adim)
}

onMounted(() => {
  if (liste.value) liste.value.scrollTop = props.kaydirma
})

watch(
  () => props.kaydirma,
  (hedef) => yumusakKaydir(hedef, props.animasyonMs),
)

const satirBosluk = Number(elle('sol.satir_bosluk', 10))
</script>

<template>
  <div class="sol-panel" :class="{ kaydirmasiz: kayitlar.length <= 5 }">
    <div ref="liste" class="liste" :style="{ gap: `${satirBosluk}px` }">
      <div
        v-for="(kayit, i) in kayitlar"
        :key="`${i}-${kayit.eczane}`"
        class="satir"
        :class="{ aktif: i === index }"
      >
        <div class="ad">{{ kayit.eczane }}</div>
        <div class="ikincil">{{ kayit.ikincil }}</div>
      </div>
    </div>
  </div>
</template>
