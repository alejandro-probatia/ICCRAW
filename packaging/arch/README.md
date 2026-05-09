_Spanish version: [README.es.md](README.es.md)_

# ProbRAW Arch/CachyOS Package

This directory contains the native Arch/CachyOS packaging for installing
ProbRAW as a `pacman` package, with an isolated venv under `/opt/probraw/venv`,
system launchers and desktop integration.

## Build

Local optimized build for this machine:

```bash
PROBRAW_ARCH_PKGREL=3 \
PROBRAW_ARCH_NATIVE=1 \
PROBRAW_BUILD_AMAZE=1 \
packaging/arch/build_pkg.sh
```

Main variables:

- `PROBRAW_ARCH_PKGREL`: Arch package release for rebuilding the same upstream
  version.
- `PROBRAW_ARCH_NATIVE=1`: uses `-O3 -march=native -mtune=native`; suitable for
  a local CachyOS package, not for redistribution to different CPUs.
- `PROBRAW_BUILD_AMAZE=1`: builds and installs `rawpy-demosaic` with AMaZE/GPL3.
- `PROBRAW_ARCH_SYNCDEPS=1`: lets `makepkg` resolve dependencies with `pacman`.
- `PROBRAW_MAKEPKG_ARGS="--cleanbuild"`: forces a clean rebuild.

The generated package is written to `build/arch/`.

## Clean Local Install

These commands clean the system installation, not user projects or user config:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

## Validation

After installing:

```bash
pacman -Q probraw
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-amaze
probraw check-color-environment --out color_environment.json
```

`check-color-environment` may return `warning` if colord/KDE does not expose an
active monitor ICC profile. In that case ProbRAW records visual sRGB fallback;
it is not a package failure while `check-tools`, AMaZE and installation
validation pass.

## Color Management

The package declares system dependencies for:

- LittleCMS2 (`lcms2`): ICC preview CMM through Pillow `ImageCms`;
- ArgyllCMS (`argyllcms`): `colprof` for ICC creation, `xicclu`/`icclu` for
  validation and `cctiff` for derived export conversions;
- colord (`colord`): Linux device-profile provider;
- ExifTool (`perl-image-exiftool`): metadata reading.

Recommended optional dependencies:

- `wayland-utils`: Wayland color/HDR protocol audit;
- `colord-kde`: KDE monitor-profile integration;
- `displaycal`: monitor calibration.

## AMaZE/rawpy-demosaic

Builds with `PROBRAW_BUILD_AMAZE=1` use
`scripts/build_rawpy_demosaic_wheel.py`. That script patches
`rawpy-demosaic` builds for current CachyOS/Python toolchains:

- minimum CMake policy compatible with older sources;
- `Cython>=3.1` and `numpy`;
- `np.set_array_base` instead of C-level `ndarr.base` assignment.

Wheel metadata and hash are installed under
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`.
