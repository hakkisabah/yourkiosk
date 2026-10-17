import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { hataYakalayicilariKur } from './hata'
import { vuetify } from './plugins/vuetify'
import { router } from './router'

const uygulama = createApp(App)
hataYakalayicilariKur(uygulama)
uygulama.use(createPinia()).use(router).use(vuetify).mount('#app')
