<script setup lang="ts">
/**
 * CİHAZLAR — match.json (cihaz → ilçe/bölge) + makinebilgileri + lastupdate.
 * Bir cihazı başka bir bölgeye taşımak, kiosk tarafında bölge değiştirmenin panelden
 * yapılan hâlidir (cihaz bir sonraki veri turunda yeni bölgeyi gösterir).
 */
import { kopya } from '@/domain/kopya'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { DOSYALAR } from '@/aws/config'
import {
  durumEkle,
  durumEtiketi,
  izlemeBaslat,
  izlemeOzeti,
  type BaglantiDurumu,
  type CihazDurumu,
  type IzlemeOturumu,
} from '@/domain/cihazIzleme'
import {
  izlemeAdresi,
  izlemeAdresiHatasi,
  izlemeKonusu,
  kimligiOku,
  kimligiSil,
  kimligiYaz,
  VARSAYILAN_IZLEME_KULLANICI,
} from '@/domain/izlemeKimligi'
import { gunEtiketi, tarihMetni, tumKayitlar } from '@/domain/veri'
import { useDosyalar } from '@/stores/dosyalar'

const dosyalar = useDosyalar()
const taslak = ref<Record<string, unknown>>(kopya(dosyalar.match.veri ?? {}))
const taslakMakine = ref<string>(dosyalar.clientId)
const mesaj = ref('')

/**
 * CİHAZ İZLEME (MQTT kalp atışı) — çevrimiçi/çevrimdışı.
 *
 * Kimlik ÇALIŞMA ANINDA istenir (pakete gömülmez): panel paketi CloudFront'tan kimlik
 * doğrulamasız indirilebildiği için `VITE_MQTT_PAROLA` derlemeye yazılırsa sır sızar (i5 bulgusu).
 * Parola yalnız sessionStorage'da tutulur; sekme kapanınca silinir.
 */
const durumlar = ref<Map<string, CihazDurumu>>(new Map())
const izlemeDurumu = ref<'kapali' | 'kimlik-gerekli' | 'baglaniyor' | 'acik' | 'koptu' | 'hata'>('kapali')
const izlemeHatasi = ref('')
const simdi = ref(new Date())
const kimlikDialog = ref(false)
const kimlikKullanici = ref(VARSAYILAN_IZLEME_KULLANICI)
const kimlikParola = ref('')
let oturum: IzlemeOturumu | null = null
let saatZamanlayici: number | undefined

const izlemeUrl = izlemeAdresi(import.meta.env as unknown as Record<string, string | undefined>)
const izlemeUrlHatasi = izlemeAdresiHatasi(import.meta.env as unknown as Record<string, string | undefined>)
const bagliMi = computed(() => izlemeDurumu.value === 'acik')

function durumEsle(durum: BaglantiDurumu, ayrinti?: string): void {
  if (durum === 'bagli') izlemeDurumu.value = 'acik'
  else if (durum === 'baglaniyor') izlemeDurumu.value = 'baglaniyor'
  else if (durum === 'koptu') izlemeDurumu.value = 'koptu'
  else {
    izlemeDurumu.value = 'hata'
    izlemeHatasi.value = ayrinti ?? 'bilinmeyen MQTT hatası'
  }
}

async function izlemeyiBagla(kullanici: string, parola: string): Promise<void> {
  oturum?.durdur()
  oturum = null
  durumlar.value = new Map()
  izlemeHatasi.value = ''
  izlemeDurumu.value = 'baglaniyor'
  try {
    const konu = izlemeKonusu(import.meta.env as unknown as Record<string, string | undefined>)
    oturum = await izlemeBaslat(
      (durum) => {
        // SINIRLI HARİTA (i5 bulgusu): durumEkle 2000 kayıtta durur, en eskiyi düşürür.
        durumlar.value = durumEkle(durumlar.value, durum)
      },
      { url: izlemeUrl, konu, kullanici, parola },
      { durum: durumEsle },
    )
    if (!oturum) izlemeDurumu.value = 'kapali'
  } catch (hata) {
    izlemeDurumu.value = 'hata'
    izlemeHatasi.value = (hata as Error).message
  }
}

function kimlikSor(): void {
  kimlikKullanici.value = kimligiOku()?.kullanici ?? VARSAYILAN_IZLEME_KULLANICI
  kimlikParola.value = ''
  kimlikDialog.value = true
}

function kimlikKaydet(): void {
  const kullanici = kimlikKullanici.value.trim()
  if (!kullanici || !kimlikParola.value) return
  kimligiYaz({ kullanici, parola: kimlikParola.value })
  kimlikDialog.value = false
  void izlemeyiBagla(kullanici, kimlikParola.value)
  kimlikParola.value = ''
}

function izlemeyiKes(): void {
  oturum?.durdur()
  oturum = null
  kimligiSil()
  durumlar.value = new Map()
  izlemeDurumu.value = izlemeUrl ? 'kimlik-gerekli' : 'kapali'
}

onMounted(async () => {
  saatZamanlayici = window.setInterval(() => (simdi.value = new Date()), 30_000)
  if (!izlemeUrl) {
    izlemeDurumu.value = 'kapali'
    return
  }
  const kimlik = kimligiOku()
  if (!kimlik) {
    izlemeDurumu.value = 'kimlik-gerekli'
    return
  }
  await izlemeyiBagla(kimlik.kullanici, kimlik.parola)
})

