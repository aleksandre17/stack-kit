# SSH — სად ჩასვა გასაღები (clone-ის შემდეგ)

Deploy (`stack-kit fe/be deploy`, `manage`, `dev`) იყენებს **OpenSSH**-ს (`ssh` / `scp`).  
პრივატული გასაღები **არასოდეს** არ უნდა იყოს git-ში.

## სწრაფი არჩევანი

| მეთოდი | სად არის key | რა ჩაწერო `ops/config/deploy.env`-ში |
|--------|--------------|-------------------------------------|
| **A — სტანდარტული (რეკომენდებული)** | `~/.ssh/id_ed25519` (ან `id_rsa`) | `DEPLOY_SERVER=user@host` |
| **B — პროექტის ფოლდერი** | `ops/config/ssh/id_ed25519` (gitignored) | `DEPLOY_SERVER=user@host` + `DEPLOY_SSH_IDENTITY_FILE=ops/config/ssh/id_ed25519` |
| **C — SSH config alias** | `ops/config/ssh/config` (gitignored) | `DEPLOY_SERVER=stack-kit-deploy` + `DEPLOY_SSH_CONFIG_FILE=ops/config/ssh/config` |

## A — `~/.ssh`

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
ssh-copy-id user@YOUR_SERVER
```

`ops/config/deploy.env`: `DEPLOY_SERVER=user@host`

## B — `ops/config/ssh/`

დააკოპირე პრივატული key → `ops/config/ssh/id_ed25519` (ან `id_rsa` + შესაბამისი `DEPLOY_SSH_IDENTITY_FILE`).

## C — config alias

`copy config.example config` → შეავსე → `DEPLOY_SSH_CONFIG_FILE=ops/config/ssh/config`, `DEPLOY_SERVER=stack-kit-deploy`.

## Ops ცვლადები

| ცვლადი | ფაილი |
|--------|--------|
| `DEPLOY_SERVER` | `ops/config/deploy.env` |
| `DEPLOY_SSH_IDENTITY_FILE` | optional |
| `DEPLOY_SSH_CONFIG_FILE` | optional |

სრული adoption: [kits/stack-kit/docs/ADOPT.md#configuration](../../../kits/stack-kit/docs/ADOPT.md#configuration)
