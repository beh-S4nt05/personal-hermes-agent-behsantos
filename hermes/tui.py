"""Chat interativo no terminal (TUI) — `hermes chat`."""

from __future__ import annotations


from .agent import Agent
from .config import Config
from .tools import is_dangerous, tool_summary

try:  # enfeites opcionais
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()
    HAS_RICH = True
except Exception:  # pragma: no cover
    console = None
    HAS_RICH = False

BOLD, CYAN, YELLOW, DIM, RESET = "\033[1m", "\033[96m", "\033[93m", "\033[2m", "\033[0m"


def _emit(text: str, **kwargs) -> None:
    if HAS_RICH:
        console.print(text, **kwargs)
    else:
        print(text)


def banner(cfg: Config) -> None:
    model = cfg.model + ("  [SIMULADO]" if cfg.mock else "")
    line = "─" * 54
    _emit(f"{CYAN}{BOLD}◈ HERMES AGENT{RESET} {DIM}— agente Linux local{RESET}")
    _emit(f"{DIM}{line}{RESET}")
    _emit(f"  modelo : {model}")
    _emit(f"  ollama : {cfg.ollama_url}")
    _emit(f"  dados  : {cfg.data_dir}")
    _emit(f"  tools  : {tool_summary()}")
    _emit(f"{DIM}  comandos: /reset limpa, /tools lista, /sai sai{RESET}")
    _emit(f"{DIM}{line}{RESET}\n")


def _confirm_dangerous(name: str, args: dict) -> bool:
    if name != "run_command":
        return True
    cmd = str(args.get("command", ""))
    if not is_dangerous(cmd):
        return True
    _emit(f"{YELLOW}⚠ comando arriscado proposto pelo agente:{RESET}\n  {cmd}")
    try:
        answer = input("  executar mesmo assim? [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("s", "sim", "y", "yes")


def run_chat(cfg: Config) -> None:
    banner(cfg)
    agent = Agent(cfg)
    history: list[dict] = []

    while True:
        try:
            user_input = input(f"{BOLD}{CYAN}você ▸{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        low = user_input.lower()
        if low in ("/sai", "/exit", "/quit", "sair"):
            break
        if low == "/reset":
            history.clear()
            _emit(f"{DIM}— memória limpa —{RESET}")
            continue
        if low == "/tools":
            _emit(f"disponíveis: {tool_summary()}")
            continue

        history.append({"role": "user", "content": user_input})
        print()

        state = {"in_tool": False}

        # default=state: amarra o valor desta iteração (B023) — o dict é
        # o mesmo objeto, mutado nunca reatribuído, comportamento idêntico
        def on_event(event: dict, state: dict = state) -> None:
            etype = event.get("type")
            if etype == "token":
                if state["in_tool"]:
                    print()
                    state["in_tool"] = False
                print(event["content"], end="", flush=True)
            elif etype == "tool_start":
                if state["in_tool"]:
                    print()
                state["in_tool"] = True
                name = event.get("name")
                args = event.get("args") or {}
                arg_str = " ".join(f"{k}={v!r}" for k, v in args.items()) or ""
                if HAS_RICH:
                    console.print(f"[dim]🔧 {name}({arg_str})[/dim]")
                else:
                    print(f"{DIM}🔧 {name}({arg_str}){RESET}")
            elif etype == "error":
                if state["in_tool"]:
                    print()
                    state["in_tool"] = False
                _emit(f"{YELLOW}! {event.get('message')}{RESET}")

        try:
            final = agent.run(history, on_event=on_event, allow_tool=_confirm_dangerous)
        except KeyboardInterrupt:
            print(f"\n{DIM}(interrompido){RESET}")
            continue
        print("\n")
        if HAS_RICH and final and not final.startswith("[erro"):
            console.print(Panel(Markdown(final), border_style="bright_black", title="hermes"))
        else:
            print(final)
        print()
        history.append({"role": "assistant", "content": final})

    _emit(f"{DIM}até logo ◈{RESET}")
