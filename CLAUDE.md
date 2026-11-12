# Vade-mécum ARSP: contexto para o Claude Code

Site com as normas da ARSP (gás canalizado, Espírito Santo) ligadas dispositivo a dispositivo: cada remissão ("§ 7º do art. 43 da Resolução ARSP nº 46/2021") vira link para o dispositivo exato, com caixinha de prévia, "citado por" e linhagem entre atos. Os documentos são públicos. O site é estático e tem no máximo 2 usuários simultâneos.

O piloto foi construído numa conversa no app do Claude e validado com 15 documentos. Em 2026-11-10, as duas peças da CP 004/2026 (a minuta e a NT GGN 001/2026) saíram da base. Em 2026-11-12 entrou o Contrato de Concessão da ES Gás (2020). Desde então, a referência para detectar regressões é de 14 documentos: 481 artigos e cláusulas, 315 remissões (5 inferidas, 1 parcial) e 0 não resolvidas.

## Como rodar

```powershell
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP"
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP" --so remissoes   # extrair | estruturar | remissoes | quartz | piloto
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP" --desde remissoes  # da etapa 3 até o fim
```

Saídas (todas regeneradas a cada execução; **nunca edite à mão**, mude o pipeline e rode de novo):

- `site-piloto/index.html` + `site-piloto/pdf/`: site de página única com caixinha, janelas fixas, busca, mapa e aba "A conferir".
- `content/`: notas Markdown para Quartz v5 e Obsidian (uma nota por artigo, block refs `^par7`).
- `dados/`: `*.estrutura.json`, `remissoes.json`, `nao_resolvidas.csv`, `revisoes_aplicadas.json`.

Depois de qualquer mudança, confira `content/revisao.md` (parciais e inferidas) e `dados/nao_resolvidas.csv`, e compare as contagens com as anteriores: `python .claude\skills\nova-resolucao\apoio.py comparar` mostra, ato por ato, o que mudou em relação ao último commit e avisa se alguma remissão sumiu.

## Publicação e atos novos

- O site de página única é publicado em https://brayanblail.github.io/vade-mecum-arsp/ pelo workflow `.github/workflows/pages.yml`, a cada push na `main` que altere `site-piloto/`.
- Para incluir uma resolução ARSP ou uma decisão ARSP/DG nova, use `/nova-resolucao` (`.claude/skills/nova-resolucao/`). Atos da ASPE ainda não são suportados: o `remissoes.py` registra toda resolução como ARSP.
- O Contrato de Concessão (`contrato-concessao-2020`, grupo "Contratos") não passa pelo `/nova-resolucao`: veja "Contrato de concessão" abaixo.
- Para aplicar as decisões da aba "A conferir" (aceitar, tirar ou corrigir um link), use `/revisar` (`.claude/skills/revisar/`). O site guarda as decisões no navegador, e o botão "Copiar para o Claude Code" gera o texto que o comando recebe.
- A aba "A conferir" é só do mantenedor. No site publicado ela fica escondida e aparece apenas no navegador que abriu o endereço uma vez com `?revisor` (`?revisor=nao` desliga). Na cópia local (arquivo ou localhost) aparece sempre. Isso só esconde a aba: quem a abrir não muda nada no site, porque as decisões só valem depois do `/revisar`.

## Revisão humana das remissões

- As decisões ficam em `pipeline/revisoes.csv` (separador `;`, 7 colunas: `doc;dispositivo;citacao;decisao;novo_alvo;nota;data`). É entrada do pipeline, como o `documentos.csv`: edite pelo `/revisar` ou por `python pipeline\revisoes.py mesclar <arquivo>`.
- A remissão é achada pelo ato e dispositivo de origem e pelo texto exato da citação. Se o texto mudar, a decisão fica "sem correspondência": a etapa 3 avisa, e o `revisoes.py validar` e o `apoio.py comparar` acusam.
- `decisao`: `aceitar` (o link fica e sai dos pendentes), `sem_link` (o trecho vira texto simples) ou `corrigir` (o link vai para `novo_alvo`, no formato do endereço do site, como `res-arsp-046-2021--art43-par7`).
- O texto da norma nunca muda, só o link. Link corrigido é verde, e a caixinha diz para onde o detector ligava antes.

## Contrato de concessão

- Fonte: `Analise Termoeletrica/Contrato de Concessão ES Gás.pdf`. É o mesmo documento da pasta `Gás Canalizado (aba do site)/01 Concessão` (E-DOCS 2020-XMH9X4), mas com camada de OCR; o daquela pasta só tem a imagem. `tipo=contrato`, `numero` vazio.
- Extração (`extrair.py`, `AJUSTES["contrato-concessao-2020"]`): `camada_ocr` agrupa as linhas da página inteira, descarta a rubrica da margem direita e corrige erros típicos (`corrigir_camada`). `corrigir` tem as correções pontuais, cada uma conferida no PDF (marcadores de inciso que o OCR perdeu). Assinaturas e cartório são omitidos; fórmulas e as tabelas dos Anexos III e IV viram "[Fórmula/Tabela: ver o PDF, p. N]".
- Estrutura (`estruturar.py`, `tipo == "contrato"`): Cláusula (`cl12`) > item (`cl12_it12-12-1`) > inciso (`cl1_it1-1_inc37`) > alínea; anexos com prefixo (`anx1_cl4_it4-1-1`). Item com número repetido no original ganha sufixo `b` no endereço (`anx1_cl6_it6-5b`).
- Remissões (`remissoes.py`): "cláusula", "item" e "anexo" só viram token no próprio contrato e nos trechos que citam o contrato de concessão. "Contrato de Concessão" liga ao contrato, exceto na LC 827 (`CONTRATO_GENERICO`: lá é qualquer contrato da ARSP). Item que não existe no corpo, mas existe num anexo ("cláusula 4.1.1 do contrato"), liga ao anexo como `inferido`. "Anexo II do contrato" sozinho liga ao ato (as partes não têm endereço).