onBeforeUnmount(() => {
  oturum?.durdur()
  oturum = null
  if (saatZamanlayici !== undefined) window.clearInterval(saatZamanlayici)
})

watch(
  () => dosyalar.match.veri,
  (yeni) => (taslak.value = kopya(yeni ?? {})),
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

/** Çevrimiçi özeti (match.json'daki tüm cihazlar üzerinden). */
const tumCihazIdleri = computed(() => [...new Set(cihazlar.value.flatMap((s) => s.cihazlar))])
const cevrimiciOzeti = computed(() => izlemeOzeti(durumlar.value, tumCihazIdleri.value, simdi.value))
const cihazDurumu = (cihaz: string) => durumEtiketi(durumlar.value.get(cihaz), simdi.value)

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
  taslak.value = kopya(dosyalar.match.veri ?? {})
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

    <v-alert v-if="izlemeDurumu === 'kapali'" :type="izlemeUrlHatasi ? 'warning' : 'info'" variant="tonal" density="compact" class="mb-4">
      <template v-if="izlemeUrlHatasi">
        Çevrimiçi izleme <strong>açılamadı</strong> — {{ izlemeUrlHatasi }}.
        Adresi düzeltin (ör. <code>wss://yourkiosk.hakkisabah.com:8084/mqtt</code>) ve paneli yeniden derleyin.
      </template>
      <template v-else>
        Çevrimiçi izleme <strong>kapalı</strong> — panelde <code>VITE_MQTT_URL</code> tanımlı değil.
        Cihazlar çalışmaya devam eder (yoklama emniyet ağı); durum sütunu "bilinmiyor" görünür.
      </template>
    </v-alert>
    <v-alert v-else-if="izlemeDurumu === 'kimlik-gerekli'" type="info" variant="tonal" density="compact" class="mb-4">
      Çevrimiçi izleme için broker <strong>okuma</strong> kimliği gerekli (kullanıcı
      <code>panel-izleme</code>). Parola pakete gömülmez; yalnız bu sekmede tutulur.
      <v-btn size="small" variant="tonal" class="ml-3" prepend-icon="mdi-lan-connect" @click="kimlikSor">
        İzlemeyi bağla
      </v-btn>
    </v-alert>
    <v-alert v-else-if="izlemeDurumu === 'hata' || izlemeDurumu === 'koptu'" type="warning" variant="tonal" density="compact" class="mb-4">
      MQTT izleme {{ izlemeDurumu === 'koptu' ? 'bağlantısı koptu' : 'başlatılamadı' }}:
      {{ izlemeHatasi }} — cihazlar etkilenmez.
      <v-btn size="small" variant="text" class="ml-3" @click="kimlikSor">Yeniden bağlan</v-btn>
    </v-alert>
    <div v-else-if="izlemeDurumu === 'baglaniyor'" class="text-caption text-medium-emphasis mb-4">
      MQTT izlemesi bağlanıyor…
    </div>

    <v-row>
      <v-col cols="12" lg="8">
        <v-card>
          <v-card-title class="text-subtitle-1 d-flex align-center">
            <span>Cihaz eşlemesi ({{ cihazlar.length }} bölge kaydı)</span>
            <v-spacer />
            <v-chip v-if="bagliMi" size="small" variant="tonal" color="success" class="mr-2">
              çevrimiçi {{ cevrimiciOzeti.cevrimici }}
            </v-chip>
            <v-chip v-if="bagliMi" size="small" variant="tonal" color="error" class="mr-2">
              çevrimdışı {{ cevrimiciOzeti.cevrimdisi }}
            </v-chip>
            <v-chip v-if="bagliMi && cevrimiciOzeti.bilinmiyor" size="small" variant="tonal">
              bilinmiyor {{ cevrimiciOzeti.bilinmiyor }}
            </v-chip>
            <v-btn v-if="bagliMi" size="small" variant="text" class="ml-2" @click="izlemeyiKes">
              İzlemeyi kes
            </v-btn>
          </v-card-title>
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
                      <v-icon
                        v-if="izlemeDurumu === 'acik'"
                        :color="cihazDurumu(c).renk"
                        size="x-small"
                        class="mr-1"
                        :icon="cihazDurumu(c).renk === 'success' ? 'mdi-circle' : cihazDurumu(c).renk === 'error' ? 'mdi-circle-off-outline' : 'mdi-help-circle-outline'"
                      />
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

    <v-dialog v-model="kimlikDialog" max-width="460">
      <v-card>
        <v-card-title class="text-subtitle-1">Çevrimiçi izleme kimliği</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-3">
            Broker'da <strong>yalnız <code>durum/+</code> okuma</strong> yetkisi olan kullanıcı. Parola
            derleme paketine gömülmez, yalnız bu sekmede (sessionStorage) tutulur.
          </p>
          <v-text-field v-model="kimlikKullanici" label="Kullanıcı" density="compact" autocomplete="username" />
          <v-text-field
            v-model="kimlikParola"
            label="Parola"
            type="password"
            density="compact"
            autocomplete="current-password"
            @keyup.enter="kimlikKaydet"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="kimlikDialog = false">Vazgeç</v-btn>
          <v-btn color="primary" :disabled="!kimlikKullanici.trim() || !kimlikParola" @click="kimlikKaydet">
            Bağlan
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
