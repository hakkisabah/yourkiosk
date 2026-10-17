<script setup lang="ts">
/**
 * Ayar formu — şemadan (`sema.ts`) üretilir; her anahtar tipine uygun denetim.
 * `mod="kapsam"` iken değerler devralınır ve yalnızca "geçersiz kıl" denince düzenlenir;
 * böylece ilçe/bölge/cihaz bazında yalnızca gerekli anahtarlar yazılır.
 */
import { computed, ref } from 'vue'

import { dogrula, type AyarGrubu, type AyarTanimi } from '@/domain/sema'

const props = withDefaults(
  defineProps<{
    grup: AyarGrubu
    /** Gösterilecek/etkin değerler (tam anahtar → değer) */
    etkin: Record<string, unknown>
    /** Yalnızca bu kapsamda geçersiz kılınmış anahtarlar */
    degisiklikler?: Record<string, unknown>
    kaynaklar?: Record<string, string>
    mod?: 'duzenle' | 'kapsam'
    gelismisGoster?: boolean
  }>(),
  { degisiklikler: () => ({}), kaynaklar: () => ({}), mod: 'duzenle', gelismisGoster: false },
)
const emit = defineEmits<{ guncelle: [tam: string, deger: unknown]; kaldir: [tam: string] }>()

const hatalar = ref<Record<string, string>>({})

const anahtarlar = computed(() =>
  props.grup.anahtarlar.filter((a) => props.gelismisGoster || !a.gelismis),
)

const gecersizKilinmis = (tam: string): boolean => Object.prototype.hasOwnProperty.call(props.degisiklikler, tam)
const duzenlenebilir = (tam: string): boolean => props.mod === 'duzenle' || gecersizKilinmis(tam)
const deger = (tam: string): unknown => (gecersizKilinmis(tam) ? props.degisiklikler[tam] : props.etkin[tam])

function gonder(t: AyarTanimi, ham: unknown): void {
  const sonuc = dogrula(t.tam, ham)
  if (!sonuc.gecerli) {
    hatalar.value = { ...hatalar.value, [t.tam]: sonuc.hata ?? 'geçersiz değer' }
    return
  }
  const { [t.tam]: _at, ...kalan } = hatalar.value
  hatalar.value = kalan
  emit('guncelle', t.tam, sonuc.deger)
}

const sayiMetni = (t: AyarTanimi): string => {
  const d = deger(t.tam)
  return d === null || d === undefined ? '' : String(d)
}

const listeMetni = (t: AyarTanimi): string => {
  const d = deger(t.tam)
  return Array.isArray(d) ? d.join(', ') : ''
}

const listeDegeri = (t: AyarTanimi): string[] => {
  const d = deger(t.tam)
  return Array.isArray(d) ? d.map((x) => String(x)) : []
}

const sayiListesiAyikla = (metin: string): number[] =>
  metin
    .split(/[,\s\n]+/)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => Number(x))
</script>

<template>
  <div>
    <template v-for="t in anahtarlar" :key="t.tam">
      <v-row dense class="align-center py-1">
        <v-col cols="12" md="5">
          <div class="font-weight-medium">
            {{ t.etiket }}
            <v-chip v-if="mod === 'kapsam'" size="x-small" variant="tonal" class="ml-2">
              {{ gecersizKilinmis(t.tam) ? 'geçersiz kılındı' : kaynaklar[t.tam] || 'devralınan' }}
            </v-chip>
          </div>
          <div class="text-caption text-medium-emphasis">
            <span v-if="t.aciklama">{{ t.aciklama }}</span>
            <span v-else>{{ t.tam }}</span>
            <span v-if="t.gelismis" class="text-warning ml-1">· GELİŞMİŞ</span>
          </div>
        </v-col>

        <v-col cols="12" md="5">
          <!-- mantıksal -->
          <v-switch
            v-if="t.tip === 'bool'"
            :model-value="Boolean(deger(t.tam))"
            :disabled="!duzenlenebilir(t.tam)"
            :label="Boolean(deger(t.tam)) ? 'açık' : 'kapalı'"
            @update:model-value="(v: unknown) => gonder(t, v)"
          />

          <!-- seçim -->
          <v-select
            v-else-if="t.tip === 'secim'"
            :model-value="String(deger(t.tam) ?? '')"
            :items="t.izinli ?? []"
            :disabled="!duzenlenebilir(t.tam)"
            @update:model-value="(v: unknown) => gonder(t, v)"
          />

          <!-- sayı -->
          <v-text-field
            v-else-if="t.tip === 'int' || t.tip === 'float'"
            :model-value="sayiMetni(t)"
            type="number"
            :suffix="t.birim"
            :disabled="!duzenlenebilir(t.tam)"
            :hint="`${t.alt ?? '—'} … ${t.ust ?? '—'}${t.birim ? ' ' + t.birim : ''}`"
            :error-messages="hatalar[t.tam]"
            persistent-hint
            @update:model-value="(v: unknown) => gonder(t, v)"
          />

          <!-- metin listesi -->
          <v-combobox
            v-else-if="t.tip === 'liste'"
            :model-value="listeDegeri(t)"
            chips
            multiple
            clearable
            :disabled="!duzenlenebilir(t.tam)"
            :error-messages="hatalar[t.tam]"
            @update:model-value="(v: unknown) => gonder(t, v)"
          />

          <!-- sayı listesi -->
          <v-text-field
            v-else-if="t.tip === 'sayi_listesi'"
            :model-value="listeMetni(t)"
            :disabled="!duzenlenebilir(t.tam)"
            hint="virgülle ayırın, ör. 443"
            :error-messages="hatalar[t.tam]"
            persistent-hint
            @update:model-value="(v: unknown) => gonder(t, sayiListesiAyikla(String(v ?? '')))"
          />

          <!-- metin -->
          <v-text-field
            v-else
            :model-value="deger(t.tam) === null || deger(t.tam) === undefined ? '' : String(deger(t.tam))"
            :disabled="!duzenlenebilir(t.tam)"
            :error-messages="hatalar[t.tam]"
            @update:model-value="(v: unknown) => gonder(t, String(v ?? ''))"
          />
        </v-col>

        <v-col cols="12" md="2" class="text-right">
          <template v-if="mod === 'kapsam'">
            <v-btn
              v-if="!gecersizKilinmis(t.tam)"
              size="small"
              variant="tonal"
              prepend-icon="mdi-pencil"
              @click="emit('guncelle', t.tam, props.etkin[t.tam])"
            >
              Geçersiz kıl
            </v-btn>
            <v-btn v-else size="small" variant="text" prepend-icon="mdi-undo" @click="emit('kaldir', t.tam)">
              Kaldır
            </v-btn>
          </template>
          <v-chip v-else-if="t.varsayilan === deger(t.tam)" size="small" variant="text">varsayılan</v-chip>
          <v-btn v-else size="small" variant="text" prepend-icon="mdi-undo" @click="emit('guncelle', t.tam, t.varsayilan)">
            sıfırla
          </v-btn>
        </v-col>
      </v-row>
      <v-divider class="my-1" />
    </template>
  </div>
</template>
