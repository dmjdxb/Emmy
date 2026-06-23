# Robin — Privacy & Data Handling

_Last updated: 2026-06-16 · Publisher: EnergyIR_

Robin is a desktop agent that runs on your machine. This document describes,
plainly, where your data goes.

## Where your data goes

- **Your files and folders stay on your machine.** Robin's file and shell tools
  run locally and are confined to the folders you explicitly grant.
- **Model inference goes to Together AI (United States).** To answer you, Robin
  sends the conversation — and any file or command context the agent decides is
  relevant — to the **Together AI** API (`https://api.together.xyz`), an
  OpenAI-compatible cloud inference provider, which runs **DeepSeek V4 Pro**.
  This content is processed on Together AI's infrastructure under
  [Together AI's terms and data-use policy](https://www.together.ai/legal/privacy-policy).
  Review those terms; they govern retention on the inference provider's side.
- Because Robin uses **Together AI**, request content is **not** sent to
  DeepSeek's own (China-operated) API infrastructure.
- **No EnergyIR servers are in the path.** Robin does not proxy your requests
  through EnergyIR. Your Together AI API key is yours (BYO key); EnergyIR never
  receives or stores it.

## Secrets

Your Together AI API key and any other tokens are stored in your operating
system's keychain (macOS Keychain, Windows Credential Manager, Linux libsecret).
They are never written in plaintext to a config file or to any folder Robin can
read as a workspace.

## Memory

- **Session memory is on by default** so Robin remembers within a conversation.
- **Cross-session user-profiling is off by default.** You can enable it; it is
  disclosed at onboarding. Memory is stored locally under `~/.robin`.

## Telemetry

Telemetry is **off by default** and opt-in.

## Sensitive content

Robin surfaces a data-handling disclosure at onboarding and a sensitivity
warning before sending flagged content. Do **not** use Robin for clinical or
otherwise regulated workloads without your own separate legal and security
review; the default configuration is not certified for such use.

## Your controls

- **Stop** halts the agent immediately.
- **Panic / revoke** withdraws folder grants.
- The **audit log** is an exportable record of every tool action and approval.
