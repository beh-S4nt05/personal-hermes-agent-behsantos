# -*- coding: utf-8 -*-
"""🌅 Modo Vida — v5.0.0 (PR #10).

O Betterme cuidando da rotina do operador:

- **Relatório diário** (manhã): o que rodou (atividades 24 h), o que
  aprendeu (rascunhos aguardando aprovação) e o que precisa de você
  (aprovações pendentes) — entregue via Telegram quando ativo.
- **Curadoria semanal de aprendizados**: rascunhos envelhecidos (>
  7 dias) viram UM resumo para decisão em lote; os originais vão para
  `aprendidos/arquivados/` (nada é apagado).
- **Missões agendadas**: tarefas `modo-vida:` no agendador — 100%
  determinísticas e LOCAIS (zero tokens, zero LLM, zero rede além do
  Telegram opcional). Nunca escrevem fora do data-dir.

PRIVACIDADE (lei): o relatório é canal de CONTROLE — só contagens e
títulos curtos, e o texto inteiro passa pelo DLP `mascarar()` ANTES de
qualquer envio. Hard gates continuam valendo em qualquer autonomia.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

_PREFIXO = "modo-vida:"
_DIAS_CURADORIA = 7


# ------------------------------------------------------------- dados
def _atividades_24h(cfg) -> Counter:
    """Contagem de atividades das últimas 24 h por fonte (agent.log)."""
    cont: Counter = Counter()
    log = Path(cfg.logfile)
    if not log.is_file():
        return cont
    agora = time.time()
    try:
        linhas = log.read_text(encoding="utf-8",
                               errors="replace").splitlines()[-2000:]
    except OSError:
        return cont
    for lin in linhas:
        if len(lin) < 22 or not lin.startswith("["):
            continue
        try:
            ts = time.mktime(time.strptime(lin[1:20], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if agora - ts > 86400:
            continue
        resto = lin[21:].strip()
        if resto.startswith("["):
            fonte = resto[1:resto.find("]")] or "?"
            cont[fonte] += 1
    return cont


def _aprovacoes_pendentes(cfg) -> int:
    """Aprovações esperando o operador (pending_approvals.json)."""
    p = Path(cfg.data_dir) / "pending_approvals.json"
    if not p.is_file():
        return 0
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(dados, dict):
        return len(dados.get("pendencias") or dados)
    return len(dados or [])


def _titulo_curto(t: str, n: int = 60) -> str:
    return " ".join(str(t or "").split())[:n]


# ------------------------------------------------------------- relatório
def relatorio_diario(cfg, _enviar=None) -> dict:
    """🌅 o que rodou · o que aprendeu · o que precisa de você.
    Texto DLP-mascarado antes de QUALQUER envio (canal de controle)."""
    import datetime as _dt
    hoje = _dt.date.today().strftime("%d/%m/%Y")
    atv = _atividades_24h(cfg)
    total_atv = sum(atv.values())
    partes = [f"🌅 RELATÓRIO DIÁRIO — {hoje}"]
    if total_atv:
        detalhe = " · ".join(f"{k} {v}" for k, v in
                             atv.most_common(6))
        partes.append(f"📊 O que rodou (24h): {total_atv} atividade(s) — "
                      f"{detalhe}")
    else:
        partes.append("📊 O que rodou (24h): nenhuma atividade registrada")
    # missões agendadas
    try:
        from .scheduler import ScheduleStore
        entries = [e for e in ScheduleStore(cfg).list_all()
                   if e.get("enabled")]
        partes.append(f"🗂 Missões agendadas: {len(entries)} ativa(s)")
    except Exception:  # noqa: BLE001
        partes.append("🗂 Missões agendadas: (indisponível)")
    # aprendizados
    try:
        from . import learning
        pend = learning.pendentes(cfg)
    except Exception:  # noqa: BLE001
        pend = []
    if pend:
        titulos = " · ".join(f"'{_titulo_curto(p.get('titulo'))}'"
                             for p in pend[:5])
        partes.append(f"📚 O que aprendi (aguardando você): "
                      f"{len(pend)} rascunho(s) — {titulos}")
    else:
        partes.append("📚 O que aprendi: nada novo aguardando aprovação")
    # pendências
    n_ap = _aprovacoes_pendentes(cfg)
    partes.append(f"🔒 Precisa de você: {n_ap} aprovação(ões) pendente(s)"
                  + (f" · {len(pend)} aprendizado(s) para revisar"
                     if pend else ""))
    texto = "\n".join(partes)
    # DLP (lei): canal de controle — nada sensível sai
    try:
        from .varredura import mascarar
        texto = mascarar(texto)
    except Exception:  # noqa: BLE001
        pass
    enviado = False
    if _enviar is not None:
        try:
            _enviar(texto)
            enviado = True
        except Exception:  # noqa: BLE001
            enviado = False
    else:
        enviado = _enviar_telegram(cfg, texto)
    try:
        from . import activity
        activity.log(cfg, "vida",
                     f"🌅 relatório diário · {total_atv} atividade(s) · "
                     f"{len(pend)} rascunho(s) · {n_ap} aprovação(ões) · "
                     f"entrega: {'telegram' if enviado else 'local'}")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "texto": texto, "enviado": enviado,
            "atividades": total_atv, "rascunhos": len(pend),
            "aprovacoes": n_ap}


def _enviar_telegram(cfg, texto: str) -> bool:
    """Entrega best-effort via Telegram (se ativo e configurado)."""
    try:
        if not getattr(cfg, "telegram_on", False):
            return False
        from . import telegram_gw
        canal = telegram_gw.CanalTelegram(cfg)
        canal.enviar(texto)
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------- curadoria
def curadoria(cfg, dias: int = _DIAS_CURADORIA) -> dict:
    """🗂 rascunhos envelhecidos → 1 resumo p/ decisão em lote;
    originais ARQUIVADOS (movidos, nunca apagados)."""
    from . import learning
    pend = learning.pendentes(cfg)
    agora = time.time()
    antigos = [e for e in pend
               if agora - float(e.get("ts") or 0) > dias * 86400]
    if not antigos:
        return {"ok": True, "arquivados": 0,
                "msg": f"nenhum rascunho com mais de {dias} dias — nada "
                       "a curar"}
    linhas = [f"- [{e.get('id')}] {_titulo_curto(e.get('titulo'))} "
              f"({e.get('tipo', '?')})" for e in antigos]
    resumo = {
        "tipo": "resumo",
        "titulo": f"Curadoria semanal: {len(antigos)} aprendizado(s) "
                  "para decidir em lote",
        "rascunho": ("RESUMO PARA DECISÃO EM LOTE (curadoria do Modo "
                     "Vida — rascunhos com mais de "
                     f"{dias} dias):\n" + "\n".join(linhas)
                     + "\n\nAplique com: betterme aprendidos"),
        "origem": "curadoria",
        "objetivo": "decisão em lote dos aprendizados envelhecidos",
    }
    learning._salvar(cfg, resumo)                     # noqa: SLF001
    # arquiva os originais (move p/ arquivados/ — nada é apagado)
    destino = learning._dir(cfg) / "arquivados"       # noqa: SLF001
    destino.mkdir(parents=True, exist_ok=True)
    for e in antigos:
        orig = learning._dir(cfg) / f"{e.get('id')}.json"  # noqa: SLF001
        if orig.is_file():
            orig.rename(destino / orig.name)
    try:
        from . import activity
        activity.log(cfg, "vida",
                     f"🗂 curadoria semanal · {len(antigos)} rascunho(s) "
                     "envelhecidos → resumo em lote + arquivados")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "arquivados": len(antigos),
            "resumo_id": resumo["id"],
            "msg": (f"{len(antigos)} rascunho(s) envelhecidos viraram o "
                    f"resumo {resumo['id']} (decisão em lote); originais "
                    "arquivados")}


# ------------------------------------------------------------- agendamento
def registrar(cfg) -> dict:
    """Cria (se faltarem) as missões do Modo Vida no agendador:
    relatório diário 07:00 + curadoria semanal seg 08:30."""
    from .scheduler import ScheduleStore, parse_schedule
    store = ScheduleStore(cfg)
    existentes = {str(e.get("input") or "") for e in store.list_all()}
    criadas = []
    desejadas = [
        ("🌅 Modo Vida: relatório diário",
         f"{_PREFIXO} relatorio", "diário 07:00"),
        ("🗂 Modo Vida: curadoria semanal de aprendizados",
         f"{_PREFIXO} curadoria", "seg 08:30"),
    ]
    for titulo, entrada, quando in desejadas:
        if entrada in existentes:
            continue
        spec = parse_schedule(quando)
        entry = store.create(entrada, spec)
        entry["titulo"] = titulo
        store.save(entry)
        criadas.append(entrada)
    return {"ok": True, "criadas": criadas,
            "msg": (f"{len(criadas)} missão(ões) do Modo Vida registrada(s)"
                    if criadas else "missões do Modo Vida já registradas")}


def executar_tarefa(cfg, entry: dict) -> dict:
    """Dispatcher das missões `modo-vida:` — determinístico e local
    (chamado pelo agendador ANTES do loop do LLM; zero tokens)."""
    t0 = time.time()
    pedido = str(entry.get("input") or "").strip().lower()
    acao = pedido[len(_PREFIXO):].strip()
    if acao.startswith("relatorio"):
        r = relatorio_diario(cfg)
        saida, status = r["texto"], "ok"
    elif acao.startswith("curadoria"):
        r = curadoria(cfg)
        saida, status = ("🗂 " + r["msg"]), ("ok" if r["ok"] else "error")
    else:
        saida = (f"✖ ação de modo-vida desconhecida: {acao!r} "
                 "(relatorio|curadoria)")
        status = "error"
    return {"status": status, "output": saida, "tools": [],
            "duration_s": round(time.time() - t0, 2)}


def status(cfg) -> dict:
    """Estado do Modo Vida: missões registradas + próximos disparos."""
    from .scheduler import ScheduleStore, next_run
    store = ScheduleStore(cfg)
    missões = []
    for e in store.list_all():
        if not str(e.get("input") or "").startswith(_PREFIXO):
            continue
        nr = next_run(e)
        missões.append({
            "input": e.get("input"), "titulo": e.get("titulo", ""),
            "enabled": bool(e.get("enabled")),
            "ultima": e.get("last_status"),
            "proxima": nr.strftime("%Y-%m-%d %H:%M") if nr else None,
        })
    return {"ok": True, "missoes": missões,
            "registrado": bool(missões)}


# ------------------------------------------------------------- CLI
def cmd(args, cfg) -> None:
    """`betterme vida status|relatorio|curadoria|registrar`."""
    acao = getattr(args, "acao", "status")
    if acao == "status":
        st = status(cfg)
        if not st["registrado"]:
            print("ℹ️ Modo Vida sem missões — rode `betterme vida registrar`")
            return
        print(f"🌅 Modo Vida — {len(st['missoes'])} missão(ões):")
        for m in st["missoes"]:
            estado = "ativa" if m["enabled"] else "pausada"
            print(f"  · {m['input']} [{estado}] · última: "
                  f"{m['ultima'] or '—'} · próxima: {m['proxima'] or '—'}")
        return
    if acao == "relatorio":
        r = relatorio_diario(cfg)
        print(r["texto"])
        destino = ("Telegram" if r["enviado"] else
                   "local (Telegram desligado — betterme telegram start)")
        print("\n→ entrega: " + destino)
        return
    if acao == "curadoria":
        r = curadoria(cfg)
        print(("🗂 " if r["ok"] else "✖ ") + r["msg"])
        return
    if acao == "registrar":
        r = registrar(cfg)
        print("✔ " + r["msg"])
        return
    print(f"✖ ação desconhecida: {acao!r} "
          "(status|relatorio|curadoria|registrar)")
    raise SystemExit(1)
