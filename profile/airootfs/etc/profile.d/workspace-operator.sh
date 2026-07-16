if [[ "${USER:-}" == "operator" && -t 1 ]]; then
    printf '\nWorkSpace operator console\n'
    printf 'Run: sudo archinstall\n'
    printf 'Return to the desktop with Ctrl+Alt+F1 or Ctrl+Alt+F2.\n\n'
fi
