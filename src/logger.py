import time
from contextlib import contextmanager
from typing import Generator, List
from rich.console import Console

console = Console()


class StageLogger:
    """Collects sub-step logs during a stage and renders them nicely with branch characters."""

    def __init__(self, step_num: int, total_steps: int, title: str):
        self.step_num = step_num
        self.total_steps = total_steps
        self.title = title
        self.messages: List[str] = []
        self.start_time: float = 0.0
        self.elapsed: float = 0.0

    def log(self, message: str) -> None:
        """Add a log entry for this stage."""
        self.messages.append(message)

    def finish(self, success: bool = True) -> None:
        """Print the stage summary header and sub-step tree."""
        step_str = f"[bold cyan][STEP {self.step_num}/{self.total_steps}][/bold cyan] {self.title}"
        status_str = f"[bold green]DONE[/bold green] ({self.elapsed:.3f}s)" if success else f"[bold red]FAILED[/bold red] ({self.elapsed:.3f}s)"

        # Calculate dots for clean terminal alignment (around 65 chars width)
        plain_len = len(f"[STEP {self.step_num}/{self.total_steps}] {self.title}")
        dots_count = max(2, 60 - plain_len)
        dots = "." * dots_count

        console.print(f"{step_str} {dots} {status_str}")

        total_msgs = len(self.messages)
        for idx, msg in enumerate(self.messages):
            branch = "└─" if idx == total_msgs - 1 else "├─"
            console.print(f"   [dim]{branch}[/dim] {msg}")


@contextmanager
def stage_timer(step_num: int, total_steps: int, title: str) -> Generator[StageLogger, None, None]:
    """Context manager for timing pipeline stages and formatting logs."""
    stage = StageLogger(step_num=step_num, total_steps=total_steps, title=title)
    stage.start_time = time.perf_counter()
    success = False
    try:
        yield stage
        success = True
    except Exception as e:
        stage.elapsed = time.perf_counter() - stage.start_time
        stage.log(f"[bold red]Error:[/bold red] {e}")
        stage.finish(success=False)
        raise
    else:
        stage.elapsed = time.perf_counter() - stage.start_time
        stage.finish(success=True)

