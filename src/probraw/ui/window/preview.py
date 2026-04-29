from __future__ import annotations

from .preview_menu import PreviewMenuMixin
from .preview_recipe import PreviewRecipeMixin
from .preview_cache import PreviewCacheMixin
from .preview_load import PreviewLoadMixin
from .preview_render import PreviewRenderMixin
from .preview_export import PreviewExportMixin


class PreviewWorkflowMixin(
    PreviewMenuMixin,
    PreviewRecipeMixin,
    PreviewCacheMixin,
    PreviewLoadMixin,
    PreviewRenderMixin,
    PreviewExportMixin,
):
    pass
