from django.db import migrations
from django.utils import timezone

def backfill_atleta_data_cadastro(apps, schema_editor):
    Atleta = apps.get_model('core', 'Atleta')
    SubstituicaoAtleta = apps.get_model('core', 'SubstituicaoAtleta')
    Inscricao = apps.get_model('core', 'Inscricao')

    for atleta in Atleta.objects.all():
        delegacao = atleta.cadastrado_por
        sub = SubstituicaoAtleta.objects.filter(atleta_entrou=atleta).first()
        
        # Check if delegation has an inscription
        inscricao = Inscricao.objects.filter(delegacao=delegacao).first() if delegacao else None
        
        # Check if athlete is in any modality of the inscription
        esta_em_modalidade = atleta.modalidades_inscritas.exists() if hasattr(atleta, 'modalidades_inscritas') else False

        if sub and sub.data_substituicao:
            atleta.data_cadastro = sub.data_substituicao
        elif inscricao and esta_em_modalidade and inscricao.data_envio:
            atleta.data_cadastro = inscricao.data_envio
        elif delegacao and delegacao.date_joined:
            atleta.data_cadastro = delegacao.date_joined
        
        atleta.save(update_fields=['data_cadastro'])

def reverse_backfill(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_alter_atleta_data_cadastro'),
    ]

    operations = [
        migrations.RunPython(backfill_atleta_data_cadastro, reverse_backfill),
    ]
