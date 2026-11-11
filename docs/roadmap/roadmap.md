# Roadmap — colombia-open

> **Qué es este archivo**: el mapa de fuentes de datos públicos de Colombia que
> `colombia-open` planea distribuir, con su nivel de dificultad de acceso y su
> estado de implementación. **No es una cola de trabajo con sprints** — es la
> lista priorizada desde la que `/next-source` elige la siguiente fuente a
> implementar.
>
> Filosofía: **una fuente por fin de semana**, de punta a punta (extractor +
> builder + validación + registro + tests + docs), nunca varias a medias. Ver
> `CLAUDE.md` para el detalle de por qué y `.claude/commands/next-source.md`
> para el flujo de arranque semanal.

## Estado actual

- **Fuentes implementadas**: 11 — `divipola` (geografía: departamentos +
  municipios, DANE), `municipios_geometria` (geometría de polígonos
  municipales, IGAC vía SNR/ArcGIS — segunda iteración de `divipola`),
  `demografia` (proyecciones de población municipal 2018-2042, DANE),
  `educacion_establecimientos` (directorio de establecimientos educativos
  2015-2025, MEN), `educacion_saber11` (resultados Saber 11 agregados por
  establecimiento y periodo, 2010-2022, ICFES),
  `delincuencia_hurto_personas` (víctimas de hurto a personas por
  municipio y día, 2003 a la fecha, MinDefensa/Policía),
  `delincuencia_lesiones_personales` (víctimas de lesiones personales y en
  accidente de tránsito por municipio, día, conducta, arma, género y grupo
  etario, 2010 a la fecha, Policía), `delincuencia_hurto_modalidades`
  (víctimas de hurto a residencias y entidades comerciales por municipio,
  día, arma, género y grupo etario, 2010 a la fecha, Policía),
  `infraestructura_poi` (puntos de interés urbanos — salud, educación,
  seguridad, finanzas, religión, gobierno, transporte, comercio —
  geocodificados por municipio, OpenStreetMap vía Geofabrik),
  `macroeconomia_trm` (Tasa de Cambio Representativa del Mercado diaria,
  1991 a la fecha, Superintendencia Financiera) y `calidad_aire` (los 6
  contaminantes del Índice de Calidad del Aire por estación, 2011 a la
  fecha, IDEAM).
