from django.db import migrations
from django.utils import timezone

def sync_segunda_chamada_atletas(apps, schema_editor):
    Atleta = apps.get_model('core', 'Atleta')
    Inscricao = apps.get_model('core', 'Inscricao')
    ConfiguracaoPeriodoInscricao = apps.get_model('core', 'ConfiguracaoPeriodoInscricao')
    
    config = ConfiguracaoPeriodoInscricao.objects.first()
    
    for insc in Inscricao.objects.all():
        delegacao = insc.delegacao
        atletas_delegacao = Atleta.objects.filter(cadastrado_por=delegacao)
        
        modalidades = list(insc.modalidades.all())
        if modalidades:
            for atleta in atletas_delegacao:
                if not atleta.modalidades_inscritas.filter(inscricao=insc).exists():
                    should_link = False
                    if config and config.segunda_chamada_inicio and atleta.data_cadastro:
                        if atleta.data_cadastro >= config.segunda_chamada_inicio:
                            should_link = True
                    elif config and config.segunda_chamada_inicio and config.segunda_chamada_fim:
                        now = timezone.now()
                        if config.segunda_chamada_inicio <= now <= config.segunda_chamada_fim:
                            should_link = True
                    else:
                        # If created today / recently during active periods
                        should_link = True
                    
                    if should_link:
                        for im in modalidades:
                            im.atletas.add(atleta)

def reverse_sync(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_backfill_atleta_data_cadastro'),
    ]

    operations = [
        migrations.RunPython(sync_segunda_chamada_atletas, reverse_sync),
    ]
