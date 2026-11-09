"""Area administrativa do SIGPAD (/painel/).

Todas as views exigem o papel de administrador (ver permissoes.py). Nada e
excluido por aqui: usuarios sao desativados e turmas/disciplinas so editadas.
"""

from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms_painel import DisciplinaPainelForm, TurmaPainelForm, UsuarioCriarForm, UsuarioEditarForm
from .indicadores import consolidar, indicadores_por_turma
from .models import (
    PERIODO_CHOICES,
    Alerta,
    Aluno,
    Aula,
    ConteudoProgramatico,
    Disciplina,
    ProcessoAvaliativo,
    Turma,
)
from .permissoes import GRUPO_ADMIN, admin_required, is_admin_sigpad

ITENS_POR_PAGINA = 20


# ---------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------
def _int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _paginar(request, queryset):
    pagina = Paginator(queryset, ITENS_POR_PAGINA).get_page(request.GET.get('page'))
    parametros = request.GET.copy()
    parametros.pop('page', None)
    return pagina, parametros.urlencode()


def _distribuicao(contagem, rotulos, classes):
    """Converte {status: quantidade} em linhas de grafico de barras."""
    total = sum(contagem.values())
    linhas = []
    for chave, rotulo in rotulos:
        quantidade = contagem.get(chave, 0)
        linhas.append({
            'rotulo': rotulo,
            'quantidade': quantidade,
            'percentual': round(quantidade * 100 / total) if total else 0,
            'classe': classes.get(chave, 'bg-secondary'),
        })
    return linhas, total


def _anos_letivos():
    return list(Turma.objects.order_by('-ano_letivo').values_list('ano_letivo', flat=True).distinct())


def _filtros_academicos(request):
    return {
        'ano': _int(request.GET.get('ano')),
        'professor': _int(request.GET.get('professor')),
        'turma': _int(request.GET.get('turma')),
        'disciplina': _int(request.GET.get('disciplina')),
        'periodo': request.GET.get('periodo') if request.GET.get('periodo') in dict(PERIODO_CHOICES) else '',
        'status': request.GET.get('status') or '',
        'q': (request.GET.get('q') or '').strip(),
    }


