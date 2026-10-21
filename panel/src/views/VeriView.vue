<script setup lang="ts">
/**
 * NÖBET + YAYIN VERİSİ (lastSystemData.json).
 * Nöbet kayıtları düzenlenebilir: eczane, telefon, adres, adres tarifi ve nöbet penceresi.
 * Pencere kuralı kiosk ile aynıdır: kayıt, kendi `start`–`end` aralığı boyunca gösterilir.
 */
import { kopya } from '@/domain/kopya'
import { computed, ref, watch } from 'vue'

import { DOSYALAR } from '@/aws/config'
import {
  aktifKayitlar,
  gunBloklari,
  gunEtiketi,
  gunSec,
  ozetle,
  tarihMetni,
  tumKayitlar,
  type NobetKaydi,
  type SistemVerisi,
} from '@/domain/veri'
import { useDosyalar } from '@/stores/dosyalar'
import { useBaglanti } from '@/stores/baglanti'
import { silinecekYayinlar } from '@/domain/temizlik'

const dosyalar = useDosyalar()
const baglanti = useBaglanti()
const taslak = ref<SistemVerisi>(kopya(dosyalar.sistemVerisi))
const sekme = ref<'nobet' | 'yayin'>('nobet')
const seciliGun = ref('')
const hata = ref('')
/** Son gösterimden sonra beklenecek güvenlik payı (saat) — temizlik önizlemesi/silme için. */
const ekSaat = ref(2)

watch(
  () => dosyalar.sistem.veri,
  (yeni) => {
    taslak.value = kopya(yeni ?? {})
    seciliGun.value = Object.keys(gunBloklari(taslak.value)).sort()[0] ?? ''
  },
  { deep: true, immediate: true },
)

const gunler = computed(() => Object.keys(gunBloklari(taslak.value)).sort())
const ozet = computed(() => ozetle(taslak.value))
const kirli = computed(() => JSON.stringify(taslak.value) !== JSON.stringify(dosyalar.sistemVerisi))

/** Seçili günün kayıtları (ilçe/bölge ayrımı yapmadan düz liste + konum bilgisi). */
interface Satir {
  kayit: NobetKaydi
  kutu: Record<string, unknown>
  liste: NobetKaydi[]
  ilceId: string
  bolgeId: string
}

const satirlar = computed<Satir[]>(() => {
  const blok = gunBloklari(taslak.value)[seciliGun.value]
  const liste: Satir[] = []
  if (!blok || typeof blok !== 'object') return liste
  for (const [ilceId, ilceListesi] of Object.entries(blok as Record<string, unknown>)) {
    if (!Array.isArray(ilceListesi)) continue
    for (const kutu of ilceListesi as Array<Record<string, unknown>>) {
      for (const [bolgeId, kayitlar] of Object.entries(kutu)) {
        if (!Array.isArray(kayitlar)) continue
        for (const kayit of kayitlar as NobetKaydi[]) {
          liste.push({ kayit, kutu, liste: kayitlar as NobetKaydi[], ilceId, bolgeId })
        }
      }
    }
  }
  return liste
})

const aktif = computed(() => aktifKayitlar(tumKayitlar(taslak.value), new Date()))
const gunSecimi = computed(() => gunSec(taslak.value))

const yayinlar = computed<Array<{ gun: string; veri: unknown }>>(() => {
  const y = (taslak.value.Yayinlar ?? {}) as Record<string, unknown>
  return Object.entries(y).map(([gun, veri]) => ({ gun, veri }))
})

/**
 * SÜRESİ GEÇEN YAYINLAR — önizleme (saf, silme yapmaz).
 *
 * Cihaz tarafı: kiosk, yayının `end` (son gösterim) tarihi + `ONBELLEK_GORSEL_SAKLAMA_GUN`
 * gün geçtikten sonra görseli kendi disk önbelleğinden siler; veride geçmeyenler anında düşer.
 * Sunucu tarafı: bu ekrandaki silme işlemi kovadaki görsel nesnesini ve veri dosyasındaki
 * kaydı kaldırır, ardından `lastupdate` damgasını tazeler (cihazlar saatlik kontrolde alır).
 */
