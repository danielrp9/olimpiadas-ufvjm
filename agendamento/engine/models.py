from dataclasses import dataclass, field
from datetime import date, time, datetime, timedelta
from typing import List, Dict, Set, Optional, Any


@dataclass
class DayWindow:
    """Janela de funcionamento de uma data da competição."""
    date: date
    start_time: time
    end_time: time

    @property
    def total_minutes(self) -> int:
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time)
        return int((end_dt - start_dt).total_seconds() // 60)


@dataclass
class ResourceConfig:
    """Configuração de um recurso físico (quadra, campo, ginásio, mesa)."""
    id: Any
    name: str
    allowed_modalities: Set[Any] = field(default_factory=set)  # IDs ou nomes de modalidades; vazio = todas
    order: int = 1
    is_active: bool = True

    def accepts_modality(self, modality_id: Any) -> bool:
        if not self.allowed_modalities:
            return True
        return modality_id in self.allowed_modalities


@dataclass
class ModalityParam:
    """Parâmetros de tempo para cada modalidade."""
    modality_id: Any
    name: str
    duration_minutes: int = 50
    buffer_minutes: int = 10


@dataclass
class PhaseConstraint:
    """Restrição obrigatória de datas por fase."""
    phase_code: str
    phase_name: str
    modality_id: Optional[Any] = None  # None = aplicável a todas
    allowed_dates: Set[date] = field(default_factory=set)  # Vazio = qualquer data geral
    precedence_order: int = 0


@dataclass
class MatchRequest:
    """Demanda de partida a ser alocada pelo gerador."""
    id: Any
    jogo_id: Optional[Any] = None
    modality_id: Any = None
    modality_name: str = ""
    phase_code: str = ""
    phase_display: str = ""
    time_a_id: Optional[Any] = None
    time_a_name: str = "A definir"
    time_b_id: Optional[Any] = None
    time_b_name: str = "A definir"
    duration_minutes: int = 50
    buffer_minutes: int = 10
    depends_on_match_ids: List[Any] = field(default_factory=list)
    precedence_order: int = 0
    fixed_date: Optional[date] = None
    fixed_time: Optional[time] = None

    @property
    def total_slot_minutes(self) -> int:
        return self.duration_minutes + self.buffer_minutes

    @property
    def teams(self) -> Set[Any]:
        res = set()
        if self.time_a_id is not None:
            res.add(self.time_a_id)
        if self.time_b_id is not None:
            res.add(self.time_b_id)
        return res

    @property
    def is_net_sport(self) -> bool:
        """Indica se a modalidade exige montagem de rede (ex: Vôlei, Peteca, etc.)"""
        m_lower = self.modality_name.lower()
        return ('volei' in m_lower or 'vôlei' in m_lower or 'peteca' in m_lower or 
                'futevolei' in m_lower or 'futevôlei' in m_lower)


@dataclass
class AllocatedSlot:
    """Partida alocada em data, horário e recurso específico."""
    match_id: Any
    match_request: MatchRequest
    date: date
    start_time: time
    end_time: time
    resource_id: Any
    resource_name: str

    @property
    def start_datetime(self) -> datetime:
        return datetime.combine(self.date, self.start_time)

    @property
    def end_datetime(self) -> datetime:
        return datetime.combine(self.date, self.end_time)


@dataclass
class DiagnosticIssue:
    """Diagnóstico explicativo de inconsistência ou capacidade insuficiente."""
    code: str
    level: str  # 'ERROR', 'WARNING', 'INFO'
    phase_code: Optional[str] = None
    phase_name: Optional[str] = None
    date: Optional[date] = None
    message: str = ""
    details: str = ""
    recommendation: str = ""


@dataclass
class EngineResult:
    """Resultado final da execução do motor de agendamento."""
    success: bool
    allocations: List[AllocatedSlot] = field(default_factory=list)
    issues: List[DiagnosticIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
