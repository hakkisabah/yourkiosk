<script setup lang="ts">
/**
 * CİHAZLAR — match.json (cihaz → ilçe/bölge) + makinebilgileri + lastupdate.
 * Bir cihazı başka bir bölgeye taşımak, kiosk tarafında bölge değiştirmenin panelden
 * yapılan hâlidir (cihaz bir sonraki veri turunda yeni bölgeyi gösterir).
 */
import { computed, ref, watch } from 'vue'

import { DOSYALAR } from '@/aws/config'
import { gunEtiketi, tarihMetni, tumKayitlar } from '@/domain/veri'
import { useDosyalar } from '@/stores/dosyalar'

const dosyalar = useDosyalar()
const taslak = ref<Record<string, unknown>>(structuredClone(dosyalar.match.veri ?? {}))
const taslakMakine = ref<string>(dosyalar.clientId)
const mesaj = ref('')

watch(
  () => dosyalar.match.veri,
  (yeni) => (taslak.value = structuredClone(yeni ?? {})),
  { deep: true },
)

interface CihazSatiri {
  ilceId: string
  bolgeId: string
  cihazlar: string[]
}

/** match.json: { ilceId: [ { bolgeId: [cihazId, ...] } ] } */
const cihazlar = computed<CihazSatiri[]>(() => {
  const liste: CihazSatiri[] = []
  for (const [ilceId, ilceListesi] of Object.entries(taslak.value)) {
    if (!Array.isArray(ilceListesi)) continue
    for (const kutu of ilceListesi as Array<Record<string, unknown>>) {
      for (const [bolgeId, idler] of Object.entries(kutu)) {
        liste.push({ ilceId, bolgeId, cihazlar: Array.isArray(idler) ? idler.map((x) => String(x)) : [] })
      }
    }
  }
  return liste.sort((a, b) => a.ilceId.localeCompare(b.ilceId) || a.bolgeId.localeCompare(b.bolgeId))
})

/** Verideki bölge adları (taşıma sırasında okunur etiket için). */
const bolgeAdlari = computed<Record<string, string>>(() => {
  const adlar: Record<string, string> = {}
  for (const k of tumKayitlar(dosyalar.sistemVerisi)) if (k.bolgeId) adlar[String(k.bolgeId)] = String(k.bolge ?? '')
  return adlar
})

const tumBolgeler = computed(() => cihazlar.value.map((c) => c.bolgeId))
const kirli = computed(() => JSON.stringify(taslak.value) !== JSON.stringify(dosyalar.match.veri ?? {}))

function tasi(satir: CihazSatiri, cihaz: string, hedefBolge: string): void {
  if (hedefBolge === satir.bolgeId) return
  const hedefSatir = cihazlar.value.find((c) => c.bolgeId === hedefBolge && c.ilceId === satir.ilceId)
  if (!hedefSatir) {
    mesaj.value = `Hedef bölge ${hedefBolge} bu ilçede bulunamadı.`
    return
  }
  satir.cihazlar = satir.cihazlar.filter((c) => c !== cihaz)
  hedefSatir.cihazlar = [...new Set([...hedefSatir.cihazlar, cihaz])]
  _uygula()
  mesaj.value = `${cihaz} → ${hedefBolge} (${bolgeAdlari.value[hedefBolge] ?? ''})`
}

function cihazEkle(satir: CihazSatiri, cihaz: string): void {
  const temiz = cihaz.trim()
  if (!temiz) return
  satir.cihazlar = [...new Set([...satir.cihazlar, temiz])]
  _uygula()
}

function cihazSil(satir: CihazSatiri, cihaz: string): void {
  satir.cihazlar = satir.cihazlar.filter((c) => c !== cihaz)
  _uygula()
}

/** Düzenlenen listeyi match.json yapısına geri yazar. */
function _uygula(): void {
  const yeni: Record<string, unknown> = {}
  for (const [ilceId, ilceListesi] of Object.entries(taslak.value)) {
    if (!Array.isArray(ilceListesi)) continue
    const kutular: Array<Record<string, unknown>> = []
    for (const kutu of ilceListesi as Array<Record<string, unknown>>) {
      const yeniKutu: Record<string, unknown> = {}
      for (const bolgeId of Object.keys(kutu)) {
        const satir = cihazlar.value.find((c) => c.ilceId === ilceId && c.bolgeId === bolgeId)
        yeniKutu[bolgeId] = satir ? satir.cihazlar : kutu[bolgeId]
      }
      kutular.push(yeniKutu)
    }
    yeni[ilceId] = kutular
  }
  taslak.value = yeni
}

function geriAl(): void {
  taslak.value = structuredClone(dosyalar.match.veri ?? {})
  mesaj.value = ''
}

