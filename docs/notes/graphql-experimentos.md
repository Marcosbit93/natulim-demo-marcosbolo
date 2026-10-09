# Clase 3 · Experimentos con la GraphQL Admin API

Tienda de desarrollo: `natulim-demo-marcosbolo`. API `2026-07`. Balde de 2000 puntos, recuperación de 100/s.

## Medición base (`scripts/explore.py`)

| Consulta | Pedido | Real | Resultado |
|---|---|---|---|
| `products` (first 5, variantes 50) | 53 | 14 | 10 productos, 1 a 5 variantes cada uno |
| `orders` (first 5, líneas 50) | 56 | 5 | sin pedidos en la tienda |
| `inventoryItems` (first 5, niveles 10) | 47 | 17 | casi todos sin SKU |

- `products(first: 50)` solo con `id title`: pedido 9, real 5 (17 productos).
- La app GraphiQL del navegador dio `ACCESS_DENIED` en orders/inventory porque es otra app, con otros scopes. Mi app (client credentials) sí tiene `read_orders`, `read_inventory`, `write_inventory`, `read_locations`.
- `InventoryItem` y `ProductVariant` tienen ids distintos: se llega al stock desde la variante con `inventoryItem { id }`.
- Casi todas las variantes tienen `sku: null`, un problema para mapear contra Odoo.

## Experimento 1 · Costo (`experimentos.py cost`)

| first productos | first variantes | Pedido | Real |
|---|---|---|---|
| 5 | 5 | 20 | 17 |
| 25 | 25 | 56 | 19 |
| 50 | 50 | 72 | 10 |
| 100 | 50 | 92 | 7 |
| 100 | 100 | 110 | 7 |
| 250 | 100 | 134 | 5 |
| 250 | 250 | 156 | 5 |

Observado:
- No llegué a `MAX_COST_EXCEEDED`: con dos niveles de listas, el pedido llegó solo a 156 (el máximo por consulta es 1000).
- El costo pedido creció mucho más despacio que el producto de los `first` (250 × 250 = 62.500).
- El costo real bajó al subir `first`, aunque la tienda es la misma (17 productos).

Según la documentación de Shopify: el costo pedido se calcula antes de ejecutar y el real con los resultados; después de ejecutar, el balde recupera la diferencia entre ambos. Los escalares cuestan 0, los objetos 1 y las conexiones se dimensionan por `first`/`last`; la doc no da una fórmula exacta ni explica el comportamiento de arriba.

### Tres niveles de listas (`experimentos.py cost-deep`)

| productos | variantes | niveles de inventario | Pedido | Real |
|---|---|---|---|---|
| 10 | 10 | 10 | 206 | 30 |
| 50 | 50 | 10 | 611 | 13 |
| 100 | 100 | 50 | rechazada: `MAX_COST_EXCEEDED` (cost 1487, maxCost 1000) | no se ejecutó |
| 250 | 250 | 250 | rechazada: `MAX_COST_EXCEEDED` (cost 3181, maxCost 1000) | no se ejecutó |

- Con tres niveles de listas sí aparece `MAX_COST_EXCEEDED`. El error trae `cost` y `maxCost` en `extensions`.
- La consulta rechazada falla antes de ejecutarse (según la doc, el límite de 1000 se evalúa con el costo pedido).

### Desglose por campo (`experimentos.py cost-debug`, encabezado `Shopify-GraphQL-Cost-Debug: 1`)

| Campo | first 5 × 5 (total pedido) | first 250 × 250 (total pedido) |
|---|---|---|
| `products.nodes.variants` | 5 | 13 |
| `products.nodes` | 6 | 14 |
| `products` | 20 | 156 |

- Los escalares (`id`) cuestan 0 y cada objeto de `nodes` cuesta 1.
- Al pasar `first` de 5 a 250 (50 veces más), el total de `variants` pasó de 5 a 13. El costo pedido NO es `first × first`.
- Sin explicar: por qué el costo real bajó (17 → 5) al subir `first`. El desglose solo muestra el costo pedido, no el real.

## Experimento 2 · Paginación con filtro (`experimentos.py filter`)

| Filtro `query` | Productos |
|---|---|
| (sin filtro) | 17 |
| `updated_at:>2026-09-01` | 17 |
| `status:draft` | 1 |
| `updated_at:>2026-10-10` | 0 |

- El filtro de septiembre no recorta nada porque todos los productos se crearon/actualizaron el 9 de octubre.
- `status:draft` aísla el producto en borrador; una fecha futura devuelve 0.
- Uso: base de la sincronización incremental (guardar la última marca de tiempo y pedir solo lo posterior).

## Experimento 3 · Idempotencia de inventario (`experimentos.py idempotency`)

Ítem con stock inicial 50.

| Paso | Qué hice | Qué pasó | Stock después |
|---|---|---|---|
| 1 | clave A, cambio 50 → 51 | Aplicado: `available` +1 y `on_hand` +1 | 51 |
| 2 | misma clave A, mismo pedido | `userErrors`: `CHANGE_FROM_QUANTITY_STALE` | 51 |
| 3 | clave B nueva, cantidad previa vieja (50) | `userErrors`: `CHANGE_FROM_QUANTITY_STALE` | 51 |

Observado:
- El cambio se aplicó una sola vez; el stock nunca pasó de 51.
- El reintento con la misma clave NO devolvió la respuesta original: devolvió `CHANGE_FROM_QUANTITY_STALE`.
- Según la documentación, un duplicado con la misma clave y el mismo contenido debería recibir la respuesta cacheada sin reprocesar la operación. Lo que vi difiere.
- Lo que sí protegió el stock fue el compare-and-set (`changeFromQuantity`), no se puede afirmar que lo haya hecho la clave de idempotencia.

Prueba con la clave escrita como texto en la consulta (`experimentos.py idempotency-literal`): resultado idéntico. El paso 2 volvió a dar `CHANGE_FROM_QUANTITY_STALE`. Queda descartado que el problema fuera pasar la clave como variable.

Hipótesis que siguen abiertas: la validación de `changeFromQuantity` se evalúa antes de la capa de idempotencia, o el reintento de una operación ya exitosa no devuelve la respuesta cacheada en esta mutación.

Experimentos propuestos para aislar la idempotencia: (1) misma clave con payload distinto, esperando `IDEMPOTENCY_KEY_PARAMETER_MISMATCH` (prueba que la capa de claves está activa); (2) `inventoryAdjustQuantities` (aplica diferencias, sin compare-and-set) dos veces con la misma clave.

Datos de la documentación de Shopify para tener presentes: las claves se recuerdan 24 horas; la misma clave con parámetros distintos falla con `IDEMPOTENCY_KEY_PARAMETER_MISMATCH`; una operación aún en curso devuelve `IDEMPOTENCY_CONCURRENT_REQUEST`.
