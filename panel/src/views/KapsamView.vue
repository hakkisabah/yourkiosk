<script setup lang="ts">
/**
 * KAPSAM AYARLARI — ilçe / bölge / cihaz bazında özellik yönetimi.
 * Çözümleme: varsayılan → ilçe → bölge → cihaz (en özel kazanır).
 * Burada yalnızca "geçersiz kılınan" anahtarlar yazılır; diğerleri üst kapsamdan devralınır.
 */
import { kopya } from '@/domain/kopya'
import { computed, ref, watch } from 'vue'

import { DOSYALAR } from '@/aws/config'
import AyarFormu from '@/components/AyarFormu.vue'
import {
  KAPSAM_ETIKETLERI,
  kapsamAyarlari,
  kapsamCoz,
  kapsamKimlikleri,
  kapsamSatirlari,
  kapsamSil,
  kapsamYaz,
  secimAnahtari,
  type KapsamBelgesi,
  type KapsamTuru,
} from '@/domain/kapsam'
import { gruplar, kapsamGrubuMu } from '@/domain/sema'
import { tumKayitlar } from '@/domain/veri'
import { useDosyalar } from '@/stores/dosyalar'
const dosyalar = useDosyalar()
const taslak = ref<KapsamBelgesi>(kopya(dosyalar.kapsamBelgesi))
const tur = ref<KapsamTuru>('varsayilan')
const kimlik = ref('')
const yeniKimlik = ref('')
const hata = ref('')

watch(
  () => dosyalar.kapsam.veri,
  (yeni) => (taslak.value = kopya(yeni ?? {})),
  { deep: true },
)

/** Veriden bilinen ilçe/bölge kimlikleri (kullanıcı elle de ekleyebilir). */
const veridekiKimlikler = computed(() => {
  const ilceler = new Set<string>()
  const bolgeler = new Set<string>()
  for (const k of tumKayitlar(dosyalar.sistemVerisi)) {
    if (k.ilceId) ilceler.add(String(k.ilceId))
    if (k.bolgeId) bolgeler.add(String(k.bolgeId))
  }
  return { ilceler: [...ilceler].sort(), bolgeler: [...bolgeler].sort() }
})

const kimlikler = computed(() => {
  const mevcut = kapsamKimlikleri(taslak.value)
  const birlesik = (a: string[], b: string[]): string[] => [...new Set([...a, ...b])].sort()
  return {
    varsayilan: [''],
    ilceler: birlesik(mevcut.ilceler, veridekiKimlikler.value.ilceler),
    bolgeler: birlesik(mevcut.bolgeler, veridekiKimlikler.value.bolgeler),
    cihazlar: birlesik(mevcut.cihazlar, dosyalar.clientId ? [dosyalar.clientId] : []),
  }
})

const secim = computed(() => ({ ...secimAnahtari(tur.value, kimlik.value) }))
const seciliBelge = computed(() => kapsamAyarlari(taslak.value, tur.value, kimlik.value))
const devralinan = computed<Record<string, unknown>>(() => {
  const cozulen = kapsamCoz(taslak.value, secim.value)
  const belge: Record<string, unknown> = {}
  for (const g of gruplar.filter((x) => x.kapsam)) {
    for (const a of g.anahtarlar) {
      belge[a.tam] = cozulen.belge?.[g.ad]?.[a.ad] ?? a.varsayilan
    }
  }
  return belge
})
const kaynaklar = computed(() => kapsamCoz(taslak.value, secim.value).kaynak)

const kirli = computed(() => JSON.stringify(taslak.value) !== JSON.stringify(dosyalar.kapsamBelgesi))

const ozet = computed(() => kapsamSatirlari(taslak.value, secim.value))
const gecersizSayisi = computed(() => ozet.value.filter((s) => s.gecersizMi).length)

function geriAl(): void {
  hata.value = ''
  taslak.value = kopya(dosyalar.kapsamBelgesi)
}

function kapsamDegistir(yeniTur: KapsamTuru): void {
  tur.value = yeniTur
  kimlik.value = yeniTur === 'varsayilan' ? '' : (kimlikler.value[yeniTur][0] ?? '')
}

function guncelle(tam: string, deger: unknown): void {
  taslak.value = kapsamYaz(taslak.value, tur.value, kimlik.value, { [tam]: deger })
}

function kaldir(tam: string): void {
  taslak.value = kapsamSil(taslak.value, tur.value, kimlik.value, [tam])
}

function kapsamEkle(): void {
  const id = yeniKimlik.value.trim()
  if (!id) return
  if (tur.value === 'varsayilan') return
  taslak.value = kapsamYaz(taslak.value, tur.value, id, {})
  kimlik.value = id
  yeniKimlik.value = ''
}