def _opcoes_filtro(filtros):
    turmas = Turma.objects.select_related('professor').order_by('-ano_letivo', 'nome')
    disciplinas = Disciplina.objects.select_related('turma').order_by('turma__nome', 'nome')
    if filtros.get('ano'):
        turmas = turmas.filter(ano_letivo=filtros['ano'])
        disciplinas = disciplinas.filter(turma__ano_letivo=filtros['ano'])
    if filtros.get('turma'):
        disciplinas = disciplinas.filter(turma_id=filtros['turma'])
    return {
        'anos': _anos_letivos(),
        'professores': User.objects.filter(turma__isnull=False).distinct().order_by('first_name', 'username'),
        'turmas_filtro': turmas,
        'disciplinas_filtro': disciplinas,
        'periodos': PERIODO_CHOICES,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_required
def painel_dashboard(request):
    ano = _int(request.GET.get('ano'))
    turmas = Turma.objects.select_related('professor').order_by('-ano_letivo', 'nome')
    if ano:
        turmas = turmas.filter(ano_letivo=ano)
    disciplinas = Disciplina.objects.filter(turma__in=turmas)
    atividades = ProcessoAvaliativo.objects.filter(turma__in=turmas)
    conteudos = ConteudoProgramatico.objects.filter(disciplina__in=disciplinas)

    for atividade in atividades.exclude(status__in=['CORRIGIDA', 'FINALIZADA']):
        atividade.atualizar_status_automatico()  # mesmo comportamento das telas do professor

    usuarios = User.objects.all()
    admins = usuarios.filter(Q(is_superuser=True) | Q(groups__name=GRUPO_ADMIN)).distinct()
    professores = usuarios.filter(is_active=True).exclude(pk__in=admins.values('pk'))

    indicadores = indicadores_por_turma(list(turmas))
    resumo = consolidar(indicadores)

    status_atividades, total_atividades = _distribuicao(
        dict(atividades.values_list('status').annotate(total=Count('id'))),
        ProcessoAvaliativo.STATUS_CHOICES,
        {'A_REALIZAR': 'bg-secondary', 'EM_ANDAMENTO': 'bg-primary', 'CORRIGIDA': 'bg-success', 'FINALIZADA': 'bg-info'},
    )
    status_conteudos, total_conteudos = _distribuicao(
        dict(conteudos.values_list('status').annotate(total=Count('id'))),
        ConteudoProgramatico.STATUS_CHOICES,
        {'PENDENTE': 'bg-secondary', 'EM_ANDAMENTO': 'bg-primary', 'CONCLUIDO': 'bg-success', 'ATRASADO': 'bg-danger'},
    )

    turmas_lista = list(turmas.annotate(total_disciplinas=Count('disciplinas', distinct=True)))
    for turma in turmas_lista:
        turma.indicadores = indicadores.get(turma.id, {})

    alertas = Alerta.objects.filter(lido=False)
    if ano:
        alertas = alertas.filter(Q(turma__ano_letivo=ano) | Q(turma__isnull=True))
    alertas_por_tipo, total_alertas = _distribuicao(
        dict(alertas.values_list('tipo').annotate(total=Count('id'))),
        Alerta.TIPO_CHOICES,
        {'INICIO': 'bg-primary', 'ATRASO': 'bg-danger', 'SISTEMA': 'bg-warning'},
    )

    context = {
        'ano': ano,
        'anos': _anos_letivos(),
        'total_professores': professores.count(),
        'professores_inativos': usuarios.filter(is_active=False).count(),
        'total_admins': admins.filter(is_active=True).count(),
        'total_turmas': turmas.count(),
        'total_disciplinas': disciplinas.count(),
        'total_atividades': total_atividades,
        'atividades_pendentes': atividades.filter(status__in=['A_REALIZAR', 'EM_ANDAMENTO']).count(),
        'total_alertas': total_alertas,
        'total_aulas': Aula.objects.filter(turma__in=turmas).aggregate(total=Sum('quantidade_aulas'))['total'] or 0,
        'resumo': resumo,
        'status_atividades': status_atividades,
        'status_conteudos': status_conteudos,
        'total_conteudos': total_conteudos,
        'alertas_por_tipo': alertas_por_tipo,
        'turmas': turmas_lista,
        'alertas_por_professor': (
            alertas.exclude(usuario__isnull=True)
            .values('usuario__id', 'usuario__first_name', 'usuario__last_name', 'usuario__username')
            .annotate(total=Count('id')).order_by('-total')[:6]
        ),
        'ultimos_usuarios': usuarios.order_by('-date_joined')[:5],
    }
    return render(request, 'painel/dashboard.html', context)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def _garantir_pode_editar(editor, usuario):
    if usuario.is_superuser and not editor.is_superuser:
        raise PermissionDenied('Somente superusuarios podem alterar outro superusuario.')


@admin_required
def painel_usuarios(request):
    q = (request.GET.get('q') or '').strip()
    papel = request.GET.get('papel') or ''
    situacao = request.GET.get('situacao') or ''
    usuarios = User.objects.annotate(
        total_turmas=Count('turma', distinct=True),
        total_disciplinas=Count('disciplina', distinct=True),
        is_admin_grupo=Count('groups', filter=Q(groups__name=GRUPO_ADMIN), distinct=True),
    ).order_by('first_name', 'last_name', 'username')
    if q:
        usuarios = usuarios.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    filtro_admin = Q(is_superuser=True) | Q(groups__name=GRUPO_ADMIN)
    if papel == 'admin':
        usuarios = usuarios.filter(filtro_admin).distinct()
    elif papel == 'professor':
        usuarios = usuarios.exclude(pk__in=User.objects.filter(filtro_admin).values('pk'))
    if situacao == 'ativos':
        usuarios = usuarios.filter(is_active=True)
    elif situacao == 'inativos':
        usuarios = usuarios.filter(is_active=False)
    pagina, querystring = _paginar(request, usuarios)
    return render(request, 'painel/usuarios_lista.html', {
        'pagina': pagina, 'querystring': querystring, 'q': q, 'papel': papel, 'situacao': situacao,
    })


@admin_required
def painel_usuario_criar(request):
    form = UsuarioCriarForm(request.POST or None, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            usuario = form.save()
        messages.success(request, f'Usuario {usuario.username} cadastrado com sucesso.')
        return redirect('painel_usuario_detalhes', id=usuario.id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': 'Novo usuario', 'voltar': 'painel_usuarios', 'icone': 'bi-person-plus',
    })


@admin_required
def painel_usuario_detalhes(request, id):
    usuario = get_object_or_404(User.objects.select_related('perfilusuario'), id=id)
    turmas = list(
        Turma.objects.filter(professor=usuario)
        .annotate(
            total_disciplinas=Count('disciplinas', distinct=True),
            total_alunos=Count('alunos', filter=Q(alunos__ativo=True), distinct=True),
        ).order_by('-ano_letivo', 'nome')
    )
    indicadores = indicadores_por_turma(turmas)
    for turma in turmas:
        turma.indicadores = indicadores.get(turma.id, {})
    disciplinas = Disciplina.objects.filter(professor=usuario).select_related('turma').order_by('turma__nome', 'nome')
    return render(request, 'painel/usuario_detalhes.html', {
        'usuario': usuario,
        'perfil': getattr(usuario, 'perfilusuario', None),
        'is_admin': is_admin_sigpad(usuario),
        'no_grupo_admin': usuario.groups.filter(name=GRUPO_ADMIN).exists(),
        'turmas': turmas,
        'disciplinas': disciplinas,
        'total_atividades': ProcessoAvaliativo.objects.filter(turma__professor=usuario).count(),
        'total_conteudos': ConteudoProgramatico.objects.filter(disciplina__professor=usuario).count(),
        'alertas_nao_lidos': Alerta.objects.filter(usuario=usuario, lido=False).count(),
        'pode_editar': not (usuario.is_superuser and not request.user.is_superuser),
    })


@admin_required
def painel_usuario_editar(request, id):
    usuario = get_object_or_404(User, id=id)
    _garantir_pode_editar(request.user, usuario)
    form = UsuarioEditarForm(request.POST or None, instance=usuario, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, 'Usuario atualizado com sucesso.')
        return redirect('painel_usuario_detalhes', id=usuario.id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': f'Editar usuario: {usuario.username}', 'voltar': 'painel_usuario_detalhes',
        'voltar_id': usuario.id, 'icone': 'bi-person-gear',
    })


