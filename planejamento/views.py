from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    AlterarSenhaForm,
    AlunoForm,
    AnotacaoTurmaForm,
    AulaForm,
    CadastroProfessorForm,
    ChamadaForm,
    ConteudoProgramaticoForm,
    DisciplinaForm,
    PerfilUsuarioForm,
    ProcessoAvaliativoForm,
    TurmaForm,
    UsuarioPerfilForm,
)
from .models import (
    Alerta,
    Aluno,
    AnotacaoTurma,
    Aula,
    Chamada,
    ConteudoProgramatico,
    Disciplina,
    NotaAluno,
    PerfilUsuario,
    Presenca,
    PresencaAluno,
    ProcessoAvaliativo,
    RegistroAlunoTurma,
    Turma,
)
from .utils import alertas_gerais_usuario, verificar_alertas_conteudos


PERIODO_ORDEM = {
    '1_BIMESTRE': 1,
    '2_BIMESTRE': 2,
    '3_BIMESTRE': 3,
    '4_BIMESTRE': 4,
    '1_TRIMESTRE': 1,
    '2_TRIMESTRE': 2,
    '3_TRIMESTRE': 3,
    '1_SEMESTRE': 1,
    '2_SEMESTRE': 2,
    'ANUAL': 1,
}

TIPO_PERIODO_ORDEM = {
    'BIMESTRE': 1,
    'TRIMESTRE': 2,
    'SEMESTRE': 3,
    'ANUAL': 4,
}

PERIODO_BADGES = {
    'BIMESTRE': 'text-bg-primary',
    'TRIMESTRE': 'text-bg-success',
    'SEMESTRE': 'text-bg-warning',
    'ANUAL': 'text-bg-info',
}

PERIODO_TITULOS = dict(ConteudoProgramatico.PERIODO_CHOICES)
TIPO_PERIODO_TITULOS = dict(ConteudoProgramatico.TIPO_PERIODO_CHOICES)


def cadastro_professor(request):
    form = CadastroProfessorForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cadastro realizado com sucesso. Entre com seu usuario e senha.')
        return redirect('login')
    return render(request, 'registration/cadastro.html', {'form': form})


def _tipo_periodo_conteudo(conteudo):
    if conteudo.tipo_periodo:
        return conteudo.tipo_periodo
    if conteudo.bimestre:
        return 'BIMESTRE'
    return 'ANUAL'


def _periodo_conteudo(conteudo):
    if conteudo.periodo:
        return conteudo.periodo
    if conteudo.bimestre:
        return f'{conteudo.bimestre}_BIMESTRE'
    return 'ANUAL'


def _titulo_periodo_conteudo(conteudo):
    titulo = conteudo.get_periodo_planejamento_display()
    return titulo.upper() if titulo != '-' else 'ANUAL'


def agrupar_conteudos_por_periodo(conteudos):
    grupos = {}
    for conteudo in conteudos:
        tipo_periodo = _tipo_periodo_conteudo(conteudo)
        periodo = _periodo_conteudo(conteudo)
        chave = (tipo_periodo, periodo)
        if chave not in grupos:
            grupos[chave] = {
                'tipo_periodo': tipo_periodo,
                'periodo': periodo,
                'titulo': _titulo_periodo_conteudo(conteudo),
                'badge': PERIODO_BADGES.get(tipo_periodo, 'text-bg-secondary'),
                'conteudos': [],
            }
        grupos[chave]['conteudos'].append(conteudo)

    grupos_ordenados = sorted(
        grupos.values(),
        key=lambda grupo: (
            TIPO_PERIODO_ORDEM.get(grupo['tipo_periodo'], 99),
            PERIODO_ORDEM.get(grupo['periodo'], 99),
            grupo['titulo'],
        ),
    )
    for grupo in grupos_ordenados:
        grupo['quantidade'] = len(grupo['conteudos'])
    return grupos_ordenados


def _media_notas(notas):
    notas_validas = [nota for nota in notas if nota is not None]
    if not notas_validas:
        return None
    media = sum(notas_validas, Decimal('0')) / len(notas_validas)
    return media.quantize(Decimal('0.01'))


def _linhas_presenca(turma, chamada=None):
    alunos = turma.alunos.filter(ativo=True)
    presencas_existentes = {}
    if chamada is not None:
        presencas_existentes = {presenca.aluno_id: presenca for presenca in chamada.presencas.select_related('aluno')}
    return [
        {
            'aluno': aluno,
            'presenca': presencas_existentes.get(aluno.id),
        }
        for aluno in alunos
    ]


def _salvar_presencas_chamada(request, turma, chamada):
    houve_erro = False
    for aluno in turma.alunos.filter(ativo=True):
        presenca = PresencaAluno.objects.filter(chamada=chamada, aluno=aluno).first() or PresencaAluno(
            chamada=chamada,
            aluno=aluno,
        )
        presenca.presente = request.POST.get(f'presente_{aluno.id}') == 'on'
        presenca.observacao = (request.POST.get(f'observacao_{aluno.id}') or '').strip()
        try:
            presenca.full_clean()
        except ValidationError as erro:
            mensagens = []
            for erros_campo in erro.message_dict.values():
                mensagens.extend(erros_campo)
            messages.error(request, f'{aluno.nome}: {" ".join(mensagens)}')
            houve_erro = True
        else:
            presenca.save()
    return not houve_erro


