from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0010_remove_conteudoprogramatico_data_prevista_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfilusuario',
            name='foto',
            field=models.ImageField(blank=True, null=True, upload_to='usuarios/fotos/', verbose_name='foto'),
        ),
    ]

