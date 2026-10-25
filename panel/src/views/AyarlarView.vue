<script setup lang="ts">
/**
 * GENEL AYARLAR (ayarlar.json) — tüm cihazlar için varsayılanlar.
 * İlçe/bölge/cihaz bazında farklılık için "Kapsam Ayarları" ekranını kullanın.
 */
import { kopya } from '@/domain/kopya'
import { computed, ref, watch } from 'vue'

import AyarFormu from '@/components/AyarFormu.vue'
import { DOSYALAR } from '@/aws/config'
import { tamBelge } from '@/domain/ayarBelgesi'
import { gruplar, kapsamGrubuMu } from '@/domain/sema'
import { useDosyalar, type AyarBelgesi } from '@/stores/dosyalar'

const dosyalar = useDosyalar()
const sekme = ref(gruplar[0]?.ad ?? 'ozellikler')
const taslak = ref<AyarBelgesi>(kopya(dosyalar.ayarlarBelgesi))

watch(
  () => dosyalar.ayarlar.veri,
  (yeni) => (taslak.value = kopya(yeni ?? {})),
  { deep: true },
)

const etkin = computed<Record<string, unknown>>(() => {
  const belge: Record<string, unknown> = {}
  for (const g of gruplar) for (const a of g.anahtarlar) belge[a.tam] = taslak.value?.[g.ad]?.[a.ad] ?? a.varsayilan
  return belge
})

const degisiklikler = computed<Record<string, unknown>>(() => {
  const farklar: Record<string, unknown> = {}
  const kaynak = dosyalar.ayarlarBelgesi
  for (const g of gruplar) {
    for (const a of g.anahtarlar) {
      const yeni = taslak.value?.[g.ad]?.[a.ad]
      if (yeni !== undefined && yeni !== kaynak?.[g.ad]?.[a.ad]) farklar[a.tam] = yeni
    }
  }
  return farklar
})

const kirli = computed(() => Object.keys(degisiklikler.value).length > 0)

function guncelle(tam: string, deger: unknown): void {
  const [grup, anahtar] = tam.split('.')
  taslak.value = { ...taslak.value, [grup]: { ...(taslak.value[grup] ?? {}), [anahtar]: deger } }
}

function sifirla(): void {
  taslak.value = kopya(dosyalar.ayarlarBelgesi)
}

async function kaydet(): Promise<void> {
  // TAM BELGE (kullanıcı kararı): şemadaki her anahtar yazılır; girilmemiş olanlar varsayılanıyla.
  await dosyalar.kaydet('ayarlar', DOSYALAR.ayarlar, tamBelge(taslak.value))
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Genel Ayarlar</h2>
        <div class="text-body-2 text-medium-emphasis">
          <code>ayarlar.json</code> — tüm cihazlar için geçerli varsayılanlar. Kiosk bu dosya yoksa
          <code>config.py</code> değerlerini kullanır. <strong>Kaydet, dosyayı tam belge olarak yazar</strong>
          (şemadaki her anahtar; dokunulmayanlar varsayılanıyla) — böylece dosya tek başına okunabilir.
        </div>
      </div>
      <v-spacer />
      <v-chip v-if="kirli" color="warning" variant="tonal" class="mr-3">{{ Object.keys(degisiklikler).length }} değişiklik</v-chip>
      <v-btn class="mr-2" variant="text" prepend-icon="mdi-undo" :disabled="!kirli" @click="sifirla">Geri al</v-btn>
      <v-btn color="primary" prepend-icon="mdi-content-save" :loading="dosyalar.mesgul" :disabled="!kirli" @click="kaydet">
        Kaydet ({{ DOSYALAR.ayarlar }})
      </v-btn>
    </div>

    <v-tabs v-model="sekme" density="comfortable" show-arrows>
      <v-tab v-for="g in gruplar" :key="g.ad" :value="g.ad">
        {{ g.baslik }}
        <v-chip v-if="kapsamGrubuMu(g.ad)" size="x-small" variant="text" class="ml-2">kapsamlanabilir</v-chip>
      </v-tab>
    </v-tabs>

    <v-tabs-window v-model="sekme" class="mt-4">
      <v-tabs-window-item v-for="g in gruplar" :key="g.ad" :value="g.ad">
        <v-card>
          <v-card-title class="d-flex align-center">
            <span class="text-subtitle-1">{{ g.baslik }}</span>
          </v-card-title>
          <v-card-text>
            <v-alert v-if="kapsamGrubuMu(g.ad)" type="info" variant="tonal" density="compact" class="mb-4">
              Bu gruptaki anahtarlar ilçe/bölge/cihaz bazında geçersiz kılınabilir
              (<router-link to="/kapsam">Kapsam Ayarları</router-link>).
            </v-alert>
            <AyarFormu
              :grup="g"
              :etkin="etkin"
              :degisiklikler="degisiklikler"
              :gelismis-goster="g.ad === 'gelismis'"
              @guncelle="guncelle"
            />
          </v-card-text>
        </v-card>
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>
