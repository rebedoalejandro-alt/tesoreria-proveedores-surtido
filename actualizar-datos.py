#!/usr/bin/env python3
"""Actualiza proveedores.json con la compra, el plazo de pago y el stock de cada
proveedor de proveedores-surtido.json, sacados de Navision/Business Central a
traves de la API de Metabase.

Variables de entorno:
  METABASE_API_KEY      API key de Metabase (obligatoria; sin ella no se toca nada)
  METABASE_URL          por defecto https://reports.autingo.es
  METABASE_DATABASE_ID  por defecto 6 (DCBigQuery)

Solo usa la libreria estandar de Python.
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.abspath(__file__))
FICHERO_LISTA = os.path.join(RAIZ, "proveedores-surtido.json")
FICHERO_DATOS = os.path.join(RAIZ, "proveedores.json")

VE = "`autingo-159109.proxy_businesscentral365.nav_anjana_value_entry`"
VD = "`autingo-159109.proxy_businesscentral365.nav_anjana_vendor`"
ST = "`autingo-159109.anjana_bi_ntg.Stock_diario_mas_precio`"


def menos_anios(d, n):
    try:
        return d.replace(year=d.year - n)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - n, day=28)


def rangos(hoy):
    """Ultimos 12 meses cerrados hasta ayer, y 24 meses para asignar articulos a proveedor."""
    hasta = hoy - datetime.timedelta(days=1)
    desde = menos_anios(hasta, 1) + datetime.timedelta(days=1)
    desde24 = menos_anios(hasta, 2) + datetime.timedelta(days=1)
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "desde24": desde24.isoformat()}


def construir_sql(ns, r):
    lista = ",".join("'" + n + "'" for n in ns)
    return "\n".join([
        "WITH lista AS (SELECT v FROM UNNEST([" + lista + "]) v),",
        "fs AS (SELECT MAX(Fecha) AS f FROM " + ST + "),",
        "compras AS (SELECT source_no_ AS v, SUM(purchase_amount__actual_ + purchase_amount__expected_) AS compra,",
        "  SUM(IF(location_code = '20', purchase_amount__actual_ + purchase_amount__expected_, 0)) AS compra_alm",
        "  FROM " + VE + " WHERE _fivetran_deleted = FALSE AND item_ledger_entry_type = 0 AND source_type = 2",
        "  AND posting_date BETWEEN '" + r["desde"] + "' AND '" + r["hasta"] + "' GROUP BY 1),",
        "ci AS (SELECT item_no_, source_no_ AS v, SUM(purchase_amount__actual_ + purchase_amount__expected_) AS imp",
        "  FROM " + VE + " WHERE _fivetran_deleted = FALSE AND item_ledger_entry_type = 0 AND source_type = 2",
        "  AND posting_date BETWEEN '" + r["desde24"] + "' AND '" + r["hasta"] + "' GROUP BY 1, 2),",
        "pi AS (SELECT item_no_, v FROM (SELECT item_no_, v, ROW_NUMBER() OVER (PARTITION BY item_no_ ORDER BY imp DESC) rn FROM ci WHERE imp > 0) WHERE rn = 1),",
        "st AS (SELECT pi.v, SUM(IF(s.Codigo_Centro = '20', GREATEST(s.Valor_stock, 0), 0)) AS st_alm,",
        "  SUM(IF(s.Codigo_Centro != '20', GREATEST(s.Valor_stock, 0), 0)) AS st_cen",
        "  FROM " + ST + " s JOIN pi ON pi.item_no_ = s.idProducto WHERE s.Fecha = (SELECT f FROM fs) GROUP BY 1)",
        "SELECT l.v AS n, vd.name AS nombre, vd.payment_terms_code AS pt, vd.payment_method_code AS pm, vd.blocked AS b,",
        "  ROUND(IFNULL(c.compra, 0)) AS c, ROUND(IFNULL(c.compra_alm, 0)) AS ca, ROUND(IFNULL(st.st_alm, 0)) AS sa, ROUND(IFNULL(st.st_cen, 0)) AS sc,",
        "  CAST((SELECT f FROM fs) AS STRING) AS fs",
        "FROM lista l",
        "LEFT JOIN " + VD + " vd ON vd.no_ = l.v AND vd._fivetran_deleted = FALSE",
        "LEFT JOIN compras c ON c.v = l.v",
        "LEFT JOIN st ON st.v = l.v",
    ])


def consultar(url, clave, bd, sql):
    cuerpo = json.dumps({"database": bd, "type": "native", "native": {"query": sql}}).encode("utf-8")
    peticion = urllib.request.Request(
        url.rstrip("/") + "/api/dataset",
        data=cuerpo,
        headers={"Content-Type": "application/json", "x-api-key": clave},
        method="POST",
    )
    try:
        with urllib.request.urlopen(peticion, timeout=600) as resp:
            res = json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError("Metabase ha respondido %s: %s" % (e.code, e.read()[:500].decode("utf-8", "replace")))
    if res.get("status") == "failed" or res.get("error"):
        raise RuntimeError("La consulta ha fallado en Metabase: %s" % str(res.get("error"))[:500])
    datos = res.get("data") or {}
    columnas = [c.get("name") for c in datos.get("cols", [])]
    return [dict(zip(columnas, fila)) for fila in datos.get("rows", [])]


def entero(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def convertir(filas_sql):
    """Filas de Metabase -> {n: {pt, pm, b, c, ca, sa, sc}} y fecha del stock.
    No guarda el nombre del proveedor: la pagina usa el de proveedores-surtido.json."""
    filas, fecha_stock = {}, None
    for x in filas_sql:
        n = str(x.get("n") or "")
        if not re.fullmatch(r"\d{6,12}", n) or x.get("pt") is None:
            continue  # no existe en Navision
        filas[n] = {
            "pt": x.get("pt"), "pm": x.get("pm"), "b": entero(x.get("b")),
            "c": entero(x.get("c")), "ca": entero(x.get("ca")),
            "sa": entero(x.get("sa")), "sc": entero(x.get("sc")),
        }
        if x.get("fs"):
            fecha_stock = str(x["fs"])[:10]
    return filas, fecha_stock


def main():
    clave = (os.environ.get("METABASE_API_KEY") or "").strip()
    if not clave:
        print("::notice::Falta el secreto METABASE_API_KEY: los datos no se actualizan y se publica lo que ya hay.")
        return 0
    url = os.environ.get("METABASE_URL") or "https://reports.autingo.es"
    bd = int(os.environ.get("METABASE_DATABASE_ID") or 6)

    with open(FICHERO_LISTA, encoding="utf-8") as f:
        lista = json.load(f)
    ns = [str(p.get("n")) for p in lista if re.fullmatch(r"\d{6,12}", str(p.get("n", "")))]
    if not ns:
        raise RuntimeError("proveedores-surtido.json no tiene proveedores validos")

    r = rangos(datetime.date.today())
    filas, fecha_stock = convertir(consultar(url, clave, bd, construir_sql(ns, r)))
    if not filas:
        raise RuntimeError("Metabase no ha devuelto ningun proveedor")

    salida = {
        "generado": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "desde": r["desde"], "hasta": r["hasta"], "fechaStock": fecha_stock, "filas": filas,
    }
    with open(FICHERO_DATOS, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)
        f.write("\n")

    faltan = [n for n in ns if n not in filas]
    print("Actualizados %d proveedores (compras %s a %s, stock a %s)." % (len(filas), r["desde"], r["hasta"], fecha_stock))
    if faltan:
        print("::warning::No se encuentran en Navision: " + ", ".join(faltan))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # el workflow falla y se mantiene la version anterior de los datos
        print("::error::" + str(e))
        sys.exit(1)
