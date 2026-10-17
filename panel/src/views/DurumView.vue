<script setup lang="ts">
/** Durum ekranı: bağlantı, dosyalar, veri özeti ve cihazın ŞU AN ne gösterdiği. */
import { computed, onMounted, ref } from 'vue'

import { DOSYALAR } from '@/aws/config'
import { DOSYA_ACIKLAMALARI } from '@/domain/dosyaBilgisi'
import { kapsamCoz, kapsamSatirlari } from '@/domain/kapsam'
import { gunEtiketi, gosterilecekKayitlar, konumAdlariniBul, ozetle, tarihMetni, type CihazKonumu } from '@/domain/veri'
import { useBaglanti } from '@/stores/baglanti'
import { useDosyalar } from '@/stores/dosyalar'

const baglanti = useBaglanti()
const dosyalar = useDosyalar()
const simdi = ref(new Date())
const sayac = ref<number | null>(null)

onMounted(async () => {
  if (!dosyalar.sistem.yuklendi) await dosyalar.hepsiniYukle()
  sayac.value = window.setInterval(() => (simdi.value = new Date()), 30_000)
})

const ozet = computed(() => ozetle(dosyalar.sistemVerisi))

/** Cihazın yeri: makinebilgileri.clientID → match.json → ilçe/bölge */
const konum = computed<CihazKonumu>(() => {
  const client = dosyalar.clientId
  const match = (dosyalar.match.veri ?? {}) as Record<string, unknown>
  const bulunan: CihazKonumu = { ilceId: '', bolgeId: '', bulundu: false }
  for (const [ilceId, liste] of Object.entries(match)) {
    if (!Array.isArray(liste)) continue
    for (const kutu of liste as Array<Record<string, unknown>>) {
      for (const [bolgeId, cihazlar] of Object.entries(kutu)) {
        const idler = Array.isArray(cihazlar) ? cihazlar.map((x) => String(x)) : []
        if (client && idler.includes(client)) {
          bulunan.ilceId = ilceId
          bulunan.bolgeId = bolgeId
          bulunan.bulundu = true
        }
      }
    }
  }
  return konumAdlariniBul(dosyalar.sistemVerisi, bulunan)
})

const cihazGosterimi = computed(() => gosterilecekKayitlar(dosyalar.sistemVerisi, konum.value, simdi.value))

const kapsamOzeti = computed(() =>
  kapsamSatirlari(dosyalar.kapsamBelgesi, {
    ilceId: String(konum.value.ilceId ?? ''),
    bolgeId: String(konum.value.bolgeId ?? ''),
    clientId: dosyalar.clientId,
  }),
)

const etkinKapsam = computed(() =>
  kapsamCoz(dosyalar.kapsamBelgesi, {
    ilceId: String(konum.value.ilceId ?? ''),
    bolgeId: String(konum.value.bolgeId ?? ''),
    clientId: dosyalar.clientId,
  }).belge,
)

const boyutMetni = (bayt?: number): string =>
  bayt === undefined ? '—' : bayt < 1024 ? `${bayt} B` : bayt < 1024 * 1024 ? `${(bayt / 1024).toFixed(1)} KB` : `${(bayt / 1024 / 1024).toFixed(2)} MB`

