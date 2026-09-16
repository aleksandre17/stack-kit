# geostat-kit CLI — module drivers by stack type (java-boot, node-vite, node-api, …)

param(

    [Parameter(Position = 0)]

    [string]$Command = "help",

    [Parameter(ValueFromRemainingArguments = $true)]

    [string[]]$CliRest = @()

)



$PackageRoot = Split-Path $PSScriptRoot -Parent

if ($Command -eq "init") {
    & (Join-Path $PackageRoot "toolkit\init\Invoke-ProjectInit.ps1") -PackageRoot $PackageRoot @Args
    exit $LASTEXITCODE
}

. (Join-Path $PackageRoot "lib\project.ps1")
. (Join-Path $PackageRoot "lib\geostat-python.ps1")

. (Join-Path $PackageRoot "lib\drivers.ps1")
. (Join-Path $PackageRoot "lib\modules.ps1")

$Root = Get-ProjectRootFromManifest

if (-not $Root) {

    Write-Host "  [ERROR] geostat.ops.json not found (run: geostat init)" -ForegroundColor Red

    exit 1

}

$env:GEOSTAT_PROJECT_ROOT = $Root

$env:GEOSTAT_KIT_ROOT = $PackageRoot



function Show-Help {
    $aliases = Get-CliAliasesFromManifest
    $aliasLine = '(none)'
    if ($aliases -and $aliases.Count -gt 0) {
        $aliasLine = ($aliases.GetEnumerator() | ForEach-Object { "$($_.Key)->$($_.Value)" }) -join ', '
    }

    Write-Host @"

  geostat — manifest-driven ops CLI (geostat-kit)

    init | validate | migrate | vscode-gen | config-gen | stack | stack-deploy | compose-gen | nginx-gen | infra | layout | hybrid | dev

    mod <moduleId> deploy|manage|compose|check|modules|run  ...

    dev up <alias|moduleId|all> [--mode hybrid|local|docker] [--no-infra] [--no-tunnel]

    hybrid boot <alias|moduleId>   Local app run (host + ops/config .env.dev)

    <alias> run                    Same as hybrid boot; aliases from geostat.ops.json cli.aliases

    init  - full bootstrap (scaffold + seed secrets + compose-gen)

    Shortcuts (cli.aliases): $aliasLine

  Stack types (drivers/registry.json):

"@

    $pyArgs = Get-GeostatPythonArgs
    if ($pyArgs) {
        Invoke-GeostatPythonExe $pyArgs (Join-Path $PackageRoot "lib\driver_api.py") "list-types" 2>$null
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



function Invoke-ModuleDriver {

    param([string]$ModuleId, [string[]]$DriverArgs)

    if (-not (Get-ModuleManifestEntry $ModuleId)) {

        Write-Host "  Unknown module: $ModuleId" -ForegroundColor Red

        Write-Host "  Defined in geostat.ops.json modules.*"

        exit 1

    }

    $sub = if ($DriverArgs.Count -gt 0) { $DriverArgs[0] } else { "deploy" }

    $rest = @()
    if ($DriverArgs.Count -gt 1) {
        $rest = [string[]]@($DriverArgs | Select-Object -Skip 1)
    }

    # node-vite: "<alias> watch" -> deploy watch; "<alias> dev watch" -> dev.ps1
    $modType = Get-ModuleType $ModuleId
    if ($sub -eq "run") {
        $env:GEOSTAT_MODULE_ID = $ModuleId
        $runScript = Get-DriverCommandPath -ModuleId $ModuleId -Command "run"
        & $runScript @rest
        exit $LASTEXITCODE
    }

    if ($sub -eq "watch" -and $modType -eq "node-vite") {
        Write-Host ""
        Write-Host "  Hint: <alias> watch -> <alias> deploy watch (static dist on server)" -ForegroundColor Yellow
        Write-Host "        <alias> dev watch -> source rsync to remote dev container" -ForegroundColor Yellow
        Write-Host ""
        $env:GEOSTAT_MODULE_ID = $ModuleId
        $deployScript = Get-DriverCommandPath -ModuleId $ModuleId -Command "deploy"
        & $deployScript watch @rest
        exit $LASTEXITCODE
    }
    if ($sub -eq "watch" -and $modType -eq "java-boot") {
        Write-Host ""
        Write-Host "  Hint: <alias> watch -> <alias> dev watch (rsync + bootRun in workspace/)" -ForegroundColor Yellow
        Write-Host "        <alias> deploy watch -> bootJar + runtime/ publish loop" -ForegroundColor Yellow
        Write-Host ""
        $env:GEOSTAT_MODULE_ID = $ModuleId
        $devScript = Get-DriverCommandPath -ModuleId $ModuleId -Command "dev"
        & $bash $devScript watch @rest
        exit $LASTEXITCODE
    }

    # java-boot: "<alias> deploy watch" — JAR publish loop (subcommand under deploy)
    if ($sub -eq "deploy" -and $modType -eq "java-boot" -and $rest.Count -gt 0 -and $rest[0] -eq "watch") {
        $env:GEOSTAT_MODULE_ID = $ModuleId
        $deployScript = Get-DriverCommandPath -ModuleId $ModuleId -Command "deploy"
        & $bash $deployScript watch @($rest | Select-Object -Skip 1)
        exit $LASTEXITCODE
    }

    $valid = @{}

    foreach ($c in Get-DriverCapabilities $ModuleId) { $valid[$c] = 1 }

    if (-not $valid.ContainsKey($sub)) {

        Write-Host "  Unknown subcommand: $sub (module $ModuleId, type $modType)" -ForegroundColor Red

        Write-Host "  Valid: $($valid.Keys -join ' | ')"
        if ($modType -eq "node-vite") {
            Write-Host "  Frontend watch: deploy watch | dev watch  (see docs/FE-WATCH.md)" -ForegroundColor Gray
        }

        exit 1

    }

    $type = Get-ModuleType $ModuleId

    $reg = Get-Content (Get-DriverRegistryPath) -Raw | ConvertFrom-Json

    $runtime = $reg.$type.runtime

    $script = Get-DriverCommandPath -ModuleId $ModuleId -Command $sub

    $env:GEOSTAT_MODULE_ID = $ModuleId

    if ($runtime -eq "bash") {

        if (-not (Test-Path $bash)) { Write-Host "Git Bash required for driver $type"; exit 1 }

        & $bash $script @rest

    } else {
        if ($type -eq "node-vite" -and $sub -eq "deploy") {
            $feEnv = "prod"
            $feArgs = [System.Collections.ArrayList]@()
            for ($i = 0; $i -lt $rest.Count; $i++) {
                $a = [string]$rest[$i]
                if ($a -eq "-Environment" -and ($i + 1) -lt $rest.Count) {
                    $feEnv = [string]$rest[$i + 1]
                    $i++
                    continue
                }
                [void]$feArgs.Add($a)
            }
            if ($feArgs.Count -gt 0) {
                & $script -Arg1 ([string]$feArgs[0]) -Environment ([string]$feEnv)
            } else {
                & $script -Environment ([string]$feEnv)
            }
        } else {
            & $script @rest
        }
    }

    exit $LASTEXITCODE

}



$globalCommands = @{

    "help" = { Show-Help }

    "stack" = {

        & (Join-Path $PackageRoot "toolkit\stack\compose.ps1") @Args

        exit $LASTEXITCODE

    }

    "stack-deploy" = {

        if (-not (Test-Path $bash)) { Write-Host "Git Bash required"; exit 1 }

        & $bash (Join-Path $PackageRoot "toolkit\deploy\stack-remote.sh") @CliRest

        exit $LASTEXITCODE

    }

    "validate" = {
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-GeostatPython (Join-Path $PackageRoot "lib\validate_manifest.py")
    }

    "migrate" = {
        $env:PYTHONPATH = "$PackageRoot"
        Invoke-GeostatPython (Join-Path $PackageRoot "lib\migrate_manifest.py") @Args
    }

    "vscode-gen" = {
        $env:PYTHONPATH = "$PackageRoot"
        $vargs = @()
        if ($CliRest -contains "--force") { $vargs += "--force" }
        Invoke-GeostatPython (Join-Path $PackageRoot "lib\vscode_gen.py") @vargs
    }

    "config-gen" = {
        $env:PYTHONPATH = "$PackageRoot"
        $cargs = @()
        if ($CliRest -contains "--all") { $cargs += "--all" }
        if ($CliRest -contains "--check") { $cargs += "--check" }
        if ($CliRest -contains "--dry-run") { $cargs += "--dry-run" }
        $mod = $CliRest | Where-Object { $_ -notin @("--all", "--check", "--dry-run") } | Select-Object -First 1
        if ($mod) { $cargs += $mod }
        Invoke-GeostatPython (Join-Path $PackageRoot "lib\config_gen.py") @cargs
    }

    "compose-gen" = {

        & (Join-Path $PackageRoot "compose\build.ps1")

        exit $LASTEXITCODE

    }

    "nginx-gen" = {
        Invoke-GeostatPython (Join-Path $PackageRoot "adapters\render_nginx.py")
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
        if (-not (Test-Path $bash)) { Write-Host "Git Bash required for: geostat infra (prereqs)"; exit 1 }
        & $bash (Join-Path $PackageRoot "toolkit\infra\ensure-prereqs.sh")
        exit $LASTEXITCODE

    }

    "layout" = {
        if ($CliRest.Count -ge 1 -and $CliRest[0] -eq "migrate") {
            if (-not (Test-Path $bash)) {
                Write-Host "  Git Bash required for: geostat layout migrate ($bash)" -ForegroundColor Red
                exit 1
            }
            $migrateArgs = @()
            if ($CliRest.Count -gt 1) { $migrateArgs = $CliRest[1..($CliRest.Count - 1)] }
            & $bash (Join-Path $PackageRoot "toolkit\deploy\migrate-layout.sh") @migrateArgs
            exit $LASTEXITCODE
        }
        if ($CliRest.Count -ge 1 -and $CliRest[0] -eq "cleanup") {
            if (-not (Test-Path $bash)) {
                Write-Host "  Git Bash required for: geostat layout cleanup ($bash)" -ForegroundColor Red
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
            Write-Host "  Usage: geostat hybrid boot <alias|moduleId>" -ForegroundColor Red
            Write-Host "  Aliases: see geostat.ops.json cli.aliases (geostat help)"
            exit 1
        }
        $target = Resolve-CliAlias $CliRest[1]
        if (-not $target) {
            $target = $CliRest[1]
        }
        if (-not (Get-ModuleManifestEntry $target)) {
            Write-Host "  Unknown module or alias: $($CliRest[1])" -ForegroundColor Red
            exit 1
        }
        Invoke-ModuleDriver -ModuleId $target -DriverArgs @("run")
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

        Write-Host "  Usage: geostat mod <moduleId> <deploy|manage|...> [args]" -ForegroundColor Red

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

Write-Host "  Run: geostat help"

exit 1

