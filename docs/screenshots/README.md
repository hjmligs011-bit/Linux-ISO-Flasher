# Capturas de tela

Este diretório guarda as imagens usadas no `README.md`. Nenhuma captura é
necessária para compilar, testar ou executar o projeto — elas são apenas
documentação visual.

## Nomes esperados

| Arquivo | Conteúdo sugerido |
| --- | --- |
| `01-inicio.png` | Janela principal com as três etapas e nenhuma imagem selecionada |
| `02-imagem-selecionada.png` | Etapa 1 com nome, formato, tamanho e caminho da imagem |
| `03-dispositivos.png` | Etapa 2 com um pendrive detectado e discos internos bloqueados |
| `04-confirmacao.png` | Diálogo de confirmação de apagamento |
| `05-progresso.png` | Etapa 3 durante gravação/verificação, com velocidade e ETA |
| `06-resultado.png` | Tela de sucesso com verificação aprovada e SHA-256 |
| `07-historico.png` | Histórico de gravações |
| `08-preferencias.png` | Preferências de tema e idioma |

Use PNG, proporção 16:9 ou a janela padrão de 900×780, e evite expor caminhos
pessoais ou números de série reais.

## Como capturar

Wayland (GNOME/KDE/Hyprland/Sway com `grim`):

```sh
grim docs/screenshots/01-inicio.png
```

X11 (ImageMagick):

```sh
import -window root docs/screenshots/01-inicio.png
```

GNOME:

```sh
gnome-screenshot -f docs/screenshots/01-inicio.png
```

Se o ambiente não tiver ferramenta de captura, o smoke test da interface também
pode ser usado para conferir o layout sem gerar arquivos:

```sh
PYTHONPATH=src python3 tests/smoke_ui.py
```

## Como aparecem no README

O `README.md` já contém uma tabela com esses caminhos. Basta salvar os arquivos
aqui com os nomes acima e trocar as linhas de texto por tags Markdown, por
exemplo:

```markdown
![Etapa 1 — imagem selecionada](docs/screenshots/02-imagem-selecionada.png)
```