def _tipo_periodo_registro(registro):
    return getattr(registro, 'tipo_periodo', None) or 'ANUAL'


def _periodo_registro(registro):
    return getattr(registro, 'periodo', None) or 'ANUAL'


def _titulo_periodo(tipo_periodo, periodo):
    return (PERIODO_TITULOS.get(periodo) or TIPO_PERIODO_TITULOS.get(tipo_periodo) or 'Anual').upper()


def _percentual_presenca(total_presencas, total_aulas):
    if not total_aulas:
        return None
    percentual = (Decimal(total_presencas) / Decimal(total_aulas)) * Decimal('100')
    return percentual.quantize(Decimal('0.01'))


def _resumo_presencas_aulas(turma, disciplina, alunos):
    aulas = list(turma.aulas.filter(disciplina=disciplina).order_by('data', 'id')) if disciplina else []
    total_aulas = sum(aula.quantidade_aulas for aula in aulas)
    presencas = Presenca.objects.filter(aula__in=aulas, aluno__in=alunos)
    aulas_por_id = {aula.id: aula for aula in aulas}
    resumo = {aluno.id: {'total_aulas': total_aulas, 'presencas': 0, 'faltas': 0, 'percentual': None} for aluno in alunos}
    for presenca in presencas:
        quantidade = aulas_por_id[presenca.aula_id].quantidade_aulas
        if presenca.presente:
            resumo[presenca.aluno_id]['presencas'] += quantidade
        else:
            resumo[presenca.aluno_id]['faltas'] += quantidade
    for aluno in alunos:
        dados = resumo[aluno.id]
        registros = dados['presencas'] + dados['faltas']
        if registros < dados['total_aulas']:
            dados['presencas'] += dados['total_aulas'] - registros
        dados['percentual'] = _percentual_presenca(dados['presencas'], dados['total_aulas'])
    return aulas, resumo


def _filtrar_por_periodo(registros, tipo_periodo, periodo):
    filtrados = []
    for registro in registros:
        if tipo_periodo and _tipo_periodo_registro(registro) != tipo_periodo:
            continue
        if periodo and _periodo_registro(registro) != periodo:
            continue
        filtrados.append(registro)
    return filtrados


@login_required
def dashboard(request):
    verificar_alertas_conteudos(request.user)
    conteudos = ConteudoProgramatico.objects.filter(disciplina__professor=request.user)
    alertas = Alerta.objects.filter(usuario=request.user)
    disciplinas = Disciplina.objects.filter(professor=request.user)
    turmas = Turma.objects.filter(professor=request.user)

    context = {
        'total_turmas': turmas.count(),
        'total_disciplinas': disciplinas.count(),
        'total_conteudos': conteudos.count(),
        'alertas_nao_lidos': alertas.filter(lido=False).count(),
        'alertas_gerais': alertas_gerais_usuario(request.user, limite=None),
        'turmas': turmas,
        'ultimas_disciplinas': disciplinas.select_related('turma')[:5],
        'ultimos_conteudos': conteudos.select_related('disciplina', 'disciplina__turma')[:5],
    }
    return render(request, 'dashboard.html', context)


@login_required
def turma_lista(request):
    turmas = Turma.objects.filter(professor=request.user)
    return render(request, 'turmas/lista.html', {'turmas': turmas})


@login_required
def turma_detalhes(request, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=id)
    verificar_alertas_conteudos(request.user)
    disciplinas = turma.disciplinas.filter(professor=request.user)
    conteudos = ConteudoProgramatico.objects.filter(
        disciplina__turma=turma,
        disciplina__professor=request.user,
    ).select_related('disciplina')
    alertas = turma.alertas.filter(usuario=request.user).select_related('conteudo')
    anotacoes = turma.anotacoes.filter(professor=request.user)
    processos = turma.processos_avaliativos.select_related('disciplina')
    chamadas = turma.chamadas.select_related('disciplina')
    context = {
        'turma': turma,
        'disciplinas': disciplinas[:6],
        'conteudos': conteudos[:6],
        'alertas': alertas[:6],
        'anotacoes': anotacoes[:6],
        'processos': processos[:6],
        'chamadas': chamadas[:6],
        'primeira_avaliacao': processos.first(),
        'total_disciplinas': disciplinas.count(),
        'total_conteudos': conteudos.count(),
        'total_alertas': alertas.count(),
        'total_alunos': turma.alunos.count(),
        'total_avaliacoes': processos.count(),
        'total_presencas': chamadas.count(),
    }
    return render(request, 'turmas/detalhes.html', context)


@login_required
def turma_criar(request):
    form = TurmaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        turma = form.save(commit=False)
        turma.professor = request.user
        turma.save()
        messages.success(request, 'Turma cadastrada com sucesso.')
        return redirect('turma_detalhes', id=turma.id)

    return render(request, 'turmas/form.html', {'form': form, 'acao': 'Nova turma'})


@login_required
def turma_editar(request, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=id)
    form = TurmaForm(request.POST or None, instance=turma)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Turma atualizada com sucesso.')
        return redirect('turma_detalhes', id=turma.id)

    return render(request, 'turmas/form.html', {'form': form, 'turma': turma, 'acao': 'Editar turma'})


