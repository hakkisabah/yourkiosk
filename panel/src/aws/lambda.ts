/**
 * Lambda modu istemcisi (Cognito YOK): oturum cookie'si + presigned S3 URL'leri.
 * Sunucu tarafı: `panel/lambda/handler.py` (aynı beyaz liste ve kurallar).
 */
import type { PanelConfig } from './config'

export interface ImzaSonucu {
  url: string
  islem: 'oku' | 'yaz'
}

export type FetchGibi = (girdi: string, baslat?: RequestInit) => Promise<Response>

export class OturumYok extends Error {
  constructor() {
    super('Oturum bulunamadı veya süresi doldu; yeniden giriş yapın.')
    this.name = 'OturumYok'
  }
}

/** Sunucudan gelen okunur hata mesajını çıkarır. */
async function _hata(yanit: Response): Promise<Error> {
  let mesaj = `Sunucu hatası (${yanit.status})`
  try {
    const veri = (await yanit.json()) as { hata?: string }
    if (veri?.hata) mesaj = veri.hata
  } catch {
    /* gövde JSON değilse varsayılan mesaj kalır */
  }
  return yanit.status === 401 ? new OturumYok() : new Error(mesaj)
}

/**
 * Lambda API istemcisi.
 * `fetchGibi` testte taklit edilebilir (ağa çıkmadan doğrulanır).
 */
export class LambdaIstemcisi {
  constructor(
    private readonly cfg: PanelConfig,
    private readonly fetchGibi: FetchGibi = globalThis.fetch.bind(globalThis),
  ) {}

  private async _cagir<T>(yol: string, govde?: unknown, yontem = 'POST'): Promise<T> {
    const yanit = await this.fetchGibi(`${this.cfg.apiUrl.replace(/\/+$/, '')}${yol}`, {
      method: yontem,
      // Oturum HttpOnly cookie'de tutulur → tarayıcı göndermeli
      credentials: 'include',
      headers: govde === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: govde === undefined ? undefined : JSON.stringify(govde),
    })
    if (!yanit.ok) throw await _hata(yanit)
    if (yontem === 'OPTIONS') return undefined as T
    return (await yanit.json()) as T
  }

  giris(sifre: string): Promise<{ giris: boolean }> {
    return this._cagir<{ giris: boolean }>('/giris', { sifre })
  }

  oturumKontrol(): Promise<{ giris: boolean }> {
    return this._cagir<{ giris: boolean }>('/oturum', undefined, 'GET')
  }

  cikis(): Promise<{ cikis: boolean }> {
    return this._cagir<{ cikis: boolean }>('/cikis', {})
  }

  imzala(istek: { dosya: string; islem: 'oku' | 'yaz'; etag?: string; boyut?: number }): Promise<ImzaSonucu> {
    return this._cagir<ImzaSonucu>('/imzala', istek)
  }

  /** Presigned URL ile doğrudan S3'e istek (kimlik bilgisi taşımaz). */
  async s3Istek(url: string, baslat: RequestInit): Promise<Response> {
    return this.fetchGibi(url, { credentials: 'omit', ...baslat })
  }
}
