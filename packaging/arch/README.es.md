# Paquete Arch/CachyOS de ProbRAW

Este directorio contiene el empaquetado nativo Arch/CachyOS para instalar
ProbRAW como paquete `pacman`, con venv aislado en `/opt/probraw/venv`,
lanzadores del sistema e integracion de escritorio.

## Construccion

Build local optimizada para este equipo:

```bash
PROBRAW_ARCH_PKGREL=3 \
PROBRAW_ARCH_NATIVE=1 \
PROBRAW_BUILD_AMAZE=1 \
packaging/arch/build_pkg.sh
```

Variables principales:

- `PROBRAW_ARCH_PKGREL`: revision del paquete Arch para recompilar la misma
  version upstream.
- `PROBRAW_ARCH_NATIVE=1`: usa `-O3 -march=native -mtune=native`; apropiado para
  CachyOS local, no para paquetes redistribuibles a CPUs distintas.
- `PROBRAW_BUILD_AMAZE=1`: compila e instala `rawpy-demosaic` con AMaZE/GPL3.
- `PROBRAW_ARCH_SYNCDEPS=1`: permite a `makepkg` resolver dependencias con
  `pacman`.
- `PROBRAW_MAKEPKG_ARGS="--cleanbuild"`: fuerza reconstruccion limpia.

El paquete generado queda en `build/arch/`.

## Instalacion Limpia Local

Estas ordenes limpian la instalacion del sistema, no los proyectos ni la
configuracion de usuario:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

## Validacion

Despues de instalar:

```bash
pacman -Q probraw
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-amaze
probraw check-color-environment --out color_environment.json
```

`check-color-environment` puede devolver `warning` si colord/KDE no exponen un
perfil ICC activo del monitor. En ese caso ProbRAW registra fallback visual sRGB;
no es fallo de paquete mientras `check-tools`, AMaZE y la validacion de
instalacion pasen.

## Gestion de Color

El paquete declara dependencias de sistema para:

- LittleCMS2 (`lcms2`): motor CMM de previsualizacion ICC via Pillow `ImageCms`;
- ArgyllCMS (`argyllcms`): `colprof` para crear ICC, `xicclu`/`icclu` para
  validar y `cctiff` para conversiones derivadas de exportacion;
- colord (`colord`): proveedor Linux de perfiles de dispositivo;
- ExifTool (`perl-image-exiftool`): lectura de metadatos.

Dependencias opcionales recomendadas:

- `wayland-utils`: auditoria de protocolos Wayland de color/HDR;
- `colord-kde`: integracion KDE de perfiles de monitor;
- `displaycal`: calibracion de monitor.

## AMaZE/rawpy-demosaic

La build con `PROBRAW_BUILD_AMAZE=1` usa
`scripts/build_rawpy_demosaic_wheel.py`. Ese script parchea la compilacion de
`rawpy-demosaic` para toolchains recientes de CachyOS/Python:

- politica CMake minima compatible con fuentes heredadas;
- `Cython>=3.1` y `numpy`;
- `np.set_array_base` en lugar de asignacion C-level de `ndarr.base`.

Los metadatos y hash de la wheel quedan en
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`.
