/**
 * Yönetici girişi — Cognito User Pool (tek kullanıcı) + Identity Pool (geçici AWS anahtarı).
 *
 * Neden bu yol: S3'e doğrudan tarayıcıdan yazabilmek için imzalı istek gerekir.
 * Sunucu (Lambda) yok; bu yüzden User Pool ile kimlik doğrulanır, Identity Pool
 * ile sınırlı IAM rolüne sahip geçici anahtarlar alınır (`infra/iam-policy.json`).
 * Panelde hiçbir şifre/anahtar saklanmaz; oturum Cognito'nun localStorage'ında tutulur.
 */
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  type CognitoUserSession,
} from 'amazon-cognito-identity-js'

import { hataMesaji, type PanelConfig } from './config'

let _havuz: CognitoUserPool | null = null

export function havuz(cfg: PanelConfig): CognitoUserPool {
  if (!_havuz) {
    _havuz = new CognitoUserPool({
      UserPoolId: cfg.userPoolId,
      ClientId: cfg.userPoolClientId,
    })
  }
  return _havuz
}

/** E-posta + şifre ile giriş; ID token döner (S3 erişimi için kullanılır). */
export function girisYap(cfg: PanelConfig, eposta: string, sifre: string): Promise<string> {
  return new Promise((cozum, red) => {
    const kullanici = new CognitoUser({ Username: eposta.trim(), Pool: havuz(cfg) })
    kullanici.authenticateUser(new AuthenticationDetails({ Username: eposta.trim(), Password: sifre }), {
      onSuccess: (oturum: CognitoUserSession) => cozum(oturum.getIdToken().getJwtToken()),
      onFailure: (hata: unknown) => red(new Error(hataMesaji(hata))),
      newPasswordRequired: () => red(new Error('Yönetici şifresi ilk girişte değiştirilmeli (Cognito konsolu).')),
    })
  })
}

/** Açık oturumdan ID token alır (gerekirse sessizce yeniler). */
export function oturumTokeni(cfg: PanelConfig): Promise<string | null> {
  return new Promise((cozum) => {
    const kullanici = havuz(cfg).getCurrentUser()
    if (!kullanici) return cozum(null)
    kullanici.getSession((hata: unknown, oturum: CognitoUserSession | null) => {
      if (hata || !oturum || !oturum.isValid()) return cozum(null)
      cozum(oturum.getIdToken().getJwtToken())
    })
  })
}

export function cikisYap(cfg: PanelConfig, eposta?: string): void {
  havuz(cfg).getCurrentUser()?.signOut()
  if (eposta) {
    // Diğer sekmelerdeki oturum da kapansın
    try {
      localStorage.removeItem(`CognitoIdentityServiceProvider.${cfg.userPoolClientId}.${eposta}.idToken`)
    } catch {
      /* localStorage erişilemezse sorun değil */
    }
  }
}
