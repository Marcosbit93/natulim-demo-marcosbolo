# ADR 0001: Autenticación con Shopify mediante client credentials

## Contexto

La integración corre sin interfaz (server-to-server) y opera sobre una tienda
de la misma organización que la app. La documentación de Shopify no aclara si
pedir un token nuevo invalida el anterior ni cómo responde ante un secreto
incorrecto, así que se comprobó con un experimento (2 de octubre de 2026,
Admin API 2026-07).

## Decisión

Usar client credentials con renovación del token cinco minutos antes del
vencimiento. El token vive solo en memoria; el secreto y el token nunca se
escriben en logs, URLs ni mensajes de error. Las conexiones HTTPS validan el
certificado contra el almacén del sistema operativo (`truststore`), nunca con
`verify=False`.

## Consecuencias

- Solo sirve para tiendas propias; para tiendas de terceros habría que usar
  authorization code.
- Resultado del experimento 1 (dos tokens): se pidieron dos tokens seguidos
  (A y B), distintos entre sí, y después de emitir B ambos respondieron
  HTTP 200 a una consulta `shop { name }`. Pedir un token nuevo **no invalida
  el anterior**, por lo que varios procesos (por ejemplo varias Lambdas)
  pueden tener su propio token vigente a la vez.
- Resultado del experimento 2 (secreto con una letra cambiada): Shopify
  responde **HTTP 400** (no 401) con un cuerpo **HTML**, no JSON, cuyo mensaje
  es `Oauth error invalid_request: Missing or invalid client secret`. El
  cuerpo no repite el secreto. Consecuencias para el código: un secreto
  inválido es un error de configuración y no se reintenta (400), y el cliente
  no debe llamar a `response.json()` sobre una respuesta de error. El proveedor
  ya lo cumple porque lanza `ShopifyAuthError` con solo el código HTTP.
- La respuesta del token trae `expires_in` de 86.399 s y la lista de scopes
  resumida: `read_inventory` no aparece porque lo incluye `write_inventory`,
  pero sí figura en `currentAppInstallation { accessScopes }`. Los scopes
  efectivos se verifican con esa consulta y no con lo declarado.
- No verificado: qué código devuelve Shopify para un token ya vencido en una
  llamada GraphQL; hasta comprobarlo se mantiene la regla de renovar una vez
  ante 401 y no reintentar más.
