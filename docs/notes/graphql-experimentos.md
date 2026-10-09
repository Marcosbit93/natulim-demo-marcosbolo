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

Pendiente (próxima sesión): correr `cost-deep` (tres niveles de listas) para provocar `MAX_COST_EXCEEDED`, y mirar el encabezado `Shopify-GraphQL-Cost-Debug: 1` para ver el costo campo por campo.

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

Hipótesis a descartar (próxima sesión, `experimentos.py idempotency-literal`): que la clave no se aplique cuando viaja como variable `$key` (la clase avisa que algunas versiones piden escribirla como texto en la consulta), o que la validación de `changeFromQuantity` se evalúe antes de la capa de idempotencia.

Datos de la documentación de Shopify para tener presentes: las claves se recuerdan 24 horas; la misma clave con parámetros distintos falla con `IDEMPOTENCY_KEY_PARAMETER_MISMATCH`; una operación aún en curso devuelve `IDEMPOTENCY_CONCURRENT_REQUEST`.