@login_required
def turma_deletar(request, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=id)
    if request.method == 'POST':
        turma.delete()
        messages.success(request, 'Turma removida com sucesso.')
        return redirect('turma_lista')

    return render(request, 'turmas/confirmar_exclusao.html', {'turma': turma})


@login_required
def disciplina_lista(request):
    disciplinas = Disciplina.objects.filter(professor=request.user).select_related('turma')
    return render(request, 'disciplinas/lista.html', {'disciplinas': disciplinas})


@login_required
def disciplina_detalhes(request, id):
    disciplina = get_object_or_404(Disciplina.objects.filter(professor=request.user).select_related('turma'), id=id)
    return render(request, 'disciplinas/detalhes.html', {'disciplina': disciplina, 'turma': disciplina.turma})


@login_required
def disciplina_criar(request):
    form = DisciplinaForm(request.POST or None, professor=request.user)
    if request.method == 'POST' and form.is_valid():
        disciplina = form.save(commit=False)
        disciplina.professor = request.user
        disciplina.save()
        messages.success(request, 'Disciplina cadastrada com sucesso.')
        return redirect('disciplina_detalhes', id=disciplina.id)

    return render(request, 'disciplinas/form.html', {'form': form, 'acao': 'Nova disciplina'})


@login_required
def turma_disciplina_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    disciplinas = Disciplina.objects.filter(professor=request.user, turma=turma)
    return render(request, 'disciplinas/lista.html', {'disciplinas': disciplinas, 'turma': turma})


@login_required
def turma_disciplina_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = DisciplinaForm(request.POST or None, professor=request.user, turma=turma)
    if request.method == 'POST' and form.is_valid():
        disciplina = form.save(commit=False)
        disciplina.professor = request.user
        disciplina.turma = turma
        disciplina.save()
        messages.success(request, 'Disciplina cadastrada com sucesso.')
        return redirect('turma_disciplina_lista', turma_id=turma.id)

    return render(request, 'disciplinas/form.html', {'form': form, 'acao': 'Nova disciplina', 'turma': turma})


@login_required
def disciplina_editar(request, id):
    disciplina = get_object_or_404(Disciplina.objects.filter(professor=request.user), id=id)
    form = DisciplinaForm(request.POST or None, instance=disciplina, professor=request.user)
    if request.method == 'POST' and form.is_valid():
        disciplina = form.save(commit=False)
        disciplina.professor = request.user
        disciplina.save()
        messages.success(request, 'Disciplina atualizada com sucesso.')
        return redirect('disciplina_detalhes', id=disciplina.id)

    return render(request, 'disciplinas/form.html', {'form': form, 'disciplina': disciplina, 'turma': disciplina.turma, 'acao': 'Editar disciplina'})


@login_required
def disciplina_deletar(request, id):
    disciplina = get_object_or_404(Disciplina.objects.filter(professor=request.user), id=id)
    if request.method == 'POST':
        disciplina.delete()
        messages.success(request, 'Disciplina removida com sucesso.')
        return redirect('disciplina_lista')

    return render(request, 'disciplinas/confirmar_exclusao.html', {'disciplina': disciplina})


@login_required
def conteudo_lista(request):
    verificar_alertas_conteudos(request.user)
    conteudos = ConteudoProgramatico.objects.filter(
        disciplina__professor=request.user,
    ).select_related('disciplina', 'disciplina__turma')
    grupos_periodo = agrupar_conteudos_por_periodo(conteudos)
    return render(request, 'conteudos/lista.html', {'conteudos': conteudos, 'grupos_periodo': grupos_periodo})


@login_required
def conteudo_detalhes(request, id):
    verificar_alertas_conteudos(request.user)
    conteudo = get_object_or_404(
        ConteudoProgramatico.objects.filter(disciplina__professor=request.user).select_related('disciplina', 'disciplina__turma'),
        id=id,
    )
    return render(request, 'conteudos/detalhes.html', {'conteudo': conteudo, 'turma': conteudo.disciplina.turma})


@login_required
def conteudo_criar(request):
    form = ConteudoProgramaticoForm(request.POST or None, request.FILES or None, professor=request.user)
    if request.method == 'POST' and form.is_valid():
        conteudo = form.save()
        conteudo.atualizar_status()
        messages.success(request, 'Conteudo programatico cadastrado com sucesso.')
        return redirect('conteudo_detalhes', id=conteudo.id)

    return render(request, 'conteudos/form.html', {'form': form, 'acao': 'Novo conteudo'})


@login_required
def turma_conteudo_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    verificar_alertas_conteudos(request.user)
    conteudos = ConteudoProgramatico.objects.filter(
        disciplina__turma=turma,
        disciplina__professor=request.user,
    ).select_related('disciplina', 'disciplina__turma')
    grupos_periodo = agrupar_conteudos_por_periodo(conteudos)
    return render(request, 'conteudos/lista.html', {'conteudos': conteudos, 'grupos_periodo': grupos_periodo, 'turma': turma})


@login_required
def turma_conteudo_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = ConteudoProgramaticoForm(request.POST or None, request.FILES or None, professor=request.user, turma=turma)
    if request.method == 'POST' and form.is_valid():
        conteudo = form.save()
        conteudo.atualizar_status()
        messages.success(request, 'Conteudo programatico cadastrado com sucesso.')
        return redirect('turma_conteudo_lista', turma_id=turma.id)

    return render(request, 'conteudos/form.html', {'form': form, 'acao': 'Novo conteudo', 'turma': turma})


