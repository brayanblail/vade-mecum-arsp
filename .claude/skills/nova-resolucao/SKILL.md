---
name: nova-resolucao
description: Inclui no vade-mécum uma resolução ARSP ou decisão ARSP/DG nova a partir do PDF na pasta "D:\Claude\Resoluções ARSP". Preenche a linha do documentos.csv, roda o pipeline, revisa as remissões e, com o OK do usuário, envia ao GitHub, que republica o site. Use quando o usuário digitar /nova-resolucao ou pedir para incluir ou cadastrar um ato novo.
argument-hint: "[arquivo.pdf | 065/2023 ...]  (vazio: lista os PDFs fora do cadastro)"
---

# /nova-resolucao

Pedido: $ARGUMENTS

Rotina: PDF na pasta → linha no CSV → pipeline → revisão → GitHub → site atualizado. As regras gerais do projeto estão no `CLAUDE.md`; aqui fica só o que é específico desta rotina.

**Antes de começar**
- A pasta dos PDFs é `D:\Claude\Resoluções ARSP` e só pode ser lida: nunca mova, renomeie nem altere arquivos nela.
- Script de apoio: `python .claude\skills\nova-resolucao\apoio.py <pendentes | sugerir | validar | comparar>`.
- O shell é o Windows PowerShell 5.1:
  - escreva a mensagem de commit num arquivo e use `git commit -F <arquivo>`, porque aspas duplas dentro de um here-string quebram os argumentos do git;
  - se `git` ou `gh` não forem encontrados, recarregue o PATH com `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.
- Confira o site só no computador. Teste no celular apenas se o usuário pedir.
- Rode `git status --short`. Se houver mudanças sem commit que não vieram deste comando, avise o usuário e pergunte se continua, porque elas entrariam no mesmo commit.

## 1. Escolher os PDFs

- **Sem argumento:** rode `apoio.py pendentes`, mostre a lista e pergunte quais incluir. Use AskUserQuestion com multiSelect quando houver até 4 opções; acima disso, liste em texto e pergunte.
- **Com argumento:** aceite o nome do arquivo, parte dele, "065/2023" ou "65". Procure o PDF na pasta principal e pergunte ao usuário se houver mais de um candidato.
- **Ato da ASPE:** não inclua. Explique que o pipeline só reconhece resoluções ARSP: `Indice.por_chave` e `doc_do_token` em `pipeline/remissoes.py` fixam o órgão. Incluir a ASPE exige mudar o pipeline antes.
- **PDF fora da pasta principal** (como `Leis e Decretos/…` ou `Consulta Pública/…`): o `sugerir` não cobre esse caso. Preencha a linha à mão. O `arquivo` é o caminho relativo à pasta dos PDFs, com `/`.

## 2. Preencher a linha do CSV

1. Rode `apoio.py sugerir "<arquivo>"` para cada PDF. A linha sugerida vem do nome do arquivo e do catálogo `_Catalogo_Resolucoes_Gas_ARSP.xlsx`.
2. Leia a primeira página do PDF (Read com `pages: "1"`). Confirme o número, a data e a ementa. O `titulo` deve ser a ementa do PDF.
   - Sem dados do catálogo, preencha a partir do PDF: `titulo` com a ementa, `situacao` "Vigente" e `observacao` com uma frase no estilo das linhas existentes.
3. **Revogações e alterações:** se o ato novo revoga ou altera outro que está no CSV, atualize também a `situacao` e a `observacao` desse outro, por exemplo "Revogada pela Res. ARSP 114/2026." Se revoga um ato fora do cadastro, mencione isso na observação do ato novo, como em "Revogou a ASPE 004/2011."
4. **`relacoes`:** use só para ligações que o texto não cita, no formato `verbo:id` (como `originou:res-arsp-114-2026`). Quase sempre fica vazia.
5. Insira a linha com Edit em `pipeline/documentos.csv`, no bloco das resoluções, em ordem de data. Decisões vêm depois das resoluções, e as consultas ficam no fim.
   - Nenhum `;` dentro dos textos.
   - O arquivo é UTF-8 sem BOM, com fim de linha LF.
6. Rode `apoio.py validar`. Ele tem de terminar com 0 erros.
7. **OCR:** se o `sugerir` acusou "SEM TEXTO" ou "SUSPEITO", a camada de texto do PDF não serve.
   - O OCR precisa de `pdftoppm` (Poppler) e de `tesseract` com o idioma `por`. Hoje nenhum dos dois está instalado nesta máquina: proponha a instalação ao usuário.
   - Gere `ocr\p<NNN>-NN.txt` como explica o README, na seção "Quando o PDF tem texto corrompido", e use `ocr=sim`.
   - Não siga adiante sem o OCR.

Formato das colunas principais, para preencher à mão:

| coluna | resolução | decisão |
|---|---|---|
| `id` | `res-arsp-065-2023` | `dec-arsp-dg-007-2026` |
| `sigla` | `Res. ARSP 065/2023` | `Decisão ARSP/DG 007/2026` |
| `tipo` / `orgao` | `resolucao` / `ARSP` | `decisao` / `ARSP/DG` |
| `numero` / `ano` / `data` | `65` / `2023` / `2023-06-29` | `7` / `2026` / `2026-10-20` |
| `grupo` | `Resoluções` | `Resoluções` |

## 3. Rodar o pipeline

```powershell
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP"
```

Rode o pipeline completo: as remissões de todos os atos são recalculadas. Na saída, confira para cada ato novo:
- **Etapa 1:** um número de linhas compatível com o tamanho do PDF.
- **Etapa 2:** `artigos` maior que 0 e `avisos=0`.
  - Um aviso de "salto de numeração" indica artigo mal reconhecido. Abra `dados/<id>.estrutura.json` e compare com o PDF.
  - Se o erro é do pipeline, corrija o pipeline. Nunca edite as saídas à mão.
  - Se o erro é da própria norma, registre a pendência.
- **Etapa 3:** `não resolvidas: 0`.

## 4. Revisar

Rode `apoio.py comparar`, que compara a pasta com o último commit. Analise:
- **Atos novos:** a linha marcada com `+`.
- **Atos que já existiam:** só a coluna "citado por" deve mudar, nos atos citados pelo novo. Se mudarem artigos ou remissões de um ato antigo, é suspeito. Investigue.
- **"ATENÇÃO … sumiram":** possível regressão. Investigue antes de seguir.
- **Decisões da revisão sem correspondência:** uma remissão já revisada (`pipeline/revisoes.csv`) mudou de texto. Avise o usuário: a decisão tem de ser refeita na aba "A conferir" e aplicada com `/revisar`.
- **Novas `parcial`:** confira no PDF.
  - Se o erro é da norma, registre em "Pendências conhecidas" no `CLAUDE.md`.
  - Se o erro é do pipeline, corrija.
- **Novas `inferido`:** confira se o ato padrão faz sentido.
- **Citações de atos antigos para o novo:** antes apareciam como "ato fora do cadastro" (pontilhado) e agora viram link. Confira duas ou três no texto.

Confira também `dados/nao_resolvidas.csv` e o que mudou em `content/revisao.md` (`git diff -- content/revisao.md`).

## 5. Confirmar com o usuário e enviar

1. Mostre um resumo curto com:
   - os atos incluídos e o número de artigos de cada um;
   - as remissões antes → depois;
   - as novas parciais e inferidas;
   - os problemas encontrados.
2. Avise que ele pode abrir `site-piloto\index.html` no navegador para ver o resultado antes do envio.
3. Pergunte se pode enviar ao GitHub, com as opções "Enviar" e "Ainda não". Só continue se a resposta for sim.
4. Rode `git add -A` e depois `git status --short`. Confira que só entraram `pipeline/documentos.csv`, `content/`, `dados/`, `site-piloto/` e, se tiverem mudado, `CLAUDE.md` ou o pipeline.
5. Escreva a mensagem do commit num arquivo do scratchpad e use `git commit -F`.
   - Título: "Inclui a Res. ARSP NNN/AAAA (assunto curto)".
   - Corpo: as contagens totais antes → depois e as pendências.
6. Rode `git push origin main`.

## 6. Conferir a publicação

1. Rode `gh run list -R brayanblail/vade-mecum-arsp --workflow pages.yml --limit 1 --json databaseId,headSha` e confira que o `headSha` é o do commit.
2. Rode `gh run watch <id> -R brayanblail/vade-mecum-arsp --exit-status`.
3. No navegador do app, abra uma aba nova em `https://brayanblail.github.io/vade-mecum-arsp/?v=<hash curto>#<id>`. O `?v=` evita o cache de 10 minutos do Pages. Confira:
   - o título do ato;
   - que o número de `section.art` é igual ao número de artigos do pipeline;
   - a linhagem;
   - que o console não tem erros;
   - que a caixinha aparece ao passar o mouse sobre uma remissão do ato novo.
4. Relate ao usuário:
   - o endereço do ato no site;
   - o hash do commit;
   - as contagens antes → depois;
   - o que ficou pendente.
