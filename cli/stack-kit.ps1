# stack-kit CLI — module drivers by stack type, as drivers/registry.json declares them

# A simple param block on purpose: an advanced one (any [Parameter()]) adds PowerShell's common
# parameters, and an operand such as `-d` then binds as -Debug and is lost (ADR-001 K3).
param([string]$Command = "help", [string[]]$CliRest = @())
$CliRest = @($CliRest) + @($args)

# Where a deploy goes is a declared target (ADR-001 amendment 9): `--target <name>` selects one, and
# is taken out of the operands; otherwise the environment asked for (--env, --dev/--prod,
# -Environment) selects that environment's default target. Both reach the resolver as variables,
# so every script below -- bash or PowerShell, however deep -- resolves the same target.
# A value an earlier run set from a flag is that run's, never this one's: a launcher run in the
# operator's own session would otherwise deploy the next command to the last command's target.
# A variable the operator set themselves (no marker) is theirs and is kept.
foreach ($name in @("TARGET", "ENVIRONMENT")) {
    if ([Environment]::GetEnvironmentVariable("STACK_KIT_${name}_FROM_FLAG")) {
        [Environment]::SetEnvironmentVariable("STACK_KIT_$name", $null)
        [Environment]::SetEnvironmentVariable("STACK_KIT_${name}_FROM_FLAG", $null)
    }
}
$kept = [System.Collections.ArrayList]@()
for ($i = 0; $i -lt $CliRest.Count; $i++) {
    $a = [string]$CliRest[$i]
    if ($a -eq "--target" -and $i + 1 -lt $CliRest.Count) {
        $env:STACK_KIT_TARGET = [string]$CliRest[++$i]; $env:STACK_KIT_TARGET_FROM_FLAG = "1"; continue
    }
    $asked = $null
    if (($a -eq "--env" -or $a -eq "-Environment") -and $i + 1 -lt $CliRest.Count -and [string]$CliRest[$i + 1] -in @("dev", "prod")) {
        $asked = [string]$CliRest[$i + 1]
    }
    if ($a -eq "--dev") { $asked = "dev" }
    if ($a -eq "--prod") { $asked = "prod" }
    if ($asked) { $env:STACK_KIT_ENVIRONMENT = $asked; $env:STACK_KIT_ENVIRONMENT_FROM_FLAG = "1" }
    [void]$kept.Add($a)
}
$CliRest = [string[]]@($kept)



$PackageRoot = Split-Path $PSScriptRoot -Parent

if ($Command -eq "init") {
    & (Join-Path $PackageRoot "toolkit\init\Invoke-ProjectInit.ps1") -PackageRoot $PackageRoot @CliRest
    exit $LASTEXITCODE
}

. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\stack-kit-python.ps1")

. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")
. (Join-Path $PackageRoot "lib\runs.ps1")

$Root = Get-ProjectRootFromManifest

if (-not $Root) {

    Write-Host "  [ERROR] stack-kit.json not found (run: stack-kit init)" -ForegroundColor Red

    exit 1

}

$env:STACK_KIT_PROJECT_ROOT = $Root

$env:STACK_KIT_KIT_ROOT = $PackageRoot



