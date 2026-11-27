# Contribuindo — Linux ISO Flasher

Obrigado por contribuir. Este projeto trata gravação de dispositivos de bloco;
mudanças pequenas podem destruir dados do usuário. Cuidado e testes são parte
do código, não opcionais.

## Padrões de código

- Python 3.11+, PEP 8, nomes descritivos e anotações de tipo nas APIs públicas.
- Use `from __future__ import annotations` nos módulos novos, seguindo `src/`.
- Nunca construa comandos de shell com dados vindos de dispositivo, arquivo ou
  interface. Se precisar de um processo externo, use lista de argumentos em
  `subprocess.Popen(..., shell=False)`.
- Nada de dados simulados no código de produção: device info vem de sysfs ou
  UDisks2; metadados de imagem vêm do arquivo selecionado.
- Erros esperados derivam de `FlasherError` (`core/errors.py`) e devem ter
  mensagens seguras para o usuário. Detalhes técnicos vão para o logger.
- A GUI consome modelos e eventos; lógica de decisão de gravação fica em
  `flashing/engine.py` e no helper. Não adicione escrita em bloco na interface.
- Comentários e documentação em pt_BR; seções curtas em inglês são bem-vindas
  quando ajudarem empacotadores.

## Testes obrigatórios

Toda mudança funcional vem com teste em `tests/`:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

- Use `unittest` e `tempfile.TemporaryDirectory()`; destinos são `FileTarget`.
- **Proibido:** teste que grave disco real, instancie `BlockDeviceTarget`, use
  `/dev/*` ou chame `pkexec` na suíte automática.
- Mudanças em `flashing/`, `devices/images/` ou `permissions/` precisam cobrir
  caminhos de erro, limites e cancelamento, não apenas o caminho feliz.
- Mudanças no protocolo JSON devem atualizar `docs/ARCHITECTURE.md` e os testes
  do `HelperLauncher` (com um helper de teste apontado por `LIF_HELPER`,
  `use_pkexec=False`).

## Segurança

- Revisar com atenção qualquer alteração em `assert_safe_target()`,
  `verify_identity()`, detecção de montagens críticas e desmontagem via
  UDisks2.
- A política Polkit em `packaging/polkit/` deve continuar exigindo
  `auth_admin`/`auth_admin_keep`. **Nunca** use `allow_yes` para ações de
  gravação.
- Novo campo no pedido JSON precisa ser validado no helper (tipo, faixa e
  formato) antes de ser usado.
- Se uma mudança exigir novo acesso a arquivo ou D-Bus, documente em
  `docs/ARCHITECTURE.md` e `docs/INSTALL.md`.

## Como adicionar uma tradução

As strings no código estão em pt_BR; gettext é configurado em `core/i18n.py`
(domínio `linux-iso-flasher`, idiomas atualmente `pt_BR` e `en`).

1. Extraia as mensagens com `xgettext` (use o domínio acima) para
   `src/linux_iso_flasher/locale/<idioma>/LC_MESSAGES/linux-iso-flasher.po`.
2. Traduza o `.po` e compile com
   `msgfmt -o linux-iso-flasher.mo linux-iso-flasher.po`.
3. Instale o `.mo` em
   `/usr/share/locale/<idioma>/LC_MESSAGES/linux-iso-flasher.mo` (ou inclua-o
   nos data-files do pacote — essa etapa ainda não está no `pyproject.toml`).
4. Se o novo idioma for selecionável na interface, atualize a lista
   `_SUPPORTED` em `core/i18n.py` e as opções válidas em `core/config.py` com
   teste correspondente.

Novos idiomas além de pt_BR/en são bem-vindos como contribuição, mas ainda não
fazem parte da versão 0.1.0.

## Commits

- Um assunto curto no imperativo: `Adiciona verificação de fingerprint` /
  `Fix: corrige desmontagem via UDisks2`.
- Commits pequenos e focados; explique no corpo o motivo quando a mudança
  envolver segurança ou protocolo.
- Antes de abrir um PR: rode os testes, descreva o cenário testado (sem discos
  reais) e liste mudanças em documentação/pacotes.
