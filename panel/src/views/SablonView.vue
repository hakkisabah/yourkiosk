<script setup lang="ts">
/** ŞABLON — sablon.json (cihazın doldurduğu veri iskeleti) ve ham veri görünümü. */
import { computed } from 'vue'

import { DOSYALAR } from '@/aws/config'
import JsonEditor from '@/components/JsonEditor.vue'
import { useDosyalar } from '@/stores/dosyalar'

const dosyalar = useDosyalar()

const sablon = computed(() => dosyalar.sablon.veri ?? {})
const bosMu = computed(() => !Object.keys(sablon.value).length)

async function kaydet(belge: unknown): Promise<void> {
  await dosyalar.kaydet('sablon', DOSYALAR.sablon, belge)
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Şablon</h2>
        <div class="text-body-2 text-medium-emphasis">
          <code>{{ DOSYALAR.sablon }}</code> — cihazın veri kaynağından doldurduğu iskelet
          (alan adları, sıralama, biçim). Alan adlarını değiştirirseniz veri dosyasının da
          aynı adları kullanması gerekir.
        </div>
      </div>
      <v-spacer />
      <v-btn variant="text" prepend-icon="mdi-refresh" @click="dosyalar.dosyaYukle('sablon', DOSYALAR.sablon)">Yeniden oku</v-btn>
    </div>

    <v-alert v-if="bosMu" type="info" variant="tonal" class="mb-4">
      Şablon okunamadı (dosya kovada yok olabilir). Kiosk tarafında şablonun bir kopyası repoda bulunur.
    </v-alert>

    <JsonEditor
      :baslik="DOSYALAR.sablon"
      aciklama="Veri şablonu — JSON olarak düzenleyin, kaydettiğinizde cihaz bir sonraki turda kullanır."
      :belge="sablon"
      :yuksek="22"
      @kaydet="kaydet"
    />
  </div>
</template>
