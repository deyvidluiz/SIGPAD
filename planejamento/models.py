from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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

TIPO_PERIODO_CHOICES = [
    ('BIMESTRE', 'Bimestre'),
    ('TRIMESTRE', 'Trimestre'),
    ('SEMESTRE', 'Semestre'),
    ('ANUAL', 'Anual'),
]

PERIODOS_POR_TIPO = {
    'BIMESTRE': [
        ('1_BIMESTRE', '1º bimestre'),
        ('2_BIMESTRE', '2º bimestre'),
        ('3_BIMESTRE', '3º bimestre'),
        ('4_BIMESTRE', '4º bimestre'),
    ],
    'TRIMESTRE': [
        ('1_TRIMESTRE', '1º trimestre'),
        ('2_TRIMESTRE', '2º trimestre'),
        ('3_TRIMESTRE', '3º trimestre'),
    ],
    'SEMESTRE': [
        ('1_SEMESTRE', '1º semestre'),
        ('2_SEMESTRE', '2º semestre'),
    ],
    'ANUAL': [
        ('ANUAL', 'Anual'),
    ],
}


class Professor(User):
    class Meta:
        proxy = True
        verbose_name = 'Professor'
        verbose_name_plural = 'Professores'


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
    TIPO_PERIODO_CHOICES = TIPO_PERIODO_CHOICES

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
    tipo_periodo = models.CharField(
        'tipo de periodo',
        max_length=20,
        choices=TIPO_PERIODO_CHOICES,
        default='BIMESTRE',
    )
    quantidade_aulas = models.PositiveIntegerField('quantidade de aulas', default=0)
    nota_total = models.DecimalField('nota total por periodo', max_digits=5, decimal_places=2, default=10)
    media_aprovacao = models.DecimalField('media de aprovacao', max_digits=5, decimal_places=2, default=6)
    ano_escolar = models.CharField('ano escolar', max_length=50)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Disciplina'
        verbose_name_plural = 'Disciplinas'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if not self.quantidade_aulas:
            self.quantidade_aulas = self.carga_horaria

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.criar_periodos_letivos()

    def criar_periodos_letivos(self):
        for ordem, (codigo, nome) in enumerate(PERIODOS_POR_TIPO.get(self.tipo_periodo, []), start=1):
            PeriodoLetivo.objects.get_or_create(
                disciplina=self,
                codigo=codigo,
                defaults={'tipo': self.tipo_periodo, 'nome': nome, 'ordem': ordem},
            )

    @property
    def aulas_dadas(self):
        return self.aulas.aggregate(total=models.Sum('quantidade_aulas'))['total'] or 0

    @property
    def aulas_restantes(self):
        return max(self.quantidade_aulas - self.aulas_dadas, 0)

    @property
    def ano_letivo(self):
        return self.turma.ano_letivo if self.turma_id else None

    def periodos_disponiveis(self):
        return PERIODOS_POR_TIPO.get(self.tipo_periodo, [])


class PeriodoLetivo(models.Model):
    disciplina = models.ForeignKey(Disciplina, verbose_name='disciplina', on_delete=models.CASCADE, related_name='periodos_letivos')
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_PERIODO_CHOICES)
    codigo = models.CharField('codigo', max_length=20, choices=PERIODO_CHOICES)
    nome = models.CharField('nome', max_length=80)
    ordem = models.PositiveSmallIntegerField('ordem', default=1)
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'Periodo letivo'
        verbose_name_plural = 'Periodos letivos'
        ordering = ['disciplina__nome', 'ordem']
        constraints = [
            models.UniqueConstraint(fields=['disciplina', 'codigo'], name='periodo_unico_por_disciplina'),
        ]

    def __str__(self):
        return f'{self.disciplina} - {self.nome}'


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

    TIPO_PERIODO_CHOICES = TIPO_PERIODO_CHOICES

    PERIODO_CHOICES = PERIODO_CHOICES

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


