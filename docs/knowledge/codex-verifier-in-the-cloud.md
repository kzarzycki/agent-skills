# Running the Codex verifier in the cloud, on subscriptions

The loop's verifier is of the other model family from the author, so for Claude-written PRs it is Codex. Today it runs on a host, and it is the last step of a thread that has no cloud route (#809, #365). This note answers: can a Codex verifier run on a cloud machine from OpenAI or Anthropic, paid by the ChatGPT and Claude subscriptions rather than API keys, and still run the project's app and Docker images?

Checked against codex-cli 0.167.1, Claude Code 2.1.322 and the vendor docs linked below. Routes 1 and 2 were then probed by runs; what the runs showed is under Spike results and overrides the docs where they differ. The last run was a real verifier pass by the Codex CLI inside an Anthropic VM, after a device login the owner approved.

## Short answer

- **Lead candidate: the Codex CLI inside an Anthropic cloud VM.** The spike showed Docker and a Postgres image running there, Codex's sandbox starting, OpenAI's hosts reachable with streaming and WebSockets intact, and `codex login --device-auth` starting inside the VM. A real verifier pass then ran there on the host verifier's model: 91 s for the first pass with a test slice and a Postgres container, 13 s for a resumed second pass. What is left is how an unattended verifier gets its login, since a device login needs the owner at a browser and dies with the VM.
- **A Codex Cloud task works, but as a weaker verifier.** It is on the subscription by construction and the report comes back. The spike also showed that containers can't run in it, that it ran on an older model than the host verifier with no way found to change it, and that each pass gets a fresh container. It fits a review plus tests that need no container.
- **Documented baseline: a rented verifier-only machine.** It is OpenAI's documented pattern and needs no change to the loop. It costs a VM and is a machine we operate. Not probed.
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

