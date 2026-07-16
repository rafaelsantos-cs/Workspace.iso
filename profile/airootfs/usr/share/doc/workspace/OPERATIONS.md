# Operação

## Criar e executar um job

```bash
workspace-job create exemplo -- /usr/bin/python task.py
workspace-job show exemplo
workspace-job start exemplo
workspace-job logs exemplo
```

O diretório do job fica em `/var/lib/lga/jobs/exemplo` e a área gravável em
`/var/lib/lga/workspaces/exemplo`. O manifesto aceita `timeout_seconds` entre 1
e 1.800 e uma lista `environment` limitada a chaves não secretas.

## Buscar conteúdo aprovado

```bash
workspace-fetch https://docs.python.org/3/library/asyncio.html
```

A resposta informa hash, tamanho, MIME e caminho de quarentena. O broker aceita
somente HTTPS e hosts listados em `/etc/lga/policy.toml`, revalida todos os
redirects e rejeita IPs privados, loopback, link-local, multicast e reservados.

## Empacotar um artefato

```bash
uimp pack resultado.json \
  --source agp-code \
  --destination lga-core \
  --protocol vsp \
  --output resultado.uimp
uimp validate resultado.uimp
```

## Diagnóstico

```bash
workspace-status
systemctl status lga-egressd
journalctl -u 'lga-learning@*'
systemd-analyze security lga-egressd.service lga-learning@.service
```

## Recuperação

Parar um job não remove seus dados:

```bash
workspace-job stop exemplo
```

O operador deve revisar e mover manualmente artefatos válidos. Não existe
limpeza automática destrutiva na v0.1.
