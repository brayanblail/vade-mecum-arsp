# Vade-mécum ARSP: contexto para o Claude Code

Site com as normas da ARSP (gás canalizado, Espírito Santo) ligadas dispositivo a dispositivo: cada remissão ("§ 7º do art. 43 da Resolução ARSP nº 46/2021") vira link para o dispositivo exato, com caixinha de prévia, "citado por" e linhagem entre atos. Os documentos são públicos. O site é estático e tem no máximo 2 usuários simultâneos.

O piloto foi construído numa conversa no app do Claude e validado com 15 documentos: 558 artigos, 347 remissões e 0 não resolvidas. Esses números servem de referência para detectar regressões.

## Como rodar

```powershell
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP"
python pipeline\construir.py --pdfs "D:\Claude\Resoluções ARSP" --so remissoes   # extrair | estruturar | remissoes | quartz | piloto
```

Saídas (todas regeneradas a cada execução; **nunca edite à mão**, mude o pipeline e rode de novo):

- `site-piloto/index.html` + `site-piloto/pdf/`: site de página única com caixinha, janelas fixas, busca, mapa e aba "A conferir".
- `content/`: notas Markdown para Quartz v5 e Obsidian (uma nota por artigo, block refs `^par7`).
- `dados/`: `*.estrutura.json`, `remissoes.json`, `nao_resolvidas.csv`.

Depois de qualquer mudança, confira `content/revisao.md` (parciais e inferidas) e `dados/nao_resolvidas.csv`, e compare as contagens com as anteriores: `python .claude\skills\nova-resolucao\apoio.py comparar` mostra, ato por ato, o que mudou em relação ao último commit e avisa se alguma remissão sumiu.

## Publicação e atos novos

- O site de página única é publicado em https://brayanblail.github.io/vade-mecum-arsp/ pelo workflow `.github/workflows/pages.yml`, a cada push na `main` que altere `site-piloto/`.
- Para incluir uma resolução ARSP ou uma decisão ARSP/DG nova, use `/nova-resolucao` (`.claude/skills/nova-resolucao/`). Atos da ASPE ainda não são suportados: o `remissoes.py` registra toda resolução como ARSP.

## Etapas do pipeline

1. `extrair.py`: PyMuPDF. Filtra cabeçalho e rodapé, agrupa spans na mesma linha de base (colunas justificadas do DIO) e descarta texto tachado (redações revogadas da LC 827).
2. `estruturar.py`: artigos, parágrafos, incisos e alíneas, com validação da sequência numérica. Anexos com prefixo `anx1_`. Linhas de assinatura encerram o artigo.
3. `remissoes.py`: cadeias de citação (art, §, inciso, alínea, "deste artigo", "Resolução ARSP nº N/AAAA", leis, decretos, códigos). Intervalos e listas ("artigos 37 a 39", "§§ 2º e 3º") geram uma remissão com `alvos` (todos os dispositivos), `arts` e `spans` (posição de cada número no texto).
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
  - `externo`: ato fora do cadastro, com LexML quando conhecido.
- PDFs com camada de texto corrompida: OCR com Tesseract (`por`, `--psm 6`), arquivos em `ocr/p<numero>-NN.txt` e `ocr=sim` no CSV.

## Teste do site de página única

Abra `site-piloto/index.html` no navegador (ou com Playwright) e confira:

- Res. 046/2021, art. 43, § 7º: "artigos 37 a 39" tem sublinhado duplo. A caixinha mostra ‹ › e os botões Art. 37, Art. 38 e Art. 39.
- O clique abre uma janela que se arrasta pelo título, redimensiona pelo canto e encaixa em Topo/Base.
- Esc ou × fecha a janela; o limite é de 6 janelas, e elas continuam abertas ao trocar de ato.
- Sem rolagem horizontal a 390 px de largura e sem erros no console.

## Pendências conhecidas

- CUSD (Res. 053/2021), cláusula 5.3.1: cita "§7º, art. 42" da Res. 046, que não existe. Pelo assunto, o certo parece ser o art. 43, § 7º. Aparece como `parcial`.
- Res. 061/2023, preâmbulo: "art. 43 da Resolução ARSP Nº 046/2021" liga só ao ato, não ao artigo.
- Remissões a CLÁUSULAS do CUSD e ao contrato de concessão ainda não viram link.
- Res. 048/2021 vem de OCR: vale conferir com o PDF.
- NT GGN 001/2026 (CP 004/2026): 48 remissões inferidas para a minuta.
- Tabelas de tarifas dos anexos saem como texto corrido.

## Ambiente (Windows)

- Use aspas nos caminhos (acentos e espaços: `Resoluções ARSP`).
- `npx quartz create --strategy symlink` pode exigir o Modo de Desenvolvedor do Windows. Alternativa: `--strategy copy` e copiar `content/` a cada atualização.
- Os PDFs originais em `D:\Claude\Resoluções ARSP` são só lidos, nunca alterados.
