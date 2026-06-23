import { useStore } from '@nanostores/react'
import { useEffect, useMemo, useState } from 'react'

import {
  FEATURED_ID,
  FeaturedProviderRow,
  KeyProviderRow,
  ProviderRow,
  sortProviders
} from '@/components/desktop-onboarding-overlay'
import { Button } from '@/components/ui/button'
import { listOAuthProviders } from '@/hermes'
import { ChevronDown, KeyRound } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { $desktopOnboarding, startManualProviderOAuth } from '@/store/onboarding'
import type { EnvVarInfo, OAuthProvider } from '@/types/hermes'

import { ProviderKeyRows } from './credential-key-ui'
import { SettingsCategoryHeading, useEnvCredentials } from './env-credentials'
import { providerMeta } from './helpers'
import { LoadingState, SettingsContent } from './primitives'

// Sub-views surfaced as a sidebar subnav: account sign-in vs raw API keys.
export const PROVIDER_VIEWS = ['accounts', 'keys'] as const

export type ProviderView = (typeof PROVIDER_VIEWS)[number]

// Robin (by EnergyIR) surfaces exactly ONE provider credential: the EnergyIR
// API key (stored as TOGETHER_API_KEY). We ALWAYS render its row — so users can
// see whether they're connected, get a key, or remove it — without gating on
// the backend env-catalog `category` (gating there made the row disappear).
// Every other provider key stays hidden (white-label).
function buildProviderKeyGroups(vars: Record<string, EnvVarInfo>): ProviderKeyGroup[] {
  const info: EnvVarInfo = vars['TOGETHER_API_KEY'] ?? {
    advanced: false,
    category: 'provider',
    description: '',
    is_password: true,
    is_set: false,
    redacted_value: null,
    tools: [],
    url: null
  }

  const meta = providerMeta('EnergyIR')

  return [
    {
      advanced: [],
      // Description + docs link drive the expandable "Your EnergyIR API key
      // powers Robin" + "Get a key" affordances.
      description: meta?.description ?? info.description,
      docsUrl: meta?.docsUrl ?? info.url ?? undefined,
      hasAnySet: Boolean(info.is_set),
      name: 'EnergyIR',
      primary: ['TOGETHER_API_KEY', info],
      priority: 0
    }
  ]
}

// Deliberately a near-1:1 replica of the first-run onboarding picker
// (`Picker` in desktop-onboarding-overlay): same recommended card, same
// provider rows, same "Other providers" disclosure, same OpenRouter quick-key
// row, and the same bottom-right "I have an API key" affordance. The leaf cards
// are the exact shared components, so the two surfaces stay visually identical.
// Selecting a provider hands off to the shared onboarding overlay, which runs
// that provider's real sign-in flow; the key affordances open the API-key
// catalog below.
function OAuthPicker({ onWantApiKey, providers }: { onWantApiKey: () => void; providers: OAuthProvider[] }) {
  const [showAll, setShowAll] = useState(false)
  const ordered = useMemo(() => sortProviders(providers), [providers])

  if (ordered.length === 0) {
    return null
  }

  const select = (p: OAuthProvider) => startManualProviderOAuth(p.id)

  const featured = ordered.find(p => p.id === FEATURED_ID) ?? null
  const rest = featured ? ordered.filter(p => p.id !== FEATURED_ID) : ordered
  // Keep connected accounts grouped and always visible; only the unconnected
  // providers hide behind the disclosure, so the page leads with what's set up.
  const connected = rest.filter(p => p.status?.logged_in)
  const others = rest.filter(p => !p.status?.logged_in)
  const collapsible = others.length > 0
  const showOthers = !collapsible || showAll

  return (
    <section className="mb-5 grid gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <SettingsCategoryHeading icon={KeyRound} title="Connect an account" />
        <Button
          className="h-auto px-0 py-0 text-[length:var(--conversation-caption-font-size)]"
          onClick={onWantApiKey}
          type="button"
          variant="textStrong"
        >
          Have an API key instead?
        </Button>
      </div>
      <p className="-mt-2 mb-1 text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
        Sign in with a subscription — no API key to copy. Robin runs the browser sign-in for you, right here in the
        app.
      </p>
      {featured && <FeaturedProviderRow onSelect={select} provider={featured} />}
      {connected.length > 0 && (
        <>
          <p className="mt-1 px-0.5 text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-tertiary)">
            Connected
          </p>
          {connected.map(p => (
            <ProviderRow key={p.id} onSelect={select} provider={p} />
          ))}
        </>
      )}
      {showOthers && (
        <>
          {others.map(p => (
            <ProviderRow key={p.id} onSelect={select} provider={p} />
          ))}
          <KeyProviderRow onClick={onWantApiKey} />
        </>
      )}
      {collapsible && (
        <Button
          className="h-auto px-0 py-1 text-[length:var(--conversation-caption-font-size)]"
          onClick={() => setShowAll(v => !v)}
          type="button"
          variant="text"
        >
          {showAll ? 'Collapse' : connected.length > 0 ? 'Connect another provider' : 'Other providers'}
          <ChevronDown className={cn('size-3.5 transition', showAll && 'rotate-180')} />
        </Button>
      )}
    </section>
  )
}