const dosyaSatirlari = computed(() =>
  Object.entries(DOSYALAR).map(([anahtar, ad]) => {
    const d = (dosyalar as unknown as Record<string, { boyut?: number; sonDegisiklik?: string; veri: unknown }>)[anahtar]
    return {
      ad,
      aciklama: DOSYA_ACIKLAMALARI[ad] ?? '',
      varMi: d?.veri !== null && d?.veri !== undefined,
      boyut: d?.boyut,
      sonDegisiklik: d?.sonDegisiklik,
    }
  }),
)
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Durum</h2>
        <div class="text-body-2 text-medium-emphasis">
          Şu anki zaman: <strong>{{ tarihMetni(simdi) }}</strong> · cihaz saati bağımsız çalışır, ekranda nöbet penceresi esastır.
        </div>
      </div>
      <v-spacer />
      <v-btn prepend-icon="mdi-refresh" :loading="dosyalar.mesgul" @click="dosyalar.hepsiniYukle()">Verileri tazele</v-btn>
    </div>

    <v-alert v-if="ozet.geciciMi" type="warning" variant="tonal" class="mb-4" title="GEÇİCİ TEST VERİSİ">
      Bu veri, sol panelde 5'ten fazla nöbetçi görünümünü sınamak için üretildi. İşiniz bittiğinde gerçek veriyle
      değiştirin (kiosk tarafında <code>tools/fetch_nobet.py</code>).
    </v-alert>

    <v-row>
      <v-col cols="12" lg="6">
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1">Cihazın şu an gösterdikleri</v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="6"><div class="text-caption text-medium-emphasis">Cihaz kimliği (clientID)</div>
                <div class="text-body-2">{{ dosyalar.clientId || 'makinebilgileri.json okunamadı' }}</div></v-col>
              <v-col cols="6"><div class="text-caption text-medium-emphasis">Kimlik modu</div>
                <div class="text-body-2">{{ baglanti.mod === 'lambda' ? 'Lambda + cookie (Cognito yok)' : 'Cognito User/Identity Pool' }}</div></v-col>
              <v-col cols="6"><div class="text-caption text-medium-emphasis">Nöbet günü</div>
                <div class="text-body-2">{{ gunEtiketi(cihazGosterimi.anahtar) || '—' }} <span class="text-caption">({{ cihazGosterimi.kaynak }})</span></div></v-col>
              <v-col cols="6"><div class="text-caption text-medium-emphasis">İlçe</div>
                <div class="text-body-2">{{ konum.ilce || '—' }}</div></v-col>
              <v-col cols="6"><div class="text-caption text-medium-emphasis">Bölge (cihazın kendi bölgesi)</div>
                <div class="text-body-2">{{ konum.bolge || '—' }}</div></v-col>
            </v-row>

            <v-divider class="my-3" />
            <div class="text-caption text-medium-emphasis mb-2">
              Aktif nöbetçiler — yalnızca <strong>kendi penceresi</strong> devam eden kayıtlar (biten nöbet listeden düşer):
            </div>
            <v-table density="compact">
              <thead>
                <tr><th>Bölge</th><th>Eczane</th><th>Telefon</th><th>Nöbet penceresi</th></tr>
              </thead>
              <tbody>
                <tr v-for="(k, i) in cihazGosterimi.kayitlar" :key="i">
                  <td>{{ k.bolge }}</td>
                  <td>{{ k.eczane }}</td>
                  <td>{{ k.tel }}</td>
                  <td class="text-caption">{{ tarihMetni(k.start) }} → {{ tarihMetni(k.end) }}</td>
                </tr>
                <tr v-if="!cihazGosterimi.kayitlar.length">
                  <td colspan="4" class="text-medium-emphasis">Kayıt bulunamadı (veri veya match.json kontrol edin).</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>

        <v-card>
          <v-card-title class="text-subtitle-1">Veri özeti (lastSystemData.json)</v-card-title>
          <v-card-text>
            <v-row dense>
              <v-col cols="6" md="3"><div class="text-caption text-medium-emphasis">Gün</div><div class="text-h6">{{ ozet.gunSayisi }}</div></v-col>
              <v-col cols="6" md="3"><div class="text-caption text-medium-emphasis">Nöbet kaydı</div><div class="text-h6">{{ ozet.kayitSayisi }}</div></v-col>
              <v-col cols="6" md="3"><div class="text-caption text-medium-emphasis">İlçe / bölge</div><div class="text-h6">{{ ozet.ilceSayisi }} / {{ ozet.bolgeSayisi }}</div></v-col>
              <v-col cols="6" md="3"><div class="text-caption text-medium-emphasis">Yayın</div><div class="text-h6">{{ ozet.yayinSayisi }}</div></v-col>
            </v-row>
            <div class="text-caption text-medium-emphasis mt-2">
              Aralık: {{ gunEtiketi(ozet.ilkGun) }} → {{ gunEtiketi(ozet.sonGun) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="6">
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1">S3 dosyaları</v-card-title>
          <v-card-text>
            <v-table density="compact">
              <thead><tr><th>Dosya</th><th>Durum</th><th>Boyut</th><th>Son değişiklik</th></tr></thead>
              <tbody>
                <tr v-for="d in dosyaSatirlari" :key="d.ad">
                  <td>
                    <div class="font-weight-medium">{{ d.ad }}</div>
                    <div class="text-caption text-medium-emphasis">{{ d.aciklama }}</div>
                  </td>
                  <td>
                    <v-chip :color="d.varMi ? 'success' : 'warning'" size="x-small" variant="tonal">
                      {{ d.varMi ? 'var' : 'yok' }}
                    </v-chip>
                  </td>
                  <td>{{ boyutMetni(d.boyut) }}</td>
                  <td class="text-caption">{{ d.sonDegisiklik ? tarihMetni(d.sonDegisiklik) : '—' }}</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>

        <v-card>
          <v-card-title class="text-subtitle-1">Bu cihaz için etkin özellikler</v-card-title>
          <v-card-subtitle>
            Kapsam sırası: varsayılan → ilçe → bölge → cihaz (en özel kazanır).
          </v-card-subtitle>
          <v-card-text>
            <v-alert v-if="!kapsamOzeti.length" type="info" variant="tonal" density="compact">
              Henüz kapsam ayarı yok — kiosk <code>config.py</code> varsayılanlarını kullanıyor.
            </v-alert>
            <v-table v-else density="compact">
              <thead><tr><th>Anahtar</th><th>Etkin değer</th><th>Kaynak</th></tr></thead>
              <tbody>
                <tr v-for="s in kapsamOzeti" :key="s.tam">
                  <td>{{ s.etiket }} <span class="text-caption text-medium-emphasis">({{ s.tam }})</span></td>
                  <td>
                    <v-chip :color="s.gecersizMi ? 'error' : 'success'" size="x-small" variant="tonal">
                      {{ String(s.etkin) }}
                    </v-chip>
                    <span v-if="s.gecersizMi" class="text-caption text-error ml-2">{{ s.hata }}</span>
                  </td>
                  <td class="text-caption">{{ s.kaynak }}</td>
                </tr>
              </tbody>
            </v-table>
            <div v-if="etkinKapsam" class="text-caption text-medium-emphasis mt-2">
              Panel bu değerleri cihazla aynı kurallarla hesaplar; dosya S3'e yazıldığında cihaz bir sonraki veri turunda alır.
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
