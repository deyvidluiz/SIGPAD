"""
Popula o banco com dados FICTICIOS de demonstracao do SIGPAD (ano letivo 2026).

Uso:
    python manage.py seed_demo            # pede confirmacao
    python manage.py seed_demo --sim      # sem pergunta (ex.: scripts)
    python manage.py seed_demo --limpar   # remove apenas os dados de demonstracao

Como os dados ficticios sao identificados
----------------------------------------
Todo registro criado aqui pertence (direta ou indiretamente) a professores
ficticios que:
  * fazem parte do grupo "SIGPAD - Dados de demonstracao";
  * possuem e-mail no dominio @demo.sigpad.local.
Turmas, disciplinas, alunos, aulas, notas, alertas etc. ficam presos a esses
usuarios por chave estrangeira, entao os nomes exibidos nas telas continuam
naturais. Nenhum registro de outros usuarios e lido para alteracao ou apagado.

Idempotencia
------------
Cada registro e buscado pela sua chave natural (ex.: turma+disciplina+data da
aula) antes de ser criado. Os valores aleatorios usam sementes fixas, entao
rodar o comando de novo nao duplica nada e gera os mesmos valores.
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from planejamento.models import (
    Alerta,
    Aluno,
    AnotacaoTurma,
    Aula,
    Chamada,
    ConteudoProgramatico,
    Disciplina,
    NotaAluno,
    Presenca,
    PresencaAluno,
    ProcessoAvaliativo,
    Recuperacao,
    RegistroAlunoTurma,
    Turma,
)
from planejamento.utils import verificar_alertas_conteudos

GRUPO_DEMO = 'SIGPAD - Dados de demonstracao'
DOMINIO_DEMO = 'demo.sigpad.local'
ANO_LETIVO = 2026
SEMENTE = 'sigpad-demo-2026'

# ---------------------------------------------------------------------------
# Calendario letivo ficticio de 2026
# ---------------------------------------------------------------------------
BIMESTRES = {
    1: (date(2026, 2, 9), date(2026, 4, 24)),
    2: (date(2026, 4, 27), date(2026, 7, 10)),
    3: (date(2026, 7, 27), date(2026, 10, 2)),
    4: (date(2026, 10, 5), date(2026, 11, 27)),
}
FERIADOS = {
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),  # Carnaval / Cinzas
    date(2026, 4, 3),   # Sexta-feira Santa
    date(2026, 4, 21),  # Tiradentes
    date(2026, 5, 1),   # Dia do Trabalho
    date(2026, 6, 4),   # Corpus Christi
    date(2026, 9, 7),   # Independencia
    date(2026, 10, 12),  # N. Sra. Aparecida
    date(2026, 10, 15),  # Dia do Professor
    date(2026, 11, 2),  # Finados
    date(2026, 11, 20),  # Consciencia Negra
}

# ---------------------------------------------------------------------------
# Professores, turmas e disciplinas
# ---------------------------------------------------------------------------
PROFESSORES = [
    {'username': 'prof.mariana', 'first_name': 'Mariana', 'last_name': 'Costa Albuquerque'},
    {'username': 'prof.ricardo', 'first_name': 'Ricardo', 'last_name': 'Nogueira Lima'},
]

# dias: {dia_da_semana (0=segunda): quantidade de aulas no dia}
TURMAS = [
    {
        'codigo': '6A', 'professor': 'prof.mariana', 'nome': '6º Ano A', 'turno': 'MATUTINO',
        'ano_escolar': '6º ano - Ensino Fundamental', 'alunos': 28,
        'descricao': 'Ensino Fundamental - Anos Finais. Sala 12, bloco B.',
        'disciplinas': [
            ('Matemática', 'MAT6', {0: 2, 2: 1, 4: 2}),
            ('Língua Portuguesa', 'LP6', {0: 1, 1: 2, 3: 2}),
            ('Ciências', 'CIE6', {1: 1, 3: 2}),
            ('Geografia', 'GEO6', {2: 1, 4: 1}),
        ],
    },
    {
        'codigo': '7B', 'professor': 'prof.mariana', 'nome': '7º Ano B', 'turno': 'VESPERTINO',
        'ano_escolar': '7º ano - Ensino Fundamental', 'alunos': 30,
        'descricao': 'Ensino Fundamental - Anos Finais. Sala 08, bloco A.',
        'disciplinas': [
            ('Matemática', 'MAT7', {0: 1, 1: 2, 3: 2}),
            ('Língua Portuguesa', 'LP7', {0: 2, 2: 1, 4: 2}),
            ('História', 'HIS7', {2: 1, 4: 1}),
        ],
    },
    {
        'codigo': '9A', 'professor': 'prof.mariana', 'nome': '9º Ano A', 'turno': 'MATUTINO',
        'ano_escolar': '9º ano - Ensino Fundamental', 'alunos': 26,
        'descricao': 'Ensino Fundamental - Anos Finais. Turma concluinte, sala 15.',
        'disciplinas': [
            ('Matemática', 'MAT9', {0: 2, 2: 2, 4: 1}),
            ('Ciências', 'CIE9', {1: 2, 3: 1}),
            ('Língua Inglesa', 'ING9', {3: 2}),
        ],
    },
    {
        'codigo': '1B', 'professor': 'prof.mariana', 'nome': '1ª Série B', 'turno': 'NOTURNO',
        'ano_escolar': '1ª série - Ensino Médio', 'alunos': 24, 'faltas_extra': 0.04,
        'descricao': 'Ensino Médio regular noturno. Sala 03, bloco C.',
        'disciplinas': [
            ('Matemática', 'MAT1EM', {0: 2, 3: 1}),
            ('Física', 'FIS1EM', {1: 2}),
            ('História', 'HIS1EM', {2: 1, 4: 1}),
        ],
    },
    {
        'codigo': '8C', 'professor': 'prof.ricardo', 'nome': '8º Ano C', 'turno': 'VESPERTINO',
        'ano_escolar': '8º ano - Ensino Fundamental', 'alunos': 27,
        'descricao': 'Ensino Fundamental - Anos Finais. Sala 10, bloco A.',
        'disciplinas': [
            ('História', 'HIS8', {0: 1, 3: 1}),
            ('Geografia', 'GEO8', {1: 1, 4: 1}),
        ],
    },
]

# Dois conteudos por bimestre para cada disciplina/serie
CONTEUDOS = {
    'MAT6': [
        ['Sistema de numeração decimal e números naturais', 'Operações com números naturais e expressões numéricas'],
        ['Múltiplos, divisores e números primos', 'Frações: significados e equivalência'],
        ['Operações com frações', 'Números decimais e porcentagem'],
        ['Figuras geométricas planas e espaciais', 'Grandezas e medidas: perímetro e área'],
    ],
    'LP6': [
        ['Gêneros textuais: conto e crônica', 'Substantivo e adjetivo'],
        ['Leitura e produção de notícia', 'Verbos: tempos e modos'],
        ['Pontuação e coesão textual', 'Produção de texto narrativo'],
        ['Poema: recursos sonoros e figuras de linguagem', 'Reescrita e revisão textual'],
    ],
    'CIE6': [
        ['Matéria e suas transformações: misturas', 'Métodos de separação de misturas'],
        ['Célula como unidade da vida', 'Níveis de organização dos seres vivos'],
        ['Sistema nervoso e órgãos dos sentidos', 'Lentes e correção da visão'],
        ['Forma e estrutura da Terra: camadas', 'Rochas, fósseis e minerais'],
    ],
    'GEO6': [
        ['Paisagem, lugar e espaço geográfico', 'Orientação e coordenadas geográficas'],
        ['Cartografia: escalas e tipos de mapas', 'Estrutura interna da Terra e relevo'],
        ['Hidrografia e ciclo da água', 'Clima e tempo atmosférico'],
        ['Biomas brasileiros', 'Atividades econômicas e transformação da paisagem'],
    ],
    'MAT7': [
        ['Números inteiros: conceito e reta numérica', 'Operações com números inteiros'],
        ['Números racionais', 'Razão e proporção'],
        ['Grandezas diretamente e inversamente proporcionais', 'Equações do 1º grau'],
        ['Ângulos e triângulos', 'Probabilidade e estatística: gráficos'],
    ],
    'LP7': [
        ['Gênero textual: reportagem', 'Frase, oração e período'],
        ['Sujeito e predicado', 'Texto argumentativo: artigo de opinião'],
        ['Advérbios e locuções adverbiais', 'Leitura de romance juvenil'],
        ['Gênero textual: entrevista', 'Revisão e reescrita de textos opinativos'],
    ],
    'HIS7': [
        ['A formação do mundo moderno', 'Grandes navegações europeias'],
        ['Renascimento e Reforma Protestante', 'Povos indígenas e a chegada dos portugueses'],
        ['Colonização da América portuguesa', 'Economia açucareira e escravidão africana'],
        ['Mineração no Brasil colonial', 'Resistências: quilombos e revoltas coloniais'],
    ],
    'MAT9': [
        ['Números reais e potenciação', 'Radiciação e notação científica'],
        ['Produtos notáveis e fatoração', 'Equações do 2º grau'],
        ['Funções: noção e representação gráfica', 'Semelhança de triângulos'],
        ['Teorema de Pitágoras e relações métricas', 'Estatística: média, moda e mediana'],
    ],
    'CIE9': [
        ['Estrutura da matéria e modelos atômicos', 'Tabela periódica'],
        ['Ligações químicas e reações', 'Hereditariedade e genética básica'],
        ['Evolução dos seres vivos', 'Ondas, som e radiações'],
        ['Astronomia: Sistema Solar e universo', 'Sustentabilidade e preservação ambiental'],
    ],
    'ING9': [
        ['Simple present and present continuous', 'Reading strategies: skimming and scanning'],
        ['Simple past: regular and irregular verbs', 'Vocabulary: technology and social media'],
        ['Future: will and going to', 'Text genre: biography'],
        ['Modal verbs: can, should, must', 'Oral presentation: my future plans'],
    ],
    'MAT1EM': [
        ['Conjuntos numéricos', 'Funções: conceito, domínio e imagem'],
        ['Função afim', 'Função quadrática'],
        ['Função exponencial', 'Logaritmos'],
        ['Progressão aritmética', 'Progressão geométrica'],
    ],
    'FIS1EM': [
        ['Grandezas físicas e notação científica', 'Cinemática: movimento uniforme'],
        ['Movimento uniformemente variado', 'Queda livre e lançamento vertical'],
        ['Leis de Newton', 'Força de atrito e plano inclinado'],
        ['Trabalho, energia e potência', 'Conservação da energia mecânica'],
    ],
    'HIS1EM': [
        ['Introdução aos estudos históricos e fontes', 'Pré-história e primeiras sociedades'],
        ['Antiguidade oriental: Mesopotâmia e Egito', 'Grécia Antiga e democracia ateniense'],
        ['Roma Antiga: república e império', 'Sociedade feudal na Europa medieval'],
        ['Povos da África antiga', 'Sociedades indígenas da América pré-colombiana'],
    ],
    'HIS8': [
        ['Iluminismo e o Antigo Regime', 'Revolução Industrial'],
        ['Independência dos Estados Unidos', 'Revolução Francesa'],
        ['Era Napoleônica e Congresso de Viena', 'Independências na América espanhola'],
        ['Independência do Brasil', 'Primeiro Reinado e Período Regencial'],
    ],
    'GEO8': [
        ['Regionalização do mundo', 'População mundial e fluxos migratórios'],
        ['América: aspectos naturais', 'América Latina: economia e urbanização'],
        ['África: aspectos físicos e diversidade cultural', 'África: economia e conflitos'],
        ['Globalização e blocos econômicos', 'Organismos internacionais e geopolítica'],
    ],
}

TIPO_TRABALHO = {
    'Matemática': 'Trabalho em dupla',
    'Língua Portuguesa': 'Produção textual',
    'Ciências': 'Relatório de experimento',
    'Geografia': 'Mapa temático',
    'História': 'Seminário',
    'Língua Inglesa': 'Oral presentation',
    'Física': 'Relatório de experimento',
}

DESCRICAO_DISCIPLINA = {
    'Matemática': 'Números, álgebra, geometria, grandezas e medidas, probabilidade e estatística.',
    'Língua Portuguesa': 'Leitura, produção de textos, oralidade e análise linguística.',
    'Ciências': 'Matéria e energia, vida e evolução, Terra e universo.',
    'Geografia': 'Espaço geográfico, cartografia, natureza e sociedade.',
    'História': 'Processos históricos, fontes e relações entre passado e presente.',
    'Língua Inglesa': 'Leitura, escrita, oralidade e conhecimentos linguísticos em inglês.',
    'Física': 'Mecânica, energia e suas aplicações no cotidiano.',
}

ATIVIDADES_AULA = [
    'Explicação dialogada e exemplos no quadro',
    'Resolução de exercícios do livro didático',
    'Correção coletiva da atividade anterior',
    'Atividade em grupo',
    'Leitura e discussão de texto de apoio',
    'Exercícios de fixação no caderno',
    'Revisão do conteúdo',
]
OBSERVACOES_AULA = [
    'Turma participativa.',
    'Alguns alunos com dificuldade; retomar na próxima aula.',
    'Atividade concluída em sala.',
    'Uso do laboratório de informática.',
    'Aula reduzida por reunião pedagógica.',
]

ANOTACOES = [
    ('Reunião de pais e mestres - 1º bimestre', 'Entrega dos boletins do 1º bimestre. Famílias dos alunos com baixo rendimento foram orientadas sobre o plano de estudos.', date(2026, 5, 8)),
    ('Conselho de classe - 2º bimestre', 'Discussão sobre frequência e rendimento. Encaminhados à coordenação os casos de faltas recorrentes.', date(2026, 7, 9)),
    ('Planejamento do 4º bimestre', 'Organização das avaliações finais e do cronograma de recuperação paralela.', date(2026, 10, 6)),
]

PRIMEIROS_NOMES = [
    'Ana', 'Beatriz', 'Camila', 'Larissa', 'Fernanda', 'Gabriela', 'Isabela', 'Júlia', 'Letícia', 'Manuela',
    'Mariana', 'Natália', 'Rafaela', 'Sofia', 'Vitória', 'Yasmin', 'Lívia', 'Heloísa', 'Clara', 'Alice',
    'Bianca', 'Eduarda', 'Luana', 'Maria Eduarda', 'Ana Luiza', 'Giovanna', 'Valentina', 'Lara', 'Emanuelly', 'Kauane',
    'Arthur', 'Bernardo', 'Caio', 'Davi', 'Enzo', 'Felipe', 'Gabriel', 'Gustavo', 'Heitor', 'Igor',
    'João Pedro', 'Kauã', 'Lucas', 'Matheus', 'Miguel', 'Nicolas', 'Otávio', 'Pedro Henrique', 'Rafael', 'Samuel',
    'Thiago', 'Vinícius', 'Wesley', 'Breno', 'Diego', 'Murilo', 'Ryan', 'Luiz Fernando', 'Cauã', 'Davi Lucca',
]
SOBRENOMES = [
    'Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes',
    'Ribeiro', 'Carvalho', 'Almeida', 'Lopes', 'Barbosa', 'Araújo', 'Rocha', 'Dias', 'Nascimento', 'Moreira',
    'Cardoso', 'Teixeira', 'Mendes', 'Freitas', 'Barros', 'Pinto', 'Moura', 'Cavalcanti', 'Batista', 'Campos',
    'Santana', 'Reis', 'Andrade', 'Correia', 'Vieira', 'Monteiro', 'Nunes', 'Macedo', 'Brito', 'Farias',
]

DUAS_CASAS = Decimal('0.01')


def rng_para(*chaves):
    """Gerador deterministico: mesma chave -> mesmos numeros em toda execucao."""
    return random.Random('|'.join([SEMENTE, *map(str, chaves)]))


def dia_letivo(dia):
    if dia.weekday() >= 5 or dia in FERIADOS:
        return False
    return bimestre_de(dia) is not None


def bimestre_de(dia):
    for numero, (inicio, fim) in BIMESTRES.items():
        if inicio <= dia <= fim:
            return numero
    return None


def ajustar_dia_letivo(dia, para_tras=False):
    passo = timedelta(days=-1 if para_tras else 1)
    while not dia_letivo(dia):
        dia += passo
    return dia


def janelas_conteudo(bimestre):
    """Divide o bimestre em duas janelas, uma para cada conteudo."""
    inicio, fim = BIMESTRES[bimestre]
    if bimestre == 4:
        meio = date(2026, 11, 13)
    else:
        meio = inicio + (fim - inicio) / 2
        meio = date(meio.year, meio.month, meio.day)
    segundo_inicio = ajustar_dia_letivo(meio + timedelta(days=1))
    return [(inicio, ajustar_dia_letivo(meio, para_tras=True)), (segundo_inicio, fim)]


def decimal2(valor):
    return Decimal(str(valor)).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)


def aware(dia, hora=17, minuto=30):
    return timezone.make_aware(datetime.combine(dia, time(hora, minuto)))


class Command(BaseCommand):
    help = 'Popula o banco com dados ficticios de demonstracao (ano letivo 2026). Apenas para desenvolvimento.'

    def add_arguments(self, parser):
        parser.add_argument('--sim', action='store_true', help='Confirma a execucao sem perguntar.')
        parser.add_argument('--senha', default='sigpad2026', help='Senha dos professores ficticios (padrao: sigpad2026).')
        parser.add_argument(
            '--data-referencia',
            help='Data "de hoje" usada para decidir o que ja aconteceu (AAAA-MM-DD). Padrao: data atual.',
        )
        parser.add_argument(
            '--limpar',
            action='store_true',
            help='Remove somente os dados de demonstracao (usuarios do grupo de demonstracao e tudo vinculado a eles).',
        )

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------
    def handle(self, *args, **opcoes):
        if not settings.DEBUG:
            raise CommandError(
                'seed_demo so pode ser executado com DEBUG=True (ambiente de desenvolvimento/demonstracao).'
            )

        banco = settings.DATABASES['default']
        destino = f"{banco.get('NAME')} em {banco.get('HOST') or 'local'}"

        if opcoes['limpar']:
            self._confirmar(opcoes, f'Remover TODOS os dados de demonstracao do banco {destino}?')
            self._limpar()
            return

        self.hoje = self._data_referencia(opcoes.get('data_referencia'))
        self._confirmar(
            opcoes,
            f'Inserir dados FICTICIOS de demonstracao no banco {destino} (data de referencia {self.hoje:%d/%m/%Y})?',
        )

        self.contagem = {}
        with transaction.atomic():
            grupo, _ = Group.objects.get_or_create(name=GRUPO_DEMO)
            professores = {dados['username']: self._professor(dados, grupo, opcoes['senha']) for dados in PROFESSORES}
            for indice_turma, config in enumerate(TURMAS):
                self._popular_turma(indice_turma, config, professores[config['professor']])
            for professor in professores.values():
                verificar_alertas_conteudos(professor)
                self._alertas_sistema(professor)

        self._resumo(professores)

    def _data_referencia(self, valor):
        if valor:
            try:
                hoje = date.fromisoformat(valor)
            except ValueError as erro:
                raise CommandError('Use o formato AAAA-MM-DD em --data-referencia.') from erro
        else:
            hoje = timezone.localdate()
        inicio, fim = BIMESTRES[1][0], BIMESTRES[4][1] + timedelta(days=1)
        if hoje != min(max(hoje, inicio), fim):
            self.stdout.write(self.style.WARNING(
                f'A data {hoje:%d/%m/%Y} esta fora do ano letivo 2026; usando {min(max(hoje, inicio), fim):%d/%m/%Y}.'
            ))
        hoje = min(max(hoje, inicio), fim)
        if hoje != timezone.localdate():
            self.stdout.write(self.style.WARNING(
                'Aviso: o SIGPAD recalcula status de conteudos e atividades com a data real do servidor; '
                'alguns status podem diferir da data de referencia.'
            ))
        return hoje

    def _confirmar(self, opcoes, pergunta):
        if opcoes['sim']:
            return
        resposta = input(f'{pergunta}\nDigite "sim" para continuar: ').strip().lower()
        if resposta != 'sim':
            raise CommandError('Operacao cancelada pelo usuario.')

    def _contar(self, chave, criado=True, quantidade=1):
        if criado and quantidade:
            self.contagem[chave] = self.contagem.get(chave, 0) + quantidade

    # ------------------------------------------------------------------
    # Limpeza (somente dados de demonstracao)
    # ------------------------------------------------------------------
    def _limpar(self):
        usuarios = User.objects.filter(groups__name=GRUPO_DEMO, email__endswith=f'@{DOMINIO_DEMO}')
        nomes = list(usuarios.values_list('username', flat=True))
        if not nomes:
            self.stdout.write('Nenhum dado de demonstracao encontrado.')
            return
        with transaction.atomic():
            usuarios.delete()  # CASCADE remove turmas, disciplinas, alunos, aulas, notas, alertas...
            Group.objects.filter(name=GRUPO_DEMO, user__isnull=True).delete()
        self.stdout.write(self.style.SUCCESS(f'Dados de demonstracao removidos (usuarios: {", ".join(nomes)}).'))

    # ------------------------------------------------------------------
    # Professores
    # ------------------------------------------------------------------
    def _professor(self, dados, grupo, senha):
        email = f"{dados['username'].replace('prof.', '')}@{DOMINIO_DEMO}"
        usuario = User.objects.filter(username=dados['username']).first()
        if usuario and not usuario.groups.filter(name=GRUPO_DEMO).exists():
            raise CommandError(
                f'O usuario "{dados["username"]}" ja existe e NAO e de demonstracao. '
                'Nada foi alterado para nao sobrescrever um registro real.'
            )
        if usuario is None:
            usuario = User(username=dados['username'], email=email,
                           first_name=dados['first_name'], last_name=dados['last_name'])
            usuario.set_password(senha)
            usuario.full_clean()
            usuario.save()  # o signal cria o PerfilUsuario
            usuario.groups.add(grupo)
            self._contar('professores')
        return usuario

    # ------------------------------------------------------------------
    # Turma completa
    # ------------------------------------------------------------------
    def _popular_turma(self, indice_turma, config, professor):
        turma = Turma.objects.filter(professor=professor, nome=config['nome'], ano_letivo=ANO_LETIVO).first()
        if turma is None:
            turma = Turma(professor=professor, nome=config['nome'], ano_letivo=ANO_LETIVO,
                          turno=config['turno'], descricao=config['descricao'])
            turma.full_clean()
            turma.save()
            self._contar('turmas')

        alunos = self._alunos(indice_turma, config, turma)
        perfis = {aluno.id: self._perfil_aluno(aluno, config) for aluno in alunos}
        ausencias = self._ausencias_por_dia(turma, alunos, perfis)
        self._anotacoes(turma, professor)

        for indice_disciplina, (nome, chave, dias) in enumerate(config['disciplinas']):
            indice_global = indice_turma * 10 + indice_disciplina
            disciplina = self._disciplina(turma, professor, nome, config['ano_escolar'], dias)
            conteudos = self._conteudos(disciplina, chave, indice_global)
            self._aulas(turma, disciplina, dias, conteudos, alunos, ausencias)
            avaliacoes = self._avaliacoes(turma, disciplina, conteudos, indice_global)
            self._notas(disciplina, avaliacoes, alunos, perfis)
            self._recuperacoes(disciplina, avaliacoes, alunos, perfis)
            self._registros(turma, disciplina, alunos, avaliacoes)

    def _alunos(self, indice_turma, config, turma):
        rng = rng_para('alunos', config['codigo'])
        usados = set(Aluno.objects.values_list('nome', flat=True))
        alunos = []
        for numero in range(1, config['alunos'] + 1):
            matricula = f'2026{indice_turma + 1:02d}{numero:03d}'
            aluno = Aluno.objects.filter(turma=turma, matricula=matricula).first()
            if aluno is None:
                while True:
                    nome = f'{rng.choice(PRIMEIROS_NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}'
                    if nome not in usados and len(set(nome.split()[-2:])) == 2:
                        break
                usados.add(nome)
                aluno = Aluno(turma=turma, nome=nome, matricula=matricula, ativo=True)
                aluno.full_clean()
                aluno.save()
                self._contar('alunos')
            if aluno.ativo:
                alunos.append(aluno)

        # Um aluno transferido no 7º ano (aparece na lista como inativo)
        if config['codigo'] == '7B':
            matricula = f'2026{indice_turma + 1:02d}{config["alunos"] + 1:03d}'
            _, criado = Aluno.objects.get_or_create(
                turma=turma, matricula=matricula,
                defaults={'nome': 'Kevin Moraes Tavares', 'ativo': False},
            )
            self._contar('alunos', criado)
        return sorted(alunos, key=lambda aluno: aluno.nome)

    def _perfil_aluno(self, aluno, config):
        """Perfil ficticio e deterministico: habilidade e propensao a faltas."""
        rng = rng_para('perfil', aluno.matricula)
        sorteio = rng.random()
        if sorteio < 0.08:
            faltas = rng.uniform(0.26, 0.36)  # baixa frequencia (< 75%)
        elif sorteio < 0.28:
            faltas = rng.uniform(0.07, 0.15)
        else:
            faltas = rng.uniform(0.01, 0.06)
        faltas += config.get('faltas_extra', 0)
        habilidade = min(max(rng.gauss(7.9, 1.2), 4.0), 9.9)
        if faltas > 0.2:
            habilidade -= 1.0
        tendencia = rng.choice([-0.3, -0.1, 0, 0, 0.1, 0.25, 0.4])  # melhora/piora ao longo do ano
        return {'faltas': faltas, 'habilidade': habilidade, 'tendencia': tendencia}

    def _ausencias_por_dia(self, turma, alunos, perfis):
        """Quando o aluno falta, falta o dia inteiro (todas as disciplinas do dia)."""
        ausencias = {}
        dia = BIMESTRES[1][0]
        while dia < self.hoje:
            if dia_letivo(dia):
                for aluno in alunos:
                    if rng_para('falta', aluno.matricula, dia).random() < perfis[aluno.id]['faltas']:
                        ausencias.setdefault(dia, set()).add(aluno.id)
            dia += timedelta(days=1)
        return ausencias

    def _anotacoes(self, turma, professor):
        for titulo, descricao, dia in ANOTACOES:
            if dia >= self.hoje:
                continue
            anotacao, criado = AnotacaoTurma.objects.get_or_create(
                turma=turma, professor=professor, titulo=titulo, defaults={'descricao': descricao},
            )
            if criado:
                AnotacaoTurma.objects.filter(pk=anotacao.pk).update(created_at=aware(dia, 18, 0))
            self._contar('anotacoes', criado)

    # ------------------------------------------------------------------
    # Disciplina, conteudos e aulas
    # ------------------------------------------------------------------
    def _datas_aula(self, dias):
        datas = []
        dia = BIMESTRES[1][0]
        while dia <= BIMESTRES[4][1]:
            if dia_letivo(dia) and dia.weekday() in dias:
                datas.append(dia)
            dia += timedelta(days=1)
        return datas

    def _disciplina(self, turma, professor, nome, ano_escolar, dias):
        disciplina = Disciplina.objects.filter(turma=turma, nome=nome).first()
        if disciplina is None:
            previstas = sum(dias[dia.weekday()] for dia in self._datas_aula(dias))
            disciplina = Disciplina(
                turma=turma, professor=professor, nome=nome,
                descricao=DESCRICAO_DISCIPLINA[nome], carga_horaria=previstas,
                tipo_periodo='BIMESTRE', quantidade_aulas=previstas,
                nota_total=Decimal('10.00'), media_aprovacao=Decimal('6.00'), ano_escolar=ano_escolar,
            )
            disciplina.full_clean()
            disciplina.save()  # cria os periodos letivos (bimestres)
            self._contar('disciplinas')
        return disciplina

    def _conteudos(self, disciplina, chave, indice_global):
        """Retorna {bimestre: [(conteudo, inicio, fim), ...]}."""
        atrasados = set()
        if indice_global % 4 == 1:
            atrasados.add((3, 1))
        if indice_global % 7 == 3:
            atrasados.add((2, 1))
        resultado = {}
        for bimestre in range(1, 5):
            resultado[bimestre] = []
            for posicao, (titulo, (inicio, fim)) in enumerate(zip(CONTEUDOS[chave][bimestre - 1], janelas_conteudo(bimestre))):
                conteudo = ConteudoProgramatico.objects.filter(disciplina=disciplina, titulo=titulo).first()
                if conteudo is None:
                    concluido = fim < self.hoje and (bimestre, posicao) not in atrasados
                    rng = rng_para('conteudo', disciplina.turma_id, titulo)
                    conteudo = ConteudoProgramatico(
                        disciplina=disciplina, titulo=titulo,
                        descricao=f'{titulo}. Aulas expositivas, exercícios e atividades de fixação.',
                        unidade=f'Unidade {bimestre * 2 - 1 + posicao}',
                        bimestre=bimestre, tipo_periodo='BIMESTRE', periodo=f'{bimestre}_BIMESTRE',
                        data_inicio=inicio, data_fim=fim, concluido=concluido,
                        data_conclusao=aware(fim - timedelta(days=rng.randint(0, 3))) if concluido else None,
                    )
                    conteudo.full_clean()
                    conteudo.save()
                    conteudo.atualizar_status()
                    self._contar('conteudos')
                resultado[bimestre].append((conteudo, inicio, fim))
        return resultado

    def _conteudo_do_dia(self, conteudos, dia):
        bimestre = bimestre_de(dia)
        for conteudo, inicio, fim in conteudos.get(bimestre, []):
            if inicio <= dia <= fim:
                return conteudo
        return conteudos[bimestre][-1][0]

    def _aulas(self, turma, disciplina, dias, conteudos, alunos, ausencias):
        existentes = set(Aula.objects.filter(turma=turma, disciplina=disciplina).values_list('data', flat=True))
        presencas_novas = []
        for dia in self._datas_aula(dias):
            if dia >= self.hoje or dia in existentes:
                continue
            rng = rng_para('aula', turma.id, disciplina.nome, dia)
            conteudo = self._conteudo_do_dia(conteudos, dia)
            aula = Aula(
                turma=turma, disciplina=disciplina, data=dia, quantidade_aulas=dias[dia.weekday()],
                conteudo_aplicado=f'{conteudo.titulo} - {rng.choice(ATIVIDADES_AULA).lower()}.',
                observacao=rng.choice(OBSERVACOES_AULA) if rng.random() < 0.15 else '',
            )
            aula.full_clean()
            aula.save()
            self._contar('aulas')
            faltaram = ausencias.get(dia, set())
            for aluno in alunos:
                presente = aluno.id not in faltaram
                observacao = ''
                if not presente and rng.random() < 0.12:
                    observacao = 'Atestado médico apresentado.'
                elif presente and rng.random() < 0.01:
                    observacao = 'Chegou atrasado.'
                presencas_novas.append(Presenca(aula=aula, aluno=aluno, presente=presente, observacao=observacao))

            # Os registros do 4º bimestre tambem aparecem como "Chamadas" na visao geral da turma
            if bimestre_de(dia) == 4:
                chamada, criado = Chamada.objects.get_or_create(
                    turma=turma, disciplina=disciplina, data=dia,
                    defaults={'tipo_periodo': 'BIMESTRE', 'periodo': '4_BIMESTRE', 'descricao': conteudo.titulo[:150]},
                )
                self._contar('chamadas', criado)
                PresencaAluno.objects.bulk_create(
                    [PresencaAluno(chamada=chamada, aluno=aluno, presente=aluno.id not in faltaram) for aluno in alunos],
                    ignore_conflicts=True,
                )
        Presenca.objects.bulk_create(presencas_novas, ignore_conflicts=True, batch_size=2000)
        self._contar('presencas', quantidade=len(presencas_novas))

    # ------------------------------------------------------------------
    # Avaliacoes, notas e recuperacoes
    # ------------------------------------------------------------------
    def _planejar_avaliacoes(self, disciplina, conteudos, indice_global):
        planos = []
        for bimestre in range(1, 5):
            inicio, fim = BIMESTRES[bimestre]
            (conteudo1, _, _), (conteudo2, _, _) = conteudos[bimestre]
            atividade = ajustar_dia_letivo(inicio + timedelta(days=14))
            abertura = ajustar_dia_letivo(inicio + timedelta(days=21))
            fechamento = ajustar_dia_letivo(abertura + timedelta(days=[4, 11, 18][indice_global % 3]))
            prova = ajustar_dia_letivo(fim - timedelta(days=4), para_tras=True)
            planos += [
                {
                    'titulo': f'Atividade avaliativa: {conteudo1.titulo}', 'tipo': 'Atividade em sala',
                    'valor': Decimal('2.00'), 'bimestre': bimestre, 'abertura': atividade, 'fechamento': atividade,
                    'descricao': conteudo1.titulo,
                },
                {
                    'titulo': f'{TIPO_TRABALHO[disciplina.nome]}: {conteudo2.titulo}', 'tipo': TIPO_TRABALHO[disciplina.nome],
                    'valor': Decimal('3.00'), 'bimestre': bimestre, 'abertura': abertura, 'fechamento': fechamento,
                    'descricao': conteudo2.titulo,
                },
                {
                    'titulo': f'Prova do {bimestre}º bimestre', 'tipo': 'Prova escrita',
                    'valor': Decimal('5.00'), 'bimestre': bimestre, 'abertura': prova, 'fechamento': prova,
                    'descricao': f'{conteudo1.titulo}; {conteudo2.titulo}',
                },
            ]
        return planos

    def _avaliacoes(self, turma, disciplina, conteudos, indice_global):
        """Retorna lista de (avaliacao, bimestre, tem_notas)."""
        resultado = []
        for plano in self._planejar_avaliacoes(disciplina, conteudos, indice_global):
            fechamento = plano['fechamento']
            if fechamento < self.hoje - timedelta(days=7):
                corrigida = True
            elif fechamento < self.hoje:
                corrigida = indice_global % 2 == 0  # as demais ficam com correcao pendente
            else:
                corrigida = False
            avaliacao = ProcessoAvaliativo.objects.filter(turma=turma, disciplina=disciplina, titulo=plano['titulo']).first()
            if avaliacao is None:
                avaliacao = ProcessoAvaliativo(
                    turma=turma, disciplina=disciplina, titulo=plano['titulo'], tipo=plano['tipo'],
                    descricao=plano['descricao'], valor_maximo=plano['valor'],
                    periodo=f"{plano['bimestre']}_BIMESTRE",
                    data_abertura=plano['abertura'], data_fechamento=fechamento, data=fechamento,
                    status='CORRIGIDA' if corrigida else 'A_REALIZAR',
                )
                avaliacao.full_clean()
                avaliacao.save()  # se nao corrigida, o proprio model calcula o status pelas datas
                self._contar('avaliacoes')
            resultado.append((avaliacao, plano['bimestre'], avaliacao.status == 'CORRIGIDA'))
        return resultado

    def _nota_aluno(self, aluno, disciplina, avaliacao, bimestre, perfil):
        rng = rng_para('nota', aluno.matricula, disciplina.nome, avaliacao.titulo)
        afinidade = rng_para('afinidade', aluno.matricula, disciplina.nome).gauss(0, 0.6)
        base = perfil['habilidade'] + afinidade + perfil['tendencia'] * (bimestre - 2) + rng.gauss(0, 0.8)
        fracao = min(max(base / 10, 0), 1)
        valor = avaliacao.valor_maximo
        nota = (Decimal(str(fracao)) * valor * 4).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / 4  # passos de 0,25
        observacao = ''
        if rng.random() < 0.03:
            nota = Decimal('0')
            observacao = 'Não entregou.'
        elif rng.random() < 0.04:
            observacao = 'Entregou fora do prazo.'
        return min(max(nota, Decimal('0')), valor).quantize(DUAS_CASAS), observacao

    def _notas(self, disciplina, avaliacoes, alunos, perfis):
        for avaliacao, bimestre, tem_notas in avaliacoes:
            if not tem_notas:
                continue
            existentes = set(avaliacao.notas.values_list('aluno_id', flat=True))
            for aluno in alunos:
                if aluno.id in existentes:
                    continue
                nota, observacao = self._nota_aluno(aluno, disciplina, avaliacao, bimestre, perfis[aluno.id])
                registro = NotaAluno(aluno=aluno, processo=avaliacao, nota=nota, observacao=observacao)
                registro.full_clean()
                registro.save()
                self._contar('notas')

    def _medias_bimestre(self, avaliacoes, alunos):
        """{(aluno_id, bimestre): media 0-10} considerando apenas avaliacoes corrigidas."""
        medias = {}
        for bimestre in range(1, 5):
            do_bimestre = [avaliacao for avaliacao, bim, tem_notas in avaliacoes if bim == bimestre and tem_notas]
            total = sum((avaliacao.valor_maximo for avaliacao in do_bimestre), Decimal('0'))
            if not total:
                continue
            soma = {}
            for nota in NotaAluno.objects.filter(processo__in=do_bimestre, aluno__in=alunos):
                soma[nota.aluno_id] = soma.get(nota.aluno_id, Decimal('0')) + nota.nota
            for aluno_id, valor in soma.items():
                medias[(aluno_id, bimestre)] = (valor / total * 10).quantize(DUAS_CASAS)
        return medias

    def _recuperacoes(self, disciplina, avaliacoes, alunos, perfis):
        medias = self._medias_bimestre(avaliacoes, alunos)
        for aluno in alunos:
            for bimestre in range(1, 4):
                if BIMESTRES[bimestre][1] >= self.hoje:
                    continue
                media = medias.get((aluno.id, bimestre))
                if media is None or media >= disciplina.media_aprovacao:
                    continue
                rng = rng_para('recuperacao', aluno.matricula, disciplina.nome, bimestre)
                nota_rec = min(media + Decimal(str(round(rng.uniform(0.5, 3.5), 1))), disciplina.nota_total)
                nota_paralela = None
                if rng.random() < 0.35:
                    nota_paralela = min(media + Decimal(str(round(rng.uniform(0.0, 2.5), 1))), disciplina.nota_total)
                rec = Recuperacao.objects.filter(aluno=aluno, disciplina=disciplina, periodo=f'{bimestre}_BIMESTRE').first()
                if rec is None:
                    rec = Recuperacao(
                        aluno=aluno, disciplina=disciplina, periodo=f'{bimestre}_BIMESTRE',
                        nota_recuperacao=nota_rec.quantize(DUAS_CASAS),
                        nota_paralela=nota_paralela.quantize(DUAS_CASAS) if nota_paralela is not None else None,
                        observacao='Recuperação paralela aplicada ao final do bimestre.',
                    )
                    rec.full_clean()
                    rec.save()
                    self._contar('recuperacoes')

    def _registros(self, turma, disciplina, alunos, avaliacoes):
        """Mantem o RegistroAlunoTurma coerente com aulas e presencas lancadas."""
        medias = self._medias_bimestre(avaliacoes, alunos)
        aulas = {aula.id: aula.quantidade_aulas for aula in Aula.objects.filter(turma=turma, disciplina=disciplina)}
        total_aulas = sum(aulas.values())
        faltas = {}
        for presenca in Presenca.objects.filter(aula_id__in=aulas, presente=False):
            faltas[presenca.aluno_id] = faltas.get(presenca.aluno_id, 0) + aulas[presenca.aula_id]
        for aluno in alunos:
            registro = RegistroAlunoTurma.objects.filter(turma=turma, aluno=aluno, disciplina=disciplina).first()
            criado = registro is None
            registro = registro or RegistroAlunoTurma(turma=turma, aluno=aluno, disciplina=disciplina)
            registro.total_aulas = total_aulas
            registro.total_faltas = faltas.get(aluno.id, 0)
            registro.nota1 = medias.get((aluno.id, 1))
            registro.nota2 = medias.get((aluno.id, 2))
            registro.nota3 = medias.get((aluno.id, 3))
            registro.full_clean()
            registro.save()
            self._contar('registros', criado)

    # ------------------------------------------------------------------
    # Alertas de baixa frequencia, desempenho e atividades
    # ------------------------------------------------------------------
    def _alerta(self, professor, turma, titulo, mensagem, prioridade, quando):
        alerta, criado = Alerta.objects.get_or_create(
            usuario=professor, turma=turma, tipo='SISTEMA', titulo=titulo[:120],
            defaults={'mensagem': mensagem, 'prioridade': prioridade},
        )
        if criado:
            Alerta.objects.filter(pk=alerta.pk).update(created_at=aware(quando, 7, 30))
        self._contar('alertas_sistema', criado)

    def _alertas_sistema(self, professor):
        from planejamento.views import _media_periodo, _resumo_presencas_aulas

        quando = self.hoje - timedelta(days=1)
        for turma in Turma.objects.filter(professor=professor):
            alunos = list(turma.alunos.filter(ativo=True))
            baixa_frequencia = {}
            abaixo_media = {}
            for disciplina in turma.disciplinas.filter(professor=professor):
                _, resumo = _resumo_presencas_aulas(turma, disciplina, alunos)
                for aluno in alunos:
                    percentual = resumo[aluno.id]['percentual']
                    if percentual is not None and percentual < Decimal('75.00'):
                        baixa_frequencia.setdefault(aluno, []).append(
                            f"{disciplina.nome}: {str(percentual).replace('.', ',')}% ({resumo[aluno.id]['faltas']} faltas)"
                        )
                avaliacoes = list(turma.processos_avaliativos.filter(disciplina=disciplina, notas__isnull=False).distinct())
                total_valor = sum((avaliacao.valor_maximo for avaliacao in avaliacoes), Decimal('0'))
                soma = {}
                for nota in NotaAluno.objects.filter(processo__in=avaliacoes, aluno__in=alunos):
                    soma[nota.aluno_id] = soma.get(nota.aluno_id, Decimal('0')) + nota.nota
                for aluno in alunos:
                    media = _media_periodo(soma.get(aluno.id), total_valor, disciplina.nota_total)
                    if media is not None and media < disciplina.media_aprovacao:
                        abaixo_media.setdefault(aluno, []).append(f"{disciplina.nome}: {str(media).replace('.', ',')}")

                for avaliacao in turma.processos_avaliativos.filter(disciplina=disciplina):
                    avaliacao.atualizar_status_automatico()
                    rotulo = f'{disciplina.nome} - {avaliacao.titulo}'
                    if avaliacao.status == 'FINALIZADA' and not avaliacao.notas.exists():
                        self._alerta(professor, turma, f'Correção pendente: {rotulo}',
                                     f'O prazo de "{avaliacao.titulo}" terminou em {avaliacao.data_fechamento:%d/%m/%Y} '
                                     'e as notas ainda não foram lançadas.', 'alta', quando)
                    elif avaliacao.status == 'EM_ANDAMENTO':
                        self._alerta(professor, turma, f'Atividade em andamento: {rotulo}',
                                     f'Entrega prevista até {avaliacao.data_fechamento:%d/%m/%Y}.', 'baixa', quando)
                    elif avaliacao.status == 'A_REALIZAR' and avaliacao.data_abertura <= self.hoje + timedelta(days=21):
                        self._alerta(professor, turma, f'Avaliação agendada: {rotulo}',
                                     f'Aplicação prevista para {avaliacao.data_abertura:%d/%m/%Y}.', 'media', quando)

            for aluno, itens in baixa_frequencia.items():
                self._alerta(professor, turma, f'Baixa frequência: {aluno.nome}',
                             f'{aluno.nome} está abaixo de 75% de frequência em: {"; ".join(itens)}. '
                             'Sugere-se contato com a família.', 'alta', quando)
            for aluno, itens in abaixo_media.items():
                self._alerta(professor, turma, f'Desempenho abaixo da média: {aluno.nome}',
                             f'Média parcial abaixo de 6,0 em: {"; ".join(itens)}.',
                             'alta' if len(itens) >= 2 else 'media', quando)

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------
    def _resumo(self, professores):
        self.stdout.write(self.style.SUCCESS('\nDados de demonstracao prontos.'))
        if self.contagem:
            self.stdout.write('Registros criados nesta execucao:')
            for chave, valor in sorted(self.contagem.items()):
                self.stdout.write(f'  {chave:<18} {valor}')
        else:
            self.stdout.write('Nenhum registro novo (os dados ja existiam).')
        self.stdout.write('\nAcesso (dados ficticios):')
        for usuario in professores.values():
            turmas = Turma.objects.filter(professor=usuario).count()
            self.stdout.write(f'  {usuario.username:<14} {usuario.get_full_name():<28} {turmas} turma(s)')
