/** Vuetify kurulumu — kiosk ekranıyla aynı koyu dil, sade bir yönetim arayüzü. */
import { createVuetify } from 'vuetify'
import { tr } from 'vuetify/locale'

export const vuetify = createVuetify({
  locale: { locale: 'tr', fallback: 'en', messages: { tr } },
  theme: {
    defaultTheme: 'koyu',
    themes: {
      koyu: {
        dark: true,
        colors: {
          background: '#101418',
          surface: '#161b22',
          primary: '#c8102e',
          secondary: '#2f81f7',
          success: '#2ea043',
          warning: '#d29922',
          error: '#f85149',
          info: '#58a6ff',
        },
      },
    },
  },
  defaults: {
    VCard: { variant: 'flat' },
    VTextField: { variant: 'outlined', density: 'comfortable' },
    VSelect: { variant: 'outlined', density: 'comfortable' },
    VCombobox: { variant: 'outlined', density: 'comfortable' },
    VSwitch: { color: 'primary', hideDetails: 'auto' },
    VBtn: { variant: 'flat' },
  },
})
