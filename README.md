# Tesorería proveedores de surtido

Herramienta web que estima la caja que necesitaría Reynasa si compra a los proveedores de surtido de la red Aurgi/Motortown a sus plazos de pago actuales y revende a la red cobrando a 60 días (o a los días que se elijan).

La web se publica con GitHub Pages desde este repositorio.

## Cómo se calcula

Necesidad = stock + cobros pendientes − pagos pendientes

- Cobros pendientes de la red = venta a la red × días de cobro / 365. La venta a la red es la compra más el margen de Reynasa (0 % por defecto).
- Pagos pendientes a proveedores = compra × días de pago / 365, proveedor a proveedor.
- Stock = valor a precio medio de lo que hay en almacén central (centro 20) y centros de los artículos de cada proveedor. Se puede limitar al almacén central.
- Cifra positiva: caja que Reynasa tendría que poner. Negativa: excedente.

Es una foto en régimen: supone que Reynasa revende lo mismo que compra y que la compra se reparte igual a lo largo del año.

## Qué se puede cambiar en la web

- Días de cobro a la red, margen, IVA y si el stock que se financia es todo o solo el del almacén central.
- Días de pago de cada proveedor (vacío = los de Navision).
- Quitar proveedores del cálculo.

Estos cambios se guardan en el navegador de cada persona y no afectan a los demás. «Volver a los datos de Navision» los deshace.

## Datos

| Fichero | Qué contiene | Quién lo cambia |
|---|---|---|
| proveedores-surtido.json | Lista de proveedores: nº de Navision, nombre, categoría y lo que figura en la hoja de compras (compra de surtido, días y forma de pago) | Se edita a mano |
| proveedores.json | Compra de 12 meses, compra que entra en almacén central, plazo y forma de pago, bloqueo y stock de cada proveedor | La actualización nocturna |

Origen: Navision/Business Central consultado a través de Metabase (base de datos 6, DCBigQuery).

- Compra: mercancía recibida en los últimos 12 meses hasta ayer, a coste y sin IVA, facturada y pendiente de facturar (movimientos de valor de compra).
- Plazo y forma de pago: ficha del proveedor.
- Stock: última foto diaria de stock. Cada artículo se asigna al proveedor al que más se le ha comprado en los últimos 24 meses.

Para añadir o quitar un proveedor para todos, edita proveedores-surtido.json en GitHub (lápiz de editar), añade o borra su línea con el mismo formato y guarda. Sus datos llegan con la actualización de esa noche, o antes si se lanza a mano.

## Actualización nocturna

El workflow «Actualizar datos y publicar» (.github/workflows/publicar.yml):

1. Cada noche a las 02:17 UTC ejecuta actualizar-datos.py, que consulta Metabase y reescribe proveedores.json.
2. Si los datos han cambiado, los guarda en el repositorio.
3. Publica la web en GitHub Pages.

También se puede lanzar a mano desde la pestaña Actions → «Actualizar datos y publicar» → Run workflow. Cada cambio que se guarde en la rama main vuelve a publicar la web, sin consultar Metabase.

### Puesta en marcha (una sola vez)

1. En Metabase (reports.autingo.es), un administrador crea una API key en Admin → Settings → Authentication → API keys, asignada a un grupo con permiso de consultas SQL sobre la base de datos DCBigQuery.
2. En este repositorio: Settings → Secrets and variables → Actions → New repository secret, con nombre METABASE_API_KEY y la clave como valor.
3. Opcional: si Metabase cambia de dirección, crear en la misma pantalla una variable METABASE_URL.
4. Lanzar el workflow a mano una vez y comprobar que termina en verde.

Sin el secreto, el workflow publica la web con los últimos datos guardados y avisa de que no ha actualizado. Si Metabase no acepta conexiones desde los servidores de GitHub, el paso de actualización fallará: los datos publicados no se tocan y GitHub avisa por correo del fallo.

## Ficheros

- index.html: la web.
- proveedores-surtido.json y proveedores.json: datos.
- actualizar-datos.py: script de actualización; solo usa la librería estándar de Python.
- .github/workflows/publicar.yml: actualización nocturna y publicación.

## Aviso

El repositorio es público: cualquiera con el enlace ve la compra, el stock y las condiciones de pago de cada proveedor.
