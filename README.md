# WorkSpace OS

WorkSpace é o perfil ArchISO da LGA (Learning Generative Agent). A distribuição
combina um desktop KDE/Plasma para o operador com uma zona separada e
restritiva para execução e aprendizado da IA.

Esta é a versão **0.1.0**. Ela prioriza isolamento, rastreabilidade e builds
automatizados. Como o Arch é rolling release, reproduzir uma ISO antiga exige
preservar também o snapshot dos repositórios e dos pacotes. A WorkSpace não é
um sistema de segurança industrial e não substitui o
Safety Supervisor físico S0/S1 descrito na arquitetura da LGA.

## O que entra na imagem

- KDE Plasma, SDDM e identidade visual monocromática WorkSpace;
- Code - OSS, Blender e Figma como PWA gerenciada do Chromium;
- Python, JupyterLab, .NET 8, Node.js, Rust, Go, Java, C/C++ e ferramentas de
  build/debug;
- NanoLGA 0.1 com bridge JSONL para o desktop;
- envelopes `.uimp` com manifesto, hashes SHA-256 e extração segura;
- jobs de aprendizado sem rede, sem privilégios e com limites de recursos;
- broker HTTPS por allowlist, quarentena e log JSONL para aquisições externas;
- Podman/Buildah para experimentos supervisionados do operador;
- validação estática, testes automatizados e workflow de build da ISO.

## Fronteiras de confiança

| Zona | Usuário | Rede | Escrita | Finalidade |
| --- | --- | --- | --- | --- |
| Operador | `workspace` | normal | home do operador | UI, Code, Blender, revisão e aprovação |
| LGA Core | integração externa | apenas provider configurado | MMA e spool próprios | orquestração e curadoria |
| Learning worker | `lga-runner` | negada | job/workspace e artefatos | executar experimentos delimitados |
| Egress broker | `lga-egress` | HTTPS por allowlist | quarentena | buscar material externo auditável |

O Chromium gerenciado é uma interface supervisionada. Políticas de navegador
são guardrails, não uma fronteira de segurança absoluta; jobs autônomos não
recebem o navegador e permanecem no worker offline.

## Construir

Em uma instalação Arch Linux atualizada:

```bash
sudo pacman -Syu --needed archiso git
git clone <repo>
cd WorkSpace
sudo ./scripts/build-iso.sh
```

A ISO será gravada em `out/`. O script copia o perfil `releng` fornecido pela
versão instalada do ArchISO, aplica o overlay WorkSpace e só então chama
`mkarchiso`; assim, bootloaders e estrutura base acompanham o ArchISO atual.

Para validar sem construir a imagem:

```bash
./scripts/validate.sh
```

Para um build isolado em uma máquina com Docker:

```bash
./scripts/build-in-container.sh
```

## Uso inicial

- `nanolga demo --json`: smoke test determinístico e offline;
- `workspace-job create <id> -- <comando>`: cria um job, sem executá-lo;
- `workspace-job start <id>`: inicia o job pelo serviço restrito;
- `workspace-fetch URL`: solicita um download HTTPS ao broker;
- `uimp pack arquivo --output arquivo.uimp`: cataloga qualquer payload;
- `uimp validate arquivo.uimp`: valida estrutura, limites e hashes;
- `workspace-status`: mostra serviços, política e filas locais.

Na sessão live, o usuário gráfico é `workspace` e a senha temporária também é
`workspace`; essa conta não possui sudo. `Ctrl+Alt+F3` abre a identidade
separada `operator`, autorizada somente a iniciar `archinstall`. As credenciais
da imagem live não são copiadas para o sistema instalado.

Não coloque tokens em manifests de jobs, arquivos UIMP ou repositórios. As
credenciais do provider devem ser entregues ao processo do Core por mecanismo
de credenciais do systemd ou por um cofre externo.

## Instalação em disco

A imagem inclui `archinstall` para instalação supervisionada. A v0.1 é
considerada primeiramente uma imagem live/VM de desenvolvimento; o perfil de
instalação totalmente automatizado fica bloqueado até haver testes destrutivos
em matriz de firmware, particionamento e criptografia. Essa decisão evita que
um instalador experimental seja tratado como seguro para discos reais.

Consulte [THREAT_MODEL.md](docs/THREAT_MODEL.md),
[ARCHITECTURE.md](docs/ARCHITECTURE.md) e
[VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md). O snapshot legível por
máquina fica em [validation-results.json](docs/validation-results.json).
