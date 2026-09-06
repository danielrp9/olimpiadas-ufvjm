from django.db import migrations


def atualizar_chaveamentos_producao(apps, schema_editor):
    from core.chaveamento_services import atualizar_classificados_e_preencher_mata_mata
    from core.models import ChaveamentoModalidade

    for chaveamento in ChaveamentoModalidade.objects.all():
        try:
            atualizar_classificados_e_preencher_mata_mata(chaveamento)
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_jogo_permitir_lancamento_atletas_and_more'),
    ]

    operations = [
        migrations.RunPython(atualizar_chaveamentos_producao, reverse_code=migrations.RunPython.noop),
    ]
