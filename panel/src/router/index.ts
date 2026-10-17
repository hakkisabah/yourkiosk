/**
 * Yönlendirme — S3 statik barındırma ile uyum için hash geçmişi kullanılır
 * (sunucuda yönlendirme kuralı gerekmez).
 *
 * Menü ve oturum kuralları `kurallar.ts` içindedir: o dosya tarayıcı gerektirmez,
 * bu yüzden testlerde doğrudan doğrulanabilir (`src/stores/baglanti.test.ts`).
 */
import { createRouter, createWebHashHistory } from 'vue-router'

import { useBaglanti } from '@/stores/baglanti'

import { MENU, rotaIzni } from './kurallar'

export { MENU, rotaIzni }

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/durum' },
    { path: '/giris', name: 'giris', component: () => import('@/views/GirisView.vue'), meta: { genel: true } },
    { path: '/kurulum', name: 'kurulum', component: () => import('@/views/KurulumView.vue'), meta: { genel: true } },
    { path: '/durum', name: 'durum', component: () => import('@/views/DurumView.vue') },
    { path: '/ayarlar', name: 'ayarlar', component: () => import('@/views/AyarlarView.vue') },
    { path: '/kapsam', name: 'kapsam', component: () => import('@/views/KapsamView.vue') },
    { path: '/veri', name: 'veri', component: () => import('@/views/VeriView.vue') },
    { path: '/cihazlar', name: 'cihazlar', component: () => import('@/views/CihazlarView.vue') },
    { path: '/sablon', name: 'sablon', component: () => import('@/views/SablonView.vue') },
    { path: '/gelismis', name: 'gelismis', component: () => import('@/views/GelismisView.vue') },
    { path: '/:yol(.*)*', redirect: '/durum' },
  ],
})

router.beforeEach((hedef) => {
  const baglanti = useBaglanti()
  return rotaIzni(hedef, {
    hazir: baglanti.hazir,
    yapilandirmaHatasi: baglanti.yapilandirmaHatasi,
    girisYapildi: baglanti.girisYapildi,
  })
})
