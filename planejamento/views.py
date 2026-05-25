from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    AlterarSenhaForm,
    AnotacaoTurmaForm,
    ConteudoProgramaticoForm,
    DisciplinaForm,
    PerfilUsuarioForm,
    TurmaForm,
    UsuarioPerfilForm,
)
from .models import Alerta, AnotacaoTurma, ConteudoProgramatico, Disciplina, PerfilUsuario, Turma
from .utils import alertas_gerais_usuario, verificar_alertas_conteudos


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
    context = {
        'turma': turma,
        'disciplinas': disciplinas[:6],
        'conteudos': conteudos[:6],
        'alertas': alertas[:6],
        'anotacoes': anotacoes[:6],
        'total_disciplinas': disciplinas.count(),
        'total_conteudos': conteudos.count(),
        'total_alertas': alertas.count(),
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
    return render(request, 'conteudos/lista.html', {'conteudos': conteudos})


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
    return render(request, 'conteudos/lista.html', {'conteudos': conteudos, 'turma': turma})


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


def logout_usuario(request):
    logout(request)
    return redirect('login')
