/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** AWS bölgesi (ör. eu-central-1) */
  readonly VITE_AWS_REGION?: string
  /** Cognito User Pool kimliği (yönetici girişi) */
  readonly VITE_USER_POOL_ID?: string
  /** Cognito User Pool uygulama istemcisi (istemci sırrı OLMADAN) */
  readonly VITE_USER_POOL_CLIENT_ID?: string
  /** Cognito Identity Pool kimliği (S3 için geçici AWS anahtarları) */
  readonly VITE_IDENTITY_POOL_ID?: string
  /** Kiosk verilerinin tutulduğu S3 kovası */
  readonly VITE_BUCKET?: string
  /** Kovadaki ön ek (ör. "kiosk/") */
  readonly VITE_PREFIX?: string
  /** Panel → cihaz anlık tetikleme: broker WebSocket adresi (sır DEĞİL) */
  readonly VITE_MQTT_URL?: string
  /** Yayın konusu (varsayılan `yourkiosk/yayin`; sır DEĞİL) */
  readonly VITE_MQTT_KONU?: string
  /** Yayın hesabının kullanıcı adı (sır DEĞİL; parola oturumda sorulur) */
  readonly VITE_MQTT_KULLANICI?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