@admin_required
@require_POST
def painel_usuario_alternar_ativo(request, id):
    usuario = get_object_or_404(User, id=id)
    _garantir_pode_editar(request.user, usuario)
    if usuario.pk == request.user.pk:
        messages.error(request, 'Voce nao pode desativar a propria conta.')
        return redirect('painel_usuario_detalhes', id=usuario.id)
    if usuario.is_active and is_admin_sigpad(usuario):
        outros = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(groups__name=GRUPO_ADMIN)
        ).exclude(pk=usuario.pk)
        if not outros.exists():
            messages.error(request, 'O SIGPAD precisa manter pelo menos um administrador ativo.')
            return redirect('painel_usuario_detalhes', id=usuario.id)
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    situacao = 'ativada' if usuario.is_active else 'desativada'
    messages.success(request, f'Conta de {usuario.username} {situacao}. Os registros academicos foram preservados.')
    return redirect(request.POST.get('next') or 'painel_usuarios')


@admin_required
def painel_usuario_senha(request, id):
    usuario = get_object_or_404(User, id=id)
    _garantir_pode_editar(request.user, usuario)
    form = SetPasswordForm(usuario, request.POST or None)
    for field in form.fields.values():
        field.widget.attrs.update({'class': 'form-control'})
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Senha de {usuario.username} redefinida.')
        return redirect('painel_usuario_detalhes', id=usuario.id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': f'Redefinir senha: {usuario.username}', 'voltar': 'painel_usuario_detalhes',
        'voltar_id': usuario.id, 'icone': 'bi-key',
    })


