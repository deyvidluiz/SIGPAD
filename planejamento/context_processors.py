from .models import Alerta, PerfilUsuario
from .utils import alertas_gerais_usuario


def perfil_usuario_logado(request):
    if not request.user.is_authenticated:
        return {'perfil_usuario_logado': None}

    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    alertas = Alerta.objects.filter(usuario=request.user, lido=False)
    return {
        'perfil_usuario_logado': perfil,
        'alertas_nao_lidos_navbar': alertas.count(),
        'alertas_navbar': alertas_gerais_usuario(request.user),
    }
