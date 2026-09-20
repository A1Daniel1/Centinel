# Modelo C4 — Diagramas de Arquitectura

Diagramas del modelo C4 para la **Plataforma de Monitoreo Territorial** (detección temprana de
deforestación, minería ilegal de oro y cultivos de coca por imágenes satelitales).

Esta carpeta **reemplaza** los diagramas anteriores del entregable. El motivo está documentado abajo:
aquellos diagramas no eran C4 correcto y no mostraban alta disponibilidad ni escalabilidad.

---

## 1. Contenido

| Archivo | Nivel C4 | Qué muestra |
| --- | --- | --- |
| `01-nivel1-contexto.puml` | **Nivel 1 — Contexto** | Alcance del sistema, actores y sistemas externos con los que intercambia datos |
| `02-nivel2-contenedores.puml` | **Nivel 2 — Contenedores** | Los contenedores desplegables, con réplicas, política de autoescalado y zonas |
| `03-nivel3-componentes-inferencia.puml` | **Nivel 3 — Componentes** | Los componentes **dentro de un solo contenedor**: `Multi-Label Inference Service` |
| `04-nivel4-codigo.puml` | **Nivel 4 — Código** | Clases e interfaces que sostienen el componente de inferencia |
| `05-despliegue-ha.puml` | **Despliegue** | Topología física: nube → región → VPC → 3 zonas de disponibilidad → cargas, más región de DR |

Cada `.puml` se renderiza a `.png` (revisión rápida) y `.svg` (vectorial, para el informe).

## 2. Por qué se rehicieron los diagramas anteriores

| Defecto del modelo anterior | Corrección |
| --- | --- |
| El "Nivel 3" mezclaba los componentes del pipeline con nodos que **no eran componentes de ese contenedor** (PostGIS, Object Storage, broker, observabilidad) | El Nivel 3 ahora describe **un único contenedor** y los sistemas externos aparecen fuera del boundary |
| No existía Nivel 4 | Se agregó el diagrama de código |
| No existía diagrama de despliegue | Se agregó, con topología multi-AZ y región de recuperación |
| El layout era una grilla forzada para evitar solapamientos | Layout producido por PlantUML/Graphviz con notación C4 canónica |
| **La alta disponibilidad no se veía** | Réplicas, autoescalado, multi-AZ, failover y DR son explícitos en los niveles 2 y de despliegue |
| Los costos no reflejaban la topología | Ver §5: la tabla de costos del entregable **no paga** la HA que declara |

## 3. Alta disponibilidad

### 3.1 Objetivos

| Objetivo | Valor | Alcance |
| --- | --- | --- |
| Disponibilidad de la API de alertas | **99,9 %** mensual | Extremo a extremo, excluyendo mantenimiento anunciado |
| Disponibilidad del pipeline de ingesta | **99,5 %** mensual | Ventanas de pasada satelital |
| RPO intra-región (base de datos) | **≈ 0** | Réplica síncrona |
| RTO intra-región | **< 2 min** | Conmutación automática gestionada |
| RPO / RTO regional | **15 min / 4 h** | Pérdida de la región primaria |
| Frescura de alerta | **p95 ≤ 48 h** | Hito desde la captura satelital |

### 3.2 Cómo se sostiene

1. **Ningún componente es punto único de falla.** Los servicios son **sin estado**: no guardan sesión
   ni estado de conversación, así que cualquier réplica atiende cualquier petición y el balanceador
   puede sacar de rotación una zona completa sin intervención.
2. **Spread real entre zonas.** Las réplicas se reparten con `anti-affinity` por zona; no alcanza con
   tener 3 réplicas si las tres caen en el mismo host o en la misma AZ.
3. **Base de datos con réplica síncrona y conmutación automática.** RPO ≈ 0 intra-región y RTO bajo,
   sin operación manual ni ventana de mantenimiento. Las **réplicas de lectura** absorben la carga
   analítica y de consulta, que en este dominio es la dominante.
4. **Bus de eventos como log replicado, no como cola en memoria.** Con factor de replicación 3 y un
   broker por zona, la caída de un broker no pierde eventos y el reproceso es posible. Es la decisión
   de HA más importante del pipeline: una cola en memoria durante una pasada satelital perdería escenas.
5. **Salida a internet independiente por zona.** Cada AZ tiene su propio NAT Gateway: una zona caída
   no aísla a las demás.