## Etapas do pipeline

1. `extrair.py`: PyMuPDF. Filtra cabeçalho e rodapé, agrupa spans na mesma linha de base (colunas justificadas do DIO) e descarta texto tachado (redações revogadas da LC 827).
2. `estruturar.py`: artigos, parágrafos, incisos e alíneas, com validação da sequência numérica. Anexos com prefixo `anx1_`. Linhas de assinatura encerram o artigo.
3. `remissoes.py`: cadeias de citação (art, §, inciso, alínea, "deste artigo", "Resolução ARSP nº N/AAAA", leis, decretos, códigos). Intervalos e listas ("artigos 37 a 39", "§§ 2º e 3º") geram uma remissão com `alvos` (todos os dispositivos), `arts` e `spans` (posição de cada número no texto). Cada aresta guarda a `citacao` (texto exato). No fim, aplica as decisões do `revisoes.csv` (`revisoes.py`).
4. `gerar_quartz.py`: `content/`. Remissões múltiplas viram um link por número.
5. `gerar_piloto.py` + `piloto_template.html`: o site de página única, com os dados embutidos em JSON.

`indice.py` carrega estruturas e arestas. `comum.py` tem caminhos e a leitura do CSV.

## Regras que não podem quebrar

- `pipeline/documentos.csv`: separador `;`, **16 colunas**, nenhum `;` dentro dos textos. Colunas: `id;sigla;tipo;orgao;numero;ano;data;grupo;arquivo;titulo;situacao;observacao;link_oficial;ocr;alvo_padrao;relacoes`.
- IDs de dispositivo no padrão LexML: `art9`, `art9_cpt`, `art9_par4`, `art9_par1u`, `art9_cpt_inc3`, `art9_cpt_inc1_ali-a`, `anx1_art49_cpt_inc1_ali-o`.
- **Endereços já colados em documentos Word dependem desses formatos.** Não mude sem um redirecionamento:
  - site de página única: `#<doc-id>--<id do dispositivo com _ trocado por ->`, ex.: `#res-arsp-046-2021--art19-par2`;
  - Quartz: `/resolucoes/res-arsp-046-2021/art-19#par2`.
- Níveis de confiança das remissões:
  - `exato`;
  - `parcial`: o dispositivo citado não existe no destino;
  - `inferido`: "art. N" sem dizer o ato; usa `alvo_padrao` do CSV;
  - `documento`: link só para o ato;
  - `externo`: ato fora do cadastro, com LexML quando conhecido;
  - `corrigido` e `sem_link`: decisões da revisão humana (`revisoes.csv`).
- PDFs com camada de texto corrompida: OCR com Tesseract (`por`, `--psm 6`), arquivos em `ocr/p<numero>-NN.txt` e `ocr=sim` no CSV.

## Teste do site de página única

Abra `site-piloto/index.html` no navegador (ou com Playwright). No painel do navegador do app, o `.claude/launch.json` serve o site em http://localhost:8765 (`preview_start` com o nome `site-piloto`). Confira:

- Res. 046/2021, art. 43, § 7º: "artigos 37 a 39" tem sublinhado duplo. A caixinha mostra ‹ › e os botões Art. 37, Art. 38 e Art. 39.
- O clique abre uma janela que se arrasta pelo título, redimensiona pelo canto e encaixa em Topo/Base.
- Esc ou × fecha a janela; o limite é de 6 janelas, e elas continuam abertas ao trocar de ato.
- Aba "A conferir" (no localhost aparece sempre; no site publicado, só com `?revisor`): Aceitar, Tirar o link e Corrigir… guardam a decisão (sobrevive ao recarregar), e "Ver o texto" mostra as linhas para o `/revisar`.
- Sem rolagem horizontal a 390 px de largura e sem erros no console.

## Pendências conhecidas

- CUSD (Res. 053/2021), cláusula 5.3.1: cita "§7º, art. 42" da Res. 046, que não existe. Pelo assunto, o certo parece ser o art. 43, § 7º. Aparece como `parcial`; a decisão é do usuário, na aba "A conferir".
- Remissões a CLÁUSULAS do próprio CUSD ainda não viram link (as do contrato de concessão viram).
- Contrato de concessão: 5 remissões `inferido` para conferir na aba "A conferir" (Res. 106/2026 e Decisão 007/2026: "cláusula I, item XXXVI e XXXVII", com o nome do contrato só no fim da frase, e "cláusula 4.1.1 do contrato", que só existe no Anexo I).
- Contrato de concessão, erros de numeração do próprio original (o texto não muda): Cláusula I, 1.1, o 50º inciso está impresso "XL" (tratado como o 50º, com o número impresso); itens 6.5 (Anexo I) e 4.3.5 (Anexo II) repetidos; faltam 15.2, 22.7 e 26.2.
- Contrato de concessão: texto de OCR. Fórmulas e as tabelas dos Anexos III e IV não estão transcritas; vale o PDF.
- Res. 048/2021 vem de OCR: vale conferir com o PDF.
- Tabelas de tarifas dos anexos saem como texto corrido.

## Ambiente (Windows)

- Use aspas nos caminhos (acentos e espaços: `Resoluções ARSP`).
- `npx quartz create --strategy symlink` pode exigir o Modo de Desenvolvedor do Windows. Alternativa: `--strategy copy` e copiar `content/` a cada atualização.
- Os PDFs originais em `D:\Claude\Resoluções ARSP` são só lidos, nunca alterados.
