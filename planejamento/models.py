from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Turma(models.Model):
    TURNO_CHOICES = [
        ('MATUTINO', 'Matutino'),
        ('VESPERTINO', 'Vespertino'),
        ('NOTURNO', 'Noturno'),
        ('INTEGRAL', 'Integral'),
    ]

    professor = models.ForeignKey(User, verbose_name='professor', on_delete=models.CASCADE)
    nome = models.CharField('nome', max_length=100)
    ano_letivo = models.PositiveIntegerField('ano letivo')
    turno = models.CharField('turno', max_length=20, choices=TURNO_CHOICES)
    descricao = models.TextField('descricao', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Turma'
        verbose_name_plural = 'Turmas'
        ordering = ['-ano_letivo', 'nome']

    def __str__(self):
        return f'{self.nome} - {self.ano_letivo}'

    def clean(self):
        super().clean()
        nome_normalizado = ' '.join((self.nome or '').split())
        if not nome_normalizado:
            raise ValidationError({'nome': 'Informe o nome da turma.'})
        self.nome = nome_normalizado


class Disciplina(models.Model):
    turma = models.ForeignKey(
        Turma,
        verbose_name='turma',
        on_delete=models.CASCADE,
        related_name='disciplinas',
        null=True,
        blank=True,
    )
    professor = models.ForeignKey(User, verbose_name='professor', on_delete=models.CASCADE, null=True, blank=True)
    nome = models.CharField('nome', max_length=120)
    descricao = models.TextField('descricao', blank=True)
    carga_horaria = models.PositiveIntegerField('carga horaria')
    ano_escolar = models.CharField('ano escolar', max_length=50)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Disciplina'
        verbose_name_plural = 'Disciplinas'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ConteudoProgramatico(models.Model):
    STATUS_CHOICES = [
        ('PENDENTE', 'Pendente'),
        ('EM_ANDAMENTO', 'Em andamento'),
        ('CONCLUIDO', 'Concluido'),
        ('ATRASADO', 'Atrasado'),
    ]

    BIMESTRE_CHOICES = [
        (1, '1º bimestre'),
        (2, '2º bimestre'),
        (3, '3º bimestre'),
        (4, '4º bimestre'),
    ]

    TIPO_PERIODO_CHOICES = [
        ('BIMESTRE', 'Bimestre'),
        ('TRIMESTRE', 'Trimestre'),
        ('SEMESTRE', 'Semestre'),
        ('ANUAL', 'Anual'),
    ]

    PERIODO_CHOICES = [
        ('1_BIMESTRE', '1º bimestre'),
        ('2_BIMESTRE', '2º bimestre'),
        ('3_BIMESTRE', '3º bimestre'),
        ('4_BIMESTRE', '4º bimestre'),
        ('1_TRIMESTRE', '1º trimestre'),
        ('2_TRIMESTRE', '2º trimestre'),
        ('3_TRIMESTRE', '3º trimestre'),
        ('1_SEMESTRE', '1º semestre'),
        ('2_SEMESTRE', '2º semestre'),
        ('ANUAL', 'Anual'),
    ]

    disciplina = models.ForeignKey(
        Disciplina,
        verbose_name='disciplina',
        on_delete=models.CASCADE,
        related_name='conteudos_programaticos',
    )
    titulo = models.CharField('titulo', max_length=160)
    descricao = models.TextField('descricao', blank=True)
    unidade = models.CharField('unidade', max_length=80)
    bimestre = models.PositiveSmallIntegerField('bimestre', choices=BIMESTRE_CHOICES, null=True, blank=True)
    tipo_periodo = models.CharField(
        'tipo de periodo',
        max_length=20,
        choices=TIPO_PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    periodo = models.CharField(
        'periodo',
        max_length=20,
        choices=PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default='PENDENTE')
    data_inicio = models.DateField('data de inicio', null=True, blank=True)
    data_fim = models.DateField('data de fim', null=True, blank=True)
    arquivo = models.FileField('arquivo', upload_to='atividades/', blank=True, null=True)
    concluido = models.BooleanField('concluido', default=False)
    data_conclusao = models.DateTimeField('data de conclusao', null=True, blank=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Conteudo programatico'
        verbose_name_plural = 'Conteudos programaticos'
        ordering = ['disciplina__nome', 'bimestre', 'unidade', 'titulo']

    def __str__(self):
        return self.titulo

    def atualizar_status(self, salvar=True):
        hoje = timezone.localdate()
        update_fields = ['status']

        if self.concluido:
            self.status = 'CONCLUIDO'
            if not self.data_conclusao:
                self.data_conclusao = timezone.now()
                update_fields.append('data_conclusao')
        elif self.data_inicio and hoje < self.data_inicio:
            self.status = 'PENDENTE'
        elif self.data_inicio and self.data_fim and self.data_inicio <= hoje <= self.data_fim:
            self.status = 'EM_ANDAMENTO'
        elif self.data_fim and hoje > self.data_fim:
            self.status = 'ATRASADO'
        elif self.data_inicio and hoje >= self.data_inicio:
            self.status = 'EM_ANDAMENTO'
        else:
            self.status = 'PENDENTE'

        if salvar:
            self.save(update_fields=update_fields)

        return self.status

    def marcar_como_concluido(self):
        self.concluido = True
        self.status = 'CONCLUIDO'
        self.data_conclusao = timezone.now()
        self.save(update_fields=['concluido', 'status', 'data_conclusao'])

    def get_periodo_planejamento_display(self):
        if self.periodo:
            return self.get_periodo_display()
        if self.bimestre:
            return self.get_bimestre_display()
        return '-'

    def get_status_badge_class(self):
        classes = {
            'PENDENTE': 'text-bg-secondary',
            'EM_ANDAMENTO': 'text-bg-primary',
            'CONCLUIDO': 'text-bg-success',
            'ATRASADO': 'text-bg-danger',
        }
        return classes.get(self.status, 'text-bg-secondary')


class AnotacaoTurma(models.Model):
    turma = models.ForeignKey(Turma, verbose_name='turma', on_delete=models.CASCADE, related_name='anotacoes')
    professor = models.ForeignKey(User, verbose_name='professor', on_delete=models.CASCADE)
    titulo = models.CharField('titulo', max_length=160)
    descricao = models.TextField('descricao')
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Anotacao da turma'
        verbose_name_plural = 'Anotacoes da turma'
        ordering = ['-created_at', 'titulo']

    def __str__(self):
        return self.titulo


class Alerta(models.Model):
    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ]

    TIPO_CHOICES = [
        ('INICIO', 'Inicio'),
        ('ATRASO', 'Atraso'),
        ('SISTEMA', 'Sistema'),
    ]

    usuario = models.ForeignKey(User, verbose_name='usuario', on_delete=models.CASCADE, null=True, blank=True)
    turma = models.ForeignKey(
        Turma,
        verbose_name='turma',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alertas',
    )
    conteudo = models.ForeignKey(
        ConteudoProgramatico,
        verbose_name='conteudo',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alertas',
    )
    titulo = models.CharField('titulo', max_length=120)
    mensagem = models.TextField('mensagem')
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_CHOICES, default='SISTEMA')
    prioridade = models.CharField('prioridade', max_length=10, choices=PRIORIDADE_CHOICES, default='media')
    lido = models.BooleanField('lido', default=False)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Alerta'
        verbose_name_plural = 'Alertas'
        ordering = ['-created_at', 'prioridade']

    def __str__(self):
        return self.titulo

    def get_badge_class(self):
        classes = {
            'INICIO': 'text-bg-primary',
            'ATRASO': 'text-bg-danger',
            'SISTEMA': 'text-bg-warning',
        }
        if self.lido:
            return 'text-bg-secondary'
        return classes.get(self.tipo, 'text-bg-secondary')

    def get_icon_class(self):
        icons = {
            'INICIO': 'bi bi-play-circle',
            'ATRASO': 'bi bi-exclamation-triangle',
            'SISTEMA': 'bi bi-info-circle',
        }
        return icons.get(self.tipo, 'bi bi-bell')


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(User, verbose_name='usuario', on_delete=models.CASCADE)
    foto = models.ImageField('foto', upload_to='perfil/fotos/', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de usuario'
        verbose_name_plural = 'Perfis de usuarios'
        ordering = ['usuario__username']

    def __str__(self):
        return self.usuario.username