# ---------------------------------------------------------------------------
# Turmas
# ---------------------------------------------------------------------------
@admin_required
def painel_turmas(request):
    filtros = _filtros_academicos(request)
    turmas = Turma.objects.select_related('professor').annotate(
        total_disciplinas=Count('disciplinas', distinct=True),
        total_alunos=Count('alunos', filter=Q(alunos__ativo=True), distinct=True),
        total_atividades=Count('processos_avaliativos', distinct=True),
    ).order_by('-ano_letivo', 'nome')
    if filtros['ano']:
        turmas = turmas.filter(ano_letivo=filtros['ano'])
    if filtros['professor']:
        turmas = turmas.filter(professor_id=filtros['professor'])
    if filtros['status'] in dict(Turma.TURNO_CHOICES):
        turmas = turmas.filter(turno=filtros['status'])
    if filtros['q']:
        turmas = turmas.filter(Q(nome__icontains=filtros['q']) | Q(descricao__icontains=filtros['q']))
    pagina, querystring = _paginar(request, turmas)
    indicadores = indicadores_por_turma(list(pagina.object_list))
    for turma in pagina.object_list:
        turma.indicadores = indicadores.get(turma.id, {})
    return render(request, 'painel/turmas_lista.html', {
        'pagina': pagina, 'querystring': querystring, 'filtros': filtros, 'turnos': Turma.TURNO_CHOICES,
        **_opcoes_filtro(filtros),
    })


@admin_required
def painel_turma_detalhes(request, id):
    turma = get_object_or_404(Turma.objects.select_related('professor'), id=id)
    disciplinas = list(
        turma.disciplinas.select_related('professor').annotate(
            total_conteudos=Count('conteudos_programaticos', distinct=True),
            conteudos_concluidos=Count('conteudos_programaticos', filter=Q(conteudos_programaticos__concluido=True), distinct=True),
            total_atividades=Count('processos_avaliativos', distinct=True),
        ).order_by('nome')
    )
    aulas = dict(
        Aula.objects.filter(turma=turma).values('disciplina_id')
        .annotate(total=Sum('quantidade_aulas')).values_list('disciplina_id', 'total')
    )
    for disciplina in disciplinas:
        disciplina.aulas_registradas = aulas.get(disciplina.id, 0)
        previstas = disciplina.quantidade_aulas or 0
        disciplina.progresso_aulas = min(round(disciplina.aulas_registradas * 100 / previstas), 100) if previstas else 0
        disciplina.progresso_conteudos = (
            round(disciplina.conteudos_concluidos * 100 / disciplina.total_conteudos) if disciplina.total_conteudos else 0
        )
    return render(request, 'painel/turma_detalhes.html', {
        'turma': turma,
        'disciplinas': disciplinas,
        'indicadores': indicadores_por_turma([turma])[turma.id],
        'alunos_inativos': Aluno.objects.filter(turma=turma, ativo=False).count(),
        'alertas_nao_lidos': turma.alertas.filter(lido=False).count(),
        'atividades_pendentes': turma.processos_avaliativos.filter(status__in=['A_REALIZAR', 'EM_ANDAMENTO']).count(),
    })


@admin_required
def painel_turma_criar(request):
    form = TurmaPainelForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        turma = form.save()
        messages.success(request, f'Turma {turma.nome} cadastrada para {turma.professor.get_full_name() or turma.professor.username}.')
        return redirect('painel_turma_detalhes', id=turma.id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': 'Nova turma', 'voltar': 'painel_turmas', 'icone': 'bi-people',
    })


