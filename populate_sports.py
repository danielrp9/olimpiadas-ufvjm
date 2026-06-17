import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'olimpiadas_project.settings')
django.setup()

from core.models import Modalidade

modalidades = [
    {'nome': 'Futsal Masculino', 'min': 5, 'max': 12},
    {'nome': 'Futsal Feminino', 'min': 5, 'max': 12},
    {'nome': 'Vôlei Masculino', 'min': 6, 'max': 12},
    {'nome': 'Vôlei Feminino', 'min': 6, 'max': 12},
    {'nome': 'Handebol Masculino', 'min': 7, 'max': 14},
    {'nome': 'Handebol Feminino', 'min': 7, 'max': 14},
    {'nome': 'Basquete Masculino', 'min': 5, 'max': 12},
    {'nome': 'Basquete Feminino', 'min': 5, 'max': 12},
    {'nome': 'Xadrez Misto', 'min': 1, 'max': 1},
    {'nome': 'Tênis de Mesa Misto', 'min': 1, 'max': 2},
]

for m in modalidades:
    obj, created = Modalidade.objects.get_or_create(
        nome=m['nome'],
        defaults={
            'limite_minimo_jogadores': m['min'],
            'limite_maximo_jogadores': m['max'],
            'inscricoes_abertas': True
        }
    )
    if created:
        print(f"Modalidade '{m['nome']}' criada.")
    else:
        print(f"Modalidade '{m['nome']}' já existe.")

print("População concluída!")
