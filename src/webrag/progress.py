"""Optional progress and cooperative cancellation shared by CLI and desktop."""
from dataclasses import dataclass
from typing import Callable


class Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Progress:
    stage: str
    message: str
    completed: int | None = None
    total: int | None = None


ProgressCallback = Callable[[Progress], None]
CancelCallback = Callable[[], bool]


def checkpoint(cancel: CancelCallback | None) -> None:
    if cancel and cancel():
        raise Cancelled("Operação cancelada. O último índice concluído foi preservado.")


def report(callback: ProgressCallback | None, stage: str, message: str,
           completed: int | None = None, total: int | None = None) -> None:
    if callback:
        callback(Progress(stage, message, completed, total))
