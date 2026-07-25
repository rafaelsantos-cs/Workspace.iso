# WorkSpace OS

WorkSpace é o perfil ArchISO da **LGA — Learning Generative Architecture**. A
distribuição fornece o desktop, as ferramentas e a zona restrita de
experimentação usadas pela arquitetura, sem transformar o sistema operacional
no próprio DeepBrain.

Esta é a versão **0.1.1**, alinhada à especificação LGA 0.3. Ela prioriza
isolamento, rastreabilidade e builds automatizados. Como o Arch é rolling
release, reproduzir uma ISO antiga exige preservar também o snapshot dos
repositórios e pacotes. A WorkSpace não é um sistema de segurança industrial e
não substitui um Safety Supervisor físico S0/S1.

## Limite canônico da LGA

A WorkSpace e a camada de apresentação ficam fora da LTCA. A rota mínima da v1
é:

`WorkSpace CLI → ingresso LTCA → DeepBrain v1`

Quando o DeepBrain precisa de sources ou memória, a rota interna é:

`DeepBrain v1 → MMA mínima → LUSC`

DeepBrain, MMA, LAM, CCA, AGPs e demais componentes operacionais pertencem à
LTCA. A LUSC é uma camada protegida dentro dela e a MMA é sua única passagem.
AGPs, CCA, multimodalidade, TTS, STT, visão, robótica e estados avançados não
são requisitos da primeira entrega.

Ezlia vem registrada como uma **LIP — LGA Intelligent Persona** opcional. Ela
altera apresentação e personalidade, não autoridade ou raciocínio; o modo
normal funciona sem qualquer LIP. A configuração instalada mantém `standard`
como padrão até um cliente compatível permitir uma escolha explícita.

## O que entra na imagem

- KDE Plasma, SDDM e identidade visual monocromática WorkSpace;
- Code - OSS, Blender e Figma como PWA gerenciada do Chromium;
- Python, JupyterLab, .NET 8, Node.js, Rust, Go, Java, C/C++ e ferramentas de
  build/debug;
- manifesto legível por máquina da arquitetura LGA 0.3 e configuração do futuro
  cliente LTCA;
- NanoLGA 0.1 como laboratório de compatibilidade da arquitetura madura, não
  como a rota de produção da v1;
- envelopes `.uimp` com manifesto, hashes SHA-256 e extração segura;
- jobs de aprendizado sem rede, sem privilégios e com limites de recursos;
- broker HTTPS por allowlist, quarentena e log JSONL para aquisições externas;
- Podman/Buildah para experimentos supervisionados;
- validação estática, testes automatizados, build ArchISO e smoke test QEMU.

## Fronteiras de confiança

| Zona | Identidade | Rede | Escrita | Finalidade |
| --- | --- | --- | --- | --- |
| WorkSpace humana | `workspace` | normal | home humano | UI, CLI, Code, Blender, revisão e aprovação |
| Cliente LTCA | futuro processo sem privilégio | somente ingresso configurado | estado próprio | autenticar e encaminhar UIMP; não hospeda o DeepBrain |
| Learning worker | `lga-runner` | negada | job/workspace e artefatos | executar experimentos delimitados |
| Egress broker | `lga-egress` | HTTPS por allowlist | quarentena/auditoria | buscar material externo auditável |
| NanoLGA lab | sessão humana ou teste | provider explícito | estado de laboratório | validar contratos maduros AGP/CCA/MMA |

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
`mkarchiso`; bootloaders e estrutura base acompanham o ArchISO atual.

Para validar sem construir a imagem:

```bash
./scripts/validate.sh
```

Para um build isolado em uma máquina com Docker:

```bash
./scripts/build-in-container.sh
```

## Uso inicial

- `workspace-status`: mostra release, limite LGA, serviços, política e filas;
- `workspace-job create <id> -- <comando>`: cria um job sem executá-lo;
- `workspace-job start <id>`: inicia o job pelo serviço restrito;
- `workspace-fetch URL`: solicita um download HTTPS ao broker;
- `uimp pack arquivo --output arquivo.uimp`: cataloga qualquer payload para o
  ingresso LTCA por padrão;
- `uimp validate arquivo.uimp`: valida estrutura, limites e hashes;
- `nanolga demo --json`: smoke test offline do laboratório NanoLGA.

O endpoint, a autenticação e a identidade de projeto do cliente LTCA permanecem
vazios em `/etc/lga/client.toml`; a distro não inventa um backend nem apresenta
chat fictício enquanto esse contrato não estiver implementado.

Na sessão live, o usuário gráfico é `workspace` e a senha temporária também é
`workspace`; essa conta não possui sudo. `Ctrl+Alt+F3` abre a identidade
separada e bloqueada `operator` por autologin local do TTY. Sua única regra de
sudo permite iniciar `archinstall`. Não existe senha compartilhada que permita
ao desktop assumir essa conta.

## Instalação em disco

A imagem inclui `archinstall` para instalação supervisionada. A v0.1 é
primeiramente uma imagem live/VM de desenvolvimento; o perfil de instalação
totalmente automatizado fica bloqueado até haver testes destrutivos em matriz
de firmware, particionamento e criptografia.

Consulte [THREAT_MODEL.md](docs/THREAT_MODEL.md),
[ARCHITECTURE.md](docs/ARCHITECTURE.md) e
[VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md). O snapshot legível por
máquina fica em [validation-results.json](docs/validation-results.json).
