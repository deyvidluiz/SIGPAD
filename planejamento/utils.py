from datetime import timedelta

from django.utils import timezone

from .models import Alerta, ConteudoProgramatico


def verificar_alertas_conteudos(usuario=None):
    hoje = timezone.localdate()
    amanha = hoje + timedelta(days=1)
    conteudos = ConteudoProgramatico.objects.select_related('disciplina')
    if getattr(usuario, 'is_authenticated', False):
        conteudos = conteudos.filter(disciplina__professor=usuario)

    for conteudo in conteudos:
        conteudo.atualizar_status()

        if conteudo.concluido:
            continue

        if conteudo.data_inicio and conteudo.data_inicio == amanha:
            Alerta.objects.get_or_create(
                usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
                turma=conteudo.disciplina.turma,
                conteudo=conteudo,
                tipo='INICIO',
                defaults={
                    'titulo': 'Conteudo inicia amanha',
                    'mensagem': f'O conteudo "{conteudo.titulo}" inicia amanha na turma {conteudo.disciplina.turma.nome}.',
                    'prioridade': 'media',
                },
            )
        elif conteudo.data_inicio and conteudo.data_inicio <= hoje:
            Alerta.objects.get_or_create(
                usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
                turma=conteudo.disciplina.turma,
                conteudo=conteudo,
                tipo='INICIO',
                defaults={
                    'titulo': 'Conteudo iniciado',
                    'mensagem': f'O conteudo "{conteudo.titulo}" ja chegou na data de inicio.',
                    'prioridade': 'media',
                },
            )

        if conteudo.data_fim and conteudo.data_fim < hoje:
            Alerta.objects.get_or_create(
                usuario=usuario if getattr(usuario, 'is_authenticated', False) else None,
                turma=conteudo.disciplina.turma,
                conteudo=conteudo,
                tipo='ATRASO',
                defaults={
                    'titulo': 'Conteudo atrasado',
                    'mensagem': f'O conteudo "{conteudo.titulo}" passou da data final e ainda nao foi concluido.',
                    'prioridade': 'alta',
                },
            )

def alertas_gerais_usuario(usuario, limite=5):
    if not getattr(usuario, 'is_authenticated', False):
        return []

    alertas = (
        Alerta.objects.filter(usuario=usuario, lido=False)
        .select_related('turma')
        .order_by('turma__nome', 'tipo')
    )
    resumo = {}
    for alerta in alertas:
        turma_id = alerta.turma_id or 0
        chave = (turma_id, alerta.tipo)
        if chave not in resumo:
            turma_nome = alerta.turma.nome if alerta.turma else 'Geral'
            resumo[chave] = {
                'turma': alerta.turma,
                'tipo': alerta.tipo,
                'titulo': _titulo_alerta_geral(turma_nome, alerta.tipo),
                'quantidade': 0,
                'badge': alerta.get_badge_class(),
                'icone': alerta.get_icon_class(),
            }
        resumo[chave]['quantidade'] += 1

    alertas_resumidos = list(resumo.values())
    return alertas_resumidos[:limite] if limite else alertas_resumidos


def _titulo_alerta_geral(turma_nome, tipo):
    titulos = {
        'ATRASO': f'Turma {turma_nome} possui atividade atrasada.',
        'INICIO': f'Turma {turma_nome} possui atividade iniciando em breve.',
        'SISTEMA': f'Turma {turma_nome} possui alerta pendente.',
    }
    return titulos.get(tipo, f'Turma {turma_nome} possui alerta.')
