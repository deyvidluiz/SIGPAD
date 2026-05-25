from django.contrib import admin

from .models import Alerta, AnotacaoTurma, ConteudoProgramatico, Disciplina, PerfilUsuario, Turma


@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'ano_letivo', 'turno', 'professor', 'created_at']
    list_filter = ['ano_letivo', 'turno', 'professor']
    search_fields = ['nome', 'professor__username', 'professor__first_name', 'professor__last_name']


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'turma', 'professor', 'ano_escolar', 'carga_horaria', 'created_at']
    list_filter = ['turma', 'professor']
    search_fields = ['nome', 'ano_escolar', 'turma__nome']


@admin.register(ConteudoProgramatico)
class ConteudoProgramaticoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'disciplina', 'unidade', 'bimestre', 'status', 'data_inicio', 'data_fim']
    list_filter = ['status', 'bimestre', 'disciplina']
    search_fields = ['titulo', 'descricao', 'disciplina__nome']


@admin.register(AnotacaoTurma)
class AnotacaoTurmaAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'turma', 'professor', 'created_at']
    list_filter = ['turma', 'professor']
    search_fields = ['titulo', 'descricao', 'turma__nome']


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'turma', 'prioridade', 'created_at']
    list_filter = ['prioridade', 'turma']
    search_fields = ['titulo', 'mensagem']


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'created_at']
    search_fields = ['usuario__username', 'usuario__first_name', 'usuario__last_name', 'usuario__email']
