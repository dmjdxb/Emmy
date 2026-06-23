# Robin — macOS code signing & notarization (runbook)

You have an Apple Developer account, so this is a one-time setup: gather **5
values** from Apple and paste them as **GitHub repository secrets**. After that,
every tagged release is automatically signed + notarized — no rebuild, no local
steps. If the secrets are absent, CI still builds (unsigned); it never fails for
lack of them.

The release workflow consumes exactly these names:

| GitHub secret | Purpose |
|---|---|
| `CSC_LINK` | Developer ID Application certificate (`.p12`, base64) — **signs** the app |
| `CSC_KEY_PASSWORD` | password for that `.p12` |
| `APPLE_API_KEY` | App Store Connect API key (`.p8` contents) — **notarizes** the app |
| `APPLE_API_KEY_ID` | the API key's Key ID |
| `APPLE_API_ISSUER` | your App Store Connect Issuer ID |

---

## Part A — the signing certificate → `CSC_LINK` + `CSC_KEY_PASSWORD`

You need a **Developer ID Application** certificate (the kind for distributing
outside the Mac App Store — *not* "Apple Development" or "Mac App Distribution").

**Easiest path (Xcode):**
1. Xcode → Settings → Accounts → select your team → **Manage Certificates…**
2. Click **+** → **Developer ID Application**. It installs into your login keychain.

**Or without Xcode:** developer.apple.com → Certificates → **+** → "Developer ID
Application", upload a CSR (Keychain Access → Certificate Assistant → Request a
Certificate from a Certificate Authority → Saved to disk), download the `.cer`,
double-click to install.

**Export it as a password-protected `.p12`:**
1. Open **Keychain Access** → **login** keychain → **My Certificates**.
2. Find **"Developer ID Application: <Your Name> (TEAMID)"**, expand it so the
   private key is included, right-click → **Export…** → save `robin-signing.p12`,
   set a strong password (this becomes `CSC_KEY_PASSWORD`).
3. Base64-encode it for the secret:
   ```bash
   base64 -i robin-signing.p12 | pbcopy   # now on your clipboard
   ```
4. GitHub → repo **Settings → Secrets and variables → Actions → New repository secret**:
   - `CSC_LINK` = paste the base64 blob
   - `CSC_KEY_PASSWORD` = the `.p12` password

electron-builder auto-detects the Team ID from this certificate; nothing else to set.

---

## Part B — the notarization key → `APPLE_API_KEY` + `APPLE_API_KEY_ID` + `APPLE_API_ISSUER`

Notarization submits the signed app to Apple's malware scan and "staples" the
result so it opens cleanly offline.

1. Go to **App Store Connect → Users and Access → Integrations → App Store Connect API**.
2. Under **Keys**, click **+** to generate a key. Name it `Robin Notary`, give it
   the **Developer** access role, and **Generate**.
3. **Download the `.p8` file** — you can only download it once. Keep it safe.
4. On that same page note:
   - the **Key ID** (e.g. `7K9ABC1234`) → `APPLE_API_KEY_ID`
   - the **Issuer ID** at the top (a UUID) → `APPLE_API_ISSUER`
5. Add the secrets:
   - `APPLE_API_KEY` = the **full contents** of the `.p8` file, including the
     `-----BEGIN PRIVATE KEY-----` / `-----END PRIVATE KEY-----` lines:
     ```bash
     pbcopy < AuthKey_7K9ABC1234.p8
     ```
   - `APPLE_API_KEY_ID` = the Key ID
   - `APPLE_API_ISSUER` = the Issuer ID

---

## Run it

```bash
git tag v1.0.0
git push origin v1.0.0
```

The `Release Robin` workflow builds on macOS, **signs** with your Developer ID,
**notarizes** with your API key, and publishes the signed `Robin-<version>-mac-<arch>.dmg`
(+ the `electron-updater` feed and SHA-256 checksums) to GitHub Releases.

**Verify a finished build** locally after downloading the `.dmg`:
```bash
spctl -a -vvv -t install /Applications/Robin.app   # expect: "accepted, source=Notarized Developer ID"
codesign -dvvv /Applications/Robin.app 2>&1 | grep TeamIdentifier
```

## Notes
- **Windows** is independent and optional — add `WIN_CSC_LINK` (base64 `.pfx`) and
  `WIN_CSC_KEY_PASSWORD` when you buy an Authenticode certificate. Until then the
  Windows build is unsigned.
- Certificates expire (Developer ID ~5 years; the API key does not). Re-export and
  update `CSC_LINK` when it does.
- These secrets live only in GitHub Actions; they are never written to the repo.
