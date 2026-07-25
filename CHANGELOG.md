# Changelog

## 0.1.1 - 2026-07-25

- alinhamento com a especificação LGA 0.3: **Learning Generative Architecture**;
- WorkSpace definida como cliente externo do ingresso da LTCA, sem expor o
  DeepBrain como endpoint público;
- rota v1 registrada como WorkSpace CLI → LTCA ingress → DeepBrain v1, com
  memória via MMA mínima → LUSC;
- Ezlia registrada como LIP opcional pré-instalada, sem autoridade cognitiva;
- NanoLGA mantida como laboratório de compatibilidade da arquitetura madura,
  fora da rota canônica da v1;
- correção do serviço `workspace-operator-setup`, removendo a troca concorrente
  de senha durante o boot;
- smoke test QEMU ligado à ISO exata de cada build e validado internamente em
  BIOS/UEFI por SDDM, Plasma, SSH e TTY3.

## 0.1.0 - 2026-07-16

- perfil ArchISO baseado dinamicamente no `releng` oficial;
- desktop KDE/Plasma WorkSpace e PWA do Figma;
- runtime NanoLGA e bridge JSONL;
- worker de aprendizado offline com hardening do systemd;
- broker de egress HTTPS com allowlist, limite e quarentena;
- formato de envelope UIMP 0.1 com hashes e extração segura;
- validação automatizada, QA estruturada e build CI da ISO.
