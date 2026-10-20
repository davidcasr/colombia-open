# Design system — colombia-open

> Qué es este archivo: la fuente de verdad de la identidad visual del
> proyecto (paleta, tipografía, logomarca, voz). Lo usa tanto
> `site/index.html`/`site/styles.css` (la landing page, en su propia
> carpeta — nada de HTML/CSS de la web en la raíz del repo, que es del
> paquete Python) como cualquier material futuro (slides, redes, badges).
> Si cambias un token aquí, cámbialo también en `site/styles.css` — no hay
> generación automática todavía.

## Logomarca — "constelación"

Un punto central dorado (el dataset ya curado) con puntos grises alrededor
(fuentes todavía sueltas) conectados por líneas finas. Se lee de afuera
hacia el centro: cada fuente oficial empieza dispersa, con su propio
formato, y converge en un único dataset validado.

- Vive en `site/assets/brand/mark-gold.svg` (punto central dorado, para
  fondos oscuros/índigo) y `site/assets/brand/mark-indigo.svg` (punto
  central índigo, para fondos claros/hueso).
- **Regla dura**: el punto central es la única señal de "dato ya
  consolidado" — nunca se usa ese color para otra cosa (alertas, enlaces
  genéricos, etc.), igual que el mint en historify o el oro en el resto de
  esta paleta.
- A favicon (32px) se reduce al punto central solo, sin los puntos
  dispersos — ver `site/favicon.svg`.

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

Las tres se cargan desde Google Fonts en `index.html` — ver el `<link>` de
`fonts.googleapis.com` ahí.

## Temas

El sitio respeta `prefers-color-scheme` por defecto, con un botón para
forzar el tema (guardado en `localStorage`, por viewer, no compartido). La
estructura de tokens en `styles.css` sigue siempre este patrón: valores
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
site/
├── index.html                      # landing page (usa los tokens de este archivo)
├── styles.css                      # implementación real de los tokens
├── favicon.svg                     # versión reducida para el tab del navegador
└── assets/
    ├── og-image.png                 # 1200×630, usado en <meta property="og:image">
    └── brand/
        ├── mark-gold.svg             # logomarca, punto central dorado (fondo oscuro)
        └── mark-indigo.svg           # logomarca, punto central índigo (fondo claro)
```

`og-image.png` es la vista previa que muestran Twitter/X, Slack, WhatsApp,
LinkedIn, etc. al compartir la URL del sitio (`<meta property="og:image">`
y `twitter:image` en `index.html`). Se regenera con el script ad-hoc que
generó la versión actual (fondo `--bg` oscuro, mark dorado escalado,
wordmark en Fraunces itálica, tagline en Inter) — no hay pipeline
automatizado todavía; si cambia el wordmark o la paleta, regenerar a mano
y mantener 1200×630.

Todo lo que GitHub Pages publica vive dentro de `site/` — la raíz del repo
es del paquete Python (`src/`, `data/`, `tests/`...), no de la web. El
workflow `.github/workflows/pages-deploy.yml` solo sube `site/`.