@admin_required
def painel_turma_editar(request, id):
    turma = get_object_or_404(Turma, id=id)
    professor_anterior = turma.professor_id
    form = TurmaPainelForm(request.POST or None, instance=turma)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            turma = form.save()
            if turma.professor_id != professor_anterior and form.cleaned_data.get('transferir_disciplinas'):
                quantidade = turma.disciplinas.update(professor=turma.professor)
                messages.info(request, f'{quantidade} disciplina(s) transferida(s) para o novo professor.')
        messages.success(request, 'Turma atualizada com sucesso.')
        return redirect('painel_turma_detalhes', id=turma.id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': f'Editar turma: {turma.nome}', 'voltar': 'painel_turma_detalhes',
        'voltar_id': turma.id, 'icone': 'bi-people',
    })


# ---------------------------------------------------------------------------
# Disciplinas
# ---------------------------------------------------------------------------
@admin_required
def painel_disciplinas(request):
    filtros = _filtros_academicos(request)
    disciplinas = Disciplina.objects.select_related('turma', 'professor').annotate(
        total_conteudos=Count('conteudos_programaticos', distinct=True),
        conteudos_concluidos=Count('conteudos_programaticos', filter=Q(conteudos_programaticos__concluido=True), distinct=True),
        total_atividades=Count('processos_avaliativos', distinct=True),
    ).order_by('turma__nome', 'nome')
    if filtros['ano']:
        disciplinas = disciplinas.filter(turma__ano_letivo=filtros['ano'])
    if filtros['professor']:
        disciplinas = disciplinas.filter(professor_id=filtros['professor'])
    if filtros['turma']:
        disciplinas = disciplinas.filter(turma_id=filtros['turma'])
    if filtros['q']:
        disciplinas = disciplinas.filter(Q(nome__icontains=filtros['q']) | Q(ano_escolar__icontains=filtros['q']))
    pagina, querystring = _paginar(request, disciplinas)
    aulas = dict(
        Aula.objects.filter(disciplina__in=list(pagina.object_list))
        .values('disciplina_id').annotate(total=Sum('quantidade_aulas')).values_list('disciplina_id', 'total')
    )
    for disciplina in pagina.object_list:
        disciplina.aulas_registradas = aulas.get(disciplina.id, 0)
        previstas = disciplina.quantidade_aulas or 0
        disciplina.progresso_aulas = min(round(disciplina.aulas_registradas * 100 / previstas), 100) if previstas else 0
    return render(request, 'painel/disciplinas_lista.html', {
        'pagina': pagina, 'querystring': querystring, 'filtros': filtros, **_opcoes_filtro(filtros),
    })


@admin_required
def painel_disciplina_criar(request):
    turma_inicial = _int(request.GET.get('turma'))
    form = DisciplinaPainelForm(request.POST or None, initial={'turma': turma_inicial} if turma_inicial else None)
    if request.method == 'POST' and form.is_valid():
        disciplina = form.save()
        messages.success(request, f'Disciplina {disciplina.nome} cadastrada na turma {disciplina.turma.nome}.')
        return redirect('painel_turma_detalhes', id=disciplina.turma_id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': 'Nova disciplina', 'voltar': 'painel_disciplinas', 'icone': 'bi-journal-bookmark',
    })


@admin_required
def painel_disciplina_editar(request, id):
    disciplina = get_object_or_404(Disciplina, id=id)
    form = DisciplinaPainelForm(request.POST or None, instance=disciplina)
    if request.method == 'POST' and form.is_valid():
        disciplina = form.save()
        messages.success(request, 'Disciplina atualizada com sucesso.')
        return redirect('painel_turma_detalhes', id=disciplina.turma_id)
    return render(request, 'painel/form.html', {
        'form': form, 'acao': f'Editar disciplina: {disciplina.nome}', 'voltar': 'painel_disciplinas',
        'icone': 'bi-journal-bookmark',
    })


