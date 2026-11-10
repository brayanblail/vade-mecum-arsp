---
name: revisar
description: Aplica as decisões de revisão das remissões copiadas da aba "A conferir" do site do vade-mécum (aceitar o link, tirar o link ou corrigir para outro dispositivo). Grava em pipeline/revisoes.csv, roda o pipeline, revisa e, com o OK do usuário, envia ao GitHub, que republica o site. Use quando o usuário colar um texto que começa com /revisar, ou pedir para aceitar, tirar ou corrigir o link de uma remissão.
argument-hint: "[texto copiado da aba A conferir]"
---

# /revisar

Decisões coladas:

$ARGUMENTS

Rotina: aba "A conferir" do site → "Copiar para o Claude Code" → `pipeline/revisoes.csv` → pipeline → revisão → GitHub → site atualizado. As regras gerais estão no `CLAUDE.md`; aqui fica só o que é específico desta rotina.

**Antes de começar**
- O texto colado tem o cabeçalho `doc;dispositivo;citacao;decisao;novo_alvo;nota;data` e uma linha por decisão. Valores de `decisao`:
  - `aceitar`: o link fica como está e sai dos pendentes;
  - `sem_link`: o trecho vira texto simples e sai do "citado por";
  - `corrigir`: o link vai para `novo_alvo`, no formato do endereço do site (`res-arsp-046-2021--art43-par7`, ou só o id do ato);
  - `desfazer`: tira a decisão do CSV, e a remissão volta a pendente.
- **Sem texto colado:** se o usuário pedir em palavras ("tira o link do art. 25 da NT"), monte as linhas você mesmo. Ache a remissão em `dados/remissoes.json` (campos `de_doc`, `de` e `citacao`) ou, se já tiver decisão, em `dados/revisoes_aplicadas.json`. Mostre as linhas ao usuário e confirme antes de gravar.
- O shell é o Windows PowerShell 5.1:
  - grave o texto colado com a ferramenta Write (UTF-8); `Set-Content` e `Get-Content` sem `-Encoding utf8` estragam os acentos;
  - escreva a mensagem de commit num arquivo e use `git commit -F <arquivo>`;
  - se `git` ou `gh` não forem encontrados, recarregue o PATH com `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.
- Rode `git status --short`. Se houver mudanças sem commit que não vieram deste comando, avise o usuário e pergunte se continua, porque elas entrariam no mesmo commit.
- A revisão muda só o link. Nunca edite o texto da norma nem as saídas à mão.

## 1. Gravar as decisões

1. Grave o texto colado num arquivo do scratchpad, como `revisar.txt`.
2. Rode `python pipeline\revisoes.py mesclar "<arquivo>"`.
   - A saída lista o que foi incluído, trocado e desfeito.
   - Se houver erro, nada é gravado. Explique o erro ao usuário. Os casos comuns são a remissão que não existe mais (o texto do ato mudou) e o destino que não existe.
3. Confira cada `corrigir` antes de seguir. Leia a citação na origem e o novo destino (em `dados/<id>.estrutura.json` ou no PDF) e diga ao usuário se o destino faz sentido pelo assunto. Se parecer errado, pergunte antes de rodar o pipeline.

## 2. Rodar o pipeline

```powershell
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP" --desde remissoes
python pipeline\revisoes.py validar
```

- Basta rodar da etapa 3 em diante, porque a revisão não muda a extração nem a estrutura.
- Na etapa 3, a linha `revisões aplicadas: N (...) | sem correspondência: 0` tem de mostrar 0 sem correspondência. Resolva qualquer "ATENÇÃO: decisão não aplicada".
- O `validar` tem de terminar com 0 erros.

## 3. Revisar

Rode `python .claude\skills\nova-resolucao\apoio.py comparar`. Confira:
- **"Decisões da revisão novas ou mudadas":** lista exatamente as linhas coladas (e "retiradas", as desfeitas).
- **Contagens:** só mudam nos atos envolvidos.
  - `aceitar` não muda contagens.
  - `sem_link` tira a remissão: o ato de origem perde uma, e o destino perde um "citado por".
  - `corrigir` muda o nível para `corrigido`, e o "citado por" passa do destino antigo para o novo.
- **"ATENÇÃO … sumiram" ou decisões sem correspondência:** não podem aparecer. Investigue antes de seguir.
- **Pendências conhecidas:** se a decisão resolve uma das pendências do `CLAUDE.md` (como a cláusula 5.3.1 do CUSD), atualize o `CLAUDE.md`.

## 4. Confirmar com o usuário e enviar

1. Mostre um resumo curto: cada decisão (origem, citação e o que muda) e as remissões antes → depois.
2. Avise que ele pode abrir `site-piloto\index.html` no navegador para ver o resultado antes do envio.
3. Pergunte se pode enviar ao GitHub, com as opções "Enviar" e "Ainda não". Só continue se a resposta for sim.
4. Rode `git add -A` e depois `git status --short`. Confira que só entraram `pipeline/revisoes.csv`, `dados/`, `content/`, `site-piloto/` e, se tiver mudado, o `CLAUDE.md`.
5. Escreva a mensagem do commit num arquivo do scratchpad e use `git commit -F`.
   - Título: "Revisa remissões: <resumo curto>", como "Revisa remissões: corrige a cláusula 5.3.1 do CUSD".
   - Corpo: as decisões e as contagens antes → depois.
6. Rode `git push origin main`.

## 5. Conferir a publicação

1. Rode `gh run list -R brayanblail/vade-mecum-arsp --workflow pages.yml --limit 1 --json databaseId,headSha` e confira que o `headSha` é o do commit.
2. Rode `gh run watch <id> -R brayanblail/vade-mecum-arsp --exit-status`.
3. No navegador do app, abra `https://brayanblail.github.io/vade-mecum-arsp/?v=<hash curto>&revisor#revisao`. Sem o `?revisor`, a aba fica escondida, como para os visitantes. Confira:
   - as decisões aparecem em "Conferidas";
   - num link corrigido, a caixinha mostra o aviso verde "Link corrigido na revisão";
   - o console não tem erros.
4. Relate ao usuário o hash do commit, as decisões aplicadas e as contagens antes → depois. Avise que as decisões guardadas no navegador dele saem sozinhas da barra quando ele abrir o site atualizado.