class Aluno(models.Model):
    turma = models.ForeignKey(Turma, verbose_name='turma', on_delete=models.CASCADE, related_name='alunos')
    nome = models.CharField('nome', max_length=150)
    matricula = models.CharField('matricula', max_length=50, blank=True, null=True)
    ativo = models.BooleanField('ativo', default=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Aluno'
        verbose_name_plural = 'Alunos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ProcessoAvaliativo(models.Model):
    STATUS_CHOICES = [
        ('A_REALIZAR', 'A realizar'),
        ('EM_ANDAMENTO', 'Em andamento'),
        ('CORRIGIDA', 'Corrigida'),
        ('FINALIZADA', 'Finalizada'),
    ]

    turma = models.ForeignKey(
        Turma,
        verbose_name='turma',
        on_delete=models.CASCADE,
        related_name='processos_avaliativos',
    )
    disciplina = models.ForeignKey(
        Disciplina,
        verbose_name='disciplina',
        on_delete=models.CASCADE,
        related_name='processos_avaliativos',
    )
    titulo = models.CharField('titulo', max_length=150)
    descricao = models.TextField('conteudo aplicado', blank=True, null=True)
    observacao = models.TextField('observacao', blank=True, null=True)
    tipo = models.CharField('tipo', max_length=100)
    valor_maximo = models.DecimalField('valor maximo', max_digits=5, decimal_places=2)
    tipo_periodo = models.CharField(
        'tipo de periodo',
        max_length=20,
        choices=ConteudoProgramatico.TIPO_PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    periodo = models.CharField(
        'periodo',
        max_length=20,
        choices=ConteudoProgramatico.PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    data_abertura = models.DateField('data de abertura', blank=True, null=True)
    data_fechamento = models.DateField('data de fechamento', blank=True, null=True)
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default='A_REALIZAR')
    arquivo = models.FileField('arquivo', upload_to='atividades/', blank=True, null=True)
    data = models.DateField('data', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Processo avaliativo'
        verbose_name_plural = 'Processos avaliativos'
        ordering = ['-data', 'disciplina__nome', 'titulo']

    def __str__(self):
        return self.titulo

    def get_tipo_display(self):
        return self.tipo

    def clean(self):
        super().clean()
        if self.disciplina_id and self.turma_id and self.disciplina.turma_id != self.turma_id:
            raise ValidationError({'disciplina': 'A disciplina deve pertencer a turma selecionada.'})
        if self.valor_maximo is not None and self.valor_maximo <= 0:
            raise ValidationError({'valor_maximo': 'O valor maximo deve ser maior que zero.'})
        if self.disciplina_id:
            self.tipo_periodo = self.disciplina.tipo_periodo
            if self.tipo_periodo == 'ANUAL':
                self.periodo = 'ANUAL'
            if self.periodo and not self.periodo.endswith(self.disciplina.tipo_periodo) and self.periodo != 'ANUAL':
                raise ValidationError({'periodo': 'O periodo deve respeitar o tipo de periodo da disciplina.'})
        if self.data_abertura and self.data_fechamento and self.data_abertura > self.data_fechamento:
            raise ValidationError({'data_fechamento': 'A data de fechamento deve ser posterior a abertura.'})

    def save(self, *args, **kwargs):
        if self.disciplina_id:
            self.tipo_periodo = self.disciplina.tipo_periodo
            if self.tipo_periodo == 'ANUAL':
                self.periodo = 'ANUAL'
        if self.status not in ['CORRIGIDA', 'FINALIZADA']:
            self.atualizar_status_automatico(salvar=False)
        super().save(*args, **kwargs)

    def get_periodo_planejamento_display(self):
        if self.periodo:
            return self.get_periodo_display()
        return 'Anual'

    def atualizar_status_automatico(self, salvar=True):
        hoje = timezone.localdate()
        if self.status in ['CORRIGIDA', 'FINALIZADA']:
            return self.status
        if self.data_abertura and hoje < self.data_abertura:
            self.status = 'A_REALIZAR'
        elif self.data_fechamento and hoje > self.data_fechamento:
            self.status = 'FINALIZADA'
        else:
            self.status = 'EM_ANDAMENTO'
        if salvar:
            self.save(update_fields=['status'])
        return self.status


class Atividade(ProcessoAvaliativo):
    class Meta:
        proxy = True
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'


class NotaAluno(models.Model):
    aluno = models.ForeignKey(Aluno, verbose_name='aluno', on_delete=models.CASCADE, related_name='notas')
    processo = models.ForeignKey(
        ProcessoAvaliativo,
        verbose_name='processo avaliativo',
        on_delete=models.CASCADE,
        related_name='notas',
    )
    nota = models.DecimalField('nota', max_digits=5, decimal_places=2)
    observacao = models.TextField('observacao', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Nota do aluno'
        verbose_name_plural = 'Notas dos alunos'
        ordering = ['aluno__nome', 'processo__titulo']
        constraints = [
            models.UniqueConstraint(fields=['aluno', 'processo'], name='nota_unica_por_aluno_processo'),
        ]

    def __str__(self):
        return f'{self.aluno} - {self.processo}: {self.nota}'

    def clean(self):
        super().clean()
        if self.nota is not None and self.nota < 0:
            raise ValidationError({'nota': 'A nota nao pode ser menor que zero.'})
        if self.processo_id and self.nota is not None and self.nota > self.processo.valor_maximo:
            raise ValidationError({'nota': 'A nota nao pode ser maior que o valor maximo.'})
        if self.aluno_id and self.processo_id and self.aluno.turma_id != self.processo.turma_id:
            raise ValidationError({'aluno': 'O aluno deve pertencer a turma da avaliacao.'})


class Nota(NotaAluno):
    class Meta:
        proxy = True
        verbose_name = 'Nota'
        verbose_name_plural = 'Notas'


class Recuperacao(models.Model):
    aluno = models.ForeignKey(Aluno, verbose_name='aluno', on_delete=models.CASCADE, related_name='recuperacoes')
    disciplina = models.ForeignKey(Disciplina, verbose_name='disciplina', on_delete=models.CASCADE, related_name='recuperacoes')
    periodo = models.CharField('periodo', max_length=20, choices=PERIODO_CHOICES, default='ANUAL')
    nota_recuperacao = models.DecimalField('nota de recuperacao', max_digits=5, decimal_places=2, blank=True, null=True)
    nota_paralela = models.DecimalField('nota paralela', max_digits=5, decimal_places=2, blank=True, null=True)
    observacao = models.TextField('observacao', blank=True, null=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Recuperacao'
        verbose_name_plural = 'Recuperacoes'
        ordering = ['aluno__nome', 'disciplina__nome', 'periodo']
        constraints = [
            models.UniqueConstraint(fields=['aluno', 'disciplina', 'periodo'], name='recuperacao_unica_por_aluno_disciplina_periodo'),
        ]

    def __str__(self):
        return f'{self.aluno} - {self.disciplina} - {self.periodo}'

    @property
    def melhor_nota(self):
        notas = [nota for nota in [self.nota_recuperacao, self.nota_paralela] if nota is not None]
        return max(notas) if notas else None

    def clean(self):
        super().clean()
        if self.aluno_id and self.disciplina_id and self.aluno.turma_id != self.disciplina.turma_id:
            raise ValidationError({'aluno': 'O aluno deve pertencer a turma da disciplina.'})
        for campo in ['nota_recuperacao', 'nota_paralela']:
            nota = getattr(self, campo)
            if nota is not None and (nota < 0 or nota > self.disciplina.nota_total):
                raise ValidationError({campo: 'A nota deve estar dentro da nota total da disciplina.'})


class Chamada(models.Model):
    turma = models.ForeignKey(Turma, verbose_name='turma', on_delete=models.CASCADE, related_name='chamadas')
    disciplina = models.ForeignKey(
        Disciplina,
        verbose_name='disciplina',
        on_delete=models.CASCADE,
        related_name='chamadas',
    )
    data = models.DateField('data')
    tipo_periodo = models.CharField(
        'tipo de periodo',
        max_length=20,
        choices=ConteudoProgramatico.TIPO_PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    periodo = models.CharField(
        'periodo',
        max_length=20,
        choices=ConteudoProgramatico.PERIODO_CHOICES,
        null=True,
        blank=True,
    )
    descricao = models.CharField('descricao', max_length=150, blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Chamada'
        verbose_name_plural = 'Chamadas'
        ordering = ['-data', 'disciplina__nome']

    def __str__(self):
        return f'{self.disciplina} - {self.data:%d/%m/%Y}'

    def clean(self):
        super().clean()
        if self.disciplina_id and self.turma_id and self.disciplina.turma_id != self.turma_id:
            raise ValidationError({'disciplina': 'A disciplina deve pertencer a turma selecionada.'})

    def get_periodo_planejamento_display(self):
        if self.periodo:
            return self.get_periodo_display()
        return 'Anual'


class PresencaAluno(models.Model):
    chamada = models.ForeignKey(
        Chamada,
        verbose_name='chamada',
        on_delete=models.CASCADE,
        related_name='presencas',
    )
    aluno = models.ForeignKey(
        Aluno,
        verbose_name='aluno',
        on_delete=models.CASCADE,
        related_name='presencas_chamadas',
    )
    presente = models.BooleanField('presente', default=True)
    observacao = models.TextField('observacao', blank=True, null=True)

    class Meta:
        verbose_name = 'Presenca do aluno'
        verbose_name_plural = 'Presencas dos alunos'
        ordering = ['aluno__nome']
        constraints = [
            models.UniqueConstraint(fields=['chamada', 'aluno'], name='presenca_unica_por_chamada_aluno'),
        ]

    def __str__(self):
        status = 'Presente' if self.presente else 'Faltou'
        return f'{self.aluno} - {self.chamada}: {status}'

    def clean(self):
        super().clean()
        if self.aluno_id and self.chamada_id and self.aluno.turma_id != self.chamada.turma_id:
            raise ValidationError({'aluno': 'O aluno deve pertencer a turma da chamada.'})


class Aula(models.Model):
    turma = models.ForeignKey(Turma, verbose_name='turma', on_delete=models.CASCADE, related_name='aulas')
    disciplina = models.ForeignKey(Disciplina, verbose_name='disciplina', on_delete=models.CASCADE, related_name='aulas')
    data = models.DateField('data da aula')
    quantidade_aulas = models.PositiveIntegerField('quantidade de aulas', default=1)
    conteudo_aplicado = models.TextField('conteudo aplicado')
    observacao = models.TextField('observacao', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Aula'
        verbose_name_plural = 'Aulas'
        ordering = ['data', 'disciplina__nome']

    def __str__(self):
        return f'{self.data:%d/%m/%Y} - {self.disciplina} - {self.turma}'

    def clean(self):
        super().clean()
        if self.disciplina_id and self.turma_id and self.disciplina.turma_id != self.turma_id:
            raise ValidationError({'disciplina': 'A disciplina deve pertencer a turma da aula.'})
        if self.quantidade_aulas < 1:
            raise ValidationError({'quantidade_aulas': 'A quantidade de aulas deve ser maior que zero.'})


class Presenca(models.Model):
    aula = models.ForeignKey(Aula, verbose_name='aula', on_delete=models.CASCADE, related_name='presencas')
    aluno = models.ForeignKey(Aluno, verbose_name='aluno', on_delete=models.CASCADE, related_name='presencas')
    presente = models.BooleanField('presente', default=True)
    observacao = models.TextField('observacao', blank=True, null=True)

    class Meta:
        verbose_name = 'Presenca'
        verbose_name_plural = 'Presencas'
        ordering = ['aluno__nome']
        unique_together = ('aula', 'aluno')

    def __str__(self):
        status = 'Presente' if self.presente else 'Faltou'
        return f'{self.aluno} - {self.aula}: {status}'

    def clean(self):
        super().clean()
        if self.aluno_id and self.aula_id and self.aluno.turma_id != self.aula.turma_id:
            raise ValidationError({'aluno': 'O aluno deve pertencer a turma da aula.'})


class Arquivo(models.Model):
    aula = models.ForeignKey(Aula, verbose_name='aula', on_delete=models.CASCADE, related_name='arquivos', null=True, blank=True)
    atividade = models.ForeignKey(ProcessoAvaliativo, verbose_name='atividade', on_delete=models.CASCADE, related_name='arquivos', null=True, blank=True)
    conteudo = models.ForeignKey(ConteudoProgramatico, verbose_name='conteudo', on_delete=models.CASCADE, related_name='arquivos_extras', null=True, blank=True)
    nome = models.CharField('nome', max_length=180, blank=True)
    arquivo = models.FileField('arquivo', upload_to='academico/')
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Arquivo'
        verbose_name_plural = 'Arquivos'
        ordering = ['-created_at', 'nome']

    def __str__(self):
        return self.nome or self.arquivo.name

    def clean(self):
        super().clean()
        vinculos = [self.aula_id, self.atividade_id, self.conteudo_id]
        if sum(1 for vinculo in vinculos if vinculo) != 1:
            raise ValidationError('Informe exatamente um vinculo para o arquivo.')

    def save(self, *args, **kwargs):
        if not self.nome and self.arquivo:
            self.nome = self.arquivo.name.rsplit('/', 1)[-1]
        super().save(*args, **kwargs)


class RegistroAlunoTurma(models.Model):
    turma = models.ForeignKey(
        Turma,
        verbose_name='turma',
        on_delete=models.CASCADE,
        related_name='registros_alunos',
    )
    aluno = models.ForeignKey(
        Aluno,
        verbose_name='aluno',
        on_delete=models.CASCADE,
        related_name='registros_turma',
    )
    disciplina = models.ForeignKey(
        Disciplina,
        verbose_name='disciplina',
        on_delete=models.CASCADE,
        related_name='registros_alunos',
        null=True,
        blank=True,
    )
    total_aulas = models.PositiveIntegerField('total de aulas', default=0)
    total_faltas = models.PositiveIntegerField('total de faltas', default=0)
    nota1 = models.DecimalField('nota 1', max_digits=5, decimal_places=2, blank=True, null=True)
    nota2 = models.DecimalField('nota 2', max_digits=5, decimal_places=2, blank=True, null=True)
    nota3 = models.DecimalField('nota 3', max_digits=5, decimal_places=2, blank=True, null=True)
    observacao = models.TextField('observacao', blank=True, null=True)
    updated_at = models.DateTimeField('atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Registro do aluno na turma'
        verbose_name_plural = 'Registros dos alunos nas turmas'
        ordering = ['aluno__nome']
        constraints = [
            models.UniqueConstraint(fields=['turma', 'aluno', 'disciplina'], name='registro_unico_por_aluno_turma_disciplina'),
        ]

    def __str__(self):
        return f'{self.aluno} - {self.turma}'

    @property
    def total_presencas(self):
        return max(self.total_aulas - self.total_faltas, 0)

    @property
    def frequencia(self):
        if not self.total_aulas:
            return None
        return (Decimal(self.total_presencas) / Decimal(self.total_aulas) * Decimal('100')).quantize(Decimal('0.01'))

    @property
    def media(self):
        notas = [nota for nota in [self.nota1, self.nota2, self.nota3] if nota is not None]
        if not notas:
            return None
        return (sum(notas, Decimal('0')) / len(notas)).quantize(Decimal('0.01'))

    @property
    def situacao(self):
        media = self.media
        frequencia = self.frequencia
        aulas_previstas = self.disciplina.quantidade_aulas if self.disciplina_id else self.total_aulas
        media_aprovacao = self.disciplina.media_aprovacao if self.disciplina_id else Decimal('6.00')
        if not aulas_previstas or self.total_aulas < aulas_previstas:
            return 'Em andamento'
        media_final = media if media is not None else Decimal('0')
        if frequencia is not None and frequencia < Decimal('75.00') and media_final < media_aprovacao:
            return 'Reprovado por nota e falta'
        if frequencia is not None and frequencia < Decimal('75.00'):
            return 'Reprovado por falta'
        if media_final < media_aprovacao:
            return 'Recuperação/Paralela'
        return 'Aprovado'

    def get_situacao_badge_class(self):
        classes = {
            'Aprovado': 'text-bg-success',
            'Reprovado por falta': 'text-bg-danger',
            'Reprovado por nota': 'text-bg-danger',
            'Reprovado por nota e falta': 'text-bg-danger',
            'Recuperação/Paralela': 'text-bg-warning',
            'Em andamento': 'text-bg-secondary',
        }
        return classes.get(self.situacao, 'text-bg-secondary')

    def clean(self):
        super().clean()
        if self.aluno_id and self.turma_id and self.aluno.turma_id != self.turma_id:
            raise ValidationError({'aluno': 'O aluno deve pertencer a turma do registro.'})
        if self.disciplina_id and self.turma_id and self.disciplina.turma_id != self.turma_id:
            raise ValidationError({'disciplina': 'A disciplina deve pertencer a turma do registro.'})
        if self.total_faltas > self.total_aulas:
            raise ValidationError({'total_faltas': 'O total de faltas nao pode ser maior que o total de aulas.'})
        for campo in ['nota1', 'nota2', 'nota3']:
            nota = getattr(self, campo)
            if nota is not None and (nota < 0 or nota > 10):
                raise ValidationError({campo: 'A nota deve estar entre 0 e 10.'})


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
    foto = models.ImageField('foto', upload_to='usuarios/fotos/', blank=True, null=True)
    created_at = models.DateTimeField('criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de usuario'
        verbose_name_plural = 'Perfis de usuarios'
        ordering = ['usuario__username']

    def __str__(self):
        return self.usuario.username