function NoProviderKeys() {
  return (
    <div className="grid min-h-32 place-items-center px-4 py-8 text-center text-[length:var(--conversation-caption-font-size)] text-muted-foreground">
      No provider API keys available.
    </div>
  )
}

export function ProvidersSettings({ onViewChange, view }: ProvidersSettingsProps) {
  const { rowProps, vars } = useEnvCredentials()
  const [oauthProviders, setOauthProviders] = useState<OAuthProvider[]>([])
  const [openProvider, setOpenProvider] = useState<null | string>(null)
  // The onboarding overlay owns the OAuth flow. Watch its `manual` flag so we
  // re-read connection state when the user finishes (or dismisses) a sign-in
  // they launched from this page — otherwise the cards keep their stale status.
  const onboardingActive = useStore($desktopOnboarding).manual

  useEffect(() => {
    if (onboardingActive) {
      return
    }

    let cancelled = false

    // OAuth providers are best-effort — a failure here just hides the panel.
    void (async () => {
      try {
        const { providers } = await listOAuthProviders()

        if (!cancelled) {
          setOauthProviders(providers)
        }
      } catch {
        // Ignore — the OAuth panel just won't render.
      }
    })()

    return () => void (cancelled = true)
  }, [onboardingActive])

  if (!vars) {
    return <LoadingState label="Loading providers..." />
  }

  // White-label: Robin only ever offers the EnergyIR API key. The third-party
  // OAuth account picker (OpenAI/Anthropic/xAI sign-in) is never shown, even if
  // something deep-links to the old `accounts` sub-view. Always render keys.
  const showApiKeys = true

  const keyGroups = buildProviderKeyGroups(vars)

  if (showApiKeys) {
    return (
      <SettingsContent>
        {keyGroups.length > 0 ? (
          <div className="grid gap-2">
            {keyGroups.map(group => (
              <ProviderKeyRows
                expanded={openProvider === group.name}
                group={group}
                key={group.name}
                onExpand={() => setOpenProvider(group.name)}
                onToggle={() => setOpenProvider(prev => (prev === group.name ? null : group.name))}
                rowProps={rowProps}
              />
            ))}
          </div>
        ) : (
          <NoProviderKeys />
        )}
      </SettingsContent>
    )
  }

  return (
    <SettingsContent>
      <OAuthPicker onWantApiKey={() => onViewChange('keys')} providers={oauthProviders} />
    </SettingsContent>
  )
}

interface ProviderKeyGroup {
  advanced: [string, EnvVarInfo][]
  description?: string
  docsUrl?: string
  hasAnySet: boolean
  name: string
  primary: [string, EnvVarInfo]
  priority: number
}

interface ProvidersSettingsProps {
  onViewChange: (view: ProviderView) => void
  view: ProviderView
}
