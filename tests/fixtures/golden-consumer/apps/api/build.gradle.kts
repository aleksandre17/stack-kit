plugins {
    id("org.springframework.boot") version "3.2.0"
    id("io.spring.dependency-management") version "1.1.4"
    java
}
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    // dev-only hot reload (test_devtools_in_root_gradle)
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
