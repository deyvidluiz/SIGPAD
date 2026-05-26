from django.contrib import admin

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
    PresencaAluno,
    Presenca,
    ProcessoAvaliativo,
    RegistroAlunoTurma,
    Turma,
)


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


@admin.register(Aluno)
class AlunoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'turma', 'matricula', 'ativo', 'created_at']
    list_filter = ['turma', 'ativo']
    search_fields = ['nome', 'matricula', 'turma__nome']


@admin.register(ProcessoAvaliativo)
class ProcessoAvaliativoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'turma', 'disciplina', 'tipo', 'valor_maximo', 'periodo', 'data']
    list_filter = ['turma', 'disciplina', 'tipo', 'tipo_periodo', 'periodo']
    search_fields = ['titulo', 'descricao', 'turma__nome', 'disciplina__nome']


@admin.register(NotaAluno)
class NotaAlunoAdmin(admin.ModelAdmin):
    list_display = ['aluno', 'processo', 'nota', 'updated_at']
    list_filter = ['processo__turma', 'processo', 'aluno__turma']
    search_fields = ['aluno__nome', 'processo__titulo', 'observacao']


@admin.register(Chamada)
class ChamadaAdmin(admin.ModelAdmin):
    list_display = ['turma', 'disciplina', 'data', 'periodo', 'descricao', 'created_at']
    list_filter = ['turma', 'disciplina', 'tipo_periodo', 'periodo', 'data']
    search_fields = ['turma__nome', 'disciplina__nome', 'descricao']


@admin.register(PresencaAluno)
class PresencaAlunoAdmin(admin.ModelAdmin):
    list_display = ['aluno', 'chamada', 'presente']
    list_filter = ['presente', 'chamada__turma', 'chamada__disciplina']
    search_fields = ['aluno__nome', 'chamada__descricao', 'observacao']


@admin.register(Aula)
class AulaAdmin(admin.ModelAdmin):
    list_display = ['data', 'turma', 'disciplina', 'quantidade_aulas', 'created_at']
    list_filter = ['turma', 'disciplina', 'data']
    search_fields = ['conteudo_aplicado', 'observacao', 'turma__nome', 'disciplina__nome']


@admin.register(Presenca)
class PresencaAdmin(admin.ModelAdmin):
    list_display = ['aluno', 'aula', 'presente']
    list_filter = ['presente', 'aula__turma', 'aula__disciplina']
    search_fields = ['aluno__nome', 'aula__conteudo_aplicado', 'observacao']


@admin.register(RegistroAlunoTurma)
class RegistroAlunoTurmaAdmin(admin.ModelAdmin):
    list_display = ['aluno', 'turma', 'disciplina', 'total_aulas', 'total_faltas', 'updated_at']
    list_filter = ['turma', 'disciplina']
    search_fields = ['aluno__nome', 'turma__nome', 'observacao']


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'turma', 'prioridade', 'created_at']
    list_filter = ['prioridade', 'turma']
    search_fields = ['titulo', 'mensagem']


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'created_at']
    search_fields = ['usuario__username', 'usuario__first_name', 'usuario__last_name', 'usuario__email']
