from django.contrib.auth.views import LoginView
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('turmas/', views.turma_lista, name='turma_lista'),
    path('turmas/nova/', views.turma_criar, name='turma_criar'),
    path('turmas/<int:id>/', views.turma_detalhes, name='turma_detalhes'),
    path('turmas/editar/<int:id>/', views.turma_editar, name='turma_editar'),
    path('turmas/deletar/<int:id>/', views.turma_deletar, name='turma_deletar'),
    path('turmas/<int:turma_id>/disciplinas/', views.turma_disciplina_lista, name='turma_disciplina_lista'),
    path('turmas/<int:turma_id>/disciplinas/nova/', views.turma_disciplina_criar, name='turma_disciplina_criar'),
    path('turmas/<int:turma_id>/conteudos/', views.turma_conteudo_lista, name='turma_conteudo_lista'),
    path('turmas/<int:turma_id>/conteudos/novo/', views.turma_conteudo_criar, name='turma_conteudo_criar'),
    path('turmas/<int:turma_id>/anotacoes/', views.turma_anotacao_lista, name='turma_anotacao_lista'),
    path('turmas/<int:turma_id>/anotacoes/nova/', views.turma_anotacao_criar, name='turma_anotacao_criar'),
    path('turmas/<int:turma_id>/anotacoes/editar/<int:id>/', views.turma_anotacao_editar, name='turma_anotacao_editar'),
    path('turmas/<int:turma_id>/anotacoes/deletar/<int:id>/', views.turma_anotacao_deletar, name='turma_anotacao_deletar'),
    path('turmas/<int:turma_id>/alertas/', views.turma_alerta_lista, name='turma_alerta_lista'),
    path('disciplinas/', views.disciplina_lista, name='disciplina_lista'),
    path('disciplinas/nova/', views.disciplina_criar, name='disciplina_criar'),
    path('disciplinas/<int:id>/', views.disciplina_detalhes, name='disciplina_detalhes'),
    path('disciplinas/editar/<int:id>/', views.disciplina_editar, name='disciplina_editar'),
    path('disciplinas/deletar/<int:id>/', views.disciplina_deletar, name='disciplina_deletar'),
    path('conteudos/', views.conteudo_lista, name='conteudo_lista'),
    path('conteudos/novo/', views.conteudo_criar, name='conteudo_criar'),
    path('conteudos/<int:id>/', views.conteudo_detalhes, name='conteudo_detalhes'),
    path('conteudos/editar/<int:id>/', views.conteudo_editar, name='conteudo_editar'),
    path('conteudos/deletar/<int:id>/', views.conteudo_deletar, name='conteudo_deletar'),
    path('conteudos/concluir/<int:id>/', views.conteudo_concluir, name='conteudo_concluir'),
    path('relatorios/', views.relatorio_lista, name='relatorio_lista'),
    path('alertas/', views.alerta_lista, name='alerta_lista'),
    path('alertas/lido/<int:id>/', views.alerta_lido, name='alerta_lido'),
    path('perfil/', views.perfil_usuario, name='perfil_usuario'),
    path('perfil/editar/', views.editar_perfil, name='editar_perfil'),
    path('perfil/alterar-senha/', views.alterar_senha, name='alterar_senha'),
    path('login/', LoginView.as_view(template_name='registration/login.html', authentication_form=LoginForm), name='login'),
    path('logout/', views.logout_usuario, name='logout'),
]
