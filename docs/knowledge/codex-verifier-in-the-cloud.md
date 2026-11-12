# Running the Codex verifier in the cloud, on subscriptions

The loop's verifier is of the other model family from the author, so for Claude-written PRs it is Codex. Today it runs on a host, and it is the last step of a thread that has no cloud route (#809, #365). This note answers: can a Codex verifier run on a cloud machine from OpenAI or Anthropic, paid by the ChatGPT and Claude subscriptions rather than API keys, and still run the project's app and Docker images?

Checked against codex-cli 0.167.1, Claude Code 2.1.322 and the vendor docs linked below. Nothing here has been proven by a run yet. The probes that would settle each open point are listed at the end.

## Short answer

- **Yes on paper, by three routes.** A Codex Cloud task, the Codex CLI inside an Anthropic cloud VM, or the Codex CLI on a machine we rent.
- **Recommended order: probe the Codex Cloud task first.** It is the only route where the ChatGPT login never leaves OpenAI, and OpenAI makes that login mandatory for it, so it is on the subscription by construction.
- **Fallback: the Codex CLI inside an Anthropic cloud VM.** It fits the loop better (model choice, later passes in one session, Docker documented), but it needs a copy of the ChatGPT login inside Anthropic's VM, which OpenAI documents only for trusted private runners.
- **Known-good baseline: a rented verifier-only machine.** It is OpenAI's documented pattern and needs no change to the loop. It costs a VM and is a machine we operate.
- **`@codex review` is not a verifier.** It reviews the diff and reports only P0/P1 issues. It doesn't run the gate, a mutation or the app.

## What the verifier needs from a runner