async function kaydet(): Promise<void> {
  hata.value = ''
  if (gecersizSayisi.value > 0) {
    hata.value = `${gecersizSayisi.value} geçersiz değer var; kiosk bunları yok sayar. Kaydetmeden önce düzeltin.`
    return
  }
  const tamam = await dosyalar.kaydet('kapsam', DOSYALAR.kapsam, taslak.value)
  if (tamam) hata.value = ''
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Kapsam Ayarları</h2>
        <div class="text-body-2 text-medium-emphasis">
          <code>{{ DOSYALAR.kapsam }}</code> — aynı anda yüzlerce cihaz yönetilebilir: bir ilçeye, bir bölgeye
          ya da tek bir cihaza özel özellik verin. Kiosk sırayla <strong>varsayılan → ilçe → bölge → cihaz</strong>
          uygular; en özel kazanır.
        </div>
      </div>
      <v-spacer />
      <v-chip v-if="kirli" color="warning" variant="tonal" class="mr-3">kaydedilmemiş</v-chip>
      <v-btn class="mr-2" variant="text" prepend-icon="mdi-undo" :disabled="!kirli" @click="geriAl">
        Geri al
      </v-btn>
      <v-btn color="primary" prepend-icon="mdi-content-save" :loading="dosyalar.mesgul" :disabled="!kirli" @click="kaydet">
        Kaydet
      </v-btn>
    </div>

    <v-alert v-if="hata" type="error" variant="tonal" class="mb-4">{{ hata }}</v-alert>

    <v-card class="mb-4">
      <v-card-text>
        <v-row dense align="center">
          <v-col cols="12" md="4">
            <v-select
              :model-value="tur"
              :items="(Object.keys(KAPSAM_ETIKETLERI) as KapsamTuru[]).map((t) => ({ title: KAPSAM_ETIKETLERI[t], value: t }))"
              label="Kapsam türü"
              @update:model-value="(v: KapsamTuru) => kapsamDegistir(v)"
            />
          </v-col>
          <v-col v-if="tur !== 'varsayilan'" cols="12" md="4">
            <v-select v-model="kimlik" :items="kimlikler[tur]" label="Kimlik (ilçeId / bölgeId / clientID)" />
          </v-col>
          <v-col v-if="tur !== 'varsayilan'" cols="12" md="4">
            <v-text-field v-model="yeniKimlik" label="Yeni kimlik ekle" append-inner-icon="mdi-plus" @click:append-inner="kapsamEkle" @keyup.enter="kapsamEkle" />
          </v-col>
        </v-row>
        <div class="text-caption text-medium-emphasis">
          Bu kapsamda <strong>{{ Object.keys(seciliBelge).length }}</strong> anahtar geçersiz kılınmış;
          {{ ozet.length }} anahtar için etkin değer hesaplandı ({{ gecersizSayisi }} geçersiz).
        </div>
      </v-card-text>
    </v-card>

    <v-card v-if="tur !== 'varsayilan'">
      <v-card-title class="text-subtitle-1">
        {{ KAPSAM_ETIKETLERI[tur] }} · {{ kimlik || 'seçilmedi' }}
      </v-card-title>
      <v-card-subtitle>
        "Geçersiz kıl" dediğiniz anahtar bu kapsam için yazılır; "Kaldır" üst kapsama döndürür.
        Değer doğrudan kiosk ile aynı kurallarla doğrulanır (aralık dışı değer kaydedilmez).
      </v-card-subtitle>
      <v-card-text>
        <v-expansion-panels variant="accordion">
          <v-expansion-panel v-for="g in gruplar.filter((x) => kapsamGrubuMu(x.ad))" :key="g.ad" :title="g.baslik">
            <v-expansion-panel-text>
              <AyarFormu
                :grup="g"
                :etkin="devralinan"
                :degisiklikler="seciliBelge"
                :kaynaklar="kaynaklar"
                mod="kapsam"
                :gelismis-goster="g.ad === 'gelismis'"
                @guncelle="guncelle"
                @kaldir="kaldir"
              />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
    </v-card>

    <v-card v-else>
      <v-card-title class="text-subtitle-1">Varsayılan kapsam</v-card-title>
      <v-card-subtitle>
        Tüm cihazlar için geçerli varsayılan kapsam. Tek cihazlı kurulumlarda genel ayarlar
        (<router-link to="/ayarlar">ayarlar.json</router-link>) genellikle yeterlidir.
      </v-card-subtitle>
      <v-card-text>
        <v-alert type="info" variant="tonal" density="compact">
          Kapsam dosyası yoksa hiçbir şey değişmez: kiosk <code>config.py</code> varsayılanlarını kullanır.
          Aşağıdaki anahtarlar yalnızca buradan değiştirilirse kapsam dosyasına yazılır.
        </v-alert>
        <v-expansion-panels variant="accordion" class="mt-3">
          <v-expansion-panel v-for="g in gruplar.filter((x) => kapsamGrubuMu(x.ad))" :key="g.ad" :title="g.baslik">
            <v-expansion-panel-text>
              <AyarFormu
                :grup="g"
                :etkin="devralinan"
                :degisiklikler="taslak.varsayilan ? kapsamAyarlari(taslak, 'varsayilan') : {}"
                :kaynaklar="kaynaklar"
                mod="kapsam"
                :gelismis-goster="g.ad === 'gelismis'"
                @guncelle="guncelle"
                @kaldir="kaldir"
              />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
    </v-card>
  </div>
</template>
