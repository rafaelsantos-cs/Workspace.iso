# Modelo de ameaças

## Ativos protegidos

- integridade do sistema base e das políticas;
- credenciais do provider e do operador;
- memória curada pelo MMA;
- arquivos pessoais do operador;
- disponibilidade da máquina;
- proveniência dos dados usados no aprendizado.

## Ameaças consideradas

| Ameaça | Mitigação da v0.1 | Risco residual |
| --- | --- | --- |
| comando gerado pela IA tenta elevar privilégio | usuário sem shell, capability set vazio, `NoNewPrivileges`, namespaces e executável sem `shell=True` | bugs de kernel/systemd |
| job tenta acessar a Internet | `PrivateNetwork=yes`, somente AF_UNIX | canal indireto por serviço autorizado |
| conteúdo externo malicioso | allowlist, HTTPS, redirect/IP validation, limite, hash, quarentena | parser vulnerável ao abrir conteúdo |
| job tenta ler o home humano | `ProtectHome=yes` e diretórios explícitos | metadados expostos por serviços externos |
| fork bomb/consumo excessivo | `TasksMax`, `MemoryMax`, `CPUQuota`, `RuntimeMaxSec` | pressão de I/O dentro da cota permitida |
| prompt tenta desativar segurança | políticas e unidades são root-owned; permissões proibidas no NanoLGA | operador root ainda pode alterar tudo |
| app do desktop tenta usar o instalador para virar root | desktop sem sudo; instalador isolado na identidade `operator` de tty3 | acesso físico ao tty3 continua privilegiado por projeto |
| arquivo UIMP malformado | limites, hash, paths normalizados, proibição de symlink e extração atômica | vulnerabilidade futura no consumidor do payload |
| browser foge da allowlist | políticas gerenciadas e filesystem isolado | política de browser não é firewall; browser fica supervisionado |
| memória aprende uma conclusão falsa | candidatos exigem confirmações e contradições; promoção não automática | evidência falsa ou confirmação humana incorreta |
| atualização compromete dependência | pacotes Arch assinados, build registrado e checksum da ISO | supply chain upstream e repositório comprometido |

## Fora do escopo

- certificação de segurança funcional, robótica ou controle físico S0/S1;
- defesa contra um operador com acesso root;
- confidencialidade contra firmware/hardware hostil;
- navegação autônoma arbitrária na Web;
- autoatualização irrestrita do sistema base;
- garantia de que um modelo não produzirá conteúdo incorreto.

## Regras invariantes

1. O worker não recebe privilégios de administrador.
2. O worker não recebe rede direta.
3. Credenciais nunca entram no workspace do job.
4. Downloads não viram memória nem execução automaticamente.
5. Ações S0/S1 não são implementadas por esta distro e continuam externas.
6. A política pode ser relaxada somente por um operador, com alteração
   versionada e nova validação.
