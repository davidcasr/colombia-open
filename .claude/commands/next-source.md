---
description: Lee docs/roadmap/roadmap.md, propone la siguiente fuente candidata y arranca la skill new-source sobre ella.
---

Lee `docs/roadmap/roadmap.md` completo. De la tabla de fuentes, identifica la fila con
menor dificultad (🟢 > 🟡 > 🟠 > 🔴) entre las que NO están implementadas
todavía (columna "Estado" = ⬜).

Antes de proponerla:
1. Verifica el endpoint/URL actual de esa fuente con una petición real
   (curl/fetch), no solo lo que dice la tabla — puede estar desactualizada.
2. Si el acceso real difiere de lo descrito (URL muerta, requiere login,
   formato distinto), dilo explícitamente y, si cambia la dificultad
   estimada, actualiza la fila en `docs/roadmap/roadmap.md` antes de seguir.
3. Presenta la fuente candidata a David con: nombre, URL verificada,
   formato de datos, licencia (si es visible), y por qué es la de menor
   dificultad disponible. Espera confirmación antes de empezar a
   implementar — no asumas que la primera candidata es la correcta sin
   que él lo confirme, puede haber una razón para priorizar otra.

Una vez confirmada, invoca la skill `new-source` sobre esa fuente (nombre +
URL verificada) y sigue su checklist completo.

Recuerda la regla de `CLAUDE.md`: una fuente por fin de semana. Esta
sesión implementa UNA fuente, de punta a punta, no varias a medias.