async function kaydet(): Promise<void> {
  await dosyalar.kaydet('match', DOSYALAR.match, taslak.value)
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Cihazlar</h2>
        <div class="text-body-2 text-medium-emphasis">
          <code>{{ DOSYALAR.match }}</code> — hangi cihaz hangi ilçe/bölgede. Bir cihazı başka bölgeye
          taşımak için ilgili satırdaki <strong>taşı</strong> listesini kullanın.
        </div>
      </div>
      <v-spacer />
      <v-chip v-if="kirli" color="warning" variant="tonal" class="mr-3">kaydedilmemiş</v-chip>
      <v-btn class="mr-2" variant="text" prepend-icon="mdi-undo" :disabled="!kirli" @click="geriAl">
        Geri al
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-content-save" :loading="dosyalar.mesgul" :disabled="!kirli" @click="kaydet">Kaydet</v-btn>
    </div>

    <v-alert v-if="mesaj" type="info" variant="tonal" class="mb-4" closable @click:close="mesaj = ''">{{ mesaj }}</v-alert>

    <v-row>
      <v-col cols="12" lg="8">
        <v-card>
          <v-card-title class="text-subtitle-1">Cihaz eşlemesi ({{ cihazlar.length }} bölge kaydı)</v-card-title>
          <v-card-text>
            <v-table density="compact">
              <thead><tr><th>İlçe</th><th>Bölge</th><th>Cihazlar (clientID)</th><th>İşlem</th></tr></thead>
              <tbody>
                <tr v-for="s in cihazlar" :key="`${s.ilceId}-${s.bolgeId}`">
                  <td class="text-caption">{{ s.ilceId }}</td>
                  <td>
                    <div>{{ bolgeAdlari[s.bolgeId] || s.bolgeId }}</div>
                    <div class="text-caption text-medium-emphasis">{{ s.bolgeId }}</div>
                  </td>
                  <td>
                    <v-chip
                      v-for="c in s.cihazlar"
                      :key="c"
                      class="ma-1"
                      size="small"
                      :color="c === dosyalar.clientId ? 'primary' : undefined"
                      closable
                      @click:close="cihazSil(s, c)"
                    >
                      {{ c }}{{ c === dosyalar.clientId ? ' (bu cihaz)' : '' }}
                    </v-chip>
                    <span v-if="!s.cihazlar.length" class="text-caption text-medium-emphasis">cihaz yok</span>
                  </td>
                  <td>
                    <v-text-field
                      density="compact"
                      hide-details
                      placeholder="clientID ekle + Enter"
                      @keyup.enter="(e: KeyboardEvent) => cihazEkle(s, String((e.target as HTMLInputElement).value))"
                    />
                    <v-select
                      class="mt-2"
                      density="compact"
                      hide-details
                      placeholder="bölgeye taşı"
                      :items="tumBolgeler.filter((b) => b !== s.bolgeId)"
                      @update:model-value="(hedef: unknown) => hedef && s.cihazlar[0] && tasi(s, s.cihazlar[0], String(hedef))"
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="4">
        <v-card class="mb-4">
          <v-card-title class="text-subtitle-1">makinebilgileri.json</v-card-title>
          <v-card-subtitle>
            Cihazın kendi kimliği. Bu kimlik <code>match.json</code> içinde geçmiyorsa cihaz kendi yerini bulamaz.
          </v-card-subtitle>
          <v-card-text>
            <v-text-field v-model="taslakMakine" label="clientID (bu cihaz)" density="compact" readonly>
              <template #append-inner>
                <v-icon icon="mdi-information-outline" />
              </template>
            </v-text-field>
            <v-alert v-if="!cihazlar.some((s) => s.cihazlar.includes(taslakMakine))" type="warning" variant="tonal" density="compact">
              Bu clientID hiçbir bölgede eşlenmemiş! Yukarıdaki tablodan bir bölgeye ekleyin.
            </v-alert>
            <v-btn class="mt-3" size="small" variant="tonal" prepend-icon="mdi-refresh" @click="dosyalar.dosyaYukle('makine', DOSYALAR.makine)">
              Yeniden oku
            </v-btn>
          </v-card-text>
        </v-card>

        <v-card>
          <v-card-title class="text-subtitle-1">lastupdate.json</v-card-title>
          <v-card-subtitle>Veri değişiklik damgası — cihaz saatlik kontrol eder, değiştiyse veriyi yeniden alır.</v-card-subtitle>
          <v-card-text>
            <v-table density="compact">
              <tbody>
                <tr v-for="(deger, anahtar) in (dosyalar.lastupdate.veri ?? {})" :key="anahtar">
                  <td class="text-caption">{{ anahtar }}</td>
                  <td>
                    {{ typeof deger === 'string' && deger.includes(':') ? tarihMetni(deger) : String(deger) }}
                  </td>
                </tr>
                <tr v-if="!Object.keys(dosyalar.lastupdate.veri ?? {}).length">
                  <td class="text-medium-emphasis">Dosya okunamadı veya boş.</td>
                </tr>
              </tbody>
            </v-table>
            <div class="text-caption text-medium-emphasis mt-2">
              Veri günü: {{ gunEtiketi(String(Object.keys((dosyalar.sistemVerisi.Nobetler ?? {}) as object).sort()[0] ?? '')) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>
