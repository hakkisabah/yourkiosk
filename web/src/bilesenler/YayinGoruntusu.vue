<script setup lang="ts">
/**
 * YAYIN GÖRÜNTÜSÜ — tam ekran görsel (Qt `ui/yayin_widget.py`).
 *
 * · Görsel alanı TAMAMEN doldurur (Qt `setScaledContents(True)` → oran korunmaz).
 * · Görsel cihaz önbelleğinden gelir (blob); internet yalnızca ilk indirmede kullanılır.
 * · Zemin siyah; kuşak bu görüntünün ÜSTÜNDE ayrı bir katmandır.
 */
defineProps<{ src: string }>()
</script>

<template>
  <div class="yayin">
    <img v-if="src" :src="src" alt="" />
  </div>
</template>