@login_required
def conteudo_editar(request, id):
    conteudo = get_object_or_404(ConteudoProgramatico.objects.filter(disciplina__professor=request.user), id=id)
    form = ConteudoProgramaticoForm(request.POST or None, request.FILES or None, instance=conteudo, professor=request.user)
    if request.method == 'POST' and form.is_valid():
        conteudo = form.save()
        conteudo.atualizar_status()
        messages.success(request, 'Conteudo programatico atualizado com sucesso.')
        return redirect('conteudo_detalhes', id=conteudo.id)

    return render(request, 'conteudos/form.html', {'form': form, 'conteudo': conteudo, 'turma': conteudo.disciplina.turma, 'acao': 'Editar conteudo'})


@login_required
def conteudo_deletar(request, id):
    conteudo = get_object_or_404(ConteudoProgramatico.objects.filter(disciplina__professor=request.user), id=id)
    if request.method == 'POST':
        conteudo.delete()
        messages.success(request, 'Conteudo programatico removido com sucesso.')
        return redirect('conteudo_lista')

    return render(request, 'conteudos/confirmar_exclusao.html', {'conteudo': conteudo})


@login_required
@require_POST
def conteudo_concluir(request, id):
    conteudo = get_object_or_404(ConteudoProgramatico.objects.filter(disciplina__professor=request.user), id=id)
    conteudo.marcar_como_concluido()
    messages.success(request, 'Conteudo marcado como concluido.')
    return redirect(request.POST.get('next') or 'conteudo_lista')


@login_required
def relatorio_lista(request):
    return render(request, 'relatorios/lista.html')


@login_required
def alerta_lista(request):
    verificar_alertas_conteudos(request.user)
    alertas = Alerta.objects.filter(usuario=request.user).select_related('conteudo', 'turma')
    return render(request, 'alertas/lista.html', {'alertas': alertas, 'alertas_gerais': alertas_gerais_usuario(request.user, limite=None)})


@login_required
def turma_alerta_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    verificar_alertas_conteudos(request.user)
    alertas = Alerta.objects.filter(usuario=request.user, turma=turma).select_related('conteudo', 'turma')
    return render(request, 'alertas/lista.html', {'alertas': alertas, 'turma': turma})


@login_required
@require_POST
def alerta_lido(request, id):
    alerta = get_object_or_404(Alerta.objects.filter(usuario=request.user), id=id)
    alerta.lido = True
    alerta.save(update_fields=['lido'])
    messages.success(request, 'Alerta marcado como lido.')
    return redirect(request.POST.get('next') or 'alerta_lista')


@login_required
@require_POST
def alerta_excluir(request, id):
    alerta = get_object_or_404(Alerta.objects.filter(usuario=request.user), id=id)
    alerta.delete()
    messages.success(request, 'Alerta excluido com sucesso.')
    return redirect(request.POST.get('next') or 'alerta_lista')


@login_required
def aluno_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    alunos = turma.alunos.all()
    return render(request, 'alunos/lista.html', {'turma': turma, 'alunos': alunos})


@login_required
def aluno_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = AlunoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        aluno = form.save(commit=False)
        aluno.turma = turma
        aluno.save()
        messages.success(request, 'Aluno cadastrado com sucesso.')
        return redirect('aluno_detalhes', turma_id=turma.id, id=aluno.id)

    return render(request, 'alunos/form.html', {'form': form, 'turma': turma, 'acao': 'Novo aluno'})


