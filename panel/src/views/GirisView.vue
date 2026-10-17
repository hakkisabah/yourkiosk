<script setup lang="ts">
/** Giriş ekranı — Cognito modunda e-posta+şifre, Lambda modunda yalnızca şifre. */
import { computed, ref } from 'vue'

import { useBaglanti } from '@/stores/baglanti'

const baglanti = useBaglanti()
const eposta = ref('')
const sifre = ref('')
const sifreGorunur = ref(false)
const yerelHata = ref('')

const lambdaModu = computed(() => baglanti.mod === 'lambda')

async function gonder(): Promise<void> {
  yerelHata.value = ''
  if (!lambdaModu.value && !eposta.value.trim()) {
    yerelHata.value = 'E-posta gerekli.'
    return
  }
  if (!sifre.value) {
    yerelHata.value = 'Şifre gerekli.'
    return
  }
  await baglanti.giris(eposta.value, sifre.value)
}
</script>

<template>
  <v-row class="justify-center mt-8">
    <v-col cols="12" md="8" lg="6">
      <v-card class="pa-2">
        <v-card-title class="text-h5">yourkiosk · Yönetim Paneli</v-card-title>
        <v-card-subtitle>
          Nöbet / yayın verileri, özellik bayrakları ve ilçe-bölge-cihaz bazlı ayarlar buradan yönetilir.
          Tüm veriler S3'te tutulur; cihaz bir sonraki güncellemede ayarları kendisi alır.
        </v-card-subtitle>
        <v-card-text>
          <v-alert v-if="baglanti.yapilandirmaHatasi" type="warning" variant="tonal" class="mb-4">
            {{ baglanti.yapilandirmaHatasi }}
          </v-alert>
          <v-alert v-if="baglanti.hata || yerelHata" type="error" variant="tonal" class="mb-4">
            {{ yerelHata || baglanti.hata }}
          </v-alert>

          <v-text-field
            v-if="!lambdaModu"
            v-model="eposta"
            label="Yönetici e-postası"
            prepend-inner-icon="mdi-account"
            autocomplete="username"
            :disabled="!baglanti.yapilandirma"
            @keyup.enter="gonder"
          />
          <v-text-field
            v-model="sifre"
            :label="lambdaModu ? 'Yönetici şifresi' : 'Şifre'"
            prepend-inner-icon="mdi-lock"
            autocomplete="current-password"
            :append-inner-icon="sifreGorunur ? 'mdi-eye-off' : 'mdi-eye'"
            :type="sifreGorunur ? 'text' : 'password'"
            :disabled="!baglanti.yapilandirma"
            @click:append-inner="sifreGorunur = !sifreGorunur"
            @keyup.enter="gonder"
          />

          <v-btn block color="primary" size="large" :loading="baglanti.mesgul" :disabled="!baglanti.yapilandirma" @click="gonder">
            Giriş yap
          </v-btn>

          <v-divider class="my-5" />
          <div class="text-caption text-medium-emphasis">
            <p class="mb-1">
              <strong>Kimlik modu: {{ baglanti.mod }}</strong>
              <span v-if="lambdaModu">— Cognito yok: şifre Lambda'da doğrulanır, oturum HttpOnly cookie'de tutulur, S3'e yalnızca 5 dakikalık imzalı URL'lerle erişilir.</span>
              <span v-else>— Cognito User Pool (tek yönetici) + Identity Pool: S3 erişimi geçici AWS anahtarıyla yapılır.</span>
            </p>
            <p class="mb-1"><strong>İlk kurulum:</strong> kurulum adımları <code>panel/README.md</code> (Cognito) veya <code>panel/lambda/README.md</code> (Cognito'suz) içinde.</p>
            <p class="mb-0">Panelde şifre/anahtar saklanmaz; maliyet ve seçenek karşılaştırması: <code>panel/MAALIYET.md</code>.</p>
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>
</template>
