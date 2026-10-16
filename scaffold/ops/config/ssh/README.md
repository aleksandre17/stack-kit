# SSH — სად ჩასვა გასაღები (clone-ის შემდეგ)

ყველა remote ზმნა (`deploy`, `release`, `ops`, `dev`, `targets --verify`) იყენებს **OpenSSH**-ს.
პრივატული გასაღები **არასოდეს** არ უნდა იყოს git-ში. სად მიდის deploy — ეს `ops/deploy/targets.json`-ია,
ვინაობა იქ მხოლოდ **მითითებაა** (`ssh.identity`), არასოდეს გასაღები.

| მეთოდი | სად არის key | `targets.<name>.ssh.identity` |
|--------|--------------|-------------------------------|
| **A — ssh-agent (რეკომენდებული)** | `~/.ssh/id_ed25519`, agent-ში | `agent` (ნაგულისხმევი) |
| **B — პროექტის ფოლდერი** | `ops/config/ssh/id_ed25519` (gitignored) | `file:ops/config/ssh/id_ed25519` |
| **C — ცვლადი** | სადმე, გზა ცვლადში | `env:DEPLOY_KEY_PATH` |
| **D — SSH config** | `ops/config/ssh/config` (gitignored) | `ssh.config: "ops/config/ssh/config"` |

სერვერის გასაღები მიმაგრებულია (`ssh.knownHosts`, `hostKeys: pinned`); `BatchMode=yes` — პაროლით შესვლა არ ხდება.

სრული adoption: [kits/stack-kit/docs/ADOPT.md#configuration](../../../kits/stack-kit/docs/ADOPT.md#configuration)
