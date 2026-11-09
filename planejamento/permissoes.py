"""Controle de acesso da area administrativa do SIGPAD (/painel/).

Um usuario e administrador do SIGPAD quando esta ativo e:
  * e superusuario do Django; ou
  * pertence ao grupo "Administradores SIGPAD".

Isso e independente do Django Admin (/admin/), que continua exigindo is_staff.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

GRUPO_ADMIN = 'Administradores SIGPAD'


def is_admin_sigpad(usuario):
    if not getattr(usuario, 'is_authenticated', False) or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True
    cache = getattr(usuario, '_is_admin_sigpad_cache', None)
    if cache is None:
        cache = usuario.groups.filter(name=GRUPO_ADMIN).exists()
        usuario._is_admin_sigpad_cache = cache
    return cache


def admin_required(view):
    """Exige login; usuarios autenticados sem papel de administrador recebem 403."""

    @login_required
    @wraps(view)
    def _view(request, *args, **kwargs):
        if not is_admin_sigpad(request.user):
            raise PermissionDenied('Acesso restrito aos administradores do SIGPAD.')
        return view(request, *args, **kwargs)

    return _view