- **The report doesn't come back through the CLI.** The CLI prints only the diff. The client code can read the task's messages, but no subcommand exposes that. A report written to an untracked file does not arrive in `codex cloud diff` either (Spike results). So the report is read from the task's record over HTTP, or the verifier posts the PR comment itself with the network secret. [cloud-tasks client](https://github.com/openai/codex/blob/main/codex-rs/cloud-tasks-client/src/http.rs)
- **No model or effort flag.** `exec` takes the prompt, `--env`, `--branch` and `--attempts`. Which model a task runs on, and whether it can be set, is not documented. [cli source](https://github.com/openai/codex/blob/main/codex-rs/cloud-tasks/src/cli.rs)
- **No follow-up turn from the CLI.** The backend takes one (Spike results), and it keeps the conversation but not the machine. `CODEX_STARTING_DIFF` can pre-apply a patch, which doesn't replace a conversation.
- **It may cost more quota.** "Cloud tasks may use more of your allowance than local messages", and both share one allowance. The verifier already uses most of the weekly quota (#475). [pricing](https://developers.openai.com/codex/pricing.md)
- **Environments are made in the web UI, per the docs.** The spike created and edited one through the backend the CLI uses, which is undocumented. The older setup-script environments, the kind that call creates, are marked legacy and due to be deprecated. [cloud environments](https://developers.openai.com/codex/environments/cloud-environments.md), [legacy](https://developers.openai.com/codex/cloud/environments.md)
- **No containers in the environment the spike could create.** Docker's daemon and rootless Podman both failed there (Spike results). The docs list Docker image pulls from ECR and Artifact Registry as supported in the newer VM-based environments, which the spike could not create. [codex-universal](https://github.com/openai/codex-universal/blob/main/Dockerfile)
- **`codex cloud` is experimental and its HTTP API is undocumented**, so a bridge built on it can break without notice.
- **A bridge is needed.** Omnigent has no agent that submits a Codex Cloud task, polls it and fetches the result. It is small: three CLI calls and the `--pr` report channel that cloud workers already use.

The Codex desktop app has a Cloud mode, but only through its UI. Its deep links open local chats only, so it gives no programmatic route. [commands](https://developers.openai.com/codex/reference/commands.md)

## Route 2: the Codex CLI inside an Anthropic cloud VM

A Claude cloud session is started as today (the `claude-cloud` agent). Its environment installs `@openai/codex`, holds a ChatGPT login, and allows OpenAI's hosts. The Claude session only carries the work: it runs `codex exec` with the verifier brief and posts the report file.

What holds:

- **The app and Docker images run (documented, and confirmed by the spike).** The VM is Ubuntu 24.04, about 4 vCPU, 16 GB RAM and 30 GB disk, with docker, dockerd, compose, PostgreSQL, Redis and Chrome preinstalled. Pulled images are kept in the environment cache. The base image can't be replaced; a setup script or a container next to the session is the way to customise it. [cloud environments](https://code.claude.com/docs/en/cloud-environments)
- **On the Claude subscription.** "Each session counts toward your plan's usage limits ... there's no separate charge for the cloud VM." [web quickstart](https://code.claude.com/docs/en/web-quickstart)
- **OpenAI's hosts can be allowed.** The allowlist takes any domain, or the environment can have full access. [access levels](https://code.claude.com/docs/en/cloud-environments#access-levels)
- **OpenAI documents a copied login.** `codex login` on a trusted machine, then the `auth.json` on the runner, for "users who need ChatGPT/Codex rate limits instead of API key usage". [CI/CD auth](https://developers.openai.com/codex/auth/ci-cd-auth.md), [non-interactive](https://developers.openai.com/codex/noninteractive.md)
- **The loop's pieces exist.** The bridge, the scriptable environment, and the `--pr` report channel are in use for cloud workers. Model, effort and a resumed later pass work as on a host, since it is the same CLI.

What stands in the way:

- **The login is a password in someone else's VM.** OpenAI: "an advanced workflow for enterprise and other trusted private automation", "Do not use this workflow for public or open-source repositories". The PR's own test code runs in the same VM as the token. An environment variable is also readable by everyone who can use that environment. Anthropic's network secrets keep a key out of the VM by adding the `Authorization` header at the proxy, but Codex reads its tokens from `auth.json` and rotates them, so whether a placeholder file plus a network secret works is an open question a probe would settle. [environment variables](https://code.claude.com/docs/en/cloud-environments#set-environment-variables)
- **The token must be kept fresh, one copy per runner.** Codex refreshes it after about 8 days, or earlier when a request gets a 401, and writes the new one back to `auth.json`. OpenAI's pattern for a short-lived runner is restore, run, then store the refreshed file. A cloud VM is fresh every session and has no way to write back to the environment's settings, so the stored copy goes stale, and a session that refreshes and then throws the new token away may leave the stored copy invalid. Several verifiers at once also share one copy, which OpenAI says not to do. Reseeding from a host about weekly is the obvious cover; it is a host step again, and whether it holds when a refresh comes early is unproven.
- **A Claude session carries a Codex verdict.** It spends Claude quota while it waits, and the report passes through the author's family. The carrier's brief has to be "run this command, post this file, change nothing", and the report file posted byte for byte.
- **A browser login can't run in the VM, a device login can.** The docs rule out a login that needs a browser in the session. `codex login --device-auth` only needs the owner to approve a code elsewhere, and the spike showed it starting. That login lasts as long as the VM. [cloud environments](https://code.claude.com/docs/en/cloud-environments#what-carries-over-from-your-setup)
- **Neither vendor's terms name this case.** Anthropic's say nothing about another vendor's CLI in a cloud session. OpenAI's consumer terms forbid making the account available to anyone else, and don't say whether a login in a VM that only its owner uses counts. [Anthropic AUP](https://www.anthropic.com/legal/aup), [OpenAI terms](https://openai.com/policies/terms-of-use/)

## Route 3: a rented verifier-only machine

A small Linux VM, or a container on any always-on box, runs an Omnigent host with codex-native and its own `codex login --device-auth`.

- **It is OpenAI's recommended shape** for subscription auth in automation: a persistent trusted runner that keeps its refreshed `auth.json`. [CI/CD auth](https://developers.openai.com/codex/auth/ci-cd-auth.md)
- **Nothing in the loop changes.** Follow-ups, model choice, the signature and Docker work as on today's hosts, and verifiers stop competing with builds on the owner's machines (#806).
- **It costs a VM and someone has to keep it running.** It is not from OpenAI's or Anthropic's cloud.

Anthropic's self-hosted environments (public beta on Team and Enterprise) are a variant of this: `claude self-hosted-runner` on our machine takes cloud sessions, with our image, our network and our GitHub credentials. The session is still Claude, so for a Codex verifier it only adds a carrier on top of a machine that can run Codex directly. It may matter for other rows of #809, since such a session is not behind Anthropic's GitHub proxy. [self-hosted environments](https://code.claude.com/docs/en/self-hosted-environments)

- **The image is ours to build.** Anthropic publishes no runner image; the docs give a minimal Dockerfile around the `claude` binary. [deploy](https://code.claude.com/docs/en/self-hosted-environments-deploy#build-the-runner-image)
- **Every member of the organisation can dispatch to it.** "Treat every runner host as reachable for code execution by everyone who can dispatch to it", so a ChatGPT login stored on that host is readable by all of them. [deploy](https://code.claude.com/docs/en/self-hosted-environments-deploy#harden-your-deployment)
- **Dispatch is scriptable.** `claude -p "<prompt>" --environment <id> --output-format json` creates the session and prints its id. [testing](https://code.claude.com/docs/en/self-hosted-environments-testing#run-the-test-loop)

## Not a route: `@codex review`

- A PR comment `@codex review` starts a cloud review on the subscription and posts a GitHub review. It follows `## Code Review Rules` in `AGENTS.md`. [GitHub integration](https://developers.openai.com/codex/integrations/github.md)
- It flags only P0/P1 issues and needs no environment, so it reads the diff. No doc says it runs tests.
- It can't write the loop's report or run a mutation, so it can't replace the verifier. It could be a cheap second opinion on low-risk PRs.

## Not a route: `claude ultrareview`

- It is a cloud review by a fleet of Claude agents, so it is the author's family for a Claude-written PR.
- It bills usage credits, not the plan: "typically $5 to $25" per review after three free runs. It takes no brief. [ultrareview](https://code.claude.com/docs/en/ultrareview)

## Comparison

| | Codex Cloud task | Codex CLI in Anthropic VM | Rented machine |
|---|---|---|---|
| Paid by | ChatGPT plan | ChatGPT plan, plus Claude plan for the carrier | ChatGPT plan, plus the VM |
| ChatGPT login leaves our hands | No | Yes, into Anthropic's VM | No |
| Docker and the app | No (spike) | Yes (spike) | Yes |
| Model and effort chosen | No way found (spike) | Yes, same CLI as a host (spike) | Yes |
| Later pass keeps the conversation | Yes (spike) | Yes, if the session is kept (spike) | Yes |
| Later pass keeps the files | No, fresh container (spike) | Yes, if the session is kept (spike) | Yes |
| Report channel | The task's record over HTTP (spike) | PR comment by the carrier (spike) | Host file, as today |
| New code | A small Omnigent bridge on an undocumented API | An environment and a carrier brief | None |
| Host step left | None | Keeping the login fresh | The machine itself |

## Spike results

Raw reports are in the comments of the PR that added this note.

### Codex Cloud task

One task with two follow-up turns, in an environment for this repo, on the branch of this note.

- **The backend the CLI talks to does more than the CLI.** `POST /wham/environments` created the environment and `PATCH` edited it, though the docs say environments are made in the UI. `POST /wham/tasks` with `follow_up: {task_id, turn_id}` adds a turn to a task. `GET /wham/tasks/<id>` returns the final message. `GET /wham/usage` returns the weekly quota in whole percent. All of it is undocumented.
- **The report comes back.** The final message, 8 to 11 thousand characters of Markdown ending in the `VERDICT:` lines, was read from the task's record. `codex cloud diff` said "no diff", since the report file was untracked.
- **Timing.** First turn ready in 278 s, including the clone and container start. Follow-ups in 139 s and 109 s.
- **Machine.** 3 CPUs, 17 GB RAM, 32 GB disk, root, Ubuntu 24.04, with git, uv, node, python and jq. `gh` works after `mise trust` and has no login.
- **Containers: no.** `apt-get install docker.io` works, then `dockerd` fails on `iptables ... Permission denied`. Rootless Podman pulls the image, then fails on `mount proc: Operation not permitted`. The environment's `enable_docker_in_docker` field stayed false when set to true.
- **A follow-up keeps the conversation, not the machine.** The second turn knew the first, and ran in a new container: the first turn's files and installed packages were gone. A setup script would have to reinstall what a pass needs.
- **Model: GPT-5.6 Sol, effort not shown.** The host verifier runs a newer model. Model and effort fields added to the request were ignored. The backend lists ten models, so a choice may exist in the UI.
- **The checkout has no remote.** `git fetch origin main` fails. `git fetch https://github.com/<owner>/<repo>.git main` works for a public repo, and the diff against it was reviewable. A private repo would need a token.
- **Network.** `api.github.com` and `pypi.org` answer with the "common dependencies" preset. Other hosts are refused.
- **The review was real.** Asked for defects in this note, it found three, all fair, and they are fixed here.
- **Quota.** The weekly figure stayed at 70% across the three turns and a tiny fourth task. They were light, so this gives no per-pass cost for a real verifier pass.
- **Not tested:** posting a PR comment with a network secret, the newer VM-based environments, and `codex cloud exec` itself, since the tasks were submitted over HTTP.

### Codex CLI in an Anthropic cloud VM

One cloud session in an environment that allows `chatgpt.com`, `auth.openai.com` and `api.openai.com`, installs `@openai/codex` in its setup script, and holds no secret.

- **Docker: yes.** The daemon is not running at session start. A bare `dockerd` as root came up in 2 s. `hello-world` ran in 2.1 s and `postgres:16-alpine` in 8.1 s with its pull. Network from inside a container was not tested.
- **Codex installs and its sandbox starts.** `codex-cli 0.167.2`. `codex sandbox -- git status -sb` exits 0, and writes to `/etc` and the working directory are refused under the default sandbox.
- **OpenAI's hosts answer.** `chatgpt.com/backend-api/codex/responses` and `api.openai.com/v1/models` return OpenAI's own 401 for a request with no login, and `auth.openai.com` returns 200. No request was denied on the way.
- **TLS to `chatgpt.com` is tunnelled through the proxy, not re-signed.** curl sees a public certificate authority's certificate. A client that ignores `HTTPS_PROXY` still gets out, through a gateway that does re-sign, so a client that pins certificates would fail on that path only.
- **Streaming and WebSockets pass.** Server-sent events arrived one per second for 24 s, not at once at the end. A WebSocket upgrade returned `101 Switching Protocols` through the proxy and echoed a message.
- **A device login starts inside the VM.** `codex login --device-auth` printed its verification URL and a code and waited. So the VM can get its own login, approved in the owner's browser, with no file copied from a host. It lasts as long as that VM.
- **Machine.** 4 CPUs, 15 GB RAM, 30 GB free disk.
- **Not tested:** the Claude quota the carrier spends, and how the login is kept across sessions.

### A real verifier pass in the Anthropic cloud VM

One kept cloud session in the same environment. The carrier started `codex login --device-auth` detached, the owner approved the code in a browser, and the carrier then ran two Codex passes and logged out.

- **The device login works end to end.** `codex login status` said `Logged in using ChatGPT` once the code was approved. The code reached the owner through the session's message, not a PR comment, since the PR is public.
- **Pass 1: 91 s.** `codex exec -m gpt-6.1-sol -c model_reasoning_effort=medium --dangerously-bypass-approvals-and-sandbox --json -o <file> "<brief>"` exited 0. The VM is the sandbox here, so Codex's own was off, which is what lets it reach Docker.
- **Codex did a verifier's work.** It fetched `main` and diffed the branch, ran the two-file test slice (57 passed), started `postgres:16-alpine` with a published port, waited for `pg_isready` and queried it, and checked two of this note's claims against `codex --help`. 15 commands, 14 of them exit 0.
- **The review was real.** It found one major and one minor defect in this note, both fair, and they are fixed here. The report ended in the three lines `approvals.py verdict` parses.
- **Pass 2: 13 s.** `codex exec resume --last` continued the same conversation, restated both findings, and saw the Postgres container from pass 1 still running. So a later pass keeps both the conversation and the machine while the session is kept.
- **Model and effort are set as on a host.** The session file Codex keeps records `gpt-6.1-sol` and `medium` for pass 1. The `--json` stream carries no model field, and the verifier itself could only say "GPT-6 family", so the signature has to come from the command line or the session file. The resume command carried no effort override, so pass 2 ran at the default: a resumed pass must repeat it.
- **Tokens.** Pass 1: 337 thousand input (286 thousand cached), 2.5 thousand output. Pass 2 added about 134 thousand input (77 thousand cached) and 0.2 thousand output; the counts `resume` reports are for the whole thread.
- **Quota.** The account's weekly Codex figure went from 72% to 73% across both passes. It is in whole percent and the account was not otherwise idle, so read it as "about a point or less".
- **Logout works.** `codex logout` removed `auth.json` and `codex login status` then said `Not logged in`, so no login stayed in the VM.
- **Session time.** About 13 minutes from start to report, 5 of them waiting for the owner's approval.
- **Not measured:** the Claude quota the carrier spent, and a pass on a PR with a full gate.

## Still open

1. **Keeping the login.** A device login needs the owner at a browser and dies with the VM. For unattended verifiers the environment has to hold an `auth.json` of its own (not the host's copy, since one copy must not be used from two machines), kept fresh from outside. That puts a ChatGPT login into an environment's settings, which is the owner's decision.
2. **The carrier's cost.** How much Claude quota a carrier session spends on a full verifier pass was not measured.
3. **Codex Cloud's newer environments.** Created in the Codex app. Whether they run containers and let a task pick its model would change the verdict on route 1.
