from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class BrowserMetadataMixin:
    def _pick_directory(self) -> None:
        p = QtWidgets.QFileDialog.getExistingDirectory(self, self.tr("Selecciona directorio"))
        if not p:
            return
        selected = Path(p)
        project_root = self._project_root_for_path(selected)
        if project_root is not None:
            self.session_root_path.setText(str(project_root))
            self._on_session_root_edited()
        self.dir_tree.setCurrentIndex(self._dir_model.index(str(selected)))
        self._set_current_directory(selected)

    def _detect_storage_roots(self) -> list[Path]:
        roots: list[Path] = []
        if sys.platform.startswith("win"):
            for fi in QtCore.QDir.drives():
                p = Path(fi.absoluteFilePath())
                if p not in roots:
                    roots.append(p)
        else:
            roots.append(Path("/"))

        if hasattr(QtCore, "QStorageInfo"):
            for vol in QtCore.QStorageInfo.mountedVolumes():
                try:
                    if not vol.isValid() or not vol.isReady():
                        continue
                    p = Path(vol.rootPath())
                    if p not in roots:
                        roots.append(p)
                except Exception:
                    continue

        roots = sorted(roots, key=lambda p: str(p))
        return roots

    def _refresh_storage_roots(self) -> None:
        roots = self._detect_storage_roots()
        self._storage_roots = roots
        current_dir = self._current_dir

        self.storage_root_combo.blockSignals(True)
        self.storage_root_combo.clear()
        best_idx = -1
        best_len = -1

        for idx, root in enumerate(roots):
            label = str(root)
            self.storage_root_combo.addItem(label, str(root))
            if str(current_dir).startswith(str(root)) and len(str(root)) > best_len:
                best_idx = idx
                best_len = len(str(root))

        if best_idx >= 0:
            self.storage_root_combo.setCurrentIndex(best_idx)
        self.storage_root_combo.blockSignals(False)

    def _on_storage_root_changed(self, idx: int) -> None:
        if idx < 0:
            return
        data = self.storage_root_combo.itemData(idx)
        if not data:
            return
        root = Path(str(data))
        self.dir_tree.setCurrentIndex(self._dir_model.index(str(root)))
        self._set_current_directory(root)

    def _on_tree_clicked(self, index) -> None:
        p = Path(self._dir_model.filePath(index))
        self._set_current_directory(p)

    def _set_current_directory(self, folder: Path) -> None:
        resolved_folder = self._resolve_existing_directory(folder)
        if resolved_folder is None:
            self._set_status(self.tr("Directorio no encontrado:") + f" {folder}")
            return
        folder = self._preferred_browsing_directory(resolved_folder)
        self._current_dir = folder
        self.current_dir_label.setText(str(folder))
        self._settings.setValue("browser/last_dir", str(folder))
        self._refresh_storage_roots()
        self._set_filesystem_model_root(folder)
        index = self._dir_model.index(str(folder))
        if index.isValid():
            self.dir_tree.blockSignals(True)
            self.dir_tree.setCurrentIndex(index)
            self.dir_tree.scrollTo(index)
            self.dir_tree.blockSignals(False)
        self._sync_operational_dirs_from_browser(folder)
        self._populate_file_list(folder)
        self._set_status(self.tr("Directorio actual:") + f" {folder}")

    def _reload_current_directory(self) -> None:
        self._populate_file_list(self._current_dir)

    def _populate_file_list(self, folder: Path) -> None:
        self._selection_load_timer.stop()
        self.file_list.clear()
        self._file_items_by_key.clear()
        self._preview_load_pending_request = None
        self._profile_preview_pending_request = None
        self._profile_preview_expected_key = None
        self._metadata_pending_request = None
        self._selected_file = None
        self._clear_manual_chart_points_for_file_change()
        self._last_loaded_preview_key = None
        self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
        self._clear_metadata_view()
        self._clear_viewer_histogram()

        max_items = 500
        shown: list[Path] = []
        truncated = False
        try:
            for p in folder.iterdir():
                if not p.is_file() or p.suffix.lower() not in BROWSABLE_EXTENSIONS:
                    continue
                shown.append(p)
                if len(shown) >= max_items:
                    truncated = True
                    break
        except OSError as exc:
            self._log_preview(f"No se pudo listar carpeta: {exc}")
            return

        shown.sort(key=lambda p: p.name.lower())

        for p in shown:
            item = QtWidgets.QListWidgetItem("")
            item.setData(QtCore.Qt.UserRole, str(p))
            item.setData(QtCore.Qt.UserRole + 1, p.name)
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setToolTip(self._file_item_tooltip(p))
            item.setIcon(self._display_icon_for_path(p, self._icon_for_file(p)))
            item.setSizeHint(self.file_list.gridSize())
            self.file_list.addItem(item)
            self._file_items_by_key[self._normalized_path_key(p)] = item

        if truncated:
            i = QtWidgets.QListWidgetItem("... mas archivos no mostrados")
            i.setFlags(QtCore.Qt.NoItemFlags)
            self.file_list.addItem(i)

        self._queue_thumbnail_generation(shown)

    def _file_list_paths(self) -> list[Path]:
        paths: list[Path] = []
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if raw_path:
                path = self._resolve_existing_browsable_path(Path(str(raw_path)))
                if path is not None:
                    if self._normalized_path_key(path) != self._normalized_path_key(Path(str(raw_path))):
                        self._update_file_item_path(item, path)
                    paths.append(path)
        return paths

    def _set_file_list_placeholder_icons(self) -> None:
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if raw_path:
                path = Path(str(raw_path))
                item.setToolTip(self._file_item_tooltip(path))
                item.setIcon(self._display_icon_for_path(path, self._icon_for_file(path)))

    def _queue_thumbnail_generation(self, paths: list[Path], *, delay_ms: int = 220) -> None:
        self._thumbnail_generation += 1
        self._pending_thumbnail_paths = list(paths)
        self._thumbnail_scan_index = 0
        if not self._pending_thumbnail_paths:
            self._thumbnail_timer.stop()
            return
        self._thumbnail_timer.start(max(0, int(delay_ms)))

    def _start_pending_thumbnail_generation(self) -> None:
        if self._thumbnail_task_active:
            return
        paths = [p for p in self._pending_thumbnail_paths if p.exists() and p.is_file()]
        if not paths:
            return

        size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        generation = self._thumbnail_generation
        self._apply_cached_thumbnails(paths, size)
        missing = self._next_thumbnail_batch(paths, size)
        if not missing:
            return

        payload_inputs = [(path, self._thumbnail_cache_key(path, size)) for path in missing]

        def task():
            return generation, size, self._build_thumbnail_payloads_for_keys(payload_inputs, size)

        thread = TaskThread(task)
        self._thumbnail_task_active = True
        self._threads.append(thread)

        def cleanup() -> None:
            self._thumbnail_task_active = False
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            if self._pending_thumbnail_paths and generation != self._thumbnail_generation:
                self._thumbnail_timer.start(0)

        def ok(payload) -> None:
            try:
                payload_generation, payload_size, thumbnails = payload
                if payload_generation != self._thumbnail_generation:
                    return
                touched_cache_dirs: set[Path] = set()
                target_icon_size = self.file_list.iconSize()
                for raw_path, key, rgb_u8 in thumbnails:
                    icon = self._icon_from_thumbnail_array(rgb_u8, target_size=target_icon_size)
                    self._image_thumb_cache[key] = icon
                    path = Path(raw_path)
                    cache_dir = self._write_thumbnail_to_disk_cache(key, rgb_u8, path=path, prune=False)
                    if cache_dir is not None:
                        touched_cache_dirs.add(cache_dir)
                    self._set_item_icon_for_path(path, icon)
                if touched_cache_dirs:
                    self._thumbnail_disk_writes_since_prune += len(thumbnails)
                    if self._thumbnail_disk_writes_since_prune >= THUMBNAIL_DISK_PRUNE_INTERVAL_WRITES:
                        for cache_dir in touched_cache_dirs:
                            self._prune_disk_cache(
                                cache_dir,
                                pattern="*.png",
                                max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                                max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                            )
                        self._thumbnail_disk_writes_since_prune = 0
                self._prune_thumbnail_cache()
                self._apply_cached_thumbnails(self._file_list_paths(), int(payload_size))
                if self._should_prefetch_more_thumbnails():
                    self._thumbnail_timer.start(80)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            cleanup()
            self._log_preview(f"No se pudieron generar miniaturas: {trace.strip().splitlines()[-1] if trace.strip() else 'error'}")

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _next_thumbnail_batch(self, paths: list[Path], size: int) -> list[Path]:
        batch: list[Path] = []
        while self._thumbnail_scan_index < len(paths) and len(batch) < THUMBNAIL_BATCH_SIZE:
            path = paths[self._thumbnail_scan_index]
            self._thumbnail_scan_index += 1
            if self._cached_thumbnail_icon(self._thumbnail_cache_key(path, size), path=path) is None:
                batch.append(path)
        return batch

    def _on_thumbnail_scroll_changed(self, _value: int) -> None:
        if self._thumbnail_task_active or not self._pending_thumbnail_paths:
            return
        if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
            return
        if self._should_prefetch_more_thumbnails():
            self._thumbnail_timer.start(80)

    def _should_prefetch_more_thumbnails(self) -> bool:
        if not hasattr(self, "file_list"):
            return False
        if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
            return False
        scrollbar = self.file_list.horizontalScrollBar()
        maximum = int(scrollbar.maximum())
        if maximum <= 0:
            return False
        margin = max(1, int(scrollbar.pageStep()) * THUMBNAIL_PREFETCH_MARGIN_PAGES)
        return int(scrollbar.value()) >= maximum - margin

    def _apply_cached_thumbnails(self, paths: list[Path], size: int) -> None:
        for p in paths:
            icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(p, size), path=p)
            if icon is not None:
                self._set_item_icon_for_path(p, icon)

    def _cached_thumbnail_icon(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
        icon = self._image_thumb_cache.get(key)
        if icon is not None:
            return icon
        icon = self._read_thumbnail_from_disk_cache(key, path=path)
        if icon is None:
            return None
        self._image_thumb_cache[key] = icon
        self._prune_thumbnail_cache()
        return icon

    def _user_disk_cache_dir(self, kind: str) -> Path:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Caches"
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        return base / APP_NAME / kind

    def _project_disk_cache_dir(self, path: Path | None, kind: str) -> Path | None:
        if path is None or self._active_session_root is None:
            return None
        if not self._path_is_inside(path, self._active_session_root):
            return None
        return self._session_paths_from_root(self._active_session_root)["work"] / "cache" / kind

    def _disk_cache_dirs(self, path: Path | None, kind: str) -> list[Path]:
        dirs: list[Path] = []
        project_dir = self._project_disk_cache_dir(path, kind)
        if project_dir is not None:
            dirs.append(project_dir)
        user_dir = self._user_disk_cache_dir(kind)
        if user_dir not in dirs:
            dirs.append(user_dir)
        return dirs

    def _thumbnail_disk_cache_dir(self, path: Path | None = None) -> Path:
        return self._disk_cache_dirs(path, "thumbnails")[0]

    def _disk_cache_path(self, base_dir: Path, key: str, suffix: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()
        return base_dir / digest[:2] / f"{digest}{suffix}"

    def _thumbnail_disk_cache_path(self, key: str, *, base_dir: Path | None = None, path: Path | None = None) -> Path:
        return self._disk_cache_path(base_dir or self._thumbnail_disk_cache_dir(path), key, ".png")

    def _read_thumbnail_from_disk_cache(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
        for cache_dir in self._disk_cache_dirs(path, "thumbnails"):
            cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
            if not cache_path.is_file():
                continue
            pixmap = QtGui.QPixmap(str(cache_path))
            if pixmap.isNull():
                continue
            try:
                os.utime(cache_path, None)
            except Exception:
                pass
            return QtGui.QIcon(pixmap)
        return None

    def _write_thumbnail_to_disk_cache(
        self,
        key: str,
        rgb_u8: np.ndarray,
        *,
        path: Path | None = None,
        prune: bool = True,
    ) -> Path | None:
        try:
            cache_dir = self._thumbnail_disk_cache_dir(path)
            cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            image = np.asarray(rgb_u8, dtype=np.uint8)
            if image.ndim == 2:
                image = np.repeat(image[..., None], 3, axis=2)
            if image.shape[-1] > 3:
                image = image[..., :3]
            Image.fromarray(np.ascontiguousarray(image)).save(cache_path, format="PNG")
            if prune:
                self._prune_disk_cache(
                    cache_dir,
                    pattern="*.png",
                    max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                    max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                )
            return cache_dir
        except Exception:
            return None

    def _prune_disk_cache(self, cache_dir: Path, *, pattern: str, max_entries: int, max_bytes: int) -> None:
        try:
            files = [p for p in cache_dir.glob(f"*/*{pattern.removeprefix('*')}") if p.is_file()]
        except Exception:
            return
        records: list[tuple[float, int, Path]] = []
        total_bytes = 0
        for file_path in files:
            try:
                stat = file_path.stat()
            except OSError:
                continue
            size = int(stat.st_size)
            total_bytes += size
            records.append((float(stat.st_mtime), size, file_path))
        records.sort(key=lambda item: item[0])
        while records and (len(records) > max_entries or total_bytes > max_bytes):
            _mtime, size, file_path = records.pop(0)
            try:
                file_path.unlink()
                total_bytes -= size
            except OSError:
                pass

    def _prune_thumbnail_cache(self) -> None:
        overflow = len(self._image_thumb_cache) - THUMBNAIL_CACHE_MAX_ENTRIES
        if overflow <= 0:
            return
        for key in list(self._image_thumb_cache.keys())[:overflow]:
            self._image_thumb_cache.pop(key, None)

    def _set_item_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> None:
        key = self._normalized_path_key(path)
        item = self._file_items_by_key.get(key)
        if item is not None and self.file_list.row(item) >= 0:
            item.setIcon(self._display_icon_for_path(path, icon))
            return
        self._file_items_by_key.pop(key, None)

    def _refresh_color_reference_thumbnail_markers(self) -> None:
        if not hasattr(self, "file_list"):
            return
        icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if not raw_path:
                continue
            path = Path(str(raw_path))
            icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
            if icon is None:
                icon = self._icon_for_file(path)
            item.setToolTip(self._file_item_tooltip(path))
            item.setIcon(self._display_icon_for_path(path, icon))

    def _display_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> QtGui.QIcon:
        adjustment_profile_type = self._raw_adjustment_profile_type(path)
        if not adjustment_profile_type:
            return icon
        size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
        return self._icon_with_thumbnail_markers(
            icon,
            size=size,
            adjustment_profile_type=adjustment_profile_type,
        )

    def _file_item_tooltip(self, path: Path) -> str:
        lines = [str(path)]
        summary = self._raw_sidecar_development_summary(path)
        if summary:
            lines.append(summary)
        if self._is_color_reference_file(path):
            lines.append("Referencia colorimétrica seleccionada")
        return "\n".join(lines)

    def _is_color_reference_file(self, path: Path) -> bool:
        key = self._normalized_path_key(path)
        return key in {self._normalized_path_key(p) for p in self._selected_chart_files}

    @staticmethod
    def _normalized_path_key(path: Path) -> str:
        try:
            return str(path.expanduser().resolve(strict=False)).lower()
        except Exception:
            return str(path).lower()

    def _icon_with_color_reference_marker(self, icon: QtGui.QIcon, *, size: int) -> QtGui.QIcon:
        return self._icon_with_thumbnail_markers(icon, size=size, adjustment_profile_type="advanced")

    def _icon_with_thumbnail_markers(
        self,
        icon: QtGui.QIcon,
        *,
        size: int,
        adjustment_profile_type: str,
    ) -> QtGui.QIcon:
        pixmap = icon.pixmap(QtCore.QSize(size, size))
        if pixmap.isNull():
            return icon
        marked = QtGui.QPixmap(pixmap)
        painter = QtGui.QPainter(marked)
        marker_h = max(3, int(round(marked.height() * 0.045)))
        marker_color = "#38bdf8" if adjustment_profile_type == "advanced" else "#22c55e"
        painter.fillRect(0, marked.height() - marker_h, marked.width(), marker_h, QtGui.QColor(marker_color))
        painter.end()
        return QtGui.QIcon(marked)

    def _thumbnail_cache_key(self, path: Path, size: int | None = None) -> str:
        try:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "nostat"
        return f"{self._cache_path_identity(path)}|{stamp}|thumb-v4"

    def _cache_path_identity(self, path: Path) -> str:
        try:
            resolved = path.expanduser().resolve(strict=False)
        except Exception:
            resolved = path
        if self._active_session_root is not None:
            try:
                root = self._active_session_root.expanduser().resolve(strict=False)
                relative = resolved.relative_to(root)
                return f"session:{relative.as_posix()}"
            except Exception:
                pass
        return str(resolved)

    def _legacy_project_path_candidate(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        roots: list[Path] = []
        if self._active_session_root is not None:
            roots.append(self._active_session_root)
        for parent in candidate.parents:
            if (parent / "00_configuraciones").is_dir() or (parent / "01_ORG").is_dir() or (parent / "02_DRV").is_dir():
                roots.append(parent)
                break

        seen: set[str] = set()
        for root in roots:
            try:
                root = root.expanduser().resolve(strict=False)
                rel = candidate.resolve(strict=False).relative_to(root)
            except Exception:
                continue
            if not rel.parts:
                continue
            replacement = LEGACY_PROJECT_DIR_RENAMES.get(rel.parts[0])
            if replacement is None:
                continue
            mapped = root / replacement
            if len(rel.parts) > 1:
                mapped = mapped.joinpath(*rel.parts[1:])
            key = str(mapped)
            if key in seen:
                continue
            seen.add(key)
            if mapped.exists():
                return mapped
        return None

    def _project_root_for_path(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        search = [candidate, *candidate.parents]
        for parent in search:
            if (
                (parent / "00_configuraciones").is_dir()
                and (parent / "01_ORG").is_dir()
                and (parent / "02_DRV").is_dir()
            ):
                try:
                    return parent.resolve()
                except Exception:
                    return parent
        return None

    def _preferred_browsing_directory(self, folder: Path) -> Path:
        project_root = self._project_root_for_path(folder)
        if project_root is not None:
            org_dir = project_root / "01_ORG"
            if folder == project_root and org_dir.is_dir():
                return org_dir.resolve()
        return folder

    def _resolve_existing_directory(self, folder: Path) -> Path | None:
        candidate = Path(folder).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
        mapped = self._legacy_project_path_candidate(candidate)
        if mapped is not None and mapped.exists() and mapped.is_dir():
            return mapped.resolve()
        return None

    def _resolve_existing_browsable_path(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in BROWSABLE_EXTENSIONS:
            return candidate.resolve()
        mapped = self._legacy_project_path_candidate(candidate)
        if mapped is not None and mapped.exists() and mapped.is_file() and mapped.suffix.lower() in BROWSABLE_EXTENSIONS:
            return mapped.resolve()
        return None

    def _update_file_item_path(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
        old_raw_path = item.data(QtCore.Qt.UserRole)
        if old_raw_path:
            self._file_items_by_key.pop(self._normalized_path_key(Path(str(old_raw_path))), None)
        item.setData(QtCore.Qt.UserRole, str(path))
        item.setToolTip(self._file_item_tooltip(path))
        self._file_items_by_key[self._normalized_path_key(path)] = item
        icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
        if icon is None:
            icon = self._icon_for_file(path)
        item.setIcon(self._display_icon_for_path(path, icon))

    def _remove_stale_file_item(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
        self._file_items_by_key.pop(self._normalized_path_key(path), None)
        row = self.file_list.row(item)
        if row >= 0:
            self.file_list.takeItem(row)
        self._selected_file = None
        self._clear_manual_chart_points_for_file_change()
        self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
        self._selection_load_timer.stop()
        self._metadata_timer.stop()
        self._clear_metadata_view()
        self._set_status(self.tr("Archivo no encontrado, miniatura retirada:") + f" {path.name}")

    @staticmethod
    def _build_thumbnail_payloads(paths: list[Path], size: int) -> list[tuple[str, str, np.ndarray]]:
        return BrowserMetadataMixin._build_thumbnail_payloads_for_keys(
            [(path, BrowserMetadataMixin._thumbnail_cache_key_for_path(path, size)) for path in paths],
            size,
        )

    @staticmethod
    def _build_thumbnail_payloads_for_keys(
        items: list[tuple[Path, str]], size: int
    ) -> list[tuple[str, str, np.ndarray]]:
        payloads: list[tuple[str, str, np.ndarray]] = []
        for path, key in items:
            try:
                rgb_u8 = BrowserMetadataMixin._thumbnail_array_for_path(path, MAX_THUMBNAIL_SIZE)
            except Exception:
                continue
            if rgb_u8 is None:
                continue
            payloads.append((str(path), key, rgb_u8))
        return payloads

    @staticmethod
    def _thumbnail_cache_key_for_path(path: Path, size: int | None = None) -> str:
        try:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "nostat"
        try:
            identity = str(path.expanduser().resolve(strict=False))
        except Exception:
            identity = str(path)
        return f"{identity}|{stamp}|thumb-v4"

    @staticmethod
    def _thumbnail_array_for_path(path: Path, size: int) -> np.ndarray | None:
        suffix = path.suffix.lower()
        if suffix in RAW_EXTENSIONS:
            image = extract_embedded_preview(path)
            if image is not None:
                return BrowserMetadataMixin._thumbnail_u8(linear_to_srgb_display(image), size)
            image = BrowserMetadataMixin._raw_thumbnail_fallback(path)
            if image is not None:
                return BrowserMetadataMixin._thumbnail_u8(linear_to_srgb_display(image), size)
            return None

        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                if "A" in img.getbands():
                    rgba = img.convert("RGBA")
                    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    base.alpha_composite(rgba)
                    img = base.convert("RGB")
                else:
                    img = img.convert("RGB")
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                return np.asarray(img, dtype=np.uint8).copy()
        except Exception:
            image = read_image(path)
            return BrowserMetadataMixin._thumbnail_u8(linear_to_srgb_display(image), size)

    @staticmethod
    def _raw_thumbnail_fallback(path: Path) -> np.ndarray | None:
        recipe = Recipe(
            demosaic_algorithm="linear",
            white_balance_mode="camera_metadata",
            output_space="scene_linear_camera_rgb",
            output_linear=True,
            tone_curve="linear",
            profiling_mode=False,
        )
        try:
            image = develop_image_array(path, recipe, half_size=True)
        except Exception:
            return None
        image = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
        if image.ndim != 3 or image.shape[2] < 3:
            return None
        return BrowserMetadataMixin._neutralize_camera_rgb_thumbnail(image[..., :3])

    @staticmethod
    def _neutralize_camera_rgb_thumbnail(image: np.ndarray) -> np.ndarray:
        rgb = np.clip(np.asarray(image, dtype=np.float32), 0.0, 1.0)
        means = np.mean(rgb, axis=(0, 1), dtype=np.float64)
        if not np.all(np.isfinite(means)) or float(np.min(means)) <= 1e-6:
            return rgb
        if float(np.max(means) / np.min(means)) < 1.35:
            return rgb
        target = float(np.median(means))
        gains = np.clip(target / means, 0.35, 2.8).astype(np.float32)
        balanced = rgb * gains.reshape((1, 1, 3))
        return np.clip(balanced, 0.0, 1.0).astype(np.float32)

    @staticmethod
    def _thumbnail_u8(image_rgb: np.ndarray, size: int) -> np.ndarray:
        rgb = np.asarray(image_rgb)
        if rgb.ndim == 2:
            rgb = np.repeat(rgb[..., None], 3, axis=2)
        if rgb.shape[-1] > 3:
            rgb = rgb[..., :3]
        if np.issubdtype(rgb.dtype, np.integer):
            maxv = float(np.iinfo(rgb.dtype).max)
            rgb_f = np.clip(rgb.astype(np.float32) / maxv, 0.0, 1.0)
        else:
            rgb_f = np.clip(rgb.astype(np.float32), 0.0, 1.0)

        h, w = int(rgb_f.shape[0]), int(rgb_f.shape[1])
        if h <= 0 or w <= 0:
            return np.zeros((1, 1, 3), dtype=np.uint8)
        scale = min(float(size) / float(max(w, h)), 1.0)
        if scale < 1.0:
            nw = max(1, int(round(w * scale)))
            nh = max(1, int(round(h * scale)))
            rgb_f = cv2.resize(rgb_f, (nw, nh), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(np.clip(np.round(rgb_f * 255.0), 0, 255).astype(np.uint8))

    def _icon_from_thumbnail_array(
        self,
        rgb_u8: np.ndarray,
        *,
        target_size: QtCore.QSize | None = None,
    ) -> QtGui.QIcon:
        rgb_u8 = self._thumbnail_u8_for_screen(rgb_u8)
        if target_size is not None:
            target_w = max(1, int(target_size.width()))
            target_h = max(1, int(target_size.height()))
            src_h, src_w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
            if src_h > 0 and src_w > 0:
                src_aspect = float(src_w) / float(src_h)
                target_aspect = float(target_w) / float(target_h)
                if src_aspect > target_aspect:
                    crop_w = max(1, int(round(src_h * target_aspect)))
                    x0 = max(0, (src_w - crop_w) // 2)
                    rgb_u8 = rgb_u8[:, x0 : x0 + crop_w]
                else:
                    crop_h = max(1, int(round(src_w / target_aspect)))
                    y0 = max(0, (src_h - crop_h) // 2)
                    rgb_u8 = rgb_u8[y0 : y0 + crop_h, :]
            interpolation = (
                cv2.INTER_AREA
                if int(rgb_u8.shape[1]) >= target_w and int(rgb_u8.shape[0]) >= target_h
                else cv2.INTER_LINEAR
            )
            rgb_u8 = cv2.resize(rgb_u8, (target_w, target_h), interpolation=interpolation)
        rgb_u8 = np.ascontiguousarray(rgb_u8.astype(np.uint8))
        h, w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
        qimg = QtGui.QImage(rgb_u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
        return QtGui.QIcon(QtGui.QPixmap.fromImage(qimg))

    def _icon_for_file(self, path: Path) -> QtGui.QIcon:
        suffix = path.suffix.lower()
        key = "raw" if suffix in RAW_EXTENSIONS else "image"
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached

        icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        self._thumb_cache[key] = icon
        return icon

    def _on_file_selection_changed(self) -> None:
        item = self.file_list.currentItem()
        if item is None:
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            return
        raw_path = item.data(QtCore.Qt.UserRole)
        if not raw_path:
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            return
        stale_path = Path(str(raw_path))
        selected = self._resolve_existing_browsable_path(stale_path)
        if selected is None:
            self._remove_stale_file_item(item, stale_path)
            return
        if self._normalized_path_key(selected) != self._normalized_path_key(stale_path):
            self._update_file_item_path(item, selected)
        if self._selected_file is None or self._normalized_path_key(self._selected_file) != self._normalized_path_key(selected):
            self._clear_manual_chart_points_for_file_change()
        self._selected_file = selected
        self.selected_file_label.setText(str(self._selected_file))
        self._apply_raw_sidecar_to_controls(self._selected_file)
        self._queue_metadata_load(self._selected_file, include_c2pa=False)
        if self._selected_file.suffix.lower() in BROWSABLE_EXTENSIONS:
            self._set_status(self.tr("Seleccionado:") + f" {self._selected_file.name}. " + self.tr("Cargando preview..."))
            self._selection_load_timer.start(250)

    def _on_file_double_clicked(self, _item) -> None:
        self._selection_load_timer.stop()
        self._on_load_selected()

    def _show_file_list_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.file_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.file_list.clearSelection()
            item.setSelected(True)
            self.file_list.setCurrentItem(item)

        menu = QtWidgets.QMenu(self)
        menu.addAction(self.tr("Guardar perfil básico en imagen"), self._save_current_development_settings_to_selected)
        menu.addAction(self.tr("Copiar perfil de ajuste"), self._copy_development_settings_from_selected)
        paste_action = menu.addAction(self.tr("Pegar perfil de ajuste"), self._paste_development_settings_to_selected)
        paste_action.setEnabled(self._development_settings_clipboard is not None)
        menu.addSeparator()
        menu.addAction(self.tr("Usar como referencia colorimétrica"), self._use_selected_files_as_profile_charts)
        menu.addAction(self.tr("Anadir a cola"), self._queue_add_selected)
        menu.exec(self.file_list.mapToGlobal(pos))

    def _queue_metadata_load(self, path: Path, *, delay_ms: int = 180, include_c2pa: bool = True) -> None:
        self._metadata_generation += 1
        self._queued_metadata_include_c2pa = bool(include_c2pa)
        if hasattr(self, "metadata_file_label"):
            self.metadata_file_label.setText(self.tr("Metadatos:") + f" {path.name}")
        if hasattr(self, "metadata_summary"):
            self._metadata_tree_message(self.metadata_summary, self.tr("Leyendo metadatos..."))
        self._metadata_timer.start(max(0, int(delay_ms)))

    def _load_metadata_from_timer(self) -> None:
        self._refresh_metadata_view(include_c2pa=self._queued_metadata_include_c2pa)

    def _refresh_metadata_view(self, _checked: bool = False, *, include_c2pa: bool = True) -> None:
        if self._selected_file is None:
            self._clear_metadata_view()
            return
        selected = self._selected_file
        if hasattr(self, "metadata_file_label"):
            self.metadata_file_label.setText(self.tr("Metadatos:") + f" {selected}")
        if hasattr(self, "metadata_summary"):
            self._metadata_tree_message(self.metadata_summary, self.tr("Leyendo metadatos..."))
        if self._metadata_task_active:
            self._metadata_pending_request = (selected, bool(include_c2pa))
            return
        self._start_metadata_refresh_task(selected, bool(include_c2pa))

    def _start_metadata_refresh_task(self, selected: Path, include_c2pa: bool) -> None:
        self._metadata_generation += 1
        generation = self._metadata_generation

        def task():
            return generation, selected, inspect_file_metadata(selected, include_c2pa=include_c2pa)

        thread = TaskThread(task)
        self._metadata_task_active = True
        self._threads.append(thread)

        def cleanup() -> None:
            self._metadata_task_active = False
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = self._metadata_pending_request
            self._metadata_pending_request = None
            if pending is not None:
                _pending_path, pending_c2pa = pending
                if self._selected_file is not None:
                    self._start_metadata_refresh_task(self._selected_file, pending_c2pa)

        def ok(payload) -> None:
            try:
                payload_generation, payload_path, metadata = payload
                if payload_generation != self._metadata_generation or self._selected_file != payload_path:
                    return
                self._apply_metadata_payload(payload_path, metadata)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                if self._selected_file == selected:
                    msg = trace.strip().splitlines()[-1] if trace.strip() else "No se pudieron leer metadatos"
                    self._metadata_tree_message(self.metadata_summary, msg)
                    self.metadata_exif.clear()
                    self.metadata_gps.clear()
                    self.metadata_c2pa.clear()
                    self.metadata_all.setPlainText(trace[-4000:])
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _apply_metadata_payload(self, path: Path, payload: dict[str, Any]) -> None:
        sections = metadata_sections_text(payload)
        display = metadata_display_sections(payload)
        self.metadata_file_label.setText(self.tr("Metadatos:") + f" {path}")
        self._populate_metadata_tree(self.metadata_summary, display["summary"])
        self._populate_metadata_tree(self.metadata_exif, display["exif"])
        self._populate_metadata_tree(self.metadata_gps, display["gps"])
        self._populate_metadata_tree(self.metadata_c2pa, display["c2pa"])
        self.metadata_all.setPlainText(sections["all"])

    def _clear_metadata_view(self) -> None:
        if not hasattr(self, "metadata_summary"):
            return
        self.metadata_file_label.setText(self.tr("Sin archivo seleccionado"))
        for widget in (
            self.metadata_summary,
            self.metadata_exif,
            self.metadata_gps,
            self.metadata_c2pa,
        ):
            widget.clear()
        self.metadata_all.clear()

    def _show_metadata_all_tab(self) -> None:
        if hasattr(self, "metadata_tabs"):
            self.metadata_tabs.setCurrentWidget(self.metadata_all)

    def _metadata_tree_message(self, tree: QtWidgets.QTreeWidget, message: str) -> None:
        tree.clear()
        item = QtWidgets.QTreeWidgetItem([str(message), ""])
        tree.addTopLevelItem(item)

    def _populate_metadata_tree(self, tree: QtWidgets.QTreeWidget, groups: Any) -> None:
        tree.clear()
        if not groups:
            self._metadata_tree_message(tree, "Sin datos")
            return
        if isinstance(groups, list):
            for group in groups:
                self._add_metadata_group(tree, group)
        elif isinstance(groups, dict):
            self._add_metadata_dict(tree, None, groups)
        else:
            self._metadata_tree_message(tree, str(groups))
        tree.expandToDepth(0)

    def _add_metadata_group(self, tree: QtWidgets.QTreeWidget, group: dict[str, Any]) -> None:
        title = str(group.get("title") or "Metadatos")
        parent = QtWidgets.QTreeWidgetItem([title, ""])
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        parent.setFirstColumnSpanned(False)
        tree.addTopLevelItem(parent)
        for item in group.get("items") or []:
            if isinstance(item, dict):
                child = QtWidgets.QTreeWidgetItem([str(item.get("label", "")), str(item.get("value", ""))])
                child.setToolTip(1, str(item.get("value", "")))
                parent.addChild(child)

    def _add_metadata_dict(self, tree: QtWidgets.QTreeWidget, parent: QtWidgets.QTreeWidgetItem | None, payload: dict[str, Any]) -> None:
        for key, value in sorted(payload.items()):
            if isinstance(value, dict):
                node = QtWidgets.QTreeWidgetItem([str(key), ""])
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
                self._add_metadata_dict(tree, node, value)
            elif isinstance(value, list):
                node = QtWidgets.QTreeWidgetItem([str(key), f"{len(value)} elementos"])
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
                for idx, item in enumerate(value):
                    child = QtWidgets.QTreeWidgetItem([str(idx + 1), json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)])
                    node.addChild(child)
            else:
                node = QtWidgets.QTreeWidgetItem([str(key), str(value)])
                node.setToolTip(1, str(value))
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
