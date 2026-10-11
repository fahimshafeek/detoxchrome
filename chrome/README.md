# DetoxChrome — Android Build Configuration

This directory contains the complete build configuration, Docker environment, and custom patches to build **DetoxChrome** for Android (`arm64`).

---

## 📌 Prerequisites

- **Host OS**: Linux (x86_64)
- **Docker & Docker Compose**: Installed and operational
- **Disk Space**: At least 60–80 GB free (for Chromium Android checkout and build artifacts)
- **RAM / Swap**: 16GB+ RAM recommended (or adequate swap)

---

## 🛠 Directory Structure

```
chrome/
├── Makefile              # Master build orchestration
├── Dockerfile            # Ubuntu 22.04 container with build tools & Node 20
├── docker-compose.yml    # Build container service definition & mount points
├── args.gn               # GN build arguments (Android arm64 release config)
├── .gclient              # Google gclient configuration for Android target
└── patches/              # Custom patch suite & source injection files
    ├── apply-patches.py      # Automated patch runner
    ├── generate-patches.py   # Patch regeneration utility
    ├── build-config/         # Standalone build config backups
    ├── docs/                 # Documentation & build logs
    ├── patches/              # 18 surgical diff patches against Chromium 149
    ├── source-files/         # Custom C++ blocker, rules, and WebUI components
    └── try_snippets/         # Platform-specific injection scripts
```

---

## 🚀 Step-by-Step Reproduction Guide

To build the APK from scratch:

### 1. Setup Build Environment
Clones `depot_tools` and builds the Docker builder container:
```bash
make setup
```

### 2. Fetch Chromium Android Source Tree
Fetches Chromium source code pinned to version `149.0.7827.84`:
```bash
make fetch
```

### 3. Apply Custom Detox Patches
Injects the navigation blocker, content rules, and UI modifications:
```bash
make patches
```

*(To revert patches if needed: `make unpatches`)*

### 4. Install Dependencies & Run Hooks
Installs OS-level package dependencies inside the container and executes `gclient runhooks`:
```bash
make deps
```

### 5. Generate Ninja Build Configuration
Generates build files in `checkout/src/out/Default` using `args.gn`:
```bash
make configure
```

### 6. Build the APK
Compiles `chrome_public_apk` using Ninja with all available cores (default: 16 cores):
```bash
make build
```
*(Or specify cores: `make build CORES=8`)*

Upon completion, the compiled APK is located at:
`checkout/src/out/Default/apks/ChromePublic.apk`

---

## ⚙️ Build Arguments (`args.gn`)

```gn
target_os = "android"
target_cpu = "arm64"
symbol_level = 1
blink_symbol_level = 0
v8_symbol_level = 0
is_debug = false
treat_warnings_as_errors = false
android_static_analysis = "off"
```
