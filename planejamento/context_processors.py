from .models import Alerta, PerfilUsuario
from .permissoes import is_admin_sigpad
from .utils import alertas_gerais_usuario


def perfil_usuario_logado(request):
    if not request.user.is_authenticated:
        return {'perfil_usuario_logado': None, 'is_admin_sigpad': False}

    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    alertas = Alerta.objects.filter(usuario=request.user, lido=False)
    return {
        'perfil_usuario_logado': perfil,
        'alertas_nao_lidos_navbar': alertas.count(),
        'alertas_navbar': alertas_gerais_usuario(request.user),
        'is_admin_sigpad': is_admin_sigpad(request.user),
    }
