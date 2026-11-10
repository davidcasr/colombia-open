# Design system — colombia-open

> Qué es este archivo: la fuente de verdad de la identidad visual del
> proyecto (paleta, tipografía, logomarca, voz). La landing page vive en
> otro repo —
> [colombia-open/colombia-open.github.io](https://github.com/colombia-open/colombia-open.github.io)
> (`app/globals.css`) — y la consume como cualquier material futuro
> (slides, redes, badges). Si cambias un token aquí, cámbialo también en
> `app/globals.css` de ese repo — no hay generación automática todavía, ver
> `.claude/rules/brand.md` allá.

## Logomarca — "constelación"

Un punto central dorado (el dataset ya curado) con puntos grises alrededor
(fuentes todavía sueltas) conectados por líneas finas. Se lee de afuera
hacia el centro: cada fuente oficial empieza dispersa, con su propio
formato, y converge en un único dataset validado.

- Copia canónica en `docs/brand/assets/mark-gold.svg` (punto central
  dorado, para fondos oscuros/índigo) y `docs/brand/assets/mark-indigo.svg`
  (punto central índigo, para fondos claros/hueso). La landing
  (`colombia-open.github.io`) lleva su propia copia en
  `public/brand/*.svg` — deben ser idénticas a estas.
- **Regla dura**: el punto central es la única señal de "dato ya
  consolidado" — nunca se usa ese color para otra cosa (alertas, enlaces
  genéricos, etc.), igual que el mint en historify o el oro en el resto de
  esta paleta.
- A favicon (32px) se reduce al punto central solo, sin los puntos
  dispersos — ver `docs/brand/assets/favicon.svg`.

## Paleta

| Token | Rol | Hex (claro) | Hex (oscuro) |
|---|---|---|---|
| `--bg` | Fondo primario | `#F4F1EA` (hueso) | `#17233D` (índigo) |
| `--bg-alt` | Superficie de tarjeta | `#FFFFFF` | `#1F2E4E` |
| `--fg` | Texto primario | `#1B2A4A` | `#F4F1EA` |
| `--fg-muted` | Texto secundario, puntos dispersos del logo | `#5B6578` | `#AEB6C4` |
| `--accent` | Acento de dato — "esto ya está consolidado" | `#C9A227` | `#D9B544` |
| `--alert` | Alerta — fuente caída, validación fallida | `#B5542E` | `#E0825A` |

`--accent` y `--alert` nunca se mezclan: oro es siempre "dato bueno /
reciente", terracota es siempre "algo falló". No hay un tercer color
semántico todavía.

**Regla dura**: nada de hex crudo fuera de `styles.css` (los `:root` /
`@media (prefers-color-scheme: dark)` / `[data-theme]`) y de este archivo.
Cualquier HTML nuevo consume `var(--token)`, nunca un literal.

## Tipografía

- **Display** (wordmark, títulos de sección): [Fraunces](https://fonts.google.com/specimen/Fraunces),
  italic, peso 560.
- **Cuerpo / UI**: [Inter](https://fonts.google.com/specimen/Inter), 400/500/600.
- **Código / datos** (hex, nombres de columna, snippets): [IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono).

Las tres se cargan desde Google Fonts en `app/layout.tsx` de la landing —
ver el `<link>` de `fonts.googleapis.com` ahí.

## Temas

El sitio respeta `prefers-color-scheme` por defecto, con un botón para
forzar el tema (guardado en `localStorage`, por viewer, no compartido). La
estructura de tokens en `app/globals.css` sigue siempre este patrón: valores
claros en `:root`, valores oscuros repetidos en
`@media (prefers-color-scheme: dark)` y en `[data-theme="dark"]` — nunca un
color definido solo dentro de un bloque condicional.

## Voz

Calmada, precisa, nombra la fuente y la fecha de vigencia del dato, nunca
promete "en vivo" cuando es un snapshot cacheado. Vocabulario ancla:
*fuente, vigencia, capa, procedencia, validado*. Evitar: "en tiempo real",
"garantizado", "oficial" sin matizar — colombia-open no es el DANE, es una
capa encima del DANE. Sin signos de exclamación cerca de datos o cifras.

## Dónde vive cada cosa

```
docs/brand/
├── design-system.md     # este archivo — fuente de verdad de los tokens
└── assets/
    ├── favicon.svg       # versión reducida del mark para el tab del navegador
    ├── og-image.png      # 1200×630, usado en <meta property="og:image"> de la landing
    └── mark-gold.svg / mark-indigo.svg   # logomarca, ver "Logomarca" arriba
```

La implementación real (HTML/CSS que consume estos tokens) vive en el repo
separado
[colombia-open/colombia-open.github.io](https://github.com/colombia-open/colombia-open.github.io):

```
app/globals.css        # implementación real de los tokens (debe igualar la tabla de arriba)
app/layout.tsx          # <meta> de OG/Twitter, carga de fuentes de Google Fonts
public/                 # copia de favicon.svg, og-image.png, brand/*.svg
```

`og-image.png` es la vista previa que muestran Twitter/X, Slack, WhatsApp,
LinkedIn, etc. al compartir la URL del sitio. Se regenera con el script
ad-hoc que generó la versión actual (fondo `--bg` oscuro, mark dorado
escalado, wordmark en Fraunces itálica, tagline en Inter) — no hay
pipeline automatizado todavía; si cambia el wordmark o la paleta,
regenerar a mano, mantener 1200×630 y copiar el archivo a ambos repos.

Este repo (`colombia-open`) ya no publica a GitHub Pages — es solo el
paquete Python (`src/`, `data/`, `tests/`...). El deploy de la landing
vive en `colombia-open/colombia-open.github.io`.
