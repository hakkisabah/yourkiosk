<script setup lang="ts">
/**
 * KURULUM EKRANI — ortam değişkenleri eksik/yer tutucu olduğunda gösterilir.
 * Beyaz ekran yerine ne yapılacağını adım adım anlatır.
 */
import { computed } from 'vue'

import { DOSYALAR, eksikDegiskenler, yerTutucuDegiskenler } from '@/aws/config'
import { useBaglanti } from '@/stores/baglanti'

const baglanti = useBaglanti()

const eksik = computed(() => eksikDegiskenler(import.meta.env))
const yerTutucu = computed(() => yerTutucuDegiskenler(import.meta.env))
const devModu = computed(() => import.meta.env.DEV)
const nodeEnvUyari = computed(() => import.meta.env.MODE === 'development' && !import.meta.env.DEV)

const ornekDosyalar = Object.values(DOSYALAR)
</script>

<template>
  <v-row class="justify-center mt-6">
    <v-col cols="12" lg="9">
      <v-card class="pa-2">
        <v-card-title class="text-h5">Kurulum gerekli</v-card-title>
        <v-card-subtitle>
          Panel yapılandırması okunamadı; bu yüzden S3'e bağlanılmadı ve hiçbir AWS isteği yapılmadı.
        </v-card-subtitle>

        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-4">
            <div v-if="eksik.length"><strong>Eksik değişkenler:</strong> {{ eksik.join(', ') }}</div>
            <div v-if="yerTutucu.length"><strong>Yer tutucu kalmış (örnek dosyadan kopyalanmış):</strong> {{ yerTutucu.join(', ') }}</div>
            <div v-if="!eksik.length && !yerTutucu.length">Yapılandırma yüklenemedi.</div>
          </v-alert>

          <v-alert v-if="nodeEnvUyari" type="info" variant="tonal" class="mb-4">
            Dev sunucusu <strong>üretim modunda</strong> çalışıyor (kabukta <code>NODE_ENV=production</code> tanımlı).
            Geliştirme için <code>npm run dev</code> kullanın (bu betik NODE_ENV'i ayarlar).
          </v-alert>

          <h3 class="text-subtitle-1 mb-2">Yapılacaklar</h3>
          <ol class="text-body-2 mb-4">
            <li><code>cp .env.ornek .env.local</code> (panel kökünde)</li>
            <li><code>.env.local</code> içinde modu seçin: <code>VITE_AUTH_MODU=cognito</code> (varsayılan) veya <code>lambda</code></li>
            <li>
              <strong>cognito</strong> modu için: <code>VITE_AWS_REGION</code>, <code>VITE_USER_POOL_ID</code>,
              <code>VITE_USER_POOL_CLIENT_ID</code>, <code>VITE_IDENTITY_POOL_ID</code>
              (kurulum: <code>README.md</code> §2.3)
            </li>
            <li>
              <strong>lambda</strong> modu için: <code>VITE_API_URL</code> (Cognito'suz kurulum:
              <code>lambda/README.md</code>)
            </li>
            <li>Ortak: <code>VITE_BUCKET</code> ve varsa <code>VITE_PREFIX</code> (ör. <code>kiosk/</code>)</li>
            <li><strong>Dev sunucusunu yeniden başlatın</strong> (ortam değişkenleri açılışta okunur)</li>
          </ol>

          <v-divider class="my-4" />

          <h3 class="text-subtitle-1 mb-2">Panelin yönettiği dosyalar (S3 ön eki altında)</h3>
          <div class="d-flex flex-wrap">
            <v-chip v-for="d in ornekDosyalar" :key="d" class="ma-1" size="small" variant="tonal">{{ d }}</v-chip>
          </div>

          <div class="text-caption text-medium-emphasis mt-4">
            Kimlik modu: <strong>{{ baglanti.mod }}</strong> ·
            Maliyet ve mod karşılaştırması: <code>MAALIYET.md</code> ·
            Geliştirme modu: {{ devModu ? 'açık' : 'kapalı' }}
          </div>

          <v-btn class="mt-4" variant="tonal" prepend-icon="mdi-refresh" @click="baglanti.baslat()">Yeniden dene</v-btn>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>