const suresiGecenler = computed(() =>
  silinecekYayinlar(dosyalar.sistemVerisi, new Date(), ekSaat.value, baglanti.kova, baglanti.onEk),
)

async function temizle(): Promise<void> {
  hata.value = ''
  await dosyalar.yayinlariTemizle(false, ekSaat.value)
}

function kayitGuncelle(satir: Satir, alan: keyof NobetKaydi, deger: unknown): void {
  satir.kayit[alan] = deger
  taslak.value = { ...taslak.value }
}

function kayitSil(satir: Satir): void {
  const s = satir.liste.indexOf(satir.kayit)
  if (s >= 0) satir.liste.splice(s, 1)
  taslak.value = { ...taslak.value }
}

function kayitEkle(): void {
  if (!satirlar.value.length) {
    hata.value = 'Şablon oluşturmak için en az bir mevcut kayıt gerekir (kiosk tarafında tools/fetch_nobet.py).'
    return
  }
  const ornek = satirlar.value[0]
  const yeni: NobetKaydi = { ...ornek.kayit, eczane: 'YENİ ECZANE', tel: '' }
  ornek.liste.push(yeni)
  taslak.value = { ...taslak.value }
}

function geriAl(): void {
  taslak.value = kopya(dosyalar.sistemVerisi)
  hata.value = ''
}

async function kaydet(): Promise<void> {
  hata.value = ''
  const bozuk = satirlar.value.find((s) => !String(s.kayit.start ?? '').trim() || !String(s.kayit.end ?? '').trim())
  if (bozuk) {
    hata.value = 'Her kaydın başlangıç ve bitiş zamanı olmalı (ör. 15/10/2026 08:30).'
    return
  }
  await dosyalar.kaydet('sistem', DOSYALAR.sistem, taslak.value)
}

// ----------------------------------------------------- nöbet değişikliği bildirimi
/**
 * `tetikle.json` (kapsam: cihazın ilçesi/bölgesi) yazılır.
 *
 * Cihaz bu dosyayı görünce 20 saniyelik yoklamada (tarayıcı modunda uzun yoklamayla ANINDA)
 * verisini yeniler; `ilceId` boş bırakılırsa TÜM cihazlar yenilenir.
 */
const tetikIlce = ref('')
const tetikGonderiliyor = ref(false)
const tetikBilgi = ref('')

const ilceSecenekleri = computed(() => {
  const gorulen = new Map<string, string>()
  for (const kayit of tumKayitlar(dosyalar.sistemVerisi)) {
    const kimlik = String(kayit.ilceId ?? '').trim()
    if (kimlik && !gorulen.has(kimlik)) gorulen.set(kimlik, String(kayit.ilce ?? kimlik))
  }
  return [
    { baslik: 'Tüm cihazlar (ilçe ayrımı yok)', deger: '' },
    ...[...gorulen.entries()].map(([deger, baslik]) => ({ baslik, deger })),
  ]
})

async function tetikBildir(): Promise<void> {
  hata.value = ''
  tetikBilgi.value = ''
  tetikGonderiliyor.value = true
  try {
    const kaynak = baglanti.kaynak
    if (!kaynak) {
      hata.value = 'Bağlantı kurulmadan bildirim gönderilemez (S3/Cognito ayarlarını kontrol edin).'
      return
    }
    const belge = {
      zaman: new Date().toISOString(),
      ilceId: tetikIlce.value,
      bolgeId: '',
      aciklama: 'Panelden bildirildi',
    }
    await kaynak.yaz('tetikle.json', belge)
    const kapsam = tetikIlce.value || 'tüm cihazlar'
    tetikBilgi.value = `Gönderildi (${kapsam}) · ${belge.zaman}`
  } catch (e) {
    hata.value = `Bildirim gönderilemedi: ${(e as Error).message}`
  } finally {
    tetikGonderiliyor.value = false
  }
}
</script>