# ---------------------------------------------------------------------------
# Planejamento (consulta de atividades e conteudos)
# ---------------------------------------------------------------------------
@admin_required
def painel_planejamento(request):
    filtros = _filtros_academicos(request)
    aba = 'conteudos' if request.GET.get('aba') == 'conteudos' else 'atividades'

    if aba == 'atividades':
        registros = ProcessoAvaliativo.objects.select_related('turma', 'disciplina', 'turma__professor').order_by(
            '-data_fechamento', 'turma__nome',
        )
        status_choices = ProcessoAvaliativo.STATUS_CHOICES
        if filtros['turma']:
            registros = registros.filter(turma_id=filtros['turma'])
        if filtros['q']:
            registros = registros.filter(Q(titulo__icontains=filtros['q']) | Q(tipo__icontains=filtros['q']))
    else:
        registros = ConteudoProgramatico.objects.select_related(
            'disciplina', 'disciplina__turma', 'disciplina__professor',
        ).order_by('disciplina__turma__nome', 'disciplina__nome', 'data_inicio')
        status_choices = ConteudoProgramatico.STATUS_CHOICES
        if filtros['turma']:
            registros = registros.filter(disciplina__turma_id=filtros['turma'])
        if filtros['q']:
            registros = registros.filter(Q(titulo__icontains=filtros['q']) | Q(unidade__icontains=filtros['q']))

    prefixo = '' if aba == 'atividades' else 'disciplina__'
    if filtros['ano']:
        registros = registros.filter(**{f'{prefixo}turma__ano_letivo': filtros['ano']})
    if filtros['professor']:
        registros = registros.filter(**{f'{prefixo}turma__professor_id': filtros['professor']})
    if filtros['disciplina']:
        registros = registros.filter(disciplina_id=filtros['disciplina'])
    if filtros['periodo']:
        registros = registros.filter(periodo=filtros['periodo'])
    if filtros['status'] in dict(status_choices):
        registros = registros.filter(status=filtros['status'])

    pagina, querystring = _paginar(request, registros)
    return render(request, 'painel/planejamento.html', {
        'aba': aba, 'pagina': pagina, 'querystring': querystring, 'filtros': filtros,
        'status_choices': status_choices, **_opcoes_filtro(filtros),
    })


# ---------------------------------------------------------------------------
# Relatorios
# ---------------------------------------------------------------------------
@admin_required
def painel_relatorios(request):
    filtros = _filtros_academicos(request)
    disciplinas = Disciplina.objects.select_related('turma', 'professor').filter(turma__isnull=False).order_by(
        '-turma__ano_letivo', 'turma__nome', 'nome',
    )
    if filtros['ano']:
        disciplinas = disciplinas.filter(turma__ano_letivo=filtros['ano'])
    if filtros['professor']:
        disciplinas = disciplinas.filter(professor_id=filtros['professor'])
    if filtros['turma']:
        disciplinas = disciplinas.filter(turma_id=filtros['turma'])
    pagina, querystring = _paginar(request, disciplinas)

    turmas = Turma.objects.select_related('professor').order_by('-ano_letivo', 'nome')
    if filtros['ano']:
        turmas = turmas.filter(ano_letivo=filtros['ano'])
    if filtros['professor']:
        turmas = turmas.filter(professor_id=filtros['professor'])
    if filtros['turma']:
        turmas = turmas.filter(id=filtros['turma'])
    turmas = list(turmas)
    indicadores = indicadores_por_turma(turmas)
    for turma in turmas:
        turma.indicadores = indicadores[turma.id]
    return render(request, 'painel/relatorios.html', {
        'pagina': pagina, 'querystring': querystring, 'filtros': filtros, 'turmas': turmas,
        'resumo': consolidar(indicadores), **_opcoes_filtro(filtros),
    })
