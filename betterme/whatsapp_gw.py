"""Canal WhatsApp via Playwright — v4.2.0 (PR #5, decisão do operador).

A política da API oficial virou bagunça paga (out/2026: até resposta de
serviço é cobrada após franquia) — e o WhatsApp COMUM segue grátis. Em
vez de terceiros (Z-API e afins, que LÊM suas mensagens), este canal
abre o **WhatsApp Web no SEU navegador em background** (Playwright +
Chromium local): custo zero, mensagens ficam na sua máquina, e você
pode retirar quando quiser (`betterme whatsapp stop|remover`).

⚠ HONESTIDADE (leia): automação do WhatsApp Web viola os termos de uso
da Meta — há risco de banimento do número. Use um número dedicado se
isso for um problema. Módulo EXPERIMENTAL: seletores do WhatsApp Web
mudam sem aviso (constantess no topo, fáceis de corrigir).

Playwright é dependência OPCIONAL: `betterme whatsapp setup`
(pip install "betterme-agent[whatsapp]" + playwright install chromium).
"""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

# ---- seletores (WhatsApp Web, out/2026 — ajuste aqui quando mudarem)
SEL_QR = "canvas, svg[ref], div[data-ref]"
SEL_LOGADO = "div[contenteditable='true'][data-tab], header"
SEL_MSGS = "div[data-id][data-preferred-id]"
SEL_ENTRADA = "footer div[contenteditable='true']"
URL_WEB = "https://web.whatsapp.com"
URL_SEND = "https://web.whatsapp.com/send?phone={fone}&text={texto}"


def perfil_dir(cfg) -> Path:
    return Path(cfg.data_dir) / "whatsapp-profile"


def qr_path(cfg) -> Path:
    return Path(cfg.data_dir) / "whatsapp-qr.png"


def numeros_autorizados(cfg) -> set[str]:
    p = Path(cfg.data_dir) / "whatsapp-numeros.txt"
    try:
        return {l.strip() for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()}
    except OSError:
        return set()


def autorizar_numero(cfg, fone: str) -> None:
    p = Path(cfg.data_dir) / "whatsapp-numeros.txt"
    atuais = numeros_autorizados(cfg)
    atuais.add("".join(c for c in str(fone) if c.isdigit()))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(sorted(atuais)) + "\n", encoding="utf-8")


def playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


INSTRUCAO_SETUP = (
    "para ativar o canal WhatsApp:\n"
    "  pip install \"betterme-agent[whatsapp]\"\n"
    "  playwright install chromium\n"
    "  betterme whatsapp start   (QR aparece em "
    "<data>/whatsapp-qr.png — escaneie com o celular)"
)


class CanalWhatsapp:
    """Controller do WhatsApp Web (Playwright injetável p/ testes)."""

    INTERVALO_S = 3.0

    def __init__(self, cfg, _pw=None):
        self.cfg = cfg
        self._pw = _pw            # fábrica (sync_playwright fake ou real)
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._gw = None
        self._vistas: set[str] = set()

    def disponivel(self) -> bool:
        return self._pw is not None or playwright_ok()

    def autorizado(self, remetente: str) -> bool:
        return "".join(c for c in str(remetente) if c.isdigit()) in \
            numeros_autorizados(self.cfg)

    # ---- interface mínima de canal
    def enviar(self, texto: str, fone: str | None = None) -> None:
        fones = [fone] if fone else sorted(numeros_autorizados(self.cfg))
        page = getattr(self, "_page", None)
        if page is None:
            return
        for f in fones:
            try:
                page.goto(URL_WEB + f"/send?phone={f}")
                page.wait_for_selector(SEL_ENTRADA, timeout=15000)
                page.fill(SEL_ENTRADA, texto[:3500])
                page.keyboard.press("Enter")
            except Exception:  # noqa: BLE001
                pass

    def _parear(self, page) -> bool:
        """Primeira vez: salva QR p/ o operador escanear."""
        try:
            page.goto(URL_WEB, wait_until="domcontentloaded")
            page.wait_for_selector(SEL_LOGADO, timeout=8000)
            return True                       # já logado (perfil salvo)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.goto(URL_WEB, wait_until="domcontentloaded")
            page.wait_for_selector(SEL_QR, timeout=20000)
            qr_path(self.cfg).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(qr_path(self.cfg)))
            print(f"📱 QR salvo em {qr_path(self.cfg)} — escaneie com o "
                  f"celular (WhatsApp → Aparelhos conectados)")
            page.wait_for_selector(SEL_LOGADO, timeout=90000)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _ler_novas(self, page) -> list[tuple[str, str]]:
        """[(remetente, texto)] das mensagens ainda não vistas."""
        out = []
        try:
            for el in page.query_selector_all(SEL_MSGS):
                data_id = el.get_attribute("data-id") or ""
                if not data_id or data_id in self._vistas:
                    continue
                self._vistas.add(data_id)
                texto = (el.inner_text() or "").strip()
                if texto:
                    out.append(("", texto))
        except Exception:  # noqa: BLE001
            pass
        return out

    def _loop(self) -> None:
        sync = self._pw or self._pw_real()
        with sync() as p:
            perfil_dir(self.cfg).mkdir(parents=True, exist_ok=True)
            browser = p.chromium.launch_persistent_context(
                str(perfil_dir(self.cfg)), headless=True)
            page = browser.new_page()
            self._page = page
            try:
                if not self._parear(page):
                    print("✖ WhatsApp: pareamento falhou (QR não escaneado "
                          "em 90 s)")
                    return
                while not self._parar.is_set():
                    if self._gw is not None:
                        for _rem, texto in self._ler_novas(page):
                            resp = self._gw.receber(self, _rem, texto)
                            if resp:
                                self.enviar(resp)
                    time.sleep(self.INTERVALO_S)
            finally:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass

    @staticmethod
    def _pw_real():
        from playwright.sync_api import sync_playwright
        return sync_playwright

    def iniciar(self, gw) -> None:
        self._gw = gw
        if self._thread is None and not self._parar.is_set():
            self._thread = threading.Thread(target=self._loop,
                                            daemon=True)
            self._thread.start()

    def parar(self) -> None:
        self._parar.set()


