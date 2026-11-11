# Vade-mécum ARSP: normas ligadas dispositivo a dispositivo

Transforma os PDFs da ARSP (resoluções, leis, consultas públicas) num site em que:

- cada remissão ("§ 7º do art. 43 da Resolução ARSP nº 46/2021", "inciso II deste artigo") vira link para o dispositivo exato;
- remissões a vários dispositivos ("artigos 37 a 39", "§§ 2º e 3º do art. 60", "incisos I, II e III") ligam a **todos** eles, inclusive aos do meio de um intervalo;
- ao passar o mouse aparece uma caixinha com o artigo inteiro;
- no fim de cada artigo aparece quem o cita (o "citado por");
- cada ato tem a sua linhagem: quais atos cita e por quais é citado.

O mesmo conteúdo serve para o **Quartz** (site público) e para o **Obsidian** (cofre local). Nele, cada número citado vira um link próprio: em "artigos 37 a 39", "artigos 37" leva ao art. 37 e "39" ao art. 39; o art. 38 não tem link no texto, mas registra a citação no seu "citado por".

### Site de página única (`site-piloto/index.html`)

O `construir.py` também gera um site num arquivo só, com o mesmo conteúdo. Nele:

- **Passar o mouse** sobre uma remissão mostra a caixinha. Remissões a vários dispositivos (sublinhado duplo) têm os botões **‹ ›** e um botão para cada dispositivo ("Art. 37 · Art. 38 · Art. 39").
- **Clicar** (ou o botão **Fixar** da caixinha) abre uma **janela** que fica na tela enquanto você lê:
  - arraste pelo título para mover; puxe o canto inferior direito para mudar o tamanho;
  - **Topo** e **Base** encaixam a janela na parte de cima ou de baixo da tela, na largura toda;
  - **×** ou **Esc** fecha; dá para abrir até 6 ao mesmo tempo, e elas continuam abertas quando você troca de ato;
  - remissões dentro da janela também mostram a caixinha e abrem outras janelas.
- **Abrir no texto** (no rodapé da caixinha ou da janela) vai até o dispositivo na norma. Ctrl+clique abre o link numa nova aba do navegador.
- No celular, o primeiro toque mostra a caixinha e o segundo abre a janela, já encaixada embaixo.

## O que tem nesta pasta

| Pasta / arquivo | O que é |
|---|---|
| `pipeline/documentos.csv` | Cadastro dos documentos: um por linha, separado por `;` |
| `pipeline/construir.py` | Roda tudo: extrai, estrutura, liga remissões e gera as saídas |
| `pipeline/*.py` | As etapas (extrair, estruturar, remissoes, gerar_quartz, gerar_piloto) |
| `ocr/` | Texto da Res. 048/2021 obtido por OCR (o PDF original tem a camada de texto corrompida) |
| `content/` | **Saída pronta para o Quartz/Obsidian**: 13 atos, 439 notas de artigo, PDFs em `content/pdf/` |
| `dados/` | Arquivos intermediários. Os dois que interessam: `remissoes.json` (todas as ligações) e `nao_resolvidas.csv` |

## 1. Rodar o pipeline (Windows)

Pré-requisito: Python 3.11 ou mais novo.

```powershell
cd caminho\para\esta\pasta
pip install -r requirements.txt
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP"
```

Leva cerca de 1 minuto para os 13 documentos. Ao final, confira:

- `content\revisao.md`: remissões **parciais** (o dispositivo citado não existe no destino) e **inferidas** (o texto não diz de qual ato é o artigo);
- `dados\nao_resolvidas.csv`: citações que não viraram link.

### Incluir mais documentos

1. Acrescente uma linha no `pipeline\documentos.csv`. As colunas principais são:
   - `id`: nome curto e único, sem espaços (ex.: `res-arsp-080-2024`);
   - `sigla`: como aparece no site (ex.: `Res. ARSP 080/2024`);
   - `tipo`: `resolucao`, `decisao`, `lei`, `lei-complementar`, `minuta` ou `nota-tecnica`;
   - `numero` e `ano`: são eles que permitem reconhecer "Resolução ARSP nº 80/2024" nos outros textos;
   - `grupo`: `Leis`, `Resoluções` ou `Consultas públicas`;
   - `arquivo`: caminho do PDF dentro da pasta `Resoluções ARSP`.
2. **Não use `;` dentro dos textos** (é o separador).
3. Rode o `construir.py` de novo. Todas as ligações são recalculadas.

