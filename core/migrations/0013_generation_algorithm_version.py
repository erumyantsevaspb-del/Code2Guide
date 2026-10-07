from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_project_app_credentials'),
    ]

    operations = [
        migrations.AddField(
            model_name='generation',
            name='algorithm_version',
            field=models.CharField(default='V0', max_length=20, verbose_name='Версия алгоритма'),
        ),
        migrations.AddField(
            model_name='generation',
            name='code_version',
            field=models.CharField(blank=True, max_length=40, verbose_name='Git commit hash Code2Guide'),
        ),
    ]
