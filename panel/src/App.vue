<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { hatayiTemizle, uygulamaHatasi } from '@/hata'
import { MENU } from '@/router'
import { useBaglanti } from '@/stores/baglanti'
import { useDosyalar } from '@/stores/dosyalar'

const baglanti = useBaglanti()
const dosyalar = useDosyalar()
const router = useRouter()
const cekmece = ref(true)

/** Yapılandırma bozuksa yan menü/üst çubuk gizlenir (kurulum ekranı tam sayfa). */
const panelAcik = computed(() => baglanti.girisYapildi && !baglanti.yapilandirmaHatasi)

onMounted(async () => {
  await baglanti.baslat()
  if (baglanti.yapilandirmaHatasi) {
    await router.replace({ name: 'kurulum' }).catch(() => undefined)
  } else if (baglanti.girisYapildi) {
    await verileriYukle()
  } else {
    await router.replace({ name: 'giris' }).catch(() => undefined)
  }
})

async function verileriYukle(): Promise<void> {
  await dosyalar.hepsiniYukle()
}

function cikis(): void {
  baglanti.cikis()
  void router.push({ name: 'giris' })
}
</script>

<template>
  <v-app>
    <v-navigation-drawer v-if="panelAcik" v-model="cekmece" width="268" color="surface">
      <template #prepend>
        <div class="pa-4">
          <div class="text-h6">yourkiosk</div>
          <div class="text-caption text-medium-emphasis">Yönetim Paneli · {{ baglanti.kova }}</div>
        </div>
        <v-divider />
      </template>

      <v-list density="comfortable" nav>
        <v-list-item
          v-for="oge in MENU"
          :key="oge.yol"
          :to="oge.yol"
          :prepend-icon="oge.ikon"
          :title="oge.baslik"
          :subtitle="oge.aciklama"
        />
      </v-list>

      <template #append>
        <v-divider />
        <v-list density="compact" nav>
          <v-list-item prepend-icon="mdi-refresh" title="Verileri tazele" :loading="dosyalar.mesgul" @click="verileriYukle" />
          <v-list-item prepend-icon="mdi-logout" title="Çıkış" @click="cikis" />
        </v-list>
      </template>
    </v-navigation-drawer>

    <v-app-bar v-if="panelAcik" color="surface" density="comfortable">
      <v-app-bar-nav-icon @click="cekmece = !cekmece" />
      <v-app-bar-title>Yönetim Paneli</v-app-bar-title>
      <v-spacer />
      <v-chip class="mr-2" size="small" variant="tonal" prepend-icon="mdi-cloud-outline">S3: {{ baglanti.onEk || '/' }}</v-chip>
      <v-chip class="mr-2" size="small" variant="tonal" prepend-icon="mdi-shield-key-outline">mod: {{ baglanti.mod }}</v-chip>
      <v-chip size="small" variant="tonal" prepend-icon="mdi-account-circle">{{ baglanti.eposta || 'yönetici' }}</v-chip>
    </v-app-bar>

    <v-main>
      <v-container fluid class="pa-6">
        <v-alert v-if="baglanti.yapilandirmaHatasi" type="warning" variant="tonal" class="mb-4">
          {{ baglanti.yapilandirmaHatasi }}
        </v-alert>
        <v-alert v-if="dosyalar.sonUyari" type="warning" variant="tonal" closable class="mb-4" @click:close="dosyalar.sonUyari = null">
          {{ dosyalar.sonUyari }}
        </v-alert>
        <v-alert v-if="dosyalar.sonBasari" type="success" variant="tonal" closable class="mb-4" @click:close="dosyalar.sonBasari = null">
          {{ dosyalar.sonBasari }}
        </v-alert>

        <!-- Beklenmeyen hata: beyaz ekran yerine okunabilir kart -->
        <v-alert v-if="uygulamaHatasi" type="error" variant="tonal" class="mb-4" closable @click:close="hatayiTemizle">
          <div class="font-weight-medium mb-1">Beklenmeyen bir hata oluştu ({{ uygulamaHatasi.zaman }})</div>
          <pre class="text-caption" style="white-space: pre-wrap">{{ uygulamaHatasi.mesaj }}</pre>
          <div v-if="uygulamaHatasi.ayrinti" class="text-caption text-medium-emphasis">Ayrıntı: {{ uygulamaHatasi.ayrinti }}</div>
          <div class="text-caption mt-2">
            Sorun sürerse bu mesajı paylaşın. Kurulum/hata ipuçları: <code>panel/README.md</code> · <code>panel/MAALIYET.md</code>
          </div>
        </v-alert>

        <router-view v-if="baglanti.hazir" :key="baglanti.girisYapildi ? 'panel' : 'giris'" />

        <v-row v-else class="justify-center mt-10">
          <v-progress-circular indeterminate color="primary" size="48" />
        </v-row>
      </v-container>
    </v-main>
  </v-app>
</template>