6. **Degradación definida, no falla total.** Si la capacidad GPU se agota, el sistema no deja de
   producir: la cola crece y la frescura de alerta se degrada de forma acotada y observable, en lugar
   de perder trabajos.

## 4. Escalabilidad

| Mecanismo | Detalle |
| --- | --- |
| **Autoescalado por la señal correcta** | Profundidad de **cola** en el pipeline, **RPS/latencia** en la API, **utilización de GPU** en inferencia. Escalar por CPU en un pipeline limitado por I/O y GPU reaccionaría tarde |
| **Ráfagas de pasada satelital** | La carga no es uniforme: llega en ventanas. El bus desacopla el pico del consumo, y los nodos **spot** absorben la ráfaga a menor costo |
| **Particionado por tile** | El bus se particiona por `tile`, así los consumidores escalan en paralelo sin coordinación |
| **Escalado de datos** | PostGIS particionado por tiempo y territorio; índice vectorial particionado y reconstruible; objetos con ciclo de vida a capas frías |
| **Escalado a cero** | El pool GPU se apaga entre ciclos: es la palanca de costo más importante del piloto |

---

## 5. Validación de costos — hallazgo principal

> **Todas las cifras son estimaciones de ingeniería en USD/mes**, con precios de referencia *on-demand*
> de nube pública (región `us-east-1`, tarifas aproximadas a 2026). **No son cotizaciones.**
> Base de comparación: §5.1 del documento `executive-review-II.md`.

### 5.1 El problema

La sección 5.1 del entregable declara una base de datos `Multi-AZ`, pero **su tabla de costos no
incluye los elementos que la alta disponibilidad exige**. La HA se declara en la arquitectura y no se
paga en el presupuesto: son dos afirmaciones incompatibles.

### 5.2 Delta de producción para sostener la HA declarada

| Concepto | Costo declarado | Con HA real | Δ USD/mes | Por qué |
| --- | --- | --- | --- | --- |
| Base de datos Multi-AZ (primario + standby) | 847 | 847 | — | Ya estaba bien dimensionado |
| **Réplicas de lectura ×2** (`db.r6g.xlarge`) | 0 | 423 | **+423** | El §5.1 promete "2 réplicas de lectura" pero no las costea |
| **Bus de eventos: 3 brokers** (`Amazon MSK`) | 200 | 490 | **+290** | Cambiar de una cola gestionada pequeña a un **log replicado 3× en 3 AZ** es lo que compra la no-pérdida de eventos, y cuesta más |
| **NAT Gateway por zona ×3** | ~66 (uno) | ~197 (tres) | **+131** | El aislamiento por zona exige una puerta de salida por AZ |
| **GPU base en una segunda zona** | 604 | 1.338 | **+734** | El §5.1 asume "escalado a cero" puro. Con GPU solo en una AZ, la caída de esa zona detiene la inferencia: la HA real exige capacidad base en ≥ 2 zonas |
| **Plano de control de EKS** | no declarado | 73 | **+73** | Línea ausente en la tabla |
| **DR: clúster tibio + snapshots + CRR** | 0 | ~270 | **+270** | La región de recuperación del diagrama de despliegue no tenía costo asignado |
| **Subtotal de infraestructura** | **~5.051** | **~6.972** | **≈ +1.921 (+38 %)** | |

**Lectura:** la alta disponibilidad multi-AZ **no es gratis ni marginal**. Cuesta cerca de un **38 %
adicional** sobre la infraestructura de producción, y la partida más grande es la **GPU base en una
segunda zona** (+734), seguida de las réplicas de lectura (+423).

### 5.3 Las dos decisiones que mueven ese número

1. **HA de GPU: pagar o degradar.** Mantener una GPU base en dos zonas cuesta **+734 USD/mes**.
   La alternativa honesta es aceptar que la caída de la zona primaria deja la inferencia en cola
   hasta que la zona secundaria escale: **no se pierden trabajos, pero la frescura de alerta se
   degrada**. Es una decisión de negocio, no técnica, y debe estar explícita.
2. **HA de red: aislar zonas o aceptar acoplamiento.** Tres NAT Gateway cuestan **+131 USD/mes** más
   procesamiento de datos. Con una sola puerta, su caída aísla la región entera.

### 5.4 Piloto: ¿necesita HA?

**Recomendación: no.** El piloto es una validación de la hipótesis de clasificación, no un servicio en
producción. Correrlo multi-AZ con GPU base en dos zonas costaría **≈ +1.161 USD/mes** y no aporta nada
a la pregunta que el piloto debe responder.

