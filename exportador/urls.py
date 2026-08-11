from django.urls import path
from .views import ExportarJogosExcelView

app_name = 'exportador'

urlpatterns = [
    path('jogos/excel/', ExportarJogosExcelView.as_view(), name='exportar_jogos_excel'),
]
