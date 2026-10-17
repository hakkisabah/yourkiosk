<script setup lang="ts">
/**
 * KAYAN YAZI KUŞAĞI (Qt `ui/yayin_widget.py` + `core/ticker.py`).
 *
 * Konum `x` Qt formülüyle hesaplanır: `x = şerit − oran×(şerit + yazı)`.
 * Tekli modda kayıt ortaya girip bekler ve sola çıkar (faz makinesi `kiosk.ts`),
 * liste modunda sağdan sola sürekli akar. Şerit yayın görselinin ÜSTÜNDEDİR.
 */
import { onMounted, ref, watch } from 'vue'

const props = defineProps<{ metin: string; x: number }>()
const emit = defineEmits<{ genislik: [number] }>()

const yazi = ref<HTMLElement | null>(null)

function olc(): void {
  emit('genislik', yazi.value?.getBoundingClientRect().width ?? 0)
}

onMounted(olc)
watch(() => props.metin, () => requestAnimationFrame(olc))
</script>

<template>
  <div class="kusak">
    <div ref="yazi" class="yazi" :style="{ transform: `translateX(${x}px)` }">{{ metin }}</div>
  </div>
</template>
