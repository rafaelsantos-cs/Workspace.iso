# Modelo de ameaças

## Ativos protegidos

- integridade do sistema base e das políticas;
- credenciais do provider e do operador;
- credenciais futuras do ingresso LTCA;
- sources e memória da LUSC, acessíveis somente via MMA;
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
| worker tenta escrever memória diretamente | a WorkSpace produz artefato/UIMP; a LUSC fica atrás da MMA dentro da LTCA | uma implementação futura do ingresso pode ter falhas de autorização |
| LIP tenta assumir autoridade cognitiva | persona declarada como apresentação sem autoridade; DeepBrain continua responsável pelo conteúdo | cliente futuro pode misturar indevidamente estilo e política |
| laboratório NanoLGA é confundido com a v1 | documentação, manifesto e status o marcam como laboratório opcional | integração externa pode ignorar a marcação |
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
6. A WorkSpace não acessa a LUSC diretamente e não expõe o DeepBrain como
   endpoint externo.
7. Uma LIP não concede permissões, memória ou autoridade de execução.
8. A política pode ser relaxada somente por um operador, com alteração
   versionada e nova validação.
