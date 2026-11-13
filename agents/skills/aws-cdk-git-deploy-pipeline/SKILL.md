---
name: aws-cdk-git-deploy-pipeline
description: Use when wiring git-to-AWS auto-deploy for a CDK app.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [aws, cdk, cicd, github-actions, security, oidc]
    related_skills: [github, ts-monorepo-build-gotchas]
---

# AWS CDK + git otomatik dağıtım hattı

Bir CDK uygulamasını git deposuna bağlarken güvenlik ve yapısal tuzaklar.

## When to Use

- User asks whether putting the repo on GitHub/GitLab enables automatic deployment
- Granting CI access to AWS, setting up an OIDC role, or reporting infra diffs on PRs
- The self-hosted runner (home PC / office server) trade-off comes up

## Ne zaman kullanılır

- "Repoyu GitHub/GitLab'a koysam otomatik deploy olur mu?" sorusu
- CI'a AWS erişimi verme, OIDC rolü kurma, PR'da altyapı farkı raporlama
- Self-hosted runner (ev PC / ofis sunucusu) tartışması

## Kurallar

1. **Uzun ömürlü AWS anahtarı CI'a KOYULMAZ.** GitHub Secret bile olsa sızma
   yolları var (`pull_request_target`, tag ile sabitlenmiş 3. parti action,
   ele geçirilmiş maintainer hesabı). OIDC kullan:
   `AssumeRoleWithWebIdentity`, koşul `sub = repo:ORG/REPO:ref:refs/heads/main`
   (+ gerekiyorsa `:environment:production`). Kalıcı sır yok, rotasyon yok.
2. **Asıl risk anahtar değil, rolün genişliğidir.** `cdk deploy` IAM/Lambda/
   CloudFront/Cognito oluşturur. `iam:PassRole` verilirse CDK bootstrap
   rollerine delege edebilir → rol fiilen admin olur. `PassRole`'ü yalnızca
   `cdk-*-cfn-exec-role` / `cdk-*-deploy-role` ARN'lerine kısıtla.
3. **Deploy işi `pull_request`/`pull_request_target` olayında KOŞMAZ.** Fork
   PR + yazma yetkisi = RCE yolu. Yalnızca `main` push'u veya
   `workflow_dispatch`, GitHub Environment + required reviewers ile onaylı.
4. **`cdk diff` PR'da kullanılamaz (kimlik ister).** Canlı stack durumunu
   okumak AWS kimliği gerektirir. Kimliksiz alternatif: temel dal ve PR dalını
   ayrı ayrı `cdk synth` edip `*.template.json` dosyalarını karşılaştır.
   Raporu `$GITHUB_STEP_SUMMARY`'ye yaz — PR yorumu `pull-requests: write`
   ister ve fork PR'larında `pull_request_target` tuzağına davet eder.
   Canlı hesapla gerçek `cdk diff` gerekiyorsa **okuma yetkili** ayrı OIDC rolü.
5. **Sentezden ÖNCE derle.** `cdk synth`/`deploy` Lambda asset'lerini şablona
   gömer; asset kaynağı (ör. `backend/dist`, `frontend/dist`) yoksa boş ya da
   eski kod dağıtılır. CI sırası: `shared` → backend build → frontend build →
   infra build → synth/deploy. Temel dal farkı için `git worktree add`.
6. **`npm ci` her yerde `--include=dev`.** Hostta/CI imajında
   `NODE_ENV=production` export edilmişse devDependencies atlanır ve
   vite/tsc/vitest "kurulu görünmeden" kaybolur.
7. **Action'ları commit SHA'sıyla sabitle.** Tag kaydırılabilir. SHA almak için
   `git/ref/tags/<tag>` → dönen SHA **annotated tag objesi** olabilir! Doğrula:
   `GET /repos/OWNER/REPO/commits/<sha>` commit mesajı dönmeli; dönmezse tag
   objesidir, `git/tags/<sha>` ile dereference et.
8. **Deploy rolünde `cdk destroy` izni olmasın.** Yanlış tetiklenen bir destroy
   Cognito user pool'u siler → kullanıcılar gider. Veri tutan kaynaklarda
   `RemovalPolicy.RETAIN`.
9. **`concurrency` kilidi koy** — elle ve CI'dan aynı anda iki deploy aynı
   stack'i kilitler (CloudFormation `UPDATE_IN_PROGRESS` çakışması).

## Self-hosted runner (ev PC / ofis sunucusu)

- Git kurmak/push'lamak **hiçbir AWS yetkisi vermez** — zararsız. Runner
  *kurmak* makineye kod çalıştırma yetkisi verir; risk orada başlar.
- **Public repoda self-hosted runner kesinlikle yasak**: herkes PR açıp senin
  makinende komut çalıştırabilir.
- Private repoda bile: ayrı kullanıcı + konteyner/VM, ephemeral ortam,
  `~/.aws` kalıcı profili yerine kısa ömürlü OIDC kimliği, yalnızca
  `self-hosted` etiketli **test** işleri. Deploy yok.
- Meşru kazanç: sıfır dakika maliyeti + E2E/tarayıcı testleri (bulut
  runner'da tarayıcı kurulumu yavaş/pahalı).

## Aşamalı yol (kanıtlanmış)

1. **Aşama 0** — `git init` + sır taraması (`git grep --cached -nE
   "AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_|xox[baprs]-"`) +
   `.gitignore` doğrulaması (`git check-ignore -q <yol>`) + `git add -A`
   sonrası yasak yol/büyük dosya kontrolü + ilk commit. Uzak depo YOK.
2. **Aşama 1** — PR'da test + sentez + kimliksiz şablon farkı (kural 4).
3. **Aşama 2** — OIDC rolü + Environment onaylı `deploy.yml`.
4. **Aşama 3** — prod izolasyonu (ayrı hesap veya stack öneki), release/tag.
5. **Aşama 4** — ev PC yalnızca E2E testleri için.

## `.gitignore` (CDK/monorepo için asgari)

`node_modules/`, `dist/`, `coverage/`, `cdk.out/`, `.env`, `.env.*` +
`!.env.example`, `*.tsbuildinfo`, `.eslintcache`, `.vite/`, `.vitest/`,
`playwright-report/`, `test-results/`, `infra/cdk.context.json` (hesap/AMI
kimliği sızdırır; yalnızca bağlam araması yapan stack'lerde gerekir).

`shared/**/*.js` + `*.d.ts` yasaklanmalı: tsc yanlış `rootDir` ile derlediğinde
kaynak ağacına `.js` bırakır ve Vite `.js`'i `.ts`'ten önce çözer → kaynak
sessizce gölgelenir ("değişikliğim neden etkisiz?").

## Testte ortam bağımlılığı tuzağı

`import.meta.env.DEV` ile karar veren bileşenlerin testleri **ortam
`NODE_ENV`'ine göre kararsız** olur (CI'da geçer, `NODE_ENV=production`
export eden hostta düşer). Test `vi.stubEnv('DEV', true)` + `vi.unstubAllEnvs()`
ile ortamdan bağımsız hale getirilmeli ve iki farklı `NODE_ENV` ile koşulmalı.
