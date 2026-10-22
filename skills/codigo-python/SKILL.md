---
name: codigo-python
description: "Projetos Python profissionais: estrutura, ambiente virtual, dependências, testes pytest, type hints e empacotamento. Use quando a tarefa envolver python, pip, venv, pytest, pandas, flask, fastapi, django, api python, script python ou módulo python."
---
# Python — engenharia de projetos

## Fluxo obrigatório
1. `python3 -m venv .venv && .venv/bin/pip install -e .` (projeto) ou instalar dependências do `requirements.txt`.
2. Escrever código com **type hints** e docstrings curtas.
3. Testes reais: `pytest -q` (ou `python -m pytest`). Colar a saída.
4. Lint rápido: `python -m py_compile` no arquivo alterado.

## Estrutura de referência
```
projeto/
├── pyproject.toml      # metadados + deps (padrão moderno)
├── src/pacote/         # código (layout src evita import acidental)
│   ├── __init__.py
│   └── modulo.py
├── tests/test_modulo.py
└── README.md
```

## Decisões de sênior
- **FastAPI** p/ APIs (validação automática, async, docs /docs); **Flask** p/ casos mínimos; Django só com admin/ORM completos.
- `dataclass`/`pydantic` para modelos; `pathlib` para caminhos (nunca string concat).
- Erros: exceções específicas; nunca `except:` nu — capture o erro real e trate.
- Dependências pinadas (`pip freeze > requirements.txt`).

## Armadilhas comuns
- Mutável default em argumento (`def f(x=[])`) — usar `None`.
- Confundir `is` com `==` (identidade × igualdade).
- Esquecer `__init__.py` (imports quebram fora do PyCharm).
- Loop síncrono em tarefa de rede — usar `asyncio`/`httpx`.

## Verificação antes de entregar
`pytest -q` verde · `python -c "import pacote"` sem erro · exemplo executado com SAÍDA REAL colada.
