from django.db import migrations


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


def criar_periodos(apps, schema_editor):
    Disciplina = apps.get_model('planejamento', 'Disciplina')
    PeriodoLetivo = apps.get_model('planejamento', 'PeriodoLetivo')
    for disciplina in Disciplina.objects.all():
        for ordem, (codigo, nome) in enumerate(PERIODOS_POR_TIPO.get(disciplina.tipo_periodo, []), start=1):
            PeriodoLetivo.objects.get_or_create(
                disciplina=disciplina,
                codigo=codigo,
                defaults={'tipo': disciplina.tipo_periodo, 'nome': nome, 'ordem': ordem},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0021_atividade_nota_professor_processoavaliativo_arquivo_and_more'),
    ]

    operations = [
        migrations.RunPython(criar_periodos, migrations.RunPython.noop),
    ]
