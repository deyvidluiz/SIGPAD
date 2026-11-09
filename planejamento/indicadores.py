"""Indicadores academicos calculados no banco para a area administrativa.

As regras seguem as mesmas usadas nas telas do professor (views.py):
  * frequencia: aulas sem registro de presenca contam como presenca; abaixo de
    75% e "baixa frequencia";
  * desempenho: soma das notas / valor das avaliacoes ja com notas lancadas,
    na escala da nota total da disciplina; abaixo da media de aprovacao e
    "abaixo da media".
"""

from decimal import Decimal

from django.db.models import Sum

from .models import Aluno, Aula, Disciplina, NotaAluno, Presenca, ProcessoAvaliativo

LIMITE_FREQUENCIA = Decimal('75.00')
DUAS_CASAS = Decimal('0.01')


def _media(valores):
    valores = list(valores)
    if not valores:
        return None
    return (sum(valores, Decimal('0')) / len(valores)).quantize(DUAS_CASAS)


def indicadores_por_turma(turmas):
    """Retorna {turma_id: {...}} com frequencia e desempenho agregados."""
    turma_ids = [turma.id for turma in turmas]
    resultado = {
        turma_id: {
            'alunos': 0,
            'frequencia_media': None,
            'alunos_baixa_frequencia': 0,
            'pares_baixa_frequencia': 0,
            'media_geral': None,
            'alunos_abaixo_media': 0,
            'pares_abaixo_media': 0,
        }
        for turma_id in turma_ids
    }
    if not turma_ids:
        return resultado

    alunos_por_turma = {}
    for aluno_id, turma_id in Aluno.objects.filter(turma_id__in=turma_ids, ativo=True).values_list('id', 'turma_id'):
        alunos_por_turma.setdefault(turma_id, []).append(aluno_id)

    disciplinas = {
        disciplina.id: disciplina
        for disciplina in Disciplina.objects.filter(turma_id__in=turma_ids)
    }

    # Frequencia ---------------------------------------------------------------
    total_aulas = dict(
        Aula.objects.filter(disciplina_id__in=disciplinas)
        .values('disciplina_id')
        .annotate(total=Sum('quantidade_aulas'))
        .values_list('disciplina_id', 'total')
    )
    faltas = {
        (linha['aluno_id'], linha['aula__disciplina_id']): linha['faltas']
        for linha in Presenca.objects.filter(
            presente=False, aula__disciplina_id__in=disciplinas, aluno__ativo=True,
        ).values('aluno_id', 'aula__disciplina_id').annotate(faltas=Sum('aula__quantidade_aulas'))
    }

    # Desempenho ---------------------------------------------------------------
    valor_lancado = {}
    for _, disciplina_id, valor in (
        ProcessoAvaliativo.objects.filter(disciplina_id__in=disciplinas, notas__isnull=False)
        .values_list('id', 'disciplina_id', 'valor_maximo').distinct()
    ):
        valor_lancado[disciplina_id] = valor_lancado.get(disciplina_id, Decimal('0')) + valor
    soma_notas = {
        (linha['aluno_id'], linha['processo__disciplina_id']): linha['soma']
        for linha in NotaAluno.objects.filter(
            processo__disciplina_id__in=disciplinas, aluno__ativo=True,
        ).values('aluno_id', 'processo__disciplina_id').annotate(soma=Sum('nota'))
    }

    for turma_id in turma_ids:
        alunos = alunos_por_turma.get(turma_id, [])
        dados = resultado[turma_id]
        dados['alunos'] = len(alunos)
        frequencias, medias = [], []
        baixa_freq, abaixo_media = set(), set()
        for disciplina in (d for d in disciplinas.values() if d.turma_id == turma_id):
            total = total_aulas.get(disciplina.id) or 0
            valor = valor_lancado.get(disciplina.id) or Decimal('0')
            for aluno_id in alunos:
                if total:
                    falta = faltas.get((aluno_id, disciplina.id), 0)
                    frequencia = (Decimal(total - falta) / Decimal(total) * 100).quantize(DUAS_CASAS)
                    frequencias.append(frequencia)
                    if frequencia < LIMITE_FREQUENCIA:
                        baixa_freq.add(aluno_id)
                        dados['pares_baixa_frequencia'] += 1
                soma = soma_notas.get((aluno_id, disciplina.id))
                if soma is not None and valor:
                    media = (soma / valor * disciplina.nota_total).quantize(DUAS_CASAS)
                    medias.append(media)
                    if media < disciplina.media_aprovacao:
                        abaixo_media.add(aluno_id)
                        dados['pares_abaixo_media'] += 1
        dados['frequencia_media'] = _media(frequencias)
        dados['media_geral'] = _media(medias)
        dados['alunos_baixa_frequencia'] = len(baixa_freq)
        dados['alunos_abaixo_media'] = len(abaixo_media)
    return resultado


def consolidar(indicadores):
    """Soma/media dos indicadores de varias turmas."""
    valores = list(indicadores.values())
    frequencias = [item['frequencia_media'] for item in valores if item['frequencia_media'] is not None]
    medias = [item['media_geral'] for item in valores if item['media_geral'] is not None]
    return {
        'alunos': sum(item['alunos'] for item in valores),
        'alunos_baixa_frequencia': sum(item['alunos_baixa_frequencia'] for item in valores),
        'alunos_abaixo_media': sum(item['alunos_abaixo_media'] for item in valores),
        'frequencia_media': _media(frequencias),
        'media_geral': _media(medias),
    }
