<script setup lang="ts">
/**
 * YAYIN HEDEF SEÇİMİ — ilçe / bölge / cihaz.
 *
 * Kurallar `kiosk/core/model.py` → `panel/src/domain/model.ts` (tek kaynak):
 *  • hepsi boş = tüm cihazlar,
 *  • birlikte seçilirse VE,
 *  • cihaz kendi konumunu bilmiyorsa hedefli yayın gösterilmez.
 *
 * Bileşen yalnız değer üretir; kaydetme çağıran taraftadır (VeriView).
 */
import { computed } from 'vue'

import type { Secenek } from '@/domain/hedef'

const props = defineProps<{
  modelValue: { ilceId: string; bolgeId: string; cihazId: string }
  ilceler: Secenek[]
  bolgeler: Secenek[]
  cihazlar: Secenek[]
  toplamCihaz?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [deger: { ilceId: string; bolgeId: string; cihazId: string }]
}>()

const deger = computed({
  get: () => props.modelValue,
  set: (yeni: { ilceId: string; bolgeId: string; cihazId: string }) => emit('update:modelValue', yeni),
})

function ayarla(alan: 'ilceId' | 'bolgeId' | 'cihazId', yeni: string | null): void {
  const sonuc = { ...deger.value, [alan]: yeni ?? '' }
  // Üst seviye değişince alt seviyeler temizlenir (ilçe değişti → bölge/cihaz anlamsız)
  if (alan === 'ilceId') {
    sonuc.bolgeId = ''
    sonuc.cihazId = ''
  }
  if (alan === 'bolgeId') sonuc.cihazId = ''
  deger.value = sonuc
}

const hedefMetni = computed(() => {
  const { ilceId, bolgeId, cihazId } = deger.value
  if (!ilceId && !bolgeId && !cihazId) {
    return props.toplamCihaz ? `Tüm cihazlar (${props.toplamCihaz})` : 'Tüm cihazlar'
  }
  const adlar = [ilceId, bolgeId, cihazId].filter(Boolean)
  return `Hedefli: ${adlar.length === 1 && cihazId ? `cihaz ${cihazId}` : `${adlar.length} seviye`}`
})
</script>

<template>
  <div>
    <div class="d-flex flex-wrap ga-3">
      <v-select
        :model-value="deger.ilceId"
        :items="ilceler"
        item-title="baslik"
        item-value="deger"
        label="İlçe"
        density="compact"
        clearable
        hide-details
        style="min-width: 260px"
        @update:model-value="(v: string | null) => ayarla('ilceId', v)"
      />
      <v-select
        :model-value="deger.bolgeId"
        :items="bolgeler"
        item-title="baslik"
        item-value="deger"
        label="Bölge"
        density="compact"
        clearable
        hide-details
        :disabled="!deger.ilceId"
        :placeholder="deger.ilceId ? 'tüm bölgeler' : 'önce ilçe seçin'"
        style="min-width: 240px"
        @update:model-value="(v: string | null) => ayarla('bolgeId', v)"
      />
      <v-select
        :model-value="deger.cihazId"
        :items="cihazlar"
        item-title="baslik"
        item-value="deger"
        label="Cihaz (isteğe bağlı)"
        density="compact"
        clearable
        hide-details
        :disabled="!deger.ilceId"
        :placeholder="deger.ilceId ? 'tüm cihazlar' : 'önce ilçe seçin'"
        style="min-width: 240px"
        @update:model-value="(v: string | null) => ayarla('cihazId', v)"
      />
    </div>
    <div class="text-caption text-medium-emphasis mt-2">
      <v-icon size="small" class="mr-1">mdi-bullseye-arrow</v-icon>{{ hedefMetni }} ·
      boş bırakılan seviye kısıt sayılmaz (hepsi eşleşmeli)
    </div>
  </div>
</template>