@login_required
def aluno_detalhes(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    aluno = get_object_or_404(Aluno.objects.filter(turma=turma), id=id)
    notas = aluno.notas.select_related('processo', 'processo__disciplina')
    return render(request, 'alunos/detalhes.html', {'turma': turma, 'aluno': aluno, 'notas': notas})


@login_required
def aluno_editar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    aluno = get_object_or_404(Aluno.objects.filter(turma=turma), id=id)
    form = AlunoForm(request.POST or None, instance=aluno)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Aluno atualizado com sucesso.')
        return redirect('aluno_detalhes', turma_id=turma.id, id=aluno.id)

    return render(request, 'alunos/form.html', {'form': form, 'turma': turma, 'aluno': aluno, 'acao': 'Editar aluno'})


@login_required
def aluno_deletar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    aluno = get_object_or_404(Aluno.objects.filter(turma=turma), id=id)
    if request.method == 'POST':
        aluno.delete()
        messages.success(request, 'Aluno removido com sucesso.')
        return redirect('aluno_lista', turma_id=turma.id)

    return render(request, 'alunos/confirmar_exclusao.html', {'turma': turma, 'aluno': aluno})


@login_required
def avaliacao_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    avaliacoes = turma.processos_avaliativos.select_related('disciplina')
    return render(request, 'avaliacoes/lista.html', {'turma': turma, 'avaliacoes': avaliacoes})


@login_required
def avaliacao_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = ProcessoAvaliativoForm(request.POST or None, turma=turma)
    if request.method == 'POST' and form.is_valid():
        avaliacao = form.save(commit=False)
        avaliacao.turma = turma
        avaliacao.save()
        messages.success(request, 'Avaliacao cadastrada com sucesso.')
        return redirect('avaliacao_detalhes', turma_id=turma.id, id=avaliacao.id)

    return render(request, 'avaliacoes/form.html', {'form': form, 'turma': turma, 'acao': 'Nova avaliacao'})


@login_required
def avaliacao_detalhes(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    avaliacao = get_object_or_404(
        ProcessoAvaliativo.objects.filter(turma=turma).select_related('disciplina'),
        id=id,
    )
    notas = avaliacao.notas.select_related('aluno')
    return render(request, 'avaliacoes/detalhes.html', {'turma': turma, 'avaliacao': avaliacao, 'notas': notas})


@login_required
def avaliacao_editar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    avaliacao = get_object_or_404(ProcessoAvaliativo.objects.filter(turma=turma), id=id)
    form = ProcessoAvaliativoForm(request.POST or None, instance=avaliacao, turma=turma)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Avaliacao atualizada com sucesso.')
        return redirect('avaliacao_detalhes', turma_id=turma.id, id=avaliacao.id)

    return render(
        request,
        'avaliacoes/form.html',
        {'form': form, 'turma': turma, 'avaliacao': avaliacao, 'acao': 'Editar avaliacao'},
    )


@login_required
def avaliacao_deletar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    avaliacao = get_object_or_404(ProcessoAvaliativo.objects.filter(turma=turma), id=id)
    if request.method == 'POST':
        avaliacao.delete()
        messages.success(request, 'Avaliacao removida com sucesso.')
        return redirect('avaliacao_lista', turma_id=turma.id)

    return render(request, 'avaliacoes/confirmar_exclusao.html', {'turma': turma, 'avaliacao': avaliacao})


@login_required
def lancar_notas(request, turma_id, avaliacao_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    avaliacao = get_object_or_404(
        ProcessoAvaliativo.objects.filter(turma=turma).select_related('disciplina'),
        id=avaliacao_id,
    )
    destino = (
        f'/turmas/{turma.id}/planilha/?disciplina={avaliacao.disciplina_id}'
        f'&tipo_periodo={avaliacao.tipo_periodo or "ANUAL"}'
        f'&periodo={avaliacao.periodo or "ANUAL"}'
    )
    return redirect(destino)


@login_required
def boletim_turma(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    avaliacoes = list(turma.processos_avaliativos.select_related('disciplina'))
    alunos = turma.alunos.filter(ativo=True)
    notas = {
        (nota.aluno_id, nota.processo_id): nota.nota
        for nota in NotaAluno.objects.filter(aluno__turma=turma, processo__turma=turma)
    }
    linhas = []
    for aluno in alunos:
        notas_aluno = [notas.get((aluno.id, avaliacao.id)) for avaliacao in avaliacoes]
        linhas.append({
            'aluno': aluno,
            'notas': notas_aluno,
            'media': _media_notas(notas_aluno),
        })

    return render(request, 'turmas/boletim.html', {'turma': turma, 'avaliacoes': avaliacoes, 'linhas': linhas})


@login_required
def planilha_turma(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    disciplinas = list(turma.disciplinas.filter(professor=request.user))
    disciplina_id = request.GET.get('disciplina') or ''
    disciplina = None
    if disciplina_id:
        disciplina = next((item for item in disciplinas if str(item.id) == str(disciplina_id)), None)
    if disciplina is None and disciplinas:
        disciplina = disciplinas[0]

    alunos = list(turma.alunos.filter(ativo=True))
    registros = {
        registro.aluno_id: registro
        for registro in RegistroAlunoTurma.objects.filter(
            turma=turma,
            disciplina=disciplina,
            aluno__in=alunos,
        ).select_related('aluno', 'disciplina')
    }
    avaliacoes = list(
        turma.processos_avaliativos.filter(disciplina=disciplina).select_related('disciplina')
        if disciplina else turma.processos_avaliativos.none()
    )
    aulas, resumo_presencas = _resumo_presencas_aulas(turma, disciplina, alunos)
    aulas_previstas = disciplina.quantidade_aulas if disciplina else 0
    media_aprovacao = disciplina.media_aprovacao if disciplina else Decimal('6.00')
    total_aulas = sum(aula.quantidade_aulas for aula in aulas)
    aulas_restantes = max(aulas_previstas - total_aulas, 0)

    if request.method == 'POST':
        houve_erro = False
        for aluno in alunos:
            registro = registros.get(aluno.id) or RegistroAlunoTurma(turma=turma, aluno=aluno, disciplina=disciplina)
            registro.total_aulas = total_aulas
            registro.total_faltas = resumo_presencas.get(aluno.id, {}).get('faltas', 0)
            registro.observacao = (request.POST.get(f'observacao_{aluno.id}') or '').strip()

            for avaliacao in avaliacoes:
                valor = (request.POST.get(f'nota_{aluno.id}_{avaliacao.id}') or '').strip().replace(',', '.')
                observacao_nota = (request.POST.get(f'nota_obs_{aluno.id}_{avaliacao.id}') or '').strip()
                nota_aluno = NotaAluno.objects.filter(aluno=aluno, processo=avaliacao).first()
                if not valor:
                    if nota_aluno:
                        nota_aluno.delete()
                    continue
                if valor:
                    try:
                        nota_decimal = Decimal(valor)
                    except InvalidOperation:
                        messages.error(request, f'Nota invalida para {aluno.nome} em {avaliacao.titulo}.')
                        houve_erro = True
                        continue
                    nota_aluno = nota_aluno or NotaAluno(aluno=aluno, processo=avaliacao)
                    nota_aluno.nota = nota_decimal
                    nota_aluno.observacao = observacao_nota
                    try:
                        nota_aluno.full_clean()
                    except ValidationError as erro:
                        mensagens = []
                        for erros_campo in erro.message_dict.values():
                            mensagens.extend(erros_campo)
                        messages.error(request, f'{aluno.nome} - {avaliacao.titulo}: {" ".join(mensagens)}')
                        houve_erro = True
                    else:
                        nota_aluno.save()

            try:
                registro.full_clean()
            except ValidationError as erro:
                mensagens = []
                for erros_campo in erro.message_dict.values():
                    mensagens.extend(erros_campo)
                messages.error(request, f'{aluno.nome}: {" ".join(mensagens)}')
                houve_erro = True
            else:
                registro.save()
                registros[aluno.id] = registro

        if not houve_erro:
            messages.success(request, 'Planilha salva com sucesso.')
            if disciplina:
                return redirect(f'/turmas/{turma.id}/planilha/?disciplina={disciplina.id}')
            return redirect('planilha_turma', turma_id=turma.id)

    notas = {
        (nota.aluno_id, nota.processo_id): nota
        for nota in NotaAluno.objects.filter(aluno__turma=turma, processo__in=avaliacoes)
    }
    chaves_periodo = {
        (_tipo_periodo_registro(avaliacao), _periodo_registro(avaliacao))
        for avaliacao in avaliacoes
    } or {('ANUAL', 'ANUAL')}

    grupos = []
    medias_grafico = {}
    for grupo_tipo, grupo_periodo in sorted(
        chaves_periodo,
        key=lambda chave: (
            TIPO_PERIODO_ORDEM.get(chave[0], 99),
            PERIODO_ORDEM.get(chave[1], 99),
            _titulo_periodo(chave[0], chave[1]),
        ),
    ):
        avaliacoes_grupo = [
            avaliacao for avaliacao in avaliacoes
            if (_tipo_periodo_registro(avaliacao), _periodo_registro(avaliacao)) == (grupo_tipo, grupo_periodo)
        ]
        linhas = []
        for aluno in alunos:
            registro = registros.get(aluno.id) or RegistroAlunoTurma(
                turma=turma,
                aluno=aluno,
                disciplina=disciplina,
                total_aulas=total_aulas,
            )
            registro.total_aulas = total_aulas
            registro.total_faltas = resumo_presencas.get(aluno.id, {}).get('faltas', 0)
            cells = []
            notas_media = []
            for avaliacao in avaliacoes_grupo:
                nota = notas.get((aluno.id, avaliacao.id))
                if nota:
                    notas_media.append(nota.nota)
                    medias_grafico.setdefault(aluno.id, []).append(nota.nota)
                cells.append({'avaliacao': avaliacao, 'nota': nota})

            presenca_dados = resumo_presencas.get(aluno.id, {'total_aulas': 0, 'presencas': 0, 'faltas': 0, 'percentual': None})
            soma_notas = sum(notas_media, Decimal('0')) if notas_media else None
            frequencia = presenca_dados.get('percentual')
            aulas_concluidas = aulas_previstas > 0 and total_aulas >= aulas_previstas
            media_final = soma_notas if soma_notas is not None else Decimal('0')
            if not aulas_concluidas:
                situacao = 'Em andamento'
                badge = 'text-bg-secondary'
            elif frequencia is not None and frequencia < Decimal('75.00') and media_final < media_aprovacao:
                situacao = 'Reprovado por nota e falta'
                badge = 'text-bg-danger'
            elif frequencia is not None and frequencia < Decimal('75.00'):
                situacao = 'Reprovado por falta'
                badge = 'text-bg-danger'
            elif media_final < media_aprovacao:
                situacao = 'Recuperação/Paralela'
                badge = 'text-bg-warning'
            else:
                situacao = 'Aprovado'
                badge = 'text-bg-success'
            linhas.append({
                'aluno': aluno,
                'registro': registro,
                'presenca': presenca_dados,
                'notas': cells,
                'media': soma_notas,
                'situacao': situacao,
                'badge': badge,
            })

        grupos.append({
            'titulo': _titulo_periodo(grupo_tipo, grupo_periodo),
            'badge': PERIODO_BADGES.get(grupo_tipo, 'text-bg-secondary'),
            'avaliacoes': avaliacoes_grupo,
            'linhas': linhas,
        })

    medias_alunos = []
    for aluno in alunos:
        notas_aluno = medias_grafico.get(aluno.id, [])
        if notas_aluno:
            soma_aluno = sum(notas_aluno, Decimal('0')).quantize(Decimal('0.01'))
            medias_alunos.append({'aluno': aluno.nome, 'media': float(soma_aluno)})
    media_geral = None
    if medias_alunos:
        media_geral = (sum(Decimal(str(item['media'])) for item in medias_alunos) / len(medias_alunos)).quantize(Decimal('0.01'))

    return render(request, 'turmas/planilha.html', {
        'turma': turma,
        'disciplinas_filtro': [
            {'id': str(item.id), 'nome': item.nome, 'selected': disciplina and item.id == disciplina.id}
            for item in disciplinas
        ],
        'disciplina': disciplina,
        'total_aulas': total_aulas,
        'aulas_previstas': aulas_previstas,
        'aulas_restantes': aulas_restantes,
        'grupos': grupos,
        'media_geral': media_geral,
        'chart_labels': [item['aluno'] for item in medias_alunos],
        'chart_medias': [item['media'] for item in medias_alunos],
    })


def _linhas_presenca_aula(turma, aula=None):
    alunos = turma.alunos.filter(ativo=True)
    presencas = {}
    if aula:
        presencas = {presenca.aluno_id: presenca for presenca in aula.presencas.select_related('aluno')}
    return [{'aluno': aluno, 'presenca': presencas.get(aluno.id)} for aluno in alunos]


def _salvar_presencas_aula(request, turma, aula):
    houve_erro = False
    for aluno in turma.alunos.filter(ativo=True):
        presenca = Presenca.objects.filter(aula=aula, aluno=aluno).first() or Presenca(aula=aula, aluno=aluno)
        presenca.presente = request.POST.get(f'presente_{aluno.id}') == 'on'
        presenca.observacao = (request.POST.get(f'observacao_{aluno.id}') or '').strip()
        try:
            presenca.full_clean()
        except ValidationError as erro:
            mensagens = []
            for erros_campo in erro.message_dict.values():
                mensagens.extend(erros_campo)
            messages.error(request, f'{aluno.nome}: {" ".join(mensagens)}')
            houve_erro = True
        else:
            presenca.save()
    return not houve_erro


@login_required
def chamada_turma(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    disciplinas = list(turma.disciplinas.filter(professor=request.user))
    disciplina_id = request.GET.get('disciplina') or ''
    disciplina = None
    if disciplina_id:
        disciplina = next((item for item in disciplinas if str(item.id) == str(disciplina_id)), None)
    if disciplina is None and disciplinas:
        disciplina = disciplinas[0]

    alunos = list(turma.alunos.filter(ativo=True))
    aulas = list(turma.aulas.filter(disciplina=disciplina).order_by('data', 'id')) if disciplina else []
    total_aulas = sum(aula.quantidade_aulas for aula in aulas)
    presencas = {
        (presenca.aluno_id, presenca.aula_id): presenca
        for presenca in Presenca.objects.filter(aula__in=aulas, aluno__in=alunos)
    }
    linhas = []
    for aluno in alunos:
        cells = []
        faltas = 0
        presencas_total = 0
        for aula in aulas:
            presenca = presencas.get((aluno.id, aula.id))
            presente = True if presenca is None else presenca.presente
            if presente:
                presencas_total += aula.quantidade_aulas
            else:
                faltas += aula.quantidade_aulas
            cells.append({'aula': aula, 'presenca': presenca, 'presente': presente})
        linhas.append({
            'aluno': aluno,
            'presencas': cells,
            'faltas': faltas,
            'percentual': _percentual_presenca(presencas_total, total_aulas),
        })

    return render(request, 'turmas/chamada.html', {
        'turma': turma,
        'disciplina': disciplina,
        'disciplinas_filtro': [
            {'id': str(item.id), 'nome': item.nome, 'selected': disciplina and item.id == disciplina.id}
            for item in disciplinas
        ],
        'aulas': aulas,
        'linhas': linhas,
    })


@login_required
def registrar_aula(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    form = AulaForm(request.POST or None, turma=turma)
    linhas = _linhas_presenca_aula(turma)
    if request.method == 'POST' and form.is_valid():
        aula = form.save(commit=False)
        aula.turma = turma
        try:
            aula.full_clean()
        except ValidationError as erro:
            for erros_campo in erro.message_dict.values():
                for mensagem in erros_campo:
                    messages.error(request, mensagem)
        else:
            aula.save()
            if _salvar_presencas_aula(request, turma, aula):
                messages.success(request, 'Aula registrada com sucesso.')
                return redirect(f'/turmas/{turma.id}/chamada/?disciplina={aula.disciplina_id}')
    return render(request, 'turmas/aula_form.html', {'turma': turma, 'form': form, 'linhas': linhas, 'acao': 'Registrar aula'})


@login_required
def editar_chamada(request, turma_id, aula_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    aula = get_object_or_404(Aula.objects.filter(turma=turma), id=aula_id)
    form = AulaForm(request.POST or None, instance=aula, turma=turma)
    if request.method == 'POST' and form.is_valid():
        aula = form.save(commit=False)
        aula.turma = turma
        try:
            aula.full_clean()
        except ValidationError as erro:
            for erros_campo in erro.message_dict.values():
                for mensagem in erros_campo:
                    messages.error(request, mensagem)
        else:
            aula.save()
            if _salvar_presencas_aula(request, turma, aula):
                messages.success(request, 'Chamada atualizada com sucesso.')
                return redirect(f'/turmas/{turma.id}/chamada/?disciplina={aula.disciplina_id}')
    linhas = _linhas_presenca_aula(turma, aula)
    return render(request, 'turmas/aula_form.html', {'turma': turma, 'form': form, 'aula': aula, 'linhas': linhas, 'acao': 'Editar chamada'})


@login_required
def presenca_lista(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    chamadas = turma.chamadas.select_related('disciplina').prefetch_related('presencas')
    return render(request, 'presencas/lista.html', {'turma': turma, 'chamadas': chamadas})


@login_required
def presenca_criar(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    form = ChamadaForm(request.POST or None, turma=turma)
    linhas = _linhas_presenca(turma)

    if request.method == 'POST' and form.is_valid():
        chamada = form.save(commit=False)
        chamada.turma = turma
        try:
            chamada.full_clean()
        except ValidationError as erro:
            for erros_campo in erro.message_dict.values():
                for mensagem in erros_campo:
                    messages.error(request, mensagem)
        else:
            chamada.save()
            if _salvar_presencas_chamada(request, turma, chamada):
                messages.success(request, 'Presenca lancada com sucesso.')
                return redirect('presenca_detalhes', turma_id=turma.id, chamada_id=chamada.id)

    return render(request, 'presencas/form.html', {'form': form, 'turma': turma, 'linhas': linhas, 'acao': 'Nova presenca'})


@login_required
def presenca_detalhes(request, turma_id, chamada_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    chamada = get_object_or_404(
        Chamada.objects.filter(turma=turma).select_related('disciplina'),
        id=chamada_id,
    )
    presencas = chamada.presencas.select_related('aluno')
    presentes = presencas.filter(presente=True).count()
    faltas = presencas.filter(presente=False).count()
    return render(
        request,
        'presencas/detalhes.html',
        {'turma': turma, 'chamada': chamada, 'presencas': presencas, 'presentes': presentes, 'faltas': faltas},
    )


@login_required
def presenca_editar(request, turma_id, chamada_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    chamada = get_object_or_404(Chamada.objects.filter(turma=turma), id=chamada_id)
    form = ChamadaForm(request.POST or None, instance=chamada, turma=turma)

    if request.method == 'POST' and form.is_valid():
        chamada = form.save(commit=False)
        chamada.turma = turma
        try:
            chamada.full_clean()
        except ValidationError as erro:
            for erros_campo in erro.message_dict.values():
                for mensagem in erros_campo:
                    messages.error(request, mensagem)
        else:
            chamada.save()
            if _salvar_presencas_chamada(request, turma, chamada):
                messages.success(request, 'Presenca atualizada com sucesso.')
                return redirect('presenca_detalhes', turma_id=turma.id, chamada_id=chamada.id)

    linhas = _linhas_presenca(turma, chamada)
    return render(
        request,
        'presencas/form.html',
        {'form': form, 'turma': turma, 'chamada': chamada, 'linhas': linhas, 'acao': 'Editar presenca'},
    )


@login_required
def presenca_deletar(request, turma_id, chamada_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    chamada = get_object_or_404(Chamada.objects.filter(turma=turma), id=chamada_id)
    if request.method == 'POST':
        chamada.delete()
        messages.success(request, 'Presenca removida com sucesso.')
        return redirect('presenca_lista', turma_id=turma.id)

    return render(request, 'presencas/confirmar_exclusao.html', {'turma': turma, 'chamada': chamada})


@login_required
def turma_anotacao_lista(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    anotacoes = AnotacaoTurma.objects.filter(professor=request.user, turma=turma)
    return render(request, 'anotacoes/lista.html', {'anotacoes': anotacoes, 'turma': turma})


@login_required
def turma_anotacao_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = AnotacaoTurmaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        anotacao = form.save(commit=False)
        anotacao.professor = request.user
        anotacao.turma = turma
        anotacao.save()
        messages.success(request, 'Anotacao cadastrada com sucesso.')
        return redirect('turma_anotacao_lista', turma_id=turma.id)

    return render(request, 'anotacoes/form.html', {'form': form, 'turma': turma, 'acao': 'Nova anotacao'})


@login_required
def turma_anotacao_editar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    anotacao = get_object_or_404(AnotacaoTurma.objects.filter(professor=request.user, turma=turma), id=id)
    form = AnotacaoTurmaForm(request.POST or None, instance=anotacao)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Anotacao atualizada com sucesso.')
        return redirect('turma_anotacao_lista', turma_id=turma.id)

    return render(request, 'anotacoes/form.html', {'form': form, 'turma': turma, 'anotacao': anotacao, 'acao': 'Editar anotacao'})


@login_required
def turma_anotacao_deletar(request, turma_id, id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    anotacao = get_object_or_404(AnotacaoTurma.objects.filter(professor=request.user, turma=turma), id=id)
    if request.method == 'POST':
        anotacao.delete()
        messages.success(request, 'Anotacao removida com sucesso.')
        return redirect('turma_anotacao_lista', turma_id=turma.id)

    return render(request, 'anotacoes/confirmar_exclusao.html', {'turma': turma, 'anotacao': anotacao})


@login_required
def perfil_usuario(request):
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    return render(request, 'perfil/perfil.html', {'perfil': perfil})


@login_required
def editar_perfil(request):
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)
    usuario_form = UsuarioPerfilForm(request.POST or None, instance=request.user)
    perfil_form = PerfilUsuarioForm(request.POST or None, request.FILES or None, instance=perfil)

    if request.method == 'POST' and usuario_form.is_valid() and perfil_form.is_valid():
        usuario_form.save()
        perfil_form.save()
        messages.success(request, 'Perfil atualizado com sucesso.')
        return redirect('perfil_usuario')

    context = {
        'usuario_form': usuario_form,
        'perfil_form': perfil_form,
    }
    return render(request, 'perfil/editar_perfil.html', context)


@login_required
def alterar_senha(request):
    form = AlterarSenhaForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, 'Senha alterada com sucesso.')
        return redirect('perfil_usuario')

    return render(request, 'perfil/alterar_senha.html', {'form': form})
