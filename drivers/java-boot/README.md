# java-boot driver

Gradle / Spring Boot modules (`"type": "java-boot"`). Everything below is a declaration in
`drivers/registry.json`; the kit's verbs (`deploy`, `dev`, `ops`) run it like any other driver.

| | Declared |
|---|---|
| lifecycle | `build` (`ps1/build.ps1`, Gradle `build -x test`), `test` (`ps1/test.ps1`) |
| host run | `run` / `hybrid boot`: the boot jar when preferred, else `bootRun` (`ps1/hybrid.ps1`; `hybrid.gradleWrapper`, `hybrid.gradleProject`, `hybrid.springProfiles`) |
| package | `build`, then `build/libs/*.jar` |
| release | `container/Dockerfile`: the boot jar on a JRE of the module's `toolchain.version` (`artifactExclude` drops `*-plain.jar`), internal port 8080 (a module's `container.port` over it) |
| remote dev | a JDK image running `bootRun`; Gradle's cache a named volume; a Java source change `rebuild`s (`classes` in the container, DevTools restarts), a build file `restart`s |
| migrations | Flyway SQL under `src/main/resources/db/migration`, structure only (`validate`) |

Several services from one Gradle build: `modules.<id>.services.<service>.context` names the
subproject whose `build/libs` it runs. Golden paths: [docs/GOLDEN-PATHS.md](../../docs/GOLDEN-PATHS.md).
