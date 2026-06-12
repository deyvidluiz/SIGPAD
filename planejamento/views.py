from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.http import HttpResponse
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
    RecuperacaoForm,
    TurmaForm,
    UsuarioPerfilForm,
)
from .models import (
    Alerta,
    Aluno,
    AnotacaoTurma,
    Arquivo,
    Aula,
    Chamada,
    ConteudoProgramatico,
    Disciplina,
    NotaAluno,
    PerfilUsuario,
    Presenca,
    PresencaAluno,
    ProcessoAvaliativo,
    Recuperacao,
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


def _situacao_academica(media, frequencia, media_aprovacao, aulas_concluidas=True):
    media_final = media if media is not None else Decimal('0')
    if not aulas_concluidas:
        return 'Em andamento', 'text-bg-secondary'
    if frequencia is not None and frequencia < Decimal('75.00') and media_final < media_aprovacao:
        return 'Reprovado por nota e falta', 'text-bg-danger'
    if frequencia is not None and frequencia < Decimal('75.00'):
        return 'Reprovado por falta', 'text-bg-danger'
    if media_final < media_aprovacao:
        return 'Recuperação/Paralela', 'text-bg-warning'
    return 'Aprovado', 'text-bg-success'


def _media_periodo(soma_notas, total_valor, nota_total):
    if soma_notas is None:
        return None
    if not total_valor:
        return soma_notas.quantize(Decimal('0.01'))
    media = (soma_notas / total_valor) * nota_total
    return media.quantize(Decimal('0.01'))


def _media_com_recuperacao(media_periodo, recuperacao, nota_total=Decimal('10.00')):
    notas = [media_periodo] if media_periodo is not None else []
    if recuperacao and recuperacao.melhor_nota is not None:
        notas.append(recuperacao.melhor_nota)
    if not notas:
        return None
    return min(max(notas), nota_total).quantize(Decimal('0.01'))


def _grupos_planejamento(avaliacoes):
    grupos = {}
    for avaliacao in avaliacoes:
        avaliacao.atualizar_status_automatico()
        tipo_periodo = _tipo_periodo_registro(avaliacao)
        periodo = _periodo_registro(avaliacao)
        chave = (tipo_periodo, periodo)
        if chave not in grupos:
            grupos[chave] = {
                'tipo_periodo': tipo_periodo,
                'periodo': periodo,
                'titulo': _titulo_periodo(tipo_periodo, periodo),
                'badge': PERIODO_BADGES.get(tipo_periodo, 'text-bg-secondary'),
                'atividades': [],
            }
        grupos[chave]['atividades'].append(avaliacao)
    return sorted(
        grupos.values(),
        key=lambda grupo: (
            TIPO_PERIODO_ORDEM.get(grupo['tipo_periodo'], 99),
            PERIODO_ORDEM.get(grupo['periodo'], 99),
            grupo['titulo'],
        ),
    )


def _resumo_risco_turma(turma, disciplinas):
    alunos_abaixo_media = set()
    alunos_baixa_frequencia = set()
    alunos_recuperacao = set()
    aulas_registradas = 0
    aulas_restantes = 0
    for disciplina in disciplinas:
        alunos = list(turma.alunos.filter(ativo=True))
        _, resumo = _resumo_presencas_aulas(turma, disciplina, alunos)
        avaliacoes = list(turma.processos_avaliativos.filter(disciplina=disciplina))
        total_valor = sum((avaliacao.valor_maximo for avaliacao in avaliacoes), Decimal('0'))
        notas_por_aluno = {}
        for nota in NotaAluno.objects.filter(aluno__in=alunos, processo__in=avaliacoes):
            notas_por_aluno.setdefault(nota.aluno_id, Decimal('0'))
            notas_por_aluno[nota.aluno_id] += nota.nota
        total_aulas = disciplina.aulas_dadas
        aulas_registradas += total_aulas
        aulas_restantes += max(disciplina.quantidade_aulas - total_aulas, 0)
        aulas_concluidas = disciplina.quantidade_aulas > 0 and total_aulas >= disciplina.quantidade_aulas
        for aluno in alunos:
            media = _media_periodo(notas_por_aluno.get(aluno.id), total_valor, disciplina.nota_total)
            frequencia = resumo.get(aluno.id, {}).get('percentual')
            situacao, _ = _situacao_academica(media, frequencia, disciplina.media_aprovacao, aulas_concluidas)
            if media is not None and media < disciplina.media_aprovacao:
                alunos_abaixo_media.add(aluno.id)
            if frequencia is not None and frequencia < Decimal('75.00'):
                alunos_baixa_frequencia.add(aluno.id)
            if situacao == 'Recuperação/Paralela':
                alunos_recuperacao.add(aluno.id)
    return {
        'alunos_abaixo_media': len(alunos_abaixo_media),
        'alunos_baixa_frequencia': len(alunos_baixa_frequencia),
        'alunos_recuperacao': len(alunos_recuperacao),
        'aulas_registradas': aulas_registradas,
        'aulas_restantes': aulas_restantes,
    }


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
    atividades = ProcessoAvaliativo.objects.filter(turma__professor=request.user)
    aulas_dadas = Aula.objects.filter(turma__professor=request.user).aggregate(total=Sum('quantidade_aulas'))['total'] or 0
    alunos_abaixo_media = 0
    alunos_baixa_frequencia = 0
    for turma in turmas.prefetch_related('alunos', 'disciplinas'):
        for disciplina in turma.disciplinas.filter(professor=request.user):
            alunos = list(turma.alunos.filter(ativo=True))
            _, resumo = _resumo_presencas_aulas(turma, disciplina, alunos)
            avaliacoes = list(turma.processos_avaliativos.filter(disciplina=disciplina))
            notas = NotaAluno.objects.filter(aluno__in=alunos, processo__in=avaliacoes)
            notas_por_aluno = {}
            for nota in notas:
                notas_por_aluno.setdefault(nota.aluno_id, Decimal('0'))
                notas_por_aluno[nota.aluno_id] += nota.nota
            total_valor = sum((avaliacao.valor_maximo for avaliacao in avaliacoes), Decimal('0'))
            alunos_abaixo_media += sum(
                1 for valor in notas_por_aluno.values()
                if (_media_periodo(valor, total_valor, disciplina.nota_total) or Decimal('0')) < disciplina.media_aprovacao
            )
            alunos_baixa_frequencia += sum(
                1 for dados in resumo.values()
                if dados.get('percentual') is not None and dados['percentual'] < Decimal('75.00')
            )

    context = {
        'total_turmas': turmas.count(),
        'total_disciplinas': disciplinas.count(),
        'total_conteudos': conteudos.count(),
        'atividades_pendentes': atividades.filter(status__in=['A_REALIZAR', 'EM_ANDAMENTO']).count(),
        'atividades_corrigidas': atividades.filter(status__in=['CORRIGIDA', 'FINALIZADA']).count(),
        'total_aulas_dadas': aulas_dadas,
        'alunos_abaixo_media': alunos_abaixo_media,
        'alunos_baixa_frequencia': alunos_baixa_frequencia,
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
    risco = _resumo_risco_turma(turma, disciplinas)
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
        **risco,
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
    avaliacoes = disciplina.processos_avaliativos.select_related('turma', 'disciplina').prefetch_related('arquivos')
    grupos_planejamento = _grupos_planejamento(avaliacoes)
    return render(
        request,
        'disciplinas/detalhes.html',
        {
            'disciplina': disciplina,
            'turma': disciplina.turma,
            'grupos_planejamento': grupos_planejamento,
            'avaliacoes': avaliacoes,
        },
    )


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
    turmas = Turma.objects.filter(professor=request.user)
    disciplinas = Disciplina.objects.filter(professor=request.user).select_related('turma')
    return render(request, 'relatorios/lista.html', {'turmas': turmas, 'disciplinas': disciplinas})


def _render_relatorio_pdf(titulo, cabecalhos, linhas, nome_arquivo):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        response = HttpResponse(_pdf_simples(titulo, cabecalhos, linhas), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}.pdf"'
        return response

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}.pdf"'
    doc = SimpleDocTemplate(response, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    data = [cabecalhos] + linhas
    tabela = Table(data, repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4f7a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d0d7de')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    doc.build([Paragraph(titulo, styles['Title']), Spacer(1, 12), tabela])
    return response


def _pdf_escape(texto):
    return str(texto).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _pdf_simples(titulo, cabecalhos, linhas):
    largura, altura = 842, 595
    y = 560
    comandos = ['BT', '/F1 14 Tf', f'40 {y} Td', f'({_pdf_escape(titulo)}) Tj']
    y -= 26
    comandos.extend(['/F1 8 Tf', f'0 -26 Td', f'({_pdf_escape(" | ".join(cabecalhos))}) Tj'])
    y -= 14
    for linha in linhas[:34]:
        texto = ' | '.join(str(valor) for valor in linha)
        if len(texto) > 170:
            texto = texto[:167] + '...'
        comandos.extend([f'0 -14 Td', f'({_pdf_escape(texto)}) Tj'])
    comandos.append('ET')
    stream = '\n'.join(comandos).encode('latin-1', errors='replace')
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {largura} {altura}] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>'.encode(),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
    ]
    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for indice, objeto in enumerate(objetos, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{indice} 0 obj\n'.encode())
        pdf.extend(objeto)
        pdf.extend(b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
    return bytes(pdf)


@login_required
def exportar_notas_pdf(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    disciplina = get_object_or_404(Disciplina, id=request.GET.get('disciplina'), turma=turma, professor=request.user)
    alunos = list(turma.alunos.filter(ativo=True))
    avaliacoes = list(turma.processos_avaliativos.filter(disciplina=disciplina).select_related('disciplina'))
    notas = {
        (nota.aluno_id, nota.processo_id): nota.nota
        for nota in NotaAluno.objects.filter(aluno__in=alunos, processo__in=avaliacoes)
    }
    cabecalhos = ['Aluno'] + [avaliacao.titulo for avaliacao in avaliacoes] + ['Media/Soma']
    linhas = []
    for aluno in alunos:
        valores = [notas.get((aluno.id, avaliacao.id)) for avaliacao in avaliacoes]
        media = sum([valor for valor in valores if valor is not None], Decimal('0')) if valores else None
        linhas.append([aluno.nome] + [str(valor or '-') for valor in valores] + [str(media if media is not None else '-')])
    return _render_relatorio_pdf(f'Notas - {turma.nome} - {disciplina.nome}', cabecalhos, linhas, 'notas')


@login_required
def exportar_frequencia_pdf(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    disciplina = get_object_or_404(Disciplina, id=request.GET.get('disciplina'), turma=turma, professor=request.user)
    alunos = list(turma.alunos.filter(ativo=True))
    _, resumo = _resumo_presencas_aulas(turma, disciplina, alunos)
    cabecalhos = ['Aluno', 'Aulas', 'Faltas', 'Presencas', 'Frequencia', 'Situacao']
    linhas = []
    for aluno in alunos:
        dados = resumo.get(aluno.id, {})
        percentual = dados.get('percentual')
        situacao = 'Baixa frequencia' if percentual is not None and percentual < Decimal('75.00') else 'Regular'
        linhas.append([
            aluno.nome,
            str(dados.get('total_aulas', 0)),
            str(dados.get('faltas', 0)),
            str(dados.get('presencas', 0)),
            f'{percentual}%' if percentual is not None else '-',
            situacao,
        ])
    return _render_relatorio_pdf(f'Frequencia - {turma.nome} - {disciplina.nome}', cabecalhos, linhas, 'frequencia')


@login_required
def relatorio_final(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    disciplina = get_object_or_404(Disciplina, id=request.GET.get('disciplina'), turma=turma, professor=request.user)
    alunos = list(turma.alunos.filter(ativo=True))
    avaliacoes = list(turma.processos_avaliativos.filter(disciplina=disciplina))
    notas = NotaAluno.objects.filter(aluno__in=alunos, processo__in=avaliacoes)
    notas_por_aluno = {}
    for nota in notas:
        notas_por_aluno.setdefault(nota.aluno_id, Decimal('0'))
        notas_por_aluno[nota.aluno_id] += nota.nota
    total_valor = sum((avaliacao.valor_maximo for avaliacao in avaliacoes), Decimal('0'))
    _, resumo = _resumo_presencas_aulas(turma, disciplina, alunos)
    cabecalhos = ['Aluno', 'Media final', 'Frequencia', 'Faltas', 'Situacao']
    linhas = []
    for aluno in alunos:
        media = _media_periodo(notas_por_aluno.get(aluno.id), total_valor, disciplina.nota_total)
        frequencia = resumo.get(aluno.id, {}).get('percentual')
        aulas_concluidas = disciplina.quantidade_aulas > 0 and disciplina.aulas_dadas >= disciplina.quantidade_aulas
        situacao, _ = _situacao_academica(media, frequencia, disciplina.media_aprovacao, aulas_concluidas)
        linhas.append([
            aluno.nome,
            str(media if media is not None else '-'),
            f'{frequencia}%' if frequencia is not None else '-',
            str(resumo.get(aluno.id, {}).get('faltas', 0)),
            situacao.upper() if situacao == 'Aprovado' else situacao,
        ])
    return _render_relatorio_pdf(f'Relatorio final - {turma.nome} - {disciplina.nome}', cabecalhos, linhas, 'relatorio_final')


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
    busca = (request.GET.get('q') or '').strip()
    if busca:
        alunos = alunos.filter(Q(nome__icontains=busca) | Q(matricula__icontains=busca))
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
    recuperacoes = aluno.recuperacoes.select_related('disciplina')
    return render(request, 'alunos/detalhes.html', {'turma': turma, 'aluno': aluno, 'notas': notas, 'recuperacoes': recuperacoes})


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
    avaliacoes = turma.processos_avaliativos.select_related('disciplina').prefetch_related('arquivos')
    grupos_planejamento = _grupos_planejamento(avaliacoes)
    return render(request, 'avaliacoes/lista.html', {'turma': turma, 'avaliacoes': avaliacoes, 'grupos_planejamento': grupos_planejamento})


@login_required
def avaliacao_criar(request, turma_id):
    turma = get_object_or_404(Turma.objects.filter(professor=request.user), id=turma_id)
    form = ProcessoAvaliativoForm(request.POST or None, request.FILES or None, turma=turma)
    if request.method == 'POST' and form.is_valid():
        avaliacao = form.save(commit=False)
        avaliacao.turma = turma
        avaliacao.save()
        for arquivo in form.cleaned_data.get('anexos') or []:
            Arquivo.objects.create(atividade=avaliacao, arquivo=arquivo)
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
    form = ProcessoAvaliativoForm(request.POST or None, request.FILES or None, instance=avaliacao, turma=turma)
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
    recuperacoes = {
        (recuperacao.aluno_id, recuperacao.periodo): recuperacao
        for recuperacao in Recuperacao.objects.filter(aluno__in=alunos, disciplina=disciplina)
    } if disciplina else {}
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

            if disciplina:
                for tipo_periodo, periodo in {
                    (_tipo_periodo_registro(avaliacao), _periodo_registro(avaliacao))
                    for avaliacao in avaliacoes
                } or {(disciplina.tipo_periodo, 'ANUAL')}:
                    rec_valor = (request.POST.get(f'recuperacao_{aluno.id}_{periodo}') or '').strip().replace(',', '.')
                    par_valor = (request.POST.get(f'paralela_{aluno.id}_{periodo}') or '').strip().replace(',', '.')
                    rec_obj = Recuperacao.objects.filter(aluno=aluno, disciplina=disciplina, periodo=periodo).first()
                    if not rec_valor and not par_valor:
                        if rec_obj:
                            rec_obj.delete()
                        continue
                    rec_obj = rec_obj or Recuperacao(aluno=aluno, disciplina=disciplina, periodo=periodo)
                    try:
                        rec_obj.nota_recuperacao = Decimal(rec_valor) if rec_valor else None
                        rec_obj.nota_paralela = Decimal(par_valor) if par_valor else None
                    except InvalidOperation:
                        messages.error(request, f'Nota de recuperacao/paralela invalida para {aluno.nome}.')
                        houve_erro = True
                        continue
                    try:
                        rec_obj.full_clean()
                    except ValidationError as erro:
                        mensagens = []
                        for erros_campo in erro.message_dict.values():
                            mensagens.extend(erros_campo)
                        messages.error(request, f'{aluno.nome}: {" ".join(mensagens)}')
                        houve_erro = True
                    else:
                        rec_obj.save()

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
    }
    if not chaves_periodo and disciplina:
        chaves_periodo = {(disciplina.tipo_periodo, codigo) for codigo, _ in disciplina.periodos_disponiveis()}
    chaves_periodo = chaves_periodo or {('ANUAL', 'ANUAL')}

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
        total_valor_grupo = sum((avaliacao.valor_maximo for avaliacao in avaliacoes_grupo), Decimal('0'))
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
                cells.append({'avaliacao': avaliacao, 'nota': nota})

            presenca_dados = resumo_presencas.get(aluno.id, {'total_aulas': 0, 'presencas': 0, 'faltas': 0, 'percentual': None})
            soma_notas = sum(notas_media, Decimal('0')) if notas_media else None
            recuperacao = recuperacoes.get((aluno.id, grupo_periodo))
            media_periodo = _media_periodo(soma_notas, total_valor_grupo, disciplina.nota_total if disciplina else Decimal('10.00'))
            media_final = _media_com_recuperacao(media_periodo, recuperacao, disciplina.nota_total if disciplina else Decimal('10.00'))
            if media_final is not None:
                medias_grafico.setdefault(aluno.id, []).append(media_final)
            frequencia = presenca_dados.get('percentual')
            aulas_concluidas = aulas_previstas > 0 and total_aulas >= aulas_previstas
            situacao, badge = _situacao_academica(media_final, frequencia, media_aprovacao, aulas_concluidas)
            linhas.append({
                'aluno': aluno,
                'registro': registro,
                'presenca': presenca_dados,
                'notas': cells,
                'soma': soma_notas,
                'media': media_periodo,
                'recuperacao': recuperacao,
                'media_final': media_final,
                'situacao': situacao,
                'badge': badge,
            })

        grupos.append({
            'titulo': _titulo_periodo(grupo_tipo, grupo_periodo),
            'tipo_periodo': grupo_tipo,
            'periodo': grupo_periodo,
            'badge': PERIODO_BADGES.get(grupo_tipo, 'text-bg-secondary'),
            'avaliacoes': avaliacoes_grupo,
            'total_valor': total_valor_grupo,
            'linhas': linhas,
        })

    medias_alunos = []
    for aluno in alunos:
        notas_aluno = medias_grafico.get(aluno.id, [])
        if notas_aluno:
            media_aluno = (sum(notas_aluno, Decimal('0')) / len(notas_aluno)).quantize(Decimal('0.01'))
            medias_alunos.append({'aluno': aluno.nome, 'media': float(media_aluno)})
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
    aulas_previstas = disciplina.quantidade_aulas if disciplina else 0
    aulas_restantes = max(aulas_previstas - total_aulas, 0)
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
        percentual = _percentual_presenca(presencas_total, total_aulas)
        linhas.append({
            'aluno': aluno,
            'presencas': cells,
            'faltas': faltas,
            'percentual': percentual,
            'situacao_frequencia': 'Baixa frequencia' if percentual is not None and percentual < Decimal('75.00') else 'Regular',
        })

    return render(request, 'turmas/chamada.html', {
        'turma': turma,
        'disciplina': disciplina,
        'disciplinas_filtro': [
            {'id': str(item.id), 'nome': item.nome, 'selected': disciplina and item.id == disciplina.id}
            for item in disciplinas
        ],
        'aulas': aulas,
        'total_aulas': total_aulas,
        'aulas_previstas': aulas_previstas,
        'aulas_restantes': aulas_restantes,
        'linhas': linhas,
    })


@login_required
def registrar_aula(request, turma_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    form = AulaForm(request.POST or None, request.FILES or None, turma=turma)
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
            for arquivo in form.cleaned_data.get('anexos') or []:
                Arquivo.objects.create(aula=aula, arquivo=arquivo)
            if _salvar_presencas_aula(request, turma, aula):
                messages.success(request, 'Aula registrada com sucesso.')
                return redirect(f'/turmas/{turma.id}/chamada/?disciplina={aula.disciplina_id}')
    return render(request, 'turmas/aula_form.html', {'turma': turma, 'form': form, 'linhas': linhas, 'acao': 'Registrar aula'})


@login_required
def editar_chamada(request, turma_id, aula_id):
    turma = get_object_or_404(Turma, id=turma_id, professor=request.user)
    aula = get_object_or_404(Aula.objects.filter(turma=turma), id=aula_id)
    form = AulaForm(request.POST or None, request.FILES or None, instance=aula, turma=turma)
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
            for arquivo in form.cleaned_data.get('anexos') or []:
                Arquivo.objects.create(aula=aula, arquivo=arquivo)
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