function Show-Help {
    $aliases = Get-CliAliasesFromManifest
    $aliasLine = '(none)'
    if ($aliases -and $aliases.Count -gt 0) {
        $aliasLine = ($aliases.GetEnumerator() | ForEach-Object { "$($_.Key)->$($_.Value)" }) -join ', '
    }

    Write-Host @"

  stack-kit — manifest-driven ops CLI (stack-kit)

    init | validate | migrate | vscode-gen | config-gen | ci-gen | stack | stack-deploy | compose-gen | nginx-gen | infra | layout | hybrid | dev

    build | test | lint [module ...]   The step for every module (or those named), fail-fast

    targets [--plan]               Each declared deploy target (and with --plan every module's remote paths)
    --target <name>                On any deploy, remote or tunnel verb: the target to use (default: the environment's)

    mod <moduleId> <command> ...   A command its driver declares (listed per module below)
    mod <moduleId> deliver <rung> [--env dev|prod] [--plan]   A rung of its driver's delivery ladder

    dev up <alias|moduleId|all> [--mode hybrid|local|docker|remote] [--no-infra] [--no-tunnel]

    hybrid boot <alias|moduleId> [--env prod]   Host run: the module's .env + .env.dev (prod: .env + .env.prod)

    <alias> run                    Same as hybrid boot; aliases from stack-kit.json cli.aliases

    init  - full bootstrap (scaffold + seed secrets + compose-gen)

    Shortcuts (cli.aliases): $aliasLine

  Stack types (drivers/registry.json):

"@

    $pyArgs = Get-StackKitPythonArgs
    if ($pyArgs) {
        Invoke-StackKitPythonExe $pyArgs (Join-Path $PackageRoot "lib\resolve_cli.py") "driver-types" 2>$null
    }

    Write-Host ""

    Write-Host "  Project modules:"

    foreach ($mid in Get-ProjectModules) {

        $typ = Get-ModuleType $mid

        $caps = (Get-DriverCapabilities $mid) -join ", "

        $role = (Get-ModuleRole $mid)

        Write-Host "    $mid  role=$role  type=$typ  [$caps]"

    }

    $aliasMap = Get-CliAliasesFromManifest
    if ($aliasMap.Count -gt 0) {
        Write-Host ""
        Write-Host "  CLI aliases:"
        foreach ($k in ($aliasMap.Keys | Sort-Object)) {
            Write-Host "    $k -> $($aliasMap[$k])"
        }
    }

    Write-Host ""

}



$bash = "${env:ProgramFiles}\Git\bin\bash.exe"

if (-not (Test-Path $bash)) { $bash = "${env:ProgramFiles}\Git\usr\bin\bash.exe" }
# Off Windows (or with Git elsewhere) the bash on PATH -- never the WSL launcher in System32.
if (-not (Test-Path $bash)) {
    $found = Get-Command bash -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch 'System32' } | Select-Object -First 1
    if ($found) { $bash = $found.Source }
}



function Invoke-DriverScript {
    # Runs one driver script by what it IS: a .sh under bash, a .ps1 in this session. A PowerShell
    # script's `-Name value` operands bind to the parameters it declares (a switch takes no value);
    # every other operand stays positional, in order. No driver is named here (ADR-001 K6).
    param([string]$Script, [string[]]$Operands = @())
    if ($Script -like '*.sh') {
        if (-not (Test-Path $bash)) { Write-Host "  Git Bash required for $Script" -ForegroundColor Red; exit 1 }
        & $bash $Script @Operands
        return
    }
    $declared = (Get-Command $Script).Parameters
    $common = [System.Management.Automation.PSCmdlet]::CommonParameters + [System.Management.Automation.PSCmdlet]::OptionalCommonParameters
    $named = @{}
    $positional = [System.Collections.ArrayList]@()
    for ($i = 0; $i -lt $Operands.Count; $i++) {
        $t = [string]$Operands[$i]
        if ($t -match '^-([A-Za-z]\w*)$' -and $declared.ContainsKey($Matches[1]) -and $Matches[1] -notin $common) {
            $p = $declared[$Matches[1]]
            if ($p.ParameterType -eq [switch]) { $named[$p.Name] = $true; continue }
            if ($i + 1 -lt $Operands.Count) { $named[$p.Name] = [string]$Operands[++$i]; continue }
        }
        [void]$positional.Add($t)
    }
    # A PowerShell driver reports failure by THROWING; a throw sets no $LASTEXITCODE, so without
    # this a failed command exited 0 (seen with a PowerShell driver's deploy).
    $global:LASTEXITCODE = 0
    $posArgs = @($positional)
    & $Script @posArgs @named
}

function Invoke-ModuleDriver {
    param([string]$ModuleId, [string[]]$DriverArgs)

    if (-not (Get-ModuleManifestEntry $ModuleId)) {
        Write-Host "  Unknown module: $ModuleId" -ForegroundColor Red
        Write-Host "  Defined in $((Get-KitIdentity).manifestFilename) modules.*"
        exit 1
    }
    $modType = Get-ModuleType $ModuleId
    $sub = if ($DriverArgs.Count -gt 0) { $DriverArgs[0] } else { "deploy" }
    $rest = @()
    if ($DriverArgs.Count -gt 1) { $rest = [string[]]@($DriverArgs | Select-Object -Skip 1) }

    # An operand the driver DECLARES as another (e.g. a bare `watch`): rewritten, and said so.
    $rewrite = Get-KitContextValue "driver:$($modType):operand:$sub"
    if ($rewrite) {
        $rw = $rewrite | ConvertFrom-Json
        if ($rw.hint) { Write-Host ""; Write-Host "  Hint: $($rw.hint)" -ForegroundColor Yellow; Write-Host "" }
        $to = @($rw.to | ForEach-Object { [string]$_ })
        $sub = $to[0]
        $rest = @($to | Select-Object -Skip 1) + $rest
    }

    # The delivery ladder the driver DECLARES: `deliver <rung> [--env dev|prod] [--plan] [operands]`.
    if ($sub -eq "deliver") {
        $rungs = @(Get-KitContextLines "driver:$($modType):rungs")
        $rung = if ($rest.Count -gt 0) { [string]$rest[0] } else { "" }
        $declaredRung = Get-KitContextValue "driver:$($modType):rung:$rung"
        if (-not $declaredRung) {
            Write-Host "  Driver '$modType' declares no delivery rung '$rung' (declared: $($rungs -join ', '))" -ForegroundColor Red
            exit 1
        }
        $how = $declaredRung | ConvertFrom-Json
        if ($how.pending) {
            Write-Host "  Rung '$rung' of driver '$modType' is declared but not built: $($how.pending)" -ForegroundColor Red
            exit 1
        }
        $environment = ""; $plan = $false; $extra = [System.Collections.ArrayList]@()
        for ($i = 1; $i -lt $rest.Count; $i++) {
            switch ([string]$rest[$i]) {
                "--plan" { $plan = $true }
                "--env" { $environment = [string]$rest[++$i] }
                default { [void]$extra.Add([string]$rest[$i]) }
            }
        }
        if ($how.via) {
            # A kit verb keeps its own default environment (a host run's is dev); only an asked one is passed.
            $viaArgs = @($how.via, "boot", $ModuleId) + $(if ($environment) { @("--env", $environment) } else { @() }) + @($extra)
            if ($plan) { Write-Host "  deliver $rung -> stack-kit $($viaArgs -join ' ')"; exit 0 }
            $self = Join-Path $PSScriptRoot "stack-kit.ps1"
            exit (Invoke-RecordedStep -Kind "deliver" -Step $rung -ModuleId $ModuleId -Environment $environment -Action {
                & $self @viaArgs
            })
        }
        if (-not $environment) { $environment = "prod" }
        $deliverRung = $rung
        $sub = [string]$how.command
        $rest = @(@($how.args) | Where-Object { $null -ne $_ } | ForEach-Object { ([string]$_).Replace("{environment}", $environment) }) + @($extra)
        if ($plan) {
            Write-Host "  deliver $rung -> $sub $($rest -join ' ')  ($(Get-DriverCommandPath -ModuleId $ModuleId -Command $sub))"
            exit 0
        }
    }

    $caps = @(Get-DriverCapabilities $ModuleId)
    if ($sub -notin $caps) {
        Write-Host "  Unknown subcommand: $sub (module $ModuleId, type $modType)" -ForegroundColor Red
        Write-Host "  Valid: $($caps -join ' | ') | deliver <$(@(Get-KitContextLines "driver:$($modType):rungs") -join '|')>"
        exit 1
    }
    $script = Get-DriverCommandPath -ModuleId $ModuleId -Command $sub
    $env:STACK_KIT_MODULE_ID = $ModuleId
    # The command by name, for a script that is several drivers' (the kit's runners).
    $env:STACK_KIT_COMMAND = $sub
    if ($deliverRung) {
        exit (Invoke-RecordedStep -Kind "deliver" -Step $deliverRung -ModuleId $ModuleId -Environment $environment -Action {
            Invoke-DriverScript -Script $script -Operands $rest
        })
    }
    try {
        Invoke-DriverScript -Script $script -Operands $rest
    } catch {
        Write-Host "[$ModuleId $sub] $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    exit $LASTEXITCODE
}

function Invoke-LifecycleStep {
    # `stack-kit build|test|lint [module|alias ...]`: the step for every module (or the named ones),
    # in manifest order, fail-fast, each in its own process so its exit code is the step's. A module
    # whose driver declares no such step fails -- except for an optional step, which it skips.
    param([Parameter(Mandatory = $true)][string]$Step, [string[]]$Only = @())
    $optional = @(Get-KitContextLines "lifecycle:optional")
    $modules = @(Get-ProjectModules)
    if ($Only.Count -gt 0) {
        $wanted = @($Only | ForEach-Object {
            $m = Resolve-CliAlias $_
            if (-not $m) { Write-Host "  Unknown module or alias: $_" -ForegroundColor Red; exit 1 }
            $m
        })
        $modules = @($modules | Where-Object { $wanted -contains $_ })
    }
    $shell = (Get-Process -Id $PID).Path
    $self = Join-Path $PSScriptRoot "stack-kit.ps1"
    $ran = 0
    foreach ($mid in $modules) {
        if ($Step -notin @(Get-DriverCapabilities $mid)) {
            if ($optional -contains $Step) {
                Write-Host "  [$mid $Step] skipped: driver '$(Get-ModuleType $mid)' declares no $Step" -ForegroundColor DarkGray
                continue
            }
            Write-Host "  [$mid $Step] driver '$(Get-ModuleType $mid)' declares no $Step step" -ForegroundColor Red
            exit 1
        }
        $code = Invoke-RecordedStep -Kind "step" -Step $Step -ModuleId $mid -Action {
            & $shell -NoProfile -ExecutionPolicy Bypass -File $self mod $mid $Step
        }
        if ($code -ne 0) {
            Write-Host "  [$mid $Step] FAILED (exit $code)" -ForegroundColor Red
            exit $code
        }
        $ran++
    }
    Write-Host "  $Step OK ($ran module(s))" -ForegroundColor Green
    exit 0
}



$globalCommands = @{

    "help" = { Show-Help }

    "stack" = {

        & (Join-Path $PackageRoot "toolkit\stack\compose.ps1") @CliRest

        exit $LASTEXITCODE

    }

    "stack-deploy" = {

        if (-not (Test-Path $bash)) { Write-Host "Git Bash required"; exit 1 }

        & $bash (Join-Path $PackageRoot "toolkit\deploy\stack-remote.sh") @CliRest

        exit $LASTEXITCODE

    }

    "validate" = {
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\validate_manifest.py") @CliRest
    }

    "migrate" = {
        # The handler is invoked without arguments: the operands are the CLI's own ($CliRest).
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\migrate_manifest.py") @CliRest
    }

    "vscode-gen" = {
        $env:PYTHONPATH = "$PackageRoot"
        $vargs = @()
        if ($CliRest -contains "--force") { $vargs += "--force" }
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\vscode_gen.py") @vargs
    }

    "config-gen" = {
        $env:PYTHONPATH = "$PackageRoot"
        $cargs = @()
        if ($CliRest -contains "--all") { $cargs += "--all" }
        if ($CliRest -contains "--check") { $cargs += "--check" }
        if ($CliRest -contains "--dry-run") { $cargs += "--dry-run" }
        $mod = $CliRest | Where-Object { $_ -notin @("--all", "--check", "--dry-run") } | Select-Object -First 1
        if ($mod) { $cargs += $mod }
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\config_gen.py") @cargs
    }

    "compose-gen" = {

        & (Join-Path $PackageRoot "compose\build.ps1")

        exit $LASTEXITCODE

    }

    "nginx-gen" = {
        Invoke-StackKitPython (Join-Path $PackageRoot "adapters\render_nginx.py")
    }

    "infra" = {

        $infraDriver = Join-Path $PackageRoot "toolkit\infra\Invoke-Infra.ps1"
        $infraPass = [System.Collections.ArrayList]@($CliRest)
        $infraProd = $false
        if ($infraPass -contains "-Prod" -or $infraPass -contains "--prod") {
            $infraProd = $true
            [void]$infraPass.Remove("-Prod")
            [void]$infraPass.Remove("--prod")
        }
        if ($infraPass.Count -gt 0 -and (Test-Path $infraDriver)) {
            $infraMode = [string]$infraPass[0]
            $infraAction = if ($infraPass.Count -gt 1) { [string]$infraPass[1] } else { "" }
            if ($infraProd) {
                & $infraDriver $infraMode $infraAction -Prod
            } else {
                & $infraDriver $infraMode $infraAction
            }
            exit $LASTEXITCODE
        }
        if (-not (Test-Path $bash)) { Write-Host "Git Bash required for: stack-kit infra (prereqs)"; exit 1 }
        & $bash (Join-Path $PackageRoot "toolkit\infra\ensure-prereqs.sh")
        exit $LASTEXITCODE

    }

    "layout" = {
        if ($CliRest.Count -ge 1 -and $CliRest[0] -eq "migrate") {
            if (-not (Test-Path $bash)) {
                Write-Host "  Git Bash required for: stack-kit layout migrate ($bash)" -ForegroundColor Red
                exit 1
            }
            $migrateArgs = @()
            if ($CliRest.Count -gt 1) { $migrateArgs = $CliRest[1..($CliRest.Count - 1)] }
            & $bash (Join-Path $PackageRoot "toolkit\deploy\migrate-layout.sh") @migrateArgs
            exit $LASTEXITCODE
        }
        if ($CliRest.Count -ge 1 -and $CliRest[0] -eq "cleanup") {
            if (-not (Test-Path $bash)) {
                Write-Host "  Git Bash required for: stack-kit layout cleanup ($bash)" -ForegroundColor Red
                exit 1
            }
            $cleanupArgs = @()
            if ($CliRest.Count -gt 1) { $cleanupArgs = $CliRest[1..($CliRest.Count - 1)] }
            & $bash (Join-Path $PackageRoot "toolkit\deploy\cleanup-scoped-layout.sh") @cleanupArgs
            exit $LASTEXITCODE
        }
        $layoutArgs = [System.Collections.ArrayList]@($CliRest)
        $roleFilter = $null
        $modFilter = $null
        $runAll = $false
        $runServer = $true
        $i = 0
        while ($i -lt $layoutArgs.Count) {
            $a = [string]$layoutArgs[$i]
            if ($a -in @("--all")) { $runAll = $true; $layoutArgs.RemoveAt($i); continue }
            if ($a -in @("--no-server")) { $runServer = $false; $layoutArgs.RemoveAt($i); continue }
            if ($a -in @("--frontend", "-Frontend")) {
                Write-Host "  [warn] --frontend deprecated; use --role ui" -ForegroundColor Yellow
                $roleFilter = "ui"; $layoutArgs.RemoveAt($i); continue
            }
            if ($a -in @("--backend", "-Backend")) {
                Write-Host "  [warn] --backend deprecated; use --role api" -ForegroundColor Yellow
                $roleFilter = "api"; $layoutArgs.RemoveAt($i); continue
            }
            if ($a -in @("--role", "-Role") -and ($i + 1) -lt $layoutArgs.Count) {
                $roleFilter = [string]$layoutArgs[$i + 1]
                $layoutArgs.RemoveAt($i + 1); $layoutArgs.RemoveAt($i); continue
            }
            if ($a -in @("--module", "-Module") -and ($i + 1) -lt $layoutArgs.Count) {
                $modFilter = [string]$layoutArgs[$i + 1]
                $layoutArgs.RemoveAt($i + 1); $layoutArgs.RemoveAt($i); continue
            }
            $i++
        }
        $targets = [System.Collections.ArrayList]@()
        if ($modFilter) {
            if (-not (Get-ModuleManifestEntry $modFilter)) {
                Write-Host "  Unknown module: $modFilter" -ForegroundColor Red; exit 1
            }
            [void]$targets.Add($modFilter)
        } elseif ($roleFilter) {
            foreach ($mid in (Get-ModuleIdsByRole $roleFilter)) { [void]$targets.Add($mid) }
            if ($targets.Count -eq 0) {
                Write-Host "  No modules with role=$roleFilter" -ForegroundColor Red; exit 1
            }
        } elseif ($runAll) {
            foreach ($mid in (Get-ProjectModules)) { [void]$targets.Add($mid) }
        } else {
            foreach ($mid in (Get-ProjectModules)) { [void]$targets.Add($mid) }
        }
        foreach ($mid in $targets) {
            Write-Host ""
            Write-Host "  === layout: module $mid (role $(Get-ModuleRole $mid), type $(Get-ModuleType $mid)) ===" -ForegroundColor Cyan
            Invoke-ModuleLayoutSimulator -ModuleId $mid @layoutArgs
        }
        if ($runServer -and -not $modFilter -and -not $roleFilter) {
            & (Join-Path $PackageRoot "toolkit\layout\simulate-server-layout.ps1") @layoutArgs
        }
        exit $LASTEXITCODE
    }

    "hybrid" = {
        if ($CliRest.Count -lt 2 -or $CliRest[0] -ne "boot") {
            Write-Host "  Usage: stack-kit hybrid boot <alias|moduleId>" -ForegroundColor Red
            Write-Host "  Aliases: see stack-kit.json cli.aliases (stack-kit help)"
            exit 1
        }
        $target = Resolve-CliAlias $CliRest[1]
        if (-not $target) {
            $target = $CliRest[1]
        }
        # A host run reads development configuration; production's only when asked (`--env prod`).
        $runEnv = "dev"
        for ($i = 2; $i -lt $CliRest.Count; $i++) {
            if ([string]$CliRest[$i] -eq "--env" -and $i + 1 -lt $CliRest.Count) { $runEnv = [string]$CliRest[++$i] }
        }
        if (-not (Get-ModuleManifestEntry $target)) {
            Write-Host "  Unknown module or alias: $($CliRest[1])" -ForegroundColor Red
            exit 1
        }
        # The host run is the shared runner and the launch step the driver declares (hybrid.script);
        # no driver command stands between them.
        $env:STACK_KIT_MODULE_ID = $target
        $env:STACK_KIT_KIT_ROOT = $PackageRoot
        & (Join-Path $PackageRoot "toolkit\hybrid\Invoke-HybridRun.ps1") -ModuleId $target -Environment $runEnv
        exit $LASTEXITCODE
    }

    "build" = { Invoke-LifecycleStep -Step "build" -Only $CliRest }
    "test" = { Invoke-LifecycleStep -Step "test" -Only $CliRest }
    "lint" = { Invoke-LifecycleStep -Step "lint" -Only $CliRest }

    "targets" = {
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\targets.py") @CliRest
    }

    "ci-gen" = {
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-StackKitPython (Join-Path $PackageRoot "lib\ci_gen.py") @CliRest
    }

    "dev" = {
        $devSub  = if ($CliRest.Count -gt 0) { [string]$CliRest[0] } else { "help" }
        $devArgs = if ($CliRest.Count -gt 1) { [string[]]@($CliRest[1..($CliRest.Count - 1)]) } else { @() }
        $devScript = Join-Path $PackageRoot "toolkit\dev\Invoke-DevUp.ps1"
        if (-not (Test-Path $devScript)) {
            Write-Host "  [dev] toolkit/dev/Invoke-DevUp.ps1 not found" -ForegroundColor Red
            exit 1
        }
        & $devScript -SubCommand $devSub -DevArgs $devArgs
        exit $LASTEXITCODE
    }

}



if ($globalCommands.ContainsKey($Command)) {

    & $globalCommands[$Command]

    exit $LASTEXITCODE

}



if ($Command -eq "mod") {

    if ($CliRest.Count -lt 1) {

        Write-Host "  Usage: stack-kit mod <moduleId> <deploy|manage|...> [args]" -ForegroundColor Red

        exit 1

    }

    $moduleId = $CliRest[0]

    $rest = if ($CliRest.Count -gt 1) { $CliRest[1..($CliRest.Count - 1)] } else { @() }

    Invoke-ModuleDriver -ModuleId $moduleId -DriverArgs $rest

}



$aliasTarget = Resolve-CliAlias $Command

if ($aliasTarget) {

    Invoke-ModuleDriver -ModuleId $aliasTarget -DriverArgs $CliRest

}



Write-Host "  Unknown command: $Command" -ForegroundColor Red

Write-Host "  Run: stack-kit help"

exit 1

