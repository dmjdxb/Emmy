import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Tip } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { triggerHaptic } from '@/lib/haptics'
import { Zap } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { setEffort } from '@/store/session'

import { GHOST_ICON_BTN } from './controls'
import type { ChatBarState } from './types'

/**
 * Composer effort selector — a Claude-style ladder that sets how hard Robin
 * thinks for the current conversation. Each tier maps (in the backend) to a
 * primary chat model; tool calls / auxiliary tasks are unaffected. The selected
 * tier id is written to the `$effort` store and sent on the next prompt.submit.
 */
export function EffortSelector({ state, disabled }: { state: ChatBarState['effort']; disabled: boolean }) {
  const { t } = useI18n()
  const c = t.composer

  const tiers = state.tiers

  if (!state.canSwitch || tiers.length === 0) {
    return null
  }

  const current = tiers.find(tier => tier.id === state.current) ?? tiers[0]

  return (
    <DropdownMenu>
      <Tip label={c.effortLabel}>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={c.effortLabel}
            className={cn(
              GHOST_ICON_BTN,
              'flex w-auto items-center gap-1 px-1.5 text-xs',
              'data-[state=open]:bg-(--chrome-action-hover) data-[state=open]:text-foreground'
            )}
            disabled={disabled}
            size="icon"
            type="button"
            variant="ghost"
          >
            <Zap size={14} />
            <span className="max-w-24 truncate font-medium">{current.label}</span>
            <Codicon name="chevron-down" size="0.75rem" />
          </Button>
        </DropdownMenuTrigger>
      </Tip>
      <DropdownMenuContent align="end" className="w-72" side="top" sideOffset={10}>
        <DropdownMenuLabel className="text-[0.7rem] font-medium uppercase tracking-wide text-muted-foreground/85">
          {c.effortTitle}
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          onValueChange={value => {
            triggerHaptic('selection')
            setEffort(value)
          }}
          value={current.id}
        >
          {tiers.map(tier => (
            <DropdownMenuRadioItem className="items-start py-1.5" key={tier.id} value={tier.id}>
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">{tier.label}</span>
                {tier.blurb ? <span className="text-[0.7rem] text-muted-foreground">{tier.blurb}</span> : null}
              </div>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <p className="px-2 py-1 text-[0.7rem] leading-snug text-muted-foreground/80">{c.effortHint}</p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
