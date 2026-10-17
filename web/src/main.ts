/**
 * Giriş noktası: yerleşim/renk değişkenlerini uygular ve kiosk arayüzünü başlatır.
 *
 * Görsel değerler `yerlesim.json`dan gelir (kiosk/tools/web_disa_aktar.py üretir) →
 * Qt ile arayüz arasında ölçü/punto/renk sapması olmaz.
 */
import { createApp } from 'vue'

import App from '@/App.vue'
import { cssDegiskenleriniUygula } from '@/stiller/olcu'
import '@/stiller/kiosk.css'

cssDegiskenleriniUygula()

createApp(App).mount('#uygulama')
