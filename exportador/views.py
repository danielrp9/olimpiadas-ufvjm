from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from .services import gerar_planilha_jogos_xlsx


class ExportarJogosExcelView(LoginRequiredMixin, View):
    """
    View independente para geração e download da planilha Excel (.xlsx) contendo
    todos os jogos e rascunhos de chaveamento para a Comissão Organizadora.
    """
    def get(self, request):
        if not getattr(request.user, 'is_comissao', False) and not request.user.is_superuser:
            messages.error(request, "Acesso restrito à Comissão Organizadora.")
            return redirect('dashboard')
            
        modalidade_id = request.GET.get('modalidade_id')
        if modalidade_id:
            try:
                modalidade_id = int(modalidade_id)
            except ValueError:
                modalidade_id = None
                
        # Gera os bytes da planilha Excel usando o serviço isolado
        xlsx_bytes = gerar_planilha_jogos_xlsx(modalidade_id=modalidade_id)
        
        timestamp = timezone.now().strftime('%Y%m%d_%H%M')
        if modalidade_id:
            filename = f"Jogos_Modalidade_{modalidade_id}_{timestamp}.xlsx"
        else:
            filename = f"Planilha_Geral_Jogos_Olimpiadas_{timestamp}.xlsx"
            
        response = HttpResponse(
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