<template>
  <div>
    <div class="d-flex align-center mb-4">
      <div>
        <h2 class="text-h5 mb-1">Nöbet ve Yayınlar</h2>
        <div class="text-body-2 text-medium-emphasis">
          <code>{{ DOSYALAR.sistem }}</code> — cihazın ekranda kullandığı veri. Nöbet penceresi
          (<code>start → end</code>) kaydın kendisinde tutulur; ekranda <strong>yalnızca devam eden</strong>
          nöbet görünür, biten nöbet kendiliğinden düşer.
        </div>
      </div>
      <v-spacer />
      <v-chip v-if="kirli" color="warning" variant="tonal" class="mr-3">kaydedilmemiş</v-chip>
      <v-btn class="mr-2" variant="text" prepend-icon="mdi-undo" :disabled="!kirli" @click="geriAl">Geri al</v-btn>
      <v-btn color="primary" prepend-icon="mdi-content-save" :loading="dosyalar.mesgul" :disabled="!kirli" @click="kaydet">
        Kaydet
      </v-btn>
    </div>

    <v-alert v-if="hata" type="error" variant="tonal" class="mb-4">{{ hata }}</v-alert>
    <v-alert v-if="ozet.geciciMi" type="warning" variant="tonal" class="mb-4">
      Bu dosya GEÇİCİ TEST verisi içeriyor (5+ nöbetçi görünümü için üretilmişti).
    </v-alert>

    <v-row dense class="mb-4">
      <v-col cols="6" md="2"><v-card><v-card-text><div class="text-caption">Gün</div><div class="text-h6">{{ ozet.gunSayisi }}</div></v-card-text></v-card></v-col>
      <v-col cols="6" md="2"><v-card><v-card-text><div class="text-caption">Kayıt</div><div class="text-h6">{{ ozet.kayitSayisi }}</div></v-card-text></v-card></v-col>
      <v-col cols="6" md="2"><v-card><v-card-text><div class="text-caption">İlçe</div><div class="text-h6">{{ ozet.ilceSayisi }}</div></v-card-text></v-card></v-col>
      <v-col cols="6" md="2"><v-card><v-card-text><div class="text-caption">Bölge</div><div class="text-h6">{{ ozet.bolgeSayisi }}</div></v-card-text></v-card></v-col>
      <v-col cols="12" md="4">
        <v-card>
          <v-card-text>
            <div class="text-caption">Şu an gösterilen gün</div>
            <div class="text-h6">{{ gunEtiketi(gunSecimi.anahtar) || '—' }}</div>
            <div class="text-caption text-medium-emphasis">{{ gunSecimi.kaynak }} · {{ aktif.length }} aktif kayıt</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-tabs v-model="sekme" class="mb-3">
      <v-tab value="nobet">Nöbetler ({{ satirlar.length }})</v-tab>
      <v-tab value="yayin">Yayınlar ({{ yayinlar.length }} gün)</v-tab>
    </v-tabs>

    <v-tabs-window v-model="sekme">
      <v-tabs-window-item value="nobet">
        <v-card>
          <v-card-title class="d-flex align-center">
            <v-select v-model="seciliGun" :items="gunler" label="Gün" density="compact" hide-details class="mr-3" style="max-width: 220px">
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" :title="gunEtiketi(String(item.value))" />
              </template>
            </v-select>
            <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="kayitEkle">Kayıt ekle</v-btn>
            <v-spacer />
            <span class="text-caption text-medium-emphasis">Kayıtlar kiosk ile aynı biçimde düzenlenir</span>
          </v-card-title>
          <v-card-text>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>İlçe / Bölge</th><th>Eczane</th><th>Telefon</th><th>Adres</th>
                  <th>Adres tarifi</th><th>Başlangıç</th><th>Bitiş</th><th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(s, i) in satirlar" :key="`${s.bolgeId}-${i}`">
                  <td class="text-caption">
                    {{ s.kayit.ilce }}<br />
                    <span class="text-medium-emphasis">{{ s.kayit.bolge }} ({{ s.bolgeId }})</span>
                  </td>
                  <td><v-text-field :model-value="String(s.kayit.eczane ?? '')" density="compact" hide-details @update:model-value="(v: unknown) => kayitGuncelle(s, 'eczane', String(v ?? ''))" /></td>
                  <td><v-text-field :model-value="String(s.kayit.tel ?? '')" density="compact" hide-details @update:model-value="(v: unknown) => kayitGuncelle(s, 'tel', String(v ?? ''))" /></td>
                  <td><v-text-field :model-value="String(s.kayit.adres ?? '')" density="compact" hide-details @update:model-value="(v: unknown) => kayitGuncelle(s, 'adres', String(v ?? ''))" /></td>
                  <td><v-text-field :model-value="String(s.kayit.adres_tarifi ?? '')" density="compact" hide-details @update:model-value="(v: unknown) => kayitGuncelle(s, 'adres_tarifi', String(v ?? ''))" /></td>
                  <td><v-text-field :model-value="String(s.kayit.start ?? '')" density="compact" hide-details placeholder="dd/aa/yyyy ss:dd" @update:model-value="(v: unknown) => kayitGuncelle(s, 'start', String(v ?? ''))" /></td>
                  <td><v-text-field :model-value="String(s.kayit.end ?? '')" density="compact" hide-details placeholder="dd/aa/yyyy ss:dd" @update:model-value="(v: unknown) => kayitGuncelle(s, 'end', String(v ?? ''))" /></td>
                  <td><v-btn size="x-small" variant="text" color="error" icon="mdi-delete" @click="kayitSil(s)" /></td>
                </tr>
                <tr v-if="!satirlar.length"><td colspan="8" class="text-medium-emphasis">Bu günde kayıt yok.</td></tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-tabs-window-item>

      <v-tabs-window-item value="yayin">
        <v-card>
          <v-card-title class="text-subtitle-1">Yayınlar (görsel modu)</v-card-title>
          <v-card-subtitle>
            Yayınlar cihazın veri kaynağından gelir; panelde görüntülenir. Kayan yazı kuşağı
            (eczane – telefon) nöbet kayıtlarından üretilir.
          </v-card-subtitle>
          <v-card-text>
            <v-expansion-panels variant="accordion">
              <v-expansion-panel v-for="y in yayinlar" :key="y.gun" :title="gunEtiketi(y.gun)">
                <v-expansion-panel-text>
                  <pre class="text-caption" style="white-space: pre-wrap">{{ JSON.stringify(y.veri, null, 2) }}</pre>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
            <div class="text-caption text-medium-emphasis mt-3">
              Son gösterim: {{ yayinlar.length ? gunEtiketi(yayinlar[yayinlar.length - 1].gun) : '—' }} ·
              {{ tarihMetni(new Date()) }}
            </div>
          </v-card-text>
        </v-card>

        <!-- ============ süresi geçen yayınların temizliği (S3 + cihaz) ============ -->
        <v-card class="mt-4" variant="tonal">
          <v-card-title class="text-subtitle-1 d-flex align-center">
            <span>Süresi geçen yayınlar</span>
            <v-chip
              class="ml-2"
              size="small"
              variant="flat"
              :color="suresiGecenler.silinenler.length ? 'warning' : 'success'"
            >
              {{ suresiGecenler.silinenler.length }}
            </v-chip>
          </v-card-title>
          <v-card-subtitle>
            Bir yayının <code>end</code> alanı onun <strong>son gösterim tarihidir</strong>. Bu tarih geçen
            yayınlar ne cihazda ne sunucuda tutulmalıdır: cihaz kendi görsel önbelleğini kendiliğinden
            temizler, sunucu tarafı (S3 nesnesi + <code>{{ DOSYALAR.sistem }}</code> kaydı) buradan silinir.
          </v-card-subtitle>
          <v-card-text>
            <v-table v-if="suresiGecenler.silinenler.length" density="compact">
              <thead>
                <tr><th>No</th><th>Son gösterim</th><th>Görsel</th><th>Kovadaki nesne</th></tr>
              </thead>
              <tbody>
                <tr v-for="y in suresiGecenler.silinenler" :key="y.id">
                  <td>{{ y.id }}</td>
                  <td class="text-caption">{{ tarihMetni(y.bitis) }}</td>
                  <td class="text-caption" style="max-width: 320px; overflow-wrap: anywhere">{{ y.url || '—' }}</td>
                  <td class="text-caption">
                    <v-chip size="x-small" variant="tonal" :color="y.anahtar ? 'primary' : 'grey'">
                      {{ y.anahtar ? 'bizim kovamız' : 'dış adres (cihaz temizler)' }}
                    </v-chip>
                  </td>
                </tr>
              </tbody>
            </v-table>
            <v-alert v-else-if="suresiGecenler.atlananlar" type="info" variant="tonal">
              Süresi geçen yayın yok. {{ suresiGecenler.atlananlar }} kaydın son gösterim tarihi
              okunamadı; yanlışlıkla canlı yayın silmemek için bunlara dokunulmadı.
            </v-alert>
            <v-alert v-else type="success" variant="tonal">Süresi geçen yayın yok.</v-alert>

            <div class="d-flex align-center flex-wrap ga-3 mt-3">
              <v-text-field
                v-model.number="ekSaat"
                type="number"
                label="Güvenlik payı (saat)"
                density="compact"
                hide-details
                style="max-width: 200px"
              />
              <v-btn
                color="warning"
                variant="tonal"
                prepend-icon="mdi-delete-sweep"
                :loading="dosyalar.mesgul"
                :disabled="!suresiGecenler.silinenler.length"
                @click="temizle"
              >
                Süresi geçenleri sil
              </v-btn>
              <span class="text-caption text-medium-emphasis">
                Kayıt silinir · kendi kovamızdaki görsel nesnesi silinir · cihazlar damgayla tazelenir
              </span>
            </div>
          </v-card-text>
        </v-card>
      </v-tabs-window-item>
    </v-tabs-window>

    <!-- NÖBET DEĞİŞİKLİĞİ BİLDİRİMİ: cihazları saatlik kontrolü beklemeden yeniletir -->
    <v-card class="mt-4">
      <v-card-title class="text-subtitle-1">Cihazlara hemen bildir (nöbet değişikliği)</v-card-title>
      <v-card-text>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Veri değişikliğini kaydettikten sonra bu bildirimi gönderin: cihazlar
          <code>tetikle.json</code> dosyasını görüp <strong>saatlik kontrolü beklemeden</strong> yenilenir
          (tarayıcı modunda uzun yoklama ile genelde 1 saniye içinde, Qt modunda en çok 20 saniye).
          Yalnızca seçtiğiniz ilçenin cihazları hemen yenilenir; diğerleri normal saatlik kontrolde alır.
        </div>
        <div class="d-flex align-center flex-wrap ga-3">
          <v-select
            v-model="tetikIlce"
            :items="ilceSecenekleri"
            item-title="baslik"
            item-value="deger"
            label="Kapsam (ilçe)"
            density="compact"
            hide-details
            style="max-width: 360px"
          />
          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-bell-ring"
            :loading="tetikGonderiliyor"
            @click="tetikBildir"
          >
            Bildir
          </v-btn>
          <span v-if="tetikBilgi" class="text-caption text-success">{{ tetikBilgi }}</span>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>
