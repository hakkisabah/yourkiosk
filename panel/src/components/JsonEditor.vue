<script setup lang="ts">
/** JSON metin düzenleyici — doğrular, kirli durumu gösterir, kaydetmeyi iletir. */
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    baslik: string
    aciklama?: string
    belge: unknown
    yuksek: number
    kaydetEtiketi?: string
  }>(),
  { aciklama: '', kaydetEtiketi: 'Kaydet' },
)
const emit = defineEmits<{ kaydet: [belge: unknown] }>()

const metin = ref(JSON.stringify(props.belge ?? {}, null, 2))
const hata = ref<string | null>(null)

watch(
  () => props.belge,
  (yeni) => {
    metin.value = JSON.stringify(yeni ?? {}, null, 2)
    hata.value = null
  },
)

const kirli = computed(() => {
  try {
    return JSON.stringify(JSON.parse(metin.value)) !== JSON.stringify(props.belge ?? {})
  } catch {
    return true
  }
})

function dogrulaVeKaydet(): void {
  try {
    const cozulen = JSON.parse(metin.value)
    if (cozulen === null || typeof cozulen !== 'object') {
      hata.value = 'Kök değer bir nesne olmalı'
      return
    }
    hata.value = null
    emit('kaydet', cozulen)
  } catch (e) {
    hata.value = `JSON çözülemedi: ${(e as Error).message}`
  }
}
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      {{ baslik }}
      <v-chip v-if="kirli" size="small" color="warning" variant="tonal" class="ml-3">kaydedilmemiş değişiklik</v-chip>
      <v-spacer />
      <v-btn size="small" variant="text" prepend-icon="mdi-undo" :disabled="!kirli" @click="metin = JSON.stringify(belge ?? {}, null, 2)">
        Geri al
      </v-btn>
      <v-btn color="primary" size="small" prepend-icon="mdi-content-save" :disabled="!kirli" @click="dogrulaVeKaydet">
        {{ kaydetEtiketi }}
      </v-btn>
    </v-card-title>
    <v-card-subtitle v-if="aciklama">{{ aciklama }}</v-card-subtitle>
    <v-card-text>
      <v-textarea
        v-model="metin"
        :rows="yuksek"
        auto-grow
        no-resize
        spellcheck="false"
        variant="outlined"
        :error-messages="hata ?? ''"
        style="font-family: monospace; font-size: 0.85rem"
      />
    </v-card-text>
  </v-card>
</template>
