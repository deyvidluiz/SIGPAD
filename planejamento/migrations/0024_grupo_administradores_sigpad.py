from django.db import migrations

GRUPO_ADMIN = 'Administradores SIGPAD'


def criar_grupo(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name=GRUPO_ADMIN)


class Migration(migrations.Migration):
    """Cria o papel de administrador da area /painel/. Nao altera dados existentes."""

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('planejamento', '0023_processoavaliativo_observacao_and_more'),
    ]

    operations = [
        # A reversao mantem o grupo para nao remover acessos ja concedidos.
        migrations.RunPython(criar_grupo, migrations.RunPython.noop),
    ]
