# Entorno de desarrollo en Windows

## Usa `uv` con Python 3.11, no 3.12 ni 3.14

Este repo se desarrolló con `uv` porque:

- `pip`/`venv` estándar en Python 3.14 falla al compilar `pyarrow` (sin
  wheel precompilado todavía).
- La build de Python 3.12 manejada por `uv` tiene un bug conocido de
  OpenSSL en TLS (`OPENSSL_Uplink... no OPENSSL_Applink`), que crashea
  cualquier `requests.get` sobre HTTPS.

```bash
uv venv --python 3.11 .venv
```

Es la combinación verificada funcionando end-to-end (bootstrap, build en
vivo, tests) en Windows.

## Errores SSL específicos de tu máquina (antivirus, proxies corporativos)

Si ves `SSLCertVerificationError` solo en tu equipo y no en CI, es
probablemente tu antivirus/proxy interceptando TLS, no un problema del
proyecto ni de la fuente de datos — ver `CLAUDE.local.md` (no versionado,
crealo si no existe) para anotar el diagnóstico y el workaround
específico de tu máquina.
