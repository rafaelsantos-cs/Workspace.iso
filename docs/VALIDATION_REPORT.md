# Relatório de validação

## Estado geral: fonte pronta; ISO ainda não construída

O código-fonte e os testes independentes da plataforma podem ser validados em
qualquer Linux com Python. A geração e o boot da ISO exigem um host Arch Linux
com `archiso`, root e, para smoke test, QEMU/UEFI. O resultado só muda para
“pronto para instalar” após esses testes produzirem evidência.

## Evidência inicial

| Verificação | Resultado | Evidência |
| --- | --- | --- |
| validação estática do perfil | aprovado | 6/6 regras estruturais e de segurança |
| testes da WorkSpace | aprovado | 15/15 incluindo UIMP, egress, jobs, merge do `releng` e proteção de paths de build |
| NanoLGA + bridge do desktop | aprovado | 11/11 incluindo round trip JSONL |
| compilação bytecode Python | aprovado | `compileall` sem erro |
| demo determinística | aprovado | resultado 120 e Safety `allow` |
| tipagem Python | aprovado | Pyright 1.1.411: 0 erros e 0 avisos |
| UIMP CLI | aprovado | pack + validate com payload arbitrário |
| hardening systemd | aprovado com contexto | egress 1,6 “OK”; worker 0,7 “SAFE” |
| ShellCheck | pendente no CI | ferramenta ausente no host local |
| binário Avalonia legado | bloqueado | bundle exige cache gravável; UI não testada na distro |
| build `mkarchiso` | pendente | host atual não contém ArchISO |
| boot BIOS/UEFI em QEMU | pendente | QEMU indisponível no host atual |

## Critérios de liberação

- todos os testes Python, shell e JSON aprovados;
- nenhum arquivo de segredo versionado;
- lista de pacotes resolvida integralmente pelos repositórios oficiais;
- `mkarchiso` concluído e `SHA256SUMS` gerado;
- boot BIOS e UEFI até SDDM;
- login da conta `workspace` e inicialização do broker;
- job de teste incapaz de ler `/home/workspace` e de alcançar rede direta;
- fetch permitido e fetch para host/IP privado negados;
- pack, validação e extração UIMP aprovados;
- `systemd-analyze security` revisado para os serviços LGA;
- teste em VM descartável antes de qualquer instalação física.

Os resultados estruturados estão em
[`validation-results.json`](validation-results.json).

## Limitações conhecidas

- Figma é uma PWA; não existe cliente Linux oficial empacotado no ArchISO.
- a allowlist de terceiros muda e precisa de manutenção versionada;
- renderização GPU para workers permanece desabilitada por padrão;
- a v0.1 não automatiza particionamento nem migração de uma instalação;
- o binário do desktop 0.9.0 não é incluído até passar por nova revisão/build.
