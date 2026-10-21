<script setup lang="ts">
/**
 * GELİŞMİŞ — JSON boyut / derinlik / düğüm sınırları ve ağ kısıtları.
 * Bunlar güvenlik ve dayanıklılık sınırlarıdır; büyük veri (20-30 MB) kullanıyorsanız
 * yalnızca boyut sınırını yükseltmek yeterlidir. Derinlik/düğüm sınırları normalde
 * dokunulmamalıdır: bozuk/zararlı veriye karşı koruma sağlarlar.
 */
import { kopya } from '@/domain/kopya'
import { computed, ref, watch } from 'vue'

import { DOSYALAR } from '@/aws/config'
import AyarFormu from '@/components/AyarFormu.vue'
import { gruplar, tanim } from '@/domain/sema'
import { useDosyalar, type AyarBelgesi } from '@/stores/dosyalar'

const dosyalar = useDosyalar()
const taslak = ref<AyarBelgesi>(kopya(dosyalar.ayarlarBelgesi))

watch(
  () => dosyalar.ayarlar.veri,
  (yeni) => (taslak.value = kopya(yeni ?? {})),
  { deep: true },
)

const gelismis = computed(() => gruplar.find((g) => g.ad === 'gelismis')!)
const ag = computed(() => gruplar.find((g) => g.ad === 'ag')!)

const etkin = computed<Record<string, unknown>>(() => {
  const belge: Record<string, unknown> = {}
  for (const g of [gelismis.value, ag.value]) {
    for (const a of g.anahtarlar) belge[a.tam] = taslak.value?.[g.ad]?.[a.ad] ?? a.varsayilan
  }
  return belge
})

const degisiklikler = computed<Record<string, unknown>>(() => {
  const farklar: Record<string, unknown> = {}
  for (const g of [gelismis.value, ag.value]) {
    for (const a of g.anahtarlar) {
      const yeni = taslak.value?.[g.ad]?.[a.ad]
      if (yeni !== undefined && yeni !== dosyalar.ayarlarBelgesi?.[g.ad]?.[a.ad]) farklar[a.tam] = yeni
    }
  }
  return farklar
})

const jsonSinirlari = computed(() => ({
  boyut: Number(etkin.value['gelismis.max_json_bayt'] ?? 0),
  derinlik: Number(etkin.value['gelismis.max_json_derinlik'] ?? 0),
  dugum: Number(etkin.value['gelismis.max_json_dugum'] ?? 0),
}))

const mb = (bayt: number): string => `${(bayt / 1024 / 1024).toFixed(1)} MB`

function guncelle(tam: string, deger: unknown): void {
  const [grup, anahtar] = tam.split('.')
  taslak.value = { ...taslak.value, [grup]: { ...(taslak.value[grup] ?? {}), [anahtar]: deger } }
}

async function kaydet(): Promise<void> {
  await dosyalar.kaydet('ayarlar', DOSYALAR.ayarlar, taslak.value)
}

function buyukVeriIcinAyarla(): void {
  const t = tanim('gelismis.max_json_bayt')!
  guncelle('gelismis.max_json_bayt', 33_554_432) // 32 MB
  guncelle('gelismis.max_json_dugum', 1_000_000)
  // (üst sınır: 512 MB / 50 M düğüm — bkz. şema)
  void t
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Gelişmiş</h2>
        <div class="text-body-2 text-medium-emphasis">
          Veri hacmi ve ağ güvenliği sınırları. Bunlar <code>ayarlar.json</code> içindeki
          <code>gelismis</code> ve <code>ag</code> gruplarıdır.
        </div>
      </div>
      <v-spacer />
      <v-chip v-if="Object.keys(degisiklikler).length" color="warning" variant="tonal" class="mr-3">
        {{ Object.keys(degisiklikler).length }} değişiklik
      </v-chip>
      <v-btn color="primary" prepend-icon="mdi-content-save" :loading="dosyalar.mesgul" :disabled="!Object.keys(degisiklikler).length" @click="kaydet">
        Kaydet
      </v-btn>
    </div>

    <v-card class="mb-4">
      <v-card-title class="text-subtitle-1">Şu anki sınırlar</v-card-title>
      <v-card-text>
        <v-row dense>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">JSON gövde üst sınırı</div>
            <div class="text-h6">{{ mb(jsonSinirlari.boyut) }}</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">İç içe geçme derinliği</div>
            <div class="text-h6">{{ jsonSinirlari.derinlik }} seviye</div>
          </v-col>
          <v-col cols="12" md="4">
            <div class="text-caption text-medium-emphasis">Düğüm (anahtar+değer) sayısı</div>
            <div class="text-h6">{{ jsonSinirlari.dugum.toLocaleString('tr-TR') }}</div>
          </v-col>
        </v-row>
        <v-divider class="my-3" />
        <div class="text-body-2">
          <p class="mb-2">
            <strong>20-30 MB veri kullanacaksanız</strong> yalnızca <em>JSON üst boyutu</em> sınırını
            yükseltmek yeterli. Derinlik ve düğüm sınırları bozuk/zararlı veriye karşı korur; veri
            bunların altında kaldığı sürece dokunmanıza gerek yok.
          </p>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-rocket-launch" @click="buyukVeriIcinAyarla">
            Büyük veri için önerilen değerleri gir (32 MB / 1 M düğüm)
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <v-card class="mb-4">
      <v-card-title class="text-subtitle-1">{{ gelismis.baslik }}</v-card-title>
      <v-card-subtitle>Yalnızca aşıldığında veri reddedilir; cihaz ekranı boş kalmaz, son geçerli veriyi kullanır.</v-card-subtitle>
      <v-card-text>
        <AyarFormu :grup="gelismis" :etkin="etkin" :degisiklikler="degisiklikler" gelismis-goster @guncelle="guncelle" />
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title class="text-subtitle-1">{{ ag.baslik }}</v-card-title>
      <v-card-subtitle>
        Veri yalnızca <strong>https</strong> ve izinli ana makinelerden alınır. Kaynağı değiştirirken
        ana makineyi listeye eklemeyi unutmayın; port kısıtı varsayılan olarak yalnızca 443'tür.
      </v-card-subtitle>
      <v-card-text>
        <AyarFormu :grup="ag" :etkin="etkin" :degisiklikler="degisiklikler" gelismis-goster @guncelle="guncelle" />
      </v-card-text>
    </v-card>
  </div>
</template>