- The PR head checked out, with the project's toolchain.
- Commands that take minutes: the gate, a mutation run, the app brought up, sometimes a service in a container.
- A Markdown report in the shape `approvals.py verdict` parses, reachable by the lead. From a cloud VM that means a PR comment (orchestrating-agents, `--pr`).
- A later pass on the same PR that reviews only the delta, ideally in the same session, since a fresh pass costs about twice as much (#475).
- A chosen model and effort, so the `Verifier model:` line and the signature (#529) hold.

## Route 1: a Codex Cloud task

`codex cloud exec --env <id> --branch <branch> "<brief>"` submits a task to OpenAI's cloud and prints its URL. `codex cloud status <id>` exits non-zero until the task is ready, so it can be polled. `codex cloud diff <id>` prints the task's diff.

What holds:

- **Subscription only.** "Codex cloud requires signing in with ChatGPT", and the CLI refuses an API-key login for cloud commands. [auth](https://developers.openai.com/codex/auth.md), [cloud-tasks source](https://github.com/openai/codex/blob/main/codex-rs/cloud-tasks/src/lib.rs)
- **No VM charge.** "Standard Codex Cloud environments have no separate VM charge. Model usage counts toward your normal Codex usage limits." [plan limits](https://help.openai.com/en/articles/11369540-codex-and-chatgpt-plan-usage-limits)
- **VM size.** Plus: 2 vCPU, 8 GiB. Pro, Business, Enterprise: 4 vCPU, 16 GiB RAM, 32 GiB disk. [cloud environments](https://developers.openai.com/codex/environments/cloud-environments.md)
- **A GitHub token without exposing it.** A network secret is swapped in by the proxy for an allowed HTTPS host, so the task can call `api.github.com` and never read the token. `api.github.com` has to be added to the allowed domains by name. [cloud environments](https://developers.openai.com/codex/environments/cloud-environments.md)

What stands in the way:

- **The report doesn't come back through the CLI.** The CLI prints only the diff. The client code can read the task's messages, but no subcommand exposes that. So the verifier either writes its report to a file (it arrives in `codex cloud diff`) or posts the PR comment itself with the network secret. [cloud-tasks client](https://github.com/openai/codex/blob/main/codex-rs/cloud-tasks-client/src/http.rs)
- **No model or effort flag.** `exec` takes the prompt, `--env`, `--branch` and `--attempts`. Which model a task runs on, and whether it can be set, is not documented. [cli source](https://github.com/openai/codex/blob/main/codex-rs/cloud-tasks/src/cli.rs)
- **No follow-up turn from the CLI.** A later pass is a new task in a new VM, so the cheaper same-session delta pass is lost. `CODEX_STARTING_DIFF` can pre-apply a patch, which doesn't replace a conversation.
- **It may cost more quota.** "Cloud tasks may use more of your allowance than local messages", and both share one allowance. The verifier already uses most of the weekly quota (#475). [pricing](https://developers.openai.com/codex/pricing.md)
- **Environments are made in the web UI only.** No API creates or edits one. The CLI only lists them. The older setup-script environments are marked legacy and due to be deprecated. [cloud environments](https://developers.openai.com/codex/environments/cloud-environments.md), [legacy](https://developers.openai.com/codex/cloud/environments.md)
- **Docker is implied, not stated.** The docs list Docker image pulls and pushes from ECR and Artifact Registry as supported inside the VM. No page says a Docker daemon runs there, and the legacy `codex-universal` image has none. [codex-universal](https://github.com/openai/codex-universal/blob/main/Dockerfile)
- **`codex cloud` is experimental and its HTTP API is undocumented**, so a bridge built on it can break without notice.
- **A bridge is needed.** Omnigent has no agent that submits a Codex Cloud task, polls it and fetches the result. It is small: three CLI calls and the `--pr` report channel that cloud workers already use.

The Codex desktop app has a Cloud mode, but only through its UI. Its deep links open local chats only, so it gives no programmatic route. [commands](https://developers.openai.com/codex/reference/commands.md)

## Route 2: the Codex CLI inside an Anthropic cloud VM

A Claude cloud session is started as today (the `claude-cloud` agent). Its environment installs `@openai/codex`, holds a ChatGPT login, and allows OpenAI's hosts. The Claude session only carries the work: it runs `codex exec` with the verifier brief and posts the report file.

What holds:

- **The app and Docker images run.** The VM is Ubuntu 24.04, about 4 vCPU, 16 GB RAM and 30 GB disk, with docker, dockerd, compose, PostgreSQL, Redis and Chrome preinstalled. Pulled images are kept in the environment cache. The base image can't be replaced; a setup script or a container next to the session is the way to customise it. [cloud environments](https://code.claude.com/docs/en/cloud-environments)
- **On the Claude subscription.** "Each session counts toward your plan's usage limits ... there's no separate charge for the cloud VM." [web quickstart](https://code.claude.com/docs/en/web-quickstart)
- **OpenAI's hosts can be allowed.** The allowlist takes any domain, or the environment can have full access. [access levels](https://code.claude.com/docs/en/cloud-environments#access-levels)
- **OpenAI documents a copied login.** `codex login` on a trusted machine, then the `auth.json` on the runner, for "users who need ChatGPT/Codex rate limits instead of API key usage". [CI/CD auth](https://developers.openai.com/codex/auth/ci-cd-auth.md), [non-interactive](https://developers.openai.com/codex/noninteractive.md)
- **The loop's pieces exist.** The bridge, the scriptable environment, and the `--pr` report channel are in use for cloud workers. Model, effort and a resumed later pass work as on a host, since it is the same CLI.

What stands in the way:

- **The login is a password in someone else's VM.** OpenAI: "an advanced workflow for enterprise and other trusted private automation", "Do not use this workflow for public or open-source repositories". The PR's own test code runs in the same VM as the token. An environment variable is also readable by everyone who can use that environment. Anthropic's network secrets keep a key out of the VM by adding the `Authorization` header at the proxy, but Codex reads its tokens from `auth.json` and rotates them, so whether a placeholder file plus a network secret works is an open question a probe would settle. [environment variables](https://code.claude.com/docs/en/cloud-environments#set-environment-variables)
- **The token must be kept fresh, one copy per runner.** Codex refreshes it after about 8 days and writes the new one back to `auth.json`. A cloud VM is fresh every session and can't write back, so the stored copy goes stale, and several verifiers at once share one copy, which OpenAI says not to do. A weekly reseed from a host covers it, and that is a host step again.
- **A Claude session carries a Codex verdict.** It spends Claude quota while it waits, and the report passes through the author's family. The carrier's brief has to be "run this command, post this file, change nothing", and the report file posted byte for byte.
- **A browser login can't run in the VM**, so `codex login` there is out. Only the copied file works. [cloud environments](https://code.claude.com/docs/en/cloud-environments#what-carries-over-from-your-setup)
- **Unproven: Codex's streaming through Anthropic's proxy.** All traffic passes a proxy that terminates TLS. The docs name only Bun as broken and say nothing about long streaming responses or WebSockets.
- **Neither vendor's terms cover it.** Anthropic's say nothing about another vendor's CLI in a cloud session. OpenAI's consumer terms forbid making the account available to anyone else. [Anthropic AUP](https://www.anthropic.com/legal/aup), [OpenAI terms](https://openai.com/policies/terms-of-use/)

## Route 3: a rented verifier-only machine

A small Linux VM, or a container on any always-on box, runs an Omnigent host with codex-native and its own `codex login --device-auth`.

- **It is OpenAI's recommended shape** for subscription auth in automation: a persistent trusted runner that keeps its refreshed `auth.json`. [CI/CD auth](https://developers.openai.com/codex/auth/ci-cd-auth.md)
- **Nothing in the loop changes.** Follow-ups, model choice, the signature and Docker work as on today's hosts, and verifiers stop competing with builds on the owner's machines (#806).
- **It costs a VM and someone has to keep it running.** It is not from OpenAI's or Anthropic's cloud.

Anthropic's self-hosted environments (public beta on Team and Enterprise) are a variant of this: `claude self-hosted-runner` on our machine takes cloud sessions, with our image, our network and our GitHub credentials. The session is still Claude, so for a Codex verifier it only adds a carrier on top of a machine that can run Codex directly. It may matter for other rows of #809, since such a session is not behind Anthropic's GitHub proxy. [self-hosted environments](https://code.claude.com/docs/en/self-hosted-environments)

## Not a route: `@codex review`

- A PR comment `@codex review` starts a cloud review on the subscription and posts a GitHub review. It follows `## Code Review Rules` in `AGENTS.md`. [GitHub integration](https://developers.openai.com/codex/integrations/github.md)
- It flags only P0/P1 issues and needs no environment, so it reads the diff. No doc says it runs tests.
- It can't write the loop's report or run a mutation, so it can't replace the verifier. It could be a cheap second opinion on low-risk PRs.

## Comparison

| | Codex Cloud task | Codex CLI in Anthropic VM | Rented machine |
|---|---|---|---|
| Paid by | ChatGPT plan | ChatGPT plan, plus Claude plan for the carrier | ChatGPT plan, plus the VM |
| ChatGPT login leaves our hands | No | Yes, into Anthropic's VM | No |
| Docker and the app | Implied, unproven | Documented | Yes |
| Model and effort chosen | Unknown | Yes | Yes |
| Later pass in the same session | No | Yes, if the session is kept | Yes |
| Report channel | File in the diff, or its own PR comment | PR comment by the carrier | Host file, as today |
| New code | A small Omnigent bridge | An environment and a carrier brief | None |
| Host step left | None | Weekly token reseed | The machine itself |

## Probes that settle it

Route 1, one task on a throwaway PR:

1. Does the report come back, as a file in `codex cloud diff` and as a PR comment through a network secret?
2. Does `docker run hello-world` work in the task VM?
3. Which model and effort ran, and can either be set (environment setting, `-c` override, prompt)?
4. How many percentage points of the weekly quota does one verifier pass cost, next to the 2.07 pp of a local first pass (#475)?
5. How long from submit to ready, including the clone and install?

Route 2, one cloud session, only if route 1 fails a probe:

1. Does `codex exec` stream a full turn through the proxy with OpenAI's hosts allowed?
2. Does Codex's own sandbox start inside the VM, or does it need `--sandbox danger-full-access`?
3. How much Claude quota does the carrier spend on a 20-minute verifier pass?

Both need the owner first: route 1 needs an environment made in the Codex web UI and a GitHub token added as a network secret, and route 2 puts a ChatGPT login into an Anthropic environment.