Colunas opcionais:

- `alvo_padrao`: o ato para onde vão os "art. N" que não dizem de qual ato são. Uma nota técnica de consulta pública, por exemplo, pode apontar para a minuta que ela fundamenta.
- `relacoes`: ligações declaradas à mão, como `originou:res-arsp-114-2026`.
- `ocr=sim`: o texto vem de `ocr\p<numero>-NN.txt`.

### Quando o PDF tem texto corrompido (letras duplicadas, palavras grudadas)

Gere o OCR uma vez com o Tesseract (com o idioma `por`) e marque `ocr=sim` no CSV:

```powershell
pdftoppm -r 300 -gray "arquivo.pdf" ocr\p048
for %f in (ocr\p048-*.pgm) do tesseract "%f" "%~dpnf" -l por --psm 6
```

O script corrige os erros típicos do OCR em normas, como "8 1º" no lugar de "§ 1º" e "|" no lugar de "I".

## 2. Publicar com o Quartz (v5)

Pré-requisitos: Node.js 22 ou mais novo e Git. O build abaixo foi testado com o conteúdo desta pasta: 575 notas viraram 603 páginas, sem link quebrado.

```powershell
git clone https://github.com/jackyzha0/quartz.git quartz-arsp
cd quartz-arsp
npm i
mkdir content
npx quartz create --template default --strategy symlink --source "..\caminho\para\esta\pasta\content" --links absolute --baseUrl SEU-USUARIO.github.io/quartz-arsp
npx quartz plugin install --from-config
npx quartz build --serve
```

Abra `http://localhost:8080`. Com `--strategy symlink`, cada vez que você roda o pipeline o site já enxerga o conteúdo novo.

No `quartz.config.yaml`, ajuste:

```yaml
configuration:
  pageTitle: Vade-mécum ARSP
  locale: pt-BR
  analytics: null        # ou remova o bloco "analytics"
```

**Hospedagem**: o site é estático. O GitHub Pages ou o Cloudflare Pages servem de graça e aguentam muito mais que duas pessoas ao mesmo tempo, sem custo por acesso. O passo a passo está em `docs/hosting.md`, dentro do Quartz.

## 3. Abrir no Obsidian

Abra a pasta `content` como cofre ("Open folder as vault"). Os links são do tipo `[[resolucoes/res-arsp-046-2021/art-43#^par7|...]]`:

- passar o mouse mostra a nota do artigo;
- o painel de backlinks mostra quem cita.

## Endereço de cada dispositivo (para linkar no Word)

```
https://SEU-SITE/resolucoes/res-arsp-046-2021/art-43          artigo
https://SEU-SITE/resolucoes/res-arsp-046-2021/art-43#par7     § 7º
https://SEU-SITE/resolucoes/res-arsp-114-2026/anexo-i-art-49#cpt-inc1-ali-o   art. 49, I, "o" do Anexo I
```

Os identificadores seguem o padrão LexML:

| Identificador | Dispositivo |
|---|---|
| `cpt` | caput |
| `par7` | § 7º |
| `par1u` | parágrafo único |
| `inc3` | inciso III |
| `ali-a` | alínea a |

Nas resoluções com Anexo, o texto normativo costuma estar no anexo (`anexo-i-art-N`).

## Limitações conhecidas

- **Remissões a cláusulas** ("conforme CLÁUSULA XXIII" no CUSD) e **ao contrato de concessão** ainda não viram link.
- **Atos fora do cadastro** (Res. ASPE 005/2007, LC 954/2020…) aparecem sublinhados com pontilhado, sem link. As leis federais conhecidas apontam para o LexML.
- **Texto consolidado**: na LC 827/2016 são mantidas só as redações vigentes; o que está tachado no PDF foi omitido. Nas resoluções, o site mostra o texto original com as remissões. Ele não monta a versão compilada.
- **Tabelas dos anexos** (tarifas) aparecem como texto em bloco. Para os números, vale o PDF (cada artigo tem link para a página).
- Em caso de dúvida, vale sempre o PDF original.

## Ideias de pedidos para o Claude Code

- "Inclua no `documentos.csv` todas as resoluções vigentes da pasta `D:\Claude\Resoluções ARSP` usando o `_Catalogo_Resolucoes_Gas_ARSP.xlsx` e rode o pipeline."
- "Faça as remissões a CLÁUSULA virarem link no CUSD."
- "Rode o pipeline e me mostre o que mudou em `content/revisao.md`."