def remover(cfg) -> str:
    """Retira o canal por completo: perfil, QR e números."""
    alvo = perfil_dir(cfg)
    if alvo.exists():
        shutil.rmtree(alvo, ignore_errors=True)
    qr_path(cfg).unlink(missing_ok=True)
    (Path(cfg.data_dir) / "whatsapp-numeros.txt").unlink(missing_ok=True)
    cfg.update({"whatsapp_on": False})
    return ("🗑 WhatsApp removido: perfil do navegador, QR e allowlist "
            "apagados — o número segue normal no seu celular")


def cmd(args, cfg) -> None:
    """`betterme whatsapp status|start|stop|qr|autorizar|remover|setup`."""
    acao = str(getattr(args, "acao", "status") or "status").lower()
    if acao == "status":
        print("\n📱 WhatsApp (via Playwright — grátis, local, removível):")
        print(f"   playwright: {'instalado' if playwright_ok() else 'AUSENTE'}")
        ligado = str(getattr(cfg, "whatsapp_on", False)).lower() in \
            ("true", "1", "yes")
        print(f"   gateway: {'LIGADO' if ligado else 'desligado'} · "
              f"perfil: {perfil_dir(cfg)}"
              f"{' (existe)' if perfil_dir(cfg).exists() else ''}")
        print(f"   números autorizados: "
              f"{', '.join(sorted(numeros_autorizados(cfg))) or '(nenhum)'}")
        if not playwright_ok():
            print("\n" + INSTRUCAO_SETUP)
        return
    if acao == "setup":
        import subprocess
        import sys
        print("⏳ instalando playwright + chromium (só uma vez)…")
        r = subprocess.run([sys.executable, "-m", "pip", "install",
                            "playwright>=1.40"], check=False)
        r2 = subprocess.run([sys.executable, "-m", "playwright",
                             "install", "chromium"], check=False)
        ok = r.returncode == 0 and r2.returncode == 0
        print(("✔ setup completo — betterme whatsapp start"
               if ok else "✖ falha no setup — veja as mensagens acima"))
        return
    if acao == "start":
        if not playwright_ok():
            print("✖ playwright ausente\n" + INSTRUCAO_SETUP)
            raise SystemExit(1)
        cfg.update({"whatsapp_on": True})
        print("✔ WhatsApp ligado — reinicie o server; no 1º uso o QR "
              f"será salvo em {qr_path(cfg)}")
        return
    if acao == "stop":
        cfg.update({"whatsapp_on": False})
        print("✔ WhatsApp desligado (perfil preservado — start religa)")
        return
    if acao == "qr":
        p = qr_path(cfg)
        print(f"{p} {'(existe — escaneie)' if p.exists() else '(ainda não gerado — rode o server com o canal ligado)'}")
        return
    if acao == "autorizar":
        fone = str(getattr(args, "id", "") or "").strip()
        if not fone:
            print("uso: betterme whatsapp autorizar <seu número com DDI, ex.: 55929...>")
            raise SystemExit(1)
        autorizar_numero(cfg, fone)
        print("✔ número autorizado")
        return
    if acao == "remover":
        print("✔ " + remover(cfg))
        return
    print(f"✖ ação inválida: {acao!r}")
    raise SystemExit(1)
