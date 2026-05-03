from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewCacheMixin:
    def _preview_recipe_signature(self, recipe: Recipe) -> str:
        wb = ",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers)
        return "|".join(
            [
                recipe.raw_developer,
                recipe.demosaic_algorithm,
                recipe.white_balance_mode,
                recipe.black_level_mode,
                recipe.tone_curve,
                f"{float(recipe.exposure_compensation):.3g}",
                recipe.output_space,
                str(bool(recipe.profiling_mode)),
                wb,
            ]
        )

    def _preview_base_signature(
        self,
        *,
        selected: Path,
        recipe: Recipe,
    ) -> str:
        try:
            st = selected.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            stamp = "nostat"
        recipe_sig = self._preview_recipe_signature(recipe)
        return f"{self._cache_path_identity(selected)}|{stamp}|preview-v4|{recipe_sig}"

    def _preview_cache_key(
        self,
        *,
        selected: Path,
        recipe: Recipe,
        fast_raw: bool,
        max_preview_side: int,
    ) -> str:
        base_sig = self._preview_base_signature(
            selected=selected,
            recipe=recipe,
        )
        fast_token = int(bool(fast_raw))
        return f"{base_sig}|{fast_token}|fr={fast_token}|ms={int(max_preview_side)}"

    @staticmethod
    def _run_preview_load_inline() -> bool:
        # Tests expect deterministic preview loading without waiting for Qt threads.
        return bool(
            os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("PROBRAW_SYNC_PREVIEW_LOAD")
        )

    def _cache_preview_memory(self, key: str, image: np.ndarray) -> None:
        if key in self._preview_cache:
            self._preview_cache.pop(key, None)
            self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
        self._preview_cache[key] = image.copy()
        self._preview_cache_order.append(key)
        while (
            len(self._preview_cache_order) > PREVIEW_CACHE_MAX_ENTRIES
            or self._preview_cache_bytes() > PREVIEW_CACHE_MAX_BYTES
        ):
            old = self._preview_cache_order.pop(0)
            self._preview_cache.pop(old, None)

    def _cache_preview_image(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
        self._cache_preview_memory(key, image)
        self._write_preview_to_disk_cache(key, image, selected=selected)

    def _cached_preview_image(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
        image = self._preview_cache.get(key)
        if image is not None:
            self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
            self._preview_cache_order.append(key)
            return image
        image = self._read_preview_from_disk_cache(key, selected=selected)
        if image is not None:
            self._cache_preview_memory(key, image)
            return image
        self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
        return None

    def _preview_disk_cache_dir(self, selected: Path | None = None) -> Path:
        return self._disk_cache_dirs(selected, "previews")[0]

    def _preview_disk_cache_path(self, key: str, *, base_dir: Path | None = None, selected: Path | None = None) -> Path:
        return self._disk_cache_path(base_dir or self._preview_disk_cache_dir(selected), key, ".npy")

    def _read_preview_from_disk_cache(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
        for cache_dir in self._disk_cache_dirs(selected, "previews"):
            cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
            if not cache_path.is_file():
                continue
            try:
                with cache_path.open("rb") as handle:
                    image = np.load(handle, allow_pickle=False)
                image = np.asarray(image, dtype=np.float32)
                if image.ndim != 3 or image.shape[-1] < 3:
                    continue
                try:
                    os.utime(cache_path, None)
                except Exception:
                    pass
                return np.ascontiguousarray(image[..., :3])
            except Exception:
                continue
        return None

    def _write_preview_to_disk_cache(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
        try:
            cache_dir = self._preview_disk_cache_dir(selected)
            cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_name(f"{cache_path.name}.tmp")
            array = np.ascontiguousarray(np.asarray(image, dtype=np.float32)[..., :3])
            with tmp_path.open("wb") as handle:
                np.save(handle, array, allow_pickle=False)
            os.replace(tmp_path, cache_path)
            self._prune_disk_cache(
                cache_dir,
                pattern="*.npy",
                max_entries=PREVIEW_DISK_CACHE_MAX_ENTRIES,
                max_bytes=PREVIEW_DISK_CACHE_MAX_BYTES,
            )
        except Exception:
            return

    def _preview_cache_bytes(self) -> int:
        return int(sum(int(image.nbytes) for image in self._preview_cache.values()))

    def _invalidate_preview_cache(self) -> None:
        self._preview_cache.clear()
        self._preview_cache_order.clear()
        self._last_loaded_preview_key = None
        self._loaded_preview_base_signature = None
        self._loaded_preview_fast_raw = None
        self._loaded_preview_source_max_side = 0
        self._loaded_preview_max_side_request = None
        self._tone_curve_histogram_key = None
        self._preview_load_pending_request = None
        self._profile_preview_pending_request = None
        self._profile_preview_expected_key = None
        self._profile_preview_error_key = None
        self._interactive_preview_pending_request = None
        self._interactive_preview_expected_key = None
        self._interactive_preview_request_seq = 0
        self._profile_preview_cache.clear()
        self._profile_preview_cache_order.clear()
        self._clear_adjustment_caches()
        if hasattr(self, "_clear_mtf_image_caches"):
            self._clear_mtf_image_caches()
        self._set_interactive_preview_busy(False)