La consecuencia es importante y debe declararse en el entregable: **el piloto no valida la alta
disponibilidad**. La HA se valida en un ambiente de *staging* antes de producción, con pruebas de
conmutación (chaos/failover drills) que no forman parte del alcance del piloto.

### 5.5 Cómo se recupera parte del delta

| Palanca | Ahorro estimado | Nota |
| --- | --- | --- |
| *Savings plans* / instancias reservadas sobre la carga base (nodos CPU y base de datos) | 20–40 % de esas líneas | Aplicable una vez estabilizada la operación, no en el piloto |
| Nodos *spot* para la ráfaga de ingestión y preproceso | Ya aplicado parcialmente | Tolerable porque son etapas reintentables e idempotentes |
| Escalado a cero agresivo fuera de ventanas de pasada | Ya aplicado | La ráfaga es predecible por efemérides satelitales |
| CRR selectivo: replicar productos derivados y una submuestra de escenas, no las 60 TB | Evita ≈ 1.380 USD/mes | Replicar todo el archivo crudo entre regiones costaría ~1.380 USD/mes; el diseño replica lo necesario para recuperar operación, no para duplicar el archivo |

### 5.6 Dimensionamiento: una inconsistencia menor

El §5.1 declara **8 nodos `m6i.xlarge`** en producción. Con reparto entre 3 zonas, 8 no es divisible:
el reparto queda 3/3/2 y una zona queda con menos margen. Se recomienda **9 (3 por zona)** por
simetría, lo que agrega **≈ +140 USD/mes** y hace que la afirmación "anti-affinity por zona" sea
verificable de un vistazo.

---

## 6. Inconsistencias detectadas en el entregable

Estas no se corrigieron en esta fase (el alcance fue generar los diagramas nuevos). Quedan registradas
para que se reconcilien:

| # | Inconsistencia | Acción sugerida |
| --- | --- | --- |
| 1 | El §5.1 declara HA multi-AZ pero no costea réplicas de lectura, NAT por zona, GPU base en 2ª AZ, plano de control EKS ni la región de DR | Actualizar la tabla con el delta de §5.2 |
| 2 | El §5.1 declara "message broker gestionado pequeño/mediano" (30 / 200), pero la arquitectura ahora requiere un log replicado 3× | Reescribir la línea y su justificación |
| 3 | El §5.1 dice "8 nodos CPU" en producción; el reparto entre 3 zonas no es entero | Pasar a 9 (3 por zona) |
| 4 | El §5.1 promete "2 réplicas de lectura" y no las incluye | Alinear tabla y texto |
| 5 | La región de recuperación no tenía costo asignado | Agregar la línea de DR |

## 7. Regenerar los diagramas

Se usa **PlantUML 1.2026.8**. Comprobado: **no requiere Graphviz**; el motor embebido renderiza C4
(iconos, estereotipos `«person»` / `«system»` / `«container»` / `«component»`, paleta C4) sin `dot`.

```powershell
# PNG (revisión) y SVG (vectorial para el informe)
java -jar <ruta-a>\plantuml.jar -tsvg -tpng -charset UTF-8 -DPLANTUML_LIMIT_SIZE=16384 *.puml
```

**Trampa registrada:** el campo `release` de `maven-metadata.xml` en Maven Central para
`net.sourceforge.plantuml:plantuml` resuelve a **`8059`, una compilación de 2017** que no incluye la
librería C4. Descargar PlantUML desde el *release* de GitHub, no desde Maven Central.

## 8. Supuestos y límites

- **Los rangos de autoescalado, las métricas SLO y los precios son parámetros de diseño**, no valores
  medidos. Deben validarse con carga real del piloto y con los proveedores.
- **No se ejecutaron pruebas de conmutación (failover drills).** La disponibilidad declarada es un
  objetivo de diseño, no un resultado observado.
- **El Nivel 4 es parcial por definición:** detalla solo el contenedor de inferencia, que es el núcleo
  de IA/ML y donde vive la hipótesis del proyecto. Los demás contenedores tendrían su propio Nivel 3 y 4.
- **Los diagramas se validaron visualmente uno por uno** tras renderizarlos; un render correcto no
  garantiza por sí solo que el contenido sea correcto.
- El `legend` de PlantUML no renderizó de forma fiable en estos diagramas, por eso el texto
  explicativo vive aquí y en las notas locales, no en un bloque `legend`.