- **Próximas candidatas sugeridas** (auditoría 2026-11-11, ordenadas por
  dificultad de acceso — la elección es del mantenedor):
  1. 🟢 **Otros delitos de la Policía/MinDefensa** (homicidio, delitos
     sexuales, violencia intrafamiliar, extorsión, secuestro…): mismo
     esquema exacto que `delincuencia_hurto_personas`, confirmados en
     vivo.
  2. 🟢 **Agro — EVA** (`2pnw-mmge` 2007-2018 + `uejq-wxrr` 2019-2025):
     acceso confirmado en vivo; unir las dos series es curación, no acceso.
  3. 🟢 **Energía — XM** (series nacionales): API pública confirmada en
     vivo; falta confirmar los términos de uso de los datos y no hay
     granularidad municipal.
  4. 🟡 **Macroeconomía — DTF/IBR/UVR**: **ya no** es "mismo patrón que
     TRM" — los IDs de datos.gov.co son enlaces, no tablas (#13); la vía
     es la API SDMX de BanRep en XML (#16).

  Siguen con diseño o investigación pendiente: vivienda (Camacol/DANE,
  sin verificar), pobreza municipal (solo años censales — decisión de
  alcance) y finanzas territoriales (sin API).

## Tabla de fuentes

| Dominio | Fuente oficial | Acceso | Dificultad | Estado |
|---|---|---|---|---|
| Geografía (códigos DIVIPOLA + centroides) | DANE, vía API Socrata de datos.gov.co (dataset `gdxc-w37w`) | API JSON directa, confirmada y estable | 🟢 Implementada | ✅ `divipola` — ver `src/extractors/divipola_extractor.py` |
| Geografía (geometría de polígonos municipales) | IGAC, vía servicio ArcGIS REST "MunicipiosSNR" de la Superintendencia de Notariado y Registro (antes: mirror DANE/MGN en HDX) | **Confirmado en vivo 2026-11-05** vía ArcGIS REST (`services2.arcgis.com/.../MunicipiosSNR/FeatureServer/0`), 1122 municipios, licencia CC BY 4.0. HDX (`cod-ab-col`) se abandonó: desde 2026-11 responde un reto AWS WAF a clientes no-navegador | 🟢 Fácil vía ArcGIS REST | ✅ `municipios_geometria` — ver `src/extractors/municipios_geometria_extractor.py` |
| Demografía (censo/proyecciones) | DANE, proyecciones de población municipal 2018-2042 | **URL exacta confirmada en vivo 2026-10-18**: `dane.gov.co/files/censo2018/proyecciones-de-poblacion/Municipal/PPED-AreaMun-2018-2042_VP.xlsx` (xlsx directo, HTTP 200, hoja `PobMunicipalxÁrea`) | 🟡 Fácil | ✅ `demografia` — ver `src/extractors/demografia_extractor.py` |
| Educación (directorio de establecimientos) | MinEducación (MEN) | **Confirmado en vivo 2026-10-18**: `datos.gov.co/resource/cfw5-qzt5.json` (CC BY-SA 4.0 explícito). 606206 filas, 2015-2025, paginado — ~360MB/~7min por build. Defecto conocido de la fuente: `codigo_dane` tiene baja cardinalidad en 2023 (ver `docs/datasets/educacion_establecimientos.md`) | 🟡 Fácil | ✅ `educacion_establecimientos` — ver `src/extractors/educacion_establecimientos_extractor.py` |
| Educación (Saber 11, ICFES) | ICFES | **Confirmado en vivo 2026-10-21**: `datos.gov.co/resource/kgxf-xxbe.json` (CC BY-SA 4.0). 7109704 filas de microdato (2010-2022) agregadas por `(codigo_dane_establecimiento, periodo)` — join directo hacia `educacion_establecimientos` — a 105110 filas publicadas. Paginado por keyset (`:id`), no `$offset` (~7x más rápido a esta escala, ver docstring del extractor) | 🟡 Fácil (acceso) | ✅ `educacion_saber11` — ver `src/extractors/educacion_saber11_extractor.py` |
| Calidad del aire | IDEAM, vía datos.gov.co (no SISAIRE directo) | **Confirmado en vivo 2026-10-22**: `datos.gov.co/resource/kekd-7v7h.json` ("Calidad del Aire en Colombia (Promedio Anual)", CC BY-SA 4.0, atribución IDEAM). 30665 filas totales, 2011-2025, 513 estaciones, 344 municipios. Se publican solo los 6 contaminantes del ICA (PM10/PM2.5/SO2/O3/NO2/CO, ~15600 filas de microdato) — las 14 variables meteorológicas y PST/NO quedan fuera, documentado como alcance. Defecto real de la fuente: ~6600 combinaciones estación+contaminante+ventana+año vienen publicadas DOS VECES — colapsadas a 8985 filas publicadas | 🟡 Media (curación de variables, no de acceso) | ✅ `calidad_aire` — ver `src/extractors/calidad_aire_extractor.py` |
| Vivienda / edificación | DANE / Camacol | Boletines + censo (Excel) | 🟡 Media | ⬜ No implementada |
| Pobreza | DANE (monetaria / multidimensional) | **Investigado 2026-10-22**: no hay tasa de pobreza municipal anual en datos.gov.co — la pobreza monetaria/multidimensional del DANE solo se calcula a nivel municipal en años censales (2005, 2018), y el dato anual (GEIH) es departamental/13 ciudades, no municipal. **Opción concreta (auditoría 2026-11-11, pendiente de decisión del mantenedor)**: publicar el IPM municipal como *snapshot censal* (2005/2018), documentado como tal, no como serie anual. **Ojo, verificado en vivo 2026-11-11**: `qgpk-sefn` ("Incidencia de la pobreza multidimensional, según municipio 2005") es de tipo `federated_href` en datos.gov.co — un enlace al geoportal del DANE (`cdge.dane.gov.co/maps/...`), no una tabla: la API Socrata responde `no row or column access to non-tabular tables`. El snapshot tendría que salir del archivo que publica el DANE, no de Socrata | 🟡 Media / requiere diseño de alcance | ⬜ No implementada |
| Consumo eléctrico | XM (operador del mercado eléctrico) / UPME | **Confirmado en vivo 2026-11-11**: XM publica una API pública sin usuario ni clave, documentada en [EquipoAnaliticaXM/API_XM](https://github.com/EquipoAnaliticaXM/API_XM) (la licencia MIT cubre el código del cliente, **no necesariamente los datos** — términos de uso de los datos sin confirmar). Endpoints: `POST https://servapibi.xm.com.co/{hourly,daily,monthly}` y `POST https://servapibi.xm.com.co/lists` (con `{"MetricId":"ListadoMetricas"}` devolvió HTTP 200 y el catálogo de métricas, p. ej. `DemaReal` por `Sistema`, `MaxDays: 31`; un `GET` a `/lists` responde 405). Cliente oficial: `pip install pydataxm`. SiMEM: `https://www.simem.co/backend-files/api/PublicData?datasetid={id}` (HTTP 200 con `datasetid=ec6945`, "Precio de bolsa horario"). Límites de rango de fechas por consulta (ver "Restricciones" del README de XM). Granularidad sistema/agente/área, **no municipio**: la demanda eléctrica por municipio sigue sin fuente | 🟢 Fácil para series nacionales (términos de los datos por confirmar); municipal: sin fuente | ⬜ No implementada |
| Macroeconomía (TRM) | Superintendencia Financiera (metodología Banco de la República) | **Confirmado en vivo 2026-10-22**: `datos.gov.co/resource/32sa-8pi3.json` (CC BY-SA 4.0). 8372 filas, 1991 a la fecha, serie diaria sin dimensión territorial — la fuente más simple del catálogo | 🟢 Fácil | ✅ `macroeconomia_trm` — ver `src/extractors/macroeconomia_trm_extractor.py` |
| Macroeconomía (otros indicadores: DTF, IBR, UVR) | Banco de la República — API SDMX (`totoro.banrep.gov.co`); datos.gov.co solo enlaza | **Corregido 2026-11-11 (ver #13)**: `gtwv-4pxq`, `ev8i-uzwt` y `mtic-nvgq` **no son tablas** — en datos.gov.co son de tipo `href` (enlaces a banrep.gov.co), y la API Socrata responde `no row or column access to non-tabular tables` (verificado en vivo 2026-11-11). El "mismo patrón que TRM" no aplica. La vía real es la API SDMX 2.1 de BanRep: `https://totoro.banrep.gov.co/nsi-jax-ws/rest/dataflow/all/all/latest` respondió HTTP 200 (2026-11-11) con los dataflows `DF_DTF_DAILY_HIST`, `DF_IBR_DAILY_HIST`, `DF_UVR_DAILY_HIST` (y variantes `_LATEST`/mensuales); solo XML SDMX (detalle de series y filtros en #16). El portal de series de BanRep migró a SUAMECA (`https://suameca.banrep.gov.co/estadisticas-economicas/home`), sin API documentada (no respondió desde el entorno de la auditoría, 2026-11-11). Licencia: datos.gov.co lista CC BY-SA 4.0 para estos enlaces; términos de la API SDMX sin confirmar | 🟡 Media (API SDMX en XML, licencia por confirmar) | ⬜ No implementada |
| Infraestructura urbana / puntos de interés | OpenStreetMap, vía extracto Geofabrik | **Confirmado en vivo 2026-10-20**: `download.geofabrik.de/south-america/colombia-latest.osm.pbf` (~332MB, ODbL 1.0, © OpenStreetMap contributors). Filtrado con pyosmium (`FileProcessor` + `KeyFilter` a nivel C++, ~5s en vez de ~25min) por lista curada de `amenity`/`shop`; geocodificado con join espacial contra `municipios_geometria`. 58046 filas publicadas (58494 nodos clasificados, ~450 excluidos por geocodificación) | 🟡 Media (geoprocesamiento) | ✅ `infraestructura_poi` — ver `src/extractors/infraestructura_poi_extractor.py` |
| Economía municipal / finanzas territoriales | DNP Terridata (basado en el FUT) | Sin API confirmada; solo descarga web por año (2000-2024) | 🟠 Difícil (requiere scraping) | ⬜ No implementada |
| Finanzas territoriales (alternativa a TerriData) | Contaduría General de la Nación — CHIP / FUT | `https://www.chip.gov.co/` responde HTTP 200 (2026-11-11), pero es un portal de consulta interactivo: no se encontró API ni descarga masiva. Evaluar como alternativa a TerriData, que tampoco tiene API | 🟠 Difícil (probable scraping) | ⬜ No implementada |
| Salud | MinSalud — REPS (Registro Especial de Prestadores) / SISPRO | **REPS nacional confirmado en vivo 2026-11-11**: `datos.gov.co/resource/c36g-9fc2.json` ("Registro Especial de Prestadores y Sedes de Servicios de Salud", MinSalud, CC BY-SA 4.0), HTTP 200, 76821 filas (sedes), con `codigoprestador`, `codigohabilitacionsede`, `municipio_prestador`, `naturalezajuridica`. El portal REPS (`https://prestadores.minsalud.gov.co/habilitacion/`) no respondió desde el entorno de la auditoría (conexión reseteada, 2026-11-11). MinSalud declara 35 conjuntos con sello de excelencia en datos.gov.co (no verificado uno por uno). Servicios habilitados por sede: buscar si hay conjunto nacional hermano. SISPRO (bodega de datos) sigue sin API pública clara | 🟡 Media (REPS: Socrata nacional); 🟠 Difícil (SISPRO) | ⬜ No implementada |
| Clima | IDEAM, vía datos.gov.co (+ descargas masivas y portal DHIME) | IDEAM tiene un [manual oficial (dic. 2023)](https://ideam.gov.co/sites/default/files/transparencia/planeacion/manual_consumo_de_datos.pdf) para consumir sus datos hidrometeorológicos vía la API Socrata (el PDF respondió HTTP 200 el 2026-11-11). **Confirmados en vivo 2026-11-11** (CC BY-SA 4.0, mismo esquema `codigoestacion`/`fechaobservacion`/`valorobservado`/`municipio`/`latitud`/`longitud`): `uext-mhny` (humedad del aire, ejemplo del manual), `s54a-sgyg` (precipitación), `sbwg-7ju4` (temperatura ambiente), `ccvq-rp9s` (temperatura máxima), `afdg-3zpb` (temperatura mínima); además `57sv-p2fu` (datos de estaciones IDEAM y terceros) y `nsz2-kzcq` (normales climatológicas). `s54a-sgyg` respondió `service-unavailable` a un `count(*)` — volumen muy alto, habrá que agregar del lado del servidor (`$group`) o paginar por keyset. Descargas masivas documentadas: `http://bart.ideam.gov.co/PQRS/AQTSUtils/{PrecipitacionNacionalDiaria,TemperaturaNacionalDiaria,HidrologiaNacionalDiaria,MetereologiaNacionalDiaria}.zip` (sic) — documentado por la fuente, sin verificar en vivo (HTTP 503 el 2026-11-11). Portal DHIME: interactivo | 🟡 Media (volumen y curación, no acceso) | ⬜ No implementada |
| Electoral | Registraduría — Observatorio Electoral | Sin API; datos no legibles por máquina según IDEA. Alternativa: `datoselectorales.org` (MOE, sociedad civil) | 🔴 Bloqueada sin scraping serio | ⬜ No implementada |
| Delincuencia (hurto a personas) | Policía Nacional, vía Ministerio de Defensa | **Confirmado en vivo 2026-10-19**: `datos.gov.co/resource/4rxi-8m8d.json` (CC BY-SA 4.0). 651200 filas ya agregadas por fecha + municipio, 2003 a la fecha, ~1.5 min por build. Defecto conocido de la fuente: 2008 casi sin desagregación municipal (365 filas "SIN ESTABLECER", excluidas — ver `docs/datasets/delincuencia_hurto_personas.md`) | 🟡 Fácil | ✅ `delincuencia_hurto_personas` — ver `src/extractors/delincuencia_hurto_personas_extractor.py` |
| Delincuencia (lesiones personales) | Policía Nacional (DIPON), vía datos.gov.co | **Confirmado en vivo 2026-10-19**: `datos.gov.co/resource/72sg-cybi.json` (CC BY-SA 4.0). 1381416 filas, 2010 a la fecha, con conducta, arma, género y grupo etario; `codigo_dane` de 8 dígitos (municipio + centro poblado) que se colapsa a municipio → ~1377323 filas, ~1 min por build. Mezcla lesiones dolosas y culposas en tránsito (columna derivada `tipo_lesion`) — ver `docs/datasets/delincuencia_lesiones_personales.md` | 🟡 Media (normalización de códigos) | ✅ `delincuencia_lesiones_personales` — ver `src/extractors/delincuencia_lesiones_personales_extractor.py` |
| Delincuencia (hurto por modalidades) | Policía Nacional (DIPON), vía datos.gov.co | **Confirmado en vivo 2026-10-20** (CC BY-SA 4.0): `datos.gov.co/resource/6sqw-8cg5.json` (653384 filas crudas; residencias y entidades comerciales). Mismo formato que lesiones: microdato por hecho, `codigo_dane` de 8 dígitos y nombres con sufijo "(CT)" | 🟡 Media (normalización de códigos; reusó la de lesiones) | ✅ `delincuencia_hurto_modalidades` — ver `src/extractors/delincuencia_hurto_modalidades_extractor.py` |
| Agro (Evaluaciones Agropecuarias Municipales, EVA) | MinAgricultura (2007-2018) / UPRA (2019 en adelante) | **Confirmado en vivo 2026-11-11** (CC BY-SA 4.0): `datos.gov.co/resource/2pnw-mmge.json` (MinAgricultura, serie 2007-2018, sin actualizar desde 2019-11) y `datos.gov.co/resource/uejq-wxrr.json` ("EVA 2019 - 2025. Base Agrícola", UPRA, 166732 filas, con `c_digo_dane_municipio`, `cultivo`, `a_o`, `periodo`). Las dos series tienen esquemas distintos: unirlas es trabajo de curación. UPRA ejecuta las EVA desde 2019 (https://upra.gov.co/en/eva) | 🟢 Fácil (acceso) / 🟡 Media (unir las dos series) | ⬜ No implementada |
| Contratación pública (SECOP II) | Colombia Compra Eficiente (ANCP-CCE) | datos.gov.co, actualización diaria. Contratos: `datos.gov.co/resource/jbjy-vk9h.json` ("SECOP II - Contratos Electrónicos", CC BY-SA 4.0) — **confirmado en vivo 2026-11-11** (HTTP 200 con `$limit=1`; un `count(*)` respondió `service-unavailable` por volumen). [Índice oficial de conjuntos](https://www.colombiacompra.gov.co/archivos/app-datos-abiertos/secop-ii) (HTTP 200). Publicar agregado (entidad × municipio × año), no el microdato completo; paginación por keyset | 🟡 Media (volumen) | ⬜ No implementada |
| Seguridad (homicidios y otros delitos) | Policía Nacional, vía Ministerio de Defensa (misma familia que `delincuencia_hurto_personas`) | **Confirmados en vivo 2026-11-11** (todos CC BY-SA 4.0, HTTP 200, mismo esquema `fecha_hecho`/`cod_depto`/`cod_muni`/`cantidad` que `4rxi-8m8d`): `m8fd-ahd9` HOMICIDIO (345195 filas, 2003-01-01 a 2026-09-30, con `sexo`, `arma_medio`, `zona`), `uav5-b85g` homicidio en accidente de tránsito, `u8eq-92tb` masacres (`casos`/`victimas`), `bz43-8ahq` delitos sexuales (451146 filas), `gepp-dxcs` violencia intrafamiliar (675813), `q2ib-t9am` extorsión (132453), `d7zw-hpf4` secuestro (10449), `csb4-y6v2` hurto a vehículos (389928; un `$limit=1` dio HTTP 500 intermitente), `p88b-5ac7` abigeato, `7i2x-h5vp` hurto a comercio (se solapa con `delincuencia_hurto_modalidades`), `yi5j-5fe9` terrorismo, `sutf-7dyz` piratería terrestre. Hay también una familia DIPON con el formato de `delincuencia_lesiones_personales` (`fpe5-yrmw` delitos sexuales, `vuyt-mqpw` violencia intrafamiliar, `ha6j-pa2r` homicidios en tránsito, `37p5-impc` terrorismo): elegir una familia por delito y documentar por qué | 🟢 Fácil (mismo patrón que `delincuencia_hurto_personas`) | ⬜ No implementada |
| Educación superior (SNIES) | MinEducación — SNIES | Portal de datos abiertos `https://snies.mineducacion.gov.co/portal/ESTADISTICAS/Datos-abiertos/` y "Bases consolidadas" responden HTTP 200 (2026-11-11), pero los archivos por año (XLSX) están detrás de páginas del portal: no se extrajo un enlace de descarga directa estable. En datos.gov.co, `n5yy-8nav` ("MEN_INSTITUCIONES EDUCACIÓN SUPERIOR") existe (CC BY-SA 4.0) pero la API respondió `internal-error` el 2026-11-11 | 🟡 Media | ⬜ No implementada |
| Biodiversidad (registros biológicos) | SiB Colombia, vía API de GBIF | **Confirmado en vivo 2026-11-11**: `https://api.gbif.org/v1/occurrence/search?country=CO` (HTTP 200, JSON). Para volumen, descargas asíncronas de GBIF (requieren cuenta GBIF). Licencia **por registro** (CC0 / CC BY / CC BY-NC): excluir CC BY-NC. Publicar conteos municipio × grupo taxonómico con join espacial contra `municipios_geometria` | 🟡 Media | ⬜ No implementada |
| Empresas (Supersociedades) | Superintendencia de Sociedades | Portal `https://www.supersociedades.gov.co/datos-abiertos` (1.000 empresas más grandes, estados financieros por grupo NIIF) — documentado por la fuente, sin verificar en vivo (sin respuesta del servidor, 2026-11-11). **Sí confirmado en vivo 2026-11-11** en datos.gov.co (Supersociedades, CC BY-SA 4.0): `pfdp-zks5` (estado de situación financiera NIIF), `prwj-nzxa` (estado de resultado integral), `ctcp-462n` (flujo de efectivo), `6hqw-m3dm` (carátula) | 🟡 Media | ⬜ No implementada |

> Esta tabla se investigó por búsqueda web además de verificación directa de
> endpoints (curl/fetch). Las filas de geografía (ambas), demografía,
> educación, delincuencia e infraestructura/POIs se verificaron **en vivo**
> (HTTP 200 o redirect válido) el 2026-10-17, cruzando hallazgos con el
> proyecto hermano `vivireneloriente` (ver su `config/fuentes.yaml` y
> `docs/decisions/` para el detalle de cómo verificó cada una originalmente).
> Las demás filas **no están verificadas contra código real** y pueden estar
> desactualizadas. Verificar en vivo no es lo mismo que implementar: antes de
> escribir el extractor, sigue confirmando el esquema completo y los límites
> de paginación con `/next-source` o manualmente.
>
> **Auditoría 2026-11-11**: las filas de consumo eléctrico, DTF/IBR/UVR,
> pobreza, salud y clima, y las filas nuevas (finanzas territoriales vía
> CHIP, agro, contratación pública, seguridad, educación superior,
> biodiversidad, empresas) se revisaron con `curl` ese día. Cada celda
> dice explícitamente qué respondió en vivo y qué quedó como
> "documentado por la fuente, sin verificar en vivo" — no son lo mismo.

## Por qué geografía fue primero

`divipola` (departamento + municipio, con nombre y centroide) es la tabla base
de códigos territoriales sobre la que se hace join con casi todas las demás
capas futuras (demografía, educación, pobreza, salud...). Es también la
fuente con el acceso más estable y confirmado de todo este mapeo: API JSON
pública y documentada, sin scraping.

**Decisión de alcance (2026-10-17)**: la primera iteración de `divipola` NO
incluye la geometría de polígonos del MGN (solo centroides lat/lon). El
mecanismo de descarga directa y estable del MGN por vigencia en el Geoportal
del DANE no se pudo confirmar sin JavaScript durante esta sesión (ver
intentos en el historial de la sesión que creó este archivo). Agregar la
geometría de polígonos es candidata a **segunda iteración de la misma fuente**
(no una fuente nueva), una vez se confirme un mecanismo de descarga
reproducible (shapefile versionado, servicio ArcGIS/WFS, o espejo estable).
Si investigas esto, documenta el hallazgo aquí antes de implementar.

**Actualización (2026-10-17)**: se encontró y verificó en vivo un espejo
estable — HDX (Humanitarian Data Exchange) redistribuye el shapefile ADM2
del DANE con descarga directa (sin JS) y licencia CC BY-IGO. Ver la fila de
geometría en la tabla arriba. Sigue siendo segunda iteración de `divipola`,
no fuente nueva — pero el bloqueo original (sin mecanismo de descarga
confirmado) ya no aplica.

**Actualización (2026-11-05)**: HDX empezó a responder un reto AWS WAF
(HTTP 202) en vez del shapefile. El extractor migró al servicio ArcGIS
REST "MunicipiosSNR" (IGAC, vía SNR), licencia CC BY 4.0 — ver
`docs/datasets/municipios_geometria.md`.

**Actualización (2026-10-20)**: implementada como `municipios_geometria`,
dataset separado de `municipios` (mismo `cod_mpio` como join key) para no
cargarle a quien solo necesita nombre/centroide con el peso de los
polígonos — ver `docs/datasets/municipios_geometria.md`.

## Cómo agregar la siguiente fuente

1. Corre `/next-source` — lee esta tabla, propone la fuente candidata (menor
   dificultad entre las no implementadas) y arranca la skill `new-source`
   sobre ella.
2. O manualmente: elige una fila 🟢/🟡, verifica su endpoint/URL actual, y usa
   la skill `new-source` (`.claude/skills/new-source/SKILL.md`) con el nombre
   de la fuente y su URL.
3. Al terminar: marca la fila como implementada en esta tabla, con el link al
   extractor correspondiente (mismo formato que la fila de geografía).

## Fuentes rechazadas o en pausa

Cuando se descarte una fuente candidata (ej. por licencia restrictiva o
acceso irrecuperable), documenta el motivo en esta tabla en vez de borrar
la fila de arriba — y no la re-audites después sin evidencia nueva.

| Fuente | Estado | Motivo |
|---|---|---|
| Intégrame (MinEnergía) | Rechazada | Pide registro de usuario — el proyecto solo consume fuentes sin credenciales |
| SISBEN | Rechazada | Datos personales. Solo se considerarían agregados que la propia entidad publique |
| RUES (consulta detallada) | Rechazada | Consulta por empresa con datos personales y acceso con tarifa. Solo agregados publicados |
| RUNT (consultas individuales) | Rechazada | Consulta individual por placa/persona, con reserva. Solo agregados publicados |
| DIAN (declaraciones) | Rechazada | Información con reserva tributaria. Solo agregados publicados |
| Registro civil | Rechazada | Datos personales con reserva. Solo agregados publicados (p. ej. estadísticas vitales del DANE) |
| HDX `cod-ab-col` (geometría ADM2) | En pausa (reemplazada) | Desde 2026-11 responde un reto AWS WAF a clientes no-navegador. `municipios_geometria` migró a ArcGIS SNR — ver la [fila de geometría](#tabla-de-fuentes) y la actualización 2026-11-05 más abajo |
